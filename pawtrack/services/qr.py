"""
PawTrack - QR codes
===================
Each animal has a random qr_token. The QR image points to the public page
/animal/<token>, which shows no owner details.
"""
import base64
import io

from flask import current_app, request, url_for

from ..config import QR_DIR
from ..helpers import lan_ip
from ..storage import get_settings


def base_url():
    configured = get_settings().get("public_base_url", "").strip().rstrip("/")
    return configured or request.host_url.rstrip("/")


def qr_target(animal):
    return f"{base_url()}/animal/{animal['qr_token']}"


def qr_path(animal_id):
    return QR_DIR / f"{animal_id}.png"


def animal_qr_url(animal):
    """URL of the animal's QR image (created on demand), or None if the qrcode package is missing."""
    if not qr_path(animal["animal_id"]).exists() and not make_qr(animal):
        return None
    return url_for("static", filename=f"qr/{animal['animal_id']}.png")


def make_qr(animal):
    """Create static/qr/<animal_id>.png pointing to the animal's public page."""
    try:
        import qrcode
    except ImportError:
        return False
    QR_DIR.mkdir(parents=True, exist_ok=True)
    qrcode.make(qr_target(animal), box_size=10, border=4).save(str(qr_path(animal["animal_id"])))
    return True


def tag_qr_src(animal):
    """QR image for the small collar tag: tight 1-module margin so the code can be printed larger on a
    tiny tag. Returned as an inline data URI. Falls back to the normal QR image if that fails."""
    try:
        import qrcode
        import qrcode.constants
        qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=10, border=1)
        qr.add_data(qr_target(animal))
        qr.make(fit=True)
        buf = io.BytesIO()
        qr.make_image(fill_color="black", back_color="white").save(buf, format="PNG")
        return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
    except Exception:
        current_app.logger.exception("Could not build the collar tag QR for %s", animal.get("animal_id"))
        return animal_qr_url(animal)


def qr_context(animal):
    """Extra values shown on the QR pages (local network hint)."""
    base = base_url()
    host = request.host.split(":")[0]
    return {"url": qr_target(animal),
            "local_only": host in ("127.0.0.1", "localhost") and not get_settings().get("public_base_url"),
            "lan_url": f"http://{lan_ip()}:{request.host.split(':')[-1] if ':' in request.host else '5000'}",
            "base": base}


def register_qr_globals(app):
    app.jinja_env.globals.update(animal_qr_url=animal_qr_url)
