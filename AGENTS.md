# AGENTS.md

Guidance for Codex and other coding agents working in this repository.

**Read [CLAUDE.md](CLAUDE.md) — it is the single source of truth** for this
project's architecture, commands, and conventions, and it is kept current.

Quick orientation (see CLAUDE.md for detail):

- This is **HexGlitcher v3**, a PySide6 image-databending app under
  `src/hexglitcher/`. (The legacy v2 single-file app was removed; it lives at the
  `v2.0.0` git tag.)
- Run: `PYTHONPATH=src python3 -m hexglitcher [image]`.
  Test: `PYTHONPATH=src python3 -m pytest tests/test_v3.py -q`.
- Architecture: `Document → compositing Layers → non-destructive op-stack`, with
  `BYTE` (pre-decode) and `PIXEL` (post-decode) op domains split at a cached
  decode node. The engine (`engine/`, `formats/`, `ops/`, `io/`, `presets/`) is
  Qt-free and headless-testable; the UI is in `ui/` + `render/`.
- To add a glitch, write an `@register_op(...)` function in an `ops/*.py` module
  and import it in `ops/__init__.py`. It auto-appears in the UI with
  ParamSpec-generated controls. Keep the engine Qt-free.
