import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from PIL import Image, ImageTk
import io
import random
import os
import logging
from typing import Optional, Tuple

# Configure logging
logging.basicConfig(
    filename='hexglitcher.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

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
    ALLOWED_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.bmp', '.gif', '.webp'}
    SYSTEM_DIRS = ['/etc', '/bin', '/sbin', '/usr/bin', '/usr/sbin', '/boot', '/sys', '/proc']

    def __init__(self, root: tk.Tk) -> None:
        """
        Initialize the GlitchApp GUI application.

        Args:
            root: The Tkinter root window
        """
        self.root = root
        self.root.title("HexGlitcher - Raw Data Bender")
        self.root.geometry("1000x700")
        self.root.configure(bg="#2b2b2b")

        # Data Storage
        self.original_data: Optional[bytearray] = None
        self.glitched_data: Optional[bytearray] = None
        self.image_preview: Optional[Image.Image] = None
        self.tk_image: Optional[ImageTk.PhotoImage] = None
        self.file_path: Optional[str] = None
        self.file_ext: Optional[str] = None

        # Setup UI components
        self.setup_styles()
        self.build_ui()

        logging.info("GlitchApp initialized")

    def setup_styles(self) -> None:
        """Configure ttk widget styles for dark theme."""
        style = ttk.Style()
        style.theme_use('clam')
        style.configure("TLabel", background="#2b2b2b", foreground="white")
        style.configure("TButton", background="#444", foreground="white", borderwidth=0)
        style.map("TButton", background=[('active', '#555')])
        style.configure("TFrame", background="#2b2b2b")
        style.configure("TLabelframe", background="#2b2b2b", foreground="white")
        style.configure("TLabelframe.Label", background="#2b2b2b", foreground="white")

    def build_ui(self) -> None:
        """Construct the main user interface layout."""
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Build left and right panels
        self.build_left_panel(main_frame)
        self.build_right_panel(main_frame)

    def build_left_panel(self, parent: ttk.Frame) -> None:
        """
        Build the left control panel with all user controls.

        Args:
            parent: The parent frame to attach to
        """
        left_panel = ttk.Frame(parent, width=300)
        left_panel.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 10))

        # Load Button
        load_btn = ttk.Button(left_panel, text="Load Image", command=self.load_image)
        load_btn.pack(fill=tk.X, pady=(0, 10))

        # Header Protection Control
        self.build_header_frame(left_panel)

        # Find and Replace
        self.build_find_replace_frame(left_panel)

        # Random Glitch
        self.build_random_glitch_frame(left_panel)

        # Save Button
        save_btn = ttk.Button(left_panel, text="Save Result", command=self.save_image)
        save_btn.pack(fill=tk.X, pady=20)

    def build_header_frame(self, parent: ttk.Frame) -> None:
        """
        Build the header protection control frame.

        Args:
            parent: The parent frame to attach to
        """
        header_frame = ttk.LabelFrame(parent, text="Header Protection (Safe Zone)")
        header_frame.pack(fill=tk.X, pady=5)

        ttk.Label(header_frame, text="Protected Bytes:").pack(anchor="w", padx=5)
        self.header_size = tk.IntVar(value=self.DEFAULT_HEADER_SIZE)
        header_entry = ttk.Entry(header_frame, textvariable=self.header_size)
        header_entry.pack(fill=tk.X, padx=5, pady=5)
        ttk.Label(header_frame, text="(Crucial to keep file valid)").pack(anchor="w", padx=5, pady=(0,5))

    def build_find_replace_frame(self, parent: ttk.Frame) -> None:
        """
        Build the find & replace hex control frame.

        Args:
            parent: The parent frame to attach to
        """
        fr_frame = ttk.LabelFrame(parent, text="Find & Replace (Hex)")
        fr_frame.pack(fill=tk.X, pady=5)

        ttk.Label(fr_frame, text="Find (e.g., FF):").pack(anchor="w", padx=5)
        self.find_hex = tk.StringVar()
        ttk.Entry(fr_frame, textvariable=self.find_hex).pack(fill=tk.X, padx=5)

        ttk.Label(fr_frame, text="Replace (e.g., 00):").pack(anchor="w", padx=5)
        self.replace_hex = tk.StringVar()
        ttk.Entry(fr_frame, textvariable=self.replace_hex).pack(fill=tk.X, padx=5)

        fr_btn = ttk.Button(fr_frame, text="Apply Find/Replace", command=self.apply_find_replace)
        fr_btn.pack(fill=tk.X, padx=5, pady=5)

    def build_random_glitch_frame(self, parent: ttk.Frame) -> None:
        """
        Build the random corruption control frame.

        Args:
            parent: The parent frame to attach to
        """
        rand_frame = ttk.LabelFrame(parent, text="Random Corruption")
        rand_frame.pack(fill=tk.X, pady=5)

        ttk.Label(rand_frame, text="Intensity (1/x bytes changed):").pack(anchor="w", padx=5)
        self.intensity = tk.IntVar(value=self.DEFAULT_INTENSITY)
        ttk.Entry(rand_frame, textvariable=self.intensity).pack(fill=tk.X, padx=5)

        ttk.Label(rand_frame, text="Byte Operation:").pack(anchor="w", padx=5)
        self.glitch_mode = tk.StringVar(value="Random")
        modes = ["Random", "Increment", "Decrement", "Zero", "Bitwise XOR"]
        ttk.OptionMenu(rand_frame, self.glitch_mode, "Random", *modes).pack(fill=tk.X, padx=5, pady=5)

        rand_btn = ttk.Button(rand_frame, text="Glitch It!", command=self.apply_random_glitch)
        rand_btn.pack(fill=tk.X, padx=5, pady=5)

    def build_right_panel(self, parent: ttk.Frame) -> None:
        """
        Build the right panel with preview and hex display.

        Args:
            parent: The parent frame to attach to
        """
        right_panel = ttk.Frame(parent)
        right_panel.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        # Image Preview Area
        self.preview_label = ttk.Label(right_panel, text="No Image Loaded", anchor="center", background="#1e1e1e")
        self.preview_label.pack(side=tk.TOP, fill=tk.BOTH, expand=True, pady=(0, 10))

        # Hex Preview Area
        hex_frame = ttk.LabelFrame(right_panel, text=f"Hex Preview (First {self.HEX_PREVIEW_BYTES} Bytes)")
        hex_frame.pack(side=tk.BOTTOM, fill=tk.X)

        self.hex_text = tk.Text(hex_frame, height=8, bg="#1e1e1e", fg="#00ff00", font=("Consolas", 10))
        self.hex_text.pack(fill=tk.BOTH, padx=5, pady=5)
        self.hex_text.config(state=tk.DISABLED)

    def load_image(self) -> None:
        """
        Open a file dialog for user to select an image file.
        Loads the file into memory as raw bytes for manipulation.
        Updates preview and hex display upon successful load.

        Validates:
            - File extension is in ALLOWED_EXTENSIONS
            - File size is under MAX_FILE_SIZE
        """
        file_path = filedialog.askopenfilename(
            filetypes=[("Images", "*.jpg *.jpeg *.png *.bmp *.gif *.webp")]
        )

        if not file_path:
            return

        # Validate file extension
        _, ext = os.path.splitext(file_path.lower())

        if ext not in self.ALLOWED_EXTENSIONS:
            logging.warning(f"Invalid file type attempted: {ext}")
            messagebox.showerror("Error", f"Invalid file type. Supported: {', '.join(self.ALLOWED_EXTENSIONS)}")
            return

        # Validate file size
        try:
            file_size = os.path.getsize(file_path)
            if file_size > self.MAX_FILE_SIZE:
                logging.warning(f"File too large: {file_size} bytes")
                messagebox.showerror("Error", f"File too large. Maximum size is {self.MAX_FILE_SIZE // (1024*1024)}MB.")
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

            # Clear old image reference before creating new one
            if self.tk_image:
                del self.tk_image

            self.glitched_data = self.original_data[:]
            self.refresh_ui()
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

    def update_hex_view(self) -> None:
        """
        Update the hex preview display with the first HEX_PREVIEW_BYTES bytes.
        Shows hex representation of raw byte data.
        """
        if not self.glitched_data:
            return

        # Show first HEX_PREVIEW_BYTES bytes
        header_len = min(self.HEX_PREVIEW_BYTES, len(self.glitched_data))
        raw_bytes = self.glitched_data[:header_len]

        hex_str = " ".join(f"{b:02X}" for b in raw_bytes)

        self.hex_text.config(state=tk.NORMAL)
        self.hex_text.delete(1.0, tk.END)
        self.hex_text.insert(tk.END, hex_str)
        self.hex_text.config(state=tk.DISABLED)

    def update_preview(self) -> None:
        """
        Update the image preview display.
        Attempts to render the glitched data as an image.
        Shows warning message if file is too corrupted to display.
        """
        if not self.glitched_data:
            return

        try:
            # Try to create image from bytes
            image_stream = io.BytesIO(self.glitched_data)
            pil_image = Image.open(image_stream)

            # Resize for display
            pil_image.thumbnail(self.PREVIEW_SIZE, Image.Resampling.LANCZOS)

            self.tk_image = ImageTk.PhotoImage(pil_image)
            self.preview_label.config(text="", image=self.tk_image)
            logging.debug("Preview updated successfully")

        except Exception as e:
            # If glitch broke the file format completely
            logging.warning(f"Preview failed: {e}")
            self.preview_label.config(
                image="",
                text="FILE BROKEN\n(Try increasing Header Protection or less intensity)"
            )

    def refresh_ui(self) -> None:
        """Refresh both preview and hex display. Call after any data modification."""
        self.update_preview()
        self.update_hex_view()

    def get_safe_data(self) -> Tuple[bytearray, bytearray]:
        """
        Separate the file data into protected header and modifiable body.

        Returns:
            Tuple of (header, body) as bytearrays

        Validates:
            - header_size is non-negative integer
            - header_size doesn't exceed data length
        """
        try:
            safe_zone = self.header_size.get()
        except tk.TclError:
            logging.error("Invalid header size: not an integer")
            messagebox.showerror("Error", "Header protection must be a valid integer")
            safe_zone = self.DEFAULT_HEADER_SIZE
            self.header_size.set(self.DEFAULT_HEADER_SIZE)

        # Validate safe_zone
        if safe_zone < 0:
            logging.warning(f"Negative header size: {safe_zone}, using default")
            messagebox.showerror("Error", "Header protection must be non-negative")
            safe_zone = self.DEFAULT_HEADER_SIZE
            self.header_size.set(self.DEFAULT_HEADER_SIZE)

        if safe_zone > len(self.original_data):
            logging.warning(f"Header size {safe_zone} exceeds file size {len(self.original_data)}")
            safe_zone = len(self.original_data)

        header = self.original_data[:safe_zone]
        body = self.original_data[safe_zone:]
        return header, body

    def apply_find_replace(self) -> None:
        """
        Apply find & replace operation on hex byte sequences.
        Only modifies the body (non-protected) portion of the file.

        Validates:
            - Both find and replace values are provided
            - Values are valid hexadecimal
            - Values have even number of characters (complete bytes)
        """
        if not self.original_data:
            messagebox.showinfo("Info", "Please load an image first")
            return

        find_str = self.find_hex.get().strip()
        replace_str = self.replace_hex.get().strip()

        # Validate hex strings are provided
        if not find_str or not replace_str:
            messagebox.showerror("Error", "Both Find and Replace values are required")
            return

        # Remove spaces and validate hex characters
        find_str = find_str.replace(" ", "")
        replace_str = replace_str.replace(" ", "")

        if not all(c in '0123456789ABCDEFabcdef' for c in find_str):
            messagebox.showerror("Error", "Find value contains invalid hex characters")
            return

        if not all(c in '0123456789ABCDEFabcdef' for c in replace_str):
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

        # Perform replace only on body
        new_body = body.replace(find_val, replace_val)

        replacements = (len(body) - len(new_body.replace(replace_val, find_val))) // len(find_val)
        logging.info(f"Find/Replace: {find_str}->{replace_str}, {replacements} replacements")

        self.glitched_data = header + new_body
        self.refresh_ui()

    def apply_random_glitch(self) -> None:
        """
        Apply random byte corruption to the file body.
        Uses optimized algorithm that pre-calculates indices to modify.

        Validates:
            - intensity is positive integer
            - glitch mode is valid
        """
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
        body = bytearray(body)  # Make mutable

        mode = self.glitch_mode.get()

        # Optimized: Pre-calculate indices to glitch instead of iterating all bytes
        if len(body) > 0:
            num_bytes_to_glitch = max(1, len(body) // intensity)
            # Ensure we don't try to sample more indices than available
            num_bytes_to_glitch = min(num_bytes_to_glitch, len(body))
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

    def save_image(self) -> None:
        """
        Save the glitched image data to a file.

        Validates:
            - glitched_data exists
            - Save path is not in system directories
            - File extension is valid
        """
        if not self.glitched_data:
            messagebox.showinfo("Info", "No glitched image to save")
            return

        # Sanitize file extension
        if not self.file_ext or self.file_ext not in self.ALLOWED_EXTENSIONS:
            self.file_ext = '.jpg'

        file_path = filedialog.asksaveasfilename(
            defaultextension=self.file_ext,
            filetypes=[("Original Type", f"*{self.file_ext}"), ("All Images", "*.jpg *.png *.bmp")]
        )

        if not file_path:
            return

        # Validate the save path is not a system directory
        abs_path = os.path.abspath(file_path)

        if any(abs_path.startswith(d) for d in self.SYSTEM_DIRS):
            logging.error(f"Attempted save to system directory: {abs_path}")
            messagebox.showerror("Error", "Cannot save to system directories")
            return

        try:
            with open(file_path, "wb") as f:
                f.write(self.glitched_data)
            logging.info(f"Saved glitched image to: {file_path}")
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

if __name__ == "__main__":
    root = tk.Tk()
    app = GlitchApp(root)
    root.mainloop()
