import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from PIL import Image, ImageTk
import io
import random
import os
import sys
import logging
from pathlib import Path
from typing import Optional, Tuple


def _get_log_path() -> Path:
    """Resolve a platform-appropriate, user-writable log path."""
    if sys.platform == "win32":
        log_dir = Path(os.environ.get("APPDATA", Path.home())) / "HexGlitcher"
    elif sys.platform == "darwin":
        log_dir = Path.home() / "Library" / "Logs" / "HexGlitcher"
    else:
        xdg_state = os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local" / "state"))
        log_dir = Path(xdg_state) / "hexglitcher"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir / "hexglitcher.log"


logging.basicConfig(
    filename=str(_get_log_path()),
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)

# Guard against decompression bombs (50 MP limit)
Image.MAX_IMAGE_PIXELS = 50_000_000


class GlitchApp:
    """
    HexGlitcher - A raw hex-level image glitching application.
    Allows data bending while preserving file headers for validity.
    """

    # Configuration constants
    DEFAULT_HEADER_SIZE = 500
    DEFAULT_INTENSITY = 1000
    HEX_PREVIEW_BYTES = 512
    PREVIEW_SIZE = (600, 400)
    MAX_FILE_SIZE = 100 * 1024 * 1024  # 100MB
    ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp"}

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("HexGlitcher - Raw Data Bender")
        self.root.geometry("1000x700")
        self.root.minsize(800, 500)
        self.root.configure(bg="#2b2b2b")

        # Data storage
        self.original_data: Optional[bytearray] = None
        self.glitched_data: Optional[bytearray] = None
        self.tk_image: Optional[ImageTk.PhotoImage] = None
        self.file_path: Optional[str] = None
        self.file_ext: Optional[str] = None

        self.setup_styles()
        self.build_ui()
        self._set_controls_enabled(False)

        # Keyboard shortcuts
        self.root.bind("<Control-o>", lambda _e: self.load_image())
        self.root.bind("<Control-s>", lambda _e: self.save_image())
        self.root.bind("<Control-z>", lambda _e: self.revert_to_original())

        logging.info("GlitchApp initialized")

    def setup_styles(self) -> None:
        """Configure ttk widget styles for dark theme."""
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TLabel", background="#2b2b2b", foreground="white")
        style.configure("TButton", background="#444", foreground="white", borderwidth=0)
        style.map("TButton", background=[("active", "#555")])
        style.configure("TFrame", background="#2b2b2b")
        style.configure("TLabelframe", background="#2b2b2b", foreground="white")
        style.configure("TLabelframe.Label", background="#2b2b2b", foreground="white")

    def build_ui(self) -> None:
        """Construct the main user interface layout."""
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        self.build_left_panel(main_frame)
        self.build_right_panel(main_frame)

    def build_left_panel(self, parent: ttk.Frame) -> None:
        left_panel = ttk.Frame(parent, width=300)
        left_panel.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 10))
        left_panel.pack_propagate(False)

        load_btn = ttk.Button(left_panel, text="Load Image  (Ctrl+O)", command=self.load_image)
        load_btn.pack(fill=tk.X, pady=(0, 10))

        self.build_header_frame(left_panel)
        self.build_find_replace_frame(left_panel)
        self.build_random_glitch_frame(left_panel)

        self._revert_btn = ttk.Button(left_panel, text="Revert to Original  (Ctrl+Z)", command=self.revert_to_original)
        self._revert_btn.pack(fill=tk.X, pady=(10, 0))

        self._save_btn = ttk.Button(left_panel, text="Save Result  (Ctrl+S)", command=self.save_image)
        self._save_btn.pack(fill=tk.X, pady=(5, 20))

    def build_header_frame(self, parent: ttk.Frame) -> None:
        header_frame = ttk.LabelFrame(parent, text="Header Protection (Safe Zone)")
        header_frame.pack(fill=tk.X, pady=5)

        ttk.Label(header_frame, text="Protected Bytes:").pack(anchor="w", padx=5)
        self.header_size = tk.IntVar(value=self.DEFAULT_HEADER_SIZE)
        ttk.Entry(header_frame, textvariable=self.header_size).pack(fill=tk.X, padx=5, pady=5)
        ttk.Label(header_frame, text="(Crucial to keep file valid)").pack(anchor="w", padx=5, pady=(0, 5))

    def build_find_replace_frame(self, parent: ttk.Frame) -> None:
        fr_frame = ttk.LabelFrame(parent, text="Find & Replace (Hex)")
        fr_frame.pack(fill=tk.X, pady=5)

        ttk.Label(fr_frame, text="Find (e.g., FF):").pack(anchor="w", padx=5)
        self.find_hex = tk.StringVar()
        ttk.Entry(fr_frame, textvariable=self.find_hex).pack(fill=tk.X, padx=5)

        ttk.Label(fr_frame, text="Replace (e.g., 00):").pack(anchor="w", padx=5)
        self.replace_hex = tk.StringVar()
        ttk.Entry(fr_frame, textvariable=self.replace_hex).pack(fill=tk.X, padx=5)

        self._fr_btn = ttk.Button(fr_frame, text="Apply Find/Replace", command=self.apply_find_replace)
        self._fr_btn.pack(fill=tk.X, padx=5, pady=5)

    def build_random_glitch_frame(self, parent: ttk.Frame) -> None:
        rand_frame = ttk.LabelFrame(parent, text="Random Corruption")
        rand_frame.pack(fill=tk.X, pady=5)

        ttk.Label(rand_frame, text="Intensity (1/x bytes changed):").pack(anchor="w", padx=5)
        self.intensity = tk.IntVar(value=self.DEFAULT_INTENSITY)
        ttk.Entry(rand_frame, textvariable=self.intensity).pack(fill=tk.X, padx=5)

        ttk.Label(rand_frame, text="Byte Operation:").pack(anchor="w", padx=5)
        self.glitch_mode = tk.StringVar(value="Random")
        # Pass each mode once — do not repeat the default in *values to avoid duplicate entry
        ttk.OptionMenu(
            rand_frame, self.glitch_mode, "Random",
            "Random", "Increment", "Decrement", "Zero", "Bitwise XOR",
        ).pack(fill=tk.X, padx=5, pady=5)

        self._rand_btn = ttk.Button(rand_frame, text="Glitch It!", command=self.apply_random_glitch)
        self._rand_btn.pack(fill=tk.X, padx=5, pady=5)

    def build_right_panel(self, parent: ttk.Frame) -> None:
        right_panel = ttk.Frame(parent)
        right_panel.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        self.preview_label = ttk.Label(
            right_panel, text="No Image Loaded\n\nCtrl+O to open", anchor="center", background="#1e1e1e"
        )
        self.preview_label.pack(side=tk.TOP, fill=tk.BOTH, expand=True, pady=(0, 10))

        hex_frame = ttk.LabelFrame(right_panel, text="Hex Preview (Glitch Area)")
        hex_frame.pack(side=tk.TOP, fill=tk.X)

        self.hex_text = tk.Text(hex_frame, height=8, bg="#1e1e1e", fg="#00ff00", font=("Consolas", 10))
        self.hex_text.pack(fill=tk.BOTH, padx=5, pady=5)
        self.hex_text.config(state=tk.DISABLED)

        self._status_var = tk.StringVar(value="Ready")
        status_bar = ttk.Label(right_panel, textvariable=self._status_var, anchor="w", relief="sunken")
        status_bar.pack(side=tk.BOTTOM, fill=tk.X, pady=(5, 0))

    # -- Control state -----------------------------------------------------

    def _set_controls_enabled(self, enabled: bool) -> None:
        state = tk.NORMAL if enabled else tk.DISABLED
        for btn in (self._fr_btn, self._rand_btn, self._save_btn, self._revert_btn):
            btn.config(state=state)

    def _update_status(self, msg: str) -> None:
        self._status_var.set(msg)

    # -- File operations ---------------------------------------------------

    def load_image(self) -> None:
        """Open a file dialog, load image bytes, update preview."""
        file_path = filedialog.askopenfilename(
            filetypes=[("Images", "*.jpg *.jpeg *.png *.bmp *.gif *.webp")]
        )
        if not file_path:
            return

        _, ext = os.path.splitext(file_path.lower())
        if ext not in self.ALLOWED_EXTENSIONS:
            logging.warning(f"Invalid file type attempted: {ext}")
            messagebox.showerror("Error", f"Invalid file type. Supported: {', '.join(self.ALLOWED_EXTENSIONS)}")
            return

        try:
            file_size = os.path.getsize(file_path)
            if file_size == 0:
                messagebox.showerror("Error", "File is empty.")
                return
            if file_size > self.MAX_FILE_SIZE:
                logging.warning(f"File too large: {file_size} bytes")
                messagebox.showerror("Error", f"File too large. Maximum size is {self.MAX_FILE_SIZE // (1024 * 1024)}MB.")
                return
            logging.info(f"Loading file: {file_path} ({file_size} bytes)")
        except OSError as e:
            logging.error(f"Cannot access file: {e}")
            messagebox.showerror("Error", f"Cannot access file: {e}")
            return

        self.file_path = file_path
        self.file_ext = ext

        try:
            with open(file_path, "rb") as f:
                self.original_data = bytearray(f.read())

            old = self.tk_image
            self.tk_image = None
            if old:
                del old

            self.glitched_data = self.original_data[:]
            self._set_controls_enabled(True)
            self.refresh_ui()
            self._update_status(f"Loaded: {os.path.basename(file_path)}  ({file_size:,} bytes)")
            logging.info(f"Successfully loaded {len(self.original_data)} bytes")

        except PermissionError:
            logging.error(f"Permission denied: {file_path}")
            messagebox.showerror("Error", "Permission denied reading file")
        except OSError as e:
            logging.error(f"File system error: {e}")
            messagebox.showerror("Error", f"File system error: {e}")
        except Exception as e:
            logging.error(f"Failed to load file: {e}", exc_info=True)
            messagebox.showerror("Error", f"Failed to load file: {e}")

    def revert_to_original(self) -> None:
        """Reset glitched_data back to the original loaded bytes."""
        if not self.original_data:
            return
        self.glitched_data = self.original_data[:]
        self.refresh_ui()
        self._update_status("Reverted to original")
        logging.info("Reverted to original data")

    def save_image(self) -> None:
        """Save glitched bytes to a file chosen by the user."""
        if not self.glitched_data:
            messagebox.showinfo("Info", "No glitched image to save")
            return

        if not self.file_ext or self.file_ext not in self.ALLOWED_EXTENSIONS:
            self.file_ext = ".jpg"

        file_path = filedialog.asksaveasfilename(
            defaultextension=self.file_ext,
            filetypes=[("Original Type", f"*{self.file_ext}"), ("All Images", "*.jpg *.png *.bmp")],
        )
        if not file_path:
            return

        # Warn before overwriting the source file
        if self.file_path and os.path.abspath(file_path) == os.path.abspath(self.file_path):
            if not messagebox.askyesno(
                "Overwrite Original?",
                "The save path matches the original file.\n"
                "This will permanently overwrite your source image.\nContinue?",
            ):
                return

        try:
            with open(file_path, "wb") as f:
                f.write(self.glitched_data)
            logging.info(f"Saved glitched image to: {file_path}")
            self._update_status(f"Saved: {os.path.basename(file_path)}")
            messagebox.showinfo("Success", f"Glitched image saved to:\n{os.path.basename(file_path)}")

        except PermissionError:
            logging.error(f"Permission denied: {file_path}")
            messagebox.showerror("Error", "Permission denied writing to this location")
        except OSError as e:
            logging.error(f"File system error: {e}")
            messagebox.showerror("Error", f"File system error: {e}")
        except Exception as e:
            logging.error(f"Failed to save: {e}", exc_info=True)
            messagebox.showerror("Error", f"Failed to save: {e}")

    # -- Display -----------------------------------------------------------

    def update_hex_view(self) -> None:
        """Show HEX_PREVIEW_BYTES bytes starting at the safe-zone boundary (the glitch area)."""
        if not self.glitched_data:
            return

        try:
            safe_zone = self.header_size.get()
        except tk.TclError:
            safe_zone = self.DEFAULT_HEADER_SIZE
        safe_zone = max(0, min(safe_zone, len(self.glitched_data)))

        start = safe_zone
        end = min(start + self.HEX_PREVIEW_BYTES, len(self.glitched_data))
        raw_bytes = self.glitched_data[start:end]

        hex_str = " ".join(f"{b:02X}" for b in raw_bytes)

        self.hex_text.config(state=tk.NORMAL)
        self.hex_text.delete(1.0, tk.END)
        self.hex_text.insert(tk.END, hex_str)
        self.hex_text.config(state=tk.DISABLED)

    def update_preview(self) -> None:
        """Render glitched_data as an image thumbnail. Shows a broken-file message on failure."""
        if not self.glitched_data:
            return

        try:
            image_stream = io.BytesIO(self.glitched_data)
            with Image.open(image_stream) as pil_image:
                pil_image.load()  # force full decode before stream closes
                pil_image.thumbnail(self.PREVIEW_SIZE, Image.Resampling.LANCZOS)
                new_tk_image = ImageTk.PhotoImage(pil_image)

            old = self.tk_image
            self.tk_image = new_tk_image
            self.preview_label.config(text="", image=self.tk_image)
            if old:
                del old
            logging.debug("Preview updated successfully")

        except MemoryError:
            logging.warning("Preview failed: out of memory (image too large)")
            self.tk_image = None
            self.preview_label.config(image="", text="FILE TOO LARGE TO PREVIEW")
        except Exception as e:
            logging.warning(f"Preview failed: {e}")
            self.tk_image = None
            self.preview_label.config(
                image="",
                text="FILE BROKEN\n(Try increasing Header Protection or less intensity)",
            )

    def refresh_ui(self) -> None:
        """Refresh both preview and hex display after any data modification."""
        self.update_preview()
        self.update_hex_view()

    # -- Glitch operations -------------------------------------------------

    def get_safe_data(self) -> Tuple[bytearray, bytearray]:
        """
        Return (header, body) split at safe_zone.
        Header always comes from original_data (protected).
        Body comes from glitched_data so operations stack correctly.
        """
        if self.original_data is None or self.glitched_data is None:
            raise RuntimeError("No image data loaded")

        try:
            safe_zone = self.header_size.get()
        except tk.TclError:
            logging.error("Invalid header size: not an integer")
            messagebox.showerror("Error", "Header protection must be a valid integer")
            safe_zone = self.DEFAULT_HEADER_SIZE
            self.header_size.set(self.DEFAULT_HEADER_SIZE)

        if safe_zone < 0:
            logging.warning(f"Negative header size: {safe_zone}, using default")
            messagebox.showerror("Error", "Header protection must be non-negative")
            safe_zone = self.DEFAULT_HEADER_SIZE
            self.header_size.set(self.DEFAULT_HEADER_SIZE)

        if safe_zone > len(self.original_data):
            logging.warning(f"Header size {safe_zone} exceeds file size {len(self.original_data)}")
            safe_zone = len(self.original_data)

        header = self.original_data[:safe_zone]   # always from original — protected
        body = bytearray(self.glitched_data[safe_zone:])  # from current state — composable
        return header, body

    def apply_find_replace(self) -> None:
        """Replace all occurrences of a hex byte sequence in the body."""
        if not self.original_data:
            messagebox.showinfo("Info", "Please load an image first")
            return

        find_str = self.find_hex.get().strip().replace(" ", "")
        replace_str = self.replace_hex.get().strip().replace(" ", "")

        if not find_str or not replace_str:
            messagebox.showerror("Error", "Both Find and Replace values are required")
            return

        if not all(c in "0123456789ABCDEFabcdef" for c in find_str):
            messagebox.showerror("Error", "Find value contains invalid hex characters")
            return

        if not all(c in "0123456789ABCDEFabcdef" for c in replace_str):
            messagebox.showerror("Error", "Replace value contains invalid hex characters")
            return

        if len(find_str) % 2 != 0 or len(replace_str) % 2 != 0:
            messagebox.showerror("Error", "Hex values must have even number of characters (complete bytes)")
            return

        try:
            find_val = bytes.fromhex(find_str)
            replace_val = bytes.fromhex(replace_str)
        except ValueError as e:
            logging.error(f"Hex conversion error: {e}")
            messagebox.showerror("Error", f"Invalid Hex: {e}")
            return

        header, body = self.get_safe_data()

        # Count before replacing for accurate logging
        replacements = body.count(find_val)
        new_body = body.replace(find_val, replace_val)
        logging.info(f"Find/Replace: {find_str}->{replace_str}, {replacements} replacements")

        self.glitched_data = header + new_body
        self.refresh_ui()
        self._update_status(f"Find/Replace: {replacements} replacement(s) of {find_str} → {replace_str}")

    def apply_random_glitch(self) -> None:
        """Randomly corrupt bytes in the body using the selected mode."""
        if not self.original_data:
            messagebox.showinfo("Info", "Please load an image first")
            return

        try:
            intensity = self.intensity.get()
        except tk.TclError:
            logging.error("Invalid intensity: not an integer")
            messagebox.showerror("Error", "Intensity must be a valid integer")
            return

        if intensity <= 0:
            messagebox.showerror("Error", "Intensity must be greater than 0")
            return

        header, body = self.get_safe_data()
        mode = self.glitch_mode.get()

        if len(body) > 0:
            num_bytes_to_glitch = max(1, min(len(body) // intensity, len(body)))
            indices = random.sample(range(len(body)), num_bytes_to_glitch)
            logging.info(f"Glitching {num_bytes_to_glitch} bytes with mode: {mode}")

            for i in indices:
                if mode == "Random":
                    body[i] = random.randint(0, 255)
                elif mode == "Increment":
                    body[i] = (body[i] + 1) % 256
                elif mode == "Decrement":
                    body[i] = (body[i] - 1) % 256
                elif mode == "Zero":
                    body[i] = 0
                elif mode == "Bitwise XOR":
                    body[i] = body[i] ^ 0xFF

        self.glitched_data = header + body
        self.refresh_ui()
        self._update_status(f"Glitched {num_bytes_to_glitch:,} bytes  [mode: {mode}, intensity: 1/{intensity}]")


if __name__ == "__main__":
    root = tk.Tk()
    app = GlitchApp(root)
    root.mainloop()
