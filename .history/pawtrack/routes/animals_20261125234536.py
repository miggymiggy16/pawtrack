"""
PawTrack - animal registration, profiles and photos
"""
import re
import secrets
from datetime import date

from flask import abort, flash, redirect, render_template, request, session, url_for

from ..config import OWNERSHIP_CHOICES, SEX_CHOICES, SPECIES_CHOICES, UP_TO_DATE
from ..extensions import app
from ..helpers import (animal_photo_url, delete_animal_photo, now_str,
                       parse_date, read_product_image, store_animal_photo,
                       valid_email)
from ..security import (admin_required, current_user, permission_required,
                        safe_next)
from ..services.inventory import adjust_vaccine_stock
from ..services.qr import make_qr, qr_path
from ..services.vaccinations import animal_vax_info
from ..storage import edit, issue_animal_id, load, lock

# ---------- animals ----------
BREED_RE = re.compile(r"^[A-Za-z][A-Za-z .'\-]*$")   # letters, spaces, dot, hyphen, apostrophe
NAME_RE = re.compile(r"^[A-Za-z][A-Za-z .'\-]*$")    # letters + spaces for personal names
AGE_RE = re.compile(r"^\d+(?:\.\d+)?$")              # number only (e.g. 2 or 2.5)
MOBILE_RE = re.compile(r"^[\d\s\-\+]+$")            # digits, spaces, dash, country code


def validate_animal(form, existing=None):
    f = {k: form.get(k, "").strip() for k in
         ("animal_name", "species", "breed", "sex", "age", "color", "description",
          "ownership_status", "owner_name", "owner_mobile", "owner_email", "registration_date")}
    errors = []
    # The Animal ID is never read from the form. New animals get one from
    # issue_animal_id(); existing animals always keep the ID they already have.
    if existing:
        f["animal_id"] = existing["animal_id"]
        if not f["animal_name"]:
            errors.append("Animal name is required.")
    if not f["species"]:
        errors.append("Species is required.")
    if f["breed"] and not BREED_RE.match(f["breed"]):
        errors.append("Breed must contain letters only.")
    if f["age"] and not AGE_RE.match(f["age"]):
        errors.append("Age must be a number only (e.g. 2 or 2.5).")
    if f["sex"] not in SEX_CHOICES:
        errors.append("Please choose the animal's sex.")
    if f["ownership_status"] not in OWNERSHIP_CHOICES:
        errors.append("Please choose an ownership status.")
    if f["ownership_status"] == "Owned":
        if not f["owner_name"]:
            errors.append("Owner name is required for owned animals.")
        elif not NAME_RE.match(f["owner_name"]):
            errors.append("Owner name must contain letters only.")
        if f["owner_mobile"] and not MOBILE_RE.match(f["owner_mobile"]):
            errors.append("Owner mobile number must contain numbers only.")
        if not f["owner_email"]:
            errors.append("Owner email is required for owned animals.")
        elif not valid_email(f["owner_email"]):
            errors.append("Owner email is not a valid email address.")
    if f["ownership_status"] == "Stray":          # strays have no owner to store
        f["owner_name"] = f["owner_mobile"] = f["owner_email"] = ""
    if not f["registration_date"]:
        f["registration_date"] = date.today().isoformat()
    elif not parse_date(f["registration_date"]):
        errors.append("Registration date is not a valid date.")
    return f, errors


def get_animal_or_404(animal_id):
    animal = next((a for a in load("animals") if a["animal_id"] == animal_id), None)
    if not animal:
        abort(404)
    return animal


ANIMALS_PER_PAGE = 12


@app.route("/animals/cancel-register")
@permission_required("animals.create")
def animal_cancel_register():
    """Cancel registration and return to the animals list."""
    flash("Registration cancelled.", "info")
    return redirect(url_for("animals_list"))


@app.route("/animals")
@permission_required("animals.view")
def animals_list():
    args = {k: request.args.get(k, "").strip() for k in
            ("q", "species", "status", "ownership")}
    all_animals = load("animals")
    matches = []                       # every animal that passes the filters except the Owned/Stray tab
    for a in all_animals:
        info = animal_vax_info(a["animal_id"])
        st = info["status"]
        if args["q"]:
            haystack = (str(a.get("animal_id", "")) + " " + str(a.get("animal_name", "")) + " " + str(a.get("breed") or "")).lower()
            if args["q"].lower() not in haystack:
                continue
        if args["species"] and a["species"] != args["species"]:
            continue
        if args["status"] == "vaccinated" and st not in UP_TO_DATE:
            continue
        if args["status"] == "unvaccinated" and st in UP_TO_DATE:
            continue
        if args["status"] in ("Vaccinated", "Upcoming", "Due Today", "Overdue", "No Record") and st != args["status"]:
            continue
        matches.append({**a, "vax_status": st, "next_due": info["next_due"],
                        "latest": info["latest"], "records": info["records"]})
    tab_counts = {"": len(matches),
                  "Owned": sum(1 for a in matches if a["ownership_status"] == "Owned"),
                  "Stray": sum(1 for a in matches if a["ownership_status"] == "Stray")}
    rows = [a for a in matches if not args["ownership"] or a["ownership_status"] == args["ownership"]]
    pages = max(1, -(-len(rows) // ANIMALS_PER_PAGE))
    try:
        page = min(max(1, int(request.args.get("page", "1"))), pages)
    except ValueError:
        page = 1
    shown = rows[(page - 1) * ANIMALS_PER_PAGE: page * ANIMALS_PER_PAGE]
    selected = request.args.get("selected", "")
    if selected not in {a["animal_id"] for a in shown}:
        selected = shown[0]["animal_id"] if shown else ""
    species = sorted({a["species"] for a in all_animals} | set(SPECIES_CHOICES))

    def link(**over):              # URL for this page that keeps the current filters, minus empty values
        q = {k: v for k, v in {**args, **over}.items() if v not in ("", None)}
        return url_for("animals_list", **q)
    return render_template("animals.html", link=link, rows=shown, args=args, species=species, total=len(all_animals),
                           matched=len(rows), tab_counts=tab_counts, page=page, pages=pages, selected=selected)


@app.route("/animals/new", methods=["GET", "POST"])
@permission_required("animals.create")
def animal_new():
    form = {"ownership_status": "Owned", "registration_date": date.today().isoformat()}
    if request.method == "POST":
        form, errors = validate_animal(request.form)
        img, ext, img_err = read_product_image(request.files.get("photo"), "Animal photo")
        if img_err:
            errors.append(img_err)
        if errors:
            for e in errors:
                flash(e, "error")
        else:
            form.update({"qr_token": secrets.token_urlsafe(8), "created_at": now_str(), "created_by": current_user()["username"]})
            with edit("animals") as items:                 # lock held: ID + save are one step
                form["animal_id"] = issue_animal_id()
                if img:
                    form["photo"] = store_animal_photo(form["animal_id"], img, ext)
                items.append(form)
            made = make_qr(form)
            flash(f"{form['animal_name']} was registered with Animal ID {form['animal_id']}." +
                  ("" if made else " QR image could not be created: install the 'qrcode' package."), "success")
            return redirect(url_for("animal_view", animal_id=form["animal_id"]))
    return render_template("animal_form.html", form=form, editing=False, species=SPECIES_CHOICES)


@app.route("/animals/<animal_id>")
@permission_required("animals.view")
def animal_view(animal_id):
    animal = get_animal_or_404(animal_id)
    return render_template("animal_profile.html", a=animal, info=animal_vax_info(animal_id))


@app.route("/animals/<animal_id>/edit", methods=["GET", "POST"])
@permission_required("animals.edit")
def animal_edit(animal_id):
    animal = get_animal_or_404(animal_id)
    form = dict(animal)
    if request.method == "POST":
        form, errors = validate_animal(request.form, existing=animal)
        img, ext, img_err = read_product_image(request.files.get("photo"), "Animal photo")
        if img_err:
            errors.append(img_err)
        if errors:
            for e in errors:
                flash(e, "error")
        else:
            old_photo, kept = animal.get("photo", ""), animal.get("photo", "")
            with edit("animals") as items:
                for i, it in enumerate(items):
                    if it["animal_id"] == animal_id:           # Animal ID and vaccinations are untouched
                        new = {**it, **form}
                        if img:                                  # replace the photo
                            new["photo"] = store_animal_photo(animal_id, img, ext)
                        elif request.form.get("remove_photo"):
                            new["photo"] = ""
                        items[i] = new
                        kept = new.get("photo", "")
            if old_photo and old_photo != kept:
                delete_animal_photo(old_photo)
            flash("Animal record updated.", "success")
            return redirect(url_for("animal_view", animal_id=animal_id))
    form["photo_url"] = animal_photo_url(animal)
    return render_template("animal_form.html", form=form, editing=True, species=SPECIES_CHOICES)


@app.route("/animals/<animal_id>/photo", methods=["POST"])
@permission_required("animals.edit")
def animal_photo(animal_id):
    """Quick photo upload from the profile or list page (no need to open the full edit form)."""
    animal = get_animal_or_404(animal_id)
    back = safe_next(request.form.get("next"), default=url_for("animal_view", animal_id=animal_id))
    img, ext, err = read_product_image(request.files.get("photo"), "Animal photo")
    if err:
        flash(err, "error")
    elif not img:
        flash("Please choose a picture to upload.", "warning")
    else:
        old_photo = animal.get("photo", "")
        name = store_animal_photo(animal_id, img, ext)
        with edit("animals") as items:
            for it in items:
                if it["animal_id"] == animal_id:
                    it["photo"] = name
        if old_photo and old_photo != name:
            delete_animal_photo(old_photo)
        flash(f"Photo saved for {animal['animal_name']}.", "success")
    return redirect(back)


@app.route("/animals/<animal_id>/delete", methods=["POST"])
@admin_required
def animal_delete(animal_id):
    animal = get_animal_or_404(animal_id)
    returned = 0
    with lock:
        for v in [v for v in load("vaccinations") if v["animal_id"] == animal_id]:
            old = (v.get("inventory_item_id", ""), int(v.get("quantity_used", 0) or 0))
            if old[0] and old[1] and adjust_vaccine_stock(old, ("", 0), v, current_user()["username"]) is None:
                returned += old[1]
        with edit("animals") as items:
            items[:] = [a for a in items if a["animal_id"] != animal_id]
        with edit("vaccinations") as vs:                 # remove its vaccinations too
            vs[:] = [v for v in vs if v["animal_id"] != animal_id]
    if qr_path(animal_id).exists():
        qr_path(animal_id).unlink()
    delete_animal_photo(animal.get("photo"))
    flash(f"{animal['animal_name']} and its vaccination records were deleted." +
          (f" Vaccine stock used by those records was returned to inventory ({returned} unit(s))." if returned else ""),
          "success")
    return redirect(url_for("animals_list"))
