"""Minimal PNG chunk reader/writer for structured glitching.

PNG stores zlib-compressed, per-scanline *filtered* pixel data, and every chunk
carries a CRC32. Naive byte edits break both. To glitch PNG and keep it valid we
decompress to the filtered stream, edit there, recompress, and recompute CRCs —
the ucnv "Art of PNG Glitch" approach.
"""
from __future__ import annotations

import struct
import zlib
from typing import List, Optional, Tuple

PNG_SIG = b"\x89PNG\r\n\x1a\n"
_CHANNELS = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}  # by IHDR color type


def parse_chunks(data: bytes) -> Optional[List[Tuple[bytes, bytes]]]:
    """Return ``[(type, data), ...]`` or None if not a PNG."""
    if data[:8] != PNG_SIG:
        return None
    chunks: List[Tuple[bytes, bytes]] = []
    i, n = 8, len(data)
    while i + 8 <= n:
        length = struct.unpack(">I", data[i:i + 4])[0]
        ctype = data[i + 4:i + 8]
        cdata = data[i + 8:i + 8 + length]
        chunks.append((ctype, cdata))
        i += 12 + length
        if ctype == b"IEND":
            break
    return chunks


def build_png(chunks: List[Tuple[bytes, bytes]]) -> bytes:
    out = bytearray(PNG_SIG)
    for ctype, cdata in chunks:
        out += struct.pack(">I", len(cdata))
        out += ctype
        out += cdata
        out += struct.pack(">I", zlib.crc32(ctype + cdata) & 0xFFFFFFFF)
    return bytes(out)


def ihdr_fields(chunks) -> Optional[dict]:
    for ctype, cdata in chunks:
        if ctype == b"IHDR" and len(cdata) >= 13:
            w, h, bit_depth, color_type = (
                struct.unpack(">I", cdata[0:4])[0],
                struct.unpack(">I", cdata[4:8])[0],
                cdata[8], cdata[9],
            )
            interlace = cdata[12]
            return {
                "width": w, "height": h, "bit_depth": bit_depth,
                "color_type": color_type, "interlace": interlace,
                "channels": _CHANNELS.get(color_type, 1),
            }
    return None


def idat_bytes(chunks) -> bytes:
    return b"".join(c for t, c in chunks if t == b"IDAT")


def replace_idat(chunks, new_idat: bytes) -> List[Tuple[bytes, bytes]]:
    """Drop all IDAT chunks, insert one new IDAT where the first one was."""
    out: List[Tuple[bytes, bytes]] = []
    inserted = False
    for ctype, cdata in chunks:
        if ctype == b"IDAT":
            if not inserted:
                out.append((b"IDAT", new_idat))
                inserted = True
        else:
            out.append((ctype, cdata))
    return out
