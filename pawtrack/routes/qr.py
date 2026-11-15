"""
PawTrack - QR identification and the public animal page
"""
import secrets

from flask import abort, flash, redirect, render_template, send_file, url_for

from ..extensions import app
from ..security import permission_required
from ..services.qr import make_qr, qr_context, qr_path, tag_qr_src
from ..services.vaccinations import animal_vax_info
from ..storage import load
from .animals import get_animal_or_404


@app.route("/animals/<animal_id>/qr")
@permission_required("qr.use")
def qr_view(animal_id):
    animal = get_animal_or_404(animal_id)
    if not qr_path(animal_id).exists() and not make_qr(animal):
        flash("The 'qrcode' package is not installed. Run: pip install -r requirements.txt", "error")
    return render_template("qr_animal.html", a=animal, has_qr=qr_path(animal_id).exists(),
                           info=animal_vax_info(animal_id), **qr_context(animal))


@app.route("/animals/<animal_id>/id-tag")
@permission_required("qr.use")
def animal_id_tag(animal_id):
    animal = get_animal_or_404(animal_id)
    src = tag_qr_src(animal)
    if not src:
        flash("The 'qrcode' package is not installed. Run: pip install -r requirements.txt", "error")
        return redirect(url_for("animal_view", animal_id=animal_id))
    return render_template("id_tag.html", a=animal, qr_src=src, **qr_context(animal))


@app.route("/animals/<animal_id>/qr/download")
@permission_required("qr.use")
def qr_download(animal_id):
    animal = get_animal_or_404(animal_id)
    if not qr_path(animal_id).exists():
        make_qr(animal)
    if not qr_path(animal_id).exists():
        abort(404)
    return send_file(qr_path(animal_id), as_attachment=True, download_name=f"PawTrack-QR-{animal_id}.png")


@app.route("/animals/<animal_id>/qr/regenerate", methods=["POST"])
@permission_required("qr.use")
def qr_regenerate(animal_id):
    animal = get_animal_or_404(animal_id)
    flash("QR code regenerated." if make_qr(animal) else "Could not create QR: install the 'qrcode' package.",
          "success" if qr_path(animal_id).exists() else "error")
    return redirect(url_for("qr_view", animal_id=animal_id))


@app.route("/animal/<token>")
def public_animal(token):
    """Public page opened when someone scans the QR. Shows NO owner details."""
    animal = next((a for a in load("animals") if secrets.compare_digest(a.get("qr_token", ""), token)), None)
    if not animal:
        abort(404)
    return render_template("qr_public.html", a=animal, info=animal_vax_info(animal["animal_id"]))
