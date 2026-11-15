"""
PawTrack - storage layer
========================
The ONLY place that touches stored data. Every route and service reads/writes
through load(), save() and edit().

If DB_NAME is set in .env these calls go to MySQL (see mysql_store.py and
schema.sql). Otherwise they use data/*.json exactly as before. A lock inside
this process serialises read-modify-write blocks; each save() is a single
database transaction.
"""
import json
import os
import re
import tempfile
import threading
from contextlib import contextmanager
from datetime import datetime

from werkzeug.security import generate_password_hash

from .config import (ANIMAL_PHOTO_DIR, DATA_DIR, DB_NAME, DEFAULT_FILES,
                     DEFAULT_SETTINGS, QR_DIR, UPLOAD_DIR)
from .helpers import now_str

lock = threading.RLock()
_store = None


# ---------------------------------------------------------------------------
# MySQL
# ---------------------------------------------------------------------------
def using_mysql():
    return _store is not None


def init_mysql():
    """Connect to MySQL when DB_NAME is configured (called once at startup)."""
    global _store
    if not DB_NAME:
        return
    from mysql_store import MySQLStore
    _store = MySQLStore(host=os.getenv("DB_HOST", "127.0.0.1"), port=os.getenv("DB_PORT", "3306"),
                        user=os.getenv("DB_USER", "root"), password=os.getenv("DB_PASSWORD", ""),
                        database=DB_NAME)
    if os.getenv("DB_AUTO_CREATE", "True").lower() in ("1", "true", "yes"):
        _store.create_database()
    _store.create_tables()
    print(f"[PawTrack] Using MySQL database '{DB_NAME}' on {os.getenv('DB_HOST', '127.0.0.1')}.")


# ---------------------------------------------------------------------------
# JSON files
# ---------------------------------------------------------------------------
def _file(name):
    return DATA_DIR / f"{name}.json"


def _fresh_default(name):
    return json.loads(json.dumps(DEFAULT_FILES[name]))


def load(name):
    """Return the stored data for `name` (a fresh copy): a list of dicts, or a dict for settings."""
    with lock:
        if _store:
            return _store.load(name)
        try:
            with open(_file(name), encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            return _fresh_default(name)
        except json.JSONDecodeError:
            backup = _file(name).with_suffix(f".corrupt-{datetime.now():%Y%m%d%H%M%S}")
            os.replace(_file(name), backup)
            print(f"[PawTrack] {name}.json was unreadable; saved a copy as {backup.name}")
            return _fresh_default(name)


def save(name, data):
    """MySQL: one transaction. JSON: temp file first, then replace, so a crash can't half-write."""
    with lock:
        if _store:
            _store.save(name, data)
            return
        DATA_DIR.mkdir(exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=DATA_DIR, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, _file(name))
        finally:
            if os.path.exists(tmp):
                os.remove(tmp)


@contextmanager
def edit(name):
    """with edit('animals') as animals: ...  -> loads, lets you change, saves."""
    with lock:
        data = load(name)
        yield data
        save(name, data)       # skipped automatically if an error is raised


def import_json_to_mysql():
    """One-time copy of existing data/*.json into EMPTY MySQL tables. Never overwrites."""
    for name in DEFAULT_FILES:
        if not _file(name).exists() or load(name):
            continue
        try:
            with open(_file(name), encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            print(f"[PawTrack] Could not read {name}.json; skipped.")
            continue
        if data:
            save(name, data)
            print(f"[PawTrack] Imported {name}.json into MySQL.")


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
    """Create folders, first-run accounts and sample data (once)."""
    from .services.seed import load_sample_data, seed_cashier, seed_images, seed_pos, seed_staff

    DATA_DIR.mkdir(exist_ok=True)
    QR_DIR.mkdir(parents=True, exist_ok=True)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    ANIMAL_PHOTO_DIR.mkdir(parents=True, exist_ok=True)
    if _store:
        import_json_to_mysql()
    else:
        for name, default in DEFAULT_FILES.items():
            if not _file(name).exists():
                save(name, default)
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
    seed_pos()
