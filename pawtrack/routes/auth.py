"""
PawTrack - login and logout
"""
from flask import (current_app, flash, jsonify, redirect, render_template,
                   request, session, url_for)
from werkzeug.security import check_password_hash

from ..extensions import app
from ..security import ROLE_LABELS, current_user, role_home, safe_next
from ..services.face import FaceError, embedding, identify
from ..storage import load

FACE_MAX_FAILURES = 5


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user():
        return redirect(role_home())
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        if not username or not password:
            flash("Please enter both username and password.", "error")
        else:
            match = next((u for u in load("users") if u["username"].lower() == username.lower()), None)
            if not match or not check_password_hash(match["password_hash"], password):
                flash("Incorrect username or password.", "error")
            elif not match.get("active", True):
                flash("This account is deactivated. Please contact an administrator.", "error")
            elif match.get("role") not in ROLE_LABELS:
                flash("This account has no valid role. Please contact an administrator.", "error")
            else:
                # Step 1 of 2FA: credentials confirmed. Now require face verification.
                session.clear()
                session.permanent = True
                session["pending_user_id"] = match["user_id"]
                session["pending_next"] = safe_next(request.args.get("next"), default=role_home(match))
                if match.get("face_descriptors"):
                    return redirect(url_for("login_face"))
                # No face enrolled yet — let them in once so they can set it up in Settings.
                session.clear()
                session.permanent = True
                session["user_id"] = match["user_id"]
                flash("Set up Face ID and ID verification in Settings to secure your account.", "warning")
                return redirect(url_for("settings"))
    return render_template("login.html")


@app.route("/login/face", methods=["GET", "POST"])
def login_face():
    """Step 2 of 2FA: verify the face of the account whose password was accepted."""
    uid = session.get("pending_user_id")
    if not uid:
        return redirect(url_for("login"))
    user = next((u for u in load("users") if u["user_id"] == uid), None)
    if not user or not user.get("face_descriptors"):
        session.pop("pending_user_id", None)
        return redirect(url_for("login"))

    if request.method == "GET":
        return render_template("login_face.html", username=user.get("username", ""))

    if session.get("face_failures", 0) >= FACE_MAX_FAILURES:
        return jsonify(ok=False, error="Too many face attempts. Please log in again with your password."), 429
    upload = request.files.get("face_image")
    if not upload:
        return jsonify(ok=False, error="No camera image was received. Please try again."), 400
    try:
        probe = embedding(upload.read())
    except FaceError as exc:
        return jsonify(ok=False, error=str(exc)), 400
    except Exception:
        current_app.logger.exception("Face verification failed")
        return jsonify(ok=False, error="Face recognition failed on the server. Please try again."), 500

    match, _score = identify([user], probe)
    if not match:
        session["face_failures"] = session.get("face_failures", 0) + 1
        return jsonify(ok=False, error="Face not recognized. Please try again."), 401

    nxt = session.pop("pending_next", None)
    session.clear()
    session.permanent = True
    session["user_id"] = match["user_id"]
    return jsonify(ok=True, redirect=nxt or role_home(match))


@app.route("/login/face/cancel", methods=["POST"])
def login_face_cancel():
    """Abandon 2FA and return to the password step."""
    session.pop("pending_user_id", None)
    session.pop("pending_next", None)
    session.pop("face_failures", None)
    return redirect(url_for("login"))


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("login"))
