"""Dark, neutral creative-tool theme.

Near-neutral grays (not pure black, so the image's own blacks stay judgeable),
one warm accent reserved for selection/focus. Applied as a global stylesheet.
"""
from __future__ import annotations

# palette
BG        = "#1b1c1f"
BG_PANEL  = "#212327"
BG_RAISED = "#2a2d33"
BG_INPUT  = "#16171a"
BORDER    = "#34373d"
FG        = "#d7d6d2"
FG_DIM    = "#83858c"
ACCENT    = "#e8a13a"
ACCENT_BG = "#3a2a10"
CANVAS_BG = "#2d2d2d"   # neutral 18%-ish gray behind the image

STYLESHEET = f"""
* {{ outline: none; }}
QWidget {{
    background: {BG};
    color: {FG};
    font-size: 12px;
}}
QMainWindow::separator {{ background: {BORDER}; width: 1px; height: 1px; }}

QToolBar {{ background: {BG_PANEL}; border: 0; spacing: 4px; padding: 3px; }}
QToolButton {{ background: transparent; border: 1px solid transparent;
    border-radius: 4px; padding: 4px 8px; }}
QToolButton:hover {{ background: {BG_RAISED}; border-color: {BORDER}; }}
QToolButton:pressed, QToolButton:checked {{ background: {ACCENT_BG}; color: {ACCENT}; }}

QDockWidget {{ titlebar-close-icon: none; color: {FG_DIM}; font-size: 11px; }}
QDockWidget::title {{ background: {BG_PANEL}; padding: 5px 8px;
    border-bottom: 1px solid {BORDER}; }}

QStatusBar {{ background: {BG_PANEL}; color: {FG_DIM}; border-top: 1px solid {BORDER}; }}
QStatusBar::item {{ border: 0; }}

QLabel {{ background: transparent; }}
QLabel#sectionHeader {{ color: {FG_DIM}; font-weight: bold; font-size: 10px;
    padding: 6px 4px 2px 4px; }}

QPushButton {{ background: {BG_RAISED}; border: 1px solid {BORDER};
    border-radius: 4px; padding: 5px 10px; }}
QPushButton:hover {{ border-color: {ACCENT}; }}
QPushButton:pressed {{ background: {ACCENT_BG}; }}
QPushButton:disabled {{ color: {FG_DIM}; background: {BG_PANEL}; }}
QPushButton#accent {{ background: {ACCENT_BG}; color: {ACCENT}; font-weight: bold; }}

QListWidget, QTreeWidget {{ background: {BG_PANEL}; border: 1px solid {BORDER};
    border-radius: 4px; }}
QListWidget::item {{ padding: 2px; border-radius: 3px; }}
QListWidget::item:selected {{ background: {ACCENT_BG}; color: {ACCENT};
    border: 1px solid {ACCENT}; }}

QComboBox, QSpinBox, QDoubleSpinBox, QLineEdit {{ background: {BG_INPUT};
    border: 1px solid {BORDER}; border-radius: 4px; padding: 3px 6px; }}
QComboBox:hover, QSpinBox:hover, QDoubleSpinBox:hover {{ border-color: {ACCENT}; }}
QComboBox QAbstractItemView {{ background: {BG_INPUT}; border: 1px solid {BORDER};
    selection-background-color: {ACCENT_BG}; selection-color: {ACCENT}; }}

QSlider::groove:horizontal {{ height: 4px; background: {BG_INPUT};
    border-radius: 2px; }}
QSlider::sub-page:horizontal {{ background: {ACCENT}; border-radius: 2px; }}
QSlider::handle:horizontal {{ background: {FG}; width: 12px; height: 12px;
    margin: -5px 0; border-radius: 6px; }}
QSlider::handle:horizontal:hover {{ background: {ACCENT}; }}

QScrollBar:vertical {{ background: {BG}; width: 11px; margin: 0; }}
QScrollBar::handle:vertical {{ background: {BG_RAISED}; border-radius: 5px;
    min-height: 24px; }}
QScrollBar::handle:vertical:hover {{ background: {BORDER}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
QScrollBar:horizontal {{ background: {BG}; height: 11px; margin: 0; }}
QScrollBar::handle:horizontal {{ background: {BG_RAISED}; border-radius: 5px;
    min-width: 24px; }}

QToolTip {{ background: {BG_RAISED}; color: {FG}; border: 1px solid {ACCENT}; padding: 4px; }}
QMenu {{ background: {BG_PANEL}; border: 1px solid {BORDER}; }}
QMenu::item:selected {{ background: {ACCENT_BG}; color: {ACCENT}; }}
QCheckBox {{ spacing: 6px; }}
"""


def apply_theme(app) -> None:
    app.setStyleSheet(STYLESHEET)
