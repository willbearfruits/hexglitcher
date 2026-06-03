"""Export a rendered document to an image file (full resolution)."""
from __future__ import annotations

import os
from typing import Optional

import numpy as np
from PIL import Image

from ..engine.document import Document
from ..engine.pipeline import RenderEngine

try:
    import cv2  # type: ignore
except Exception:  # pragma: no cover
    cv2 = None


def render_full(doc: Document) -> Optional[np.ndarray]:
    """Render the whole document at native resolution -> RGBA uint8 (or None)."""
    rgba, _ok = RenderEngine().render(doc.snapshot(), max_dim=None)
    return rgba


def export_document(doc: Document, path: str, quality: int = 92) -> None:
    rgba = render_full(doc)
    if rgba is None:
        raise RuntimeError("Nothing to export (no decodable image).")
    im = Image.fromarray(rgba)
    ext = os.path.splitext(path)[1].lower()
    if ext in (".jpg", ".jpeg", ".bmp"):
        im = im.convert("RGB")
        im.save(path, quality=quality)
    else:
        im.save(path)


def export_animation(doc: Document, path: str, frames: int = 16, fps: int = 12) -> int:
    """Sweep the document seed across `frames` renders and save an animated GIF.

    The seed feeds every randomized op, so a sweep walks through related-but-
    different glitches — a moving, evolving version of the current stack.
    Returns the number of frames written.
    """
    eng = RenderEngine()
    base_seed = doc.seed
    imgs = []
    for i in range(max(1, frames)):
        snap = doc.snapshot()
        snap.seed = base_seed + i
        rgba, _ = eng.render(snap)
        if rgba is not None:
            imgs.append(Image.fromarray(rgba).convert("RGB"))
    if not imgs:
        raise RuntimeError("Nothing to export (no decodable image).")
    duration = max(20, int(1000 / max(1, fps)))
    imgs[0].save(path, save_all=True, append_images=imgs[1:],
                 duration=duration, loop=0, optimize=False, format="GIF")
    return len(imgs)


_ENCODER_CACHE: dict = {}


def video_encoder() -> str:
    """Pick a GPU encoder (NVENC) if ffmpeg exposes it, else CPU libx264."""
    if "enc" not in _ENCODER_CACHE:
        import subprocess
        enc = "libx264"
        try:
            out = subprocess.run(["ffmpeg", "-hide_banner", "-encoders"],
                                 capture_output=True, text=True, timeout=10)
            if "h264_nvenc" in out.stdout:
                enc = "h264_nvenc"
        except Exception:
            pass
        _ENCODER_CACHE["enc"] = enc
    return _ENCODER_CACHE["enc"]


def export_video(doc: Document, path: str, fps: float = 24.0,
                 frames=None, audio_from=None, progress=None) -> int:
    """Glitch every frame through the stack and stream it to ffmpeg.

    Frames are read sequentially (one capture, no per-frame seek) and each is
    materialized as the source's current frame so the whole pipeline renders it;
    the result is piped as raw video into ffmpeg, which encodes on the GPU
    (h264_nvenc when available) and muxes the original audio back in.
    ``progress(i, n)`` is called per frame. Returns frames written.
    """
    import subprocess
    import tempfile

    if cv2 is None:
        raise RuntimeError("OpenCV is required for video export.")
    cw, ch = doc.canvas_size()
    if cw <= 0 or ch <= 0:
        raise RuntimeError("Nothing to export.")

    from ..engine.layer import SourceImage
    from ..engine.video import SourceVideo

    vid = next((s for s in doc.sources.values() if isinstance(s, SourceVideo)), None)
    n = int(frames) if frames else doc.frame_count()
    eng = RenderEngine()
    encoder = video_encoder()

    cmd = ["ffmpeg", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24",
           "-s", f"{cw}x{ch}", "-r", str(float(fps) or 24.0), "-i", "pipe:0"]
    if audio_from:
        cmd += ["-i", audio_from]
    cmd += ["-c:v", encoder, "-pix_fmt", "yuv420p"]
    if audio_from:
        cmd += ["-map", "0:v:0", "-map", "1:a:0?", "-shortest"]
    cmd += [path]

    errfile = tempfile.TemporaryFile()
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE,
                            stdout=subprocess.DEVNULL, stderr=errfile)
    cap = cv2.VideoCapture(vid.path) if vid is not None else None
    written = 0
    try:
        for i in range(n):
            if cap is not None:
                ok, frame = cap.read()
                if not ok:
                    break
                ok_b, enc = cv2.imencode(".bmp", frame)
                if ok_b:
                    vid._frame_cache = {i: SourceImage(data=enc.tobytes(), ext=".bmp",
                                                       name=f"{vid.name}#{i}")}
            snap = doc.snapshot()
            snap.frame = i
            rgba, _ = eng.render(snap)
            if rgba is None:
                continue
            bgr = cv2.cvtColor(np.ascontiguousarray(rgba[..., :3]), cv2.COLOR_RGB2BGR)
            if bgr.shape[:2] != (ch, cw):
                bgr = cv2.resize(bgr, (cw, ch))
            proc.stdin.write(bgr.tobytes())
            written += 1
            if progress:
                progress(i + 1, n)
    finally:
        if cap is not None:
            cap.release()
        try:
            proc.stdin.close()
        except Exception:
            pass
        proc.wait()
    if proc.returncode not in (0, None):
        errfile.seek(0)
        msg = errfile.read().decode("utf-8", "ignore")[-400:]
        raise RuntimeError(f"ffmpeg ({encoder}) failed:\n{msg}")
    return written
