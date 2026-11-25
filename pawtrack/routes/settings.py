"""
PawTrack - clinic, notification and account settings
"""
import re

from flask import (current_app, flash, jsonify, redirect, render_template,
                   request, session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

from ..config import FACE_MATCH_THRESHOLD
from ..extensions import app
from ..helpers import (delete_animal_photo, delete_product_image, lan_ip,
                       now_str, valid_email)
from ..security import (admin_required, current_user, login_required,
                        password_errors)
from ..services.email import build_message, mail_config, notify
from ..services.face import MODEL_NAME
from ..services.identity import ID_TYPES, VERIFICATION_DIR, scan_id
from ..services.qr import make_qr, qr_path
from ..storage import edit, get_settings, load


def _settings_redirect():
    """Back to Settings on the tab the submitted form belongs to."""
    return redirect(url_for("settings", tab=request.form.get("tab")))


@app.route("/settings")
@login_required
def settings():
    return render_template("settings.html", s=get_settings(), mail=mail_config(), lan=lan_ip(),
                           has_sample=any(x.get("sample") for x in load("animals") + load("inventory")),
                           id_types=ID_TYPES,
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
    return _settings_redirect()


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
    return _settings_redirect()


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
    return _settings_redirect()


@app.route("/settings/identity/scan", methods=["POST"])
@login_required
def settings_identity_scan():
    """Step 1-2: scan the uploaded ID and extract fields into a pending session record."""
    if request.form.get("consent") != "1":
        return jsonify(ok=False, error="Please consent to ID and facial data processing."), 400
    if not check_password_hash(current_user()["password_hash"], request.form.get("password", "")):
        return jsonify(ok=False, error="Current password is incorrect."), 400
    id_type = request.form.get("id_type", "").strip()
    if id_type not in ID_TYPES:
        return jsonify(ok=False, error="Please choose a supported ID type."), 400
    upload = request.files.get("id_image")
    if not upload or not upload.filename:
        return jsonify(ok=False, error="Please choose an ID image to upload."), 400
    data = upload.read()
    try:
        fields = scan_id(data, id_type)
    except Exception as exc:
        return jsonify(ok=False, error="ID scanning failed: " + str(exc)), 400
    if not fields.get("complete"):
        missing = ", ".join(fields.get("missing", [])) or "face"
        return jsonify(ok=False, error="ID not accepted: missing " + missing + ". Upload a clearer image."), 400
    import uuid
    ext = upload.filename.rsplit(".", 1)[-1].lower() if "." in upload.filename else "png"
    name = "user_" + current_user()["user_id"] + "_" + uuid.uuid4().hex + "." + ext
    (VERIFICATION_DIR / name).write_bytes(data)
    session["settings_pending_id"] = {
        "id_type": id_type, "fields": {k: v for k, v in fields.items() if k != "id_face_descriptor"},
        "id_descriptor": fields.get("id_face_descriptor"),
        "id_image": "uploads/verifications/" + name,
    }
    return jsonify(ok=True, fields=session["settings_pending_id"]["fields"],
                   id_image=session["settings_pending_id"]["id_image"])


@app.route("/settings/identity/face", methods=["POST"])
@login_required
def settings_identity_face():
    """Step 3-4: guided face captures, matched against the ID photo, then save everything."""
    from ..services.face import embedding, identify
    from ..services.identity import match_faces
    pending = session.get("settings_pending_id")
    if not pending or not pending.get("id_descriptor"):
        return jsonify(ok=False, error="No scanned ID found. Start the verification again."), 400
    files = [f for f in request.files.getlist("face_image") if f and f.filename]
    if not files:
        return jsonify(ok=False, error="No camera images were received. Please repeat the capture."), 400
    try:
        descriptors = [embedding(f.read()) for f in files]
    except Exception as exc:
        return jsonify(ok=False, error="Face capture failed: " + str(exc) + " Please repeat."), 400
    if not descriptors:
        return jsonify(ok=False, error="No face was detected. Please repeat with better lighting."), 400
    best_score = max(match_faces(pending["id_descriptor"], d)[1] for d in descriptors)
    if best_score < FACE_MATCH_THRESHOLD:
        return jsonify(ok=False, error="Face does not match the ID photo. Please retake the captures."), 400
    me = current_user()
    with edit("users") as users:
        for u in users:
            if u["user_id"] == me["user_id"]:
                u["id_type"] = pending["id_type"]
                u["id_number"] = pending["fields"].get("id_number", "")
                u["id_full_name"] = pending["fields"].get("full_name", "")
                u["id_date_of_birth"] = pending["fields"].get("date_of_birth", "")
                u["id_address"] = pending["fields"].get("address", "")
                u["id_expiry_date"] = pending["fields"].get("expiry_date", "")
                u["id_image"] = pending["id_image"]
                u["id_verified_at"] = now_str()
                u["face_descriptors"] = descriptors
                u["face_enrolled_at"] = now_str()
                u["face_model"] = MODEL_NAME
    session.pop("settings_pending_id", None)
    return jsonify(ok=True, score=round(best_score, 3), message="Identity verification complete.")


@app.route("/settings/identity/remove", methods=["POST"])
@login_required
def settings_identity_remove():
    """Remove all stored identity verification (ID + face) for the signed-in user."""
    me = current_user()
    with edit("users") as users:
        for u in users:
            if u["user_id"] == me["user_id"]:
                for key in ("id_type", "id_number", "id_full_name", "id_date_of_birth", "id_address",
                            "id_expiry_date", "id_image", "id_verified_at",
                            "face_descriptors", "face_enrolled_at", "face_model"):
                    u.pop(key, None)
    flash("Your identity verification was removed.", "success")
    return _settings_redirect()


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
    return _settings_redirect()


@app.route("/settings/regenerate-qr", methods=["POST"])
@admin_required
def settings_regenerate_qr():
    animals = load("animals")
    made = sum(1 for a in animals if make_qr(a))
    flash(f"Regenerated {made} of {len(animals)} QR codes." if made or not animals
          else "Could not create QR codes: install the 'qrcode' package.", "success" if made or not animals else "error")
    return _settings_redirect()


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
    return _settings_redirect()
