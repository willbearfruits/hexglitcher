"""Export-GIF dialog — choose seed vs parameter sweep, frames, fps, loop, size."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QSpinBox,
)

from ..engine.document import Document

_SIZES = [("256 px (small)", 256), ("360 px", 360), ("480 px", 480),
          ("640 px", 640), ("Native (large)", None)]
_LOOPS = [("Forever", "forever"), ("Ping-pong", "pingpong"), ("Once", "once")]


def _numeric_params(doc: Document):
    """Sweepable params across the stack: [(label, layer_idx, op_uid, key, spec), ...]."""
    out = []
    for li, layer in enumerate(doc.layers):
        for op in layer.ops:
            for spec in op.optype.params:
                if spec.kind in ("int", "float") and spec.min is not None and spec.max is not None:
                    out.append((f"L{li} · {op.display_name()} · {spec.label}",
                                li, op.uid, spec.key, spec))
    return out


class GifExportDialog(QDialog):
    def __init__(self, doc: Document, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Export GIF")
        self.setMinimumWidth(440)
        self._params = _numeric_params(doc)

        self._form = QFormLayout(self)

        self._mode = QComboBox()
        self._mode.addItem("Seed sweep — random variation", "seed")
        if self._params:
            self._mode.addItem("Parameter sweep — smooth motion", "param")
        self._mode.currentIndexChanged.connect(self._sync_mode)
        self._form.addRow("Animate", self._mode)

        self._param = QComboBox()
        for label, *_ in self._params:
            self._param.addItem(label)
        self._param.currentIndexChanged.connect(self._sync_param)
        self._start = QDoubleSpinBox()
        self._end = QDoubleSpinBox()
        self._form.addRow("Parameter", self._param)
        self._form.addRow("From", self._start)
        self._form.addRow("To", self._end)

        self._frames = QSpinBox(); self._frames.setRange(2, 240); self._frames.setValue(24)
        self._form.addRow("Frames", self._frames)
        self._fps = QSpinBox(); self._fps.setRange(1, 50); self._fps.setValue(12)
        self._form.addRow("FPS", self._fps)
        self._loop = QComboBox()
        for label, val in _LOOPS:
            self._loop.addItem(label, val)
        self._form.addRow("Loop", self._loop)
        self._size = QComboBox()
        for label, val in _SIZES:
            self._size.addItem(label, val)
        self._size.setCurrentIndex(2)                 # 480 px default
        self._form.addRow("Max size", self._size)
        self._dither = QCheckBox("Dither (smoother gradients)")
        self._dither.setChecked(True)
        self._form.addRow("", self._dither)

        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        self._form.addRow(bb)

        if self._params:
            self._sync_param(0)
        self._sync_mode()

    def _sync_mode(self) -> None:
        is_param = self._mode.currentData() == "param"
        for w in (self._param, self._start, self._end):
            self._form.setRowVisible(w, is_param)

    def _sync_param(self, idx: int) -> None:
        if not self._params or idx < 0:
            return
        spec = self._params[idx][4]
        for sb in (self._start, self._end):
            sb.setDecimals(0 if spec.kind == "int" else 3)
            sb.setRange(float(spec.min), float(spec.max))
            sb.setSingleStep(float(spec.step or 1))
        self._start.setValue(float(spec.min))
        self._end.setValue(float(spec.max))

    def options(self) -> dict:
        opts = {
            "frames": self._frames.value(),
            "fps": self._fps.value(),
            "loop": self._loop.currentData(),
            "max_dim": self._size.currentData(),
            "dither": self._dither.isChecked(),
            "sweep": None,
        }
        if self._mode.currentData() == "param" and self._params:
            _, li, op_uid, key, _ = self._params[self._param.currentIndex()]
            opts["sweep"] = {"layer": li, "op_uid": op_uid, "param": key,
                             "start": self._start.value(), "end": self._end.value()}
        return opts
