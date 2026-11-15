"""
PawTrack - inventory logic
==========================
Stock status, expiry status, enriched rows, audit transactions and the
vaccine-stock adjustment that keeps inventory in step with vaccination
records without ever deducting the same dose twice.
"""
from datetime import date
from decimal import Decimal

from ..helpers import (fmt_date, item_image_url, item_value, now_str,
                       parse_date)
from ..storage import edit, get_settings, load, lock, next_id


def stock_status(item):
    q = item["quantity"]
    if q <= 0:
        return "Out of Stock"
    return "Low Stock" if q <= item["min_stock"] else "In Stock"


def expiry_status(item, warn_days=None):
    d = parse_date(item.get("expiration_date"))
    if not d:
        return "Valid"
    warn_days = warn_days if warn_days is not None else get_settings()["expiry_warning_days"]
    if d < date.today():
        return "Expired"
    return "Expiring Soon" if (d - date.today()).days <= warn_days else "Valid"


def enriched_inventory():
    warn = get_settings()["expiry_warning_days"]
    out = []
    for it in load("inventory"):
        it = dict(it)
        it["stock_status"] = stock_status(it)
        it["expiry_status"] = expiry_status(it, warn)
        it["value"] = item_value(it["quantity"], it["unit_cost"])
        it["image_url"] = item_image_url(it)
        out.append(it)
    return out


def inventory_counts(items=None):
    items = items if items is not None else enriched_inventory()
    return {
        "total": len(items),
        "low": sum(1 for i in items if i["stock_status"] == "Low Stock"),
        "out": sum(1 for i in items if i["stock_status"] == "Out of Stock"),
        "expired": sum(1 for i in items if i["expiry_status"] == "Expired"),
        "expiring": sum(1 for i in items if i["expiry_status"] == "Expiring Soon"),
        "value": float(sum(Decimal(str(i["value"])) for i in items)),
    }


def add_transaction(item, ttype, qty_change, reason, before, after, user, **extra):
    """Append one row to the stock history. `extra` carries links such as vaccination_id."""
    with edit("inventory_transactions") as tx:
        tx.append({"transaction_id": next_id("TXN", tx, "transaction_id", 5),
                   "item_id": item["item_id"], "item_name": item["item_name"],
                   "transaction_type": ttype, "quantity": qty_change,
                   "quantity_before": before, "quantity_after": after,
                   "reason": reason, "datetime": now_str(), "user": user, **extra})


def adjust_vaccine_stock(old, new, vacc, user):
    """Make vaccine stock match a vaccination record. Returns an error text, or None when it worked.

    old / new are (inventory_item_id, quantity) pairs: what the record deducted BEFORE this
    change and what it should deduct AFTER. Only the DIFFERENCE is applied, so saving,
    reopening or re-saving the same record can never deduct the same dose twice:
      same item, 1 -> 1      nothing happens
      same item, 1 -> 3      2 more are deducted
      item changed           the old item gets its doses back, the new item is deducted
      record deleted/unlinked all doses go back to stock
    Everything is checked first; if anything is wrong NO stock is changed at all."""
    need = {}
    if old[0] and old[1]:
        need[old[0]] = need.get(old[0], 0) - old[1]
    if new[0] and new[1]:
        need[new[0]] = need.get(new[0], 0) + new[1]
    need = {k: v for k, v in need.items() if v}
    if not need:
        return None
    label = f"{vacc['vaccination_id']} ({vacc.get('vaccine_name', '')} for {vacc.get('animal_id', '')})"
    moves = []
    with lock:
        with edit("inventory") as items:
            by_id = {i["item_id"]: i for i in items}
            for item_id, amount in need.items():          # 1) check everything first
                it = by_id.get(item_id)
                if amount > 0:
                    if not it:
                        return "The selected vaccine stock item no longer exists."
                    if it.get("category") != "Vaccines":
                        return f"{it['item_name']} is not a vaccine inventory item."
                    if expiry_status(it) == "Expired":
                        return f"{it['item_name']} expired on {fmt_date(it.get('expiration_date'))} and cannot be used."
                    if it["quantity"] < amount:
                        return f"Not enough stock. {it['item_name']} has only {it['quantity']} {it['unit']} available."
            for item_id, amount in need.items():          # 2) then change the stock
                it = by_id.get(item_id)
                if not it:
                    continue                              # item was deleted: nothing to return to
                before = it["quantity"]
                after = before - amount
                it["quantity"], it["last_updated"] = after, now_str()
                moves.append((dict(it), amount, before, after))
    for it, amount, before, after in moves:               # 3) write the audit rows
        if amount > 0:
            reason = f"Correction of {label}: more used" if old[0] == it["item_id"] else f"Vaccination {label}"
            add_transaction(it, "Stock Out", amount, reason, before, after, user,
                            vaccination_id=vacc["vaccination_id"], source="vaccination")
        else:
            why = "record deleted" if not (new[0] and new[1]) else "record corrected"
            add_transaction(it, "Stock In", -amount, f"Returned to stock: {label}, {why}", before, after, user,
                            vaccination_id=vacc["vaccination_id"], source="vaccination")
    return None
