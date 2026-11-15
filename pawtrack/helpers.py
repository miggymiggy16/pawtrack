"""
PawTrack - shared helpers
=========================
Dates, formatting, money, file names, image uploads and template filters.
Nothing here reads or writes the database; storage.py does that.
"""
import io
import re
import socket
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from flask import url_for

from .config import (ANIMAL_PHOTO_DIR, EMAIL_RE, IMAGE_EXTS, IMG_DIR,
                     MAX_IMAGE_BYTES, UPLOAD_DIR)


# ---------------------------------------------------------------------------
# Dates and formatting
# ---------------------------------------------------------------------------
def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def parse_date(value):
    try:
        return datetime.strptime(str(value), "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def days_until(date_str):
    d = parse_date(date_str)
    return (d - date.today()).days if d else None


def valid_email(value):
    return bool(EMAIL_RE.match(value or ""))


def lan_ip():
    """Best guess of this computer's address on the local network."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))       # no traffic is actually sent
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return "127.0.0.1"


def fmt_date(value):
    d = parse_date(value) if not isinstance(value, date) else value
    return d.strftime("%b %d, %Y") if d else "-"


def fmt_dt(value):
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S").strftime("%b %d, %Y %I:%M %p")
    except (ValueError, TypeError):
        return value or "-"


def money(value):
    try:
        return "\u20b1{:,.2f}".format(float(value))
    except (ValueError, TypeError):
        return "\u20b10.00"


def parse_money(raw):
    """'150', '150.5', '1,500.00', '\u20b1150' -> Decimal pesos with 2 places. Raises ValueError."""
    text = str(raw if raw is not None else "").replace("\u20b1", "").replace(",", "").replace(" ", "").strip()
    if not text:
        raise ValueError("empty")
    try:
        val = Decimal(text)
    except InvalidOperation:
        raise ValueError("not a number")
    if not val.is_finite():
        raise ValueError("not a number")
    if val != val.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP):
        raise ValueError("more than 2 decimals")
    return val.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def item_value(qty, cost):
    """Stock value in pesos, calculated with Decimal so there is no float drift."""
    return float((Decimal(str(qty)) * Decimal(str(cost))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def slug(value):
    return re.sub(r"[^a-z0-9]+", "-", str(value).lower()).strip("-")


def _safe_cell(value):
    """Block spreadsheet formula injection in CSV exports."""
    text = str(value)
    if text == "-":
        return value
    return "'" + text if text[:1] in ("=", "+", "-", "@") else value


# ---------------------------------------------------------------------------
# Image URLs
# ---------------------------------------------------------------------------
def item_image_url(item):
    """URL of an item's picture, or None if it has none / the file is missing."""
    name = (item or {}).get("image")
    if name and re.match(r"^[A-Za-z0-9_.-]+$", name) and (UPLOAD_DIR / name).is_file():
        return url_for("static", filename=f"uploads/inventory/{name}")
    return None


def item_image_url_safe(item):
    """True if the item already has a picture file on disk (works outside a request)."""
    name = (item or {}).get("image")
    return bool(name and re.match(r"^[A-Za-z0-9_.-]+$", name) and (UPLOAD_DIR / name).is_file())


def animal_photo_url(animal):
    """URL of an animal's profile photo, or None if it has none / the file is missing."""
    name = (animal or {}).get("photo")
    if name and re.match(r"^[A-Za-z0-9_.-]+$", name) and (ANIMAL_PHOTO_DIR / name).is_file():
        return url_for("static", filename=f"uploads/animals/{name}")
    return None


def animal_photo_safe(animal):
    """True if the animal already has a photo file on disk (works outside a request)."""
    name = (animal or {}).get("photo")
    return bool(name and re.match(r"^[A-Za-z0-9_.-]+$", name) and (ANIMAL_PHOTO_DIR / name).is_file())


def logo_url():
    """The clinic's real logo if static/img/logo.(png|jpg|jpeg|webp|svg) exists, else None."""
    for ext in ("png", "jpg", "jpeg", "webp", "svg"):
        f = IMG_DIR / f"logo.{ext}"
        if f.is_file():
            return url_for("static", filename=f"img/logo.{ext}") + f"?v={int(f.stat().st_mtime)}"
    return None


# ---------------------------------------------------------------------------
# Image uploads (validated and re-encoded with Pillow)
# ---------------------------------------------------------------------------
def process_image_bytes(raw, label="Product picture"):
    """Re-encode image bytes with Pillow so only real images are ever stored.
    The picture is only ever scaled DOWN with thumbnail(), which keeps its aspect ratio
    (nothing is stretched or squashed). Returns (bytes, ext, error)."""
    try:
        from PIL import Image, ImageOps
        img = Image.open(io.BytesIO(raw))
        img.load()
        img = ImageOps.exif_transpose(img)           # phone photos: respect the camera rotation
        img.thumbnail((900, 900))
        out = io.BytesIO()
        if img.mode in ("RGBA", "LA", "P"):
            img.convert("RGBA").save(out, "PNG", optimize=True)
            return out.getvalue(), "png", None
        img.convert("RGB").save(out, "JPEG", quality=88, optimize=True)
        return out.getvalue(), "jpg", None
    except ImportError:
        return None, None, "Pillow is not installed, so pictures cannot be uploaded. Run: pip install -r requirements.txt"
    except Exception:
        return None, None, "That file is not a valid image."


def read_product_image(file_storage, label="Product picture"):
    """Validate an uploaded picture. Returns (bytes, ext, error). (None, None, None) = nothing uploaded."""
    if not file_storage or not file_storage.filename:
        return None, None, None
    ext = file_storage.filename.rsplit(".", 1)[-1].lower() if "." in file_storage.filename else ""
    if ext not in IMAGE_EXTS:
        return None, None, f"{label} must be a PNG, JPG, GIF or WEBP file."
    raw = file_storage.read(MAX_IMAGE_BYTES + 1)
    if not raw:
        return None, None, f"The {label.lower()} file is empty."
    if len(raw) > MAX_IMAGE_BYTES:
        return None, None, f"{label} must be 4 MB or smaller."
    return process_image_bytes(raw, label)


def store_product_image(item_id, data, ext):
    import secrets
    name = f"{item_id}-{secrets.token_hex(4)}.{ext}"
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    (UPLOAD_DIR / name).write_bytes(data)
    return name


def store_animal_photo(animal_id, data, ext):
    import secrets
    name = f"{animal_id}-{secrets.token_hex(4)}.{ext}"
    ANIMAL_PHOTO_DIR.mkdir(parents=True, exist_ok=True)
    (ANIMAL_PHOTO_DIR / name).write_bytes(data)
    return name


def delete_animal_photo(name):
    if name and re.match(r"^[A-Za-z0-9_.-]+$", name) and (ANIMAL_PHOTO_DIR / name).is_file():
        try:
            (ANIMAL_PHOTO_DIR / name).unlink()
        except OSError:
            pass


def delete_product_image(name):
    if name and re.match(r"^[A-Za-z0-9_.-]+$", name) and (UPLOAD_DIR / name).is_file():
        try:
            (UPLOAD_DIR / name).unlink()
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Jinja filters and globals
# ---------------------------------------------------------------------------
def register_template_helpers(app):
    """Register the filters and globals used by every template."""
    app.add_template_filter(fmt_date, "fmt_date")
    app.add_template_filter(fmt_dt, "fmt_dt")
    app.add_template_filter(money, "money")
    app.add_template_filter(slug, "slug")
    app.jinja_env.globals.update(
        item_image_url=item_image_url,
        animal_photo_url=animal_photo_url,
        logo_url=logo_url,
    )
