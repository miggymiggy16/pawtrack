"""
PawTrack - vaccination records
"""
import secrets
from datetime import date

from flask import abort, flash, redirect, render_template, request, url_for

from ..config import VACCINE_SUGGESTIONS
from ..extensions import app
from ..helpers import now_str, parse_date, valid_email, year_has_at_most_4_digits
from ..security import (admin_required, current_user, permission_required)
from ..services.email import build_message, notify
from ..services.inventory import adjust_vaccine_stock, enriched_inventory
from ..services.vaccinations import all_vax_rows
from ..storage import edit, get_settings, load, lock, next_id


# ---------- vaccinations ----------
def vaccine_stock_options(current_id=""):
    """Vaccine inventory items offered on the vaccination form (the currently linked one is always kept)."""
    out = []
    for i in enriched_inventory():
        if i["category"] != "Vaccines":
            continue
        usable = i["quantity"] > 0 and i["expiry_status"] != "Expired"
        out.append({**i, "usable": usable or i["item_id"] == current_id})
    return sorted(out, key=lambda i: i["item_name"].lower())


def vaccination_stock_of(record):
    """(inventory_item_id, quantity) that a saved vaccination record has deducted. Old records: ('', 0)."""
    try:
        qty = int(record.get("quantity_used", 0) or 0)
    except (TypeError, ValueError):
        qty = 0
    item_id = record.get("inventory_item_id", "") or ""
    return (item_id, qty) if item_id and qty > 0 else ("", 0)


def validate_vaccination(form):
    f = {k: form.get(k, "").strip() for k in
         ("animal_id", "vaccine_name", "date_administered", "next_due_date", "notes")}
    errors = []
    # Optional link to vaccine stock. With no item chosen, no stock is touched.
    f["inventory_item_id"] = form.get("inventory_item_id", "").strip()
    f["form_token"] = form.get("form_token", "").strip()[:40]
    raw_qty = form.get("quantity_used", "").strip() or "1"
    f["quantity_used"] = 0
    if f["inventory_item_id"]:
        try:
            qty = int(raw_qty)
            if qty < 1 or qty > 1000:
                raise ValueError
            f["quantity_used"] = qty
        except ValueError:
            errors.append("Quantity used must be a whole number from 1 to 1,000.")
            f["quantity_used"] = raw_qty
        item = next((i for i in load("inventory") if i["item_id"] == f["inventory_item_id"]), None)
        if not item or item.get("category") != "Vaccines":
            errors.append("Please choose a vaccine from the inventory list, or leave it as 'Do not deduct'.")
    if not any(a["animal_id"] == f["animal_id"] for a in load("animals")):
        errors.append("Please choose a registered animal.")
    if not f["vaccine_name"]:
        errors.append("Vaccine name is required.")
    if not year_has_at_most_4_digits(f["date_administered"]):
        errors.append("Date administered year must have at most 4 digits.")
    if not year_has_at_most_4_digits(f["next_due_date"]):
        errors.append("Next due date year must have at most 4 digits.")
    given, due = parse_date(f["date_administered"]), parse_date(f["next_due_date"])
    if not given:
        errors.append("Date administered is required and must be a valid date.")
    elif given > date.today():
        errors.append("Date administered cannot be in the future.")
    if f["next_due_date"] and not due:
        errors.append("Next due date is not a valid date.")
    if given and due and due < given:
        errors.append("Next due date cannot be earlier than the date administered.")
    return f, errors


@app.route("/vaccinations")
@permission_required("vaccinations.view")
def vaccinations():
    args = {k: request.args.get(k, "").strip()
            for k in ("animal_id", "q", "status", "vaccine", "due_from", "due_to")}
    if args["status"] not in ("Completed", "Upcoming", "Due Today", "Overdue"):
        args["status"] = ""
    due_from, due_to = parse_date(args["due_from"]), parse_date(args["due_to"])
    if not due_from:
        args["due_from"] = ""
    if not due_to:
        args["due_to"] = ""
    rows = all_vax_rows()                      # read-only: viewing never touches stock
    # Summary cards always describe ALL records (not the filtered list)
    counts = {"total": len(rows)}
    for s_ in ("Completed", "Upcoming", "Due Today", "Overdue"):
        counts[s_] = sum(1 for r in rows if r["status"] == s_)
    vaccine_options = sorted({r["vaccine_name"].strip() for r in rows if r["vaccine_name"].strip()},
                             key=str.lower)
    q = args["q"].lower()

    def match(r):
        if args["animal_id"] and r["animal_id"] != args["animal_id"]:
            return False
        if q and not any(q in str(x).lower() for x in
                         (r["animal_id"], r["animal"].get("animal_name", ""), r["vaccine_name"])):
            return False
        if args["status"] and r["status"] != args["status"]:
            return False
        if args["vaccine"] and r["vaccine_name"].strip().lower() != args["vaccine"].lower():
            return False
        due = parse_date(r.get("next_due_date"))
        if (due_from or due_to) and not due:
            return False
        if due_from and due < due_from:
            return False
        if due_to and due > due_to:
            return False
        return True

    filtered = [r for r in rows if match(r)]
    # Most urgent first (Overdue, Due Today, Upcoming by due date), then history by newest
    urgency = {"Overdue": 0, "Due Today": 1, "Upcoming": 2}
    filtered.sort(key=lambda r: (r["date_administered"], r["vaccination_id"]), reverse=True)
    filtered.sort(key=lambda r: (urgency.get(r["status"], 3),
                                 (r.get("next_due_date") or "") if r["status"] in urgency else ""))
    animal = next((a for a in load("animals") if a["animal_id"] == args["animal_id"]), None)
    filters_active = any(args[k] for k in ("q", "vaccine", "due_from", "due_to", "animal_id"))
    return render_template("vaccination.html", rows=filtered, args=args, animal=animal, counts=counts,
                           vaccine_options=vaccine_options, filters_active=filters_active,
                           reminder_days=get_settings()["reminder_days"])


@app.route("/vaccinations/new", methods=["GET", "POST"])
@permission_required("vaccinations.create")
def vaccination_new():
    animals = sorted(load("animals"), key=lambda a: a["animal_id"])
    form = {"animal_id": request.args.get("animal_id", ""), "date_administered": date.today().isoformat()}
    if request.method == "POST":
        form, errors = validate_vaccination(request.form)
        if errors:
            for e in errors:
                flash(e, "error")
        else:
            user = current_user()["username"]
            with lock:                                  # one step: stock check, deduction and save
                existing = next((v for v in load("vaccinations")
                                 if form["form_token"] and v.get("form_token") == form["form_token"]), None)
                if existing:                             # same form sent twice: do NOT record or deduct again
                    flash(f"This vaccination was already recorded as {existing['vaccination_id']}. "
                          "Nothing was deducted a second time.", "warning")
                    return redirect(url_for("animal_view", animal_id=existing["animal_id"]))
                new_id = next_id("VAC", load("vaccinations"), "vaccination_id")
                new_stock = vaccination_stock_of(form)
                err = adjust_vaccine_stock(("", 0), new_stock, {**form, "vaccination_id": new_id}, user)
                if err:
                    flash(err, "error")
                else:
                    try:
                        with edit("vaccinations") as vs:
                            form.update({"vaccination_id": new_id, "created_at": now_str(), "created_by": user})
                            vs.append(form)
                    except Exception:                    # could not save: give the doses back, then report
                        adjust_vaccine_stock(new_stock, ("", 0), {**form, "vaccination_id": new_id}, user)
                        raise
                    msg = "Vaccination recorded."
                    if new_stock[0]:
                        msg += f" {new_stock[1]} unit(s) deducted from vaccine stock."
                    flash(msg, "success")
                    maybe_email_update(form)
                    return redirect(url_for("animal_view", animal_id=form["animal_id"]))
    else:
        form["form_token"] = secrets.token_hex(8)
    return render_template("vaccination_form.html", form=form, animals=animals, editing=False,
                           suggestions=VACCINE_SUGGESTIONS, stock_items=vaccine_stock_options(form.get("inventory_item_id", "")))


def maybe_email_update(vacc_form):
    """If the 'email owner' box was ticked, send a Vaccination Updated email and report honestly."""
    if not request.form.get("email_owner"):
        return
    animal = next((a for a in load("animals") if a["animal_id"] == vacc_form["animal_id"]), None)
    if not animal or not valid_email(animal.get("owner_email", "")):
        flash("No email sent: this animal has no valid owner email.", "warning")
        return
    if not get_settings()["email_enabled"]:
        flash("No email sent: email notifications are turned off in Settings.", "warning")
        return
    subject, body = build_message("Vaccination Updated", animal, vacc_form)
    ok, err = notify(animal, animal["owner_email"], "Vaccination Updated", "Vaccination record changed",
                     subject, body, vacc_form, by=current_user()["username"])
    flash("Owner was emailed about the update." if ok else f"Email could not be sent: {err}",
          "success" if ok else "error")


@app.route("/vaccinations/<vacc_id>/edit", methods=["GET", "POST"])
@permission_required("vaccinations.edit")
def vaccination_edit(vacc_id):
    record = next((v for v in load("vaccinations") if v["vaccination_id"] == vacc_id), None)
    if not record:
        abort(404)
    animals = sorted(load("animals"), key=lambda a: a["animal_id"])
    form = dict(record)
    if request.method == "POST":
        form, errors = validate_vaccination(request.form)
        if errors:
            for e in errors:
                flash(e, "error")
        else:
            user = current_user()["username"]
            with lock:
                current = next((v for v in load("vaccinations") if v["vaccination_id"] == vacc_id), None)
                if not current:
                    abort(404)
                old_stock, new_stock = vaccination_stock_of(current), vaccination_stock_of(form)
                err = adjust_vaccine_stock(old_stock, new_stock, {**form, "vaccination_id": vacc_id}, user)
                if err:
                    flash(err, "error")
                else:
                    form.pop("form_token", None)         # the original token stays on the record
                    try:
                        with edit("vaccinations") as vs:
                            for i, v in enumerate(vs):
                                if v["vaccination_id"] == vacc_id:
                                    vs[i] = {**v, **form}
                    except Exception:
                        adjust_vaccine_stock(new_stock, old_stock, {**form, "vaccination_id": vacc_id}, user)
                        raise
                    form["vaccination_id"] = vacc_id
                    msg = "Vaccination record updated."
                    if old_stock != new_stock:
                        msg += " Vaccine stock was adjusted to match."
                    flash(msg, "success")
                    maybe_email_update(form)
                    return redirect(url_for("animal_view", animal_id=form["animal_id"]))
    form["vaccination_id"] = vacc_id
    return render_template("vaccination_form.html", form=form, animals=animals, editing=True,
                           suggestions=VACCINE_SUGGESTIONS, stock_items=vaccine_stock_options(form.get("inventory_item_id", "")))


@app.route("/vaccinations/<vacc_id>/delete", methods=["POST"])
@admin_required
def vaccination_delete(vacc_id):
    record = next((v for v in load("vaccinations") if v["vaccination_id"] == vacc_id), None)
    if not record:
        abort(404)
    old_stock = vaccination_stock_of(record)
    with lock:
        returned = old_stock[1] if old_stock[0] and adjust_vaccine_stock(
            old_stock, ("", 0), record, current_user()["username"]) is None else 0
        with edit("vaccinations") as vs:
            vs[:] = [v for v in vs if v["vaccination_id"] != vacc_id]
    flash("Vaccination record deleted." +
          (f" {returned} unit(s) of vaccine stock were returned to inventory." if returned else ""), "success")
    return redirect(url_for("animal_view", animal_id=record["animal_id"]))
