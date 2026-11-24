"""
PawTrack - integrated identity verification
==========================================
Combines Valid ID Verification and Face Recognition into one workflow:

    ID upload -> ID scan (OCR) -> face registration/capture -> face matching
    -> personal information -> final verification result

OCR uses PaddleOCR (open source). Face matching reuses the InsightFace
descriptors from services.face. Verification records are stored in the
``verifications`` collection.
"""
import io
import os
import re
import threading
from datetime import date, datetime

import numpy as np
from PIL import Image

from ..config import ANIMAL_PHOTO_DIR, UPLOAD_DIR
from ..helpers import now_str
from ..storage import edit, load

ID_TYPES = ["Philippine National ID", "Driver's License", "Passport", "UMID"]
ID_TYPE_KEYS = {
    "Philippine National ID": "philsys",
    "Driver's License": "drivers_license",
    "Passport": "passport",
    "UMID": "umid",
}

VERIFICATION_DIR = UPLOAD_DIR.parent / "verifications"  # static/uploads/verifications
VERIFICATION_DIR.mkdir(parents=True, exist_ok=True)

_face_engine = None
_face_error = None
_face_lock = threading.Lock()
_ocr_engine = None
_ocr_error = None
_ocr_lock = threading.Lock()


def _load_face():
    from .face import _load_engine as load_insight
    return load_insight()


def _load_ocr():
    global _ocr_engine, _ocr_error
    if _ocr_engine is not None:
        return _ocr_engine
    with _ocr_lock:
        if _ocr_engine is not None:
            return _ocr_engine
        try:
            from paddleocr import PaddleOCR
        except Exception as exc:
            _ocr_error = str(exc)
            raise RuntimeError("PaddleOCR is not installed. Run: pip install paddleocr") from exc
        try:
            engine = PaddleOCR(use_angle_cls=True, lang="en")
        except Exception as exc:
            _ocr_error = str(exc)
            raise RuntimeError("PaddleOCR could not start: " + str(exc)) from exc
        _ocr_engine = engine
        return engine


def ocr_status():
    if _ocr_engine is not None:
        return "ready"
    if _ocr_error:
        return "error"
    return "idle"


def _decode_image(image_bytes):
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    return img


def run_ocr(image_bytes):
    """Return (full_text, list_of_(text, box)) from an image."""
    engine = _load_ocr()
    img = _decode_image(image_bytes)
    arr = np.array(img)
    try:
        result = engine.ocr(arr, cls=True)
    except Exception:
        try:
            result = engine.ocr(arr)
        except Exception as exc:
            raise RuntimeError("OCR failed: " + str(exc))
    lines = []
    boxes = []
    if result:
        for page in result:
            if not page:
                continue
            for item in page:
                # item: [box, (text, score)] or [box, text]
                try:
                    box = item[0]
                    text_part = item[1]
                    if isinstance(text_part, (list, tuple)):
                        text = text_part[0]
                        score = text_part[1] if len(text_part) > 1 else 1.0
                    else:
                        text = text_part
                        score = 1.0
                except Exception:
                    continue
                if text:
                    lines.append(str(text).strip())
                    boxes.append((box, str(text).strip(), float(score)))
    full = "\n".join(lines)
    return full, boxes


DATE_RE = re.compile(r"\b(\d{1,2})[\/\-.](\d{1,2})[\/\-.](\d{2,4})\b")
ID_NUMBER_RE = re.compile(r"\b([A-Z0-9][A-Z0-9\-]{4,}[A-Z0-9])\b")


def _normalize_date(s):
    m = DATE_RE.search(s)
    if not m:
        return ""
    d, mo, y = m.group(1), m.group(2), m.group(3)
    if len(y) == 2:
        y = ("20" if int(y) < 50 else "19") + y
    try:
        dt = datetime(int(y), int(mo), int(d)).date()
        return dt.isoformat()
    except ValueError:
        try:
            dt = datetime(int(y), int(d), int(mo)).date()
            return dt.isoformat()
        except ValueError:
            return ""


def _age_from_dob(dob_iso):
    if not dob_iso:
        return ""
    try:
        d = datetime.fromisoformat(dob_iso).date()
    except ValueError:
        return ""
    today = date.today()
    age = today.year - d.year - ((today.month, today.day) < (d.month, d.day))
    return str(age) if age >= 0 else ""


NAME_LABELS = ["name", "full name", "given name", "surname", "last name", "first name"]
ADDRESS_LABELS = ["address", "addr"]
ID_LABELS = ["id no", "id number", "card no", "license no", "passport no", "umid", "number"]
EXPIRY_LABELS = ["expiry", "expires", "valid until", "valid thru", "expiration"]


def _find_labeled(lines, labels):
    low = [l.lower() for l in lines]
    for i, l in enumerate(low):
        for lab in labels:
            if lab in l:
                # value may be on same line after colon, or next line
                val = l
                for sep in (":", "-", "="):
                    if sep in val:
                        parts = val.split(sep, 1)
                        if len(parts) == 2 and parts[1].strip():
                            return parts[1].strip()
                if i + 1 < len(lines):
                    return lines[i + 1].strip()
    return ""


def parse_fields(text):
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    full_text = "\n".join(lines)

    # Name: try labeled, else first line of capitalized words
    name = _find_labeled(lines, NAME_LABELS)
    if not name:
        for ln in lines:
            if re.match(r"^[A-Z][A-Za-z .,'-]{4,}$", ln) and " " in ln:
                name = ln
                break

    # DOB
    dob = ""
    for ln in lines:
        if any(k in ln.lower() for k in ("birth", "dob", "born")):
            dob = _normalize_date(ln)
            if dob:
                break
    if not dob:
        # first date that is not expiry
        for m in DATE_RE.finditer(full_text):
            cand = _normalize_date(m.group(0))
            if cand:
                # heuristic: birth years before 2010
                try:
                    if int(cand[:4]) <= 2010:
                        dob = cand
                        break
                except ValueError:
                    pass

    # Expiry
    expiry = ""
    for ln in lines:
        if any(k in ln.lower() for k in EXPIRY_LABELS):
            expiry = _normalize_date(ln)
            if expiry:
                break

    # Address
    address = _find_labeled(lines, ADDRESS_LABELS)
    if not address:
        # look for a line containing common address words
        for ln in lines:
            if re.search(r"\b(st|street|ave|avenue|rd|road|brgy|barangay|city|province)\b", ln, re.I):
                address = ln
                break

    # ID number
    id_number = _find_labeled(lines, ID_LABELS)
    if not id_number:
        for ln in lines:
            m = ID_NUMBER_RE.search(ln)
            if m:
                id_number = m.group(1)
                break

    age = _age_from_dob(dob)
    return {
        "full_name": name,
        "date_of_birth": dob,
        "age": age,
        "address": address,
        "id_number": id_number,
        "expiry_date": expiry,
        "raw_text": full_text,
    }


def detect_face_on_id(image_bytes):
    """Return (embedding, crop_bytes) for the face found on the ID image."""
    try:
        from .face import embedding as face_embedding
    except Exception:
        return None, None
    # embedding() requires exactly one face; ID photos usually one face.
    try:
        desc = face_embedding(image_bytes)
    except Exception:
        return None, None
    # crop face using insightface bbox for display
    crop = None
    try:
        import cv2
        from insightface.app import FaceAnalysis
        # reuse face module's engine loader
        from .face import _load_engine
        engine = _load_engine()
        img = cv2.imdecode(np.frombuffer(image_bytes, np.uint8), cv2.IMREAD_COLOR)
        faces = [f for f in engine.get(img) if float(f.det_score) >= 0.5]
        if faces:
            f = max(faces, key=lambda x: (x.bbox[2]-x.bbox[0])*(x.bbox[3]-x.bbox[1]))
            x1, y1, x2, y2 = [int(v) for v in f.bbox]
            h, w = img.shape[:2]
            x1, y1 = max(0, x1), max(0, y1)
            x2, y2 = min(w, x2), min(h, y2)
            crop_img = img[y1:y2, x1:x2]
            if crop_img.size:
                ok, buf = cv2.imencode(".jpg", crop_img)
                if ok:
                    crop = buf.tobytes()
    except Exception:
        crop = None
    return desc, crop


def scan_id(image_bytes, id_type):
    text, boxes = run_ocr(image_bytes)
    fields = parse_fields(text)
    fields["id_type"] = id_type
    id_face_desc, id_face_crop = detect_face_on_id(image_bytes)
    fields["id_face_found"] = bool(id_face_desc)
    # store crop
    crop_path = None
    if id_face_crop:
        import uuid
        name = "idface_" + uuid.uuid4().hex + ".jpg"
        path = VERIFICATION_DIR / name
        with open(path, "wb") as fh:
            fh.write(id_face_crop)
        crop_path = "uploads/verifications/" + name
    fields["id_face_crop"] = crop_path
    fields["id_face_descriptor"] = id_face_desc
    # completeness check
    required = ["full_name", "date_of_birth", "id_number"]
    missing = [r for r in required if not fields.get(r)]
    fields["complete"] = (len(missing) == 0) and bool(id_face_desc)
    fields["missing"] = missing
    return fields


def match_faces(id_descriptor, captured_descriptor):
    if not id_descriptor or not captured_descriptor:
        return False, -1.0
    from .face import similarity
    score = similarity(id_descriptor, captured_descriptor)
    threshold = 0.45
    try:
        import os
        threshold = float(os.getenv("FACE_MATCH_THRESHOLD", "0.45"))
    except Exception:
        pass
    return (score >= threshold), float(score)


def save_verification(data):
    import uuid
    rec = dict(data)
    rec.setdefault("verification_id", "VER-" + uuid.uuid4().hex[:8].upper())
    rec.setdefault("created_at", now_str())
    rec.setdefault("status", "verified" if rec.get("face_matched") else "failed")
    with edit("verifications") as items:
        items.append(rec)
    return rec["verification_id"]


def get_verification(vid):
    for v in load("verifications"):
        if v.get("verification_id") == vid:
            return v
    return None


def latest_verified_for_session(session):
    vid = session.get("verification_id") if session else None
    if not vid:
        return None
    return get_verification(vid)
