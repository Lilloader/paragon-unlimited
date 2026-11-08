"""Paragon Unlimited - "UI" color settings (cosmetic only)."""
import logging

from PySide6.QtGui import QColor, QIcon
from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QComboBox, QPushButton, QColorDialog, QLabel

from paragon.unlimited.app import ui_theme


class PUColorButton(QPushButton):
    def __init__(self, color, on_change):
        super().__init__()
        self.on_change = on_change
        self.setFixedWidth(110)
        self.set_color(color)
        self.clicked.connect(self._pick)

    def set_color(self, color):
        self.color = QColor(color).name()
        text = "#000000" if QColor(self.color).lightness() > 140 else "#ffffff"
        self.setText(self.color)
        self.setStyleSheet(
            f"QPushButton {{ background-color: {self.color}; color: {text}; border: 1px solid #888; border-radius: 4px; padding: 3px; }}"
        )

    def _pick(self):
        c = QColorDialog.getColor(QColor(self.color), self, "Pick a color")
        if c.isValid():
            self.set_color(c.name())
            self.on_change()


class PUUIColorsDialog(QDialog):
    CUSTOM = "Custom"

    def __init__(self, ms, parent=None):
        super().__init__(parent)
        self.ms = ms
        self.setWindowTitle("Paragon Unlimited - UI Colors")
        self.setWindowIcon(QIcon("paragon.ico"))
        self._loading = True

        current = dict(getattr(ms.config, "pu_ui_colors", None) or ui_theme.PRESETS[ui_theme.HOME_PRESET])
        self.preset = QComboBox()
        for name in ui_theme.PRESETS:
            self.preset.addItem(name)
        self.preset.addItem(self.CUSTOM)

        form = QFormLayout()
        form.addRow("Preset", self.preset)
        self.buttons = {}
        for key in ui_theme.KEYS:
            b = PUColorButton(current.get(key, ui_theme.PRESETS[ui_theme.DEFAULT_PRESET][key]), self._on_color_changed)
            self.buttons[key] = b
            form.addRow(ui_theme.LABELS[key], b)

        reset_tabs = QPushButton("Reset the colored tabs")
        reset_tabs.setToolTip("Back to the default color of every banner's tab on the main window.\n"
                              "(One tab: click it on the main window to change it, right-click for its default.)")
        reset_tabs.clicked.connect(self._reset_tabs)

        note = QLabel("Only changes how Paragon Unlimited looks. Game files are never touched. The colored "
                      "tabs on the main window keep their own colors: click a tab to change it.")
        note.setWordWrap(True)

        close = QPushButton("Close")
        close.clicked.connect(self.accept)
        bottom = QHBoxLayout()
        bottom.addStretch(1)
        bottom.addWidget(close)

        layout = QVBoxLayout()
        layout.addLayout(form)
        layout.addWidget(reset_tabs)
        layout.addWidget(note)
        layout.addLayout(bottom)
        self.setLayout(layout)

        name = getattr(ms.config, "pu_ui_preset", None) or ui_theme.HOME_PRESET
        idx = self.preset.findText(name)
        self.preset.setCurrentIndex(idx if idx >= 0 else self.preset.findText(self.CUSTOM))
        self.preset.currentIndexChanged.connect(self._on_preset)
        self._loading = False

    def _reset_tabs(self):
        self.ms.config.pu_tab_colors = None
        try:
            self.ms.config.save("paragon.json")
        except Exception:
            logging.exception("Could not save the tab colors.")
        for w in list(ui_theme._main_windows):
            if hasattr(w, "set_tab_colors"):
                try:
                    w.set_tab_colors(None)
                except RuntimeError:
                    pass

    def colors(self):
        return {k: b.color for k, b in self.buttons.items()}

    def _on_preset(self):
        name = self.preset.currentText()
        if name in ui_theme.PRESETS:
            self._loading = True
            for k, v in ui_theme.PRESETS[name].items():
                self.buttons[k].set_color(v)
            self._loading = False
            self._apply(name)

    def _on_color_changed(self):
        if self._loading:
            return
        self._loading = True
        self.preset.setCurrentIndex(self.preset.findText(self.CUSTOM))
        self._loading = False
        self._apply(self.CUSTOM)

    def _apply(self, preset_name):
        colors = self.colors()
        ui_theme.apply(colors)
        try:
            self.ms.config.pu_ui_colors = colors
            self.ms.config.pu_ui_preset = preset_name
            self.ms.config.save("paragon.json")
        except Exception:
            logging.exception("Could not save UI colors.")
