"""
PawTrack - integrated identity verification
==========================================
Combines Valid ID Verification and Face Recognition into one workflow:

    ID upload -> ID scan (OCR) -> face registration/capture -> face matching
    -> personal information -> final verification result

OCR uses Tesseract (open source). Face matching reuses the InsightFace
descriptors from services.face. Verified ID details are stored on the user
record by the Settings identity wizard; this module only provides the scan
and matching primitives.
"""
import io
import os
import re
import threading
from datetime import date, datetime

import numpy as np
from PIL import Image

from ..config import ANIMAL_PHOTO_DIR, UPLOAD_DIR

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


def _silence_fd(func, *args, **kwargs):
    """Run func while suppressing OS-level stdout/stderr (C-level prints)."""
    import os
    devnull = open(os.devnull, "w")
    old_out = os.dup(1)
    old_err = os.dup(2)
    os.dup2(devnull.fileno(), 1)
    os.dup2(devnull.fileno(), 2)
    try:
        return func(*args, **kwargs)
    finally:
        os.dup2(old_out, 1)
        os.dup2(old_err, 2)
        os.close(old_out)
        os.close(old_err)
        devnull.close()


def _load_ocr():
    """Configure and return pytesseract (lightweight OCR, no heavy ML models)."""
    global _ocr_engine, _ocr_error
    if _ocr_engine is not None:
        return _ocr_engine
    with _ocr_lock:
        if _ocr_engine is not None:
            return _ocr_engine
        try:
            import pytesseract
            # Tesseract is installed on Windows but may not be on PATH.
            candidates = [
                os.getenv("TESSERACT_CMD", ""),
                r"C:\Program Files\Tesseract-OCR\tesseract.exe",
                r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
            ]
            for exe in candidates:
                if exe and os.path.exists(exe):
                    pytesseract.pytesseract.tesseract_cmd = exe
                    break
            # Verify Tesseract actually runs.
            pytesseract.get_tesseract_version()
        except Exception as exc:
            _ocr_error = str(exc)
            raise RuntimeError("Tesseract OCR is not installed. Install Tesseract from "
                               "https://github.com/tesseract-ocr/tesseract") from exc
        _ocr_engine = pytesseract
        return _ocr_engine


def ocr_status():
    if _ocr_engine is not None:
        return "ready"
    if _ocr_error:
        return "error"
    return "idle"


def _decode_image(image_bytes):
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    # Keep memory/CPU reasonable: cap the longest side.
    max_side = 1280
    w, h = img.size
    if max(w, h) > max_side:
        scale = max_side / max(w, h)
        img = img.resize((int(w * scale), int(h * scale)))
    return img


def run_ocr(image_bytes):
    """Return (full_text, list_of_(text, box)) from an image."""
    engine = _load_ocr()
    img = _decode_image(image_bytes)
    # Preprocess: grayscale + autocontrast + upscale helps Tesseract read
    # low-contrast text (e.g. red numbers on a busy ID background).
    from PIL import ImageOps
    proc = ImageOps.autocontrast(ImageOps.grayscale(img), cutoff=1)
    proc = proc.resize((proc.width * 2, proc.height * 2))
    try:
        data = engine.image_to_data(proc, lang="eng", config="--psm 6",
                                    output_type=engine.Output.DICT)
    except Exception as exc:
        raise RuntimeError("OCR failed: " + str(exc))
    lines = []
    boxes = []
    n = len(data.get("text", []))
    for i in range(n):
        text = str(data["text"][i]).strip()
        if not text:
            continue
        try:
            conf = float(data["conf"][i])
        except Exception:
            conf = -1.0
        left, top, w, h = (int(data["left"][i]), int(data["top"][i]),
                           int(data["width"][i]), int(data["height"][i]))
        box = [(left, top), (left + w, top), (left + w, top + h), (left, top + h)]
        lines.append(text)
        boxes.append((box, text, conf / 100.0 if conf >= 0 else 0.0))
    # Prefer line-based text from Tesseract so date/label parsing works.
    # Fall back to joining words if image_to_string is unavailable.
    try:
        clean = engine.image_to_string(img, lang="eng")
    except Exception:
        clean = "\n".join(lines)
    if not clean or not clean.strip():
        clean = "\n".join(lines)
    try:
        enhanced = engine.image_to_string(proc, lang="eng", config="--psm 6")
    except Exception:
        enhanced = ""
    # Merge both passes: clean text first for readable names/labels/dates,
    # then enhanced text to add faint details (e.g. red ID number).
    full = (clean or "") + "\n" + (enhanced or "")
    return full, boxes


DATE_RE = re.compile(r"\b(\d{1,2})[\/\-.](\d{1,2})[\/\-.](\d{2,4})\b")
ID_NUMBER_RE = re.compile(r"\b([A-Z0-9][A-Z0-9\-]{4,}[A-Z0-9])\b")
PHILSYS_NUMBER_RE = re.compile(r"\b\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{4}\b")
PHILID_CARD_RE = re.compile(r"\b\d{4}[- ]?\d{4}[- ]?\d{4}\b")


MONTHS = {"january":1,"february":2,"march":3,"april":4,"may":5,"june":6,
          "july":7,"august":8,"september":9,"october":10,"november":11,"december":12,
          "jan":1,"feb":2,"mar":3,"apr":4,"jun":6,"jul":7,"aug":8,"sep":9,"oct":10,"nov":11,"dec":12}

def _normalize_date(s):
    # Month-name form: "January 15, 1995" or "15 January 1995"
    m = re.search(r"([A-Za-z]+)\s+(\d{1,2}),?\s+(\d{4})", s)
    if m and m.group(1).lower() in MONTHS:
        try:
            return datetime(int(m.group(3)), MONTHS[m.group(1).lower()], int(m.group(2))).date().isoformat()
        except ValueError:
            pass
    m = re.search(r"(\d{1,2})\s+([A-Za-z]+),?\s+(\d{4})", s)
    if m and m.group(2).lower() in MONTHS:
        try:
            return datetime(int(m.group(3)), MONTHS[m.group(2).lower()], int(m.group(1))).date().isoformat()
        except ValueError:
            pass
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


NAME_LABELS = ["name", "full name", "given name", "surname", "last name", "first name",
               "apelyido", "pangalan", "gitnang pangalan"]
ADDRESS_LABELS = ["address", "addr", "tirahan"]
ID_LABELS = ["id no", "id number", "card no", "license no", "passport no", "umid", "number",
             "philsys", "psn", "philid"]
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

    # Name: PhilSys-style first/middle/last, or labeled, or first capitalized line
    first = _find_labeled(lines, ["first name", "pangalan", "given name"])
    last = _find_labeled(lines, ["last name", "apelyido", "surname"])
    middle = _find_labeled(lines, ["middle name", "gitnang pangalan"])
    if first or last:
        name = " ".join(x for x in (first, middle, last) if x)
    else:
        name = _find_labeled(lines, NAME_LABELS)
    if not name:
        for ln in lines:
            if re.match(r"^[A-Z][A-Za-z .,'-]{4,}$", ln) and " " in ln:
                name = ln
                break

    # DOB
    dob = ""
    for i, ln in enumerate(lines):
        if any(k in ln.lower() for k in ("birth", "dob", "born")):
            dob = _normalize_date(ln)
            if not dob and i + 1 < len(lines):
                dob = _normalize_date(lines[i + 1])
            if dob:
                break
    if not dob:
        # scan all lines for a month-name or numeric date (prefer earlier birth years)
        for ln in lines:
            cand = _normalize_date(ln)
            if cand:
                try:
                    if int(cand[:4]) <= 2010:
                        dob = cand
                        break
                except ValueError:
                    pass
        if not dob:
            for ln in lines:
                cand = _normalize_date(ln)
                if cand:
                    dob = cand
                    break

    # Expiry
    expiry = ""
    for ln in lines:
        if any(k in ln.lower() for k in EXPIRY_LABELS):
            expiry = _normalize_date(ln)
            if expiry:
                break

    # Address (PhilSys: label, then "PHL", then one or more address lines)
    address = _find_labeled(lines, ADDRESS_LABELS)
    if not address or address.upper() == "PHL" or len(address) < 4:
        address = ""
        for i, ln in enumerate(lines):
            if any(lab in ln.lower() for lab in ADDRESS_LABELS):
                collected = []
                for j in range(i + 1, len(lines)):
                    nxt = lines[j].strip()
                    if not nxt or any(k in nxt.lower() for k in ("expiry", "valid", "signature", "date of")):
                        break
                    if nxt.upper() == "PHL":
                        continue
                    collected.append(nxt)
                if collected:
                    address = ", ".join(collected)
                break
    if not address:
        for ln in lines:
            if re.search(r"\b(st|street|ave|avenue|rd|road|brgy|barangay|city|province|manila)\b", ln, re.I):
                address = ln
                break

    # ID number: prefer PhilSys number, then generic
    id_number = _find_labeled(lines, ID_LABELS)
    if not id_number:
        for ln in lines:
            m = PHILSYS_NUMBER_RE.search(ln)
            if m:
                id_number = m.group(0)
                break
    if not id_number:
        for ln in lines:
            m = PHILID_CARD_RE.search(ln)
            if m:
                id_number = m.group(0)
                break
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
        if img is None:
            return None, None
        # downscale for memory
        h, w = img.shape[:2]
        if max(h, w) > 640:
            scale = 640 / max(h, w)
            img = cv2.resize(img, (int(w * scale), int(h * scale)))
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


def scan_id(image_bytes, id_type, demo_mode=False):
    text, boxes = run_ocr(image_bytes)
    fields = parse_fields(text)
    fields["id_type"] = id_type
    # Always detect the face on the ID — required for face matching in the sequence.
    id_face_desc, id_face_crop = detect_face_on_id(image_bytes)
    fields["id_face_found"] = bool(id_face_desc)
    fields["demo_mode"] = bool(demo_mode)
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
    if demo_mode:
        fields["complete"] = (len(missing) == 0)
    else:
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

