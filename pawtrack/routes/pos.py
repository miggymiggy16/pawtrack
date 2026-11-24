"""
PawTrack - point of sale screens and sales data
"""
import csv
import io
import secrets
from datetime import date, datetime, timedelta

from flask import (Response, abort, flash, jsonify, redirect, render_template,
                   request, url_for)

from ..config import PAYMENT_METHODS
from ..extensions import app
from ..helpers import _safe_cell, now_str, parse_date
from ..security import (can, current_user, login_required,
                        permission_required)
from ..services.pos import (create_sale, filter_sales, pos_catalog,
                            sale_summary, void_sale)
from ..storage import edit, get_settings, load, next_id


def _sale_args():
    today = date.today()
    args = {k: request.args.get(k, "").strip() for k in ("date_from", "date_to", "cashier", "payment", "status", "q")}
    if "date_from" not in request.args:
        args["date_from"] = (today - timedelta(days=29)).isoformat()      # default: last 30 days
    if "date_to" not in request.args:
        args["date_to"] = today.isoformat()
    for k in ("date_from", "date_to"):
        if args[k] and not parse_date(args[k]):
            args[k] = ""
    return args


# ---------- cashier: the POS screen ----------
@app.route("/pos")
@permission_required("pos.use")
def pos_screen():
    me = current_user()
    mine = filter_sales({"date_from": date.today().isoformat(), "date_to": date.today().isoformat()},
                        only_cashier=me["username"])
    animals = sorted(load("animals"), key=lambda a: a["animal_id"])
    return render_template("pos.html", catalog=pos_catalog(), payments=PAYMENT_METHODS,
                           token=secrets.token_hex(8), recent=mine[:6], today_summary=sale_summary(mine),
                           animals=[{"id": a["animal_id"], "name": a["animal_name"]} for a in animals])


@app.route("/pos/checkout", methods=["POST"])
@permission_required("pos.use")
def pos_checkout():
    """Answers with JSON so the cashier's cart stays on screen when something is refused."""
    sale, err, dup = create_sale(request.form, current_user())
    if err:
        return jsonify(ok=False, error=err), 400
    return jsonify(ok=True, duplicate=dup, sale_id=sale["sale_id"],
                   receipt_url=url_for("sale_receipt", sale_id=sale["sale_id"], new=1))


@app.route("/pos/sales")
@permission_required("pos.use")
def pos_my_sales():
    me = current_user()
    args = {k: request.args.get(k, "").strip() for k in ("date_from", "date_to", "q")}
    if "date_from" not in request.args and "date_to" not in request.args:
        args["date_from"] = args["date_to"] = date.today().isoformat()
    for k in ("date_from", "date_to"):
        if args[k] and not parse_date(args[k]):
            args[k] = ""
    rows = filter_sales(args, only_cashier=me["username"])
    return render_template("pos_sales.html", rows=rows[:300], total=len(rows), args=args,
                           summary=sale_summary(rows), payments=list(PAYMENT_METHODS))


@app.route("/pos/receipt/<sale_id>")
@login_required
def sale_receipt(sale_id):
    sale = next((s for s in load("pos_sales") if s["sale_id"] == sale_id), None)
    if not sale:
        abort(404)
    if can("pos.use"):
        if sale["cashier"] != current_user()["username"]:
            abort(403)                                       # a cashier sees only their own receipts
    elif not can("pos.data"):
        abort(403)
    return render_template("receipt.html", s=sale, is_new=bool(request.args.get("new")) and can("pos.use"))


# ---------- admin and staff: the sales data ----------
@app.route("/sales")
@permission_required("pos.data")
def sales_list():
    args = _sale_args()
    rows = filter_sales(args)
    cashiers = sorted({s["cashier"] for s in load("pos_sales")})
    payments = list(PAYMENT_METHODS)
    for s in load("pos_sales"):            # keep any method used by older sales filterable
        m = s.get("payment_method")
        if m and m not in payments:
            payments.append(m)
    return render_template("sales.html", rows=rows[:300], total=len(rows), args=args, cashiers=cashiers,
                           payments=payments, summary=sale_summary(rows),
                           show_profit=can("pos.manage"))


@app.route("/sales/export")
@permission_required("pos.data")
def sales_export():
    args = _sale_args()
    rows = filter_sales(args)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow([get_settings()["clinic"]["name"], "POS sales"])
    w.writerow(["Generated", now_str(), "Filters", ", ".join(f"{k}={v}" for k, v in args.items() if v) or "none"])
    w.writerow([])
    w.writerow(["Sale no.", "Date and time", "Cashier", "Customer", "Animal ID", "Items", "Subtotal", "Discount",
                "Total", "Payment", "Reference", "Cash received", "Change", "Status"])
    for s in rows:
        items = "; ".join(f"{ln['qty']} x {ln['name']}" for ln in s["items"])
        w.writerow([_safe_cell(c) for c in (
            s["sale_id"], s["datetime"], s["cashier"], s.get("customer_name", ""), s.get("animal_id", ""), items,
            f"{s['subtotal']:.2f}", f"{s['discount']:.2f}", f"{s['total']:.2f}", s["payment_method"],
            s.get("reference", ""), f"{s['amount_tendered']:.2f}", f"{s['change']:.2f}",
            s.get("status", "Completed"))])
    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    return Response("\ufeff" + buf.getvalue(), mimetype="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="PawTrack-sales-{stamp}.csv"'})


@app.route("/sales/<sale_id>/void", methods=["POST"])
@permission_required("pos.manage")
def sale_void(sale_id):
    reason = request.form.get("reason", "").strip()[:100]
    if not reason:
        flash("Please give a reason for voiding the sale.", "error")
    else:
        err = void_sale(sale_id, reason, current_user())
        flash(err or f"{sale_id} was voided and its products were returned to stock.", "error" if err else "success")
    return redirect(url_for("sale_receipt", sale_id=sale_id))

