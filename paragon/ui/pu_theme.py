"""Paragon Unlimited - UI color themes (cosmetic only; never touches game files)."""
import logging
from typing import Dict, Optional

from PySide6.QtGui import QPalette, QColor
from PySide6.QtWidgets import QApplication

KEYS = ("background", "panels", "buttons", "text", "accent")
LABELS = {
    "background": "Background",
    "panels": "Boxes / input fields",
    "buttons": "Buttons",
    "text": "Text",
    "accent": "Accent (selection, highlights)",
}

PRESETS: Dict[str, Dict[str, str]] = {
    "Classic (Paragon dark)": dict(background="#353535", panels="#232323", buttons="#353535", text="#ffffff", accent="#2a82da"),
    "Midnight": dict(background="#1e2230", panels="#161a24", buttons="#2a3042", text="#e6e9f0", accent="#7aa2f7"),
    "Plum & Gold": dict(background="#241b2f", panels="#1a1322", buttons="#33263f", text="#eee6f5", accent="#d4a64a"),
    "Forest": dict(background="#1d2621", panels="#151c18", buttons="#29352e", text="#e3eee6", accent="#6fcf97"),
    "Ember": dict(background="#2a1f1c", panels="#1f1714", buttons="#3a2b26", text="#f2e6df", accent="#f08a4b"),
    "Slate": dict(background="#2b2f33", panels="#212427", buttons="#383d42", text="#e8eaed", accent="#8ab4f8"),
    "Ocean": dict(background="#18262c", panels="#111c21", buttons="#22353d", text="#e0f0f4", accent="#4fc3d9"),
}
DEFAULT_PRESET = "Classic (Paragon dark)"


def _c(hex_str) -> QColor:
    return QColor(hex_str)


def build_palette(colors: Dict[str, str]) -> QPalette:
    bg, panels, buttons = _c(colors["background"]), _c(colors["panels"]), _c(colors["buttons"])
    text, accent = _c(colors["text"]), _c(colors["accent"])
    dim = QColor(text)
    dim.setAlpha(110)
    p = QPalette()
    p.setColor(QPalette.Window, bg)
    p.setColor(QPalette.WindowText, text)
    p.setColor(QPalette.Base, panels)
    p.setColor(QPalette.AlternateBase, bg)
    p.setColor(QPalette.ToolTipBase, panels)
    p.setColor(QPalette.ToolTipText, text)
    p.setColor(QPalette.PlaceholderText, dim)
    p.setColor(QPalette.Text, text)
    p.setColor(QPalette.Button, buttons)
    p.setColor(QPalette.ButtonText, text)
    p.setColor(QPalette.BrightText, QColor("#ff5555"))
    p.setColor(QPalette.Link, accent)
    p.setColor(QPalette.Highlight, accent)
    p.setColor(QPalette.HighlightedText, panels if accent.lightness() > 128 else text)
    p.setColor(QPalette.Light, buttons.lighter(130))
    p.setColor(QPalette.Midlight, buttons.lighter(115))
    p.setColor(QPalette.Mid, bg.darker(120))
    p.setColor(QPalette.Dark, bg.darker(150))
    p.setColor(QPalette.Shadow, QColor(0, 0, 0))
    for role in (QPalette.ButtonText, QPalette.WindowText, QPalette.Text):
        p.setColor(QPalette.Disabled, role, QColor(text).darker(220))
    p.setColor(QPalette.Disabled, QPalette.Light, bg)
    return p


def build_stylesheet(colors: Dict[str, str]) -> str:
    accent = colors["accent"]
    border = _c(colors["buttons"]).lighter(140).name()
    hover = _c(colors["buttons"]).lighter(120).name()
    return f"""
QPushButton {{
    background-color: {colors['buttons']};
    color: {colors['text']};
    border: 1px solid {border};
    border-radius: 5px;
    padding: 4px 10px;
}}
QPushButton:hover {{ background-color: {hover}; border-color: {accent}; }}
QPushButton:pressed {{ background-color: {accent}; }}
QPushButton:disabled {{ color: {_c(colors['text']).darker(220).name()}; }}
QGroupBox {{
    border: 1px solid {border};
    border-radius: 6px;
    margin-top: 14px;
    padding-top: 6px;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 4px;
    color: {accent};
    font-weight: bold;
}}
"""


_main_windows = []  # widgets that get the decorative stylesheet (main window only)


def register_main_window(widget):
    _main_windows.append(widget)


def apply(colors: Optional[Dict[str, str]], app: Optional[QApplication] = None):
    """Apply colors to the running app. None = original Paragon dark theme.

    Only the palette is changed app-wide (cheap and safe for every editor window). The
    decorative stylesheet (rounded buttons, colored box titles) is applied to the main
    window only. The Qt style itself is never switched at run time - doing that while
    windows exist can crash Qt.
    """
    app = app or QApplication.instance()
    if app is None:
        return
    try:
        full = dict(PRESETS[DEFAULT_PRESET])
        if colors:
            full.update({k: v for k, v in colors.items() if k in KEYS and v})
        app.setPalette(build_palette(full))
        sheet = build_stylesheet(full) if colors else ""
        alive = []
        for w in _main_windows:
            try:
                w.setStyleSheet(sheet)
                alive.append(w)
            except RuntimeError:
                pass  # window already deleted
        _main_windows[:] = alive
    except Exception:
        logging.exception("Could not apply UI colors.")
