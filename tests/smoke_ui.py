"""Headless UI wiring smoke test (offscreen Qt).

Run: QT_QPA_PLATFORM=offscreen PYTHONPATH=src python3 tests/smoke_ui.py
"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEventLoop, QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from hexglitcher.engine.operation import Operation  # noqa: E402
from hexglitcher.io.export import export_document  # noqa: E402
from hexglitcher.ops import register_builtin_ops  # noqa: E402
from hexglitcher.ui.main_window import MainWindow  # noqa: E402
from hexglitcher.ui.theme import apply_theme  # noqa: E402

HERE = os.path.dirname(__file__)
IMG = os.path.join(HERE, "..", "test_images", "test.jpg")


def pump(ms: int) -> None:
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


def main() -> None:
    register_builtin_ops()
    app = QApplication(sys.argv)
    apply_theme(app)
    win = MainWindow()
    win.show()

    win.load_path(IMG)
    pump(700)
    assert win._last_shown > 0, "no preview was produced"
    print(f"  initial preview produced (rid={win._last_shown}, layers={len(win.doc.layers)})")

    win.surprise_me()
    pump(700)
    print(f"  surprise applied (rid={win._last_shown}, "
          f"glitch ops={len(win.doc.layers[-1].ops)})")

    # add a pixel op, select layer, re-render
    win.doc.layers[-1].ops.append(Operation("pixel.sort", {"low": 0.3, "high": 0.9}))
    win.stack.set_layer(win.doc.layers[-1])
    win._render(proxy=False)
    pump(700)

    out = "/tmp/hexglitch_ui.png"
    export_document(win.doc, out)
    assert os.path.exists(out) and os.path.getsize(out) > 0
    print(f"  exported {out} ({os.path.getsize(out):,} B)")

    win.close()
    pump(100)
    print("UI OK")


if __name__ == "__main__":
    main()
