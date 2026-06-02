"""Pixel-domain operations — they transform the decoded RGBA image (numpy).

These run after the decode boundary, so they always have a valid image to work
on (the pipeline falls back to the clean decode if corrupted bytes won't decode).
"""
from __future__ import annotations

import numpy as np

from ..engine.operation import OpDomain, register_op
from .params import p_bool, p_choice, p_float, p_int

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
    work = np.swapaxes(img, 0, 1) if vertical else img
    key = _sort_key(work, params["by"])
    bright = _luma(work)
    lo, hi = params["low"] * 255.0, params["high"] * 255.0
    mask = (bright >= lo) & (bright <= hi)
    out = work.copy()
    reverse = bool(params["reverse"])
    h = work.shape[0]
    for y in range(h):
        for a, b in _spans(mask[y]):
            if b - a < 2:
                continue
            order = np.argsort(key[y, a:b], kind="stable")
            if reverse:
                order = order[::-1]
            out[y, a:b] = work[y, a:b][order]
    return np.swapaxes(out, 0, 1) if vertical else out
