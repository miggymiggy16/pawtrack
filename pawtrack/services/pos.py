"""
PawTrack - point of sale logic
==============================
Only the Cashier role can sell (pos.use). Veterinary Staff has NO access to
POS or sales; only administrators can read the sales data (pos.data), void a
sale or edit services (pos.manage).

A sale deducts inventory stock, writes a "Stock Out" history row, and keeps a
snapshot of every price, so later price changes never rewrite old receipts.
"""
import json
from datetime import date
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from ..config import (MAX_SALE_LINES, MAX_SALE_QTY, PAYMENT_METHODS, VAT_PERCENT,
                      VAT_RATE)
from ..helpers import fmt_date, item_image_url, money, now_str, parse_money
from ..storage import edit, get_settings, load, lock, next_id
from .inventory import add_transaction, expiry_status


def pos_catalog():
    """What the cashier may sell: inventory items that have a selling price.
    Cost prices are never included."""
    warn = get_settings()["expiry_warning_days"]
    rows = []
    for it in load("inventory"):
        try:
            price = float(it.get("selling_price") or 0)
        except (TypeError, ValueError):
            price = 0
        if price <= 0:
            continue
        qty = it["quantity"]
        state = "out" if qty <= 0 else "expired" if expiry_status(it, warn) == "Expired" else "ok"
        rows.append({"kind": "product", "id": it["item_id"], "name": it["item_name"], "category": it["category"],
                     "unit": it["unit"], "price": price, "stock": qty, "state": state,
                     "low": 0 < qty <= it["min_stock"], "image": item_image_url(it) or ""})
    rows.sort(key=lambda r: (r["category"], r["name"].lower()))
    return rows


def _q(value):
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def vat_included(gross):
    """The VAT already sitting inside a VAT-inclusive peso amount.

    Shelf prices are tax-inclusive, so the customer never pays tax on top.
    We only work out how much of the total is VAT, to report it."""
    return _q(Decimal(str(gross)) * VAT_RATE / (Decimal("1") + VAT_RATE))


def create_sale(form, user):
    """Validate a checkout and record it. Returns (sale, error, duplicate).

    Everything the customer pays is recalculated HERE from the saved prices; the browser only
    says WHAT and HOW MANY. Stock is checked first, so a refused sale changes nothing."""
    try:
        cart = json.loads(form.get("cart", "") or "[]")
    except ValueError:
        cart = None
    if not isinstance(cart, list) or not cart:
        return None, "The cart is empty.", False
    if len(cart) > MAX_SALE_LINES:
        return None, f"A sale can have at most {MAX_SALE_LINES} different lines.", False
    wanted = {}                                              # (kind, id) -> quantity
    for c in cart:
        qty = c.get("qty") if isinstance(c, dict) else None
        if not isinstance(c, dict) or c.get("kind") != "product" or isinstance(qty, bool) \
                or not isinstance(qty, int) or not 1 <= qty <= MAX_SALE_QTY:
            return None, f"Each cart line needs a valid quantity (1 to {MAX_SALE_QTY:,}).", False
        key = (c["kind"], str(c.get("id", "")))
        wanted[key] = wanted.get(key, 0) + qty
    if any(q_ > MAX_SALE_QTY for q_ in wanted.values()):
        return None, f"Quantity cannot be more than {MAX_SALE_QTY:,} per line.", False

    method = form.get("payment_method", "")
    if method not in PAYMENT_METHODS:
        return None, "Choose a payment method.", False
    customer = form.get("customer_name", "").strip()[:100]
    reference = form.get("reference", "").strip()[:60]
    reason = form.get("discount_reason", "").strip()[:100]
    animal_id = form.get("animal_id", "").strip().upper()
    try:
        discount = parse_money(form.get("discount", "0") or "0")
        if discount < 0:
            raise ValueError
    except ValueError:
        return None, "Discount must be an amount in pesos (0 or more, at most 2 decimals).", False
    if discount > 0 and not reason:
        return None, "Please give a reason for the discount.", False
    token = form.get("form_token", "").strip()[:64]

    with lock:                                               # one step: check, deduct stock, save
        sales = load("pos_sales")
        if token:
            dup = next((s for s in sales if s.get("form_token") == token), None)
            if dup:
                return dup, None, True                       # same form sent twice: never charge twice
        animal = None
        if animal_id:
            animal = next((a for a in load("animals") if a["animal_id"].upper() == animal_id), None)
            if not animal:
                return None, f"Animal {animal_id} was not found. Clear the field or pick a registered animal.", False
        inventory = {i["item_id"]: i for i in load("inventory")}
        lines, subtotal, cost_total = [], Decimal("0"), Decimal("0")
        for (kind, cid), qty in wanted.items():
            it = inventory.get(cid)
            try:
                price = _q(it.get("selling_price") or 0) if it else Decimal("0")
            except (InvalidOperation, ValueError):
                price = Decimal("0")
            if not it or price <= 0:
                return None, "An item in the cart is no longer for sale. Refresh the page.", False
            if expiry_status(it) == "Expired":
                return None, f"{it['item_name']} expired on {fmt_date(it.get('expiration_date'))} and cannot be sold.", False
            if it["quantity"] < qty:
                return None, f"Not enough stock. {it['item_name']} has only {it['quantity']} {it['unit']} available.", False
            cost = _q(it.get("unit_cost") or 0)
            lines.append({"kind": "product", "item_id": cid, "name": it["item_name"], "category": it["category"],
                          "unit": it["unit"], "qty": qty, "unit_price": float(price),
                          "line_total": float(price * qty), "unit_cost": float(cost)})
            cost_total += cost * qty
            subtotal += price * qty
        if discount > subtotal:
            return None, "The discount cannot be more than the subtotal.", False
        total = subtotal - discount
        if total <= 0:
            return None, "The total must be more than zero.", False
        vat = vat_included(total)          # 12% is already inside the price - it is reported, never added on top
        if method == "Cash":
            try:
                tendered = parse_money(form.get("amount_tendered", ""))
            except ValueError:
                return None, "Enter the cash amount received (pesos, at most 2 decimals).", False
            if tendered < total:
                return None, f"Cash received is less than the total ({money(total)}).", False
        else:
            tendered = total
        sale_id = next_id("SAL", sales, "sale_id", 5)
        sale = {"sale_id": sale_id, "datetime": now_str(), "date": date.today().isoformat(),
                "cashier": user["username"], "cashier_name": user.get("full_name") or user["username"],
                "customer_name": customer, "animal_id": animal["animal_id"] if animal else "",
                "animal_name": animal["animal_name"] if animal else "",
                "items": lines, "subtotal": float(subtotal), "discount": float(discount),
                "discount_reason": reason if discount > 0 else "", "total": float(total),
                "vat": float(vat), "vat_rate": VAT_PERCENT,
                "cost_total": float(cost_total), "payment_method": method, "reference": reference,
                "amount_tendered": float(tendered), "change": float(tendered - total),
                "status": "Completed", "form_token": token}

        moves = []                                           # stock: deduct (all checked above)
        product_lines = [ln for ln in lines if ln["kind"] == "product"]
        if product_lines:
            with edit("inventory") as items:
                by_id = {i["item_id"]: i for i in items}
                for ln in product_lines:
                    it = by_id[ln["item_id"]]
                    before = it["quantity"]
                    it["quantity"], it["last_updated"] = before - ln["qty"], now_str()
                    moves.append((dict(it), ln["qty"], before, before - ln["qty"]))
        try:
            with edit("pos_sales") as rows:
                rows.append(sale)
        except Exception:                                    # could not save the sale: give the stock back
            if moves:
                with edit("inventory") as items:
                    by_id = {i["item_id"]: i for i in items}
                    for it, qty, _b, _a in moves:
                        if it["item_id"] in by_id:
                            by_id[it["item_id"]]["quantity"] += qty
            raise
        for it, qty, before, after in moves:
            add_transaction(it, "Stock Out", qty, f"POS sale {sale_id}", before, after, user["username"],
                            sale_id=sale_id, source="pos")
    return sale, None, False


def void_sale(sale_id, reason, user):
    """Mark a sale Voided and put its products back in stock. Returns an error text or None."""
    with lock:
        sales = load("pos_sales")
        sale = next((s for s in sales if s["sale_id"] == sale_id), None)
        if not sale:
            return "Sale not found."
        if sale.get("status") == "Voided":
            return "This sale was already voided."
        moves = []
        with edit("inventory") as items:
            by_id = {i["item_id"]: i for i in items}
            for ln in sale["items"]:
                it = by_id.get(ln["item_id"]) if ln["kind"] == "product" else None
                if it:                                       # an item deleted since has nothing to return to
                    before = it["quantity"]
                    it["quantity"], it["last_updated"] = before + ln["qty"], now_str()
                    moves.append((dict(it), ln["qty"], before, before + ln["qty"]))
        with edit("pos_sales") as rows:
            for s in rows:
                if s["sale_id"] == sale_id:
                    s.update({"status": "Voided", "voided_at": now_str(), "voided_by": user["username"],
                              "void_reason": reason})
        for it, qty, before, after in moves:
            add_transaction(it, "Stock In", qty, f"Returned to stock: POS sale {sale_id} voided ({reason})",
                            before, after, user["username"], sale_id=sale_id, source="pos")
    return None


def sale_summary(sales):
    """Numbers for a list of sales. Voided sales are listed but never counted as revenue."""
    done = [s for s in sales if s.get("status") != "Voided"]
    total = sum((Decimal(str(s["total"])) for s in done), Decimal("0"))
    discount = sum((Decimal(str(s["discount"])) for s in done), Decimal("0"))
    cost = sum((Decimal(str(s.get("cost_total", 0))) for s in done), Decimal("0"))
    by_pay, top = {}, {}
    units = 0
    for s in done:
        by_pay[s["payment_method"]] = by_pay.get(s["payment_method"], Decimal("0")) + Decimal(str(s["total"]))
        for ln in s["items"]:
            units += ln["qty"]
            t = top.setdefault(ln["name"], {"name": ln["name"], "qty": 0, "revenue": Decimal("0")})
            t["qty"] += ln["qty"]
            t["revenue"] += Decimal(str(ln["line_total"]))
    top_items = sorted(top.values(), key=lambda t: (-t["revenue"], t["name"]))[:8]
    return {"count": len(done), "voided": len(sales) - len(done), "total": float(total),
            "discount": float(discount), "units": units, "profit": float(total - cost),
            "average": float(total / len(done)) if done else 0.0,
            "by_payment": [(m, float(v)) for m, v in sorted(by_pay.items(), key=lambda kv: -kv[1])],
            "top_items": [{"name": t["name"], "qty": t["qty"], "revenue": float(t["revenue"])} for t in top_items]}


def filter_sales(args, only_cashier=None):
    q = args.get("q", "").lower()
    rows = []
    for s in load("pos_sales"):
        if only_cashier and s["cashier"] != only_cashier:
            continue
        if args.get("date_from") and s["date"] < args["date_from"]:
            continue
        if args.get("date_to") and s["date"] > args["date_to"]:
            continue
        if args.get("cashier") and s["cashier"] != args["cashier"]:
            continue
        if args.get("payment") and s["payment_method"] != args["payment"]:
            continue
        if args.get("status") and s.get("status", "Completed") != args["status"]:
            continue
        if q:
            hay = " ".join([s["sale_id"], s.get("customer_name", ""), s.get("animal_id", ""), s.get("animal_name", ""),
                            s.get("reference", "")] + [ln["name"] for ln in s["items"]]).lower()
            if q not in hay:
                continue
        rows.append(s)
    rows.sort(key=lambda s: s["datetime"], reverse=True)
    return rows



