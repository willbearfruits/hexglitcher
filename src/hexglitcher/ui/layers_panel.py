"""Compositing layers panel — N layers, blend mode, opacity, visibility.

Layers display top-first (Photoshop style): list row 0 is the topmost layer,
which is ``document.layers[-1]``. The bottom row is the locked "Original".
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from ..engine.blend import BLEND_MODES
from ..engine.document import Document


class LayersPanel(QWidget):
    layerSelected = Signal(int)        # document index
    changed = Signal()
    committed = Signal()

    def __init__(self) -> None:
        super().__init__()
        self._doc: Optional[Document] = None
        self._building = False

        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(4)

        self._list = QListWidget()
        self._list.currentRowChanged.connect(self._on_row)
        self._list.itemChanged.connect(self._on_item_changed)
        root.addWidget(self._list, 1)

        # per-layer controls
        ctl = QVBoxLayout()
        ctl.setSpacing(2)
        self._blend = QComboBox()
        self._blend.addItems(list(BLEND_MODES))
        self._blend.currentTextChanged.connect(self._on_blend)
        ctl.addWidget(QLabel("Blend"))
        ctl.addWidget(self._blend)
        self._opacity = QSlider(Qt.Orientation.Horizontal)
        self._opacity.setRange(0, 100)
        self._opacity.valueChanged.connect(self._on_opacity)
        self._opacity.sliderReleased.connect(lambda: self.committed.emit())
        self._opacity_lbl = QLabel("Opacity 100%")
        ctl.addWidget(self._opacity_lbl)
        ctl.addWidget(self._opacity)
        root.addLayout(ctl)

        row = QHBoxLayout()
        self._dup = QPushButton("＋ Duplicate")
        self._del = QPushButton("🗑")
        self._up = QPushButton("▲")
        self._dn = QPushButton("▼")
        for b in (self._del, self._up, self._dn):
            b.setFixedWidth(34)
        self._dup.clicked.connect(self._duplicate)
        self._del.clicked.connect(self._remove)
        self._up.clicked.connect(lambda: self._move(1))     # up in list = +1 doc index
        self._dn.clicked.connect(lambda: self._move(-1))
        row.addWidget(self._dup, 1)
        row.addWidget(self._del)
        row.addWidget(self._up)
        row.addWidget(self._dn)
        root.addLayout(row)
        self.set_document(None)

    # mapping helpers --------------------------------------------------------
    def _doc_index(self, row: int) -> int:
        return len(self._doc.layers) - 1 - row

    def _row(self, doc_index: int) -> int:
        return len(self._doc.layers) - 1 - doc_index

    # public -----------------------------------------------------------------
    def set_document(self, doc: Optional[Document]) -> None:
        self._doc = doc
        self._rebuild()
        on = doc is not None
        for w in (self._dup, self._del, self._up, self._dn, self._blend, self._opacity):
            w.setEnabled(on)
        if on and doc.layers:
            self._list.setCurrentRow(0)

    def current_doc_index(self) -> int:
        r = self._list.currentRow()
        return self._doc_index(r) if (self._doc and r >= 0) else -1

    # internals --------------------------------------------------------------
    def _rebuild(self) -> None:
        self._building = True
        self._list.clear()
        if self._doc is not None:
            for layer in reversed(self._doc.layers):
                lock = " 🔒" if layer.locked else ""
                it = QListWidgetItem(f"{layer.name}{lock}")
                it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                it.setCheckState(Qt.CheckState.Checked if layer.visible else Qt.CheckState.Unchecked)
                self._list.addItem(it)
        self._building = False

    def _current_layer(self):
        i = self.current_doc_index()
        if self._doc and 0 <= i < len(self._doc.layers):
            return self._doc.layers[i]
        return None

    def _on_row(self, row: int) -> None:
        layer = self._current_layer()
        if layer is not None:
            self._building = True
            self._blend.setCurrentText(layer.blend)
            self._opacity.setValue(int(layer.opacity * 100))
            self._opacity_lbl.setText(f"Opacity {int(layer.opacity*100)}%")
            self._blend.setEnabled(not layer.locked)
            self._opacity.setEnabled(not layer.locked)
            self._building = False
        self.layerSelected.emit(self.current_doc_index())

    def _on_item_changed(self, item: QListWidgetItem) -> None:
        if self._building or self._doc is None:
            return
        row = self._list.row(item)
        layer = self._doc.layers[self._doc_index(row)]
        vis = item.checkState() == Qt.CheckState.Checked
        if vis != layer.visible:
            layer.visible = vis
            self.changed.emit()
            self.committed.emit()

    def _on_blend(self, text: str) -> None:
        if self._building:
            return
        layer = self._current_layer()
        if layer and not layer.locked:
            layer.blend = text
            self.changed.emit()
            self.committed.emit()

    def _on_opacity(self, val: int) -> None:
        self._opacity_lbl.setText(f"Opacity {val}%")
        if self._building:
            return
        layer = self._current_layer()
        if layer and not layer.locked:
            layer.opacity = val / 100.0
            self.changed.emit()

    def _duplicate(self) -> None:
        if self._doc is None:
            return
        i = self.current_doc_index()
        if i < 0:
            i = len(self._doc.layers) - 1
        self._doc.duplicate_layer(i)
        self._rebuild()
        self._list.setCurrentRow(self._row(i + 1))
        self.changed.emit()
        self.committed.emit()

    def _remove(self) -> None:
        layer = self._current_layer()
        if self._doc and layer and not layer.locked:
            self._doc.remove_layer(self.current_doc_index())
            self._rebuild()
            self._list.setCurrentRow(0)
            self.changed.emit()
            self.committed.emit()

    def _move(self, delta: int) -> None:
        if self._doc is None:
            return
        i = self.current_doc_index()
        j = i + delta
        layer = self._doc.layers[i] if 0 <= i < len(self._doc.layers) else None
        if layer is None or layer.locked:
            return
        if 1 <= j < len(self._doc.layers):   # never below the locked base (index 0)
            self._doc.move_layer(i, j)
            self._rebuild()
            self._list.setCurrentRow(self._row(j))
            self.changed.emit()
            self.committed.emit()
