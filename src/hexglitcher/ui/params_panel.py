"""Contextual parameter editor — widgets generated automatically from ParamSpec.

Bind it to an :class:`Operation` and it renders a slider+spinbox / combo / checkbox
per parameter, writing edits straight back into ``op.params`` and emitting
:attr:`changed` so the controller can re-render (debounced).
"""
from __future__ import annotations

import secrets
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ..engine.operation import Operation, ParamSpec

_FLOAT_STEPS = 1000


class ParamsPanel(QWidget):
    changed = Signal()             # a parameter value changed (re-render)
    committed = Signal()           # interaction ended (request full-res)

    def __init__(self) -> None:
        super().__init__()
        self._op: Optional[Operation] = None
        self._building = False

        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(4)

        self._title = QLabel("No operation selected")
        self._title.setObjectName("sectionHeader")
        root.addWidget(self._title)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self._form_host = QWidget()
        self._form = QFormLayout(self._form_host)
        self._form.setContentsMargins(2, 2, 2, 2)
        self._form.setSpacing(8)
        self._scroll.setWidget(self._form_host)
        root.addWidget(self._scroll, 1)

        btns = QHBoxLayout()
        self._reset_btn = QPushButton("Reset")
        self._rand_btn = QPushButton("🎲 Randomize")
        self._reset_btn.clicked.connect(self._reset)
        self._rand_btn.clicked.connect(self._randomize)
        btns.addWidget(self._reset_btn)
        btns.addWidget(self._rand_btn)
        root.addLayout(btns)
        self._set_enabled(False)

    def _set_enabled(self, on: bool) -> None:
        self._reset_btn.setEnabled(on)
        self._rand_btn.setEnabled(on)

    # public -----------------------------------------------------------------
    def set_operation(self, op: Optional[Operation]) -> None:
        self._op = op
        self._clear()
        if op is None:
            self._title.setText("No operation selected")
            self._set_enabled(False)
            return
        ot = op.optype
        self._title.setText(f"{ot.label}  ·  {ot.category}")
        self._set_enabled(True)
        self._building = True
        for spec in ot.params:
            self._form.addRow(spec.label, self._build_widget(spec))
        self._building = False

    def refresh(self) -> None:
        """Re-read values from the op into the widgets (after randomize/reset)."""
        if self._op is not None:
            self.set_operation(self._op)

    # internals --------------------------------------------------------------
    def _clear(self) -> None:
        while self._form.rowCount():
            self._form.removeRow(0)

    def _emit_changed(self) -> None:
        if not self._building:
            self.changed.emit()

    def _build_widget(self, spec: ParamSpec) -> QWidget:
        kind = spec.kind
        if kind in ("int", "seed"):
            return self._int_widget(spec)
        if kind == "float":
            return self._float_widget(spec)
        if kind == "bool":
            return self._bool_widget(spec)
        if kind == "choice":
            return self._choice_widget(spec)
        return self._fallback_widget(spec)

    def _int_widget(self, spec: ParamSpec) -> QWidget:
        host = QWidget()
        lay = QHBoxLayout(host)
        lay.setContentsMargins(0, 0, 0, 0)
        spin = QSpinBox()
        spin.setRange(int(spec.min if spec.min is not None else -2_000_000_000),
                      int(spec.max if spec.max is not None else 2_000_000_000))
        spin.setSingleStep(int(spec.step or 1))
        spin.setValue(int(self._op.params[spec.key]))
        slider = QSlider(Qt.Orientation.Horizontal)
        has_range = spec.min is not None and spec.max is not None
        if has_range:
            slider.setRange(int(spec.min), int(spec.max))
            slider.setValue(int(self._op.params[spec.key]))
            slider.valueChanged.connect(spin.setValue)
            spin.valueChanged.connect(slider.setValue)
            lay.addWidget(slider, 1)
        else:
            slider.hide()
        if spec.help:
            spin.setToolTip(spec.help)
            slider.setToolTip(spec.help)

        def on_change(v):
            self._op.params[spec.key] = int(v)
            self._emit_changed()

        spin.valueChanged.connect(on_change)
        if has_range:
            slider.sliderReleased.connect(lambda: self.committed.emit())
        lay.addWidget(spin)
        return host

    def _float_widget(self, spec: ParamSpec) -> QWidget:
        host = QWidget()
        lay = QHBoxLayout(host)
        lay.setContentsMargins(0, 0, 0, 0)
        lo = spec.min if spec.min is not None else 0.0
        hi = spec.max if spec.max is not None else 1.0
        spin = QDoubleSpinBox()
        spin.setRange(lo, hi)
        spin.setDecimals(3)
        spin.setSingleStep(spec.step or 0.01)
        spin.setValue(float(self._op.params[spec.key]))
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(0, _FLOAT_STEPS)

        def to_slider(val):
            return int(round((val - lo) / (hi - lo) * _FLOAT_STEPS)) if hi > lo else 0

        def to_val(s):
            return lo + (s / _FLOAT_STEPS) * (hi - lo)

        slider.setValue(to_slider(float(self._op.params[spec.key])))
        if spec.help:
            spin.setToolTip(spec.help)
            slider.setToolTip(spec.help)

        def on_slider(s):
            if self._building:
                return
            spin.blockSignals(True)
            spin.setValue(to_val(s))
            spin.blockSignals(False)
            self._op.params[spec.key] = to_val(s)
            self._emit_changed()

        def on_spin(v):
            slider.blockSignals(True)
            slider.setValue(to_slider(v))
            slider.blockSignals(False)
            self._op.params[spec.key] = float(v)
            self._emit_changed()

        slider.valueChanged.connect(on_slider)
        spin.valueChanged.connect(on_spin)
        slider.sliderReleased.connect(lambda: self.committed.emit())
        lay.addWidget(slider, 1)
        lay.addWidget(spin)
        return host

    def _bool_widget(self, spec: ParamSpec) -> QWidget:
        cb = QCheckBox()
        cb.setChecked(bool(self._op.params[spec.key]))
        if spec.help:
            cb.setToolTip(spec.help)

        def on_toggle(state):
            self._op.params[spec.key] = bool(state)
            self._emit_changed()
            self.committed.emit()

        cb.toggled.connect(on_toggle)
        return cb

    def _choice_widget(self, spec: ParamSpec) -> QWidget:
        combo = QComboBox()
        combo.addItems([str(c) for c in (spec.choices or ())])
        cur = str(self._op.params[spec.key])
        i = combo.findText(cur)
        if i >= 0:
            combo.setCurrentIndex(i)
        if spec.help:
            combo.setToolTip(spec.help)

        def on_change(text):
            self._op.params[spec.key] = text
            self._emit_changed()
            self.committed.emit()

        combo.currentTextChanged.connect(on_change)
        return combo

    def _fallback_widget(self, spec: ParamSpec) -> QWidget:
        from PySide6.QtWidgets import QLineEdit
        edit = QLineEdit(str(self._op.params[spec.key]))

        def on_change(text):
            self._op.params[spec.key] = text
            self._emit_changed()

        edit.editingFinished.connect(lambda: (on_change(edit.text()), self.committed.emit()))
        return edit

    # buttons ----------------------------------------------------------------
    def _reset(self) -> None:
        if self._op is None:
            return
        self._op.params = self._op.optype.default_params()
        self.refresh()
        self.changed.emit()
        self.committed.emit()

    def _randomize(self) -> None:
        if self._op is None:
            return
        for spec in self._op.optype.params:
            if spec.kind in ("int", "seed") and spec.min is not None and spec.max is not None:
                self._op.params[spec.key] = secrets.randbelow(int(spec.max) - int(spec.min) + 1) + int(spec.min)
            elif spec.kind == "float" and spec.min is not None and spec.max is not None:
                self._op.params[spec.key] = spec.min + secrets.randbelow(1000) / 1000.0 * (spec.max - spec.min)
            elif spec.kind == "choice" and spec.choices:
                self._op.params[spec.key] = spec.choices[secrets.randbelow(len(spec.choices))]
        self.refresh()
        self.changed.emit()
        self.committed.emit()
