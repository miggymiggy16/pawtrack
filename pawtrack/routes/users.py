"""
PawTrack - user accounts
"""
from flask import abort, flash, redirect, render_template, request, url_for
from werkzeug.security import generate_password_hash

from ..config import USERNAME_RE
from ..extensions import app
from ..helpers import now_str, valid_email
from ..security import (ROLE_LABELS, admin_required, current_user,
                        password_errors)
from ..storage import edit, load, next_id


# ----------------------------------------------------------------------------
# ROUTES: USERS & SETTINGS
# ----------------------------------------------------------------------------
def active_admins(users, ignore_id=None):
    return [u for u in users if u["role"] == "admin" and u.get("active", True) and u["user_id"] != ignore_id]


@app.route("/users")
@admin_required
def users():
    return render_template("users.html", rows=load("users"))


def validate_user(form, existing=None):
    f = {k: form.get(k, "").strip() for k in ("username", "full_name", "email", "role")}
    f["active"] = bool(form.get("active"))
    errors = []
    others = [u for u in load("users") if not existing or u["user_id"] != existing["user_id"]]
    if not USERNAME_RE.match(f["username"]):
        errors.append("Username must be 3-30 characters: letters, numbers, dot, dash or underscore.")
    elif any(u["username"].lower() == f["username"].lower() for u in others):
        errors.append("That username is already taken.")
    if not f["full_name"]:
        errors.append("Full name is required.")
    if f["email"] and not valid_email(f["email"]):
        errors.append("Email is not valid.")
    if f["role"] not in ROLE_LABELS:
        errors.append("Role must be Administrator, Veterinary Staff or Cashier.")
    return f, errors


@app.route("/users/new", methods=["GET", "POST"])
@admin_required
def user_new():
    form = {"role": "staff", "active": True}
    if request.method == "POST":
        form, errors = validate_user(request.form)
        password = request.form.get("password", "")
        errors.extend(password_errors(password))
        if errors:
            for e in errors:
                flash(e, "error")
        else:
            with edit("users") as us:
                form.update({"user_id": next_id("USR", us, "user_id"), "created_at": now_str(),
                             "password_hash": generate_password_hash(password)})
                us.append(form)
            flash(f"User {form['username']} created.", "success")
            return redirect(url_for("users"))
    return render_template("user_form.html", form=form, editing=False)


@app.route("/users/<user_id>/edit", methods=["GET", "POST"])
@admin_required
def user_edit(user_id):
    target = next((u for u in load("users") if u["user_id"] == user_id), None)
    if not target:
        abort(404)
    form = dict(target)
    if request.method == "POST":
        form, errors = validate_user(request.form, existing=target)
        me = current_user()
        if target["user_id"] == me["user_id"] and (form["role"] != "admin" or not form["active"]):
            errors.append("You cannot remove your own admin role or deactivate yourself.")
        if target["role"] == "admin" and (form["role"] != "admin" or not form["active"]) \
                and not active_admins(load("users"), ignore_id=user_id):
            errors.append("At least one active admin is required.")
        if errors:
            for e in errors:
                flash(e, "error")
        else:
            with edit("users") as us:
                for i, u in enumerate(us):
                    if u["user_id"] == user_id:
                        us[i] = {**u, **form}
            flash("User updated.", "success")
            return redirect(url_for("users"))
    form["user_id"] = user_id
    return render_template("user_form.html", form=form, editing=True)


@app.route("/users/<user_id>/toggle", methods=["POST"])
@admin_required
def user_toggle(user_id):
    users_ = load("users")
    target = next((u for u in users_ if u["user_id"] == user_id), None)
    if not target:
        abort(404)
    if target["user_id"] == current_user()["user_id"]:
        flash("You cannot deactivate your own account.", "error")
    elif target.get("active", True) and target["role"] == "admin" and not active_admins(users_, ignore_id=user_id):
        flash("At least one active admin is required.", "error")
    else:
        with edit("users") as us:
            for u in us:
                if u["user_id"] == user_id:
                    u["active"] = not u.get("active", True)
                    state = "activated" if u["active"] else "deactivated"
        flash(f"{target['username']} was {state}.", "success")
    return redirect(url_for("users"))


@app.route("/users/<user_id>/delete", methods=["POST"])
@admin_required
def user_delete(user_id):
    users_ = load("users")
    target = next((u for u in users_ if u["user_id"] == user_id), None)
    if not target:
        abort(404)
    if target["user_id"] == current_user()["user_id"]:
        flash("You cannot delete your own account.", "error")
    elif target["role"] == "admin" and not active_admins(users_, ignore_id=user_id):
        flash("You cannot delete the last active admin.", "error")
    else:
        with edit("users") as us:
            us[:] = [u for u in us if u["user_id"] != user_id]
        flash(f"User {target['username']} deleted.", "success")
    return redirect(url_for("users"))


@app.route("/users/<user_id>/reset-password", methods=["POST"])
@admin_required
def user_reset_password(user_id):
    password = request.form.get("new_password", "")
    problems = password_errors(password)
    if problems:
        for problem in problems:
            flash(problem, "error")
        return redirect(url_for("user_edit", user_id=user_id))
    with edit("users") as us:
        target = next((u for u in us if u["user_id"] == user_id), None)
        if not target:
            abort(404)
        target["password_hash"] = generate_password_hash(password)
    flash(f"Password for {target['username']} was reset.", "success")
    return redirect(url_for("users"))


@app.route("/users/<user_id>/reset-face", methods=["POST"])
@admin_required
def user_reset_face(user_id):
    """Remove a user's face so an administrator can ask them to register again."""
    with edit("users") as us:
        target = next((u for u in us if u["user_id"] == user_id), None)
        if not target:
            abort(404)
        target.pop("face_descriptors", None)
        target.pop("face_enrolled_at", None)
        target.pop("face_model", None)
        username = target["username"]
    flash(f"Face ID for {username} was reset.", "success")
    return redirect(url_for("user_edit", user_id=user_id))
