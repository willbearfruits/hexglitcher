"""The Document: an ordered stack of compositing layers + a source registry.

Layers are ordered bottom→top (index 0 is the base). A freshly opened image
produces a document with a single locked "Original" layer; the user duplicates
it and adds ops to the copy to "blend the original with the glitched version".
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Optional

from .layer import Layer, SourceImage
from .video import SourceVideo


@dataclass
class Document:
    sources: dict[str, SourceImage] = field(default_factory=dict)
    layers: list[Layer] = field(default_factory=list)   # bottom → top
    seed: int = 0
    frame: int = 0                                       # current frame (video docs)
    name: str = "Untitled"
    uid: str = field(default_factory=lambda: uuid.uuid4().hex)

    # construction -----------------------------------------------------------
    @classmethod
    def from_source(cls, src: SourceImage) -> "Document":
        doc = cls(sources={src.uid: src}, name=src.name)
        doc.layers.append(Layer(source_id=src.uid, locked=True, name="Original"))
        return doc

    @classmethod
    def from_video(cls, vid: SourceVideo) -> "Document":
        doc = cls(sources={vid.uid: vid}, name=vid.name)
        doc.layers.append(Layer(source_id=vid.uid, locked=True, name="Original"))
        return doc

    def add_source(self, src: SourceImage) -> str:
        self.sources[src.uid] = src
        return src.uid

    def resolve_source(self, source_id: str, frame: Optional[int] = None) -> Optional[SourceImage]:
        """Get a source's SourceImage, materializing the current video frame."""
        s = self.sources.get(source_id)
        if isinstance(s, SourceVideo):
            return s.frame_source(self.frame if frame is None else frame)
        return s

    def frame_count(self) -> int:
        counts = [s.frame_count for s in self.sources.values() if isinstance(s, SourceVideo)]
        return max(counts) if counts else 1

    def is_video(self) -> bool:
        return any(isinstance(s, SourceVideo) for s in self.sources.values())

    @property
    def base_source(self) -> Optional[SourceImage]:
        if not self.layers:
            return None
        return self.resolve_source(self.layers[0].source_id)

    def canvas_size(self) -> tuple[int, int]:
        """(width, height) taken from the base layer's clean decode."""
        src = self.base_source
        if src is not None:
            clean = src.clean_decoded()
            if clean is not None:
                h, w = clean.shape[:2]
                return (w, h)
        return (0, 0)

    # layer ops --------------------------------------------------------------
    def duplicate_layer(self, index: int) -> Layer:
        src_layer = self.layers[index]
        new = Layer.from_dict(src_layer.to_dict())
        new.uid = uuid.uuid4().hex
        new.locked = False
        new.name = f"{src_layer.name} copy"
        for op in new.ops:
            op.uid = uuid.uuid4().hex
        self.layers.insert(index + 1, new)
        return new

    def move_layer(self, index: int, to: int) -> None:
        if self.layers[index].locked and to == 0:
            return
        layer = self.layers.pop(index)
        self.layers.insert(max(0, min(to, len(self.layers))), layer)

    def remove_layer(self, index: int) -> None:
        if not self.layers[index].locked:
            self.layers.pop(index)

    def snapshot(self) -> "Document":
        """A copy safe to hand to the render thread.

        Layers/ops are deep-copied (small, and they mutate as the user edits);
        the immutable source images are shared by reference so we never copy
        large byte buffers, and their content hashes stay cache-stable.
        """
        import copy
        new = Document(sources=self.sources, seed=self.seed, frame=self.frame,
                       name=self.name, uid=self.uid)
        new.layers = copy.deepcopy(self.layers)
        return new

    @classmethod
    def from_dict(cls, d: dict) -> "Document":
        import base64
        sources: dict[str, SourceImage] = {}
        for sid, entry in d.get("sources", {}).items():
            if entry.get("kind") == "video" and entry.get("path"):
                vsrc = SourceVideo.from_file(entry["path"])
                vsrc.uid = sid
                sources[sid] = vsrc
                continue
            data = base64.b64decode(entry["data_b64"]) if "data_b64" in entry else b""
            src = SourceImage(data=data, ext=entry.get("ext", ""), name=entry.get("name", "image"))
            src.uid = sid
            sources[sid] = src
        doc = cls(sources=sources, seed=int(d.get("seed", 0)), name=d.get("name", "Untitled"))
        doc.layers = [Layer.from_dict(l) for l in d.get("layers", [])]
        return doc

    # serialization ----------------------------------------------------------
    def to_dict(self, embed_sources: bool = False) -> dict:
        import base64
        srcs = {}
        for sid, s in self.sources.items():
            if isinstance(s, SourceVideo):
                # videos are referenced by path, not embedded (frames are huge)
                srcs[sid] = {"kind": "video", "path": s.path, "ext": s.ext, "name": s.name}
                continue
            entry = {"ext": s.ext, "name": s.name}
            if embed_sources:
                entry["data_b64"] = base64.b64encode(s.data).decode("ascii")
            srcs[sid] = entry
        return {
            "version": 3,
            "name": self.name,
            "seed": self.seed,
            "sources": srcs,
            "layers": [l.to_dict() for l in self.layers],
        }
