"""Presets ("Looks") and the Surprise Me generator.

A Look is a list of layer specs that populates a document; Surprise Me builds a
tasteful random glitch layer. Both teach the stack model by example — the user
sees ops appear and can poke each one.
"""
from __future__ import annotations

import random

from ..engine.document import Document
from ..engine.operation import OP_REGISTRY, Operation
from ..ops import register_builtin_ops

_rng = random.SystemRandom()

CURATED_BYTE = ["byte.noise", "byte.shift", "byte.transpose", "byte.repeat", "byte.sort"]
CURATED_PIXEL = ["pixel.channel_shift", "pixel.sort", "pixel.channel_swap"]
BLENDS = ["normal", "screen", "difference", "lighten", "overlay", "addition"]


def _rnd_params(type_id: str) -> dict:
    ot = OP_REGISTRY[type_id]
    params = ot.default_params()
    for spec in ot.params:
        if spec.kind in ("int", "seed") and spec.min is not None and spec.max is not None:
            params[spec.key] = _rng.randint(int(spec.min), int(spec.max))
        elif spec.kind == "float" and spec.min is not None and spec.max is not None:
            params[spec.key] = round(_rng.uniform(spec.min, spec.max), 3)
        elif spec.kind == "choice" and spec.choices:
            params[spec.key] = _rng.choice(spec.choices)
    # keep corruption tasteful, not destructive
    if "amount" in params:
        params["amount"] = min(params["amount"], _rng.randint(8, 70))
    return params


def _make_op(type_id: str) -> Operation:
    return Operation(type_id, _rnd_params(type_id))


def apply_surprise(doc: Document) -> None:
    """Replace any glitch layers with one fresh, randomized glitch layer."""
    register_builtin_ops()
    doc.layers = [l for l in doc.layers if l.locked] or doc.layers[:1]
    glitch = doc.duplicate_layer(0)
    glitch.name = "Surprise"
    glitch.locked = False
    glitch.blend = _rng.choice(BLENDS)
    glitch.opacity = round(_rng.uniform(0.6, 1.0), 2)
    ops = [_make_op(t) for t in _rng.sample(CURATED_BYTE, _rng.randint(1, 2))]
    ops += [_make_op(t) for t in _rng.sample(CURATED_PIXEL, _rng.randint(1, 2))]
    glitch.ops = ops


# ── Named "Looks": curated stacks that populate the document in one click ──────
# Each value: dict(blend, opacity, ops=[(type_id, params), ...]).
LOOKS: dict[str, dict] = {
    "Chromatic Drift": {"blend": "normal", "opacity": 1.0, "ops": [
        ("pixel.channel_shift", {"shift_r": 14, "shift_b": -14}),
        ("pixel.sort", {"direction": "horizontal", "low": 0.3, "high": 0.85}),
    ]},
    "Scanline Ghost": {"blend": "screen", "opacity": 0.9, "ops": [
        ("pixel.row_shift", {"axis": "rows", "mode": "sine", "max_shift": 22, "rate": 60.0}),
        ("pixel.noise", {"amount": 18, "mono": True}),
        ("pixel.channel_shift", {"shift_r": 6, "shift_b": -6}),
    ]},
    "JPEG Rot": {"blend": "normal", "opacity": 1.0, "ops": [
        ("jpeg.recompress", {"quality": 8, "iterations": 8}),
        ("byte.noise", {"amount": 22, "mode": "random", "seed": 1}),
    ]},
    "Datamosh": {"blend": "normal", "opacity": 1.0, "ops": [
        ("byte.shift", {"offset": 5}),
        ("byte.transpose", {"chunks": 12, "seed": 2}),
        ("pixel.channel_shift", {"shift_r": 10, "shift_b": -8}),
    ]},
    "Plane Tear": {"blend": "difference", "opacity": 0.85, "ops": [
        ("decoder.planar", {"shift": 5000}),
        ("pixel.row_shift", {"axis": "rows", "mode": "random", "max_shift": 30, "seed": 7}),
    ]},
    "Wrong Width": {"blend": "normal", "opacity": 1.0, "ops": [
        ("decoder.wrong_width", {"width_delta": 7, "channels": "3 (RGB)"}),
        ("pixel.sort", {"direction": "vertical", "low": 0.2, "high": 0.9}),
    ]},
}


def look_names() -> list[str]:
    return list(LOOKS.keys())


def apply_look(doc: Document, name: str) -> None:
    """Replace glitch layers with one layer built from the named Look."""
    register_builtin_ops()
    spec = LOOKS.get(name)
    if not spec:
        return
    doc.layers = [l for l in doc.layers if l.locked] or doc.layers[:1]
    glitch = doc.duplicate_layer(0)
    glitch.name = name
    glitch.locked = False
    glitch.blend = spec.get("blend", "normal")
    glitch.opacity = float(spec.get("opacity", 1.0))
    glitch.ops = [Operation(tid, dict(params)) for tid, params in spec["ops"]]
