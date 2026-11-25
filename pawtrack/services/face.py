"""
PawTrack - face recognition service
===================================
Server-side face detection and recognition using InsightFace (ONNX Runtime,
CPU). The browser only sends camera frames; the server turns each frame into a
512-number face descriptor and stores those numbers in the user record. No
face photo is ever stored.

How it is used:
* enrollment  -> enroll([frame1, frame2, frame3]) returns the descriptors
* login       -> identify(users, probe) returns the matching user, if any

The model is loaded once, lazily, on the first face request. The first call can
take 15-30 seconds while InsightFace prepares the ONNX model.
"""
import os
import threading

import numpy as np

from ..config import FACE_MATCH_THRESHOLD

MODEL_NAME = (os.getenv("FACE_MODEL", "buffalo_l") or "buffalo_l").strip()
MATCH_THRESHOLD = FACE_MATCH_THRESHOLD
MATCH_MARGIN = float(os.getenv("FACE_MATCH_MARGIN", "0.05"))
MIN_DET_SCORE = float(os.getenv("FACE_MIN_DET_SCORE", "0.50"))
CONSISTENCY_THRESHOLD = float(os.getenv("FACE_CONSISTENCY_THRESHOLD", "0.50"))
MAX_SAMPLES = 3
MAX_IMAGE_BYTES = 100 * 1024 * 1024


class FaceError(Exception):
    """A problem the user can fix (no face, two faces, bad image, ...)."""


_engine = None
_engine_error = None
_engine_lock = threading.Lock()


def _load_engine():
    """Load the InsightFace model once. Raises FaceError with a readable message."""
    global _engine, _engine_error
    if _engine is not None:
        return _engine
    with _engine_lock:
        if _engine is not None:
            return _engine
        try:
            from insightface.app import FaceAnalysis
        except Exception as exc:                       # package missing
            _engine_error = str(exc)
            raise FaceError(
                "Face recognition is not installed on the server. "
                "Run: pip install -r requirements.txt") from exc
        import warnings
        warnings.filterwarnings("ignore")
        try:
            engine = FaceAnalysis(name=MODEL_NAME, providers=["CPUExecutionProvider"])
            engine.prepare(ctx_id=-1, det_size=(320, 320))
            _engine = engine
            return _engine
        except Exception as exc:                       # model download / runtime problem
            _engine_error = str(exc)
            raise FaceError(
                "The face model could not start. Check the server log and try again.") from exc


def engine_status():
    """'ready', 'error' or 'idle' - used by the settings page."""
    if _engine is not None:
        return "ready"
    if _engine_error:
        return "error"
    return "idle"


def _decode(image_bytes):
    import cv2

    if not image_bytes:
        raise FaceError("The camera did not send an image. Please try again.")
    if len(image_bytes) > MAX_IMAGE_BYTES:
        raise FaceError("That photo is too large. Please try again.")
    buffer = np.frombuffer(image_bytes, dtype=np.uint8)
    image = cv2.imdecode(buffer, cv2.IMREAD_COLOR)
    if image is None:
        raise FaceError("That image could not be read. Please try again.")
    return image


def _descriptor(face):
    values = getattr(face, "normed_embedding", None)
    if values is None:
        values = np.asarray(face.embedding, dtype=float)
        norm = float(np.linalg.norm(values))
        if norm:
            values = values / norm
    return [round(float(v), 6) for v in values]


def embedding(image_bytes):
    """Return one face descriptor from an image, or raise FaceError."""
    engine = _load_engine()
    faces = engine.get(_decode(image_bytes))
    faces = [f for f in faces if float(f.det_score) >= MIN_DET_SCORE]
    if not faces:
        raise FaceError("No face detected. Look straight at the camera in good light.")
    if len(faces) > 1:
        raise FaceError("More than one face is visible. Please make sure only you are in the picture.")
    return _descriptor(faces[0])


def similarity(a, b):
    """Cosine similarity of two descriptors (-1 when they cannot be compared)."""
    try:
        left = np.asarray(a, dtype=float)
        right = np.asarray(b, dtype=float)
        if left.shape != right.shape:
            return -1.0
        return float(np.dot(left, right))
    except Exception:
        return -1.0


def clean_descriptors(user):
    """Return only the valid descriptors stored on a user record."""
    raw = user.get("face_descriptors") or []
    if not isinstance(raw, list):
        return []
    return [item for item in raw
            if isinstance(item, list) and len(item) >= 64]


def has_face(user):
    return bool(clean_descriptors(user))


def enroll(samples):
    """Validate camera samples and return the descriptors to save.

    Each sample must contain exactly one clear face, and the samples must be
    consistent with each other so one person cannot accidentally register a
    mixture of different faces.
    """
    if not samples:
        raise FaceError("No camera images were received. Please try again.")
    samples = samples[:MAX_SAMPLES]
    descriptors = [embedding(sample) for sample in samples]
    for i in range(len(descriptors)):
        for j in range(i + 1, len(descriptors)):
            if similarity(descriptors[i], descriptors[j]) < CONSISTENCY_THRESHOLD:
                raise FaceError(
                    "The captures did not match. Keep your face still, use good light, "
                    "and try again.")
    return descriptors


def identify(users, probe):
    """Return (user, score) for the best confident match, otherwise (None, score).

    A match must pass the similarity threshold and be clearly better than the
    second-best account, which prevents a face from being assigned to the wrong
    user when two people look similar.
    """
    best_user = None
    best_score = -1.0
    second_score = -1.0
    for user in users:
        scores = [similarity(probe, descriptor)
                  for descriptor in clean_descriptors(user)]
        if not scores:
            continue
        score = max(scores)
        if score > best_score:
            second_score = best_score
            best_score = score
            best_user = user
        elif score > second_score:
            second_score = score
    if best_user is None or best_score < MATCH_THRESHOLD:
        return None, best_score
    if second_score >= 0 and (best_score - second_score) < MATCH_MARGIN:
        return None, best_score
    return best_user, best_score
