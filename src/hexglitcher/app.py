"""Application entry point."""
from __future__ import annotations

import os
import sys


def main() -> int:
    from PySide6.QtWidgets import QApplication

    from .ops import register_builtin_ops
    from .ui.main_window import MainWindow
    from .ui.theme import apply_theme

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
