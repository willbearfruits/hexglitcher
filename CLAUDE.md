# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

HexGlitcher **v3** is a PySide6 desktop app for image **databending** — non-destructive, layered, realtime glitch art. It's a ground-up rewrite of the v2 single-file Tkinter app and lives as a package under `src/hexglitcher/`.

> The legacy v2 single-file Tkinter app has been removed; it's preserved at the `v2.0.0` git tag. All work goes in `src/hexglitcher/`.

## Commands

```bash
# Run (GUI, needs a display). PySide6/numpy/Pillow/opencv must be installed.
PYTHONPATH=src python3 -m hexglitcher [image]
# or: pip install -e .  then  hexglitcher

# Tests (headless, no Qt) — fast
PYTHONPATH=src python3 -m pytest tests/test_v3.py -q
PYTHONPATH=src python3 tests/smoke_engine.py        # engine end-to-end on real images
QT_QPA_PLATFORM=offscreen PYTHONPATH=src python3 tests/smoke_ui.py   # UI wiring, headless

# Compile check
python3 -m compileall -q src
```

Deps are in `pyproject.toml`. OpenCV (`cv2`) is used for fast/tolerant decode and BMP re-encode; if absent the engine falls back to Pillow.

## Architecture

Two halves: a **Qt-free engine** (`engine/`, `formats/`, `ops/`, `io/`, `presets/`) and the **Qt UI** (`ui/`, `render/`). The engine is fully testable headless.

### Data model
`Document` → ordered list of compositing **`Layer`s** (bottom→top) → each layer references a `SourceImage` and carries a non-destructive **op-stack**. Layer 0 is the locked "Original". Sources are immutable; the document is a *recipe* applied on demand. `Document.snapshot()` deep-copies layers/ops (sharing immutable sources) for safe hand-off to the render thread.

### Two op domains, one decode boundary
Operations (`engine/operation.py`) are `BYTE` (mangle raw file bytes, pre-decode) or `PIXEL` (transform the decoded RGBA image, post-decode). The pipeline renders each layer as:

```
source bytes ─[BYTE ops]→ corrupted bytes ─[DECODE]→ RGBA ─[PIXEL ops]→ buffer → composite
```

### The pipeline (`engine/pipeline.py`) — read this first
- **Prefix cache** (darktable-style): each op folds its identity into a running hash (`engine/hashing.py`); the output *after* it is cached. Editing op *i* recomputes only *i…N*; a PIXEL-op edit reuses the cached decode. Bounded LRU.
- **Decode is never fatal** (`engine/decode.py`): a failed decode returns `None` and the layer falls back to its clean original (`ok=False`).
- **Auto-rasterize fallback** (non-obvious, important): byte corruption breaks brittle formats (PNG/WebP/GIF) → decode fails → the engine *re-runs the byte stage on a BMP re-encoding* of the source so the glitch stays visible. This is why byte/audio ops "work" on PNG. Implemented in `RenderEngine.render_layer` / `_rasterized_source`.
- **Proxy vs full**: `render(doc, max_dim=N)` downscales the decode for fast interactive previews; `max_dim=None` is full res. Compositing is bottom-up alpha+blend (`engine/blend.py`).

### Adding an operation (the common task)
Write a function decorated with `@register_op(type_id, label, domain, category, params=(...))` in an `ops/*.py` module and import that module in `ops/__init__.py:register_builtin_ops()`. That's it — the op auto-appears in the palette and the params panel **auto-generates widgets from its `ParamSpec`s**. BYTE signature `fn(region: bytearray, params, ctx: ByteContext) -> bytes|None`; PIXEL signature `fn(img: ndarray HxWx4, params, ctx: PixelContext) -> ndarray`. Set `whole_file=True` for structural BYTE ops that need the entire buffer (e.g. `png.filter_rewrite`, `jpeg.*`) instead of a region. Randomized ops should read `ctx.rng` (seeded from a `seed` param or the doc seed).

### Format backends (`formats/`)
`detect_format(bytes, ext)` → a `FormatBackend` whose `safe_zone(data)` returns the corruptible `(header_end, footer_start)` body (JPEG-after-SOS, PNG IHDR/IEND, BMP-54, GIF GCT-aware). Region-based byte ops default to this safe zone. `formats/png.py` has the chunk reader/writer used by the PNG filter-rewrite op (decompress → edit filtered stream → recompress → fix CRC).

### UI (`ui/`, `render/`)
- `render/worker.py`: a `RenderWorker` QObject on a `QThread`, **latest-wins** single request slot (no FIFO of slider positions), results via queued `previewReady(QImage, rid, ok)`. Never touch GUI off-thread.
- `ui/main_window.py`: debounced render controller (proxy on change ~45 ms, full-res on idle ~280 ms), docks, toolbar, undo/redo (deep-copied layer-state history), open/`.glitch`/export/GIF, Surprise + Looks, hold-`\` compare.
- `ui/params_panel.py` builds widgets from `ParamSpec` (int/float→slider+spinbox, choice→combo, bool→checkbox, text/filepath→lineedit).

### Persistence & export (`io/`, `presets/`)
`io/recipe.py` saves/loads the whole document as a self-contained `.glitch` JSON (layers + ops + base64 sources). `io/export.py` exports a flattened image or a seed-sweep animated GIF. `presets/` has `apply_surprise` and named `LOOKS`.

## Conventions
- Engine code stays Qt-free (so tests run headless and the engine is reusable).
- Don't claim a GUI build/packaging works unless it was actually run — packaging a PySide6+cv2 app (AppImage etc.) is not verified in CI yet.
- `master` holds v3 (released as tag `v3.0.0`); v2.0 is preserved at tag `v2.0.0`. Two remotes: `origin` (GitHub, canonical) + `gitea`.
