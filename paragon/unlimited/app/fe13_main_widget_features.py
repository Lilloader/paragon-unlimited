"""Paragon Unlimited: what the FE13 main window does beyond Paragon: the Paralogue Maker
(Map Maker), Sprite Workshop and UI buttons, the icons, the colored tabs and the UI colors.
The look itself is in home_view.py.
"""
import logging
from paragon.ui import utils


class FE13MainWidgetFeatures:
    """Mixed into FE13MainWidget (paragon/ui/controllers/fe13_main_widget.py)."""

    def _setup_home(self):
        self._apply_pu_icons()
        self.set_tab_colors(getattr(self.ms.config, "pu_tab_colors", None))
        for banner in self.banners.values():
            banner.tabClicked.connect(self._on_tab_color)
            banner.tabReset.connect(self._on_tab_color_reset)
        try:
            from paragon.unlimited.app import ui_theme

            ui_theme.register_main_window(self)
            colors = getattr(self.ms.config, "pu_ui_colors", None) or ui_theme.PRESETS[ui_theme.HOME_PRESET]
            ui_theme.apply(colors)
        except Exception:
            logging.exception("Could not apply UI colors to the main window.")
        try:  # the home page needs more room than Paragon's first window size
            w = self.main_window
            w.resize(max(w.width(), 1220), max(w.height(), 900))
        except Exception:
            pass

    def _apply_pu_icons(self):
        try:
            from paragon.unlimited.app import ui_icons

            icons = ui_icons.fe13_button_icons(self.gs, self.ms.config)
            for name, icon in icons.items():
                button = getattr(self, name, None)
                if button is not None and icon is not None:
                    button.setIcon(icon)
                    if hasattr(button, "set_pixel_art"):
                        button.set_pixel_art(name in ui_icons.PIXEL_ART and icon.cacheKey() not in ui_icons.DRAWN_KEYS)
        except Exception:
            logging.exception("Could not set button icons.")

    # --- colored tabs (their own colors; they do not follow the UI colors)
    def _save_tab_color(self, key, color):
        colors = dict(getattr(self.ms.config, "pu_tab_colors", None) or {})
        if color:
            colors[key] = color
        else:
            colors.pop(key, None)
        self.ms.config.pu_tab_colors = colors or None
        try:
            self.ms.config.save("paragon.json")
        except Exception:
            logging.exception("Could not save the tab colors.")
        self.set_tab_colors(self.ms.config.pu_tab_colors)

    def _on_tab_color(self, key):
        from PySide6.QtWidgets import QColorDialog

        banner = self.banners[key]
        color = QColorDialog.getColor(banner.tab_color, self, f"Tab color: {banner.text()}")
        if color.isValid():
            self._save_tab_color(key, color.name())

    def _on_tab_color_reset(self, key):
        self._save_tab_color(key, None)

    def _on_ui_colors(self):
        from paragon.unlimited.app.ui_colors_dialog import PUUIColorsDialog

        if not self.ui_colors_dialog:
            self.ui_colors_dialog = PUUIColorsDialog(self.ms)
        self.ui_colors_dialog.show()

    def _on_sprite_workshop(self):
        try:
            from paragon.unlimited.sprites.sprite_workshop_window import SpriteWorkshop

            if getattr(self, "sprite_workshop", None) is None:
                self.sprite_workshop = SpriteWorkshop(self.gs)
            self.sprite_workshop.show()
            self.sprite_workshop.raise_()
        except Exception:
            logging.exception("Could not open the Sprite Workshop.")
            utils.error(self)

    def _on_map_maker(self):
        try:
            from paragon.unlimited.map_maker.map_maker_window import MapMaker

            if getattr(self, "map_maker", None) is None:
                self.map_maker = MapMaker(self.gs, self.main_window)
            self.map_maker.show()
            self.map_maker.raise_()
            self.map_maker.activateWindow()
        except Exception:
            logging.exception("Could not open the Map Maker.")
            utils.error(self)
