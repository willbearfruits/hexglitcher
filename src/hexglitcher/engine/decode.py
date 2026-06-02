"""Decode (possibly corrupted) image bytes to an RGBA uint8 array — safely.

Decode failure is *expected* in a databending tool, never exceptional. Every
function here returns ``None`` on failure rather than raising, so the pipeline
can fall back to a layer's last-good frame or its clean original.

Decode order: OpenCV's ``imdecode`` first (fast, libjpeg-turbo / libpng under the
hood, and notably tolerant of truncated/corrupt data — it returns partial images
where Pillow would abort), then Pillow as a fallback for formats/edge cases cv2
misses (e.g. some WebP/GIF paths).
"""
from __future__ import annotations

import io
import warnings
from typing import Optional

import numpy as np

try:
    import cv2  # type: ignore
    _HAVE_CV2 = True
except Exception:  # pragma: no cover - cv2 should be installed
    _HAVE_CV2 = False

from PIL import Image

Image.MAX_IMAGE_PIXELS = 80_000_000  # decompression-bomb guard


def _to_rgba(arr: np.ndarray) -> Optional[np.ndarray]:
    """Normalize any decoded array to contiguous HxWx4 uint8 RGBA."""
    if arr is None:
        return None
    if arr.dtype != np.uint8:
        # 16-bit PNGs etc. -> scale down to 8-bit
        arr = (arr.astype(np.float32) / max(1.0, arr.max()) * 255.0).astype(np.uint8)
    if arr.ndim == 2:  # grayscale
        arr = np.stack([arr, arr, arr, np.full_like(arr, 255)], axis=-1)
    elif arr.ndim == 3:
        c = arr.shape[2]
        if c == 1:
            g = arr[..., 0]
            arr = np.stack([g, g, g, np.full_like(g, 255)], axis=-1)
        elif c == 3:
            alpha = np.full(arr.shape[:2], 255, np.uint8)
            arr = np.dstack([arr, alpha])
        elif c == 4:
            pass
        else:
            arr = arr[..., :4]
    else:
        return None
    return np.ascontiguousarray(arr, dtype=np.uint8)


def _decode_cv2(data: bytes) -> Optional[np.ndarray]:
    if not _HAVE_CV2 or not data:
        return None
    try:
        buf = np.frombuffer(data, dtype=np.uint8)
        # IMREAD_UNCHANGED keeps alpha; cv2 yields BGR(A).
        img = cv2.imdecode(buf, cv2.IMREAD_UNCHANGED)
        if img is None:
            return None
        if img.ndim == 3 and img.shape[2] == 3:
            img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        elif img.ndim == 3 and img.shape[2] == 4:
            img = cv2.cvtColor(img, cv2.COLOR_BGRA2RGBA)
        return _to_rgba(img)
    except Exception:
        return None


def _decode_pillow(data: bytes) -> Optional[np.ndarray]:
    if not data:
        return None
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            with Image.open(io.BytesIO(data)) as im:
                im = im.convert("RGBA")
                # truncated images: load what we can
                try:
                    im.load()
                except Exception:
                    pass
                return _to_rgba(np.asarray(im))
    except Exception:
        return None


def decode_bytes(data: bytes) -> Optional[np.ndarray]:
    """Decode bytes to HxWx4 uint8 RGBA, or ``None`` if undecodable.

    cv2 is tried first (faster and more corruption-tolerant), Pillow second.
    """
    img = _decode_cv2(bytes(data))
    if img is not None:
        return img
    return _decode_pillow(bytes(data))


def decode_raw_rgb(data: bytes, width: int, channels: int = 3) -> Optional[np.ndarray]:
    """Interpret raw bytes as an uninterpreted pixel grid (the Briz 'wrong-decode').

    Lays `data` out as ``width`` columns of ``channels`` bytes-per-pixel, inferring
    the height from the length. This is the classic "open a JPEG's bytes as raw RGB"
    glitch — used by decoder-hack ops, not for normal image loading.
    """
    if width <= 0 or channels not in (1, 3, 4) or not data:
        return None
    stride = width * channels
    height = len(data) // stride
    if height <= 0:
        return None
    arr = np.frombuffer(bytes(data[: height * stride]), dtype=np.uint8)
    arr = arr.reshape(height, width, channels)
    return _to_rgba(arr)
