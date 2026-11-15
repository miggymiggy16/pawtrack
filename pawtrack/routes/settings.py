"""
PawTrack - clinic, notification and account settings
"""
import re

from flask import (current_app, flash, jsonify, redirect, render_template,
                   request, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

from ..extensions import app
from ..helpers import (delete_animal_photo, delete_product_image, lan_ip,
                       now_str, valid_email)
from ..security import (admin_required, current_user, login_required,
                        password_errors)
from ..services.email import build_message, mail_config, notify
from ..services.face import MODEL_NAME, FaceError, enroll
from ..services.qr import make_qr, qr_path
from ..storage import edit, get_settings, load


@app.route("/settings")
@login_required
def settings():
    return render_template("settings.html", s=get_settings(), mail=mail_config(), lan=lan_ip(),
                           has_sample=any(x.get("sample") for x in load("animals") + load("inventory")),
                           port=request.host.split(":")[-1] if ":" in request.host else "5000")


@app.route("/settings/notifications", methods=["POST"])
@admin_required
def settings_notifications():
    errors = []
    try:
        days = int(request.form.get("reminder_days", ""))
        warn = int(request.form.get("expiry_warning_days", ""))
        if not (0 <= days <= 365) or not (0 <= warn <= 365):
            raise ValueError
    except ValueError:
        errors.append("Reminder days and expiry warning days must be whole numbers from 0 to 365.")
    if errors:
        flash(errors[0], "error")
    else:
        with edit("settings") as s:
            s["reminder_days"], s["expiry_warning_days"] = days, warn
            s["email_enabled"] = bool(request.form.get("email_enabled"))
        flash("Notification settings saved.", "success")
    return redirect(url_for("settings"))


@app.route("/settings/clinic", methods=["POST"])
@admin_required
def settings_clinic():
    clinic = {k: request.form.get(k, "").strip() for k in ("name", "address", "phone", "email")}
    base = request.form.get("public_base_url", "").strip().rstrip("/")
    if not clinic["name"]:
        flash("Clinic name is required.", "error")
    elif clinic["email"] and not valid_email(clinic["email"]):
        flash("Clinic email is not valid.", "error")
    elif base and not re.match(r"^https?://[^\s/]+(:\d+)?(/[^\s]*)?$", base):
        flash("QR base URL must look like http://192.168.1.10:5000", "error")
    else:
        with edit("settings") as s:
            s["clinic"], s["public_base_url"] = clinic, base
        flash("Clinic information saved.", "success")
    return redirect(url_for("settings"))


@app.route("/settings/password", methods=["POST"])
@login_required
def settings_password():
    me = current_user()
    current, new, confirm = (request.form.get(k, "") for k in ("current_password", "new_password", "confirm_password"))
    problems = password_errors(new)
    if not check_password_hash(me["password_hash"], current):
        flash("Current password is incorrect.", "error")
    elif problems:
        for problem in problems:
            flash(problem, "error")
    elif new != confirm:
        flash("New password and confirmation do not match.", "error")
    else:
        with edit("users") as us:
            for u in us:
                if u["user_id"] == me["user_id"]:
                    u["password_hash"] = generate_password_hash(new)
        flash("Your password was changed.", "success")
    return redirect(url_for("settings"))


@app.route("/settings/face", methods=["POST"])
@login_required
def settings_face():
    """Register or replace the signed-in user's face from 1-3 camera frames."""
    me = current_user()
    password = request.form.get("password", "")
    if not check_password_hash(me["password_hash"], password):
        return jsonify(ok=False, error="Current password is incorrect."), 400
    uploads = [item for item in request.files.getlist("face_image")
               if item and item.filename]
    if not uploads:
        return jsonify(ok=False, error="No camera images were received. Please try again."), 400
    try:
        descriptors = enroll([item.read() for item in uploads])
    except FaceError as exc:
        return jsonify(ok=False, error=str(exc)), 400
    except Exception:
        current_app.logger.exception("Face enrollment failed")
        return jsonify(ok=False,
                       error="Face registration failed on the server. Please try again."), 500

    enrolled_at = now_str()
    with edit("users") as users:
        for user in users:
            if user["user_id"] == me["user_id"]:
                user["face_descriptors"] = descriptors
                user["face_enrolled_at"] = enrolled_at
                user["face_model"] = MODEL_NAME
    return jsonify(ok=True,
                   message="Face ID registered. You can now log in by scanning your face.",
                   enrolled_at=enrolled_at, samples=len(descriptors))


@app.route("/settings/face/remove", methods=["POST"])
@login_required
def settings_face_remove():
    """Forget the signed-in user's face so it can no longer be used to log in."""
    me = current_user()
    with edit("users") as users:
        for user in users:
            if user["user_id"] == me["user_id"]:
                user.pop("face_descriptors", None)
                user.pop("face_enrolled_at", None)
                user.pop("face_model", None)
    flash("Your face ID was removed.", "success")
    return redirect(url_for("settings"))


@app.route("/settings/test-email", methods=["POST"])
@admin_required
def settings_test_email():
    to = request.form.get("to", "").strip()
    if not valid_email(to):
        flash("Enter a valid email address for the test.", "error")
    else:
        subject, body = build_message("Test Email", {"animal_id": "", "animal_name": "-"})
        ok, err = notify(None, to, "Test Email", "Email configuration test", subject, body,
                         by=current_user()["username"])
        flash(f"Test email sent to {to}." if ok else f"Test email failed: {err}", "success" if ok else "error")
    return redirect(url_for("settings"))


@app.route("/settings/regenerate-qr", methods=["POST"])
@admin_required
def settings_regenerate_qr():
    animals = load("animals")
    made = sum(1 for a in animals if make_qr(a))
    flash(f"Regenerated {made} of {len(animals)} QR codes." if made or not animals
          else "Could not create QR codes: install the 'qrcode' package.", "success" if made or not animals else "error")
    return redirect(url_for("settings"))


@app.route("/settings/remove-sample", methods=["POST"])
@admin_required
def settings_remove_sample():
    with edit("animals") as animals:
        gone = {a["animal_id"] for a in animals if a.get("sample")}
        for a in animals:
            if a.get("sample"):
                delete_animal_photo(a.get("photo"))
        animals[:] = [a for a in animals if not a.get("sample")]
    with edit("vaccinations") as vs:
        vs[:] = [v for v in vs if not v.get("sample") and v["animal_id"] not in gone]
    for name in ("inventory", "inventory_transactions", "notifications"):
        with edit(name) as rows:
            if name == "inventory":
                for r in rows:
                    if r.get("sample"):
                        delete_product_image(r.get("image"))
            rows[:] = [r for r in rows if not r.get("sample")]
    with edit("pos_services") as services:
        services[:] = [r for r in services if not r.get("sample")]
    for animal_id in gone:
        if qr_path(animal_id).exists():
            qr_path(animal_id).unlink()
    flash(f"Sample data removed ({len(gone)} sample animals and their records).", "success")
    return redirect(url_for("settings"))
