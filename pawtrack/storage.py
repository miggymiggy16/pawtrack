"""
PawTrack - storage layer
========================
The ONLY place that touches stored data. Every route and service reads/writes
through load(), save() and edit().

If DB_NAME is set in .env these calls go to MySQL (see pawtrack/mysql_store.py and
schema.sql) - there is no other store. A lock inside this process serialises
read-modify-write blocks; each save() is a single database transaction.

DB_NAME must be set in .env and MySQL/MariaDB must be reachable; otherwise the
app stops at startup with a readable message.
"""
import json
import os
import re
import threading
from contextlib import contextmanager

from werkzeug.security import generate_password_hash

from .config import (ANIMAL_PHOTO_DIR, DB_NAME, DEFAULT_FILES,
                     DEFAULT_SETTINGS, QR_DIR, UPLOAD_DIR)
from .helpers import now_str

lock = threading.RLock()
_store = None


# ---------------------------------------------------------------------------
# MySQL (the only store)
# ---------------------------------------------------------------------------
def using_mysql():
    return _store is not None


def init_mysql():
    """Connect to MySQL (called once at startup). Stops the app with a clear message if it cannot."""
    global _store
    host = os.getenv("DB_HOST", "127.0.0.1")
    port = os.getenv("DB_PORT", "3306")
    user = os.getenv("DB_USER", "root")
    database = DB_NAME
    if not database:
        _fatal_mysql("DB_NAME is not set in .env.")
    from .mysql_store import MySQLStore
    store = MySQLStore(host=host, port=int(port), user=user,
                       password=os.getenv("DB_PASSWORD", ""), database=database)
    try:
        if os.getenv("DB_AUTO_CREATE", "True").lower() in ("1", "true", "yes"):
            store.create_database()
        store.create_tables()
    except Exception as exc:
        _fatal_mysql(f"could not connect to MySQL/MariaDB at {host}:{port} (user '{user}', database '{database}'): {exc}")
    _store = store
    print(f"[PawTrack] Using MySQL database '{database}' on {host}.")


def _fatal_mysql(reason):
    print()
    print(f"[PawTrack] DATABASE ERROR: {reason}")
    print()
    print("PawTrack stores everything in MySQL/MariaDB now - the data files under")
    print("data/*.json are only a legacy copy, never the live store.")
    print()
    print("How to fix it:")
    print("  1. Make sure MySQL or MariaDB is running on this computer")
    print("     (XAMPP -> Control Panel -> Start next to 'MySQL').")
    print("  2. In .env, check these values:")
    print("       DB_HOST=127.0.0.1")
    print("       DB_PORT=3306")
    print("       DB_USER=root")
    print("       DB_PASSWORD=        (blank is fine for a default XAMPP install)")
    print("       DB_NAME=pawtrack")
    print("  3. Start PawTrack again. If the database is empty but data/*.json exists,")
    print("     the old data is imported automatically on the first run.")
    raise SystemExit(1)


def load(name):
    """Return the stored data for `name` (a fresh copy): a list of dicts, or a dict for settings."""
    with lock:
        return _store.load(name)


def save(name, data):
    """MySQL: one transaction per save()."""
    with lock:
        _store.save(name, data)


@contextmanager
def edit(name):
    """with edit('animals') as animals: ...  -> loads, lets you change, saves."""
    with lock:
        data = load(name)
        yield data
        save(name, data)       # skipped automatically if an error is raised


def import_json_to_mysql():
    """One-time copy of existing data/*.json into EMPTY MySQL tables. Never overwrites.

    Kept only so older installs (which stored data in JSON files) keep working -
    fresh installs never need it.
    """
    from pathlib import Path
    data_dir = Path(__file__).resolve().parent.parent / "data"
    for name in DEFAULT_FILES:
        legacy = data_dir / f"{name}.json"
        if not legacy.exists() or load(name):
            continue
        try:
            with open(legacy, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            print(f"[PawTrack] Could not read {legacy}; skipped.")
            continue
        if data:
            save(name, data)
            print(f"[PawTrack] Imported {legacy.name} into MySQL.")


# ---------------------------------------------------------------------------
# Settings and IDs
# ---------------------------------------------------------------------------
def get_settings():
    s = load("settings")
    merged = {**DEFAULT_SETTINGS, **s}
    merged["clinic"] = {**DEFAULT_SETTINGS["clinic"], **s.get("clinic", {})}
    return merged


def next_id(prefix, items, key, width=4):
    """PT-0001, VAC-0007 ... one more than the highest number in use."""
    top = 0
    for it in items:
        m = re.search(r"(\d+)$", str(it.get(key, "")))
        if m:
            top = max(top, int(m.group(1)))
    return f"{prefix}-{top + 1:0{width}d}"


def issue_animal_id():
    """Create the next unique Animal ID (PT-0001, PT-0002 ...).
    Call this INSIDE `with edit("animals") as animals:` so two registrations can
    never receive the same number. A counter saved in settings only goes up,
    so the ID of a deleted animal is never handed out again."""
    animals = load("animals")
    used = {str(a.get("animal_id", "")).lower() for a in animals}
    top = 0
    for a in animals:
        m = re.match(r"^PT-(\d+)$", str(a.get("animal_id", "")), re.I)
        if m:
            top = max(top, int(m.group(1)))
    with edit("settings") as st:
        n = max(int(st.get("animal_counter", 0) or 0), top) + 1
        while f"pt-{n:04d}" in used:
            n += 1
        st["animal_counter"] = n
    return f"PT-{n:04d}"


# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------
def init_storage():
    """Create folders, import any legacy JSON data, first-run accounts and sample data (once)."""
    from .services.seed import load_sample_data, seed_cashier, seed_images, seed_pos, seed_sample_photos, seed_staff

    QR_DIR.mkdir(parents=True, exist_ok=True)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    ANIMAL_PHOTO_DIR.mkdir(parents=True, exist_ok=True)
    import_json_to_mysql()
    with edit("users") as users:
        if not users:
            users.append({"user_id": "USR-0001", "username": "Admin_01",
                          "full_name": "System Administrator", "email": "",
                          "role": "admin", "active": True,
                          "password_hash": generate_password_hash("password"),
                          "created_at": now_str()})
    seed_cashier()
    seed_staff()
    settings = load("settings")
    if not settings.get("sample_loaded"):
        if not load("animals") and not load("inventory"):
            load_sample_data()
        with edit("settings") as s:
            s["sample_loaded"] = True
    seed_images()
    seed_sample_photos()
    seed_pos()
