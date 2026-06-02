"""Source images and compositing layers.

A :class:`SourceImage` owns the immutable bytes of a loaded file plus its format
backend and a cached *clean* decode (used as the fallback when corrupted bytes
fail to decode). Multiple layers may reference the same source by id.

A :class:`Layer` references a source and carries a non-destructive op-stack, a
blend mode, opacity, visibility and (later) a mask. Layers composite bottom→top.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from .decode import decode_bytes
from .hashing import hash_bytes
from .operation import Operation, OpDomain
from ..formats import detect_format
from ..formats.base import FormatBackend


@dataclass
class SourceImage:
    data: bytes
    ext: str = ""
    name: str = "image"
    uid: str = field(default_factory=lambda: uuid.uuid4().hex)
    _fmt: Optional[FormatBackend] = field(default=None, repr=False)
    _hash: Optional[str] = field(default=None, repr=False)
    _clean: Optional[np.ndarray] = field(default=None, repr=False)

    @property
    def fmt(self) -> FormatBackend:
        if self._fmt is None:
            self._fmt = detect_format(self.data, self.ext)
        return self._fmt

    @property
    def content_hash(self) -> str:
        if self._hash is None:
            self._hash = hash_bytes(self.data)
        return self._hash

    def clean_decoded(self) -> Optional[np.ndarray]:
        """Decode of the pristine, uncorrupted bytes (cached). The safety net."""
        if self._clean is None:
            self._clean = decode_bytes(self.data)
        return self._clean

    @classmethod
    def from_file(cls, path: str) -> "SourceImage":
        import os
        with open(path, "rb") as fh:
            data = fh.read()
        _, ext = os.path.splitext(path)
        return cls(data=data, ext=ext.lower(), name=os.path.basename(path))


@dataclass
class Layer:
    source_id: str
    ops: list[Operation] = field(default_factory=list)
    blend: str = "normal"
    opacity: float = 1.0
    visible: bool = True
    locked: bool = False               # the Original base layer can't be edited/moved
    name: str = "Layer"
    uid: str = field(default_factory=lambda: uuid.uuid4().hex)

    def byte_ops(self) -> list[Operation]:
        return [o for o in self.ops if o.enabled and o.domain is OpDomain.BYTE]

    def pixel_ops(self) -> list[Operation]:
        return [o for o in self.ops if o.enabled and o.domain is OpDomain.PIXEL]

    def to_dict(self) -> dict:
        return {
            "source_id": self.source_id,
            "ops": [o.to_dict() for o in self.ops],
            "blend": self.blend,
            "opacity": self.opacity,
            "visible": self.visible,
            "locked": self.locked,
            "name": self.name,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Layer":
        return cls(
            source_id=d["source_id"],
            ops=[Operation.from_dict(o) for o in d.get("ops", [])],
            blend=d.get("blend", "normal"),
            opacity=float(d.get("opacity", 1.0)),
            visible=bool(d.get("visible", True)),
            locked=bool(d.get("locked", False)),
            name=d.get("name", "Layer"),
        )
