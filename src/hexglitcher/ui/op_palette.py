"""Searchable "add operation" palette."""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
)

from ..ops import ops_by_category


class OpPalette(QDialog):
    """Pick an op type. Returns its ``type_id`` via :meth:`chosen`."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Add Operation")
        self.resize(380, 460)
        self._chosen: Optional[str] = None

        lay = QVBoxLayout(self)
        self._search = QLineEdit()
        self._search.setPlaceholderText("Search operations…  (e.g. sort, shift, jpeg)")
        self._search.textChanged.connect(self._filter)
        lay.addWidget(self._search)

        self._list = QListWidget()
        self._list.itemDoubleClicked.connect(lambda _i: self._accept())
        self._list.currentItemChanged.connect(self._update_help)
        lay.addWidget(self._list, 1)

        self._help = QLabel("")
        self._help.setObjectName("sectionHeader")
        self._help.setWordWrap(True)
        self._help.setMinimumHeight(40)
        lay.addWidget(self._help)

        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self._accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

        self._populate()
        self._search.setFocus()

    def _populate(self) -> None:
        self._list.clear()
        for category, optypes in ops_by_category().items():
            header = QListWidgetItem(f"— {category} —")
            header.setFlags(Qt.ItemFlag.NoItemFlags)
            header.setForeground(Qt.GlobalColor.gray)
            self._list.addItem(header)
            for ot in optypes:
                it = QListWidgetItem(f"   {ot.label}")
                it.setData(Qt.ItemDataRole.UserRole, ot.type_id)
                it.setData(Qt.ItemDataRole.UserRole + 1, f"{ot.label} {ot.category} {ot.type_id}".lower())
                it.setToolTip(ot.help)
                self._list.addItem(it)

    def _filter(self, text: str) -> None:
        text = text.strip().lower()
        for i in range(self._list.count()):
            it = self._list.item(i)
            tid = it.data(Qt.ItemDataRole.UserRole)
            if tid is None:  # category header
                it.setHidden(bool(text))
                continue
            hay = it.data(Qt.ItemDataRole.UserRole + 1) or ""
            it.setHidden(text not in hay)

    def _update_help(self, cur, _prev) -> None:
        if cur is None:
            self._help.setText("")
            return
        from ..engine.operation import OP_REGISTRY
        tid = cur.data(Qt.ItemDataRole.UserRole)
        self._help.setText(OP_REGISTRY[tid].help if tid in OP_REGISTRY else "")

    def _accept(self) -> None:
        cur = self._list.currentItem()
        if cur is not None and cur.data(Qt.ItemDataRole.UserRole):
            self._chosen = cur.data(Qt.ItemDataRole.UserRole)
            self.accept()

    def chosen(self) -> Optional[str]:
        return self._chosen
