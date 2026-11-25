"""PawTrack - identity verification public API (facade).

Implementation lives in services.ocr (Tesseract scanning + field parsing) and
services.id_face (face detection + matching). This module keeps the historical
import paths working for callers.
"""
from ..config import ID_TYPES
from .id_face import VERIFICATION_DIR, detect_face_on_id, match_faces
from .ocr import (parse_fields, run_ocr, scan_id)

__all__ = [
    "ID_TYPES", "VERIFICATION_DIR", "detect_face_on_id", "match_faces",
    "parse_fields", "run_ocr", "scan_id",
]
