"""Export a rendered document to an image file (full resolution)."""
from __future__ import annotations

import os
from typing import Optional

import numpy as np
from PIL import Image

from ..engine.document import Document
from ..engine.pipeline import RenderEngine


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
