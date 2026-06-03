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
    QInputDialog,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QProgressDialog,
    QSlider,
    QSplitter,
    QToolBar,
    QToolButton,
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

_OPEN_FILTER = (
    "Media (*.jpg *.jpeg *.png *.bmp *.gif *.tif *.tiff *.webp "
    "*.mp4 *.mov *.avi *.mkv *.webm *.glitch);;All files (*)"
)


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
        self._build_transport()
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
        self._a_export = act("Export", self.export_image, "Ctrl+E", "Export the result image")
        self._a_gif = act("Export GIF", self.export_gif, None, "Export a seed-sweep animation")
        self._a_save = act("Save .glitch", self.save_project, "Ctrl+S", "Save project (re-editable)")
        self._a_expvid = act("Export Video", self.export_video_action, None, "Render the glitched video (MP4)")
        tb.addSeparator()
        self._a_undo = act("↶ Undo", self.undo, "Ctrl+Z")
        self._a_redo = act("↷ Redo", self.redo, "Ctrl+Y")
        tb.addSeparator()
        self._a_surprise = act("🎲 Surprise", self.surprise_me, "Ctrl+R", "Random glitch stack")
        # Looks menu (curated preset stacks)
        from .. import presets
        self._looks_btn = QToolButton()
        self._looks_btn.setText("✨ Looks")
        self._looks_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        looks_menu = QMenu(self._looks_btn)
        for name in presets.look_names():
            a = looks_menu.addAction(name)
            a.triggered.connect(lambda checked=False, n=name: self._apply_look(n))
        self._looks_btn.setMenu(looks_menu)
        tb.addWidget(self._looks_btn)
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

    # ── video transport ──────────────────────────────────────────────────────
    def _build_transport(self) -> None:
        self._video_fps_val = 24.0
        self._transport = QToolBar("Transport", self)
        self._transport.setMovable(False)
        self.addToolBar(Qt.ToolBarArea.BottomToolBarArea, self._transport)
        self._play_btn = QToolButton()
        self._play_btn.setText("▶")
        self._play_btn.setCheckable(True)
        self._play_btn.toggled.connect(self._toggle_play)
        self._transport.addWidget(self._play_btn)
        self._frame_slider = QSlider(Qt.Orientation.Horizontal)
        self._frame_slider.setMinimumWidth(320)
        self._frame_slider.valueChanged.connect(self._on_frame_changed)
        self._transport.addWidget(self._frame_slider)
        self._frame_lbl = QLabel("0 / 0")
        self._transport.addWidget(self._frame_lbl)
        self._play_timer = QTimer(self)
        self._play_timer.timeout.connect(self._advance_frame)
        self._transport.setVisible(False)

    def _setup_transport_for(self, doc: Document) -> None:
        if self._play_btn.isChecked():
            self._play_btn.setChecked(False)
        is_vid = doc.is_video()
        self._transport.setVisible(is_vid)
        if is_vid:
            n = doc.frame_count()
            doc.frame = 0
            self._frame_slider.blockSignals(True)
            self._frame_slider.setRange(0, max(0, n - 1))
            self._frame_slider.setValue(0)
            self._frame_slider.blockSignals(False)
            self._frame_lbl.setText(f"0 / {max(0, n - 1)}")

    def _on_frame_changed(self, i: int) -> None:
        if self.doc is None:
            return
        self.doc.frame = int(i)
        self._frame_lbl.setText(f"{i} / {max(0, self.doc.frame_count() - 1)}")
        self._render(proxy=True)

    def _toggle_play(self, on: bool) -> None:
        if on and self.doc is not None and self.doc.is_video():
            self._play_btn.setText("⏸")
            self._play_timer.start(int(1000 / max(1.0, self._video_fps_val)))
        else:
            self._play_btn.setText("▶")
            self._play_timer.stop()

    def _advance_frame(self) -> None:
        if self.doc is None:
            return
        n = self.doc.frame_count()
        self._frame_slider.setValue((self.doc.frame + 1) % max(1, n))

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
        if path.lower().endswith(".glitch"):
            self.load_project(path)
            return
        from ..engine.video import SourceVideo, is_video
        if is_video(path):
            try:
                vid = SourceVideo.from_file(path)
            except Exception as e:
                QMessageBox.critical(self, "Open failed", str(e))
                return
            if vid.read_rgb(0) is None:
                QMessageBox.warning(self, "Unsupported", "Could not read that video.")
                return
            self._video_fps_val = vid.fps
            self._install_document(Document.from_video(vid))
            return
        try:
            src = SourceImage.from_file(path)
        except Exception as e:
            QMessageBox.critical(self, "Open failed", str(e))
            return
        if src.clean_decoded() is None:
            QMessageBox.warning(self, "Unsupported", "Could not decode that image.")
            return
        self._install_document(Document.from_source(src))

    def _install_document(self, doc: Document) -> None:
        """Make `doc` the active document and refresh all panels + preview."""
        self._worker.clear_cache()
        self.doc = doc
        base = doc.base_source
        clean = base.clean_decoded() if base else None
        self.canvas.set_original(ndarray_to_qimage(clean) if clean is not None else None)
        self.canvas._has_image = False  # force re-fit on first render
        self.layers.set_document(doc)
        idx = self.layers.current_doc_index()
        self.stack.set_layer(doc.layers[idx] if 0 <= idx < len(doc.layers) else None)
        self.params.set_operation(None)
        self._undo = [copy.deepcopy(doc.layers)]
        self._redo = []
        self._setup_transport_for(doc)
        w, h = doc.canvas_size()
        kind = f"video · {doc.frame_count()}f" if doc.is_video() else f"{len(doc.layers)} layer(s)"
        self._sb_info.setText(f"{doc.name}  ·  {w}×{h}  ·  {kind}")
        self._update_actions_enabled()
        self._render(proxy=False)

    def load_project(self, path: str) -> None:
        from ..io.recipe import load_project as _load
        try:
            doc = _load(path)
        except Exception as e:
            QMessageBox.critical(self, "Open failed", str(e))
            return
        # Security: a .glitch can reference arbitrary external files via Inject
        # ops (their bytes get baked into the result). Warn and let the user drop
        # the references unless they trust the project.
        refs = [op.params.get("source", "") for layer in doc.layers for op in layer.ops
                if op.type_id == "byte.inject" and (op.params.get("source") or "").strip()]
        if refs:
            shown = "\n  ".join(refs[:6]) + ("\n  …" if len(refs) > 6 else "")
            keep = QMessageBox.question(
                self, "External file references",
                "This project reads these external files via Inject ops:\n  "
                f"{shown}\n\nOnly keep them if you trust this project. Keep the references?",
            ) == QMessageBox.StandardButton.Yes
            if not keep:
                for layer in doc.layers:
                    for op in layer.ops:
                        if op.type_id == "byte.inject":
                            op.params["source"] = ""
        self._install_document(doc)

    def save_project(self) -> None:
        if self.doc is None:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Project", "glitch.glitch", "HexGlitcher project (*.glitch)")
        if not path:
            return
        from ..io.recipe import save_project
        try:
            save_project(self.doc, path)
            self._sb_render.setText(f"saved {os.path.basename(path)}")
        except Exception as e:
            QMessageBox.critical(self, "Save failed", str(e))

    def export_gif(self) -> None:
        if self.doc is None:
            return
        frames, ok = QInputDialog.getInt(self, "Export GIF", "Frames (seed sweep):", 16, 2, 240)
        if not ok:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export GIF", "glitch.gif", "GIF (*.gif)")
        if not path:
            return
        from ..io.export import export_animation
        try:
            n = export_animation(self.doc, path, frames=frames)
            self._sb_render.setText(f"exported {n}-frame GIF")
        except Exception as e:
            QMessageBox.critical(self, "Export failed", str(e))

    def export_video_action(self) -> None:
        if self.doc is None or not self.doc.is_video():
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export Video", "glitched.mp4", "MP4 (*.mp4)")
        if not path:
            return
        from ..engine.video import SourceVideo
        from ..io.export import export_video
        if self._play_btn.isChecked():
            self._play_btn.setChecked(False)
        n = self.doc.frame_count()
        dlg = QProgressDialog("Rendering glitched video…", "Cancel", 0, n, self)
        dlg.setWindowModality(Qt.WindowModality.WindowModal)
        dlg.setMinimumDuration(0)
        dlg.setValue(0)
        state = {"cancel": False}

        def prog(i, total):
            dlg.setValue(i)
            QApplication.processEvents()
            if dlg.wasCanceled():
                state["cancel"] = True
                raise RuntimeError("cancelled")

        audio = next((s.path for s in self.doc.sources.values()
                      if isinstance(s, SourceVideo)), None)
        try:
            cnt = export_video(self.doc, path, fps=self._video_fps_val,
                               audio_from=audio, progress=prog)
            self._sb_render.setText(f"exported {cnt}-frame video")
        except Exception as e:
            if not state["cancel"]:
                QMessageBox.critical(self, "Export failed", str(e))
        finally:
            dlg.close()

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

    def _apply_look(self, name: str) -> None:
        if self.doc is None:
            return
        from .. import presets
        presets.apply_look(self.doc, name)
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
        for a in (self._a_export, self._a_surprise, self._a_save, self._a_gif, self._looks_btn):
            a.setEnabled(has)
        self._a_expvid.setEnabled(has and self.doc.is_video())
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
