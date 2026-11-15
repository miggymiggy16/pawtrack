"""
PawTrack
========
Application package. Importing it builds the Flask app, registers security,
template helpers/globals and every route, then prepares storage.

Run the program with ``python app.py`` from the project folder.
"""
import importlib

from .extensions import app
from .helpers import register_template_helpers
from .security import init_access_gate, init_security
from .services.notifications import register_notification_globals
from .services.qr import register_qr_globals
from .storage import init_mysql, init_storage

# Optional shared password in front of everything (only when .env sets it).
init_access_gate(app)

# Security hooks and the functions/filters templates rely on.
init_security(app)
register_template_helpers(app)
register_qr_globals(app)
register_notification_globals(app)

# Importing the routes package registers every URL on the shared app.
importlib.import_module(".routes", __name__)

# Connect to MySQL when configured, otherwise prepare the JSON files/folders,
# default accounts and first-run sample data (all steps are idempotent).
init_mysql()
init_storage()

__all__ = ["app"]
