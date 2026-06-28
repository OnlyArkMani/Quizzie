"""
Evidence snapshots for high-severity proctoring events.

When a serious violation fires (multiple faces, no face), we keep a small
downscaled JPEG thumbnail (base64) so an examiner can later see what the camera
actually showed, instead of just a flag name. Kept tiny and only for high
severity to bound storage, since it lives inside the cheat_log JSON metadata.
"""
from __future__ import annotations

import base64
from typing import Optional

import cv2
import numpy as np

_MAX_DIM = 200
_JPEG_QUALITY = 55


def thumbnail_b64(image_bytes: bytes, max_dim: int = _MAX_DIM) -> Optional[str]:
    """Return a small base64 JPEG data URI for an encoded image, or None."""
    try:
        arr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if img is None:
            return None
        h, w = img.shape[:2]
        scale = max_dim / float(max(h, w))
        if scale < 1.0:
            img = cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
        ok, buf = cv2.imencode(".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), _JPEG_QUALITY])
        if not ok:
            return None
        return "data:image/jpeg;base64," + base64.b64encode(buf.tobytes()).decode()
    except Exception:
        return None


def attach_snapshots(image_bytes: bytes, flags: list) -> list:
    """
    For each high-severity flag, attach an evidence thumbnail under
    metadata['snapshot']. Best-effort; flags are returned unchanged on failure.
    """
    if not flags:
        return flags
    if not any(isinstance(f, dict) and f.get("severity") == "high" for f in flags):
        return flags
    thumb = thumbnail_b64(image_bytes)
    if not thumb:
        return flags
    for f in flags:
        if isinstance(f, dict) and f.get("severity") == "high":
            meta = dict(f.get("metadata") or {})
            meta["snapshot"] = thumb
            f["metadata"] = meta
    return flags
