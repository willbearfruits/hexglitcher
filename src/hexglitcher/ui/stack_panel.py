"""Op-stack panel for the selected layer: add / reorder / bypass / select ops.

Ops display in application order. A faint "DECODE" divider marks the boundary
between byte-domain ops (above) and pixel-domain ops (below).
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..engine.layer import Layer
from ..engine.operation import Operation, OpDomain
from .op_palette import OpPalette


class StackPanel(QWidget):
    opSelected = Signal(object)        # Operation or None
    changed = Signal()                 # stack/enabled mutated -> re-render
    committed = Signal()

    def __init__(self) -> None:
        super().__init__()
        self._layer: Optional[Layer] = None
        self._building = False

        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(4)

        self._list = QListWidget()
        self._list.currentItemChanged.connect(self._on_select)
        self._list.itemChanged.connect(self._on_item_changed)
        self._list.model().rowsMoved.connect(lambda *_: self._on_reorder())
        self._list.setDragDropMode(QListWidget.DragDropMode.InternalMove)
        root.addWidget(self._list, 1)

        row = QHBoxLayout()
        self._add = QPushButton("＋ Add")
        self._del = QPushButton("🗑")
        self._up = QPushButton("▲")
        self._dn = QPushButton("▼")
        for b in (self._del, self._up, self._dn):
            b.setFixedWidth(34)
        self._add.clicked.connect(self._add_op)
        self._del.clicked.connect(self._remove_op)
        self._up.clicked.connect(lambda: self._move(-1))
        self._dn.clicked.connect(lambda: self._move(1))
        row.addWidget(self._add, 1)
        row.addWidget(self._del)
        row.addWidget(self._up)
        row.addWidget(self._dn)
        root.addLayout(row)
        self.set_layer(None)

    # public -----------------------------------------------------------------
    def set_layer(self, layer: Optional[Layer]) -> None:
        self._layer = layer
        self._rebuild()
        enabled = layer is not None
        for b in (self._add, self._del, self._up, self._dn):
            b.setEnabled(enabled)

    def selected_op(self) -> Optional[Operation]:
        it = self._list.currentItem()
        if it is None:
            return None
        return it.data(Qt.ItemDataRole.UserRole)

    # internals --------------------------------------------------------------
    def _rebuild(self) -> None:
        self._building = True
        self._list.clear()
        if self._layer is not None:
            for op in self._layer.ops:
                it = QListWidgetItem(self._label(op))
                it.setData(Qt.ItemDataRole.UserRole, op)
                it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                it.setCheckState(Qt.CheckState.Checked if op.enabled else Qt.CheckState.Unchecked)
                it.setToolTip(op.optype.help)
                self._list.addItem(it)
        self._building = False

    @staticmethod
    def _label(op: Operation) -> str:
        tag = "𝙱" if op.domain is OpDomain.BYTE else "𝙿"
        return f"{tag}  {op.display_name()}"

    def _on_select(self, cur, _prev) -> None:
        self.opSelected.emit(cur.data(Qt.ItemDataRole.UserRole) if cur else None)

    def _on_item_changed(self, item: QListWidgetItem) -> None:
        if self._building:
            return
        op = item.data(Qt.ItemDataRole.UserRole)
        if op is not None:
            new_enabled = item.checkState() == Qt.CheckState.Checked
            if new_enabled != op.enabled:
                op.enabled = new_enabled
                self.changed.emit()
                self.committed.emit()

    def _on_reorder(self) -> None:
        if self._building or self._layer is None:
            return
        self._layer.ops = [self._list.item(i).data(Qt.ItemDataRole.UserRole)
                           for i in range(self._list.count())]
        self.changed.emit()
        self.committed.emit()

    def _add_op(self) -> None:
        if self._layer is None:
            return
        dlg = OpPalette(self)
        if dlg.exec() and dlg.chosen():
            op = Operation(dlg.chosen())
            # keep byte ops above pixel ops for a tidy default order
            if op.domain is OpDomain.BYTE:
                insert_at = sum(1 for o in self._layer.ops if o.domain is OpDomain.BYTE)
            else:
                insert_at = len(self._layer.ops)
            self._layer.ops.insert(insert_at, op)
            self._rebuild()
            self._select_op(op)
            self.changed.emit()
            self.committed.emit()

    def _remove_op(self) -> None:
        op = self.selected_op()
        if op and self._layer:
            self._layer.ops.remove(op)
            self._rebuild()
            self.opSelected.emit(self.selected_op())
            self.changed.emit()
            self.committed.emit()

    def _move(self, delta: int) -> None:
        op = self.selected_op()
        if not op or not self._layer:
            return
        i = self._layer.ops.index(op)
        j = i + delta
        if 0 <= j < len(self._layer.ops):
            self._layer.ops[i], self._layer.ops[j] = self._layer.ops[j], self._layer.ops[i]
            self._rebuild()
            self._select_op(op)
            self.changed.emit()
            self.committed.emit()

    def _select_op(self, op: Operation) -> None:
        for i in range(self._list.count()):
            if self._list.item(i).data(Qt.ItemDataRole.UserRole) is op:
                self._list.setCurrentRow(i)
                return
