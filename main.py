"""
HexGlitcher v2.0 — Pure hex-level databending.

Architecture guarantee: Pillow is ONLY used to decode bytes for display
(Image.open -> thumbnail -> ImageTk.PhotoImage). It never writes back to
any bytearray. All visual output is the result of raw byte manipulation.
"""

import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from PIL import Image, ImageTk
import io
import random
import os
import sys
import logging
import threading
import queue as queue_module
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Dict, Tuple, List, Callable


# ── Logging ───────────────────────────────────────────────────────────────────

def _get_log_path() -> Path:
    if sys.platform == "win32":
        log_dir = Path(os.environ.get("APPDATA", Path.home())) / "HexGlitcher"
    elif sys.platform == "darwin":
        log_dir = Path.home() / "Library" / "Logs" / "HexGlitcher"
    else:
        xdg = os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local" / "state"))
        log_dir = Path(xdg) / "hexglitcher"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir / "hexglitcher.log"


logging.basicConfig(
    filename=str(_get_log_path()),
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)

Image.MAX_IMAGE_PIXELS = 50_000_000


# ── Constants ─────────────────────────────────────────────────────────────────

ALLOWED_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp",
    ".tiff", ".tif", ".tga", ".pcx", ".raw", ".bin",
}
MAX_FILE_SIZE = 100 * 1024 * 1024
PREVIEW_SIZE = (640, 480)
HEX_BYTES_PER_ROW = 16
HEX_ROWS_PER_PAGE = 256   # 4096 bytes visible at once
HISTORY_MAX = 50

FORMAT_HEADER_SIZES: Dict[str, int] = {
    ".jpg": 600, ".jpeg": 600,
    ".png": 33,
    ".bmp": 54,
    ".gif": 13,
    ".webp": 30,
    ".tiff": 256, ".tif": 256,
    ".tga": 18,
    ".pcx": 128,
    ".raw": 0, ".bin": 0,
}

# Colour palette
BG         = "#111114"
BG_RAISED  = "#1a1a1f"
BG_INPUT   = "#0d0d10"
BORDER     = "#2a2a32"
FG         = "#d8d4cc"
FG_DIM     = "#6a6870"
ACCENT     = "#e8a030"
ACCENT_DIM = "#3a2808"
CYAN       = "#28b8c8"
CHANGED_FG = "#ffaa00"
CHANGED_BG = "#2a1800"
HEADER_FG  = "#664444"
REGION_BG  = "#001a2a"
REGION_FG  = "#00aaff"


# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class HistoryEntry:
    description: str
    bytes_changed: int
    range_start: int
    range_old: bytes
    range_new: bytes


@dataclass
class SavedState:
    data: bytearray
    label: str
    thumbnail: Optional[object] = field(default=None, repr=False)  # ImageTk.PhotoImage


# ── Helpers ───────────────────────────────────────────────────────────────────

def _safe_thumbnail(data: bytearray, size: Tuple[int, int]) -> Optional[object]:
    """Decode bytes to a thumbnail PhotoImage, or None if corrupt."""
    try:
        stream = io.BytesIO(data)
        with Image.open(stream) as img:
            img.load()
            img.thumbnail(size, Image.Resampling.LANCZOS)
            return ImageTk.PhotoImage(img)
    except Exception:
        return None


def _count_diff(a: bytes, b: bytes) -> int:
    return sum(x != y for x, y in zip(a, b)) + abs(len(a) - len(b))


# ── Hex Viewer ────────────────────────────────────────────────────────────────

class HexViewerFrame(ttk.Frame):
    """Three-column hex dump: offset | hex bytes | ASCII. Changed bytes highlighted."""

    MONO = ("Consolas", 9) if sys.platform == "win32" else ("Courier New", 9)

    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        self._original: Optional[bytearray] = None
        self._current: Optional[bytearray] = None
        self._page_offset = 0          # byte index of first displayed byte
        self._header_end = 0
        self._region_start = 0
        self._region_end = 0
        self._last_op_offset = 0
        self._build()

    def _build(self):
        nav = ttk.Frame(self)
        nav.pack(fill=tk.X, pady=(0, 2))
        ttk.Label(nav, text="Hex Viewer", foreground=FG_DIM, font=("TkDefaultFont", 8)).pack(side=tk.LEFT, padx=4)
        ttk.Button(nav, text="← Header", width=9, command=self.jump_to_header).pack(side=tk.LEFT, padx=2)
        ttk.Button(nav, text="Last Edit →", width=10, command=self.jump_to_last_edit).pack(side=tk.LEFT, padx=2)
        ttk.Button(nav, text="◀ Page", width=7, command=self._prev_page).pack(side=tk.RIGHT, padx=2)
        ttk.Button(nav, text="Page ▶", width=7, command=self._next_page).pack(side=tk.RIGHT, padx=2)
        self._page_label = ttk.Label(nav, text="", foreground=FG_DIM, font=("TkDefaultFont", 8))
        self._page_label.pack(side=tk.RIGHT, padx=6)

        self._text = tk.Text(
            self, font=self.MONO, bg=BG_INPUT, fg=FG, bd=0,
            highlightthickness=0, state=tk.DISABLED, cursor="arrow",
            selectbackground=ACCENT_DIM, selectforeground=FG,
        )
        sb = ttk.Scrollbar(self, orient=tk.VERTICAL, command=self._text.yview)
        self._text.configure(yscrollcommand=sb.set)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        self._text.pack(fill=tk.BOTH, expand=True)

        self._text.tag_configure("header",  foreground=HEADER_FG)
        self._text.tag_configure("body",    foreground=FG_DIM)
        self._text.tag_configure("changed", foreground=CHANGED_FG, background=CHANGED_BG)
        self._text.tag_configure("region",  foreground=REGION_FG, background=REGION_BG)
        self._text.tag_configure("offset",  foreground="#505060")
        self._text.tag_configure("ascii",   foreground="#808888")

    def refresh(self, original: bytearray, current: bytearray,
                header_end: int, region_start: int, region_end: int):
        self._original = original
        self._current = current
        self._header_end = header_end
        self._region_start = region_start
        self._region_end = region_end if region_end > 0 else len(current)
        self._render()

    def _render(self):
        if self._current is None:
            return
        data = self._current
        orig = self._original
        page_start = self._page_offset
        page_end = min(page_start + HEX_BYTES_PER_ROW * HEX_ROWS_PER_PAGE, len(data))
        total_pages = max(1, (len(data) + HEX_BYTES_PER_ROW * HEX_ROWS_PER_PAGE - 1)
                         // (HEX_BYTES_PER_ROW * HEX_ROWS_PER_PAGE))
        cur_page = self._page_offset // (HEX_BYTES_PER_ROW * HEX_ROWS_PER_PAGE) + 1
        self._page_label.config(text=f"pg {cur_page}/{total_pages}  offset {page_start:08X}")

        self._text.config(state=tk.NORMAL)
        self._text.delete("1.0", tk.END)

        for row_start in range(page_start, page_end, HEX_BYTES_PER_ROW):
            row_end = min(row_start + HEX_BYTES_PER_ROW, page_end)
            row_bytes = data[row_start:row_end]
            orig_bytes = orig[row_start:row_end] if orig else row_bytes

            # Offset column
            self._text.insert(tk.END, f"{row_start:08X}  ", "offset")

            # Hex bytes
            for i, (b, ob) in enumerate(zip(row_bytes, orig_bytes)):
                abs_off = row_start + i
                hex_str = f"{b:02X} "
                if abs_off < self._header_end:
                    tag = "header"
                elif self._region_start <= abs_off < self._region_end and b != ob:
                    tag = "changed"
                elif self._region_start <= abs_off < self._region_end:
                    tag = "region"
                else:
                    tag = "body"
                self._text.insert(tk.END, hex_str, tag)

            # Padding for short rows
            pad = HEX_BYTES_PER_ROW - len(row_bytes)
            self._text.insert(tk.END, "   " * pad)
            self._text.insert(tk.END, " ")

            # ASCII column
            ascii_str = ""
            for b in row_bytes:
                ascii_str += chr(b) if 32 <= b < 127 else "."
            self._text.insert(tk.END, ascii_str + "\n", "ascii")

        self._text.config(state=tk.DISABLED)

    def _prev_page(self):
        page_size = HEX_BYTES_PER_ROW * HEX_ROWS_PER_PAGE
        self._page_offset = max(0, self._page_offset - page_size)
        self._render()

    def _next_page(self):
        if self._current is None:
            return
        page_size = HEX_BYTES_PER_ROW * HEX_ROWS_PER_PAGE
        max_off = max(0, len(self._current) - page_size)
        self._page_offset = min(max_off, self._page_offset + page_size)
        self._render()

    def jump_to_header(self):
        page_size = HEX_BYTES_PER_ROW * HEX_ROWS_PER_PAGE
        self._page_offset = (self._header_end // page_size) * page_size
        self._render()

    def jump_to_last_edit(self):
        page_size = HEX_BYTES_PER_ROW * HEX_ROWS_PER_PAGE
        self._page_offset = (self._last_op_offset // page_size) * page_size
        self._render()

    def set_last_op_offset(self, offset: int):
        self._last_op_offset = offset

    def clear(self):
        self._original = self._current = None
        self._text.config(state=tk.NORMAL)
        self._text.delete("1.0", tk.END)
        self._text.config(state=tk.DISABLED)
        self._page_label.config(text="")


# ── Iteration Strip ───────────────────────────────────────────────────────────

class IterationStrip(ttk.Frame):
    """Scrollable column of saved-state thumbnails."""

    THUMB = (72, 54)

    def __init__(self, parent, restore_cb: Callable, **kwargs):
        super().__init__(parent, **kwargs)
        self._restore_cb = restore_cb
        self._states: List[SavedState] = []
        self._widgets: List[tk.Frame] = []
        self._build()

    def _build(self):
        ttk.Label(self, text="Saved States", foreground=FG_DIM,
                  font=("TkDefaultFont", 8)).pack(anchor="w", padx=4, pady=(4, 2))

        canvas_frame = ttk.Frame(self)
        canvas_frame.pack(fill=tk.BOTH, expand=True)

        self._canvas = tk.Canvas(canvas_frame, bg=BG, bd=0, highlightthickness=0)
        sb = ttk.Scrollbar(canvas_frame, orient=tk.VERTICAL, command=self._canvas.yview)
        self._canvas.configure(yscrollcommand=sb.set)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        self._canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self._inner = tk.Frame(self._canvas, bg=BG)
        self._win_id = self._canvas.create_window((0, 0), window=self._inner, anchor="nw")
        self._inner.bind("<Configure>", lambda e: self._canvas.configure(
            scrollregion=self._canvas.bbox("all")))
        self._canvas.bind("<Configure>", lambda e: self._canvas.itemconfig(
            self._win_id, width=e.width))

        btn = ttk.Button(self, text="Save Current State", command=self._on_save_btn)
        btn.pack(fill=tk.X, padx=4, pady=4)
        self._save_btn = btn

    def _on_save_btn(self):
        # Signal to app via callback with special marker
        self._restore_cb("__save__")

    def push(self, state: SavedState):
        self._states.append(state)
        idx = len(self._states) - 1
        self._add_widget(idx)
        # Scroll to bottom
        self._canvas.after(50, lambda: self._canvas.yview_moveto(1.0))

    def _add_widget(self, idx: int):
        state = self._states[idx]
        frame = tk.Frame(self._inner, bg=BG_RAISED, relief="flat", bd=1)
        frame.pack(fill=tk.X, padx=4, pady=2)

        if state.thumbnail:
            img_lbl = tk.Label(frame, image=state.thumbnail, bg=BG_RAISED, cursor="hand2")
        else:
            img_lbl = tk.Label(frame, text="BROKEN", bg="#330000", fg="#ff4444",
                               font=("TkDefaultFont", 7), width=10, height=3)
        img_lbl.pack(side=tk.LEFT, padx=2, pady=2)

        info = tk.Frame(frame, bg=BG_RAISED)
        info.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=2)
        tk.Label(info, text=f"v{idx + 1}", fg=ACCENT, bg=BG_RAISED,
                 font=("TkDefaultFont", 8, "bold")).pack(anchor="w")
        tk.Label(info, text=state.label, fg=FG_DIM, bg=BG_RAISED,
                 font=("TkDefaultFont", 7), wraplength=80).pack(anchor="w")

        def restore(i=idx):
            self._restore_cb(i)

        def delete_state(i=idx):
            self._delete(i)

        frame.bind("<Button-1>", lambda e, i=idx: restore(i))
        img_lbl.bind("<Button-1>", lambda e, i=idx: restore(i))

        menu = tk.Menu(frame, tearoff=0, bg=BG_RAISED, fg=FG)
        menu.add_command(label="Restore this state", command=restore)
        menu.add_command(label="Delete state", command=delete_state)

        def show_menu(e, m=menu):
            m.tk_popup(e.x_root, e.y_root)

        frame.bind("<Button-3>", show_menu)
        self._widgets.append(frame)

    def _delete(self, idx: int):
        if 0 <= idx < len(self._states):
            self._states.pop(idx)
            # Rebuild all widgets
            for w in self._widgets:
                w.destroy()
            self._widgets.clear()
            for i in range(len(self._states)):
                self._add_widget(i)

    def clear(self):
        self._states.clear()
        for w in self._widgets:
            w.destroy()
        self._widgets.clear()

    def get_states(self) -> List[SavedState]:
        return list(self._states)


# ── GIF Export Dialog ─────────────────────────────────────────────────────────

class ExportGifDialog(tk.Toplevel):
    def __init__(self, parent, states: List[SavedState]):
        super().__init__(parent)
        self.title("Export Animated GIF")
        self.configure(bg=BG)
        self.resizable(False, False)
        self.grab_set()
        self._states = states
        self._check_vars: List[tk.BooleanVar] = []
        self._build(states)

    def _build(self, states: List[SavedState]):
        ttk.Label(self, text="Select frames to include:").pack(anchor="w", padx=10, pady=(10, 4))

        list_frame = ttk.Frame(self)
        list_frame.pack(fill=tk.BOTH, padx=10, pady=4)

        for i, state in enumerate(states):
            var = tk.BooleanVar(value=True)
            self._check_vars.append(var)
            row = ttk.Frame(list_frame)
            row.pack(fill=tk.X)
            ttk.Checkbutton(row, variable=var).pack(side=tk.LEFT)
            if state.thumbnail:
                lbl = tk.Label(row, image=state.thumbnail, bg=BG)
                lbl.pack(side=tk.LEFT, padx=4)
            ttk.Label(row, text=f"v{i + 1}: {state.label}").pack(side=tk.LEFT)

        sep = ttk.Separator(self, orient=tk.HORIZONTAL)
        sep.pack(fill=tk.X, padx=10, pady=6)

        params = ttk.Frame(self)
        params.pack(fill=tk.X, padx=10)

        ttk.Label(params, text="Frame delay (ms):").grid(row=0, column=0, sticky="w", pady=2)
        self._delay_var = tk.IntVar(value=200)
        ttk.Entry(params, textvariable=self._delay_var, width=8).grid(row=0, column=1, padx=6, pady=2)

        ttk.Label(params, text="Loop count (0=∞):").grid(row=1, column=0, sticky="w", pady=2)
        self._loop_var = tk.IntVar(value=0)
        ttk.Entry(params, textvariable=self._loop_var, width=8).grid(row=1, column=1, padx=6, pady=2)

        self._progress = ttk.Progressbar(self, mode="indeterminate")
        self._progress.pack(fill=tk.X, padx=10, pady=6)

        btn_row = ttk.Frame(self)
        btn_row.pack(pady=(4, 10))
        ttk.Button(btn_row, text="Export", command=self._export).pack(side=tk.LEFT, padx=6)
        ttk.Button(btn_row, text="Cancel", command=self.destroy).pack(side=tk.LEFT)

    def _export(self):
        selected = [s for s, v in zip(self._states, self._check_vars) if v.get()]
        if not selected:
            messagebox.showwarning("No frames", "Select at least one frame.", parent=self)
            return

        path = filedialog.asksaveasfilename(
            parent=self, defaultextension=".gif",
            filetypes=[("GIF", "*.gif")], title="Save Animated GIF",
        )
        if not path:
            return

        delay = max(1, self._delay_var.get())
        loop = max(0, self._loop_var.get())

        self._progress.start(10)
        self.update()

        def worker():
            frames = []
            for state in selected:
                try:
                    with Image.open(io.BytesIO(state.data)) as img:
                        img.load()
                        frames.append(img.convert("RGB"))
                except Exception:
                    continue
            return frames

        frames = worker()
        self._progress.stop()

        if not frames:
            messagebox.showerror("Export Failed",
                                 "No valid frames could be decoded.", parent=self)
            return

        try:
            frames[0].save(
                path, format="GIF", save_all=True,
                append_images=frames[1:], loop=loop,
                duration=delay, optimize=False,
            )
            messagebox.showinfo("Exported",
                                f"GIF saved: {os.path.basename(path)}\n{len(frames)} frames",
                                parent=self)
            self.destroy()
        except Exception as e:
            messagebox.showerror("Export Failed", str(e), parent=self)


# ── Main Application ──────────────────────────────────────────────────────────

class GlitchApp:
    """
    HexGlitcher v2.0 — all visual output is produced solely by raw byte
    manipulation. Pillow is used exclusively for display decoding.
    """

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("HexGlitcher v2.0 — Raw Data Bender")
        self.root.geometry("1280x800")
        self.root.minsize(900, 600)
        self.root.configure(bg=BG)

        # State
        self.original_data: Optional[bytearray] = None
        self.glitched_data: Optional[bytearray] = None
        self.file_path: Optional[str] = None
        self.file_ext: Optional[str] = None
        self._save_version: int = 1
        self._tk_image: Optional[object] = None
        self._tk_image_orig: Optional[object] = None
        self._view_mode: str = "current"   # "original", "current", "compare"

        # Region controls (IntVars shared with right panel UI)
        self.header_size = tk.IntVar(value=500)
        self.region_start = tk.IntVar(value=500)
        self.region_end = tk.IntVar(value=0)   # 0 = EOF

        # History
        self._history: deque[HistoryEntry] = deque(maxlen=HISTORY_MAX)
        self._redo_stack: List[HistoryEntry] = []
        self._last_op_offset: int = 0

        # Batch
        self._batch_cancel = threading.Event()
        self._batch_queue: queue_module.Queue = queue_module.Queue()
        self._batch_running: bool = False

        # Build UI
        self.setup_styles()
        self._build_menubar()
        self._build_toolbar()
        self._build_main_layout()
        self._build_status_bar()
        self._set_controls_enabled(False)
        self._update_status("Ready — open an image to begin")

        # Shortcuts
        self.root.bind("<Control-o>", lambda _e: self.load_image())
        self.root.bind("<Control-s>", lambda _e: self.save_image())
        self.root.bind("<Control-S>", lambda _e: self.save_next_version())
        self.root.bind("<Control-z>", lambda _e: self.undo())
        self.root.bind("<Control-y>", lambda _e: self.redo())
        self.root.bind("<Control-Return>", lambda _e: self.apply_operation())
        self.root.bind("<Control-b>", lambda _e: self.run_batch())
        self.root.bind("<Control-h>", lambda _e: self._toggle_hex_viewer())
        self.root.bind("<Control-1>", lambda _e: self._set_view("original"))
        self.root.bind("<Control-2>", lambda _e: self._set_view("current"))
        self.root.bind("<Control-3>", lambda _e: self._set_view("compare"))
        self.root.bind("<F5>", lambda _e: self.refresh_ui())

        logging.info("GlitchApp v2.0 initialized")

    # ── Styles ────────────────────────────────────────────────────────────────

    def setup_styles(self) -> None:
        style = ttk.Style()
        style.theme_use("clam")
        style.configure(".", background=BG, foreground=FG, borderwidth=0)
        style.configure("TFrame", background=BG)
        style.configure("TLabel", background=BG, foreground=FG)
        style.configure("TLabelframe", background=BG, foreground=FG)
        style.configure("TLabelframe.Label", background=BG, foreground=FG_DIM,
                        font=("TkDefaultFont", 8))
        style.configure("TButton", background=BG_RAISED, foreground=FG,
                        borderwidth=1, relief="flat", padding=(6, 3))
        style.map("TButton",
                  background=[("active", ACCENT_DIM), ("pressed", ACCENT_DIM)],
                  foreground=[("active", ACCENT)])
        style.configure("Accent.TButton", background=ACCENT_DIM, foreground=ACCENT,
                        font=("TkDefaultFont", 9, "bold"))
        style.map("Accent.TButton",
                  background=[("active", "#4a3010")])
        style.configure("TNotebook", background=BG, tabmargins=[2, 2, 2, 0])
        style.configure("TNotebook.Tab", background=BG_RAISED, foreground=FG_DIM,
                        padding=[8, 3])
        style.map("TNotebook.Tab",
                  background=[("selected", BG)],
                  foreground=[("selected", ACCENT)])
        style.configure("TEntry", fieldbackground=BG_INPUT, foreground=FG,
                        insertcolor=FG, borderwidth=1)
        style.configure("TCheckbutton", background=BG, foreground=FG)
        style.configure("TRadiobutton", background=BG, foreground=FG)
        style.configure("TScrollbar", background=BG_RAISED, troughcolor=BG_INPUT,
                        borderwidth=0, arrowsize=12)
        style.configure("TCombobox", fieldbackground=BG_INPUT, foreground=FG,
                        selectbackground=ACCENT_DIM)
        style.configure("TProgressbar", background=ACCENT, troughcolor=BG_INPUT)
        style.configure("TSeparator", background=BORDER)
        style.configure("Status.TLabel", background=BG_RAISED, foreground=FG_DIM,
                        padding=(6, 2))

    # ── Menubar ───────────────────────────────────────────────────────────────

    def _build_menubar(self):
        menubar = tk.Menu(self.root, bg=BG_RAISED, fg=FG, activebackground=ACCENT_DIM,
                          activeforeground=ACCENT, relief="flat", bd=0)
        self.root.config(menu=menubar)

        file_menu = tk.Menu(menubar, tearoff=0, bg=BG_RAISED, fg=FG,
                            activebackground=ACCENT_DIM, activeforeground=ACCENT)
        file_menu.add_command(label="Open…  Ctrl+O", command=self.load_image)
        file_menu.add_command(label="Save  Ctrl+S", command=self.save_image)
        file_menu.add_command(label="Save Next Version  Ctrl+Shift+S", command=self.save_next_version)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.root.quit)
        menubar.add_cascade(label="File", menu=file_menu)

        edit_menu = tk.Menu(menubar, tearoff=0, bg=BG_RAISED, fg=FG,
                            activebackground=ACCENT_DIM, activeforeground=ACCENT)
        edit_menu.add_command(label="Undo  Ctrl+Z", command=self.undo)
        edit_menu.add_command(label="Redo  Ctrl+Y", command=self.redo)
        edit_menu.add_separator()
        edit_menu.add_command(label="Revert to Original", command=self.revert_to_original)
        menubar.add_cascade(label="Edit", menu=edit_menu)

        ops_menu = tk.Menu(menubar, tearoff=0, bg=BG_RAISED, fg=FG,
                           activebackground=ACCENT_DIM, activeforeground=ACCENT)
        ops_menu.add_command(label="Apply  Ctrl+Enter", command=self.apply_operation)
        ops_menu.add_command(label="Run Batch  Ctrl+B", command=self.run_batch)
        ops_menu.add_command(label="Auto-Sequence Export…", command=self.auto_sequence_export)
        menubar.add_cascade(label="Operations", menu=ops_menu)

        view_menu = tk.Menu(menubar, tearoff=0, bg=BG_RAISED, fg=FG,
                            activebackground=ACCENT_DIM, activeforeground=ACCENT)
        view_menu.add_command(label="Original  Ctrl+1", command=lambda: self._set_view("original"))
        view_menu.add_command(label="Current  Ctrl+2", command=lambda: self._set_view("current"))
        view_menu.add_command(label="Compare  Ctrl+3", command=lambda: self._set_view("compare"))
        view_menu.add_separator()
        view_menu.add_command(label="Toggle Hex Viewer  Ctrl+H", command=self._toggle_hex_viewer)
        menubar.add_cascade(label="View", menu=view_menu)

        export_menu = tk.Menu(menubar, tearoff=0, bg=BG_RAISED, fg=FG,
                              activebackground=ACCENT_DIM, activeforeground=ACCENT)
        export_menu.add_command(label="Save Current State", command=self.save_state)
        export_menu.add_command(label="Export Animated GIF…", command=self.export_gif)
        export_menu.add_command(label="Auto-Sequence Export…", command=self.auto_sequence_export)
        menubar.add_cascade(label="Export", menu=export_menu)

    # ── Toolbar ───────────────────────────────────────────────────────────────

    def _build_toolbar(self):
        tb = tk.Frame(self.root, bg=BG_RAISED, height=36)
        tb.pack(fill=tk.X, padx=0, pady=0)
        tb.pack_propagate(False)

        def tbtn(text, cmd, tip=""):
            b = tk.Button(tb, text=text, command=cmd, bg=BG_RAISED, fg=FG,
                          activebackground=ACCENT_DIM, activeforeground=ACCENT,
                          relief="flat", bd=0, padx=8, pady=4,
                          font=("TkDefaultFont", 9), cursor="hand2")
            b.pack(side=tk.LEFT, padx=1, fill=tk.Y)
            return b

        def sep():
            tk.Frame(tb, bg=BORDER, width=1).pack(side=tk.LEFT, fill=tk.Y, pady=4, padx=4)

        tbtn("Open", self.load_image)
        tbtn("Save", self.save_image)
        tbtn("Save v+1", self.save_next_version)
        sep()
        tbtn("↩ Undo", self.undo)
        tbtn("↪ Redo", self.redo)
        sep()
        tbtn("Revert", self.revert_to_original)
        tbtn("Save State", self.save_state)
        sep()
        # View toggle buttons
        for mode, label in (("original", "Orig"), ("current", "Current"), ("compare", "Compare")):
            tbtn(label, lambda m=mode: self._set_view(m))
        sep()
        tbtn("GIF Export", self.export_gif)
        tbtn("Auto-Seq", self.auto_sequence_export)

    # ── Main layout ───────────────────────────────────────────────────────────

    def _build_main_layout(self):
        # Outer horizontal paned window
        self._h_pane = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        self._h_pane.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)

        # Left panel
        self._left_frame = ttk.Frame(self._h_pane, width=200)
        self._h_pane.add(self._left_frame, weight=0)
        self._build_left_panel(self._left_frame)

        # Centre vertical paned window
        self._v_pane = ttk.PanedWindow(self._h_pane, orient=tk.VERTICAL)
        self._h_pane.add(self._v_pane, weight=3)

        # Preview
        self._preview_outer = ttk.Frame(self._v_pane)
        self._v_pane.add(self._preview_outer, weight=3)
        self._build_preview(self._preview_outer)

        # Hex viewer
        self._hex_viewer = HexViewerFrame(self._v_pane)
        self._v_pane.add(self._hex_viewer, weight=2)
        self._hex_visible = True

        # Right panel
        self._right_frame = ttk.Frame(self._h_pane, width=360)
        self._h_pane.add(self._right_frame, weight=0)
        self._build_right_panel(self._right_frame)

    # ── Left panel ────────────────────────────────────────────────────────────

    def _build_left_panel(self, parent: ttk.Frame):
        # File info
        info_frame = ttk.LabelFrame(parent, text="File")
        info_frame.pack(fill=tk.X, padx=4, pady=(4, 2))
        self._info_name  = ttk.Label(info_frame, text="—", foreground=FG, font=("TkDefaultFont", 9, "bold"))
        self._info_name.pack(anchor="w", padx=6, pady=(4, 0))
        self._info_size  = ttk.Label(info_frame, text="", foreground=FG_DIM, font=("TkDefaultFont", 8))
        self._info_size.pack(anchor="w", padx=6)
        self._info_fmt   = ttk.Label(info_frame, text="", foreground=FG_DIM, font=("TkDefaultFont", 8))
        self._info_fmt.pack(anchor="w", padx=6)
        self._info_ops   = ttk.Label(info_frame, text="", foreground=FG_DIM, font=("TkDefaultFont", 8))
        self._info_ops.pack(anchor="w", padx=6, pady=(0, 4))

        # Iteration strip
        self._iter_strip = IterationStrip(parent, restore_cb=self._on_strip_action)
        self._iter_strip.pack(fill=tk.BOTH, expand=True, padx=4, pady=(2, 4))

    # ── Preview ───────────────────────────────────────────────────────────────

    def _build_preview(self, parent: ttk.Frame):
        # View mode buttons
        ctrl = tk.Frame(parent, bg=BG_RAISED)
        ctrl.pack(fill=tk.X)
        for mode, label in (("original", "Original"), ("current", "Current"), ("compare", "Compare")):
            tk.Button(ctrl, text=label,
                      command=lambda m=mode: self._set_view(m),
                      bg=BG_RAISED, fg=FG_DIM, activebackground=ACCENT_DIM,
                      activeforeground=ACCENT, relief="flat", bd=0,
                      padx=10, pady=3, font=("TkDefaultFont", 8)).pack(side=tk.LEFT)

        # Single preview label (or two labels side by side for compare)
        self._preview_container = tk.Frame(parent, bg=BG_INPUT)
        self._preview_container.pack(fill=tk.BOTH, expand=True)

        self._preview_lbl = tk.Label(
            self._preview_container, text="Open an image  (Ctrl+O)",
            bg=BG_INPUT, fg=FG_DIM, font=("TkDefaultFont", 10), anchor="center",
        )
        self._preview_lbl.pack(fill=tk.BOTH, expand=True)

        self._preview_lbl_orig = tk.Label(
            self._preview_container, text="Original",
            bg=BG_INPUT, fg=FG_DIM, font=("TkDefaultFont", 9), anchor="center",
        )
        # not packed yet; used in compare mode

    # ── Right panel ───────────────────────────────────────────────────────────

    def _build_right_panel(self, parent: ttk.Frame):
        parent.pack_propagate(False)

        # Region controls
        reg_frame = ttk.LabelFrame(parent, text="Region")
        reg_frame.pack(fill=tk.X, padx=4, pady=(4, 2))

        def _region_row(frame, label, var, btn_label, btn_cmd):
            row = ttk.Frame(frame)
            row.pack(fill=tk.X, padx=4, pady=1)
            ttk.Label(row, text=label, width=12).pack(side=tk.LEFT)
            ttk.Entry(row, textvariable=var, width=9).pack(side=tk.LEFT, padx=2)
            ttk.Button(row, text=btn_label, width=8, command=btn_cmd).pack(side=tk.LEFT)

        _region_row(reg_frame, "Header end:", self.header_size,
                    "Set start →", self._sync_region_start)
        _region_row(reg_frame, "Region start:", self.region_start,
                    "= Header", self._sync_region_start)
        _region_row(reg_frame, "Region end:", self.region_end,
                    "= EOF", lambda: self.region_end.set(0))
        ttk.Label(reg_frame, text="(0 = EOF)", foreground=FG_DIM,
                  font=("TkDefaultFont", 7)).pack(anchor="e", padx=6, pady=(0, 4))

        # Operations notebook
        nb = ttk.Notebook(parent)
        nb.pack(fill=tk.BOTH, expand=True, padx=4, pady=2)
        self._notebook = nb

        self._build_tab_random(nb)
        self._build_tab_find_replace(nb)
        self._build_tab_block(nb)
        self._build_tab_arithmetic(nb)
        self._build_tab_inject(nb)

        # Apply controls
        apply_frame = ttk.Frame(parent)
        apply_frame.pack(fill=tk.X, padx=4, pady=2)

        self._apply_btn = ttk.Button(apply_frame, text="APPLY  (Ctrl+Enter)",
                                     style="Accent.TButton", command=self.apply_operation)
        self._apply_btn.pack(fill=tk.X, pady=(0, 4))

        # Batch
        batch_frame = ttk.LabelFrame(apply_frame, text="Batch")
        batch_frame.pack(fill=tk.X)
        row = ttk.Frame(batch_frame)
        row.pack(fill=tk.X, padx=4, pady=2)
        ttk.Label(row, text="×").pack(side=tk.LEFT)
        self.batch_n = tk.IntVar(value=5)
        ttk.Entry(row, textvariable=self.batch_n, width=5).pack(side=tk.LEFT, padx=4)
        self._batch_save_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(row, text="Save each", variable=self._batch_save_var).pack(side=tk.LEFT)
        btn_row = ttk.Frame(batch_frame)
        btn_row.pack(fill=tk.X, padx=4, pady=(0, 4))
        self._run_batch_btn = ttk.Button(btn_row, text="Run Batch  (Ctrl+B)", command=self.run_batch)
        self._run_batch_btn.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self._cancel_batch_btn = ttk.Button(btn_row, text="Cancel",
                                             command=self._cancel_batch, state=tk.DISABLED)
        self._cancel_batch_btn.pack(side=tk.LEFT, padx=(4, 0))

        # Seed
        seed_frame = ttk.LabelFrame(apply_frame, text="Seed")
        seed_frame.pack(fill=tk.X, pady=(4, 0))
        seed_row = ttk.Frame(seed_frame)
        seed_row.pack(fill=tk.X, padx=4, pady=4)
        self.seed_mode = tk.StringVar(value="Random")
        ttk.OptionMenu(seed_row, self.seed_mode, "Random", "Random", "Fixed").pack(side=tk.LEFT)
        self.seed_value = tk.StringVar(value="12345")
        ttk.Entry(seed_row, textvariable=self.seed_value, width=8).pack(side=tk.LEFT, padx=4)

        # Progress bar (hidden during normal use)
        self._progress = ttk.Progressbar(parent, mode="indeterminate")
        self._progress.pack(fill=tk.X, padx=4, pady=2)
        self._progress.pack_forget()

        # History
        hist_frame = ttk.LabelFrame(parent, text="History")
        hist_frame.pack(fill=tk.BOTH, padx=4, pady=(4, 4))
        list_frame = ttk.Frame(hist_frame)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)
        self._history_list = tk.Listbox(
            list_frame, bg=BG_INPUT, fg=FG_DIM,
            selectbackground=ACCENT_DIM, selectforeground=ACCENT,
            relief="flat", bd=0, height=6, font=("TkDefaultFont", 8),
        )
        hist_sb = ttk.Scrollbar(list_frame, orient=tk.VERTICAL,
                                 command=self._history_list.yview)
        self._history_list.configure(yscrollcommand=hist_sb.set)
        hist_sb.pack(side=tk.RIGHT, fill=tk.Y)
        self._history_list.pack(fill=tk.BOTH, expand=True)
        self._history_list.bind("<Double-1>", self._on_history_jump)
        ttk.Button(hist_frame, text="Undo", command=self.undo).pack(
            side=tk.LEFT, padx=2, pady=2)
        ttk.Button(hist_frame, text="Redo", command=self.redo).pack(
            side=tk.LEFT, padx=2, pady=2)

    # ── Operation tabs ────────────────────────────────────────────────────────

    def _build_tab_random(self, nb: ttk.Notebook):
        f = ttk.Frame(nb)
        nb.add(f, text="Random")

        ttk.Label(f, text="Intensity (1/N bytes):").pack(anchor="w", padx=6, pady=(6, 0))
        self.intensity = tk.IntVar(value=1000)
        ttk.Entry(f, textvariable=self.intensity).pack(fill=tk.X, padx=6)

        ttk.Label(f, text="Mode:").pack(anchor="w", padx=6, pady=(6, 0))
        self.glitch_mode = tk.StringVar(value="Random")
        modes = ["Random", "Increment", "Decrement", "Zero", "Max",
                 "XOR", "AND", "OR", "Shift Left", "Shift Right",
                 "Rotate Left", "Rotate Right"]
        ttk.OptionMenu(f, self.glitch_mode, "Random", *modes,
                       command=self._on_glitch_mode_change).pack(fill=tk.X, padx=6)

        # Mask (XOR/AND/OR)
        self._mask_frame = ttk.Frame(f)
        self._mask_frame.pack(fill=tk.X, padx=6, pady=(4, 0))
        ttk.Label(self._mask_frame, text="Mask (hex):").pack(side=tk.LEFT)
        self.mask_var = tk.StringVar(value="FF")
        ttk.Entry(self._mask_frame, textvariable=self.mask_var, width=6).pack(side=tk.LEFT, padx=4)

        # Bit count (shifts/rotates)
        self._bit_frame = ttk.Frame(f)
        self._bit_frame.pack(fill=tk.X, padx=6, pady=(2, 0))
        ttk.Label(self._bit_frame, text="Bit count (1–7):").pack(side=tk.LEFT)
        self.bit_n_var = tk.IntVar(value=1)
        ttk.Entry(self._bit_frame, textvariable=self.bit_n_var, width=4).pack(side=tk.LEFT, padx=4)

        # Step mode
        sep = ttk.Separator(f, orient=tk.HORIZONTAL)
        sep.pack(fill=tk.X, padx=6, pady=6)
        self.step_mode_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(f, text="Step mode (every Nth byte)",
                        variable=self.step_mode_var).pack(anchor="w", padx=6)
        step_row = ttk.Frame(f)
        step_row.pack(fill=tk.X, padx=6)
        ttk.Label(step_row, text="N =").pack(side=tk.LEFT)
        self.step_n_var = tk.IntVar(value=4)
        ttk.Entry(step_row, textvariable=self.step_n_var, width=6).pack(side=tk.LEFT, padx=4)

        self._on_glitch_mode_change()

    def _on_glitch_mode_change(self, *_args):
        mode = self.glitch_mode.get() if hasattr(self, "glitch_mode") else "Random"
        if mode in ("XOR", "AND", "OR"):
            self._mask_frame.pack(fill=tk.X, padx=6, pady=(4, 0))
        else:
            self._mask_frame.pack_forget()
        if mode in ("Shift Left", "Shift Right", "Rotate Left", "Rotate Right"):
            self._bit_frame.pack(fill=tk.X, padx=6, pady=(2, 0))
        else:
            self._bit_frame.pack_forget()

    def _build_tab_find_replace(self, nb: ttk.Notebook):
        f = ttk.Frame(nb)
        nb.add(f, text="Find/Replace")

        ttk.Label(f, text="Mode:").pack(anchor="w", padx=6, pady=(6, 0))
        self.find_mode = tk.StringVar(value="Exact")
        modes = ["Exact", "Wildcard ??", "Greater Than", "Less Than", "Range"]
        ttk.OptionMenu(f, self.find_mode, "Exact", *modes,
                       command=self._on_find_mode_change).pack(fill=tk.X, padx=6)

        # Exact / Wildcard fields
        self._exact_frame = ttk.Frame(f)
        self._exact_frame.pack(fill=tk.X, padx=6, pady=(4, 0))
        ttk.Label(self._exact_frame, text="Find (hex):").pack(anchor="w")
        self.find_hex = tk.StringVar()
        self.find_hex.trace_add("write", self._on_find_input_change)
        ttk.Entry(self._exact_frame, textvariable=self.find_hex).pack(fill=tk.X)
        ttk.Label(self._exact_frame, text="Replace (hex):").pack(anchor="w", pady=(4, 0))
        self.replace_hex = tk.StringVar()
        ttk.Entry(self._exact_frame, textvariable=self.replace_hex).pack(fill=tk.X)

        # Threshold fields
        self._thresh_frame = ttk.Frame(f)
        thresh_row = ttk.Frame(self._thresh_frame)
        thresh_row.pack(fill=tk.X)
        ttk.Label(thresh_row, text="Threshold (0-255):").pack(side=tk.LEFT)
        self.threshold_val = tk.IntVar(value=128)
        ttk.Entry(thresh_row, textvariable=self.threshold_val, width=6).pack(side=tk.LEFT, padx=4)
        ttk.Label(self._thresh_frame, text="Replace byte (hex):").pack(anchor="w")
        self.threshold_replace = tk.StringVar(value="00")
        ttk.Entry(self._thresh_frame, textvariable=self.threshold_replace).pack(fill=tk.X)

        # Range fields
        self._range_frame = ttk.Frame(f)
        rrow1 = ttk.Frame(self._range_frame)
        rrow1.pack(fill=tk.X)
        ttk.Label(rrow1, text="Low:").pack(side=tk.LEFT)
        self.range_low = tk.IntVar(value=0)
        ttk.Entry(rrow1, textvariable=self.range_low, width=6).pack(side=tk.LEFT, padx=4)
        ttk.Label(rrow1, text="High:").pack(side=tk.LEFT)
        self.range_high = tk.IntVar(value=255)
        ttk.Entry(rrow1, textvariable=self.range_high, width=6).pack(side=tk.LEFT, padx=4)
        ttk.Label(self._range_frame, text="Replace byte (hex):").pack(anchor="w", pady=(4, 0))
        self.range_replace = tk.StringVar(value="00")
        ttk.Entry(self._range_frame, textvariable=self.range_replace).pack(fill=tk.X)

        # Max replacements
        max_row = ttk.Frame(f)
        max_row.pack(fill=tk.X, padx=6, pady=(6, 0))
        ttk.Label(max_row, text="Max replacements (0=∞):").pack(side=tk.LEFT)
        self.max_replacements = tk.IntVar(value=0)
        ttk.Entry(max_row, textvariable=self.max_replacements, width=6).pack(side=tk.LEFT, padx=4)

        # Match preview
        self._match_preview = ttk.Label(f, text="", foreground=CYAN,
                                         font=("TkDefaultFont", 8))
        self._match_preview.pack(anchor="w", padx=6, pady=(4, 0))

        self._on_find_mode_change()

    def _on_find_mode_change(self, *_args):
        mode = self.find_mode.get() if hasattr(self, "find_mode") else "Exact"
        self._exact_frame.pack_forget()
        self._thresh_frame.pack_forget()
        self._range_frame.pack_forget()
        if mode in ("Exact", "Wildcard ??"):
            self._exact_frame.pack(fill=tk.X, padx=6, pady=(4, 0))
        elif mode in ("Greater Than", "Less Than"):
            self._thresh_frame.pack(fill=tk.X, padx=6, pady=(4, 0))
        elif mode == "Range":
            self._range_frame.pack(fill=tk.X, padx=6, pady=(4, 0))

    def _on_find_input_change(self, *_args):
        if not self.glitched_data or not hasattr(self, "_region_bounds_method"):
            return
        # Debounced match count preview would go here
        pass

    def _build_tab_block(self, nb: ttk.Notebook):
        f = ttk.Frame(nb)
        nb.add(f, text="Block")

        ttk.Label(f, text="Operation:").pack(anchor="w", padx=6, pady=(6, 0))
        self.block_op = tk.StringVar(value="Reverse")
        block_ops = ["Reverse", "Sort Ascending", "Sort Descending", "Shuffle",
                     "Swap A↔B", "Copy-Overwrite A→B", "XOR Blend A^B", "Step-Skip"]
        ttk.OptionMenu(f, self.block_op, "Reverse", *block_ops,
                       command=self._on_block_op_change).pack(fill=tk.X, padx=6)

        ttk.Label(f, text="Uses active region (right panel) by default.",
                  foreground=FG_DIM, font=("TkDefaultFont", 7),
                  wraplength=200).pack(anchor="w", padx=6, pady=(2, 0))

        sep = ttk.Separator(f, orient=tk.HORIZONTAL)
        sep.pack(fill=tk.X, padx=6, pady=6)

        # Secondary range (for dual-range ops)
        self._block_b_frame = ttk.LabelFrame(f, text="Secondary Start (B)")
        self._block_b_frame.pack(fill=tk.X, padx=6, pady=2)
        b_row = ttk.Frame(self._block_b_frame)
        b_row.pack(fill=tk.X, padx=4, pady=4)
        ttk.Label(b_row, text="B start offset:").pack(side=tk.LEFT)
        self.block_b_start = tk.IntVar(value=0)
        ttk.Entry(b_row, textvariable=self.block_b_start, width=10).pack(side=tk.LEFT, padx=4)

        # Step-skip options
        self._block_step_frame = ttk.LabelFrame(f, text="Step-Skip Options")
        self._block_step_frame.pack(fill=tk.X, padx=6, pady=2)
        ss_row = ttk.Frame(self._block_step_frame)
        ss_row.pack(fill=tk.X, padx=4, pady=4)
        ttk.Label(ss_row, text="Every Nth byte, N=").pack(side=tk.LEFT)
        self.block_step_n = tk.IntVar(value=4)
        ttk.Entry(ss_row, textvariable=self.block_step_n, width=5).pack(side=tk.LEFT, padx=2)
        ttk.Label(self._block_step_frame, text="Operation on each hit:").pack(
            anchor="w", padx=4)
        self.block_step_mode = tk.StringVar(value="XOR")
        ttk.OptionMenu(self._block_step_frame, self.block_step_mode,
                       "XOR", "XOR", "Zero", "Max", "Increment", "Decrement",
                       "Random").pack(fill=tk.X, padx=4, pady=(0, 4))

        self._on_block_op_change()

    def _on_block_op_change(self, *_args):
        op = self.block_op.get() if hasattr(self, "block_op") else "Reverse"
        dual = op in ("Swap A↔B", "Copy-Overwrite A→B", "XOR Blend A^B")
        step = op == "Step-Skip"
        if dual:
            self._block_b_frame.pack(fill=tk.X, padx=6, pady=2)
        else:
            self._block_b_frame.pack_forget()
        if step:
            self._block_step_frame.pack(fill=tk.X, padx=6, pady=2)
        else:
            self._block_step_frame.pack_forget()

    def _build_tab_arithmetic(self, nb: ttk.Notebook):
        f = ttk.Frame(nb)
        nb.add(f, text="Arithmetic")

        ttk.Label(f, text="Operation:").pack(anchor="w", padx=6, pady=(6, 0))
        self.arith_op = tk.StringVar(value="Add")
        ttk.OptionMenu(f, self.arith_op, "Add", "Add", "Subtract", "Multiply").pack(
            fill=tk.X, padx=6)

        ttk.Label(f, text="Value (0–255):").pack(anchor="w", padx=6, pady=(6, 0))
        self.arith_val = tk.IntVar(value=16)
        ttk.Entry(f, textvariable=self.arith_val).pack(fill=tk.X, padx=6)

        ttk.Label(f, text="Overflow:").pack(anchor="w", padx=6, pady=(6, 0))
        self.overflow_mode = tk.StringVar(value="Wrap")
        overflow_row = ttk.Frame(f)
        overflow_row.pack(fill=tk.X, padx=6)
        for mode in ("Wrap", "Clamp"):
            ttk.Radiobutton(overflow_row, text=mode,
                            variable=self.overflow_mode, value=mode).pack(side=tk.LEFT)

        sep = ttk.Separator(f, orient=tk.HORIZONTAL)
        sep.pack(fill=tk.X, padx=6, pady=8)

        # Channel targeting
        self.channel_enable = tk.BooleanVar(value=False)
        ttk.Checkbutton(f, text="Channel / stride targeting",
                        variable=self.channel_enable).pack(anchor="w", padx=6)
        self._chan_frame = ttk.LabelFrame(f, text="Stride")
        self._chan_frame.pack(fill=tk.X, padx=6, pady=4)
        c1 = ttk.Frame(self._chan_frame)
        c1.pack(fill=tk.X, padx=4, pady=2)
        ttk.Label(c1, text="Start offset:").pack(side=tk.LEFT)
        self.channel_start = tk.IntVar(value=2)
        ttk.Entry(c1, textvariable=self.channel_start, width=7).pack(side=tk.LEFT, padx=4)
        c2 = ttk.Frame(self._chan_frame)
        c2.pack(fill=tk.X, padx=4, pady=(0, 4))
        ttk.Label(c2, text="Step:").pack(side=tk.LEFT)
        self.channel_step = tk.IntVar(value=3)
        ttk.Entry(c2, textvariable=self.channel_step, width=7).pack(side=tk.LEFT, padx=4)
        ttk.Label(self._chan_frame,
                  text="e.g. start=2 step=3 → blue channel in 24-bit BGR BMP",
                  foreground=FG_DIM, font=("TkDefaultFont", 7), wraplength=200
                  ).pack(anchor="w", padx=4, pady=(0, 4))

    def _build_tab_inject(self, nb: ttk.Notebook):
        f = ttk.Frame(nb)
        nb.add(f, text="Inject")

        ttk.Label(f, text="Hex pattern:").pack(anchor="w", padx=6, pady=(6, 0))
        self.inject_pattern = tk.StringVar(value="FF 00 AA 55")
        ttk.Entry(f, textvariable=self.inject_pattern).pack(fill=tk.X, padx=6)
        ttk.Label(f, text="(space-separated bytes, e.g. FF 00 AA)",
                  foreground=FG_DIM, font=("TkDefaultFont", 7)).pack(anchor="w", padx=6)

        sep = ttk.Separator(f, orient=tk.HORIZONTAL)
        sep.pack(fill=tk.X, padx=6, pady=8)

        ttk.Label(f, text="Mode:").pack(anchor="w", padx=6)
        self.inject_mode = tk.StringVar(value="Overwrite Tile")
        for mode, desc in (
            ("Overwrite Tile", "Tile pattern repeatedly into region"),
            ("XOR Tile", "XOR each region byte with tiled pattern"),
            ("Insert", "Insert at offset (shifts bytes — breaks most formats)"),
        ):
            ttk.Radiobutton(f, text=mode, variable=self.inject_mode,
                            value=mode, command=self._on_inject_mode_change).pack(
                anchor="w", padx=6)
            ttk.Label(f, text=desc, foreground=FG_DIM, font=("TkDefaultFont", 7)).pack(
                anchor="w", padx=20)

        # Insert offset (only for Insert mode)
        self._insert_frame = ttk.Frame(f)
        self._insert_frame.pack(fill=tk.X, padx=6, pady=4)
        ttk.Label(self._insert_frame, text="Insert at offset:").pack(side=tk.LEFT)
        self.insert_offset = tk.IntVar(value=0)
        ttk.Entry(self._insert_frame, textvariable=self.insert_offset, width=10).pack(
            side=tk.LEFT, padx=4)

        self._insert_warning = ttk.Label(
            f, text="⚠ Insert shifts all bytes — will break most image formats.",
            foreground="#cc6644", wraplength=200, font=("TkDefaultFont", 7),
        )
        self._on_inject_mode_change()

    def _on_inject_mode_change(self, *_args):
        if not hasattr(self, "inject_mode"):
            return
        if self.inject_mode.get() == "Insert":
            self._insert_frame.pack(fill=tk.X, padx=6, pady=4)
            self._insert_warning.pack(anchor="w", padx=6)
        else:
            self._insert_frame.pack_forget()
            self._insert_warning.pack_forget()

    # ── Status bar ────────────────────────────────────────────────────────────

    def _build_status_bar(self):
        bar = tk.Frame(self.root, bg=BG_RAISED, height=22)
        bar.pack(fill=tk.X, side=tk.BOTTOM)
        bar.pack_propagate(False)

        def seg(var, width=None):
            kw = dict(textvariable=var, style="Status.TLabel")
            if width:
                kw["width"] = width
            lbl = ttk.Label(bar, **kw)
            lbl.pack(side=tk.LEFT)
            tk.Frame(bar, bg=BORDER, width=1).pack(side=tk.LEFT, fill=tk.Y, pady=2)
            return lbl

        self._status_file  = tk.StringVar(value="No file")
        self._status_size  = tk.StringVar(value="")
        self._status_fmt   = tk.StringVar(value="")
        self._status_rgn   = tk.StringVar(value="")
        self._status_ops   = tk.StringVar(value="")
        self._status_chg   = tk.StringVar(value="")
        self._status_msg   = tk.StringVar(value="Ready")

        seg(self._status_file, 14)
        seg(self._status_size, 10)
        seg(self._status_fmt, 6)
        seg(self._status_rgn, 16)
        seg(self._status_ops, 8)
        seg(self._status_chg, 12)
        ttk.Label(bar, textvariable=self._status_msg, style="Status.TLabel").pack(
            side=tk.LEFT, fill=tk.X, expand=True)

    # ── File operations ───────────────────────────────────────────────────────

    def load_image(self) -> None:
        filetypes = [
            ("Images", "*.jpg *.jpeg *.png *.bmp *.gif *.webp *.tiff *.tif *.tga *.pcx"),
            ("Raw/Binary", "*.raw *.bin"),
            ("All Files", "*.*"),
        ]
        path = filedialog.askopenfilename(filetypes=filetypes)
        if not path:
            return

        _, ext = os.path.splitext(path.lower())
        if ext and ext not in ALLOWED_EXTENSIONS:
            messagebox.showerror("Error",
                                 f"Unsupported type: {ext}\nSupported: {', '.join(sorted(ALLOWED_EXTENSIONS))}")
            return

        try:
            size = os.path.getsize(path)
            if size == 0:
                messagebox.showerror("Error", "File is empty.")
                return
            if size > MAX_FILE_SIZE:
                messagebox.showerror("Error",
                                     f"File too large ({size // (1024*1024)} MB). Max: {MAX_FILE_SIZE // (1024*1024)} MB.")
                return
        except OSError as e:
            messagebox.showerror("Error", f"Cannot access file: {e}")
            return

        try:
            with open(path, "rb") as fh:
                self.original_data = bytearray(fh.read())
        except PermissionError:
            messagebox.showerror("Error", "Permission denied.")
            return
        except OSError as e:
            messagebox.showerror("Error", f"File system error: {e}")
            return

        self.file_path = path
        self.file_ext = ext if ext else ".bin"
        self.glitched_data = bytearray(self.original_data)
        self._save_version = 1

        # Set default header size
        default_hdr = FORMAT_HEADER_SIZES.get(self.file_ext, 500)
        self.header_size.set(default_hdr)
        self.region_start.set(default_hdr)
        self.region_end.set(0)

        # Reset history and state
        self._history.clear()
        self._redo_stack.clear()
        self._last_op_offset = default_hdr
        self._iter_strip.clear()
        self._update_history_list()

        self._set_controls_enabled(True)
        self._update_file_info()
        self.refresh_ui()
        self._update_status(f"Loaded: {os.path.basename(path)}  ({size:,} bytes)")
        logging.info(f"Loaded {path} ({size} bytes)")

    def save_image(self) -> None:
        if not self.glitched_data:
            return
        ext = self.file_ext or ".jpg"
        path = filedialog.asksaveasfilename(
            defaultextension=ext,
            filetypes=[("Same format", f"*{ext}"), ("All Images", "*.jpg *.png *.bmp")],
        )
        if not path:
            return
        if self.file_path and os.path.abspath(path) == os.path.abspath(self.file_path):
            if not messagebox.askyesno("Overwrite Original?",
                                       "This will permanently overwrite your source file.\nContinue?"):
                return
        self._write_file(path, self.glitched_data)

    def save_next_version(self) -> None:
        if not self.glitched_data or not self.file_path:
            return
        base, ext = os.path.splitext(self.file_path)
        path = f"{base}_v{self._save_version}{ext}"
        if self._write_file(path, self.glitched_data):
            self._save_version += 1

    def _write_file(self, path: str, data: bytearray) -> bool:
        try:
            with open(path, "wb") as fh:
                fh.write(data)
            self._update_status(f"Saved: {os.path.basename(path)}")
            logging.info(f"Saved {path}")
            return True
        except PermissionError:
            messagebox.showerror("Error", "Permission denied.")
        except OSError as e:
            messagebox.showerror("Error", f"File system error: {e}")
        return False

    # ── State management ──────────────────────────────────────────────────────

    def save_state(self, label: str = "") -> None:
        if not self.glitched_data:
            return
        n = len(self._iter_strip.get_states()) + 1
        if not label:
            tab_idx = self._notebook.index(self._notebook.select())
            tab_names = ["Random", "Find/Replace", "Block", "Arithmetic", "Inject"]
            label = tab_names[tab_idx] if tab_idx < len(tab_names) else "manual"
        thumb = _safe_thumbnail(self.glitched_data, (72, 54))
        state = SavedState(data=bytearray(self.glitched_data), label=label, thumbnail=thumb)
        self._iter_strip.push(state)
        self._update_status(f"State v{n} saved")

    def _on_strip_action(self, action):
        if action == "__save__":
            self.save_state()
        elif isinstance(action, int):
            states = self._iter_strip.get_states()
            if 0 <= action < len(states):
                old = bytes(self.glitched_data) if self.glitched_data else b""
                self.glitched_data = bytearray(states[action].data)
                self._update_status(f"Restored state v{action + 1}")
                self.refresh_ui()

    def revert_to_original(self) -> None:
        if not self.original_data:
            return
        if self.glitched_data == self.original_data:
            self._update_status("Already at original")
            return
        # Record as history entry before reverting
        start, end = self._get_region_bounds()
        old_region = bytes(self.glitched_data[start:end])
        self.glitched_data = bytearray(self.original_data)
        new_region = bytes(self.glitched_data[start:end])
        entry = HistoryEntry(
            description="Revert to original",
            bytes_changed=_count_diff(old_region, new_region),
            range_start=start, range_old=old_region, range_new=new_region,
        )
        self._history.append(entry)
        self._redo_stack.clear()
        self._update_history_list()
        self.refresh_ui()
        self._update_status("Reverted to original")

    # ── Region helpers ────────────────────────────────────────────────────────

    def _get_region_bounds(self) -> Tuple[int, int]:
        if not self.glitched_data:
            return 0, 0
        start = max(0, self.region_start.get())
        end_raw = self.region_end.get()
        end = len(self.glitched_data) if end_raw <= 0 else min(end_raw, len(self.glitched_data))
        return start, max(start, end)

    def _sync_region_start(self):
        self.region_start.set(self.header_size.get())

    # ── Apply operation ───────────────────────────────────────────────────────

    def apply_operation(self) -> None:
        if not self.glitched_data:
            return
        if self._batch_running:
            return
        tab_idx = self._notebook.index(self._notebook.select())
        ops = [self._op_random, self._op_find_replace,
               self._op_block, self._op_arithmetic, self._op_inject]
        if 0 <= tab_idx < len(ops):
            ops[tab_idx]()

    def _apply_seed(self):
        if self.seed_mode.get() == "Fixed":
            try:
                random.seed(int(self.seed_value.get()))
            except (ValueError, tk.TclError):
                pass

    def _record_and_apply(self, description: str, fn: Callable[[bytearray], Optional[bytearray]]) -> bool:
        """
        Call fn(region) -> modified region (or None = in-place). Record history.
        Returns True if anything changed.
        """
        if not self.glitched_data:
            return False
        start, end = self._get_region_bounds()
        old_region = bytes(self.glitched_data[start:end])
        region = bytearray(old_region)

        result = fn(region)
        new_region = bytes(result) if result is not None else bytes(region)

        if old_region == new_region:
            self._update_status("No changes made")
            return False

        # Apply
        if len(new_region) != len(old_region):
            # Length-changing op (e.g. insert/find-replace with different lengths)
            self.glitched_data = (bytearray(self.glitched_data[:start])
                                  + bytearray(new_region)
                                  + bytearray(self.glitched_data[end:]))
        else:
            self.glitched_data[start:end] = new_region

        entry = HistoryEntry(
            description=description,
            bytes_changed=_count_diff(old_region, new_region),
            range_start=start, range_old=old_region, range_new=new_region,
        )
        self._history.append(entry)
        self._redo_stack.clear()
        self._last_op_offset = start
        self._hex_viewer.set_last_op_offset(start)
        self._update_history_list()
        self.refresh_ui()
        self._update_file_info()
        return True

    # ── Individual operations ─────────────────────────────────────────────────

    def _op_random(self):
        self._apply_seed()
        try:
            intensity = max(1, self.intensity.get())
        except tk.TclError:
            messagebox.showerror("Error", "Intensity must be a valid integer")
            return
        mode = self.glitch_mode.get()
        step_mode = self.step_mode_var.get()
        try:
            step_n = max(1, self.step_n_var.get())
        except tk.TclError:
            step_n = 4
        mask = 0xFF
        if mode in ("XOR", "AND", "OR"):
            try:
                mask = int(self.mask_var.get(), 16) & 0xFF
            except ValueError:
                mask = 0xFF
        bit_n = 1
        if mode in ("Shift Left", "Shift Right", "Rotate Left", "Rotate Right"):
            try:
                bit_n = max(1, min(7, self.bit_n_var.get()))
            except tk.TclError:
                bit_n = 1

        def apply(body: bytearray) -> None:
            if not body:
                return
            if step_mode:
                indices = list(range(0, len(body), step_n))
            else:
                num = max(1, min(len(body), len(body) // intensity))
                indices = random.sample(range(len(body)), num)
            for i in indices:
                b = body[i]
                if mode == "Random":        body[i] = random.randint(0, 255)
                elif mode == "Increment":   body[i] = (b + 1) % 256
                elif mode == "Decrement":   body[i] = (b - 1) % 256
                elif mode == "Zero":        body[i] = 0
                elif mode == "Max":         body[i] = 0xFF
                elif mode == "XOR":         body[i] = b ^ mask
                elif mode == "AND":         body[i] = b & mask
                elif mode == "OR":          body[i] = b | mask
                elif mode == "Shift Left":  body[i] = (b << bit_n) & 0xFF
                elif mode == "Shift Right": body[i] = (b >> bit_n) & 0xFF
                elif mode == "Rotate Left": body[i] = ((b << bit_n) | (b >> (8 - bit_n))) & 0xFF
                elif mode == "Rotate Right":body[i] = ((b >> bit_n) | (b << (8 - bit_n))) & 0xFF

        ok = self._record_and_apply(f"Random/{mode}", apply)
        if ok:
            self._update_status(f"Random/{mode} applied")

    def _op_find_replace(self):
        mode = self.find_mode.get()
        if mode in ("Exact", "Wildcard ??"):
            find_str = self.find_hex.get().strip().replace(" ", "")
            repl_str = self.replace_hex.get().strip().replace(" ", "")
            if not find_str or not repl_str:
                messagebox.showerror("Error", "Both Find and Replace values are required")
                return
            for s, name in ((find_str, "Find"), (repl_str, "Replace")):
                if not all(c in "0123456789ABCDEFabcdef" for c in s):
                    messagebox.showerror("Error", f"{name} contains invalid hex characters")
                    return
                if len(s) % 2 != 0:
                    messagebox.showerror("Error", f"{name} must have even number of hex chars")
                    return
            try:
                find_val = bytes.fromhex(find_str)
                repl_val = bytes.fromhex(repl_str)
            except ValueError as e:
                messagebox.showerror("Error", f"Invalid hex: {e}")
                return
            max_r = self.max_replacements.get()

            def apply_exact(body: bytearray) -> bytes:
                data = bytes(body)
                count = body.count(find_val) if max_r <= 0 else min(body.count(find_val), max_r)
                if max_r <= 0:
                    return data.replace(find_val, repl_val)
                result = data
                replaced = 0
                while replaced < max_r:
                    pos = result.find(find_val)
                    if pos == -1:
                        break
                    result = result[:pos] + repl_val + result[pos + len(find_val):]
                    replaced += 1
                return result

            def apply_wildcard(body: bytearray) -> bytes:
                # ?? matches any byte in find pattern
                pattern_raw = find_str
                pairs = [pattern_raw[i:i+2] for i in range(0, len(pattern_raw), 2)]
                pat_len = len(pairs)
                repl_bytes = bytes.fromhex(repl_str)
                data = bytes(body)
                result = b""
                i = 0
                count = 0
                while i <= len(data) - pat_len:
                    match = all(
                        p == "??" or data[i + j] == int(p, 16)
                        for j, p in enumerate(pairs)
                    )
                    if match and (max_r <= 0 or count < max_r):
                        result += repl_bytes
                        i += pat_len
                        count += 1
                    else:
                        result += bytes([data[i]])
                        i += 1
                result += data[i:]
                return result

            fn = apply_wildcard if mode == "Wildcard ??" else apply_exact
            ok = self._record_and_apply(f"F&R/{mode}", fn)
            if ok:
                self._update_status(f"Find/Replace ({mode}) applied")

        elif mode in ("Greater Than", "Less Than"):
            try:
                threshold = max(0, min(255, self.threshold_val.get()))
                repl_str = self.threshold_replace.get().strip().replace(" ", "")
                repl_byte = int(repl_str, 16) & 0xFF if repl_str else 0
            except (tk.TclError, ValueError):
                messagebox.showerror("Error", "Invalid threshold value")
                return
            cmp = (lambda b: b > threshold) if mode == "Greater Than" else (lambda b: b < threshold)

            def apply_thresh(body: bytearray) -> None:
                for i in range(len(body)):
                    if cmp(body[i]):
                        body[i] = repl_byte

            ok = self._record_and_apply(f"F&R/{mode} {threshold}", apply_thresh)
            if ok:
                self._update_status(f"Threshold replace ({mode} {threshold}) applied")

        elif mode == "Range":
            try:
                lo = max(0, min(255, self.range_low.get()))
                hi = max(0, min(255, self.range_high.get()))
                repl_str = self.range_replace.get().strip().replace(" ", "")
                repl_byte = int(repl_str, 16) & 0xFF if repl_str else 0
            except (tk.TclError, ValueError):
                messagebox.showerror("Error", "Invalid range values")
                return

            def apply_range(body: bytearray) -> None:
                for i in range(len(body)):
                    if lo <= body[i] <= hi:
                        body[i] = repl_byte

            ok = self._record_and_apply(f"F&R/Range {lo}–{hi}", apply_range)
            if ok:
                self._update_status(f"Range replace ({lo}–{hi}) applied")

    def _op_block(self):
        op = self.block_op.get()

        if op == "Reverse":
            def apply(body: bytearray) -> None:
                body[:] = body[::-1]
            self._record_and_apply("Block/Reverse", apply)

        elif op == "Sort Ascending":
            def apply(body: bytearray) -> None:
                body[:] = bytearray(sorted(body))
            self._record_and_apply("Block/Sort↑", apply)

        elif op == "Sort Descending":
            def apply(body: bytearray) -> None:
                body[:] = bytearray(sorted(body, reverse=True))
            self._record_and_apply("Block/Sort↓", apply)

        elif op == "Shuffle":
            self._apply_seed()
            def apply(body: bytearray) -> None:
                lst = list(body)
                random.shuffle(lst)
                body[:] = bytearray(lst)
            self._record_and_apply("Block/Shuffle", apply)

        elif op in ("Swap A↔B", "Copy-Overwrite A→B", "XOR Blend A^B"):
            start, end = self._get_region_bounds()
            region_len = end - start
            try:
                b_start = max(0, self.block_b_start.get())
            except tk.TclError:
                messagebox.showerror("Error", "Invalid B start offset")
                return
            if b_start < end or b_start + region_len > len(self.glitched_data):
                messagebox.showerror("Error",
                    "B start must be after region end and leave room for region length.\n"
                    f"B start must be ≥ {end} and ≤ {len(self.glitched_data) - region_len}.")
                return

            old_a = bytes(self.glitched_data[start:end])
            old_b = bytes(self.glitched_data[b_start:b_start + region_len])
            new_data = bytearray(self.glitched_data)

            if op == "Swap A↔B":
                new_data[start:end] = old_b
                new_data[b_start:b_start + region_len] = old_a
                desc = "Block/Swap A↔B"
            elif op == "Copy-Overwrite A→B":
                new_data[b_start:b_start + region_len] = old_a
                desc = "Block/Copy A→B"
            else:  # XOR Blend
                blended = bytearray(a ^ b for a, b in zip(old_a, old_b))
                new_data[start:end] = blended
                desc = "Block/XOR A^B"

            # Record manually (two regions)
            old_full = bytes(self.glitched_data)
            self.glitched_data = new_data
            entry = HistoryEntry(
                description=desc,
                bytes_changed=sum(a != b for a, b in zip(old_full, new_data)),
                range_start=start,
                range_old=old_full[start:b_start + region_len],
                range_new=bytes(new_data[start:b_start + region_len]),
            )
            self._history.append(entry)
            self._redo_stack.clear()
            self._update_history_list()
            self.refresh_ui()
            self._update_status(f"{desc} applied")

        elif op == "Step-Skip":
            try:
                n = max(1, self.block_step_n.get())
            except tk.TclError:
                n = 4
            step_mode = self.block_step_mode.get()
            self._apply_seed()

            def apply(body: bytearray) -> None:
                for i in range(0, len(body), n):
                    b = body[i]
                    if step_mode == "Zero":         body[i] = 0
                    elif step_mode == "Max":        body[i] = 0xFF
                    elif step_mode == "Increment":  body[i] = (b + 1) % 256
                    elif step_mode == "Decrement":  body[i] = (b - 1) % 256
                    elif step_mode == "Random":     body[i] = random.randint(0, 255)
                    elif step_mode == "XOR":        body[i] = b ^ 0xFF

            self._record_and_apply(f"Block/Step-{n}/{step_mode}", apply)

        self._update_status(f"Block/{op} applied")

    def _op_arithmetic(self):
        try:
            val = max(0, min(255, self.arith_val.get()))
        except tk.TclError:
            messagebox.showerror("Error", "Value must be an integer 0–255")
            return
        op = self.arith_op.get()
        overflow = self.overflow_mode.get()
        channel = self.channel_enable.get()
        try:
            ch_start = max(0, self.channel_start.get())
            ch_step = max(1, self.channel_step.get())
        except tk.TclError:
            ch_start, ch_step = 0, 3

        def do_op(b: int) -> int:
            if op == "Add":
                r = b + val
            elif op == "Subtract":
                r = b - val
            else:  # Multiply
                r = b * val
            if overflow == "Wrap":
                return r % 256
            else:
                return max(0, min(255, r))

        def apply(body: bytearray) -> None:
            if channel:
                for i in range(ch_start, len(body), ch_step):
                    body[i] = do_op(body[i])
            else:
                for i in range(len(body)):
                    body[i] = do_op(body[i])

        ok = self._record_and_apply(f"Arith/{op} {val}", apply)
        if ok:
            self._update_status(f"Arithmetic {op} {val} ({overflow}) applied")

    def _op_inject(self):
        pat_str = self.inject_pattern.get().strip().replace(" ", "")
        if not pat_str:
            messagebox.showerror("Error", "Pattern is empty")
            return
        if not all(c in "0123456789ABCDEFabcdef" for c in pat_str) or len(pat_str) % 2 != 0:
            messagebox.showerror("Error", "Pattern must be valid even-length hex (e.g. FF00AA)")
            return
        try:
            pattern = bytes.fromhex(pat_str)
        except ValueError as e:
            messagebox.showerror("Error", f"Invalid hex pattern: {e}")
            return

        mode = self.inject_mode.get()

        if mode == "Overwrite Tile":
            def apply(body: bytearray) -> None:
                for i in range(len(body)):
                    body[i] = pattern[i % len(pattern)]
            self._record_and_apply("Inject/Overwrite", apply)
            self._update_status("Pattern tiled into region")

        elif mode == "XOR Tile":
            def apply(body: bytearray) -> None:
                for i in range(len(body)):
                    body[i] = body[i] ^ pattern[i % len(pattern)]
            self._record_and_apply("Inject/XOR", apply)
            self._update_status("Pattern XOR-tiled into region")

        elif mode == "Insert":
            try:
                ins_off = max(0, self.insert_offset.get())
            except tk.TclError:
                ins_off = 0
            abs_off = self.region_start.get() + ins_off

            if abs_off > len(self.glitched_data):
                messagebox.showerror("Error", "Insert offset exceeds file size")
                return

            old = bytes(self.glitched_data)
            new_data = bytearray(old[:abs_off]) + bytearray(pattern) + bytearray(old[abs_off:])
            start = abs_off

            entry = HistoryEntry(
                description="Inject/Insert",
                bytes_changed=len(pattern),
                range_start=start,
                range_old=b"",
                range_new=bytes(pattern),
            )
            self.glitched_data = new_data
            self._history.append(entry)
            self._redo_stack.clear()
            self._update_history_list()
            self.refresh_ui()
            self._update_status(f"Inserted {len(pattern)} bytes at offset {abs_off}")

    # ── Batch mode ────────────────────────────────────────────────────────────

    def run_batch(self) -> None:
        if not self.glitched_data or self._batch_running:
            return
        try:
            n = max(1, min(100, self.batch_n.get()))
        except tk.TclError:
            messagebox.showerror("Error", "Batch count must be a valid integer")
            return

        save_each = self._batch_save_var.get()
        tab_idx = self._notebook.index(self._notebook.select())
        tab_names = ["Random", "Find/Replace", "Block", "Arithmetic", "Inject"]
        tab_name = tab_names[tab_idx] if tab_idx < len(tab_names) else "Op"

        self._batch_cancel.clear()
        self._batch_running = True
        self._run_batch_btn.config(state=tk.DISABLED)
        self._cancel_batch_btn.config(state=tk.NORMAL)
        self._apply_btn.config(state=tk.DISABLED)
        self._progress.pack(fill=tk.X, padx=4, pady=2)
        self._progress.start(8)
        self._update_status(f"Running batch ×{n}…")

        def worker():
            for i in range(n):
                if self._batch_cancel.is_set():
                    break
                self._batch_queue.put(("iter", i + 1, n))

            self._batch_queue.put(("done", None, None))

        def poll():
            try:
                while True:
                    msg, a, b = self._batch_queue.get_nowait()
                    if msg == "iter":
                        self.apply_operation()
                        if save_each:
                            self.save_state(f"{tab_name} batch {a}/{b}")
                        self._update_status(f"Batch {a}/{b}…")
                    elif msg == "done":
                        self._batch_done()
                        return
            except queue_module.Empty:
                pass
            self.root.after(50, poll)

        threading.Thread(target=worker, daemon=True).start()
        self.root.after(50, poll)

    def _batch_done(self):
        self._batch_running = False
        self._progress.stop()
        self._progress.pack_forget()
        self._run_batch_btn.config(state=tk.NORMAL)
        self._cancel_batch_btn.config(state=tk.DISABLED)
        self._apply_btn.config(state=tk.NORMAL)
        self._update_status("Batch complete")

    def _cancel_batch(self):
        self._batch_cancel.set()

    # ── Undo / Redo ───────────────────────────────────────────────────────────

    def undo(self) -> None:
        if not self._history or not self.glitched_data:
            self._update_status("Nothing to undo")
            return
        entry = self._history.pop()
        # Push current state to redo
        start = entry.range_start
        old_len = len(entry.range_old) if entry.range_old else 0
        cur_slice = bytes(self.glitched_data[start:start + old_len])
        redo_entry = HistoryEntry(
            description=entry.description,
            bytes_changed=entry.bytes_changed,
            range_start=start,
            range_old=cur_slice,
            range_new=entry.range_old,
        )
        self._redo_stack.append(redo_entry)
        # Restore
        if entry.range_old is not None:
            old_len_new = len(entry.range_new) if entry.range_new else 0
            new_len_old = len(entry.range_old)
            if old_len_new != new_len_old:
                self.glitched_data = (bytearray(self.glitched_data[:start])
                                      + bytearray(entry.range_old)
                                      + bytearray(self.glitched_data[start + old_len_new:]))
            else:
                self.glitched_data[start:start + new_len_old] = entry.range_old
        self._update_history_list()
        self.refresh_ui()
        self._update_status(f"Undo: {entry.description}")

    def redo(self) -> None:
        if not self._redo_stack or not self.glitched_data:
            self._update_status("Nothing to redo")
            return
        entry = self._redo_stack.pop()
        start = entry.range_start
        old_len = len(entry.range_old) if entry.range_old else 0
        if entry.range_new is not None:
            new_len = len(entry.range_new)
            if old_len != new_len:
                self.glitched_data = (bytearray(self.glitched_data[:start])
                                      + bytearray(entry.range_new)
                                      + bytearray(self.glitched_data[start + old_len:]))
            else:
                self.glitched_data[start:start + new_len] = entry.range_new
        self._history.append(entry)
        self._update_history_list()
        self.refresh_ui()
        self._update_status(f"Redo: {entry.description}")

    def _on_history_jump(self, _event=None):
        sel = self._history_list.curselection()
        if not sel:
            return
        # Jump to that history point by undoing to it
        target = sel[0]
        current = len(self._history) - 1
        steps = current - target
        for _ in range(steps):
            self.undo()

    def _update_history_list(self):
        self._history_list.delete(0, tk.END)
        for i, entry in enumerate(self._history):
            marker = "● " if i == len(self._history) - 1 else "  "
            self._history_list.insert(tk.END,
                f"{marker}{entry.description}  ({entry.bytes_changed:,}B)")
        if self._history:
            self._history_list.see(tk.END)

    # ── Export ────────────────────────────────────────────────────────────────

    def export_gif(self) -> None:
        states = self._iter_strip.get_states()
        if not states:
            messagebox.showinfo("No States",
                                "No saved states to export.\nUse 'Save State' or batch with 'Save each' enabled.")
            return
        ExportGifDialog(self.root, states)

    def auto_sequence_export(self) -> None:
        if not self.glitched_data:
            messagebox.showinfo("No File", "Load an image first.")
            return
        try:
            n = max(1, min(50, self.batch_n.get()))
        except tk.TclError:
            n = 5
        # Run batch with save_each forced
        old_save = self._batch_save_var.get()
        self._batch_save_var.set(True)
        self.run_batch()
        self._batch_save_var.set(old_save)
        # After batch completes, open GIF export
        def _open_export():
            states = self._iter_strip.get_states()
            if states:
                ExportGifDialog(self.root, states)
        self.root.after(200, _open_export)

    # ── UI refresh ────────────────────────────────────────────────────────────

    def refresh_ui(self) -> None:
        self._update_preview()
        self._update_hex_viewer()
        self._update_status_bar_counts()

    def _set_view(self, mode: str):
        self._view_mode = mode
        self._update_preview()

    def _toggle_hex_viewer(self):
        if self._hex_visible:
            self._v_pane.forget(self._hex_viewer)
        else:
            self._v_pane.add(self._hex_viewer, weight=2)
        self._hex_visible = not self._hex_visible

    def _update_preview(self) -> None:
        if not self.glitched_data:
            return

        if self._view_mode == "compare":
            # Show original and current side by side
            self._preview_lbl.pack_forget()
            self._preview_lbl_orig.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            self._preview_lbl.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            orig_thumb = _safe_thumbnail(self.original_data, (320, 240)) if self.original_data else None
            if orig_thumb:
                old = self._tk_image_orig
                self._tk_image_orig = orig_thumb
                self._preview_lbl_orig.config(image=self._tk_image_orig, text="")
                if old:
                    del old
            else:
                self._preview_lbl_orig.config(image="", text="Original")
            data = self.glitched_data
        else:
            self._preview_lbl_orig.pack_forget()
            self._preview_lbl.pack(fill=tk.BOTH, expand=True)
            data = self.original_data if self._view_mode == "original" else self.glitched_data

        thumb = _safe_thumbnail(data, PREVIEW_SIZE)
        old = self._tk_image
        self._tk_image = thumb
        if thumb:
            self._preview_lbl.config(image=self._tk_image, text="")
        else:
            self._preview_lbl.config(image="",
                text="FILE BROKEN\nTry increasing Header Protection or reduce intensity\nUndo last operation to recover")
        if old:
            del old

    def _update_hex_viewer(self) -> None:
        if not self.glitched_data or not self.original_data:
            return
        header_end = self.header_size.get()
        region_start, region_end = self._get_region_bounds()
        self._hex_viewer.refresh(
            self.original_data, self.glitched_data,
            header_end, region_start, region_end,
        )

    def _update_file_info(self) -> None:
        if not self.file_path:
            self._info_name.config(text="—")
            self._info_size.config(text="")
            self._info_fmt.config(text="")
            self._info_ops.config(text="")
            return
        name = os.path.basename(self.file_path)
        size = len(self.glitched_data) if self.glitched_data else 0
        self._info_name.config(text=name)
        self._info_size.config(text=f"{size:,} bytes")
        self._info_fmt.config(text=(self.file_ext or "").upper().lstrip("."))
        self._info_ops.config(text=f"Ops: {len(self._history)}")

    def _update_status_bar_counts(self) -> None:
        if not self.file_path:
            return
        name = os.path.basename(self.file_path)
        size = len(self.glitched_data) if self.glitched_data else 0
        fmt = (self.file_ext or "").upper().lstrip(".")
        start, end = self._get_region_bounds()
        end_label = "EOF" if self.region_end.get() <= 0 else str(end)
        rgn = f"Region: {start}–{end_label}"

        changed = 0
        if self.original_data and self.glitched_data:
            changed = sum(a != b for a, b in zip(self.original_data, self.glitched_data))
            changed += abs(len(self.original_data) - len(self.glitched_data))

        self._status_file.set(name[:14])
        self._status_size.set(f"{size:,} B")
        self._status_fmt.set(fmt[:6])
        self._status_rgn.set(rgn[:16])
        self._status_ops.set(f"Ops: {len(self._history)}")
        self._status_chg.set(f"Δ {changed:,} B")

    def _update_status(self, msg: str) -> None:
        self._status_msg.set(msg)
        logging.info(msg)

    # ── Controls enable/disable ───────────────────────────────────────────────

    def _set_controls_enabled(self, enabled: bool) -> None:
        state = tk.NORMAL if enabled else tk.DISABLED
        self._apply_btn.config(state=state)
        self._run_batch_btn.config(state=state)
        self._iter_strip._save_btn.config(state=state)


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    root = tk.Tk()
    app = GlitchApp(root)
    root.mainloop()
