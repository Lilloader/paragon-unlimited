"""Offscreen Qt test: Paragon Unlimited UI colors + main-window icons (no game files)."""
import os, sys, types
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
if os.path.isdir(r"C:\Windows\Fonts"):
    os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")  # real fonts in the renders
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.chdir(os.path.join(os.path.dirname(__file__), ".."))

from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QApplication

from paragon.unlimited.app import ui_theme
from paragon.unlimited.app import ui_icons
from paragon.unlimited.app.home_view import UnlimitedFE13MainView
from paragon.unlimited.app.ui_colors_dialog import PUUIColorsDialog


class FakeConfig:
    pu_ui_colors = None
    pu_ui_preset = None
    fe13_avatar = types.SimpleNamespace(portraits="FID_マイユニ_少女_顔立ちA")
    saved = 0

    def save(self, path):
        FakeConfig.saved += 1


def main():
    app = QApplication.instance() or QApplication([])
    os.makedirs("qt_out", exist_ok=True)
    for kind in ("flag", "grid", "sprite", "pin", "book", "code", "star", "cube", "sliders", "bubble", "bolt", "person",
                 "db", "palette", "frame", "scroll", "coins", "sword", "seal", "skill", "army", "x"):
        assert not ui_icons.drawn(kind).isNull(), kind
    gs = types.SimpleNamespace(data=types.SimpleNamespace(key_to_rid=lambda *a: None, int=lambda *a: None,
                                                          file_exists=lambda *a: False), icons=types.SimpleNamespace(model=lambda m: None),
                               portraits=types.SimpleNamespace(from_fsid=lambda f: None))
    icons = ui_icons.fe13_button_icons(gs, FakeConfig())
    assert len(icons) == 22 and all(not i.isNull() for i in icons.values())

    w = UnlimitedFE13MainView()
    assert set(icons) == set(w.banners), set(icons) ^ set(w.banners)
    for name, icon in icons.items():
        getattr(w, name).setIcon(icon)
    w.resize(1200, 880)

    ms = types.SimpleNamespace(config=FakeConfig())
    dlg = PUUIColorsDialog(ms)
    names = list(ui_theme.PRESETS)
    for i, name in list(enumerate(names))[1:] + [(0, names[0])]:
        dlg.preset.setCurrentText(name)
        assert app.palette().color(QPalette.Window).name() == ui_theme.PRESETS[name]["background"], name
        assert ms.config.pu_ui_colors["accent"] == ui_theme.PRESETS[name]["accent"]
        assert ms.config.pu_ui_preset == name
        w.grab().save(os.path.join("qt_out", f"main_{i}_{name.split()[0]}.png"))
    dlg.buttons["accent"].set_color("#ff00aa")
    dlg._on_color_changed()
    assert dlg.preset.currentText() == "Custom" and ms.config.pu_ui_colors["accent"] == "#ff00aa"
    dlg.grab().save(os.path.join("qt_out", "ui_colors_dialog.png"))
    assert FakeConfig.saved > 0

    # After changing colors, opening big new editor windows must still work quickly.
    import time
    from PySide6.QtWidgets import QWidget, QVBoxLayout, QGroupBox, QFormLayout, QLineEdit, QComboBox, QScrollArea
    ui_theme.register_main_window(w)
    ui_theme.apply(ui_theme.PRESETS["Midnight"])
    t0 = time.time()
    big = QWidget()
    lay = QVBoxLayout(big)
    for i in range(150):
        gb = QGroupBox(f"Support #{i:03}")
        f = QFormLayout(gb)
        f.addRow("Character", QComboBox())
        f.addRow("Type", QLineEdit())
        lay.addWidget(gb)
    sc = QScrollArea()
    sc.setWidget(big)
    sc.show()
    app.processEvents()
    dt = time.time() - t0
    print(f"big editor shown in {dt:.2f}s")
    assert dt < 10, dt
    assert app.styleSheet() == "", "no app-wide stylesheet"
    assert w.styleSheet() != ""
    sc.close()
    print("UI colors / icons Qt test: all checks passed")


if __name__ == "__main__":
    main()
