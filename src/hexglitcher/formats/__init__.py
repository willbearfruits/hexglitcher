"""Format detection: sniff bytes (and fall back to extension) -> FormatBackend."""
from __future__ import annotations

from .base import (
    BmpFormat,
    FormatBackend,
    GifFormat,
    JpegFormat,
    PngFormat,
    RawFormat,
)

# Order matters: most specific magic first, RawFormat last (matches anything).
_BACKENDS = [JpegFormat, PngFormat, BmpFormat, GifFormat]

_BY_EXT = {
    ".jpg": JpegFormat, ".jpeg": JpegFormat, ".jpe": JpegFormat,
    ".png": PngFormat,
    ".bmp": BmpFormat, ".dib": BmpFormat,
    ".gif": GifFormat,
}


def detect_format(data: bytes, ext: str = "") -> FormatBackend:
    for backend in _BACKENDS:
        try:
            if backend.detect(data):
                return backend()
        except Exception:
            continue
    cls = _BY_EXT.get(ext.lower())
    if cls is not None:
        return cls()
    return RawFormat()


__all__ = [
    "FormatBackend", "RawFormat", "BmpFormat", "GifFormat",
    "JpegFormat", "PngFormat", "detect_format",
]
