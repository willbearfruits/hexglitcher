"""Headless end-to-end smoke test of the v3 engine (no Qt).

Run: PYTHONPATH=src python3 tests/smoke_engine.py
"""
import os
import sys
import time

import numpy as np

from hexglitcher.engine.document import Document
from hexglitcher.engine.layer import SourceImage
from hexglitcher.engine.operation import Operation
from hexglitcher.engine.pipeline import RenderEngine
from hexglitcher.ops import register_builtin_ops

HERE = os.path.dirname(__file__)
IMAGES = os.path.join(HERE, "..", "test_images")


def _save(rgba: np.ndarray, path: str) -> None:
    from PIL import Image
    Image.fromarray(rgba).save(path)


def run(img_name: str) -> None:
    register_builtin_ops()
    src_path = os.path.join(IMAGES, img_name)
    src = SourceImage.from_file(src_path)
    print(f"\n=== {img_name} ===  format={src.fmt.name}  bytes={len(src.data):,}")
    clean = src.clean_decoded()
    assert clean is not None, "clean decode failed — bad test image?"
    print(f"  clean decode: {clean.shape}  safe_zone={src.fmt.safe_zone(src.data)}")

    doc = Document.from_source(src)
    glitch = doc.duplicate_layer(0)          # copy of Original on top
    glitch.blend = "screen"
    glitch.opacity = 0.85
    glitch.ops = [
        Operation("byte.noise", {"amount": 40, "mode": "random", "seed": 7}),
        Operation("byte.shift", {"offset": 3}),
        Operation("pixel.channel_shift", {"shift_r": 12, "shift_b": -12}),
        Operation("pixel.sort", {"direction": "horizontal", "low": 0.2, "high": 0.85}),
    ]

    eng = RenderEngine()

    t0 = time.perf_counter()
    full, ok = eng.render(doc)
    t_full = time.perf_counter() - t0
    print(f"  full render: {full.shape} ok={ok} in {t_full*1000:.0f} ms  cache={len(eng._cache)}")

    # Second render should be all cache hits (no recompute).
    t0 = time.perf_counter()
    full2, _ = eng.render(doc)
    t_cached = time.perf_counter() - t0
    print(f"  cached render: {t_cached*1000:.1f} ms  (speedup x{t_full/max(t_cached,1e-6):.0f})")
    assert np.array_equal(full, full2), "cached render differs!"

    # Edit only a PIXEL op -> decode must be reused (fast).
    glitch.ops[2].params["shift_r"] = 20
    t0 = time.perf_counter()
    eng.render(doc)
    t_pix = time.perf_counter() - t0
    print(f"  after pixel-op edit: {t_pix*1000:.0f} ms (decode reused)")

    # Proxy render (preview during drag).
    t0 = time.perf_counter()
    proxy, _ = eng.render(doc, max_dim=400)
    t_proxy = time.perf_counter() - t0
    print(f"  proxy render: {proxy.shape} in {t_proxy*1000:.0f} ms")

    out = f"/tmp/hexglitch_{src.fmt.name}.png"
    _save(full, out)
    print(f"  wrote {out}")


if __name__ == "__main__":
    names = sys.argv[1:] or ["test.bmp", "test.jpg", "test.png"]
    for n in names:
        if os.path.exists(os.path.join(IMAGES, n)):
            run(n)
        else:
            print(f"(skip {n}: not found)")
    print("\nOK")
