"""
PawTrack - integrated identity verification
"""
import os
import uuid

from flask import (Response, flash, jsonify, redirect, render_template, request,
                   session, url_for)
from werkzeug.utils import secure_filename

from ..config import IMAGE_EXTS, MAX_IMAGE_BYTES
from ..extensions import app
from ..helpers import now_str
from ..security import current_user, permission_required
from ..services.face import FaceError, embedding
from ..services.identity import (ID_TYPES, match_faces, save_verification,
                                scan_id)
from ..storage import load

UPLOAD_DIR = None
try:
    from ..config import UPLOAD_DIR as _UD
    UPLOAD_DIR = _UD
except Exception:
    pass

ID_UPLOAD_DIR = None
from pathlib import Path
ID_UPLOAD_DIR = Path(__file__).resolve().parent.parent.parent / "static" / "uploads" / "verification"
ID_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def _save_upload(file_storage):
    if not file_storage or not file_storage.filename:
        return None, "Please choose an ID image to upload."
    ext = file_storage.filename.rsplit(".", 1)[-1].lower() if "." in file_storage.filename else ""
    if ext not in IMAGE_EXTS:
        return None, "Unsupported image type. Use PNG, JPG, JPEG, GIF or WEBP."
    data = file_storage.read()
    if not data or len(data) > MAX_IMAGE_BYTES:
        return None, "Image is empty or too large (max 100 MB)."
    name = "id_" + uuid.uuid4().hex + "." + ext
    path = ID_UPLOAD_DIR / name
    with open(path, "wb") as fh:
        fh.write(data)
    return name, None


def _close_popup():
    html = ("<!DOCTYPE html><html><body><script>"
            "try{window.parent.postMessage('close','*');}catch(e){}"
            "setTimeout(function(){window.close();},200);"
            "</script><p>Closing...</p></body></html>")
    return Response(html, mimetype="text/html")


@app.route("/verify", methods=["GET", "POST"])
def verify_start():
    nxt = request.args.get("next") or request.form.get("next")
    if nxt:
        session["verify_next"] = nxt
    if request.method == "POST":
        id_type = request.form.get("id_type", "").strip()
        demo_mode = request.form.get("demo_mode") == "1"
        if id_type not in ID_TYPES:
            flash("Please select a supported ID type.", "error")
            return render_template("verify_start.html", id_types=ID_TYPES)
        file = request.files.get("id_image")
        filename, err = _save_upload(file)
        if err:
            flash("Upload not accepted: " + err + " Please upload another picture.", "warning")
            return render_template("verify_start.html", id_types=ID_TYPES)
        image_path = "uploads/verification/" + filename
        full_path = ID_UPLOAD_DIR / filename
        with open(full_path, "rb") as fh:
            image_bytes = fh.read()
        try:
            fields = scan_id(image_bytes, id_type, demo_mode=demo_mode)
        except Exception as exc:
            flash("ID scanning failed: " + str(exc), "error")
            return _close_popup()
        # store in session
        session["verify_id_type"] = id_type
        session["verify_image_path"] = image_path
        session["verify_demo_mode"] = bool(demo_mode)
        session["verify_fields"] = {k: v for k, v in fields.items()
                                    if k not in ("id_face_descriptor",)}
        session["verify_id_face_descriptor"] = fields.get("id_face_descriptor")
        session["verify_id_face_crop"] = fields.get("id_face_crop")
        session["verify_face_matched"] = False
        session["verify_captured_descriptor"] = None
        if not fields.get("complete"):
            missing = ", ".join(fields.get("missing", [])) or "face"
            flash("ID not accepted: missing " + missing + ".", "error")
            return _close_popup()
        flash("ID scanned successfully. Now capture your face.", "success")
        return redirect(url_for("verify_face"))
    return render_template("verify_start.html", id_types=ID_TYPES)


@app.route("/verify/face", methods=["GET"])
def verify_face():
    if not session.get("verify_fields"):
        flash("Please upload your ID first.", "error")
        return redirect(url_for("verify_start"))
    return render_template("verify_face.html")


@app.route("/verify/face", methods=["POST"])
def verify_face_post():
    if not session.get("verify_fields"):
        return jsonify(ok=False, error="No ID uploaded yet."), 400
    demo_mode = bool(session.get("verify_demo_mode"))
    id_desc = session.get("verify_id_face_descriptor")
    if demo_mode:
        # Sample/synthetic ID: skip face-on-ID requirement for testing.
        session["verify_face_matched"] = True
        session["verify_match_score"] = 1.0
        session["verify_captured_descriptor"] = None
        return jsonify(ok=True, matched=True, score=1.0, redirect=url_for("verify_info"))
    if not id_desc:
        return jsonify(ok=False, error="No face was detected on the ID. Please re-upload a clearer ID."), 400
    files = request.files.getlist("face_image")
    if not files:
        single = request.files.get("face_image")
        if single:
            files = [single]
    if not files:
        return jsonify(ok=False, error="No camera image received."), 400
    try:
        captured = embedding(files[0].read())
    except FaceError as exc:
        return jsonify(ok=False, error=str(exc)), 400
    except Exception as exc:
        return jsonify(ok=False, error="Face recognition failed: " + str(exc)), 500
    matched, score = match_faces(id_desc, captured)
    session["verify_captured_descriptor"] = captured
    session["verify_face_matched"] = bool(matched)
    session["verify_match_score"] = score
    if matched:
        return jsonify(ok=True, matched=True, score=round(score, 3),
                      redirect=url_for("verify_info"))
    return jsonify(ok=False, matched=False, score=round(score, 3),
                  error="Face does not match the ID photo. Please retry.")


@app.route("/verify/info", methods=["GET", "POST"])
def verify_info():
    if not session.get("verify_fields"):
        flash("Please upload your ID first.", "error")
        return redirect(url_for("verify_start"))
    if not session.get("verify_face_matched"):
        flash("Face matching must succeed before entering personal information.", "error")
        return redirect(url_for("verify_face"))
    fields = dict(session.get("verify_fields", {}))
    if request.method == "POST":
        # user review/edit
        fields["full_name"] = request.form.get("full_name", "").strip()
        fields["date_of_birth"] = request.form.get("date_of_birth", "").strip()
        fields["address"] = request.form.get("address", "").strip()
        fields["id_number"] = request.form.get("id_number", "").strip()
        fields["expiry_date"] = request.form.get("expiry_date", "").strip()
        # recalc age
        from datetime import datetime
        try:
            dob = datetime.fromisoformat(fields["date_of_birth"]).date()
            today = datetime.now().date()
            fields["age"] = str(today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day)))
        except ValueError:
            fields["age"] = fields.get("age", "")
        session["verify_fields"] = fields
        # save verification record
        rec = {
            "demo_mode": bool(session.get("verify_demo_mode")),
            "id_type": session.get("verify_id_type"),
            "id_image": session.get("verify_image_path"),
            "id_face_crop": session.get("verify_id_face_crop"),
            "full_name": fields.get("full_name"),
            "date_of_birth": fields.get("date_of_birth"),
            "age": fields.get("age"),
            "address": fields.get("address"),
            "id_number": fields.get("id_number"),
            "expiry_date": fields.get("expiry_date"),
            "face_matched": True,
            "match_score": session.get("verify_match_score"),
            "raw_text": fields.get("raw_text", ""),
            "created_by": (current_user() or {}).get("username", "guest"),
        }
        # Do NOT save to the database yet. Keep the record pending in the session;
        # it is only persisted when the animal registration is actually submitted.
        session["pending_verification"] = rec
        session["verification_id"] = None
        flash("Identity verified successfully.", "success")
        # Always go to the result page. When verification runs inside the
        # register-animal iframe, the result page tells the parent to close the
        # popup and reload the main screen (instead of loading the app in the iframe).
        session.pop("verify_next", None)
        return redirect(url_for("verify_result"))
    return render_template("verify_info.html", fields=fields,
                           id_type=session.get("verify_id_type"),
                           id_image=session.get("verify_image_path"),
                           id_face_crop=session.get("verify_id_face_crop"))


@app.route("/verify/result", methods=["GET"])
def verify_result():
    rec = session.get("pending_verification")
    if not rec:
        vid = session.get("verification_id")
        if vid:
            for v in load("verifications"):
                if v.get("verification_id") == vid:
                    rec = v
                    break
    if not rec:
        flash("No verification record found.", "warning")
        return redirect(url_for("verify_start"))
    return render_template("verify_result.html", rec=rec)


@app.route("/verify/cancel", methods=["GET"])
def verify_cancel():
    """Exit verification without saving. Clears all in-progress verification state."""
    for key in ("verification_id", "pending_verification", "verify_next", "verify_id_type",
                "verify_image_path", "verify_demo_mode", "verify_fields",
                "verify_id_face_descriptor", "verify_id_face_crop", "verify_face_matched",
                "verify_captured_descriptor", "verify_match_score"):
        session.pop(key, None)
    html = ("<!DOCTYPE html><html><body><script>"
            "try{window.parent.postMessage('close','*');}catch(e){}"
            "setTimeout(function(){window.close();},200);"
            "</script><p>Closing...</p></body></html>")
    return Response(html, mimetype="text/html")


@app.route("/verify/retry", methods=["POST"])
def verify_retry():
    # clear face match only, keep ID
    session["verify_face_matched"] = False
    session["verify_captured_descriptor"] = None
    return redirect(url_for("verify_face"))
