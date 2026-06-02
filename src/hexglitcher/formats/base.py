"""Format backends: detect a file's type and its corruptible "safe zone".

The safe zone is the byte range ``[header_end, footer_start)`` that byte-domain
ops may touch without destroying the file's structural framing. Corrupting the
header (magic, dimensions, palette/quant tables) usually means the file won't
open at all; corrupting the footer can drop the end-of-image marker.

These backends do *generic* framing. Format-specific glitch techniques that need
to decode/re-encode (PNG per-scanline filter rewriting, JPEG quant-table edits)
live in their own ops and use the richer helpers added alongside this module.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class FormatBackend:
    name: str
    default_header: int = 0
    default_footer: int = 0          # bytes reserved at EOF

    @classmethod
    def detect(cls, data: bytes) -> bool:  # pragma: no cover - overridden
        return False

    def safe_zone(self, data: bytes) -> tuple[int, int]:
        """(header_end, footer_start) — the editable body of `data`."""
        n = len(data)
        header = min(self.default_header, n)
        footer = max(header, n - self.default_footer)
        return header, footer


class RawFormat(FormatBackend):
    def __init__(self) -> None:
        super().__init__(name="raw", default_header=0, default_footer=0)

    @classmethod
    def detect(cls, data: bytes) -> bool:
        return True  # fallback — matches anything


class BmpFormat(FormatBackend):
    def __init__(self) -> None:
        super().__init__(name="bmp", default_header=54, default_footer=0)

    @classmethod
    def detect(cls, data: bytes) -> bool:
        return data[:2] == b"BM"


class GifFormat(FormatBackend):
    def __init__(self) -> None:
        super().__init__(name="gif", default_header=13, default_footer=1)

    @classmethod
    def detect(cls, data: bytes) -> bool:
        return data[:6] in (b"GIF87a", b"GIF89a")

    def safe_zone(self, data: bytes) -> tuple[int, int]:
        # Skip logical screen descriptor (13) + global color table if present.
        n = len(data)
        header = min(13, n)
        if n > 10:
            packed = data[10]
            if packed & 0x80:  # global color table flag
                gct_size = 3 * (2 ** ((packed & 0x07) + 1))
                header = min(13 + gct_size, n)
        return header, max(header, n - 1)  # trailing 0x3B


class JpegFormat(FormatBackend):
    """Protect everything up to and including the Start-Of-Scan header.

    Corruption after SOS desynchronizes the Huffman stream and the DC-prediction
    chain — exactly the blocky color-shear glitch — while the file still decodes.
    """
    def __init__(self) -> None:
        super().__init__(name="jpeg", default_header=600, default_footer=2)

    @classmethod
    def detect(cls, data: bytes) -> bool:
        return data[:2] == b"\xff\xd8"

    def safe_zone(self, data: bytes) -> tuple[int, int]:
        n = len(data)
        sos = data.find(b"\xff\xda")
        if sos == -1:
            return min(self.default_header, n), max(0, n - 2)
        # SOS segment: FFDA, 2-byte length, then header bytes; scan starts after.
        if sos + 4 <= n:
            seg_len = (data[sos + 2] << 8) | data[sos + 3]
            header_end = min(sos + 2 + seg_len, n)
        else:
            header_end = min(sos + 2, n)
        footer = n - 2 if data[-2:] == b"\xff\xd9" else n
        return header_end, max(header_end, footer)


class PngFormat(FormatBackend):
    """Generic framing only: protect signature + IHDR, reserve the IEND chunk.

    Naive byte corruption mostly *breaks* PNG (CRC + zlib), so the real PNG glitch
    is the per-scanline filter-rewrite op, not raw body corruption. This framing
    keeps generic byte ops from trashing the structural chunks.
    """
    def __init__(self) -> None:
        super().__init__(name="png", default_header=33, default_footer=12)

    @classmethod
    def detect(cls, data: bytes) -> bool:
        return data[:8] == b"\x89PNG\r\n\x1a\n"

    def safe_zone(self, data: bytes) -> tuple[int, int]:
        n = len(data)
        # IHDR is the first chunk: 8 sig + 4 len + 4 'IHDR' + 13 data + 4 crc = 33
        header = min(33, n)
        first_idat = data.find(b"IDAT")
        if first_idat != -1:
            header = min(max(header, first_idat - 4), n)
        iend = data.rfind(b"IEND")
        footer = (iend - 4) if iend != -1 else n
        return header, max(header, footer)
