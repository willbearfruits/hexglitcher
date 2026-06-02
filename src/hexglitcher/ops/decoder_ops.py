"""Decoder-hack ops (the Nick Briz tier).

Instead of corrupting data, these mis-*interpret* the decoded raster — the spirit
of hacking the codec itself. Reading pixels at the wrong row width gives the
classic diagonal "raw misread" shear; reading interleaved RGB as separate planes
tears the channels into bands. Pixel-domain, so they work on every format.
"""
from __future__ import annotations

import numpy as np

from ..engine.decode import decode_raw_rgb
from ..engine.operation import OpDomain, register_op
from .params import p_choice, p_int

CAT = "Decoder Hacks"


@register_op(
    "decoder.wrong_width", "Wrong-Width Decode", OpDomain.PIXEL, CAT,
    params=(
        p_int("width_delta", "Width offset (px)", 3, -512, 512, 1),
        p_int("offset", "Byte offset", 0, 0, 1_000_000, 1),
        p_choice("channels", "Read as", "3 (RGB)", ("1 (gray)", "3 (RGB)", "4 (RGBA)")),
    ),
    help="Re-lay the decoded pixels at the wrong row width — the diagonal 'raw "
         "misread' shear. Small offsets skew; large ones scramble.",
)
def _wrong_width(img, params, ctx):
    ch = {"1 (gray)": 1, "3 (RGB)": 3, "4 (RGBA)": 4}[params["channels"]]
    src = img if ch == 4 else (img[..., :3] if ch == 3 else img[..., :1])
    buf = np.ascontiguousarray(src).tobytes()
    w = max(1, img.shape[1] + int(params["width_delta"]))
    off = int(params["offset"]) % max(1, len(buf))
    out = decode_raw_rgb(buf[off:], w, ch)
    return out if out is not None else img


@register_op(
    "decoder.planar", "Planar Misread", OpDomain.PIXEL, CAT,
    params=(p_int("shift", "Plane shift", 0, -1_000_000, 1_000_000, 1),),
    help="Read interleaved RGB as three stacked planes — channels separate into "
         "vertical bands (the classic plane-misalignment glitch).",
)
def _planar(img, params, ctx):
    h, w = img.shape[:2]
    third = h * w
    buf = np.frombuffer(np.ascontiguousarray(img[..., :3]).tobytes(), dtype=np.uint8)
    if buf.size:
        buf = np.roll(buf, int(params["shift"]) % buf.size)
    if buf.size < third * 3:
        buf = np.pad(buf, (0, third * 3 - buf.size))
    r = buf[0:third].reshape(h, w)
    g = buf[third:2 * third].reshape(h, w)
    b = buf[2 * third:3 * third].reshape(h, w)
    a = np.full((h, w), 255, np.uint8)
    return np.dstack([r, g, b, a]).astype(np.uint8)
