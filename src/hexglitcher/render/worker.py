"""Background render worker — keeps the GUI thread free during recompute.

Follows the KDAB "eight rules of multithreaded Qt": a plain QObject moved onto a
QThread, results delivered back via a queued signal, and a single *latest-wins*
request slot (no FIFO of stale slider positions). The UI submits an immutable
document snapshot; the worker owns the RenderEngine (and thus the prefix cache).
"""
from __future__ import annotations

from typing import Optional

import numpy as np
from PySide6.QtCore import (
    QMetaObject,
    QMutex,
    QMutexLocker,
    QObject,
    Qt,
    Signal,
    Slot,
)
from PySide6.QtGui import QImage

from ..engine.document import Document
from ..engine.pipeline import RenderEngine


def ndarray_to_qimage(rgba: np.ndarray) -> QImage:
    """RGBA uint8 HxWx4 -> a detached QImage that owns its pixels."""
    rgba = np.ascontiguousarray(rgba, dtype=np.uint8)
    h, w = rgba.shape[:2]
    img = QImage(rgba.data, w, h, rgba.strides[0], QImage.Format.Format_RGBA8888)
    return img.copy()  # detach from the (about-to-be-freed) numpy buffer


class RenderWorker(QObject):
    """Renders document snapshots off the GUI thread."""

    previewReady = Signal(object, int, bool)   # (QImage, req_id, all_decoded_ok)
    renderFailed = Signal(int)                  # req_id

    def __init__(self) -> None:
        super().__init__()
        self._engine = RenderEngine()
        self._mutex = QMutex()
        self._latest: Optional[tuple] = None
        self._counter = 0

    # called FROM the GUI thread -------------------------------------------
    def submit(self, doc: Document, max_dim: Optional[int]) -> int:
        with QMutexLocker(self._mutex):
            self._counter += 1
            rid = self._counter
            self._latest = (doc, max_dim, rid)
        # hop to the worker thread's event loop
        QMetaObject.invokeMethod(self, "_process", Qt.ConnectionType.QueuedConnection)
        return rid

    def clear_cache(self) -> None:
        self._engine.clear_cache()

    # runs ON the worker thread --------------------------------------------
    @Slot()
    def _process(self) -> None:
        with QMutexLocker(self._mutex):
            job = self._latest
            self._latest = None
        if job is None:
            return
        doc, max_dim, rid = job
        try:
            rgba, ok = self._engine.render(doc, max_dim)
        except Exception:
            import logging
            logging.getLogger("hexglitcher.render").exception("render failed")
            rgba, ok = None, False
        if rgba is None:
            self.renderFailed.emit(rid)
            return
        self.previewReady.emit(ndarray_to_qimage(rgba), rid, ok)
