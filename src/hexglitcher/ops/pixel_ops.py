"""Pixel-domain operations — they transform the decoded RGBA image (numpy).

These run after the decode boundary, so they always have a valid image to work
on (the pipeline falls back to the clean decode if corrupted bytes won't decode).
"""
from __future__ import annotations

import numpy as np

from ..engine import accel
from ..engine.operation import OpDomain, register_op
from .params import p_bool, p_choice, p_float, p_int, p_seed

CAT_CH = "Channels"
CAT_SORT = "Sorting"


def _luma(img: np.ndarray) -> np.ndarray:
    r, g, b = img[..., 0].astype(np.float32), img[..., 1].astype(np.float32), img[..., 2].astype(np.float32)
    return 0.299 * r + 0.587 * g + 0.114 * b


def _sort_key(img: np.ndarray, by: str) -> np.ndarray:
    if by == "red":
        return img[..., 0].astype(np.float32)
    if by == "green":
        return img[..., 1].astype(np.float32)
    if by == "blue":
        return img[..., 2].astype(np.float32)
    if by in ("hue", "saturation"):
        mx = img[..., :3].max(axis=-1).astype(np.float32)
        mn = img[..., :3].min(axis=-1).astype(np.float32)
        if by == "saturation":
            return np.where(mx > 0, (mx - mn) / np.maximum(mx, 1e-6), 0.0) * 255.0
        return (mx - mn)  # cheap hue-ish proxy (chroma); good enough for sorting
    return _luma(img)


@register_op(
    "pixel.channel_shift", "Channel Shift", OpDomain.PIXEL, CAT_CH,
    params=(
        p_choice("axis", "Direction", "horizontal", ("horizontal", "vertical")),
        p_int("shift_r", "Red shift", 8, -512, 512, 1),
        p_int("shift_g", "Green shift", 0, -512, 512, 1),
        p_int("shift_b", "Blue shift", -8, -512, 512, 1),
    ),
    help="Offset the R/G/B channels independently — chromatic aberration / RGB split.",
)
def _channel_shift(img, params, ctx):
    out = img.copy()
    axis = 1 if params["axis"] == "horizontal" else 0
    for ci, key in enumerate(("shift_r", "shift_g", "shift_b")):
        s = int(params[key])
        if s:
            out[..., ci] = np.roll(img[..., ci], s, axis=axis)
    return out


@register_op(
    "pixel.channel_swap", "Channel Swap", OpDomain.PIXEL, CAT_CH,
    params=(p_choice("order", "Channel order", "BGR",
                     ("RGB", "RBG", "GRB", "GBR", "BRG", "BGR")),),
    help="Reorder the colour channels.",
)
def _channel_swap(img, params, ctx):
    idx = {"R": 0, "G": 1, "B": 2}
    order = [idx[c] for c in params["order"]]
    out = img.copy()
    out[..., 0], out[..., 1], out[..., 2] = img[..., order[0]], img[..., order[1]], img[..., order[2]]
    return out


def _spans(mask_row: np.ndarray):
    """Yield (start, end) of contiguous True runs in a 1-D boolean array."""
    if not mask_row.any():
        return
    idx = np.flatnonzero(np.diff(np.concatenate(([0], mask_row.view(np.int8), [0]))))
    for i in range(0, len(idx), 2):
        yield int(idx[i]), int(idx[i + 1])


@register_op(
    "pixel.sort", "Pixel Sort", OpDomain.PIXEL, CAT_SORT,
    params=(
        p_choice("direction", "Direction", "horizontal", ("horizontal", "vertical")),
        p_choice("by", "Sort by", "brightness",
                 ("brightness", "hue", "saturation", "red", "green", "blue")),
        p_float("low", "Threshold low", 0.25, 0.0, 1.0, 0.01,
                "Only sort pixels brighter than this"),
        p_float("high", "Threshold high", 0.80, 0.0, 1.0, 0.01,
                "Only sort pixels darker than this"),
        p_bool("reverse", "Reverse", False),
    ),
    help="Asendorf-style threshold pixel sort — sorts bright/contiguous spans, "
         "leaving the rest intact for that signature streaked look.",
)
def _pixel_sort(img, params, ctx):
    vertical = params["direction"] == "vertical"
    work = np.ascontiguousarray(np.swapaxes(img, 0, 1) if vertical else img)
    key = np.ascontiguousarray(_sort_key(work, params["by"]).astype(np.float32))
    bright = _luma(work)
    lo, hi = params["low"] * 255.0, params["high"] * 255.0
    mask = np.ascontiguousarray((bright >= lo) & (bright <= hi))
    reverse = bool(params["reverse"])
    out = work.copy()
    if accel.HAVE_NUMBA:
        accel.sort_spans(out, key, mask, reverse)          # JIT kernel, in-place
    else:
        for y in range(work.shape[0]):
            for a, b in _spans(mask[y]):
                if b - a < 2:
                    continue
                order = np.argsort(key[y, a:b], kind="stable")
                if reverse:
                    order = order[::-1]
                out[y, a:b] = work[y, a:b][order]
    return np.swapaxes(out, 0, 1) if vertical else out


@register_op(
    "pixel.row_shift", "Row / Column Shift", OpDomain.PIXEL, "Geometry",
    params=(
        p_choice("axis", "Axis", "rows", ("rows", "columns")),
        p_choice("mode", "Mode", "sine", ("sine", "random")),
        p_int("max_shift", "Max shift (px)", 30, 0, 4000, 1),
        p_float("rate", "Cycles (sine)", 6.0, 0.1, 400.0, 0.1),
        p_seed(),
    ),
    help="Displace each row (or column) sideways — wavy scanline / slice glitch.",
    randomizable=True,
)
def _row_shift(img, params, ctx):
    cols = params["axis"] == "columns"
    work = np.swapaxes(img, 0, 1) if cols else img
    h, w = work.shape[:2]
    m = int(params["max_shift"])
    if m <= 0:
        return img
    if params["mode"] == "sine":
        shifts = (m * np.sin(2 * np.pi * float(params["rate"]) * np.arange(h) / max(1, h))).astype(np.int64)
    else:
        shifts = ctx.rng.integers(-m, m + 1, size=h)
    # vectorized per-row roll: gather columns shifted per row (no Python loop)
    idx = (np.arange(w)[None, :] - shifts[:, None]) % w
    out = work[np.arange(h)[:, None], idx]
    return np.swapaxes(out, 0, 1) if cols else out


@register_op(
    "pixel.noise", "Noise Overlay", OpDomain.PIXEL, "Texture",
    params=(
        p_int("amount", "Amount", 40, 0, 255, 1),
        p_bool("mono", "Monochrome", True),
        p_seed(),
    ),
    help="Add random noise over the pixels.",
    randomizable=True,
)
def _pixel_noise(img, params, ctx):
    a = int(params["amount"])
    if a <= 0:
        return img
    h, w = img.shape[:2]
    if params["mono"]:
        n = np.repeat(ctx.rng.integers(-a, a + 1, size=(h, w, 1)), 3, axis=2)
    else:
        n = ctx.rng.integers(-a, a + 1, size=(h, w, 3))
    out = img.astype(np.int16)
    out[..., :3] = np.clip(out[..., :3] + n, 0, 255)
    return out.astype(np.uint8)
