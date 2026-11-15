"""
PawTrack - Flask application object
===================================
A single application instance is created here and imported by every route
module. Keeping one object (instead of an application factory) means all URL
endpoint names stay exactly the same as before the refactor, so every template
and redirect continues to work unchanged.
"""
import os
import secrets
from datetime import timedelta

from flask import Flask

from .config import BASE_DIR

app = Flask(
    __name__,
    template_folder=str(BASE_DIR / "templates"),
    static_folder=str(BASE_DIR / "static"),
)

_secret = os.getenv("SECRET_KEY", "")
if not _secret or _secret == "change_this_secret_key":
    # Without a real key we generate a temporary one. Logins reset on restart.
    _secret = secrets.token_hex(32)
    print("[PawTrack] WARNING: SECRET_KEY is not set in .env - using a temporary key.")

app.config.update(
    SECRET_KEY=_secret,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
    MAX_CONTENT_LENGTH=6 * 1024 * 1024,      # room for product photos (checked again at 4 MB)
)
