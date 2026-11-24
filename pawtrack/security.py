"""
PawTrack - authentication, roles and request security
=====================================================
Roles live in the users collection ("role" field). "staff" is the Veterinary
Staff role. One permission table is used by BOTH the server
(permission_required) and the templates (can()), so the menu and the server
always agree.
"""
import base64
import os
import secrets
from datetime import date
from functools import wraps

from flask import (Response, abort, flash, g, redirect, render_template,
                   request, session, url_for)

from .storage import get_settings, load

ROLE_LABELS = {"admin": "Administrator", "staff": "Veterinary Staff", "cashier": "Cashier"}
_BOTH = {"admin", "staff"}
_ADMIN = {"admin"}

PASSWORD_RULE = "at least 8 characters, with a letter, a number, and a symbol"


def password_errors(password):
    """Return every problem with a new password (an empty list means it is acceptable)."""
    password = password or ""
    problems = []
    if len(password) < 8:
        problems.append("Password must be at least 8 characters.")
    if not any(c.isalpha() for c in password):
        problems.append("Password must include at least one letter.")
    if not any(c.isdigit() for c in password):
        problems.append("Password must include at least one number.")
    if not any(not c.isalnum() and not c.isspace() for c in password):
        problems.append("Password must include at least one symbol.")
    return problems

PERMISSIONS = {
    "animals.view": _BOTH, "animals.create": _BOTH, "animals.edit": _BOTH, "animals.delete": _ADMIN,
    "vaccinations.view": _BOTH, "vaccinations.create": _BOTH, "vaccinations.edit": _BOTH, "vaccinations.delete": _ADMIN,
    "qr.use": _BOTH,
    "notifications.view": _BOTH, "notifications.run": _ADMIN,
    "inventory.view": _BOTH,            # staff: read-only stock view (vaccines, medicines, supplies), no prices
    "inventory.manage": _ADMIN,         # add / edit / stock in / stock out / adjustments / minimum levels
    "inventory.history": _ADMIN,
    "analytics.view": _ADMIN, "reports.view": _ADMIN,
    "users.manage": _ADMIN, "settings.manage": _ADMIN, "activity.view": _ADMIN,
    # Point of Sale: only the Cashier can sell. Veterinary Staff has NO POS or sales access.
    "pos.use": {"cashier"},             # the POS screen, checkout and the cashier's own receipts
    "pos.data": _ADMIN,                 # sales records, receipts, summaries, CSV export, service list
    "pos.manage": _ADMIN,               # void a sale, manage the services list
}


# ---------------------------------------------------------------------------
# Current user and permissions
# ---------------------------------------------------------------------------
def current_user():
    if "user" in g:
        return g.user
    g.user = None
    uid = session.get("user_id")
    if uid:
        for u in load("users"):
            # an account with an unknown role is treated as not signed in
            if u["user_id"] == uid and u.get("active", True) and u.get("role") in ROLE_LABELS:
                g.user = u
                break
    return g.user


def can(permission):
    """True when the signed-in user's role holds this permission (decided on the server)."""
    u = current_user()
    return bool(u) and u.get("role") in PERMISSIONS.get(permission, ())


def role_home(user=None):
    user = user or current_user()
    role = (user or {}).get("role")
    if role == "admin":
        return url_for("admin_dashboard")
    if role == "staff":
        return url_for("staff_dashboard")
    if role == "cashier":
        return url_for("pos_screen")
    return url_for("login")


def safe_next(target, default=None):
    """Only allow redirects to pages inside PawTrack."""
    if target and target.startswith("/") and not target.startswith("//"):
        return target
    return default or role_home()


# ---------------------------------------------------------------------------
# Route decorators
# ---------------------------------------------------------------------------
def login_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if not current_user():
            session.clear()
            flash("Please log in to continue.", "warning")
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapper


def admin_required(view):
    """Checked on the server, so typing the URL directly does not bypass it."""
    @wraps(view)
    @login_required
    def wrapper(*args, **kwargs):
        if current_user()["role"] != "admin":
            abort(403)
        return view(*args, **kwargs)
    return wrapper


def permission_required(permission):
    """Server-side check for one named permission. Hiding a button is never enough."""
    def deco(view):
        @wraps(view)
        @login_required
        def wrapper(*args, **kwargs):
            if not can(permission):
                abort(403)
            return view(*args, **kwargs)
        return wrapper
    return deco


# ---------------------------------------------------------------------------
# CSRF and template globals
# ---------------------------------------------------------------------------
def csrf_token():
    if "csrf" not in session:
        session["csrf"] = secrets.token_hex(16)
    return session["csrf"]


def init_access_gate(app):
    """Optional HTTP Basic Auth gate for public hosting (Tailscale Funnel, ngrok, ...).

    It is only active when BOTH PAWTRACK_GATE_USER and PAWTRACK_GATE_PASSWORD are
    set in .env, so normal LAN use is unchanged. When active it sits in front of
    the PawTrack login page: a visitor must pass this shared password before they
    can even see the sign-in form.

    The public QR page (/animal/<token>) stays open on purpose: it is already
    protected by its random token and must load for anyone holding a printed tag.
    """
    user = os.getenv("PAWTRACK_GATE_USER", "").strip()
    password = os.getenv("PAWTRACK_GATE_PASSWORD", "")
    if not user or not password:
        return
    expected = base64.b64encode(f"{user}:{password}".encode("utf-8")).decode("ascii")
    # The scanned-QR page is public, so its styles, scripts and logo must load
    # too. Uploaded photos and QR images stay behind the gate.
    open_paths = ("/animal/", "/static/css/", "/static/js/", "/static/img/", "/static/fonts/")

    @app.before_request
    def access_gate():
        if request.path.startswith(open_paths):
            return None
        header = request.headers.get("Authorization", "")
        if header.startswith("Basic "):
            provided = header[6:].strip().encode("utf-8", "ignore")
            if secrets.compare_digest(provided, expected.encode("ascii")):
                return None
        return Response(
            "PawTrack is private. Enter the access username and password.",
            401,
            {"WWW-Authenticate": 'Basic realm="PawTrack", charset="UTF-8"',
             "Cache-Control": "no-store"},
        )


def init_security(app):
    """Wire request hooks, error pages and security-related template globals."""
    app.jinja_env.globals["can"] = can
    app.jinja_env.globals["role_home"] = lambda: role_home()
    app.jinja_env.globals["csrf_token"] = csrf_token   # also visible inside imported macros

    @app.before_request
    def check_csrf():
        if request.method == "POST":
            sent = request.form.get("csrf_token", "")
            if not sent or not secrets.compare_digest(sent, session.get("csrf", "")):
                abort(400, "Your form expired. Please go back, refresh the page, and try again.")

    @app.context_processor
    def inject_globals():
        s = get_settings()
        u = current_user()
        return {"user": u, "clinic": s["clinic"], "role_label": ROLE_LABELS.get((u or {}).get("role"), ""),
                "today": date.today().isoformat(), "app_name": "PawTrack"}

    @app.after_request
    def security_headers(resp):
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["X-Frame-Options"] = "SAMEORIGIN"
        resp.headers["Referrer-Policy"] = "same-origin"
        return resp

    @app.errorhandler(400)
    @app.errorhandler(403)
    @app.errorhandler(404)
    @app.errorhandler(413)
    def http_error(err):
        messages = {400: "Bad request", 403: "You do not have permission to open this page.",
                    404: "We couldn't find that page.",
                    413: "That file is too large. Please upload another picture (max 100 MB)."}
        detail = err.description if err.code == 400 else messages[err.code]
        # Keep identity-verification failures inside the popup instead of the
        # full error page (which would show the whole system / dashboard link).
        try:
            from flask import request
            if request.path.startswith("/verify"):
                from flask import flash, render_template as _rt
                flash(detail, "warning")
                from pawtrack.services.identity import ID_TYPES
                return _rt("verify_start.html", id_types=ID_TYPES), err.code
        except Exception:
            pass
        return render_template("error.html", code=err.code, message=detail), err.code
