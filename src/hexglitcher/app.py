"""Application entry point."""
from __future__ import annotations

import os
import sys


def _log_path():
    from pathlib import Path
    if sys.platform == "win32":
        d = Path(os.environ.get("APPDATA", Path.home())) / "HexGlitcher"
    elif sys.platform == "darwin":
        d = Path.home() / "Library" / "Logs" / "HexGlitcher"
    else:
        d = Path(os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local" / "state"))) / "hexglitcher"
    d.mkdir(parents=True, exist_ok=True)
    return d / "hexglitcher.log"


def _setup_logging() -> None:
    """File logging + a global excepthook so crashes are recorded in packaged builds."""
    import logging
    logging.basicConfig(
        filename=str(_log_path()), level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    def _hook(exctype, value, tb):
        logging.getLogger("hexglitcher").critical("Uncaught exception", exc_info=(exctype, value, tb))
        sys.__excepthook__(exctype, value, tb)

    sys.excepthook = _hook


def main() -> int:
    from PySide6.QtWidgets import QApplication

    from .ops import register_builtin_ops
    from .ui.main_window import MainWindow
    from .ui.theme import apply_theme

    _setup_logging()
    register_builtin_ops()
    app = QApplication(sys.argv)
    app.setApplicationName("HexGlitcher")
    app.setApplicationDisplayName("HexGlitcher v3")
    apply_theme(app)

    win = MainWindow()
    win.show()
    if len(sys.argv) > 1 and os.path.exists(sys.argv[1]):
        win.load_path(sys.argv[1])
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
