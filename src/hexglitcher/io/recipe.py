"""Save/load a glitch *recipe* — the whole non-destructive document as a
self-contained ``.glitch`` JSON project (layers + ops + params + embedded source
images), so a session can be reopened and kept editing.
"""
from __future__ import annotations

import json

from ..engine.document import Document


def save_project(doc: Document, path: str) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(doc.to_dict(embed_sources=True), fh, separators=(",", ":"))


def load_project(path: str) -> Document:
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    return Document.from_dict(data)
