"""The main window: docks, toolbar, the debounced render controller, undo, I/O."""
from __future__ import annotations

import copy
import os
from typing import Optional

from PySide6.QtCore import Qt, QThread, QTimer, Signal
from PySide6.QtGui import QAction, QImage, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QDockWidget,
    QFileDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QSplitter,
    QWidget,
    QVBoxLayout,
)

from ..engine.document import Document
from ..engine.layer import SourceImage
from ..ops import register_builtin_ops
from ..render.worker import RenderWorker, ndarray_to_qimage
from .canvas import CanvasView
from .layers_panel import LayersPanel
from .params_panel import ParamsPanel
from .stack_panel import StackPanel

_OPEN_FILTER = "Images (*.jpg *.jpeg *.png *.bmp *.gif *.tif *.tiff *.webp);;All files (*)"


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        register_builtin_ops()
        self.setWindowTitle("HexGlitcher v3")
        self.resize(1320, 840)
        self.setAcceptDrops(True)

        self.doc: Optional[Document] = None
        self._last_shown = 0
        self._undo: list = []
        self._redo: list = []

        self._setup_worker()
        self._build_central()
        self._build_docks()
        self._build_actions()
        self._build_status()
        self._setup_timers()
        self._update_actions_enabled()

    # ── worker thread ──────────────────────────────────────────────────────
    def _setup_worker(self) -> None:
        self._thread = QThread(self)
        self._worker = RenderWorker()
        self._worker.moveToThread(self._thread)
        self._worker.previewReady.connect(self._on_preview)
        self._worker.renderFailed.connect(self._on_failed)
        self._thread.start()

    # ── layout ─────────────────────────────────────────────────────────────
    def _build_central(self) -> None:
        self.canvas = CanvasView()
        self.setCentralWidget(self.canvas)

    def _build_docks(self) -> None:
        self.layers = LayersPanel()
        left = QDockWidget("Layers", self)
        left.setWidget(self.layers)
        left.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetMovable |
                         QDockWidget.DockWidgetFeature.DockWidgetFloatable)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, left)

        self.stack = StackPanel()
        self.params = ParamsPanel()
        right_split = QSplitter(Qt.Orientation.Vertical)
        right_split.addWidget(self.stack)
        right_split.addWidget(self.params)
        right_split.setSizes([300, 460])
        right_host = QWidget()
        rl = QVBoxLayout(right_host)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.addWidget(right_split)
        right = QDockWidget("Effects", self)
        right.setWidget(right_host)
        right.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetMovable |
                          QDockWidget.DockWidgetFeature.DockWidgetFloatable)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, right)
        self.resizeDocks([left, right], [250, 320], Qt.Orientation.Horizontal)

        # wiring
        self.layers.layerSelected.connect(self._on_layer_selected)
        self.layers.changed.connect(lambda: self._schedule())
        self.layers.committed.connect(self._on_committed)
        self.stack.opSelected.connect(self.params.set_operation)
        self.stack.changed.connect(lambda: self._schedule())
        self.stack.committed.connect(self._on_committed)
        self.params.changed.connect(lambda: self._schedule())
        self.params.committed.connect(self._on_committed)

    def _build_actions(self) -> None:
        tb = self.addToolBar("Main")
        tb.setMovable(False)

        def act(text, slot, shortcut=None, tip=""):
            a = QAction(text, self)
            if shortcut:
                a.setShortcut(QKeySequence(shortcut))
            a.triggered.connect(slot)
            a.setToolTip(tip or text)
            tb.addAction(a)
            return a

        self._a_open = act("Open", self.open_image, "Ctrl+O", "Open an image")
        self._a_export = act("Export", self.export_image, "Ctrl+E", "Export the result")
        tb.addSeparator()
        self._a_undo = act("↶ Undo", self.undo, "Ctrl+Z")
        self._a_redo = act("↷ Redo", self.redo, "Ctrl+Y")
        tb.addSeparator()
        self._a_surprise = act("🎲 Surprise", self.surprise_me, "Ctrl+R", "Random glitch stack")
        tb.addSeparator()
        act("Fit", self.canvas.fit, "Ctrl+0", "Fit to window")
        act("100%", self.canvas.actual_size, "Ctrl+1", "Actual size")

    def _build_status(self) -> None:
        self._sb_info = QLabel("Open an image to begin")
        self._sb_render = QLabel("")
        self._sb_zoom = QLabel("")
        self.statusBar().addWidget(self._sb_info, 1)
        self.statusBar().addPermanentWidget(self._sb_render)
        self.statusBar().addPermanentWidget(self._sb_zoom)

    def _setup_timers(self) -> None:
        self._proxy_timer = QTimer(self)
        self._proxy_timer.setSingleShot(True)
        self._proxy_timer.setInterval(45)
        self._proxy_timer.timeout.connect(lambda: self._render(proxy=True))
        self._full_timer = QTimer(self)
        self._full_timer.setSingleShot(True)
        self._full_timer.setInterval(280)
        self._full_timer.timeout.connect(lambda: self._render(proxy=False))

    # ── document lifecycle ──────────────────────────────────────────────────
    def open_image(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Open Image", "", _OPEN_FILTER)
        if path:
            self.load_path(path)

    def load_path(self, path: str) -> None:
        try:
            src = SourceImage.from_file(path)
        except Exception as e:
            QMessageBox.critical(self, "Open failed", str(e))
            return
        if src.clean_decoded() is None:
            QMessageBox.warning(self, "Unsupported", "Could not decode that image.")
            return
        self._worker.clear_cache()
        self.doc = Document.from_source(src)
        # the un-glitched base, for hold-to-compare
        clean = src.clean_decoded()
        self.canvas.set_original(ndarray_to_qimage(clean))
        self.canvas._has_image = False  # force re-fit on first render
        self.layers.set_document(self.doc)
        self.stack.set_layer(self.doc.layers[self.layers.current_doc_index()] if self.doc.layers else None)
        self.params.set_operation(None)
        self._undo = [copy.deepcopy(self.doc.layers)]
        self._redo = []
        w, h = self.doc.canvas_size()
        self._sb_info.setText(f"{src.name}  ·  {src.fmt.name.upper()}  ·  {w}×{h}  ·  {len(src.data):,} B")
        self._update_actions_enabled()
        self._render(proxy=False)

    # ── render controller ────────────────────────────────────────────────────
    def _schedule(self) -> None:
        if self.doc is None:
            return
        self._proxy_timer.start()
        self._full_timer.start()

    def _on_committed(self) -> None:
        self._push_history()
        self._schedule()

    def _proxy_dim(self) -> int:
        vp = self.canvas.viewport().size()
        return max(256, min(1600, max(vp.width(), vp.height())))

    def _render(self, proxy: bool) -> None:
        if self.doc is None:
            return
        if proxy:
            self._full_timer.start()  # ensure a full pass still follows
        dim = self._proxy_dim() if proxy else None
        self._sb_render.setText("● rendering…")
        self._worker.submit(self.doc.snapshot(), dim)

    def _on_preview(self, qimg: QImage, rid: int, ok: bool) -> None:
        if rid < self._last_shown:
            return
        self._last_shown = rid
        self.canvas.set_image(qimg, self.doc.canvas_size() if self.doc else None)
        self._sb_render.setText("" if ok else "⚠ decode fell back to original")
        self._sb_zoom.setText(f"{self.canvas.zoom_percent()}%")

    def _on_failed(self, rid: int) -> None:
        self._sb_render.setText("⚠ render failed")

    # ── undo / redo ───────────────────────────────────────────────────────────
    def _push_history(self) -> None:
        if self.doc is None:
            return
        self._undo.append(copy.deepcopy(self.doc.layers))
        self._redo.clear()
        if len(self._undo) > 100:
            self._undo.pop(0)
        self._update_actions_enabled()

    def undo(self) -> None:
        if self.doc is None or len(self._undo) < 2:
            return
        self._redo.append(self._undo.pop())
        self.doc.layers = copy.deepcopy(self._undo[-1])
        self._refresh_after_state_change()

    def redo(self) -> None:
        if self.doc is None or not self._redo:
            return
        state = self._redo.pop()
        self._undo.append(state)
        self.doc.layers = copy.deepcopy(state)
        self._refresh_after_state_change()

    def _refresh_after_state_change(self) -> None:
        self.layers.set_document(self.doc)
        idx = self.layers.current_doc_index()
        self.stack.set_layer(self.doc.layers[idx] if 0 <= idx < len(self.doc.layers) else None)
        self.params.set_operation(None)
        self._update_actions_enabled()
        self._render(proxy=False)

    # ── panel callbacks ────────────────────────────────────────────────────────
    def _on_layer_selected(self, idx: int) -> None:
        if self.doc and 0 <= idx < len(self.doc.layers):
            self.stack.set_layer(self.doc.layers[idx])
        else:
            self.stack.set_layer(None)
        self.params.set_operation(self.stack.selected_op())

    # ── surprise / export ──────────────────────────────────────────────────────
    def surprise_me(self) -> None:
        if self.doc is None:
            return
        from .. import presets
        presets.apply_surprise(self.doc)
        self._refresh_after_state_change()
        self._push_history()

    def export_image(self) -> None:
        if self.doc is None:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Image", "glitched.png",
            "PNG (*.png);;JPEG (*.jpg);;WebP (*.webp);;TIFF (*.tif)")
        if not path:
            return
        from ..io.export import export_document
        try:
            export_document(self.doc, path)
            self._sb_render.setText(f"exported {os.path.basename(path)}")
        except Exception as e:
            QMessageBox.critical(self, "Export failed", str(e))

    def _update_actions_enabled(self) -> None:
        has = self.doc is not None
        for a in (self._a_export, self._a_surprise):
            a.setEnabled(has)
        self._a_undo.setEnabled(has and len(self._undo) >= 2)
        self._a_redo.setEnabled(has and bool(self._redo))

    # ── compare (hold backslash) ────────────────────────────────────────────────
    def keyPressEvent(self, e) -> None:  # noqa: N802
        if e.key() == Qt.Key.Key_Backslash and not e.isAutoRepeat():
            self.canvas.set_compare(True)
        else:
            super().keyPressEvent(e)

    def keyReleaseEvent(self, e) -> None:  # noqa: N802
        if e.key() == Qt.Key.Key_Backslash and not e.isAutoRepeat():
            self.canvas.set_compare(False)
        else:
            super().keyReleaseEvent(e)

    # ── drag & drop ──────────────────────────────────────────────────────────────
    def dragEnterEvent(self, e) -> None:  # noqa: N802
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e) -> None:  # noqa: N802
        for url in e.mimeData().urls():
            p = url.toLocalFile()
            if p:
                self.load_path(p)
                break

    # ── shutdown ───────────────────────────────────────────────────────────────
    def closeEvent(self, e) -> None:  # noqa: N802
        self._thread.quit()
        self._thread.wait(2000)
        super().closeEvent(e)
