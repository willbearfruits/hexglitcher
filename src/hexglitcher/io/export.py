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


def export_video(doc: Document, path: str, fps: float = 24.0,
                 frames=None, audio_from=None, progress=None) -> int:
    """Render every frame of a video document through the stack and write an MP4.

    Each frame is rendered by setting ``doc.frame`` and reusing the whole glitch
    pipeline. If `audio_from` (the original video path) is given and has an audio
    track, it's muxed back in with ffmpeg. `progress(i, n)` is called per frame.
    Returns the number of frames written.
    """
    if cv2 is None:
        raise RuntimeError("OpenCV is required for video export.")
    cw, ch = doc.canvas_size()
    if cw <= 0 or ch <= 0:
        raise RuntimeError("Nothing to export.")
    n = int(frames) if frames else doc.frame_count()
    eng = RenderEngine()
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    silent = path
    if audio_from:
        root, ext = os.path.splitext(path)
        silent = f"{root}.silent{ext or '.mp4'}"
    writer = cv2.VideoWriter(silent, fourcc, float(fps) or 24.0, (cw, ch))
    try:
        for i in range(n):
            snap = doc.snapshot()
            snap.frame = i
            rgba, _ = eng.render(snap)
            if rgba is None:
                continue
            bgr = cv2.cvtColor(np.ascontiguousarray(rgba[..., :3]), cv2.COLOR_RGB2BGR)
            if bgr.shape[:2] != (ch, cw):
                bgr = cv2.resize(bgr, (cw, ch))
            writer.write(bgr)
            if progress:
                progress(i + 1, n)
    finally:
        writer.release()

    if audio_from:
        import shutil
        import subprocess
        try:
            subprocess.run(
                ["ffmpeg", "-y", "-i", silent, "-i", audio_from,
                 "-c:v", "copy", "-map", "0:v:0", "-map", "1:a:0?", "-shortest", path],
                check=True, capture_output=True,
            )
            os.remove(silent)
        except Exception:
            shutil.move(silent, path)  # no audio track / ffmpeg missing -> keep silent
    return n
