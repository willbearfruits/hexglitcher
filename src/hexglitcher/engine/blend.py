"""Blend modes and bottom-up alpha compositing of RGBA layers (numpy).

Layers composite like Photoshop/Krita: the bottom layer is the base, each layer
above is blended onto the running result using its blend mode, then alpha-composited
with ``alpha = layer.alpha * opacity * mask``.

All math is done in float [0,1]; inputs/outputs are uint8 RGBA.
"""
from __future__ import annotations

from typing import Callable, Optional

import numpy as np

# Each blend fn takes base RGB and top RGB (float arrays, same shape) -> RGB.
_BLENDS: dict[str, Callable[[np.ndarray, np.ndarray], np.ndarray]] = {
    "normal":      lambda b, s: s,
    "multiply":    lambda b, s: b * s,
    "screen":      lambda b, s: 1.0 - (1.0 - b) * (1.0 - s),
    "overlay":     lambda b, s: np.where(b <= 0.5, 2 * b * s, 1.0 - 2 * (1.0 - b) * (1.0 - s)),
    "hard_light":  lambda b, s: np.where(s <= 0.5, 2 * b * s, 1.0 - 2 * (1.0 - b) * (1.0 - s)),
    "soft_light":  lambda b, s: (1 - 2 * s) * b * b + 2 * s * b,
    "darken":      lambda b, s: np.minimum(b, s),
    "lighten":     lambda b, s: np.maximum(b, s),
    "difference":  lambda b, s: np.abs(b - s),
    "exclusion":   lambda b, s: b + s - 2 * b * s,
    "addition":    lambda b, s: np.clip(b + s, 0.0, 1.0),
    "subtract":    lambda b, s: np.clip(b - s, 0.0, 1.0),
    "divide":      lambda b, s: np.clip(b / np.maximum(s, 1e-6), 0.0, 1.0),
    "negation":    lambda b, s: 1.0 - np.abs(1.0 - b - s),
}

BLEND_MODES: tuple[str, ...] = tuple(_BLENDS.keys())


def blend_pair(
    base: np.ndarray,
    top: np.ndarray,
    mode: str = "normal",
    opacity: float = 1.0,
    mask: Optional[np.ndarray] = None,
) -> np.ndarray:
    """Composite `top` (RGBA uint8) over `base` (RGBA uint8) -> RGBA uint8.

    `mask`, if given, is HxW in [0,1] (or uint8) gating where `top` applies.
    """
    b = base.astype(np.float32) / 255.0
    s = top.astype(np.float32) / 255.0
    b_rgb, b_a = b[..., :3], b[..., 3:4]
    s_rgb, s_a = s[..., :3], s[..., 3:4]

    blended_rgb = _BLENDS.get(mode, _BLENDS["normal"])(b_rgb, s_rgb)
    # Where the base is transparent, fall back to the straight source color so
    # blending onto empty pixels doesn't darken/halo.
    blended_rgb = b_rgb * (1.0 - s_a) * 0 + np.where(b_a > 0, blended_rgb, s_rgb)

    eff_a = s_a * float(np.clip(opacity, 0.0, 1.0))
    if mask is not None:
        m = mask.astype(np.float32)
        if m.max() > 1.0:
            m = m / 255.0
        eff_a = eff_a * m[..., None]

    out_rgb = blended_rgb * eff_a + b_rgb * (1.0 - eff_a)
    out_a = eff_a + b_a * (1.0 - eff_a)
    out = np.concatenate([out_rgb, out_a], axis=-1)
    return (np.clip(out, 0.0, 1.0) * 255.0 + 0.5).astype(np.uint8)


def composite(layers: list[tuple[np.ndarray, str, float, Optional[np.ndarray]]]) -> Optional[np.ndarray]:
    """Composite a bottom-up list of ``(rgba, mode, opacity, mask)`` -> RGBA uint8.

    The first entry is the base; ``mode``/``opacity``/``mask`` on the base are ignored.
    """
    if not layers:
        return None
    base = layers[0][0]
    for rgba, mode, opacity, mask in layers[1:]:
        base = blend_pair(base, rgba, mode, opacity, mask)
    return base
