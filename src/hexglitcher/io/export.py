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
