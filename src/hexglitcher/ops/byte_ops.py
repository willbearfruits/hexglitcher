"""Byte-domain operations — they mangle raw file bytes before decode.

Each op receives the bytes of its target region (the format safe zone by default)
and returns the new region bytes. Length may change. These are the classic
databending moves: corrupt, sort, shift, repeat, find/replace, transpose.
"""
from __future__ import annotations

import numpy as np

from ..engine.operation import OpDomain, register_op
from .params import p_choice, p_int, p_seed, p_text

CAT = "Corruption"


@register_op(
    "byte.noise", "Random Corruption", OpDomain.BYTE, CAT,
    params=(
        p_int("amount", "Amount (‰)", 30, 0, 1000, 1,
              "Bytes changed per 1000 (30 = 3% of the region)"),
        p_choice("mode", "Operation", "random",
                 ("random", "zero", "max", "xor", "increment", "decrement")),
        p_int("mask", "XOR/bit mask", 255, 0, 255, 1),
        p_seed(),
    ),
    help="Corrupt a fraction of bytes in the region. The bread-and-butter glitch.",
    randomizable=True,
)
def _noise(region, params, ctx):
    n = len(region)
    if n == 0:
        return None
    k = max(1, int(round(n * params["amount"] / 1000.0)))
    k = min(k, n)
    idx = ctx.rng.integers(0, n, size=k)
    arr = np.frombuffer(bytes(region), dtype=np.uint8).copy()
    mode = params["mode"]
    if mode == "random":
        arr[idx] = ctx.rng.integers(0, 256, size=k, dtype=np.uint8)
    elif mode == "zero":
        arr[idx] = 0
    elif mode == "max":
        arr[idx] = 255
    elif mode == "xor":
        arr[idx] ^= int(params["mask"]) & 0xFF
    elif mode == "increment":
        arr[idx] = (arr[idx].astype(np.int16) + 1) % 256
    elif mode == "decrement":
        arr[idx] = (arr[idx].astype(np.int16) - 1) % 256
    return arr.tobytes()


@register_op(
    "byte.sort", "Byte Sort", OpDomain.BYTE, CAT,
    params=(
        p_int("chunk", "Chunk size (0 = whole region)", 4096, 0, 1_000_000, 1),
        p_choice("order", "Order", "ascending", ("ascending", "descending")),
    ),
    help="Sort bytes within chunks. Produces smooth banding / gradient tears.",
)
def _sort(region, params, ctx):
    arr = np.frombuffer(bytes(region), dtype=np.uint8).copy()
    n = arr.size
    if n == 0:
        return None
    chunk = int(params["chunk"]) or n
    desc = params["order"] == "descending"
    for a in range(0, n, chunk):
        seg = arr[a:a + chunk]
        seg.sort()
        if desc:
            seg[:] = seg[::-1]
    return arr.tobytes()


@register_op(
    "byte.shift", "Byte Shift / Rotate", OpDomain.BYTE, CAT,
    params=(p_int("offset", "Shift (bytes)", 1, -1_000_000, 1_000_000, 1),),
    help="Circularly rotate the region's bytes. Small shifts smear color/structure.",
)
def _shift(region, params, ctx):
    arr = np.frombuffer(bytes(region), dtype=np.uint8)
    if arr.size == 0:
        return None
    return np.roll(arr, int(params["offset"])).tobytes()


@register_op(
    "byte.transpose", "Chunk Shuffle", OpDomain.BYTE, CAT,
    params=(
        p_int("chunks", "Number of chunks", 8, 2, 4096, 1),
        p_seed(),
    ),
    help="Cut the region into N chunks and reorder them. Block-displacement glitch.",
    randomizable=True,
)
def _transpose(region, params, ctx):
    n = len(region)
    if n < 2:
        return None
    chunks = min(int(params["chunks"]), n)
    bounds = np.linspace(0, n, chunks + 1).astype(int)
    pieces = [bytes(region[bounds[i]:bounds[i + 1]]) for i in range(chunks)]
    order = ctx.rng.permutation(chunks)
    return b"".join(pieces[i] for i in order)


@register_op(
    "byte.repeat", "Repeat Run", OpDomain.BYTE, CAT,
    params=(
        p_int("run", "Run length", 256, 1, 65536, 1),
        p_int("times", "Repeat count", 4, 1, 256, 1),
        p_seed(),
    ),
    help="Pick a byte run and stamp copies of it across the region — stutter/echo.",
    randomizable=True,
)
def _repeat(region, params, ctx):
    n = len(region)
    run = min(int(params["run"]), n)
    if run <= 0:
        return None
    arr = bytearray(region)
    start = int(ctx.rng.integers(0, max(1, n - run)))
    chunk = bytes(arr[start:start + run])
    pos = start + run
    for _ in range(int(params["times"])):
        end = min(pos + run, n)
        arr[pos:end] = chunk[: end - pos]
        pos = end
        if pos >= n:
            break
    return bytes(arr)


@register_op(
    "byte.find_replace", "Find / Replace (Hex)", OpDomain.BYTE, CAT,
    params=(
        p_text("find", "Find (hex)", "FF", "Byte pattern to find, e.g. FF00"),
        p_text("replace", "Replace (hex)", "00", "Replacement bytes, e.g. 0000"),
        p_int("max", "Max replacements (0 = all)", 0, 0, 1_000_000, 1),
    ),
    help="Replace a hex byte pattern with another — the structured 'wordpad "
         "effect'. More deliberate than random corruption.",
)
def _find_replace(region, params, ctx):
    find = (params.get("find") or "").replace(" ", "")
    repl = (params.get("replace") or "").replace(" ", "")
    try:
        fb = bytes.fromhex(find)
        rb = bytes.fromhex(repl)
    except ValueError:
        return None
    if not fb:
        return None
    data = bytes(region)
    mx = int(params["max"])
    return data.replace(fb, rb) if mx <= 0 else data.replace(fb, rb, mx)
