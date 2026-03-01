# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Run the application
python3 main.py

# Install runtime dependencies
pip install -r requirements.txt

# Install build dependencies (PyInstaller etc.)
pip install -r requirements-build.txt

# Build platform executables
python3 build.py
```

There is no test suite. Validate changes by running `python3 main.py` directly. Syntax check without display:
```bash
python3 -c "import ast; ast.parse(open('main.py').read()); print('OK')"
```

## Architecture

Single-file Tkinter app. All logic is in `main.py` — one class `GlitchApp` wired to a `tk.Tk` root.

### Data model
Three bytearrays track state:
- `self.original_data` — raw bytes of the loaded file, **never mutated** after load
- `self.glitched_data` — current working state; all operations read from and write back to this
- Header protection (`self.header_size`) splits both at a byte offset: `header = original_data[:safe_zone]`, `body = glitched_data[safe_zone:]`

`get_safe_data()` returns `(header, body)`. Glitch operations rebuild `glitched_data = header + modified_body` and call `refresh_ui()`.

### UI layout
```
root
└── main_frame (horizontal pack)
    ├── left_panel (300px fixed, fill=Y)
    │   ├── Load Image button
    │   ├── Header Protection LabelFrame
    │   ├── Find & Replace LabelFrame
    │   ├── Random Corruption LabelFrame
    │   ├── Revert to Original button
    │   └── Save Result button
    └── right_panel (fill=BOTH, expand)
        ├── preview_label (image preview, fill=BOTH)
        ├── hex_frame (Hex Preview LabelFrame, fixed height)
        └── status_bar (bottom label)
```

### Key constraints
- **Tkinter is single-threaded** — all UI and file I/O runs on the event loop thread. File loads and preview renders block the UI. Heavy operations (large files + high intensity) will freeze briefly.
- **PIL/Pillow** used only for preview rendering (`Image.open` → `thumbnail` → `ImageTk.PhotoImage`). The raw byte manipulation uses pure Python `bytearray` and `bytes.replace` — Pillow is not involved in the glitch logic.
- **Log location**: written to a platform-appropriate user-writable path (not CWD) to work from AppImage/PyInstaller contexts.
- **`mosh.py` equivalent**: there is none — all glitch logic is inline in `GlitchApp`.
- `build.py` produces platform-specific outputs in `dist/`: `HexGlitcher-Windows-Portable.zip`, `HexGlitcher-x86_64.AppImage`, `HexGlitcher-macOS.dmg`.
- CI pipeline in `.github/workflows/build-release.yml` triggers on `v*` tags.

### Control enable/disable pattern
Controls that require a loaded image (`_fr_btn`, `_rand_btn`, `_save_btn`, `_revert_btn`) are disabled on startup via `_set_controls_enabled(False)` and enabled after a successful `load_image()`. This prevents silent no-ops.
