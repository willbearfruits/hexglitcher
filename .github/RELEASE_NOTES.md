# HexGlitcher v2.0.0 — Major Rewrite

**Complete rebuild with five operation modes, multi-level undo, animated export, and batch processing — all pure databending.**

HexGlitcher v2.0 is a ground-up rewrite that transforms the tool into a proper databending workstation. Every visual result comes from raw byte manipulation; Pillow is used only to decode bytes for display, never to write pixels.

---

## What's New in v2.0

### New Layout
Three-panel resizable workspace:
- **Left:** Iteration Strip — scrollable saved-state thumbnails; click to restore any state
- **Center:** Live preview + paged Hex Viewer with amber diff highlighting
- **Right:** 5-tab Operation Notebook

### Five Operation Modes

| Tab | Operations |
|-----|-----------|
| **Random** | XOR/AND/OR mask, bit shift, bit rotate, step mode |
| **Find/Replace** | Exact, Wildcard `??`, Greater Than, Less Than, Range |
| **Block** | Reverse, Sort, Shuffle, Swap A↔B, Copy-Overwrite, XOR Blend, Step-Skip |
| **Arithmetic** | Add/Sub/Multiply with Wrap or Clamp; channel-stride targeting |
| **Inject** | Overwrite-tile, XOR-tile, Insert (byte shift) |

### Other Highlights
- **Multi-level undo/redo** (50 levels, range-based) — `Ctrl+Z` / `Ctrl+Y`
- **Region selection** — apply any operation to any byte range
- **Fixed seed** — reproducible glitch sequences
- **Animated GIF export** from saved states
- **Auto-sequence export** — applies N random operations and saves each frame
- **Batch mode** — threaded, with progress bar and cancel
- **New formats** — TGA, TIFF, PCX, raw binary (`.raw`/`.bin`)
- **Auto header detection** per format on load

---

## Download

| Platform | File |
|----------|------|
| Windows | `HexGlitcher-Windows-Portable.zip` |
| Linux | `HexGlitcher-x86_64.AppImage` |
| macOS | `HexGlitcher-macOS.dmg` |

**No installation or Python required — just download and run.**

---

Built with [Claude Code](https://claude.com/claude-code)
