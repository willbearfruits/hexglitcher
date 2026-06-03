"""QA tests — exercise every operation and the cross-cutting machinery.

The headline test renders *every registered op* through the real pipeline on an
appropriate base image and asserts it produces a valid RGBA buffer without
raising. This is the cheapest, highest-value safety net: any op that crashes or
returns garbage fails here.

Run: PYTHONPATH=src python3 -m pytest tests/test_ops.py -q
 or: PYTHONPATH=src python3 tests/test_ops.py
"""
import os
import tempfile

import numpy as np

from hexglitcher import presets
from hexglitcher.engine.blend import BLEND_MODES, composite
from hexglitcher.engine.document import Document
from hexglitcher.engine.layer import SourceImage
from hexglitcher.engine.operation import OP_REGISTRY, Operation
from hexglitcher.engine.pipeline import RenderEngine
from hexglitcher.io.recipe import load_project, save_project
from hexglitcher.ops import register_builtin_ops

register_builtin_ops()
IMG = os.path.join(os.path.dirname(__file__), "..", "test_images")


def _base_for(type_id: str) -> str:
    if type_id.startswith("png."):
        return "test.png"
    if type_id.startswith("jpeg."):
        return "test.jpg"
    return "test.bmp"


def _params_for(type_id: str) -> dict:
    p = OP_REGISTRY[type_id].default_params()
    if type_id == "byte.inject":          # needs a real file to mix in
        p["source"] = os.path.join(IMG, "test.bmp")
    return p


def _valid_rgba(arr) -> bool:
    return (arr is not None and arr.dtype == np.uint8
            and arr.ndim == 3 and arr.shape[2] == 4 and arr.shape[0] > 0)


def test_every_op_renders():
    """Every registered op renders through the pipeline to valid RGBA."""
    failures = []
    for type_id in sorted(OP_REGISTRY):
        try:
            src = SourceImage.from_file(os.path.join(IMG, _base_for(type_id)))
            doc = Document.from_source(src)
            doc.duplicate_layer(0).ops = [Operation(type_id, _params_for(type_id))]
            rgba, _ = RenderEngine().render(doc)
            assert _valid_rgba(rgba), f"{type_id}: invalid output"
        except Exception as e:  # noqa: BLE001
            failures.append(f"{type_id}: {e!r}")
    assert not failures, "ops that failed to render:\n" + "\n".join(failures)


def test_every_op_with_extreme_params():
    """Min and max of every numeric param shouldn't crash (hand-edited .glitch)."""
    failures = []
    for type_id, ot in sorted(OP_REGISTRY.items()):
        for spec in ot.params:
            if spec.kind in ("int", "float", "seed") and spec.min is not None and spec.max is not None:
                for val in (spec.min, spec.max):
                    try:
                        src = SourceImage.from_file(os.path.join(IMG, _base_for(type_id)))
                        doc = Document.from_source(src)
                        params = _params_for(type_id)
                        params[spec.key] = val
                        doc.duplicate_layer(0).ops = [Operation(type_id, params)]
                        rgba, _ = RenderEngine().render(doc)
                        assert _valid_rgba(rgba)
                    except Exception as e:  # noqa: BLE001
                        failures.append(f"{type_id}.{spec.key}={val}: {e!r}")
    assert not failures, "extreme-param failures:\n" + "\n".join(failures)


def test_all_blend_modes_composite():
    a = np.random.default_rng(0).integers(0, 256, (32, 32, 4), dtype=np.uint8)
    b = np.random.default_rng(1).integers(0, 256, (32, 32, 4), dtype=np.uint8)
    for mode in BLEND_MODES:
        out = composite([(a, "normal", 1.0, None), (b, mode, 0.7, None)])
        assert _valid_rgba(out), f"blend {mode} produced invalid output"


def test_recipe_roundtrip_many_ops():
    src = SourceImage.from_file(os.path.join(IMG, "test.jpg"))
    doc = Document.from_source(src)
    g = doc.duplicate_layer(0)
    g.blend, g.opacity = "screen", 0.7
    g.ops = [
        Operation("byte.noise", {"amount": 30, "seed": 5}),
        Operation("byte.find_replace", {"find": "FF", "replace": "00"}),
        Operation("pixel.channel_shift", {"shift_r": 8}),
        Operation("pixel.sort", {"low": 0.2, "high": 0.9}),
        Operation("decoder.planar", {"shift": 100}),
    ]
    before = RenderEngine().render(doc)[0]
    path = os.path.join(tempfile.gettempdir(), "qa_roundtrip.glitch")
    save_project(doc, path)
    after = RenderEngine().render(load_project(path))[0]
    assert np.array_equal(before, after)


def test_disabled_op_is_identity():
    src = SourceImage.from_file(os.path.join(IMG, "test.bmp"))
    base = RenderEngine().render(Document.from_source(src))[0]
    doc = Document.from_source(src)
    op = Operation("byte.noise", {"amount": 80})
    op.enabled = False
    doc.duplicate_layer(0).ops = [op]
    out = RenderEngine().render(doc)[0]
    assert np.array_equal(base, out), "disabled op changed the output"


def test_corrupt_and_empty_sources_dont_crash():
    for data in (b"", b"not an image", bytes(range(256))):
        src = SourceImage(data=data, ext=".bin")
        doc = Document.from_source(src)
        # canvas may be empty; render must not raise
        rgba, ok = RenderEngine().render(doc)
        assert ok is False or rgba is not None


def test_all_looks_and_surprise():
    src = SourceImage.from_file(os.path.join(IMG, "test.jpg"))
    for name in presets.look_names():
        doc = Document.from_source(src)
        presets.apply_look(doc, name)
        assert _valid_rgba(RenderEngine().render(doc)[0])
    doc = Document.from_source(src)
    presets.apply_surprise(doc)
    assert _valid_rgba(RenderEngine().render(doc)[0])


def test_video_source_frames_render():
    """Generate a tiny video with OpenCV and render two different frames."""
    import cv2
    path = os.path.join(tempfile.gettempdir(), "qa_video.avi")
    writer = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"MJPG"), 12, (64, 48))
    if not writer.isOpened():
        return  # codec unavailable in this environment; skip
    for i in range(8):
        frame = np.full((48, 64, 3), i * 20, np.uint8)
        frame[:, :, 0] = (i * 30) % 256
        writer.write(frame)
    writer.release()

    from hexglitcher.engine.video import SourceVideo
    vid = SourceVideo.from_file(path)
    assert vid.frame_count >= 1
    doc = Document.from_video(vid)
    doc.duplicate_layer(0).ops = [Operation("pixel.sort", {"low": 0.1, "high": 0.95})]
    doc.frame = 0
    f0 = RenderEngine().render(doc)[0]
    doc.frame = min(5, vid.frame_count - 1)
    f5 = RenderEngine().render(doc)[0]
    assert _valid_rgba(f0) and _valid_rgba(f5)


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
