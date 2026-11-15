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
                session.clear()
                session.permanent = True
                session["user_id"] = match["user_id"]
                # the role stored with the account (never anything the browser sends) picks the dashboard
                return redirect(safe_next(request.args.get("next"), default=role_home(match)))
    return render_template("login.html")


@app.route("/login/face", methods=["POST"])
def login_face():
    """Identify an active account from one camera frame and start its session."""
    if current_user():
        return jsonify(ok=True, redirect=role_home())
    if session.get("face_failures", 0) >= FACE_MAX_FAILURES:
        return jsonify(ok=False,
                       error="Too many face attempts. Please log in with your password."), 429
    upload = request.files.get("face_image")
    if not upload:
        return jsonify(ok=False, error="No camera image was received. Please try again."), 400
    try:
        probe = embedding(upload.read())
    except FaceError as exc:
        return jsonify(ok=False, error=str(exc)), 400
    except Exception:
        current_app.logger.exception("Face login failed")
        return jsonify(ok=False,
                       error="Face recognition failed on the server. Please use your password."), 500

    enrolled = [u for u in load("users")
                if u.get("active", True) and u.get("role") in ROLE_LABELS
                and u.get("face_descriptors")]
    match, _score = identify(enrolled, probe)
    if not match:
        session["face_failures"] = session.get("face_failures", 0) + 1
        return jsonify(ok=False,
                       error="Face not recognized. Please try again or use your password."), 401

    session.clear()
    session.permanent = True
    session["user_id"] = match["user_id"]
    return jsonify(ok=True,
                   redirect=safe_next(request.args.get("next"), default=role_home(match)))


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("login"))
