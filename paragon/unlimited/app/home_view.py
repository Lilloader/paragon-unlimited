"""Paragon Unlimited: the FE13 main window (the page with Chapters, Characters, Items, ...).

Every entry is a banner button: a colored tab on the left, a round icon, the name and an arrow.
The banners, frames and titles take their colors from the UI colors (Assets -> UI), so they
follow any preset. The colored tab of each banner has its own color: clicking the tab picks a
new one (right-click: back to the default). Tab colors are kept in paragon.json (pu_tab_colors)
and do not change with the UI colors.

FE13MainWidget (paragon/ui/controllers/fe13_main_widget.py) uses this as its view; the button
names (chapters_button, characters_button, ...) are the ones Paragon's controller connects.
"""
import math
from typing import Dict, Optional

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QPolygonF,
    QRadialGradient,
)
from PySide6.QtWidgets import QAbstractButton, QGridLayout, QHBoxLayout, QSizePolicy, QVBoxLayout, QWidget

# Default tab colors (the colored chevron on the left of each banner).
DEFAULT_TAB_COLORS: Dict[str, str] = {
    "chapters_button": "#4a90e2",
    "characters_button": "#8e5bd6",
    "items_button": "#d64545",
    "classes_button": "#d9a441",
    "skills_button": "#3fb89a",
    "scripts_button": "#4a90e2",
    "armies_button": "#d9a441",
    "tiles_button": "#3fb89a",
    "sprite_data_button": "#4a90e2",
    "gmap_button": "#8e5bd6",
    "endings_button": "#b04fc9",
    "renown_button": "#d9a441",
    "map_maker_button": "#3fae5a",
    "sprite_workshop_button": "#e07b39",
    "asset_definitions_button": "#4a90e2",
    "presets_button": "#3fb89a",
    "portraits_button": "#8e5bd6",
    "ui_colors_button": "#d6458f",
    "edit_dialogue_button": "#4a90e2",
    "quick_dialogue_button": "#d9a441",
    "configure_avatar_button": "#8e5bd6",
    "store_manager_button": "#3fb89a",
}

SERIF = ["Cambria", "Georgia", "Palatino Linotype", "Book Antiqua", "Times New Roman", "serif"]


def serif_font(pixel_size: int, bold: bool = False) -> QFont:
    f = QFont()
    f.setFamilies(SERIF)
    f.setPixelSize(max(8, int(pixel_size)))
    f.setBold(bold)
    return f


def _alpha(color: QColor, a: int) -> QColor:
    c = QColor(color)
    c.setAlpha(a)
    return c


def _star(p: QPainter, center: QPointF, r: float, color: QColor):
    """Small four-pointed star (the sparkle at the end of lines and banners)."""
    pts = []
    for i in range(8):
        rad = r if i % 2 == 0 else r * 0.28
        a = i * math.pi / 4
        pts.append(QPointF(center.x() + rad * math.cos(a), center.y() + rad * math.sin(a)))
    p.setPen(Qt.NoPen)
    p.setBrush(color)
    p.drawPolygon(QPolygonF(pts))


class BannerButton(QAbstractButton):
    """One entry of the main window: colored tab, round icon, name, arrow."""

    tabClicked = Signal(str)  # left click on the colored tab: pick a color
    tabReset = Signal(str)  # right click on the colored tab: default color

    def __init__(self, text: str, key: str, height: int = 52, parent=None):
        super().__init__(parent)
        self.key = key
        self.setText(text)
        self.setObjectName(key)
        self.tab_color = QColor(DEFAULT_TAB_COLORS.get(key, "#4a90e2"))
        self.banner_height = height
        self._pixmap: Optional[QPixmap] = None
        self._smooth = True
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(max(36, int(height * 0.72)))
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.setAttribute(Qt.WA_Hover, True)

    # Paragon's code calls setIcon / setIconSize on its buttons; keep those working.
    def setIcon(self, icon):
        super().setIcon(icon)
        pm = icon.pixmap(64, 64) if icon is not None and not icon.isNull() else None
        self._pixmap = pm if pm is not None and not pm.isNull() else None
        self.update()

    def set_pixel_art(self, pixel_art: bool):
        """Pixel art (map sprites, game icons) is scaled without smoothing."""
        self._smooth = not pixel_art
        self.update()

    def set_tab_color(self, color):
        self.tab_color = QColor(color)
        self.update()

    def sizeHint(self):
        return QSize(320, self.banner_height)

    # --- geometry
    def _geometry(self):
        full = QRectF(self.rect()).adjusted(2, 1, -4, -1)
        inset = full.height() * 0.11  # the round icon sticks out above and below the banner
        r = full.adjusted(0, inset, 0, -inset)
        h = r.height()
        cut = h * 0.34  # how far the pointed ends reach in
        tab_w = max(12.0, h * 0.32)
        return r, h, cut, tab_w

    def icon_rect(self) -> QRectF:
        """Where the icon goes (inside the round medallion), in this widget's coordinates."""
        r, h, cut, tab_w = self._geometry()
        radius = h * 0.58
        cx = r.left() + cut + tab_w * 0.75 + radius * 0.55
        side = radius * (1.55 if not self._smooth else 1.25)  # sprites fill more of the circle
        return QRectF(cx - side / 2, r.center().y() - side / 2, side, side)

    def _tab_hit(self, pos) -> bool:
        r, h, cut, tab_w = self._geometry()
        return pos.x() <= r.left() + cut + tab_w + 4

    def mousePressEvent(self, e):
        if self._tab_hit(e.position()):
            e.accept()
            if e.button() == Qt.LeftButton:
                self.tabClicked.emit(self.key)
            elif e.button() == Qt.RightButton:
                self.tabReset.emit(self.key)
            return
        super().mousePressEvent(e)

    def changeEvent(self, e):
        if e.type() in (e.Type.PaletteChange, e.Type.ApplicationPaletteChange):
            self.update()
        super().changeEvent(e)

    # --- painting
    def paintEvent(self, _e):
        pal = self.palette()
        base = pal.color(pal.ColorRole.Button)
        text = pal.color(pal.ColorRole.ButtonText)
        accent = pal.color(pal.ColorRole.Highlight)
        hover = self.underMouse()
        down = self.isDown()

        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        r, h, cut, tab_w = self._geometry()
        mid = r.center().y()
        x0, x1, top, bottom = r.left(), r.right(), r.top(), r.bottom()

        # banner body: pointed at both ends
        body = QPolygonF([
            QPointF(x0 + cut, top), QPointF(x1 - cut * 0.9, top), QPointF(x1, mid),
            QPointF(x1 - cut * 0.9, bottom), QPointF(x0 + cut, bottom), QPointF(x0, mid),
        ])
        g = QLinearGradient(0, top, 0, bottom)
        g.setColorAt(0, base.lighter(135 if hover else 122))
        g.setColorAt(0.5, base.lighter(108 if hover else 100))
        g.setColorAt(1, base.darker(135))
        if down:
            g.setColorAt(0, base.darker(110))
        p.setBrush(QBrush(g))
        p.setPen(QPen(_alpha(accent, 210 if hover else 95), 1.4))
        p.drawPolygon(body)
        # thin inner highlight along the top edge
        p.setPen(QPen(_alpha(QColor("#ffffff"), 28), 1))
        p.drawLine(QPointF(x0 + cut + 2, top + 2), QPointF(x1 - cut, top + 2))

        # colored tab: two chevrons following the left point
        def chevron(offset, width):
            return QPolygonF([
                QPointF(x0 + offset + cut, top + 1), QPointF(x0 + offset + cut + width, top + 1),
                QPointF(x0 + offset + width, mid), QPointF(x0 + offset + cut + width, bottom - 1),
                QPointF(x0 + offset + cut, bottom - 1), QPointF(x0 + offset, mid),
            ])

        tg = QLinearGradient(0, top, 0, bottom)
        tg.setColorAt(0, self.tab_color.lighter(130))
        tg.setColorAt(1, self.tab_color.darker(140))
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(tg))
        p.drawPolygon(chevron(0, tab_w * 0.62))
        p.setBrush(_alpha(self.tab_color.darker(110), 190))
        p.drawPolygon(chevron(tab_w * 0.7, tab_w * 0.36))

        # round icon medallion
        radius = h * 0.58
        cx = x0 + cut + tab_w * 0.75 + radius * 0.55
        center = QPointF(cx, mid)
        glow = QRadialGradient(center, radius * 1.35)
        glow.setColorAt(0.65, _alpha(self.tab_color, 90 if hover else 55))
        glow.setColorAt(1, _alpha(self.tab_color, 0))
        p.setBrush(glow)
        p.drawEllipse(center, radius * 1.35, radius * 1.35)
        mg = QRadialGradient(center - QPointF(radius * 0.3, radius * 0.4), radius * 1.4)
        mg.setColorAt(0, base.lighter(150))
        mg.setColorAt(1, base.darker(170))
        p.setBrush(mg)
        p.setPen(QPen(_alpha(accent, 235), max(1.6, h * 0.045)))
        p.drawEllipse(center, radius, radius)
        p.setPen(QPen(_alpha(self.tab_color.lighter(120), 150), 1))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(center, radius - h * 0.08, radius - h * 0.08)
        if self._pixmap is not None:
            if not self._smooth:  # game sprites are dark: a soft light behind them
                light = QRadialGradient(center, radius * 0.9)
                light.setColorAt(0, _alpha(self.tab_color.lighter(170), 150))
                light.setColorAt(1, _alpha(self.tab_color, 0))
                p.setPen(Qt.NoPen)
                p.setBrush(light)
                p.drawEllipse(center, radius * 0.9, radius * 0.9)
            target = self.icon_rect()
            p.setRenderHint(QPainter.SmoothPixmapTransform, self._smooth)
            pm = self._pixmap
            scale = min(target.width() / pm.width(), target.height() / pm.height())
            w, hh = pm.width() * scale, pm.height() * scale
            p.drawPixmap(QRectF(cx - w / 2, mid - hh / 2, w, hh), pm, QRectF(pm.rect()))

        # name
        text_left = cx + radius + h * 0.4
        arrow_x = x1 - cut * 0.9 - h * 0.25
        p.setFont(serif_font(h * 0.46))
        p.setPen(text if self.isEnabled() else _alpha(text, 110))
        p.drawText(QRectF(text_left, top, arrow_x - text_left - h * 0.2, h), Qt.AlignVCenter | Qt.AlignLeft,
                   self.text())

        # arrow and sparkle at the right point
        p.setPen(QPen(_alpha(text, 220 if hover else 170), max(1.4, h * 0.035), Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        a = h * 0.13
        p.drawPolyline(QPolygonF([QPointF(arrow_x - a * 0.6, mid - a), QPointF(arrow_x + a * 0.4, mid),
                                  QPointF(arrow_x - a * 0.6, mid + a)]))
        _star(p, QPointF(x1 - 2, mid), h * 0.09, _alpha(accent, 230 if hover else 170))
        p.end()


class SectionTitle(QWidget):
    """'Core Data' with a line ending in a small star; optional small icon before the text."""

    def __init__(self, text: str, size: int = 30, icon: Optional[QPixmap] = None, parent=None):
        super().__init__(parent)
        self.text = text
        self.size = size
        self.icon = icon
        self.setMinimumHeight(int(size * 1.5))
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def sizeHint(self):
        return QSize(300, int(self.size * 1.5))

    def paintEvent(self, _e):
        pal = self.palette()
        accent = pal.color(pal.ColorRole.Highlight)
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        x = 6.0
        h = self.height()
        if self.icon is not None and not self.icon.isNull():
            side = self.size * 1.05
            p.drawPixmap(QRectF(x, (h - side) / 2, side, side), self.icon, QRectF(self.icon.rect()))
            x += side + self.size * 0.4
        font = serif_font(self.size, bold=False)
        font.setLetterSpacing(QFont.PercentageSpacing, 103)
        p.setFont(font)
        p.setPen(accent.lighter(115))
        width = p.fontMetrics().horizontalAdvance(self.text)
        p.drawText(QRectF(x, 0, width + 4, h), Qt.AlignVCenter | Qt.AlignLeft, self.text)
        lx = x + width + self.size * 0.6
        end = min(self.width() - 12.0, lx + max(80.0, self.width() * 0.45))
        if end > lx + 20:
            g = QLinearGradient(lx, 0, end, 0)
            g.setColorAt(0, _alpha(accent, 220))
            g.setColorAt(1, _alpha(accent, 40))
            p.setPen(QPen(QBrush(g), 1.3))
            p.drawLine(QPointF(lx, h / 2), QPointF(end, h / 2))
            _star(p, QPointF(lx + (end - lx) * 0.42, h / 2), self.size * 0.22, accent.lighter(120))
        p.end()


class OrnateFrame(QWidget):
    """A box with a thin gold border and small corner ornaments (Assets, Misc.)."""

    def __init__(self, parent=None):
        super().__init__(parent)

    def paintEvent(self, _e):
        pal = self.palette()
        accent = pal.color(pal.ColorRole.Highlight)
        base = pal.color(pal.ColorRole.Window)
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        r = QRectF(self.rect()).adjusted(6, 6, -6, -6)
        g = QLinearGradient(0, r.top(), 0, r.bottom())
        g.setColorAt(0, base.lighter(118))
        g.setColorAt(1, base.darker(115))
        path = QPainterPath()
        path.addRoundedRect(r, 10, 10)
        p.fillPath(path, QBrush(g))
        p.setPen(QPen(_alpha(accent, 150), 1.3))
        p.drawPath(path)
        inner = r.adjusted(4, 4, -4, -4)
        p.setPen(QPen(_alpha(accent, 50), 1))
        p.drawRoundedRect(inner, 8, 8)
        # corner curls
        p.setPen(QPen(_alpha(accent, 200), 1.6))
        k = 14
        for (cx, cy, sx, sy) in ((r.left(), r.top(), 1, 1), (r.right(), r.top(), -1, 1),
                                 (r.left(), r.bottom(), 1, -1), (r.right(), r.bottom(), -1, -1)):
            p.setPen(QPen(_alpha(accent, 200), 1.6))
            p.setBrush(Qt.NoBrush)
            curl = QPainterPath(QPointF(cx + sx * 2, cy + sy * (k + 6)))
            curl.cubicTo(QPointF(cx - sx * 4, cy + sy * 4), QPointF(cx + sx * 4, cy - sy * 4),
                         QPointF(cx + sx * (k + 6), cy + sy * 2))
            p.drawPath(curl)
            _star(p, QPointF(cx + sx * 1, cy + sy * 1), 3.2, accent)
        p.end()


class Divider(QWidget):
    """Thin gold line with a star in the middle, between Core Data and the boxes below."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(22)

    def paintEvent(self, _e):
        accent = self.palette().color(self.palette().ColorRole.Highlight)
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        w, mid = self.width(), self.height() / 2
        g = QLinearGradient(0, 0, w, 0)
        g.setColorAt(0, _alpha(accent, 0))
        g.setColorAt(0.5, _alpha(accent, 200))
        g.setColorAt(1, _alpha(accent, 0))
        p.setPen(QPen(QBrush(g), 1.2))
        p.drawLine(QPointF(10, mid), QPointF(w - 10, mid))
        _star(p, QPointF(w / 2, mid), 7, accent.lighter(120))
        p.end()


class UnlimitedFE13MainView(QWidget):
    """The buttons and layout of the FE13 main window."""

    BANNERS = [  # (attribute, text, tooltip)
        ("chapters_button", "Chapters", None),
        ("characters_button", "Characters", None),
        ("items_button", "Items", None),
        ("classes_button", "Classes", None),
        ("skills_button", "Skills", None),
        ("scripts_button", "Scripts", None),
        ("armies_button", "Armies", None),
        ("tiles_button", "Tiles", None),
        ("sprite_data_button", "BMap / Sprite Data", None),
        ("gmap_button", "Chapter Placements / GMap", None),
        ("endings_button", "Endings", None),
        ("renown_button", "Renown", None),
        ("map_maker_button", "Paralogue Maker",
         "Make up to 9 new paralogues (and edit the units of any chapter): ready-made maps, enemies, "
         "boss, story and world map spot"),
        ("sprite_workshop_button", "Sprite Workshop",
         "Build map sprites from a head and a class body, in player / enemy / ally colors"),
        ("asset_definitions_button", "Asset Definitions", None),
        ("presets_button", "Presets", None),
        ("portraits_button", "Portraits", None),
        ("ui_colors_button", "UI", "Interface colors (does not change the game)"),
        ("edit_dialogue_button", "Edit Dialogue", None),
        ("quick_dialogue_button", "Quick Dialogue Generator", None),
        ("configure_avatar_button", "Configure Avatar", None),
        ("store_manager_button", "Store Manager", None),
    ]
    SMALL = {"asset_definitions_button", "presets_button", "portraits_button", "ui_colors_button",
             "edit_dialogue_button", "quick_dialogue_button", "configure_avatar_button", "store_manager_button"}

    def __init__(self):
        super().__init__()
        self.setAutoFillBackground(False)
        self.banners: Dict[str, BannerButton] = {}
        tab_hint = " (click the colored tab to change its color)"
        for key, text, tip in self.BANNERS:
            b = BannerButton(text, key, 50 if key in self.SMALL else 64)
            b.setToolTip((tip or text) + tab_hint)
            setattr(self, key, b)
            self.banners[key] = b

        def column(keys):
            col = QVBoxLayout()
            col.setSpacing(4)
            for k in keys:
                col.addWidget(self.banners[k])
            return col

        core = QGridLayout()
        core.setHorizontalSpacing(18)
        core.addLayout(column(["chapters_button", "characters_button", "items_button", "classes_button",
                               "skills_button", "scripts_button"]), 0, 0)
        core.addLayout(column(["armies_button", "tiles_button", "sprite_data_button", "gmap_button",
                               "endings_button", "renown_button"]), 0, 1)

        unlimited = QHBoxLayout()
        unlimited.setSpacing(18)
        unlimited.addWidget(self.map_maker_button)
        unlimited.addWidget(self.sprite_workshop_button)

        def box(title, keys):
            frame = OrnateFrame()
            lay = QVBoxLayout(frame)
            lay.setContentsMargins(22, 12, 22, 20)
            lay.setSpacing(3)
            lay.addWidget(SectionTitle(title, 22))
            for k in keys:
                lay.addWidget(self.banners[k])
            return frame

        bottom = QHBoxLayout()
        bottom.setSpacing(16)
        bottom.addWidget(box("Assets", ["asset_definitions_button", "presets_button", "portraits_button",
                                        "ui_colors_button"]))
        bottom.addWidget(box("Misc.", ["edit_dialogue_button", "quick_dialogue_button", "configure_avatar_button",
                                       "store_manager_button"]))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 10, 18, 14)
        layout.setSpacing(6)
        layout.addWidget(SectionTitle("Core Data", 30))
        layout.addLayout(core)
        layout.addSpacing(4)
        layout.addWidget(SectionTitle("Unlimited", 24))
        layout.addLayout(unlimited)
        layout.addWidget(Divider())
        layout.addLayout(bottom)
        layout.addStretch(1)

    def set_tab_colors(self, colors: Optional[Dict[str, str]]):
        for key, b in self.banners.items():
            b.set_tab_color((colors or {}).get(key) or DEFAULT_TAB_COLORS.get(key, "#4a90e2"))

    def paintEvent(self, _e):
        """Background: the UI background color, a little lighter at the top."""
        pal = self.palette()
        base = pal.color(pal.ColorRole.Window)
        p = QPainter(self)
        g = QLinearGradient(0, 0, 0, self.height())
        g.setColorAt(0, base.lighter(118))
        g.setColorAt(1, base.darker(112))
        p.fillRect(self.rect(), QBrush(g))
        p.end()

    def changeEvent(self, e):
        if e.type() in (e.Type.PaletteChange, e.Type.ApplicationPaletteChange):
            self.update()
        super().changeEvent(e)
