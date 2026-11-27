"""
PawTrack - inventory items and stock movements
"""
from datetime import date

from flask import abort, flash, redirect, render_template, request, url_for

from ..config import CATEGORIES, MAX_QTY, VACCINE_TYPES
from ..extensions import app
from ..helpers import (delete_product_image, item_image_url, now_str,
                       parse_date, parse_money, read_product_image,
                       store_product_image, year_has_at_most_4_digits)
from ..security import admin_required, can, current_user, permission_required
from ..services.inventory import add_transaction, enriched_inventory, inventory_counts
from ..storage import edit, load, next_id


# ----------------------------------------------------------------------------
# ROUTES: INVENTORY
# ----------------------------------------------------------------------------
def validate_item(form, editing=False):
    f = {k: form.get(k, "").strip() for k in
         ("item_name", "category", "description", "unit", "supplier", "expiration_date",
          "vaccine_type", "manufacturer", "batch_number")}
    errors = []
    if f["category"] != "Vaccines":                  # vaccine-only details are kept just for vaccines
        f["vaccine_type"] = f["manufacturer"] = f["batch_number"] = ""
    for key, label in (("vaccine_type", "Vaccine type"), ("manufacturer", "Manufacturer / brand"),
                       ("batch_number", "Batch / lot number")):
        if len(f[key]) > 100:
            errors.append(f"{label} must be 100 characters or fewer.")
    if not f["item_name"]:
        errors.append("Item name is required.")
    if f["category"] not in CATEGORIES:
        errors.append("Please choose a valid category.")
    if not f["unit"]:
        errors.append("Unit is required (for example: pcs, vials, boxes).")
    nums = [("min_stock", "Minimum stock level", int)]
    if not editing:
        nums.insert(0, ("quantity", "Quantity", int))
    for key, label, cast in nums:
        raw = form.get(key, "").strip()
        try:
            val = cast(raw)
            if val < 0:
                errors.append(f"{label} cannot be negative.")
            elif val > MAX_QTY:
                errors.append(f"{label} cannot be more than {MAX_QTY:,}.")
            f[key] = val
        except ValueError:
            errors.append(f"{label} must be a valid number.")
            f[key] = 0
    # Unit cost is in PESOS (e.g. 150.00), never cents. Parsed with Decimal, stored with 2 decimals.
    try:
        cost = parse_money(form.get("unit_cost", "0") or "0")
        if cost < 0:
            errors.append("Unit cost cannot be negative.")
        f["unit_cost"] = float(cost)
    except ValueError:
        errors.append("Unit cost must be an amount in pesos with at most 2 decimals, for example 150.00.")
        f["unit_cost"] = form.get("unit_cost", "")        # show what the user typed so they can fix it
    # Selling price (POS). 0 / empty = not sold at the cashier. Cost is what the clinic paid; this is what the customer pays.
    try:
        price = parse_money(form.get("selling_price", "0") or "0")
        if price < 0:
            errors.append("Selling price cannot be negative.")
        f["selling_price"] = float(price)
    except ValueError:
        errors.append("Selling price must be an amount in pesos with at most 2 decimals, for example 175.00.")
        f["selling_price"] = form.get("selling_price", "")
    if f["expiration_date"] and not year_has_at_most_4_digits(f["expiration_date"]):
        errors.append("Expiration date year must have at most 4 digits.")
    elif f["expiration_date"] and not parse_date(f["expiration_date"]):
        errors.append("Expiration date is not a valid date.")
    return f, errors


def get_item_or_404(item_id):
    item = next((i for i in load("inventory") if i["item_id"] == item_id), None)
    if not item:
        abort(404)
    return item


@app.route("/inventory")
@permission_required("inventory.view")
def inventory():
    args = {k: request.args.get(k, "").strip() for k in ("q", "category", "view")}
    items = enriched_inventory()
    readonly = not can("inventory.manage")
    views = {"in": lambda i: i["stock_status"] == "In Stock",
             "low": lambda i: i["stock_status"] == "Low Stock",
             "out": lambda i: i["stock_status"] == "Out of Stock",
             "expired": lambda i: i["expiry_status"] == "Expired",
             "expiring": lambda i: i["expiry_status"] == "Expiring Soon"}
    rows = [i for i in items
            if (not args["q"] or args["q"].lower() in
                (i["item_name"] + i["item_id"] + i["supplier"] + i["category"]).lower())
            and (not args["category"] or i["category"] == args["category"])
            and (args["view"] not in views or views[args["view"]](i))]
    return render_template("inventory.html", rows=rows, args=args, categories=CATEGORIES,
                           counts=inventory_counts(items), readonly=readonly)


@app.route("/inventory/new", methods=["GET", "POST"])
@permission_required("inventory.manage")
def inventory_new():
    form = {"quantity": 0, "min_stock": 5, "unit_cost": 0, "category": "Medicines"}
    if request.method == "POST":
        form, errors = validate_item(request.form)
        img, ext, img_err = read_product_image(request.files.get("image"))
        if img_err:
            errors.append(img_err)
        if errors:
            for e in errors:
                flash(e, "error")
        else:
            with edit("inventory") as items:
                form.update({"item_id": next_id("INV", items, "item_id"), "date_added": date.today().isoformat(),
                             "last_updated": now_str()})
                if img:
                    form["image"] = store_product_image(form["item_id"], img, ext)
                items.append(form)
            if form["quantity"] > 0:
                add_transaction(form, "Stock In", form["quantity"], "Initial stock", 0, form["quantity"],
                                current_user()["username"])
            flash(f"{form['item_name']} added to inventory.", "success")
            return redirect(url_for("inventory_view", item_id=form["item_id"]))
    return render_template("inventory_form.html", form=form, editing=False, categories=CATEGORIES,
                           vaccine_types=VACCINE_TYPES)


@app.route("/inventory/<item_id>")
@permission_required("inventory.view")
def inventory_view(item_id):
    item = next((i for i in enriched_inventory() if i["item_id"] == item_id), None)
    if not item:
        abort(404)
    tx = [t for t in load("inventory_transactions") if t["item_id"] == item_id]
    tx.sort(key=lambda t: t["datetime"], reverse=True)
    return render_template("inventory_item.html", i=item, tx=tx)


@app.route("/inventory/<item_id>/edit", methods=["GET", "POST"])
@permission_required("inventory.manage")
def inventory_edit(item_id):
    item = get_item_or_404(item_id)
    form = dict(item)
    if request.method == "POST":
        form, errors = validate_item(request.form, editing=True)
        img, ext, img_err = read_product_image(request.files.get("image"))
        if img_err:
            errors.append(img_err)
        if errors:
            for e in errors:
                flash(e, "error")
            form["image"], form["image_url"] = item.get("image", ""), item_image_url(item)
        else:
            old_image = item.get("image", "")
            with edit("inventory") as items:
                for idx, it in enumerate(items):
                    if it["item_id"] == item_id:        # quantity is NOT changed here
                        new = {**it, **form, "last_updated": now_str()}
                        if img:                          # replace the picture
                            new["image"] = store_product_image(item_id, img, ext)
                        elif request.form.get("remove_image"):
                            new["image"] = ""
                        items[idx] = new
                        kept = new.get("image", "")
            if old_image and old_image != kept:
                delete_product_image(old_image)
            flash("Item updated.", "success")
            return redirect(url_for("inventory_view", item_id=item_id))
    form["item_id"] = item_id
    form["quantity"] = item["quantity"]
    form["image_url"] = item_image_url(item)
    return render_template("inventory_form.html", form=form, editing=True, categories=CATEGORIES,
                           vaccine_types=VACCINE_TYPES)


@app.route("/inventory/<item_id>/delete", methods=["POST"])
@admin_required
def inventory_delete(item_id):
    item = get_item_or_404(item_id)
    with edit("inventory") as items:
        items[:] = [i for i in items if i["item_id"] != item_id]
    delete_product_image(item.get("image"))
    flash(f"{item['item_name']} was deleted. Its past transactions are kept in the history.", "success")
    return redirect(url_for("inventory"))


@app.route("/inventory/<item_id>/stock", methods=["POST"])
@permission_required("inventory.manage")
def inventory_stock(item_id):
    """Stock In / Stock Out / Adjustment. Records a transaction that matches the real change."""
    get_item_or_404(item_id)
    ttype = request.form.get("transaction_type", "")
    reason = request.form.get("reason", "").strip()
    try:
        amount = int(request.form.get("quantity", "").strip())
    except ValueError:
        flash("Quantity must be a whole number.", "error")
        return redirect(url_for("inventory_view", item_id=item_id))
    if ttype not in ("Stock In", "Stock Out", "Adjustment"):
        flash("Choose a valid transaction type.", "error")
    elif amount < 0 or (ttype != "Adjustment" and amount == 0):
        flash("Quantity must be greater than zero (an adjustment may be zero or more).", "error")
    elif amount > MAX_QTY:
        flash(f"Quantity cannot be more than {MAX_QTY:,}.", "error")
    elif not reason:
        flash("Please give a reason for this stock change.", "error")
    else:
        result = None
        with edit("inventory") as items:
            for it in items:
                if it["item_id"] == item_id:
                    before = it["quantity"]
                    if ttype == "Stock In":
                        after = before + amount
                    elif ttype == "Stock Out":
                        after = before - amount
                    else:                                   # Adjustment: amount is the NEW total
                        after = amount
                    if after < 0:
                        result = ("error", f"Not enough stock. Only {before} {it['unit']} available.")
                    else:
                        it["quantity"], it["last_updated"] = after, now_str()
                        result = ("ok", it, before, after)
        if result[0] == "error":
            flash(result[1], "error")
        else:
            _, it, before, after = result
            if after != before or ttype != "Adjustment":
                add_transaction(it, ttype, after - before if ttype == "Adjustment" else amount,
                                reason, before, after, current_user()["username"])
            flash(f"{ttype} saved. Quantity changed from {before} to {after} {it['unit']}.", "success")
    return redirect(url_for("inventory_view", item_id=item_id))


@app.route("/inventory/transactions")
@permission_required("inventory.history")
def inventory_transactions():
    args = {k: request.args.get(k, "").strip() for k in ("item", "type", "date_from", "date_to")}
    rows = []
    for t in load("inventory_transactions"):
        if args["item"] and args["item"].lower() not in (t["item_name"] + t["item_id"]).lower():
            continue
        if args["type"] and t["transaction_type"] != args["type"]:
            continue
        if args["date_from"] and t["datetime"][:10] < args["date_from"]:
            continue
        if args["date_to"] and t["datetime"][:10] > args["date_to"]:
            continue
        rows.append(t)
    rows.sort(key=lambda t: t["datetime"], reverse=True)
    return render_template("inventory_transactions.html", rows=rows, args=args)
