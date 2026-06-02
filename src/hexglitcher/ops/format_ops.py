"""Format-specific structural glitches (the differentiator tier).

These BYTE ops parse a whole file's structure and edit it in ways that keep it
*decodable* — so the glitch reads as intentional, not just broken:

* PNG filter rewrite — lie about each scanline's filter byte (ucnv). The decoder
  un-filters with the wrong predictor; Sub smears sideways, Up bleeds down, Paeth
  sprays wide damage. zlib + CRC are recomputed so the file stays valid.
* JPEG quant scale — multiply the quantization tables; controllable blockiness.
* JPEG recompress — re-encode at low quality N times; stacked DCT artifacts (the
  snorpey building block — pair with Random Corruption after it for full effect).
"""
from __future__ import annotations

import zlib

import numpy as np

try:
    import cv2  # type: ignore
except Exception:  # pragma: no cover
    cv2 = None

from ..engine.operation import OpDomain, register_op
from ..formats import png as pngmod
from .params import p_choice, p_float, p_int, p_seed

CAT = "Format (Structural)"


@register_op(
    "png.filter_rewrite", "PNG Filter Rewrite", OpDomain.BYTE, CAT,
    params=(
        p_choice("mode", "Mode", "random", ("random", "force", "increment", "shift")),
        p_int("filter", "Filter (force mode)", 4, 0, 4, 1),
        p_int("shift", "Shift / amount", 1, 0, 4, 1),
        p_seed(),
    ),
    help="Rewrite each scanline's PNG filter type so it un-filters wrong — "
         "structured directional glitch that still opens. (Non-interlaced PNG.)",
    whole_file=True,
    randomizable=True,
)
def _png_filter_rewrite(region, params, ctx):
    chunks = pngmod.parse_chunks(bytes(region))
    if chunks is None:
        return None
    info = pngmod.ihdr_fields(chunks)
    if info is None or info["interlace"] != 0:
        return None
    stride = (info["width"] * info["channels"] * info["bit_depth"] + 7) // 8
    row = 1 + stride
    h = info["height"]
    try:
        raw = bytearray(zlib.decompress(pngmod.idat_bytes(chunks)))
    except Exception:
        return None
    if row <= 1 or len(raw) < h * row:
        return None

    mode = params["mode"]
    rng = ctx.rng
    for r in range(h):
        idx = r * row
        f = raw[idx]
        if mode == "force":
            nf = int(params["filter"])
        elif mode == "random":
            nf = int(rng.integers(0, 5))
        elif mode == "increment":
            nf = (f + 1) % 5
        else:  # shift
            nf = (f + int(params["shift"])) % 5
        raw[idx] = nf

    new_idat = zlib.compress(bytes(raw), 6)
    return pngmod.build_png(pngmod.replace_idat(chunks, new_idat))


def _iter_jpeg_segments(data: bytes):
    """Yield (marker, seg_start, seg_len) for each marker segment up to SOS."""
    i, n = 2, len(data)
    while i + 4 <= n:
        if data[i] != 0xFF:
            i += 1
            continue
        marker = data[i + 1]
        if marker == 0xDA or marker == 0xD9:  # SOS / EOI -> stop
            return
        if marker == 0xD8 or 0xD0 <= marker <= 0xD7 or marker == 0x01:
            i += 2
            continue
        seg_len = (data[i + 2] << 8) | data[i + 3]
        yield marker, i + 4, seg_len
        i += 2 + seg_len


@register_op(
    "jpeg.quant_scale", "JPEG Quantize", OpDomain.BYTE, CAT,
    params=(p_float("factor", "Quant factor", 3.0, 0.1, 16.0, 0.1),),
    help="Scale the JPEG quantization tables — coarser quant = bigger blocky, "
         "color-shifted DCT artifacts. File stays valid.",
    whole_file=True,
)
def _jpeg_quant_scale(region, params, ctx):
    if region[:2] != b"\xff\xd8":
        return None
    out = bytearray(region)
    factor = float(params["factor"])
    for marker, start, seg_len in _iter_jpeg_segments(bytes(out)):
        if marker != 0xDB:  # DQT
            continue
        p, end = start, start + seg_len - 2
        while p < end:
            prec = out[p] >> 4
            p += 1
            if prec == 0:
                for k in range(64):
                    if p + k < len(out):
                        out[p + k] = max(1, min(255, int(round(out[p + k] * factor))))
                p += 64
            else:
                for k in range(64):
                    idx = p + k * 2
                    if idx + 1 < len(out):
                        v = (out[idx] << 8) | out[idx + 1]
                        v = max(1, min(65535, int(round(v * factor))))
                        out[idx], out[idx + 1] = v >> 8, v & 0xFF
                p += 128
    return bytes(out)


@register_op(
    "jpeg.recompress", "JPEG Recompress", OpDomain.BYTE, CAT,
    params=(
        p_int("quality", "Quality", 12, 1, 95, 1),
        p_int("iterations", "Iterations", 6, 1, 40, 1),
    ),
    help="Re-encode as JPEG at low quality, repeatedly — stacked generation-loss "
         "artifacts. Add Random Corruption after it for the classic jpg-glitch look.",
    whole_file=True,
)
def _jpeg_recompress(region, params, ctx):
    if cv2 is None:
        return None
    img = cv2.imdecode(np.frombuffer(bytes(region), np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        return None
    q = int(params["quality"])
    enc = None
    for _ in range(int(params["iterations"])):
        ok, enc = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, q])
        if not ok:
            return None
        img = cv2.imdecode(enc, cv2.IMREAD_COLOR)
    return enc.tobytes() if enc is not None else None
