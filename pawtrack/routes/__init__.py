"""
PawTrack - route modules
========================
Importing this package registers every URL on the shared Flask application.
Each module keeps the exact endpoint names the templates and redirects expect.
"""
from . import (analytics, animals, auth, dashboard, identity, inventory, notifications,
               pos, qr, reports, settings, users, vaccinations)

__all__ = [
    "analytics", "animals", "auth", "dashboard", "identity", "inventory", "notifications",
    "pos", "qr", "reports", "settings", "users", "vaccinations",
]
