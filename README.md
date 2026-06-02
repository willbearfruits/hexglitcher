# HexGlitcher v3 — Layered Realtime Databender

A desktop tool for **databending**: corrupting the raw bytes of an image to make
glitch art, with a live preview that re-decodes as you work. v3 is a ground-up
PySide6 rewrite with non-destructive layers, a stacked effect pipeline, and
realtime feedback.

![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Python](https://img.shields.io/badge/python-3.10+-blue.svg)
![Platform](https://img.shields.io/badge/platform-Linux%20%7C%20Windows%20%7C%20macOS-lightgrey.svg)

## Support

Most of my work stays free and open-source.
Support early access, live sessions, and workshop-time:
https://www.patreon.com/Seriousshit

## Features

- **Realtime preview** on a background thread — drag a slider, watch it update (fast proxy while dragging, full-res on release). The UI never blocks.
- **Multi-layer compositing** — stack glitch layers over the original with blend modes + opacity. Blend the original with the glitched version, or collage several.
- **Non-destructive op-stack per layer** — add, reorder, bypass; nothing is ever baked until export.
- **Two op domains** — *byte* ops corrupt the raw file (pre-decode), *pixel* ops transform the decoded image (post-decode), split at the decode boundary.
- **A deep op library** across categories:
  - **Corruption** — random noise, byte sort, shift, chunk-shuffle, repeat, find/replace.
  - **Audio (Databend)** — echo, tremolo, flanger, bitcrush, overdrive applied to the bytes-as-audio (the Audacity workflow, built in).
  - **Inject / Mix** — weave bytes from another file (music, audio, an image) into a region.
  - **Format (Structural)** — PNG per-scanline filter rewrite (valid, structured PNG glitch), JPEG quantize, JPEG recompress.
  - **Decoder Hacks** — wrong-width "raw misread" shear, planar channel tearing.
  - **Sorting / Channels / Geometry / Texture** — threshold pixel sort, channel shift/swap, row/column displacement, noise.
- **Looks & Surprise Me** — one-click curated presets; a dice button for happy accidents.
- **Reproducible & re-editable** — seeds make any result regenerable; save the whole session as a `.glitch` project and keep editing later.
- **Export** — flattened image (PNG/JPEG/WebP/TIFF) or a seed-sweep **animated GIF**.
- **Works on any format** — if byte corruption would break a brittle format (PNG), it transparently rasterizes so the glitch stays visible.

## Run from source

Requires Python 3.10+ with a display. Dependencies: PySide6, numpy, Pillow, opencv-python.

```bash
git clone https://github.com/willbearfruits/hexglitcher.git
cd hexglitcher
pip install -e .
hexglitcher                      # or: hexglitcher path/to/image.png
# without installing:
PYTHONPATH=src python3 -m hexglitcher test_images/test.jpg
```

## Usage

1. **Open** an image (or drag-and-drop). The Original loads as a locked base layer.
2. Click **＋ Duplicate** in Layers to make a glitch layer, then set its **blend** and **opacity** to mix it over the original.
3. In **Effects → ＋ Add**, pick an operation (search by name). Tweak its sliders — the preview updates live. Reorder or bypass ops freely.
4. Hold **`\`** to compare against the original; scroll to zoom, drag to pan, **Ctrl+0** to fit.
5. Try **✨ Looks** for instant presets or **🎲 Surprise** for a random stack.
6. **Export** an image or GIF, or **Save .glitch** to keep editing later.

Tip: PNG/JPEG glitch differently. PNG byte-corruption auto-rasterizes; for *structured* PNG glitches use **Format → PNG Filter Rewrite**. JPEG loves **JPEG Recompress** followed by **Random Corruption**.

## Development

The engine (`src/hexglitcher/engine`, `formats`, `ops`, `io`, `presets`) is Qt-free and headless-testable; the UI is in `ui/` + `render/`. See [CLAUDE.md](CLAUDE.md) for architecture and how to add an operation.

```bash
PYTHONPATH=src python3 -m pytest tests/test_v3.py -q
```

## License

MIT — see [LICENSE](LICENSE). Created with [Claude Code](https://claude.com/claude-code).
