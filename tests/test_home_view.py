"""Offscreen Qt test: the FE13 main window (banners, colored tabs, icons, UI colors)."""
import os
import sys
import types

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
if os.path.isdir(r"C:\Windows\Fonts"):
    os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")  # real fonts in the renders
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.chdir(os.path.join(os.path.dirname(__file__), ".."))

from PySide6.QtCore import QEvent, QPointF, Qt  # noqa: E402
from PySide6.QtGui import QMouseEvent  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from paragon.unlimited.app import ui_icons, ui_theme  # noqa: E402
from paragon.unlimited.app.fe13_main_widget_features import FE13MainWidgetFeatures  # noqa: E402
from paragon.unlimited.app.home_view import DEFAULT_TAB_COLORS, UnlimitedFE13MainView  # noqa: E402


def check(cond, what):
    if not cond:
        raise AssertionError(what)


class Config:
    pu_ui_colors = None
    pu_ui_preset = None
    pu_tab_colors = None
    saved = 0

    def save(self, path):
        Config.saved += 1


class Home(FE13MainWidgetFeatures, UnlimitedFE13MainView):
    """The view with the Unlimited behavior, without Paragon's controller."""

    def __init__(self):
        super().__init__()
        self.ms = types.SimpleNamespace(config=Config())
        data = types.SimpleNamespace(key_to_rid=lambda *a: None, int=lambda *a: None, file_exists=lambda *a: False)
        self.gs = types.SimpleNamespace(data=data, icons=types.SimpleNamespace(model=lambda m: None))
        self.main_window = types.SimpleNamespace(width=lambda: 700, height=lambda: 450, resize=lambda *a: None)
        self._setup_home()


def click(widget, x, y, button=Qt.LeftButton):
    pos = QPointF(x, y)
    for kind in (QEvent.MouseButtonPress, QEvent.MouseButtonRelease):
        ev = QMouseEvent(kind, pos, widget.mapToGlobal(pos), button, button, Qt.NoModifier)
        QApplication.sendEvent(widget, ev)


def main():
    app = QApplication.instance() or QApplication([])
    os.makedirs("qt_out", exist_ok=True)
    w = Home()
    w.resize(1200, 880)
    w.show()
    app.processEvents()
    check(len(w.banners) == 22, len(w.banners))
    for key in ("chapters_button", "characters_button", "map_maker_button", "configure_avatar_button"):
        check(getattr(w, key) is w.banners[key], key)
    check(w.map_maker_button.text() == "Paralogue Maker", w.map_maker_button.text())
    check(all(b._pixmap is not None for b in w.banners.values()), "every banner has an icon")
    check(app.palette().color(app.palette().ColorRole.Window).name() == ui_theme.PRESETS[ui_theme.HOME_PRESET]["background"],
          "the home colors are used until the user picks UI colors")
    w.grab().save(os.path.join("qt_out", "home_0_default.png"))

    # tabs: left click on the tab asks for a color; a click on the rest opens the editor
    items = w.items_button
    picked, opened = [], []
    items.clicked.connect(lambda: opened.append(1))
    w._on_tab_color = lambda key: picked.append(key)  # stand-in for the color dialog
    items.tabClicked.disconnect()
    items.tabClicked.connect(w._on_tab_color)
    click(items, 8, items.height() / 2)
    check(picked == ["items_button"] and not opened, (picked, opened))
    click(items, items.width() / 2, items.height() / 2)
    check(opened == [1], "the banner itself still works")
    check(items.tab_color.name() == DEFAULT_TAB_COLORS["items_button"], "items tab is red by default")

    w._save_tab_color("items_button", "#00ff00")
    check(w.ms.config.pu_tab_colors == {"items_button": "#00ff00"} and items.tab_color.name() == "#00ff00", "saved")
    ui_theme.apply(ui_theme.PRESETS["Ember"])
    app.processEvents()
    check(items.tab_color.name() == "#00ff00", "the tab keeps its color when the UI colors change")
    w.grab().save(os.path.join("qt_out", "home_1_ember_green_items.png"))
    click(items, 8, items.height() / 2, Qt.RightButton)
    check(items.tab_color.name() == DEFAULT_TAB_COLORS["items_button"] and not w.ms.config.pu_tab_colors, "reset")
    check(Config.saved >= 2, "tab colors written to paragon.json")

    for name in ("Classic (Paragon dark)", "Plum & Gold"):
        ui_theme.apply(ui_theme.PRESETS[name])
        app.processEvents()
        w.grab().save(os.path.join("qt_out", f"home_{name.split()[0].lower()}.png"))
    ui_theme.apply(ui_theme.PRESETS[ui_theme.HOME_PRESET])
    w.resize(760, 640)
    app.processEvents()
    w.grab().save(os.path.join("qt_out", "home_small_window.png"))

    # without icons, plus where each icon goes: lets a preview with real game icons be put
    # together on a machine that has the game (game images are never part of the build)
    import json

    from PySide6.QtGui import QIcon, QPixmap

    w.resize(1200, 880)
    app.processEvents()
    for k, b in w.banners.items():
        b.setIcon(QIcon())
    app.processEvents()
    from paragon.unlimited.app.ui_icons import PIXEL_ART

    rects = {}
    for k, b in w.banners.items():
        b.set_pixel_art(k in PIXEL_ART)
        r = b.icon_rect()
        top_left = b.mapTo(w, r.topLeft().toPoint())
        rects[k] = [top_left.x(), top_left.y(), r.width(), r.height()]
    pm = QPixmap(4, 4)  # a stand-in "sprite" so the light behind sprites is drawn, then hidden
    pm.fill(Qt.transparent)
    for k in PIXEL_ART:
        w.banners[k].setIcon(QIcon(pm))
    app.processEvents()
    w.grab().save(os.path.join("qt_out", "home_no_icons.png"))
    with open(os.path.join("qt_out", "home_icon_rects.json"), "w") as f:
        json.dump(rects, f)

    # banner close-up with a pixel-art icon
    from PySide6.QtGui import QColor, QPixmap

    pm = QPixmap(28, 28)
    pm.fill(QColor("#c04040"))
    w.characters_button.setIcon(ui_icons.QIcon(pm))
    w.characters_button.set_pixel_art(True)
    w.resize(1200, 880)
    app.processEvents()
    w.characters_button.grab().save(os.path.join("qt_out", "home_banner.png"))
    w.close()
    print("home view test: all checks passed")


if __name__ == "__main__":
    main()
