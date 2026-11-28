"""
PawTrack - login and logout
"""
import secrets

from flask import (current_app, flash, jsonify, redirect, render_template,
                   request, session, url_for)
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from werkzeug.security import check_password_hash, generate_password_hash

from ..extensions import app
from ..security import ROLE_LABELS, current_user, password_errors, role_home, safe_next
from ..services.face import FaceError, embedding, identify
from ..storage import edit, load

FACE_MAX_FAILURES = 5
RESET_MAX_AGE = 15 * 60          # reset links expire after 15 minutes


def _reset_serializer():
    return URLSafeTimedSerializer(app.config["SECRET_KEY"], salt="pawtrack-password-reset")


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


@app.route("/login/face/bypass", methods=["POST"])
def login_face_bypass():
    """DEMO ONLY: skip face verification. Remove before any real deployment."""
    uid = session.get("pending_user_id")
    if not uid:
        return redirect(url_for("login"))
    user = next((u for u in load("users") if u["user_id"] == uid), None)
    if not user:
        return redirect(url_for("login"))
    nxt = session.pop("pending_next", None)
    session.clear()
    session.permanent = True
    session["user_id"] = user["user_id"]
    return jsonify(ok=True, redirect=nxt or role_home(user))


@app.route("/login/face/cancel", methods=["POST"])
def login_face_cancel():
    """Abandon 2FA and return to the password step."""
    session.pop("pending_user_id", None)
    session.pop("pending_next", None)
    session.pop("face_failures", None)
    return redirect(url_for("login"))


@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    """Step 1 of password recovery: verify identity and issue a single-use reset link."""
    if current_user():
        return redirect(role_home())
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        full_name = request.form.get("full_name", "").strip()
        match = next((u for u in load("users")
                      if u["username"].lower() == username.lower()
                      and (u.get("full_name") or "").strip().lower() == full_name.lower()), None)
        if not match:
            # Generic message: never reveal whether a username exists.
            flash("If the username and full name match an active account, a reset link has been issued.", "info")
        elif not match.get("active", True):
            flash("This account is deactivated. Please contact an administrator.", "error")
        else:
            nonce = secrets.token_hex(8)
            with edit("users") as users:
                for u in users:
                    if u["user_id"] == match["user_id"]:
                        u["reset_nonce"] = nonce
            token = _reset_serializer().dumps({"uid": match["user_id"], "nonce": nonce})
            link = url_for("reset_password", token=token, _external=True)
            # Email it when mail is configured; otherwise show it locally so
            # recovery still works on an offline clinic machine.
            from ..services.email import mail_config, send_email
            cfg = mail_config()
            recipient = (match.get("email") or "").strip()
            if cfg["configured"] and recipient and "@" in recipient:
                ok, err = send_email(
                    recipient, "PawTrack password reset",
                    f"Hello {match.get('full_name') or match['username']},\n\n"
                    f"Use this link to reset your PawTrack password within 15 minutes:\n{link}\n\n"
                    f"If you did not request this, ignore this email.\n\nPawTrack")
                if ok:
                    flash("A password reset link has been sent to your registered email.", "success")
                else:
                    flash(f"Could not send the email ({err}). Ask an administrator for help.", "error")
            else:
                flash("Password reset link (valid 15 minutes): " + link, "info")
        return render_template("forgot_password.html", username=username)
    return render_template("forgot_password.html")


@app.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):
    """Step 2: consume the signed, single-use token and set a new password."""
    if current_user():
        return redirect(role_home())
    try:
        data = _reset_serializer().loads(token, max_age=RESET_MAX_AGE)
        uid, nonce = data["uid"], data["nonce"]
    except (BadSignature, SignatureExpired, KeyError, TypeError):
        flash("This reset link is invalid or has expired. Please request a new one.", "error")
        return redirect(url_for("forgot_password"))

    user = next((u for u in load("users") if u["user_id"] == uid), None)
    if not user or not user.get("active", True) or user.get("reset_nonce") != nonce:
        flash("This reset link has already been used or is no longer valid.", "error")
        return redirect(url_for("forgot_password"))

    if request.method == "POST":
        new, confirm = request.form.get("new_password", ""), request.form.get("confirm_password", "")
        problems = password_errors(new)
        if problems:
            for problem in problems:
                flash(problem, "error")
        elif new != confirm:
            flash("New password and confirmation do not match.", "error")
        else:
            with edit("users") as users:
                for u in users:
                    if u["user_id"] == uid and u.get("reset_nonce") == nonce:
                        u["password_hash"] = generate_password_hash(new)
                        u.pop("reset_nonce", None)      # single use
            flash("Your password has been reset. Please log in with the new password.", "success")
            return redirect(url_for("login"))
    return render_template("reset_password.html", token=token)


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("login"))
