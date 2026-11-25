"""PawTrack - face detection and matching for identity verification.

Shared with the OCR module and the Settings identity wizard. Only numeric face
descriptors are stored; captured images are never persisted.
"""
import os

import numpy as np

from ..config import FACE_MATCH_THRESHOLD, UPLOAD_DIR
from .face import similarity


VERIFICATION_DIR = UPLOAD_DIR.parent / "verifications"
VERIFICATION_DIR.mkdir(parents=True, exist_ok=True)


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



def match_faces(id_descriptor, captured_descriptor):
    if not id_descriptor or not captured_descriptor:
        return False, -1.0
    from .face import similarity
    score = similarity(id_descriptor, captured_descriptor)
    return (score >= FACE_MATCH_THRESHOLD), float(score)

