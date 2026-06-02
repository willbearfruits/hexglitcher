"""Preview canvas — zoom-to-cursor, pan, fit, and a before/after compare wipe."""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPixmap
from PySide6.QtWidgets import (
    QGraphicsPixmapItem,
    QGraphicsScene,
    QGraphicsView,
)

from .theme import CANVAS_BG


class CanvasView(QGraphicsView):
    def __init__(self) -> None:
        super().__init__()
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self._item = QGraphicsPixmapItem()
        self._item.setTransformationMode(Qt.TransformationMode.SmoothTransformation)
        self._scene.addItem(self._item)

        self._orig_item = QGraphicsPixmapItem()           # original, for compare
        self._orig_item.setVisible(False)
        self._scene.addItem(self._orig_item)

        self.setBackgroundBrush(QColor(CANVAS_BG))
        self.setRenderHints(QPainter.RenderHint.SmoothPixmapTransform)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._has_image = False
        self._compare = False

    # image ------------------------------------------------------------------
    def set_image(self, qimage: QImage, logical_size: Optional[tuple] = None) -> None:
        """Show `qimage`. If `logical_size` (full canvas w,h) is given, the pixmap
        is scaled to it so a low-res proxy occupies the same space as the full
        render — the preview never jumps size between proxy and full passes.
        """
        pix = QPixmap.fromImage(qimage)
        first = not self._has_image
        self._item.setPixmap(pix)
        if logical_size and pix.width():
            lw, lh = logical_size
            self._item.setScale(lw / pix.width())
            self._scene.setSceneRect(QRectF(0, 0, lw, lh))
        else:
            self._item.setScale(1.0)
            self._scene.setSceneRect(QRectF(pix.rect()))
        self._has_image = True
        if first:
            self.fit()

    def set_original(self, qimage: Optional[QImage]) -> None:
        if qimage is None:
            self._orig_item.setPixmap(QPixmap())
            return
        self._orig_item.setPixmap(QPixmap.fromImage(qimage))

    def set_compare(self, on: bool) -> None:
        """Hold-to-compare: show the original instead of the result."""
        self._compare = on
        self._orig_item.setVisible(on and not self._orig_item.pixmap().isNull())
        self._item.setVisible(not on)

    # navigation -------------------------------------------------------------
    def fit(self) -> None:
        if self._has_image:
            self.fitInView(self._item, Qt.AspectRatioMode.KeepAspectRatio)

    def actual_size(self) -> None:
        self.resetTransform()

    def zoom_percent(self) -> int:
        return int(round(self.transform().m11() * 100))

    def wheelEvent(self, event) -> None:  # noqa: N802
        if not self._has_image:
            return
        step = 1.0015 ** event.angleDelta().y()
        self.scale(step, step)
