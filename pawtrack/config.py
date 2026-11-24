"""
PawTrack - configuration and constants
======================================
Every fixed value the application uses lives here: folder locations, the
choices shown in forms, validation limits and the default settings.
"""
import os
import re
from decimal import Decimal
from pathlib import Path

from dotenv import load_dotenv

# PawTrack/  (the folder that contains app.py and this package)
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")          # reads SECRET_KEY, MAIL_*, DB_* from .env

# ---------------------------------------------------------------------------
# Folders
# ---------------------------------------------------------------------------
DATA_DIR = BASE_DIR / "data"
QR_DIR = BASE_DIR / "static" / "qr"
IMG_DIR = BASE_DIR / "static" / "img"                          # clinic logo lives here
UPLOAD_DIR = BASE_DIR / "static" / "uploads" / "inventory"     # inventory product images
ANIMAL_PHOTO_DIR = BASE_DIR / "static" / "uploads" / "animals"  # animal profile photos
SEED_DIR = BASE_DIR / "seed_assets"                            # pictures supplied with this project

# ---------------------------------------------------------------------------
# Form choices and validation limits
# ---------------------------------------------------------------------------
SPECIES_CHOICES = ["Dog", "Cat", "Rabbit", "Bird", "Other"]
SEX_CHOICES = ["Male", "Female", "Unknown"]
OWNERSHIP_CHOICES = ["Owned", "Stray"]
CATEGORIES = ["Vaccines", "Medicines", "Medical Supplies", "Equipment",
              "Cleaning Supplies", "Animal Supplies", "Other"]
NOTIFY_TYPES = ["Upcoming Vaccination", "Due Today", "Overdue Vaccination",
                "Vaccination Updated", "Test Email"]
VACCINE_SUGGESTIONS = ["Anti-Rabies", "5-in-1 (DHPP)", "FVRCP", "Bordetella",
                       "Leptospirosis", "Feline Leukemia (FeLV)", "Deworming"]
VACCINE_TYPES = ["Rabies", "Combination (DHPP)", "Feline combination (FVRCP)", "Bordetella",
                 "Leptospirosis", "Feline Leukemia (FeLV)", "Other"]
MAX_IMAGE_BYTES = 100 * 1024 * 1024
MAX_QTY = 1_000_000                    # sanity limit for any stock quantity
IMAGE_EXTS = {"png", "jpg", "jpeg", "gif", "webp"}

ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,30}$")           # safe for file names & URLs
USERNAME_RE = re.compile(r"^[A-Za-z0-9_.-]{3,30}$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# Counts as "vaccinated" on dashboards and reports
UP_TO_DATE = {"Vaccinated", "Upcoming", "Due Today"}

# ---------------------------------------------------------------------------
# Default settings and seed accounts
# ---------------------------------------------------------------------------
DEFAULT_SETTINGS = {
    "reminder_days": 7,
    "expiry_warning_days": 30,
    "email_enabled": True,
    "public_base_url": "",
    "sample_loaded": False,
    "animal_counter": 0,          # highest Animal ID number ever issued (never goes down)
    "clinic": {"name": "PawTrack Veterinary Clinic", "address": "Naga City, Camarines Sur",
               "phone": "", "email": ""},
}

DEFAULT_FILES = {
    "animals": [], "vaccinations": [], "users": [], "notifications": [],
    "inventory": [], "inventory_transactions": [], "settings": {},
    "pos_sales": [], "pos_services": [], "verifications": [],
    "notification_reads": {},      # {user_id: {notification key: "read at"}}
}

CASHIER_USERNAME, CASHIER_PASSWORD = "Cashier", "Cashier_01"   # created once on first start
STAFF_USERNAME, STAFF_PASSWORD = "Staff_01", "password"        # default Veterinary Staff account

# ---------------------------------------------------------------------------
# Point of Sale
# ---------------------------------------------------------------------------
PAYMENT_METHODS = ["Cash", "E-Wallet", "Bank Transfer"]
VAT_RATE = Decimal("0.12")          # 12% VAT - already inside every shelf price, never added on top
VAT_PERCENT = 12
MAX_SALE_LINES = 60
MAX_SALE_QTY = 9999
SAMPLE_PRICES = {"Amoxicillin 250mg": 20, "Ivermectin Injection": 380, "Disposable Syringe 3 mL": 12,
                 "Surgical Gloves": 300, "Digital Thermometer": 280, "Disinfectant 1L": 220,
                 "Dog Food 5kg": 950}
SAMPLE_SERVICES = [("Consultation", 350), ("Deworming", 250), ("Nail trimming", 150),
                   ("Grooming (small pet)", 400)]

# ---------------------------------------------------------------------------
# MySQL/MariaDB (required - the database is the only store)
# ---------------------------------------------------------------------------
DB_NAME = os.getenv("DB_NAME", "").strip()
