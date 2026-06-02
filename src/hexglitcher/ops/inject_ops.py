"""Inject / mix external data into a byte region — the multitrack databend.

Pull bytes from any external file (a piece of music, an audio clip, another
image, anything) and weave them into the region. Re-decoded, foreign data
produces structured tears, color blocks and rhythmic noise unlike anything the
source image's own bytes can make. This is the "paste music between the header
and footer" Audacity technique, native.
"""
from __future__ import annotations

import numpy as np

from ..engine.operation import OpDomain, register_op
from .params import p_choice, p_filepath, p_float, p_int

CAT = "Inject / Mix"


@register_op(
    "byte.inject", "Inject / Mix Data", OpDomain.BYTE, CAT,
    params=(
        p_filepath("source", "Source file", "",
                   "Any file — audio, music, another image. Its bytes get woven in."),
        p_choice("mode", "Mode", "overwrite",
                 ("overwrite", "insert", "xor", "average", "interleave")),
        p_int("src_offset", "Read from (byte)", 0, 0, 1_000_000_000, 1),
        p_int("length", "Length (0 = fill region)", 0, 0, 1_000_000_000, 1),
        p_float("position", "Position in region", 0.0, 0.0, 1.0, 0.01),
        p_int("stride", "Interleave stride", 2, 1, 256, 1),
    ),
    help="Weave bytes from another file into the region (overwrite/insert/xor/"
         "average/interleave). Pick a source file to enable it.",
)
def _inject(region, params, ctx):
    path = (params.get("source") or "").strip()
    if not path:
        return None
    ext = ctx.load_external(path)
    if not ext:
        return None

    src_off = min(int(params["src_offset"]), max(0, len(ext) - 1))
    chunk = ext[src_off:]
    length = int(params["length"])
    if length > 0:
        chunk = chunk[:length]
    if not chunk:
        return None

    region = bytearray(region)
    rn = len(region)
    pos = max(0, min(int(params["position"] * rn), rn))
    mode = params["mode"]

    if mode == "insert":
        return bytes(region[:pos]) + bytes(chunk) + bytes(region[pos:])

    m = min(len(chunk), rn - pos)
    if m <= 0:
        return None
    a = np.frombuffer(bytes(region[pos:pos + m]), dtype=np.uint8)
    b = np.frombuffer(bytes(chunk[:m]), dtype=np.uint8)

    if mode == "overwrite":
        region[pos:pos + m] = b.tobytes()
    elif mode == "xor":
        region[pos:pos + m] = (a ^ b).tobytes()
    elif mode == "average":
        region[pos:pos + m] = ((a.astype(np.uint16) + b) // 2).astype(np.uint8).tobytes()
    elif mode == "interleave":
        stride = max(1, int(params["stride"]))
        positions = np.arange(pos, rn, stride)[:len(b)]
        arr = np.frombuffer(bytes(region), dtype=np.uint8).copy()
        arr[positions] = b[:len(positions)]
        return arr.tobytes()
    return bytes(region)
