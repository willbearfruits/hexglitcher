"""Headless engine tests for HexGlitcher v3.

Run with pytest (``pytest -q``) or directly (``PYTHONPATH=src python tests/test_v3.py``).
"""
import os
import tempfile

import numpy as np

from hexglitcher import presets
from hexglitcher.engine.decode import decode_bytes
from hexglitcher.engine.document import Document
from hexglitcher.engine.layer import SourceImage
from hexglitcher.engine.operation import OP_REGISTRY, ByteContext, Operation
from hexglitcher.engine.pipeline import RenderEngine
from hexglitcher.formats import detect_format
from hexglitcher.io.recipe import load_project, save_project
from hexglitcher.ops import register_builtin_ops

register_builtin_ops()
IMG = os.path.join(os.path.dirname(__file__), "..", "test_images")


def _doc(fn="test.jpg") -> Document:
    return Document.from_source(SourceImage.from_file(os.path.join(IMG, fn)))


def test_registry_populated():
    assert len(OP_REGISTRY) >= 20


def test_render_bmp_rgba():
    rgba, ok = RenderEngine().render(_doc("test.bmp"))
    assert ok and rgba is not None and rgba.shape[2] == 4


def test_prefix_cache_is_deterministic():
    doc = _doc()
    g = doc.duplicate_layer(0)
    g.ops = [Operation("byte.noise", {"seed": 1}), Operation("pixel.sort")]
    eng = RenderEngine()
    a, _ = eng.render(doc)
    b, _ = eng.render(doc)
    assert np.array_equal(a, b)


def test_proxy_smaller_than_full():
    doc = _doc("test.bmp")
    full, _ = RenderEngine().render(doc)
    proxy, _ = RenderEngine().render(doc, max_dim=64)
    assert max(proxy.shape[:2]) <= 64 < max(full.shape[:2])


def test_png_byte_op_visible_via_autoraster():
    base = RenderEngine().render(_doc("test.png"))[0].astype(np.int16)
    doc = _doc("test.png")
    doc.duplicate_layer(0).ops = [Operation("audio.echo")]
    out, ok = RenderEngine().render(doc)
    assert ok and np.abs(out.astype(np.int16) - base).mean() > 1.0


def test_png_filter_rewrite_stays_decodable():
    data = open(os.path.join(IMG, "test.png"), "rb").read()
    op = Operation("png.filter_rewrite", {"mode": "force", "filter": 4})
    ctx = ByteContext(rng=np.random.default_rng(0), fmt=detect_format(data, ""),
                      region=(0, len(data)), total_size=len(data))
    out = op.optype.apply(bytearray(data), op.params, ctx)
    assert out and decode_bytes(bytes(out)) is not None


def test_recipe_roundtrip_identical(tmp_path=None):
    doc = _doc()
    g = doc.duplicate_layer(0)
    g.blend = "screen"
    g.ops = [Operation("byte.noise", {"seed": 2}), Operation("pixel.sort")]
    before = RenderEngine().render(doc)[0]
    path = os.path.join(str(tmp_path) if tmp_path else tempfile.gettempdir(), "rt.glitch")
    save_project(doc, path)
    after = RenderEngine().render(load_project(path))[0]
    assert np.array_equal(before, after)


def test_all_looks_render():
    for name in presets.look_names():
        doc = _doc()
        presets.apply_look(doc, name)
        rgba, ok = RenderEngine().render(doc)
        assert rgba is not None


if __name__ == "__main__":
    import traceback
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in tests:
        try:
            fn()
            print("PASS", fn.__name__)
        except Exception:
            failed += 1
            print("FAIL", fn.__name__)
            traceback.print_exc()
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    raise SystemExit(1 if failed else 0)
