"""Audio-DSP-over-bytes — the Audacity databending workflow, built in.

These byte-domain ops treat the region's bytes as a mono PCM signal (samples
centered at 128) and run classic audio effects over it. Re-decoded as an image,
echo/flanger/tremolo produce the smeared, rhythmic, banded glitches that the
"import raw → apply effect → export raw" Audacity trick is loved for — without
leaving the app or risking the header (the region defaults to the safe zone).
"""
from __future__ import annotations

import numpy as np

from ..engine.operation import OpDomain, register_op
from .params import p_float, p_int

CAT = "Audio (Databend)"


def _to_signal(region) -> np.ndarray:
    """Bytes -> float signal centered at 0 (range roughly -128..127)."""
    return np.frombuffer(bytes(region), dtype=np.uint8).astype(np.float32) - 128.0


def _from_signal(sig: np.ndarray) -> bytes:
    return (np.clip(sig, -128.0, 127.0) + 128.0).astype(np.uint8).tobytes()


@register_op(
    "audio.echo", "Echo / Delay", OpDomain.BYTE, CAT,
    params=(
        p_int("delay", "Delay (bytes)", 600, 1, 200_000, 1),
        p_float("decay", "Decay", 0.5, 0.0, 0.99, 0.01),
        p_int("taps", "Repeats", 4, 1, 32, 1),
    ),
    help="Adds decaying delayed copies of the signal — ghosted, repeating echoes.",
)
def _echo(region, params, ctx):
    sig = _to_signal(region)
    n = sig.size
    if n == 0:
        return None
    delay = int(params["delay"])
    decay = float(params["decay"])
    out = sig.copy()
    for r in range(1, int(params["taps"]) + 1):
        d = delay * r
        if d >= n:
            break
        out[d:] += (decay ** r) * sig[: n - d]
    return _from_signal(out)


@register_op(
    "audio.tremolo", "Tremolo / Modulation", OpDomain.BYTE, CAT,
    params=(
        p_float("rate", "Cycles over region", 40.0, 0.1, 5000.0, 0.1),
        p_float("depth", "Depth", 0.8, 0.0, 1.0, 0.01),
    ),
    help="Amplitude-modulate the signal with a sine LFO — rhythmic brightness bands.",
)
def _tremolo(region, params, ctx):
    sig = _to_signal(region)
    n = sig.size
    if n == 0:
        return None
    t = np.arange(n, dtype=np.float32)
    lfo = 1.0 - float(params["depth"]) * (0.5 + 0.5 * np.sin(2 * np.pi * float(params["rate"]) * t / n))
    return _from_signal(sig * lfo)


@register_op(
    "audio.flanger", "Flanger / Phaser", OpDomain.BYTE, CAT,
    params=(
        p_int("base", "Base delay (bytes)", 80, 1, 50_000, 1),
        p_int("sweep", "Sweep (bytes)", 64, 0, 50_000, 1),
        p_float("rate", "Cycles over region", 8.0, 0.1, 2000.0, 0.1),
        p_float("mix", "Mix", 0.7, 0.0, 1.0, 0.01),
    ),
    help="A delay whose length sweeps with an LFO — swirling comb-filter streaks.",
)
def _flanger(region, params, ctx):
    sig = _to_signal(region)
    n = sig.size
    if n == 0:
        return None
    t = np.arange(n, dtype=np.float32)
    d = params["base"] + params["sweep"] * (0.5 + 0.5 * np.sin(2 * np.pi * float(params["rate"]) * t / n))
    idx = np.clip(t - d, 0, n - 1).astype(np.int64)
    return _from_signal(sig + float(params["mix"]) * sig[idx])


@register_op(
    "audio.bitcrush", "Bitcrush", OpDomain.BYTE, CAT,
    params=(p_int("step", "Quantize step", 16, 2, 128, 1),),
    help="Reduce sample resolution — chunky posterized banding.",
)
def _bitcrush(region, params, ctx):
    arr = np.frombuffer(bytes(region), dtype=np.uint8)
    if arr.size == 0:
        return None
    step = int(params["step"])
    return ((arr // step) * step).astype(np.uint8).tobytes()


@register_op(
    "audio.overdrive", "Overdrive / Distort", OpDomain.BYTE, CAT,
    params=(
        p_float("gain", "Gain", 3.0, 1.0, 32.0, 0.1),
        p_float("bias", "Bias", 0.0, -1.0, 1.0, 0.01),
    ),
    help="Amplify and hard-clip the signal — harsh saturated bands.",
)
def _overdrive(region, params, ctx):
    sig = _to_signal(region)
    if sig.size == 0:
        return None
    return _from_signal(sig * float(params["gain"]) + 128.0 * float(params["bias"]))
