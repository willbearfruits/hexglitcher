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
