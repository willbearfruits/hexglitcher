"""Video sources — a video is treated as a sequence of frames, each of which is
materialized into an ordinary :class:`SourceImage` so the *entire existing
pipeline* (byte ops, decode, pixel ops, compositing) glitches it unchanged.

A :class:`SourceVideo` lazily reads frames with OpenCV and BMP-encodes the
requested frame; the resulting per-frame ``SourceImage`` carries frame-specific
bytes (and therefore a frame-specific cache hash), so scrubbing just re-renders
the current frame.
"""
from __future__ import annotations

import os
import uuid
from typing import Optional

import numpy as np

try:
    import cv2  # type: ignore
except Exception:  # pragma: no cover
    cv2 = None

from .layer import SourceImage

VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v", ".mpg", ".mpeg"}


def is_video(path: str) -> bool:
    return os.path.splitext(path)[1].lower() in VIDEO_EXTS


class SourceVideo:
    """A frame provider that looks like a source to the document/pipeline."""

    def __init__(self, path: str, ext: str = "", name: str = "video") -> None:
        self.path = path
        self.ext = ext
        self.name = name
        self.uid = uuid.uuid4().hex
        self._count = 1
        self._fps = 24.0
        self._size = (0, 0)
        self._frame_cache: dict[int, SourceImage] = {}
        self._probe()

    def _probe(self) -> None:
        if cv2 is None:
            return
        cap = cv2.VideoCapture(self.path)
        try:
            if cap.isOpened():
                self._count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 1
                self._fps = cap.get(cv2.CAP_PROP_FPS) or 24.0
                self._size = (int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
                              int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)))
        finally:
            cap.release()

    @property
    def frame_count(self) -> int:
        return max(1, self._count)

    @property
    def fps(self) -> float:
        return self._fps or 24.0

    @property
    def size(self) -> tuple[int, int]:
        return self._size

    def read_rgb(self, i: int) -> Optional[np.ndarray]:
        """Decode frame `i` to an HxWx3 uint8 RGB array (or None)."""
        if cv2 is None:
            return None
        cap = cv2.VideoCapture(self.path)
        try:
            if not cap.isOpened():
                return None
            i = max(0, min(int(i), self.frame_count - 1))
            cap.set(cv2.CAP_PROP_POS_FRAMES, i)
            ok, frame = cap.read()
            if not ok or frame is None:
                return None
            return cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        finally:
            cap.release()

    def frame_source(self, i: int) -> SourceImage:
        """Materialize frame `i` as a BMP-backed SourceImage (cached)."""
        i = max(0, min(int(i), self.frame_count - 1))
        cached = self._frame_cache.get(i)
        if cached is not None:
            return cached
        rgb = self.read_rgb(i)
        data = b""
        if rgb is not None and cv2 is not None:
            ok, enc = cv2.imencode(".bmp", cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))
            if ok:
                data = enc.tobytes()
        src = SourceImage(data=data, ext=".bmp", name=f"{self.name}#{i}")
        if len(self._frame_cache) > 8:        # keep only a small scrub window
            self._frame_cache.clear()
        self._frame_cache[i] = src
        return src

    @classmethod
    def from_file(cls, path: str) -> "SourceVideo":
        _, ext = os.path.splitext(path)
        return cls(path=path, ext=ext.lower(), name=os.path.basename(path))
