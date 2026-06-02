# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

## What this is

HexGlitcher v2.0 is a single-file Tkinter desktop app (`main.py`, ~2000 lines) for image **databending** — corrupting raw bytes to make glitch art while keeping a file's header intact so it still decodes. Pure-Python `bytearray` manipulation does all the work; Pillow only *decodes bytes for on-screen preview* and never writes back (this invariant is stated in the module docstring — preserve it).

## Commands

```bash
python3 main.py                      # run (GUI, needs a display)
pip install -r requirements.txt      # runtime dep: Pillow only (Tkinter ships with Python)
pip install -r requirements-build.txt
python3 build.py                     # build platform executable into dist/
```

**No test suite.** Validate by running the app, or syntax-check headlessly:
```bash
python3 -c "import ast; ast.parse(open('main.py').read()); print('OK')"
```
`test_images/` holds 26 fixtures across 16 formats for manual testing.

## Architecture

One file, several classes. `GlitchApp` is the controller; the rest are widgets/data:

- **`GlitchApp`** — owns state, builds the UI, dispatches operations.
- **`HexViewerFrame`** — paginated `offset | hex | ASCII` dump; highlights changed bytes vs original.
- **`IterationStrip`** — horizontal strip of saved-state thumbnails (the GIF-frame source).
- **`ExportGifDialog`** — assembles an animated GIF from saved states.
- **`@dataclass HistoryEntry`** — one undo/redo unit (see below). **`@dataclass SavedState`** — a snapshot for the strip.
- Module helpers: `_get_log_path()`, `_safe_thumbnail()` (decode→thumbnail, `None` if corrupt), `_count_diff()`.

### Data model — the load-bearing concept

Two buffers: `original_data` (immutable after load) and `glitched_data` (the working buffer). **Operations mutate `glitched_data` in place and therefore STACK** — apply twice and the second builds on the first. (This is the key behavior change from v1.0, which recomputed from the original each time; do not reintroduce that assumption.)

Glitching is confined to a **region**, not just a protected header: `region_start`/`region_end` IntVars define the editable window (`end == 0` means EOF). `header_size` is just a default that seeds `region_start` on load. `_get_region_bounds()` resolves the active `(start, end)`. On load, `FORMAT_HEADER_SIZES` picks a sensible default header per extension (jpg 600, png 33, bmp 54, gif 13, raw/bin 0, …).

### The central chokepoint: `_record_and_apply(description, fn)`

**Almost every operation routes through this method.** It slices the region out of `glitched_data`, hands the bytes to `fn(region: bytearray) -> Optional[bytearray]` (mutate in place and return `None`, or return a new/resized buffer), splices the result back, and pushes a `HistoryEntry`. **When adding a new glitch, write an `fn` and pass it here** — you get undo/redo, diff counting, and region handling for free. Length-changing results are spliced correctly.

Two operations bypass it and record history manually because they touch two regions or change length: Block's `Swap/Copy/XOR-blend A↔B`, and `Inject/Insert`. Match that pattern only when you genuinely can't express the change as a single-region `fn`.

### Operations — 5 notebook tabs

`apply_operation()` reads the selected tab index and calls `[_op_random, _op_find_replace, _op_block, _op_arithmetic, _op_inject][idx]`. Tab order is load-bearing — it's mirrored in several `["Random","Find/Replace","Block","Arithmetic","Inject"]` lists (batch labels, `save_state`). Keep them in sync.

- **Random** — per-byte Random/Increment/Decrement/Zero/Max/XOR/AND/OR/Shift/Rotate; either `intensity` (1 byte per N) or step-every-N; hex mask for bitwise modes.
- **Find/Replace** — Exact, `Wildcard ??` (byte-wise pattern match), and threshold modes (Greater Than / Less Than / Range) that replace matching byte values; `max_replacements` cap.
- **Block** — Reverse, Sort ↑/↓, Shuffle, Step-Skip, and the two-region Swap/Copy/XOR-blend.
- **Arithmetic** — Add/Subtract/Multiply with Wrap or Clamp overflow; optional channel stride (`start`/`step`) to hit one interleaved channel.
- **Inject** — Overwrite-tile, XOR-tile, and Insert (length-changing).

`_apply_seed()` re-seeds the `random` module from a fixed value when seed mode is "Fixed" — call it at the top of any new randomized op so results are reproducible.

### Undo/redo — range diffs, not snapshots

`HistoryEntry` stores only the changed byte range (`range_start`, `range_old`, `range_new`), so history is cheap even on large files. `_history` is a `deque(maxlen=HISTORY_MAX=50)`; `_redo_stack` is cleared on every new op. `undo()`/`redo()` splice the stored range back and handle length changes. The History list and IterationStrip are distinct: history = reversible op log; strip = manually saved checkpoints for comparison and GIF export.

### Batch — main-thread work, worker only ticks

`run_batch()` repeats the current tab's op N times (1–100). **Tkinter is single-threaded**, so the actual `apply_operation()` calls run on the main thread inside a `root.after()` poll loop; the worker thread only enqueues tick messages onto `_batch_queue`. `_batch_cancel` (an `Event`) stops it. Don't move byte-mutating or UI work onto the worker thread.

### Other constraints

- **Whole-region ops** (sort/reverse/shuffle/threshold/arithmetic-over-all) are O(n) Python loops/copies — with the region set to EOF on a large file they can briefly freeze the UI. Acceptable, but don't make it worse.
- **Logging** goes to a platform user dir via `_get_log_path()` (`%APPDATA%` / `~/Library/Logs` / `$XDG_STATE_HOME`), **not** the CWD — required because PyInstaller/AppImage may run from a read-only directory. A stray `hexglitcher.log` in the repo root is a v1.0 leftover, not the live log.
- `Image.MAX_IMAGE_PIXELS = 50_000_000` guards against decompression-bomb previews.
- Saving writes raw bytes (no re-encode): `save_image()` (warns before overwriting the source) and `save_next_version()` (appends `_v1`, `_v2`, …).

## Releases

Pushing a `v*` tag triggers `.github/workflows/build-release.yml`, which builds Windows/Linux/macOS via `build.py` and publishes a GitHub Release using `.github/RELEASE_NOTES.md` as the body. Bump `CFBundleShortVersionString` in `hexglitcher.spec` and the README changelog before tagging.
