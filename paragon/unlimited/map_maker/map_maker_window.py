"""Paragon Unlimited - Map Maker: make new chapters and edit any chapter's map in a few clicks.

Home page: your own chapters (and free chapter slots) as cards, plus "edit any chapter".
Editor page: the map with every unit drawn on it. Pick a tool, click the map, drag units around.
Everything else (story, enemies' difficulty, unlock, title) is on the left, in numbered steps.
"""
import copy
import logging
from typing import Dict, List, Optional, Tuple

from PySide6.QtCore import Qt, QRect, QPoint, QSize, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QIcon,
    QImage,
    QKeySequence,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QShortcut,
)
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QPlainTextEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSlider,
    QSpinBox,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from paragon.unlimited.map_maker import chapter_builder as cm
from paragon.unlimited.map_maker import map_maker_details as md

CELL = 36
TEAM_COLORS = {"player": QColor(70, 130, 255), "enemy": QColor(230, 60, 60), "ally": QColor(60, 190, 90),
               "join": QColor(40, 200, 230), "other": QColor(150, 150, 150)}
TEAM_FILES = {"player": "青", "enemy": "赤", "ally": "緑", "join": "青", "other": "赤"}
GREEN_BUTTON = "QPushButton { background: #2e8b57; color: white; font-weight: bold; padding: 8px 18px; border-radius: 6px; }"
BIG_BUTTON = "QPushButton { padding: 8px 14px; font-size: 13px; }"


def stars(tier: int) -> str:
    return "★" * tier + "☆" * (6 - tier)


def qimage_rgba(w: int, h: int, rgba: bytes) -> QImage:
    img = QImage(rgba, w, h, w * 4, QImage.Format_RGBA8888)
    return img.copy()


def render_title(label: str, title: str) -> bytes:
    """256x64 title card in the game's style: dark letters with a warm glow."""
    img = QImage(256, 64, QImage.Format_RGBA8888)
    img.fill(Qt.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.TextAntialiasing)

    def draw(text, size, y, max_w=240):
        if not text:
            return
        f = QFont("Georgia", size, QFont.Bold)
        f.setStyleStrategy(QFont.PreferAntialias)
        while size > 7:
            f.setPointSize(size)
            from PySide6.QtGui import QFontMetrics

            if QFontMetrics(f).horizontalAdvance(text) <= max_w:
                break
            size -= 1
        path = QPainterPath()
        from PySide6.QtGui import QFontMetrics

        w = QFontMetrics(f).horizontalAdvance(text)
        path.addText((256 - w) / 2, y, f, text)
        p.setPen(QPen(QColor(200, 120, 30, 230), 4, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.drawPath(path)
        p.setPen(QPen(QColor(255, 200, 90, 255), 1.5))
        p.drawPath(path)
        p.fillPath(path, QColor(25, 18, 10))

    draw(label, 11, 22)
    draw(title, 17, 52)
    p.end()
    ptr = img.constBits()
    return bytes(ptr)[: 256 * 64 * 4]


def render_banner(text: str):
    """The text of a mission banner (Seize / Survive) as the game draws its own: white bold
    letters on black, 256 x 32 (a PIL image)."""
    from PIL import Image
    from PySide6.QtGui import QFontMetrics

    w, h = 256, 32
    img = QImage(w, h, QImage.Format_RGBA8888)
    img.fill(QColor(0, 0, 0))
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.TextAntialiasing)
    f = QFont("Trebuchet MS")
    f.setBold(True)
    f.setStyleStrategy(QFont.PreferAntialias)
    size = 25
    while size > 10:
        f.setPixelSize(size)
        if QFontMetrics(f).horizontalAdvance(text) <= w - 10:
            break
        size -= 1
    fm = QFontMetrics(f)
    path = QPainterPath()
    path.addText((w - fm.horizontalAdvance(text)) / 2, (h + fm.ascent() - fm.descent()) / 2, f, text)
    p.fillPath(path, QColor(255, 255, 255))
    p.end()
    return Image.frombytes("RGBA", (w, h), bytes(img.constBits())[: w * h * 4])


# ----------------------------------------------------------------------------- sprites
class SpriteCache:
    def __init__(self, gs):
        self.gs = gs
        self.gd = gs.data
        self.cache: Dict[Tuple[str, str, str], Optional[QPixmap]] = {}

    def get(self, unit: cm.Unit) -> Optional[QPixmap]:
        team = TEAM_FILES.get(unit.team, "赤")
        key = (unit.job or "", unit.pid if unit.team in ("player", "join") else "", team)
        if key in self.cache:
            return self.cache[key]
        pix = None
        try:
            pix = self._load(unit, team)
        except Exception:
            logging.exception("Sprite for %s", unit.job)
        self.cache[key] = pix
        return pix

    def _load(self, unit: cm.Unit, team: str) -> Optional[QPixmap]:
        gd = self.gd
        job = gd.key_to_rid("jobs", unit.job) if unit.job else None
        if not job:
            return None
        icon = gd.rid(job, "bmap_icon")
        name = gd.string(icon, "name") if icon else None
        if not name:
            return None
        paths = []
        if unit.team in ("player", "join") and unit.pid.startswith("PID_"):
            paths.append(f"map/unit/{name[:-1]}{unit.pid[4:]}{team}.ctpk.lz")
        paths.append(f"map/unit/{name}{team}.ctpk.lz")
        for path in paths:
            if gd.file_exists(path, False):
                from paragon import paragon as pgn

                tex = pgn.read_ctpk(bytes(gd.read_file(path)))[0]
                rgba = bytes(pgn.increase_alpha(tex.pixel_data))
                img = qimage_rgba(tex.width, tex.height, rgba)
                fw, fh = 32, 32
                bm = gd.key_to_rid("bmap_icons", name)
                if bm:
                    fw = gd.int(bm, "frame_width") or 32
                    fh = gd.int(bm, "frame_height") or 32
                return QPixmap.fromImage(img.copy(0, 0, fw, fh))
        return None


# ----------------------------------------------------------------------------- the map
class MapCanvas(QWidget):
    unitSelected = Signal(object)
    changed = Signal(str)  # description of the change (for undo)
    hover = Signal(str)

    TOOLS = ("move", "enemy", "boss", "player", "join", "erase", "terrain", "treasure", "event")

    def __init__(self, maker_window):
        super().__init__()
        self.win = maker_window
        self.units: List[cm.Unit] = []
        self.grid = None  # (w, h, raw)
        self.background: Optional[QPixmap] = None
        self.tile_names: List[str] = []
        self.tool = "move"
        self.selected: Optional[cm.Unit] = None
        self.drag: Optional[cm.Unit] = None
        self.drag_pos: Optional[QPoint] = None
        self.drag_start: Optional[Tuple[int, int]] = None
        self.show_grid = True
        self.painting = False
        self.painted: Dict[Tuple[int, int], int] = {}
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMinimumSize(320, 320)

    def set_map(self, grid, minimap, tile_names):
        if grid:
            grid = (grid[0], grid[1], bytearray(grid[2]))
        self.grid = grid
        self.tile_names = tile_names
        self.background = None
        if grid and minimap:
            w, h, _ = grid
            mw, mh, rgba = minimap
            img = qimage_rgba(mw, mh, rgba)
            x0, y0 = max(0, 96 - 3 * w), max(0, 96 - 3 * h)
            crop = img.copy(x0, y0, min(6 * w, mw - x0), min(6 * h, mh - y0))
            self.background = QPixmap.fromImage(
                crop.scaled(w * CELL, h * CELL, Qt.IgnoreAspectRatio, Qt.SmoothTransformation))
        if grid:
            self.setFixedSize(grid[0] * CELL + 1, grid[1] * CELL + 1)
        self.update()

    def set_units(self, units):
        self.units = units
        if self.selected not in units:
            self.selected = None
        self.update()

    # helpers ---------------------------------------------------------------
    def cell_at(self, pos: QPoint) -> Tuple[int, int]:
        return pos.x() // CELL, pos.y() // CELL

    def unit_at(self, x: int, y: int) -> Optional[cm.Unit]:
        for u in reversed(self.units):
            if u.x == x and u.y == y and u.team != "other":
                return u
        return None

    def can_place(self, x, y, unit: Optional[cm.Unit], job=None) -> bool:
        if not self.grid:
            return False
        if not cm.ChapterMaker.can_stand(self.grid, x, y, job or (unit.job if unit else None)):
            return False
        other = self.unit_at(x, y)
        return other is None or other is unit

    def tile_name(self, x, y) -> str:
        if not self.grid:
            return ""
        w, h, raw = self.grid
        if 0 <= x < w and 0 <= y < h:
            t = raw[y * 32 + x]
            return self.tile_names[t] if t < len(self.tile_names) else str(t)
        return ""

    # painting --------------------------------------------------------------
    def paintEvent(self, _ev):
        p = QPainter(self)
        if self.background is not None:
            p.drawPixmap(0, 0, self.background)
        else:
            p.fillRect(self.rect(), QColor(60, 90, 60))
        if self.grid:
            w, h, _raw = self.grid
            if self.tool in ("enemy", "boss", "player", "join") or self.drag is not None:
                # shade the tiles nobody can stand on
                job = self.drag.job if self.drag else (
                    self.win.new_unit_job() if self.tool in ("enemy", "boss") else
                    self.win.join_job() if self.tool == "join" else None)
                for y in range(h):
                    for x in range(w):
                        if not cm.ChapterMaker.can_stand(self.grid, x, y, job):
                            p.fillRect(x * CELL, y * CELL, CELL, CELL, QColor(0, 0, 0, 90))
            if self.show_grid:
                p.setPen(QPen(QColor(255, 255, 255, 45), 1))
                for x in range(w + 1):
                    p.drawLine(x * CELL, 0, x * CELL, h * CELL)
                for y in range(h + 1):
                    p.drawLine(0, y * CELL, w * CELL, y * CELL)
        self._draw_marks(p)
        for u in self.units:
            if u is self.drag:
                continue
            self._draw_unit(p, u, u.x * CELL, u.y * CELL)
        if self.drag is not None and self.drag_pos is not None:
            x, y = self.cell_at(self.drag_pos)
            ok = self.can_place(x, y, self.drag)
            p.fillRect(x * CELL, y * CELL, CELL, CELL, QColor(80, 220, 80, 90) if ok else QColor(255, 40, 40, 110))
            p.setOpacity(0.85)
            self._draw_unit(p, self.drag, self.drag_pos.x() - CELL // 2, self.drag_pos.y() - CELL // 2)
            p.setOpacity(1.0)
        p.end()

    def _draw_marks(self, p: QPainter):
        """Painted tiles, chests / villages and tile events."""
        f = QFont(p.font())
        f.setPointSize(7)
        f.setBold(True)
        p.setFont(f)
        for (x, y), t in self.painted.items():
            p.fillRect(x * CELL, y * CELL, CELL, CELL, QColor(255, 140, 0, 70))
            p.setPen(QPen(QColor(255, 160, 40), 1, Qt.DashLine))
            p.setBrush(Qt.NoBrush)
            p.drawRect(x * CELL + 1, y * CELL + 1, CELL - 3, CELL - 3)
            name = self.tile_names[t] if t < len(self.tile_names) else str(t)
            p.setPen(QColor(255, 255, 255))
            p.drawText(QRect(x * CELL, y * CELL + CELL - 12, CELL, 12), Qt.AlignCenter, name[:6])
        plan = self.win.plan
        if plan is None:
            return
        for t in plan.treasures:
            col = QColor(230, 180, 40) if t.is_chest else QColor(120, 200, 120)
            r = QRect(t.x * CELL + CELL - 15, t.y * CELL + 2, 13, 12)
            p.setPen(QPen(QColor(0, 0, 0), 1))
            p.setBrush(col)
            p.drawRoundedRect(r, 3, 3)
            p.setPen(QColor(0, 0, 0))
            p.drawText(r, Qt.AlignCenter, "C" if t.is_chest else "V")
        st = plan.seize or []
        if plan.win == "seize" and len(st) == 2:
            sx, sy = st
            p.fillRect(sx * CELL, sy * CELL, CELL, CELL, QColor(170, 60, 230, 70))
            p.setPen(QPen(QColor(200, 110, 255), 2))
            p.setBrush(Qt.NoBrush)
            p.drawRect(sx * CELL + 1, sy * CELL + 1, CELL - 3, CELL - 3)
            p.setPen(QPen(QColor(255, 255, 255), 2))
            p.drawLine(sx * CELL + CELL - 12, sy * CELL + 4, sx * CELL + CELL - 12, sy * CELL + 18)
            p.fillRect(sx * CELL + CELL - 11, sy * CELL + 4, 8, 6, QColor(200, 110, 255))
        for e in plan.tile_events:
            r = QRect(e.x * CELL + 2, e.y * CELL + CELL - 15, 13, 13)
            p.setPen(QPen(QColor(0, 0, 0), 1))
            p.setBrush(QColor(220, 80, 220))
            p.drawEllipse(r)
            p.setPen(QColor(255, 255, 255))
            p.drawText(r, Qt.AlignCenter, "!")

    def _draw_unit(self, p: QPainter, u: cm.Unit, px: int, py: int):
        col = TEAM_COLORS.get(u.team, QColor(200, 200, 200))
        if u.team == "player" and not u.pid:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(col.red(), col.green(), col.blue(), 120))
            p.drawRoundedRect(px + 3, py + 3, CELL - 6, CELL - 6, 6, 6)
        pix = self.win.sprites.get(u) if u.job else None
        if pix is not None:
            target = QRect(px + (CELL - pix.width()) // 2, py + CELL - pix.height() - 1, pix.width(), pix.height())
            p.drawPixmap(target, pix)
        else:
            p.setPen(QPen(col.darker(150), 2))
            p.setBrush(col)
            p.drawEllipse(px + 7, py + 7, CELL - 14, CELL - 14)
        if u.team == "player" and not pix:
            p.setPen(QColor(255, 255, 255))
            f = p.font()
            f.setBold(True)
            p.setFont(f)
            p.drawText(QRect(px, py, CELL, CELL), Qt.AlignCenter, "P")
        if u.team == "join":  # joins your army: cyan frame with a star
            p.setPen(QPen(TEAM_COLORS["join"], 2))
            p.setBrush(Qt.NoBrush)
            p.drawRect(px + 1, py + 1, CELL - 2, CELL - 2)
            p.fillRect(px + 1, py + 1, 13, 12, TEAM_COLORS["join"])
            p.setPen(QColor(0, 0, 0))
            f = QFont(p.font())
            f.setPointSize(7)
            f.setBold(True)
            p.setFont(f)
            p.drawText(QRect(px + 1, py + 1, 13, 12), Qt.AlignCenter, "★")
        if u.boss:
            p.setPen(QPen(QColor(255, 215, 0), 2))
            p.setBrush(Qt.NoBrush)
            p.drawRect(px + 1, py + 1, CELL - 2, CELL - 2)
            p.fillRect(px + 1, py + 1, 14, 11, QColor(255, 215, 0))
            p.setPen(QColor(0, 0, 0))
            f = QFont(p.font())
            f.setPointSize(6)
            f.setBold(True)
            p.setFont(f)
            p.drawText(QRect(px + 1, py + 1, 14, 11), Qt.AlignCenter, "B")
        if u is self.selected:
            p.setPen(QPen(QColor(255, 255, 255), 2, Qt.DashLine))
            p.setBrush(Qt.NoBrush)
            p.drawRect(px + 1, py + 1, CELL - 2, CELL - 2)

    # mouse -----------------------------------------------------------------
    def mousePressEvent(self, ev):
        x, y = self.cell_at(ev.position().toPoint())
        u = self.unit_at(x, y)
        if ev.button() == Qt.RightButton:
            if u is not None:
                self.win.remove_unit(u)
            return
        if ev.button() != Qt.LeftButton:
            return
        if self.win.seize_pick.isChecked():
            self.win.seize_picked(x, y)
            return
        if self.tool == "erase":
            if u is not None:
                self.win.remove_unit(u)
            return
        if self.tool == "terrain":
            self.win.before_change("Paint terrain")
            self.painting = True
            self.win.paint_tile(x, y)
            return
        if self.tool == "treasure":
            self.win.treasure_clicked(x, y)
            return
        if self.tool == "event":
            self.win.event_tile_clicked(x, y)
            return
        if self.tool in ("enemy", "boss", "player", "join") and u is None:
            self.win.add_unit(self.tool, x, y)
            return
        if u is not None:
            self.selected = u
            self.unitSelected.emit(u)
            self.drag = u
            self.drag_start = (u.x, u.y)
            self.drag_pos = ev.position().toPoint()
        else:
            self.selected = None
            self.unitSelected.emit(None)
        self.update()

    def mouseMoveEvent(self, ev):
        pos = ev.position().toPoint()
        x, y = self.cell_at(pos)
        if self.drag is not None:
            self.drag_pos = pos
            self.update()
        if self.painting and ev.buttons() & Qt.LeftButton:
            self.win.paint_tile(x, y)
        u = self.unit_at(x, y)
        text = f"({x}, {y}) {self.tile_name(x, y)}"
        if u is not None:
            text += " - " + self.win.describe(u)
        text += self.win.marks_text(x, y)
        self.hover.emit(text)

    def mouseReleaseEvent(self, ev):
        if self.painting:
            self.painting = False
            self.win.paint_done()
            return
        if self.drag is None:
            return
        x, y = self.cell_at(ev.position().toPoint())
        u = self.drag
        self.drag = None
        self.drag_pos = None
        if (x, y) != self.drag_start and self.can_place(x, y, u):
            self.win.before_change("Move unit")
            u.x, u.y = x, y
            self.changed.emit("move")
        self.update()

    def keyPressEvent(self, ev):
        if ev.key() in (Qt.Key_Delete, Qt.Key_Backspace) and self.selected is not None:
            self.win.remove_unit(self.selected)
            return
        super().keyPressEvent(ev)


# ----------------------------------------------------------------------------- template gallery
class TemplateGallery(QDialog):
    def __init__(self, maker: cm.ChapterMaker, current: str = "", parent=None):
        super().__init__(parent)
        self.maker = maker
        self.setWindowTitle("Choose a map")
        self.resize(980, 680)
        self.chosen: Optional[str] = None
        self.list = QListWidget()
        self.list.setViewMode(QListWidget.IconMode)
        self.list.setIconSize(QSize(150, 150))
        self.list.setGridSize(QSize(200, 230))
        self.list.setResizeMode(QListWidget.Adjust)
        self.list.setMovement(QListWidget.Static)
        self.list.setWordWrap(True)
        self.list.setSpacing(6)
        self.list.itemDoubleClicked.connect(lambda _i: self.accept())
        self.filter_tag = QComboBox()
        self.filter_tag.addItem("All kinds of maps", "")
        tags = sorted({t for m in maker.templates.maps.values() for t in m.get("tags", [])})
        for t in tags:
            self.filter_tag.addItem(t, t)
        self.filter_tier = QComboBox()
        self.filter_tier.addItem("Any difficulty", 0)
        for t, info in cm.TIERS.items():
            self.filter_tier.addItem(f"{stars(t)}  {info['name']}", t)
        self.filter_tag.currentIndexChanged.connect(self._fill)
        self.filter_tier.currentIndexChanged.connect(self._fill)
        self.note = QLabel()
        self.note.setWordWrap(True)
        top = QHBoxLayout()
        top.addWidget(QLabel("Show:"))
        top.addWidget(self.filter_tag)
        top.addWidget(self.filter_tier)
        top.addStretch(1)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("Use this map")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("<b>Pick a map.</b> Every map comes with player starts and enemies; "
                             "you can change all of them afterwards. Double-click to choose."))
        lay.addLayout(top)
        lay.addWidget(self.list, 1)
        lay.addWidget(self.note)
        lay.addWidget(buttons)
        self.current = current
        self._fill()

    def _fill(self):
        self.list.clear()
        tag = self.filter_tag.currentData()
        tier = self.filter_tier.currentData()
        missing_dlc = 0
        for m in sorted(self.maker.templates.maps.values(), key=lambda m: (m.get("source") != "base", m["id"])):
            if tag and tag not in m.get("tags", []):
                continue
            if tier and m.get("tier") != tier:
                continue
            ok = self.maker.template_available(m["id"])
            if not ok:
                missing_dlc += m.get("source") == "dlc"
                continue
            mini = self.maker.minimap(m["id"])
            icon = QIcon()
            if mini:
                w, h = m["size"]
                img = qimage_rgba(*mini)
                x0, y0 = max(0, 96 - 3 * w), max(0, 96 - 3 * h)
                icon = QIcon(QPixmap.fromImage(img.copy(x0, y0, 6 * w, 6 * h).scaled(150, 150, Qt.KeepAspectRatio,
                                                                                       Qt.SmoothTransformation)))
            text = (f"{m.get('label', '')}\n{m.get('title', m['id'])}\n{stars(m.get('tier', 3))}\n"
                    f"{', '.join(m.get('tags', []))} - {len(m['enemies'])} enemies")
            it = QListWidgetItem(icon, text)
            it.setData(Qt.UserRole, m["id"])
            it.setToolTip(f"{m['size'][0]} x {m['size'][1]} tiles, {len(m['players'])} player units, "
                          f"{len(m['enemies'])} enemies ({cm.THEMES.get(m.get('theme'), {}).get('name', '')})")
            self.list.addItem(it)
            if m["id"] == self.current:
                self.list.setCurrentItem(it)
        self.note.setText(
            f"{missing_dlc} DLC maps are hidden: import your DLC first (Unlimited -> Import DLC Maps)." if missing_dlc else "")

    def accept(self):
        it = self.list.currentItem()
        if it is None:
            return
        self.chosen = it.data(Qt.UserRole)
        super().accept()


# ----------------------------------------------------------------------------- conversation editor
class ConversationEditor(QWidget):
    """Lines of a conversation: who talks, their expression, and the text in a multi-line box.

    Enter = new row in the text box, an empty row = new text box. Under each line the preview
    shows the text boxes exactly as the game will show them (two rows of ~38 characters)."""

    changed = Signal()

    def __init__(self, speakers: List[Tuple[str, str]], big_button: bool = True):
        super().__init__()
        self.speakers = speakers
        self.rows: List[Tuple[QComboBox, QComboBox, QPlainTextEdit, QWidget, QLabel]] = []
        self.box = QVBoxLayout()
        self.box.setContentsMargins(0, 0, 0, 0)
        add = QPushButton("+ Add a line")
        add.clicked.connect(lambda: (self.add_line(cm.Line(self._next_speaker(), "Normal", ""), focus=True),
                                     self.changed.emit()))
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        hint = QLabel("<small>Enter = new row, an empty row = new text box. Long rows wrap by themselves; "
                      "the grey boxes show how the game will split the text.</small>")
        hint.setWordWrap(True)
        lay.addWidget(hint)
        lay.addLayout(self.box)
        bottom = QHBoxLayout()
        bottom.addWidget(add)
        if big_button:
            big = QPushButton("Open in a big window...")
            big.setToolTip("See and edit the whole conversation in a larger window")
            big.clicked.connect(self._open_big)
            bottom.addWidget(big)
        bottom.addStretch(1)
        lay.addLayout(bottom)

    def _next_speaker(self) -> str:
        """The one who did not talk last (conversations go back and forth)."""
        if len(self.rows) >= 2:
            return self.rows[-2][0].currentData()
        return self.rows[-1][0].currentData() if self.rows else "クロム"

    def set_lines(self, lines: List[cm.Line]):
        for row in self.rows:
            row[3].deleteLater()
        self.rows = []
        for l in lines:
            self.add_line(l)

    def add_line(self, line: cm.Line, focus: bool = False):
        row = QFrame()
        row.setFrameShape(QFrame.StyledPanel)
        v = QVBoxLayout(row)
        v.setContentsMargins(4, 4, 4, 4)
        v.setSpacing(2)
        h = QHBoxLayout()
        h.setContentsMargins(0, 0, 0, 0)
        who = QComboBox()
        who.setMaximumWidth(170)
        for name, code in self.speakers:
            who.addItem(name, code)
        i = who.findData(line.speaker)
        if i < 0:
            who.addItem(line.speaker, line.speaker)
            i = who.count() - 1
        who.setCurrentIndex(i)
        mood = QComboBox()
        mood.addItems(list(cm.MOODS))
        mood.setCurrentText(line.mood if line.mood in cm.MOODS else "Normal")
        up = QToolButton()
        up.setText("▲")
        up.setToolTip("Move this line up")
        rm = QToolButton()
        rm.setText("✕")
        rm.setToolTip("Remove this line")
        h.addWidget(who)
        h.addWidget(mood)
        h.addStretch(1)
        h.addWidget(up)
        h.addWidget(rm)
        text = QPlainTextEdit(line.text)
        text.setPlaceholderText("What they say...")
        text.setTabChangesFocus(True)
        preview = QLabel()
        preview.setTextFormat(Qt.RichText)
        preview.setWordWrap(False)
        v.addLayout(h)
        v.addWidget(text)
        v.addWidget(preview)
        entry = (who, mood, text, row, preview)
        rm.clicked.connect(lambda: self._remove(entry))
        up.clicked.connect(lambda: self._move_up(entry))
        for w in (who, mood):
            w.currentIndexChanged.connect(self.changed.emit)
        text.textChanged.connect(lambda: (self._refresh(entry), self.changed.emit()))
        self.rows.append(entry)
        self.box.addWidget(row)
        self._refresh(entry)
        if focus:
            text.setFocus()

    def _refresh(self, entry):
        text, preview = entry[2], entry[4]
        rows = max(2, min(8, text.toPlainText().count("\n") + 2))
        text.setFixedHeight(text.fontMetrics().lineSpacing() * rows + 12)
        boxes = cm.text_boxes(text.toPlainText())
        if not boxes:
            preview.setText("")
            preview.setVisible(False)
            return
        import html

        cells = "".join(
            "<td style='border:1px solid #888; padding:2px 6px; background:rgba(128,128,128,40);'>"
            + "<br>".join(html.escape(r) for r in b) + "</td>" for b in boxes)
        preview.setText(f"<table cellspacing='4' style='font-family:Consolas,monospace; font-size:8pt; "
                        f"color:#888;'><tr>{cells}</tr></table>"
                        f"<small style='color:#888'>{len(boxes)} text box{'es' if len(boxes) > 1 else ''}</small>")
        preview.setVisible(True)

    def _remove(self, entry):
        if entry in self.rows:
            self.rows.remove(entry)
            entry[3].deleteLater()
            self.changed.emit()

    def _move_up(self, entry):
        i = self.rows.index(entry) if entry in self.rows else -1
        if i <= 0:
            return
        lines = self.lines(keep_empty=True)
        lines[i - 1], lines[i] = lines[i], lines[i - 1]
        self.set_lines(lines)
        self.changed.emit()

    def _open_big(self):
        d = QDialog(self)
        d.setWindowTitle("Conversation")
        d.resize(900, 760)
        lay = QVBoxLayout(d)
        ed = ConversationEditor(self.speakers, big_button=False)
        ed.set_lines(self.lines(keep_empty=True))
        sc = QScrollArea()
        sc.setWidgetResizable(True)
        sc.setWidget(ed)
        lay.addWidget(sc, 1)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(d.accept)
        bb.rejected.connect(d.reject)
        lay.addWidget(bb)
        if d.exec() == QDialog.Accepted:
            self.set_lines(ed.lines(keep_empty=True))
            self.changed.emit()

    def lines(self, keep_empty: bool = False) -> List[cm.Line]:
        out = []
        for w, m, t, _r, _p in self.rows:
            text = t.toPlainText().rstrip()
            if text.strip() or keep_empty:
                out.append(cm.Line(w.currentData(), m.currentText(), text))
        return out


# ----------------------------------------------------------------------------- the window
class MapMaker(QMainWindow):
    def __init__(self, gs, main_window=None):
        super().__init__()
        self.gs = gs
        self.main_window = main_window
        self.setWindowTitle("Paragon Unlimited - Map Maker")
        self.setWindowIcon(QIcon("paragon.ico"))
        self.resize(1360, 860)
        self._pu_help_topic = "map_maker"
        out = gs.project.output_path
        dlc_original = None
        try:
            from paragon.unlimited.map_maker import dlc_maps

            dlc_original = str(dlc_maps.workspace(out) / "original")
        except Exception:
            pass
        self.maker = getattr(gs, "pu_chapter_maker", None)
        if self.maker is None:
            self.maker = cm.ChapterMaker(gs.data, cm.Templates.load(), out, dlc_original)
            gs.pu_chapter_maker = self.maker
        self.maker.banner_renderer = render_banner
        self.sprites = SpriteCache(gs)
        self.plan: Optional[cm.ChapterPlan] = None
        self.made_here = False
        self.dirty = False
        self.undo_stack: List[list] = []
        self.redo_stack: List[list] = []
        self.mode = "Normal"
        self._loading = False

        self.pages = QStackedWidget()
        self.home = self._build_home()
        self.editor = self._build_editor()
        self.pages.addWidget(self.home)
        self.pages.addWidget(self.editor)
        self.setCentralWidget(self.pages)
        QShortcut(QKeySequence.Undo, self, self.undo)
        QShortcut(QKeySequence.Redo, self, self.redo)
        QShortcut(QKeySequence.Save, self, self.save)
        self.refresh_home()
        try:
            from paragon.unlimited.app import window_memory

            window_memory.remember_window(self, "map_maker")
        except Exception:
            pass

    # ================================================================== home page
    def _build_home(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        title = QLabel("<h1>Map Maker</h1>")
        intro = QLabel(
            "Make brand-new chapters for your mod, or move the units of any chapter around. "
            "Click a card to start. Press <b>F1</b> any time for a step-by-step tutorial.")
        intro.setWordWrap(True)
        self.slot_info = QLabel()
        self.slot_info.setWordWrap(True)
        self.cards = QGridLayout()
        self.cards.setSpacing(12)
        cards_w = QWidget()
        cards_w.setLayout(self.cards)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(cards_w)
        self.fill_button = QPushButton("Fill every empty slot with a ready-to-play chapter")
        self.fill_button.setStyleSheet(BIG_BUTTON)
        self.fill_button.clicked.connect(self.fill_all)
        existing = QGroupBox("Edit the map of any chapter")
        eh = QHBoxLayout(existing)
        self.chapter_pick = QComboBox()
        self.chapter_pick.setMinimumWidth(380)
        open_btn = QPushButton("Open map")
        open_btn.setStyleSheet(BIG_BUTTON)
        open_btn.clicked.connect(lambda: self.open_chapter(self.chapter_pick.currentData()))
        eh.addWidget(QLabel("Chapter:"))
        eh.addWidget(self.chapter_pick, 1)
        eh.addWidget(open_btn)
        lay.addWidget(title)
        lay.addWidget(intro)
        lay.addWidget(self.slot_info)
        lay.addWidget(scroll, 1)
        row = QHBoxLayout()
        row.addWidget(self.fill_button)
        row.addStretch(1)
        lay.addLayout(row)
        lay.addWidget(existing)
        return w

    def refresh_home(self):
        while self.cards.count():
            it = self.cards.takeAt(0)
            card = it.widget()
            if card is not None:
                card.hide()
                card.deleteLater()
        own = self.maker.custom_chapters()
        free = self.maker.free_rows()
        total = len(own) + free
        self.slot_info.setText(
            f"<b>Your chapters: {len(own)} of {total}.</b> The game's save file has room for "
            f"{cm.MAX_CHAPTERS} chapters and the game uses {cm.GAME_CHAPTERS}, so every mod can add "
            f"{cm.MAX_CHAPTERS - cm.GAME_CHAPTERS}. "
            + (f"{free} empty slot(s) left." if free else "All slots are used."))
        col = 0
        row = 0
        for c in own:
            self.cards.addWidget(self._card(c["cid"], c["name"], made=c["made_here"]), row, col)
            col += 1
            if col == 4:
                col, row = 0, row + 1
        nxt = self.maker.next_slot_id()
        for i in range(free):
            self.cards.addWidget(self._empty_card(nxt if i == 0 else None), row, col)
            col += 1
            if col == 4:
                col, row = 0, row + 1
        self.fill_button.setEnabled(free > 0 and nxt is not None)
        self.chapter_pick.clear()
        for cid, name in self.maker.story_chapters():
            self.chapter_pick.addItem(name, cid)

    def _thumb(self, cid: str, size=160) -> Optional[QPixmap]:
        mini = self.maker.minimap(cid)
        grid = self.maker.grid(cid)
        if not mini:
            return None
        img = qimage_rgba(*mini)
        if grid:
            w, h, _ = grid
            img = img.copy(max(0, 96 - 3 * w), max(0, 96 - 3 * h), 6 * w, 6 * h)
        return QPixmap.fromImage(img.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def _card(self, cid, name, made) -> QWidget:
        f = QFrame()
        f.setFrameShape(QFrame.StyledPanel)
        f.setMinimumWidth(230)
        v = QVBoxLayout(f)
        pic = QLabel()
        pic.setAlignment(Qt.AlignCenter)
        t = self._thumb(cid)
        if t:
            pic.setPixmap(t)
        v.addWidget(pic)
        lab = QLabel(f"<b>{name}</b><br><small>{cid}{' - made with the Map Maker' if made else ''}</small>")
        lab.setWordWrap(True)
        v.addWidget(lab)
        b = QPushButton("Edit")
        b.setStyleSheet(BIG_BUTTON)
        b.clicked.connect(lambda: self.open_chapter(cid))
        v.addWidget(b)
        if cid not in cm.GAME_CIDS:
            row = QHBoxLayout()
            clear = QPushButton("Clear (start over)")
            clear.setToolTip("Wipe this chapter: pick a map and start again with fresh units, story and events.\n"
                             "The slot stays yours.")
            clear.clicked.connect(lambda: self.clear_chapter(cid))
            row.addWidget(clear)
            delete = QPushButton("Delete")
            delete.setToolTip("Take this chapter out of the game (its spot on the world map too).")
            delete.clicked.connect(lambda: self.delete_chapter(cid))
            row.addWidget(delete)
            v.addLayout(row)
        return f

    def _empty_card(self, slot: Optional[str]) -> QWidget:
        f = QFrame()
        f.setFrameShape(QFrame.StyledPanel)
        f.setMinimumWidth(230)
        f.setMinimumHeight(240)
        v = QVBoxLayout(f)
        lab = QLabel("<h3>Empty slot</h3>A new chapter goes here.")
        lab.setAlignment(Qt.AlignCenter)
        lab.setWordWrap(True)
        v.addStretch(1)
        v.addWidget(lab)
        b = QPushButton("+ Make a new chapter")
        b.setStyleSheet(GREEN_BUTTON)
        b.setEnabled(slot is not None)
        b.clicked.connect(self.new_chapter)
        v.addWidget(b)
        v.addStretch(1)
        return f

    # ================================================================== editor page
    def _build_editor(self) -> QWidget:
        w = QWidget()
        outer = QVBoxLayout(w)
        bar = QHBoxLayout()
        back = QPushButton("← My chapters")
        back.clicked.connect(self.go_home)
        self.undo_btn = QPushButton("Undo")
        self.undo_btn.clicked.connect(self.undo)
        self.redo_btn = QPushButton("Redo")
        self.redo_btn.clicked.connect(self.redo)
        self.save_btn = QPushButton("Save chapter")
        self.save_btn.setStyleSheet(GREEN_BUTTON)
        self.save_btn.clicked.connect(self.save)
        self.play_btn = QPushButton("Save + copy to emulator")
        self.play_btn.setToolTip("Save the chapter and put your mod into Azahar so you can play it right away")
        self.play_btn.clicked.connect(self.save_and_play)
        help_btn = QPushButton("Help / Tutorial")
        help_btn.clicked.connect(self._help)
        self.editor_title = QLabel()
        self.editor_title.setStyleSheet("font-size: 16px; font-weight: bold;")
        bar.addWidget(back)
        bar.addWidget(self.editor_title, 1)
        bar.addWidget(self.undo_btn)
        bar.addWidget(self.redo_btn)
        bar.addWidget(help_btn)
        bar.addWidget(self.play_btn)
        bar.addWidget(self.save_btn)
        outer.addLayout(bar)

        body = QHBoxLayout()
        outer.addLayout(body, 1)

        # ---------------- left: steps
        self.step_name = QGroupBox("1. Name your chapter")
        fn = QFormLayout(self.step_name)
        self.title_edit = QLineEdit()
        self.label_edit = QLineEdit()
        self.label_edit.setPlaceholderText("e.g. Paralogue 25 or Side Story")
        self.desc_edit = QLineEdit()
        self.desc_edit.setPlaceholderText("One line shown on the world map")
        fn.addRow("Title:", self.title_edit)
        fn.addRow("Small text above it:", self.label_edit)
        fn.addRow("Description:", self.desc_edit)
        for e in (self.title_edit, self.label_edit, self.desc_edit):
            e.textEdited.connect(self._touched)

        self.step_map = QGroupBox("2. Map")
        fm = QVBoxLayout(self.step_map)
        self.map_label = QLabel()
        self.map_label.setWordWrap(True)
        pick_map = QPushButton("Choose a different map...")
        pick_map.setStyleSheet(BIG_BUTTON)
        pick_map.clicked.connect(self.choose_map)
        fm.addWidget(self.map_label)
        fm.addWidget(pick_map)

        self.step_enemies = QGroupBox("3. Enemies")
        fe = QFormLayout(self.step_enemies)
        self.theme_combo = QComboBox()
        for k, t in cm.THEMES.items():
            self.theme_combo.addItem(t["name"], k)
        self.tier_slider = QSlider(Qt.Horizontal)
        self.tier_slider.setRange(1, 6)
        self.tier_slider.setPageStep(1)
        self.tier_slider.setTickPosition(QSlider.TicksBelow)
        self.tier_label = QLabel()
        self.tier_slider.valueChanged.connect(self._tier_label)
        self.tier_slider.sliderReleased.connect(self._tier_changed)
        self.tier_slider.valueChanged.connect(lambda _v: None if self.tier_slider.isSliderDown() else self._tier_changed())
        self.win_combo = QComboBox()
        self.win_combo.addItem("Defeat every enemy", "rout")
        self.win_combo.addItem("Defeat the boss", "boss")
        self.win_combo.addItem("Seize a tile", "seize")
        self.win_combo.addItem("Survive some turns", "survive")
        self.win_combo.currentIndexChanged.connect(self._touched)
        self.win_combo.currentIndexChanged.connect(self._win_changed)
        # Seize: the tile (picked on the map) and who must reach it
        self.seize_box = QWidget()
        sb = QHBoxLayout(self.seize_box)
        sb.setContentsMargins(0, 0, 0, 0)
        self.seize_label = QLabel()
        self.seize_pick = QPushButton("Pick the tile on the map")
        self.seize_pick.setCheckable(True)
        self.seize_pick.setToolTip("Click this, then click the tile to seize on the map.")
        self.seize_who = QComboBox()
        self.seize_who.addItem("any of your units", "")
        self.seize_who.addItem("Chrom only", "PID_クロム")
        self.seize_who.currentIndexChanged.connect(self._touched)
        sb.addWidget(self.seize_label, 1)
        sb.addWidget(self.seize_pick)
        sb.addWidget(self.seize_who)
        self.survive_turns = QSpinBox()
        self.survive_turns.setRange(2, 50)
        self.survive_turns.setValue(8)
        self.survive_turns.setSuffix(" turns")
        self.survive_turns.setToolTip("When this many turns are over, the enemies withdraw and the chapter is won.")
        self.survive_turns.valueChanged.connect(self._touched)
        self.survive_turns.valueChanged.connect(lambda _v: self._banner_hint())
        self.banner_edit = QLineEdit()
        self.banner_edit.setMaxLength(24)
        self.banner_edit.setToolTip("Shown at the start of the battle, like the game's \"Rout the enemy\".\n"
                                    "Needs the game code patch (Unlimited -> Install Game Code Patch).")
        self.banner_edit.textEdited.connect(self._touched)
        self.win_note = QLabel()
        self.win_note.setWordWrap(True)
        self.boss_name = QLineEdit()
        self.boss_name.textEdited.connect(self._boss_name_changed)
        self.boss_face = QComboBox()
        self.boss_face.addItem("Plain soldier (no portrait)", "")
        self._fill_boss_faces()
        self.boss_face.currentIndexChanged.connect(self._boss_face_changed)
        self.boss_line = QPlainTextEdit()
        self.boss_line.setPlaceholderText("Last words when defeated (needs a portrait). Enter = new row.")
        self.boss_line.setFixedHeight(self.boss_line.fontMetrics().lineSpacing() * 3 + 12)
        self.boss_line.textChanged.connect(self._touched)
        regen = QPushButton("Make new enemies for this map")
        regen.clicked.connect(self.regenerate)
        fe.addRow("Army:", self.theme_combo)
        fe.addRow("Difficulty:", self.tier_slider)
        fe.addRow("", self.tier_label)
        fe.addRow("To win:", self.win_combo)
        fe.addRow("Tile:", self.seize_box)
        fe.addRow("Survive:", self.survive_turns)
        fe.addRow("Banner:", self.banner_edit)
        fe.addRow("", self.win_note)
        self._win_form = fe
        self._win_changed()
        fe.addRow("Boss name:", self.boss_name)
        fe.addRow("Boss portrait:", self.boss_face)
        fe.addRow("Boss line:", self.boss_line)
        fe.addRow(regen)
        self.theme_combo.currentIndexChanged.connect(self._touched)

        self.step_story = QGroupBox("4. Story")
        fs = QVBoxLayout(self.step_story)
        speakers = self.maker.speakers()
        self.opening = ConversationEditor(speakers)
        self.ending = ConversationEditor(speakers)
        fs.addWidget(QLabel("<b>Before the battle</b> (leave empty to skip):"))
        fs.addWidget(self.opening)
        fs.addWidget(QLabel("<b>After the battle</b>:"))
        fs.addWidget(self.ending)
        self.opening.changed.connect(self._touched)
        self.ending.changed.connect(self._touched)

        self.step_unlock = QGroupBox("5. When does it appear?")
        fu = QFormLayout(self.step_unlock)
        self.unlock_combo = QComboBox()
        for cid, name in self.maker.story_chapters():
            self.unlock_combo.addItem(name, cid)
        self.unlock_combo.currentIndexChanged.connect(self._touched)
        fu.addRow("Appears after:", self.unlock_combo)
        self._world_spot: list = []
        spot_row = QHBoxLayout()
        self.spot_label = QLabel()
        self.spot_label.setWordWrap(True)
        self.spot_button = QPushButton("Choose on the map...")
        self.spot_button.setToolTip("Pick where the chapter sits on the world map.")
        self.spot_button.clicked.connect(self._choose_spot)
        spot_row.addWidget(self.spot_label, 1)
        spot_row.addWidget(self.spot_button)
        fu.addRow("World map spot:", spot_row)
        self._spot_text()

        self.existing_note = QLabel(
            "<b>This is one of the game's own chapters</b> (or one made outside the Map Maker). "
            "You can move, add, change and remove units, paint its terrain and set what its chests and "
            "villages give. Its story and other events are not changed.")
        self.existing_note.setWordWrap(True)
        mode_row = QHBoxLayout()
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(list(cm.MODES))
        self.mode_combo.currentTextChanged.connect(self._mode_changed)
        mode_row.addWidget(QLabel("Show the units of:"))
        mode_row.addWidget(self.mode_combo)
        self.mode_widget = QWidget()
        self.mode_widget.setLayout(mode_row)
        self.other_note = QLabel()
        self.other_note.setWordWrap(True)

        self.events = md.EventsPanel(self)

        left_w = QWidget()
        left_l = QVBoxLayout(left_w)
        for g in (self.existing_note, self.mode_widget, self.other_note, self.step_name, self.step_map,
                  self.step_enemies, self.step_story, self.step_unlock, self.events):
            left_l.addWidget(g)
        left_l.addStretch(1)
        left_scroll = QScrollArea()
        left_scroll.setWidgetResizable(True)
        left_scroll.setWidget(left_w)
        left_scroll.setMinimumWidth(430)
        left_scroll.setMaximumWidth(520)
        body.addWidget(left_scroll)

        # ---------------- center: tools + map
        center = QVBoxLayout()
        tools = QHBoxLayout()
        tools2 = QHBoxLayout()
        tools2.addWidget(QLabel("Map:"))
        self.tool_group = QButtonGroup(self)
        self.tool_group.setExclusive(True)
        for tid, label, tip in (
            ("move", "✋ Move", "Drag units to move them. Click one to change it."),
            ("enemy", "+ Enemy", "Click an empty tile to add an enemy"),
            ("boss", "+ Boss", "Click an empty tile to add a boss"),
            ("player", "+ Player start", "Click an empty tile to add a spot for one of your units"),
            ("join", "★ Joins your army", "Pick a character in 'Who joins', then click an empty tile: they join your army\n"
                                         "at the start of turn 1, the way Donnel joins in Paralogue 1."),
            ("erase", "✕ Remove", "Click a unit to remove it (right-click works in every tool)"),
            ("terrain", "🖌 Terrain", "Paint tiles (pick the tile on the right). Changes where units can go,\n"
                                     "their defense and avoid. The 3D picture of the map stays as it is."),
            ("treasure", "C Chest / village", "Click a chest or village / house tile to set what it gives.\n"
                                             "Click any other tile to put a chest there."),
            ("event", "! Event tile", "Click a tile: when a unit (or one character) waits there, a conversation\n"
                                      "plays and they get a gift (like the DLC maps)."),
        ):
            b = QPushButton(label)
            b.setCheckable(True)
            b.setToolTip(tip)
            b.setStyleSheet("QPushButton { padding: 6px 12px; } QPushButton:checked { background: #3a6ea5; color: white; }")
            b.setProperty("tool", tid)
            self.tool_group.addButton(b)
            (tools2 if tid in ("terrain", "treasure", "event") else tools).addWidget(b)
            if tid == "move":
                b.setChecked(True)
        self.tool_group.buttonClicked.connect(self._tool)
        self.new_class = QComboBox()
        self.new_class.setToolTip("Class of the enemies you add")
        self.new_class.setMinimumWidth(170)
        for name, jid in self.maker.enemy_classes():
            self.new_class.addItem(name, jid)
        tools.addWidget(QLabel("New enemies are:"))
        tools.addWidget(self.new_class)
        self.join_who = QComboBox()
        self.join_who.setToolTip("The character the ★ Joins your army tool places")
        self.join_who.setMinimumWidth(150)
        self._join_jobs = {}
        for name, pid, jid in sorted(self.maker.joinable_characters()):
            self.join_who.addItem(name, pid)
            self._join_jobs[pid] = jid
        tools.addWidget(QLabel("Who joins:"))
        tools.addWidget(self.join_who)
        self.paint_tile_box = QComboBox()
        self.paint_tile_box.setToolTip("The tile the Terrain tool paints")
        self.paint_tile_box.setMinimumWidth(140)
        for t, name in enumerate(self.maker.tile_names()):
            if name and not name.startswith("TID_"):
                self.paint_tile_box.addItem(f"{name} ({t})", t)
        self.paint_label = QLabel("Paint:")
        tools2.addWidget(self.paint_label)
        tools2.addWidget(self.paint_tile_box)
        tools2.addStretch(1)
        self.grid_check = QCheckBox("Grid")
        self.grid_check.setChecked(True)
        self.grid_check.toggled.connect(self._grid)
        tools.addWidget(self.grid_check)
        tools.addStretch(1)
        center.addLayout(tools)
        center.addLayout(tools2)
        self.canvas = MapCanvas(self)
        self.canvas.unitSelected.connect(self.show_unit)
        self.canvas.changed.connect(lambda _w: self._after_change())
        self.canvas.hover.connect(lambda t: self.statusBar().showMessage(t))
        map_scroll = QScrollArea()
        map_scroll.setWidget(self.canvas)
        map_scroll.setAlignment(Qt.AlignCenter)
        map_scroll.setStyleSheet("QScrollArea { background: #222; }")
        center.addWidget(map_scroll, 1)
        self.summary = QLabel()
        center.addWidget(self.summary)
        body.addLayout(center, 1)

        # ---------------- right: selected unit
        self.unit_box = QGroupBox("Selected unit")
        self.unit_box.setMinimumWidth(400)
        self.unit_box.setMaximumWidth(480)
        ub = QVBoxLayout(self.unit_box)
        self.details = md.UnitDetails(self)
        ub.addWidget(self.details)
        rv = QVBoxLayout()
        rv.addWidget(self.unit_box, 1)
        tips = QLabel(
            "<b>Tips</b><ul>"
            "<li>Drag a unit to move it. Red tiles: it can't stand there.</li>"
            "<li>Right-click a unit to remove it.</li>"
            "<li>Ctrl+Z undoes, Ctrl+S saves.</li>"
            "<li>Gold frame = boss. Cyan frame with ★ = joins your army on turn 1.</li>"
            "<li>C = chest, V = village, ! = tile event, orange = painted tile.</li></ul>")
        tips.setWordWrap(True)
        rv.addWidget(tips)
        body.addLayout(rv)
        self.details.show_unit(None)
        return w

    def _fill_boss_faces(self):
        gd = self.gs.data
        seen = set()
        try:
            r, f = gd.table("characters")
            for c in gd.items(r, f):
                fid = gd.string(c, "fid") or ""
                pid = gd.string(c, "pid") or ""
                if fid and fid not in seen and fid.startswith("FID_") and ("ボス" in fid or pid.endswith("ボス")):
                    seen.add(fid)
        except Exception:
            pass
        for ch in ("001", "002", "013", "024", "X001", "X002", "X003", "X004", "X005", "X009", "X010", "007", "008"):
            try:
                p = gd.multi_open("person", f"data/person/{ch}.bin.lz")
                for c in gd.items(p, "people"):
                    fid = gd.string(c, "fid") or ""
                    if fid.endswith("ボス") and fid not in seen:
                        seen.add(fid)
                        name = self.maker.message(gd.string(c, "name")) or fid
                        self.boss_face.addItem(f"{name} ({fid[4:]})", fid)
            except Exception:
                continue

    # ================================================================== open / new
    def go_home(self):
        if self.dirty and not self._ask_discard():
            return
        self.dirty = False
        self.refresh_home()
        self.pages.setCurrentIndex(0)

    def _ask_discard(self) -> bool:
        r = QMessageBox.question(self, "Map Maker", "Save your changes to this chapter first?",
                                 QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel)
        if r == QMessageBox.Save:
            return self.save()
        return r == QMessageBox.Discard

    def new_chapter(self):
        slot = self.maker.next_slot_id()
        if slot is None or self.maker.free_rows() <= 0:
            QMessageBox.information(self, "Map Maker", "There is no empty chapter slot left.")
            return
        idx = len(self.maker.custom_chapters())
        plan = self.maker.default_plan(slot, idx)
        gallery = TemplateGallery(self.maker, plan.template, self)
        if gallery.exec() != QDialog.Accepted or not gallery.chosen:
            return
        plan.template = gallery.chosen
        t = self.maker.templates.get(plan.template) or {}
        plan.theme = t.get("theme", plan.theme)
        plan.tier = t.get("tier", plan.tier)
        plan.boss_name = cm.THEMES.get(plan.theme, cm.THEMES["ruffian"])["boss"]
        plan.units = self.maker.template_units(plan.template, plan.tier, plan.theme)
        try:
            self.maker.create_chapter(plan, render_title)
        except Exception as e:
            logging.exception("Could not make the chapter")
            QMessageBox.critical(self, "Map Maker", f"Could not make the chapter:\n{e}")
            return
        self.dirty = True
        self._mark_project_changed()
        self._open_plan(plan, made=True)
        self.statusBar().showMessage(f"Made {plan.cid}. Change anything you like, then press Save chapter.", 10000)

    def clear_chapter(self, cid: str):
        name = self.maker.chapter_name(cid)
        r = QMessageBox.warning(
            self, "Clear chapter",
            f"Wipe {cid} ({name})?\n\nIts map, units, story, events, chests and villages are replaced by a "
            "fresh chapter on the map you pick next. Nothing is written until you save the project, so closing "
            "Paragon without saving brings it back.",
            QMessageBox.Yes | QMessageBox.Cancel, QMessageBox.Cancel)
        if r != QMessageBox.Yes:
            return
        idx = cm.SLOT_IDS.index(cid) if cid in cm.SLOT_IDS else 0
        plan = self.maker.default_plan(cid, idx)
        gallery = TemplateGallery(self.maker, plan.template, self)
        if gallery.exec() != QDialog.Accepted or not gallery.chosen:
            return
        plan.template = gallery.chosen
        t = self.maker.templates.get(plan.template) or {}
        plan.theme = t.get("theme", plan.theme)
        plan.tier = t.get("tier", plan.tier)
        plan.boss_name = cm.THEMES.get(plan.theme, cm.THEMES["ruffian"])["boss"]
        plan.units = self.maker.template_units(plan.template, plan.tier, plan.theme)
        try:
            self.maker.clear_chapter(plan, render_title)
        except Exception as e:
            logging.exception("Could not clear the chapter")
            QMessageBox.critical(self, "Map Maker", f"Could not clear the chapter:\n{e}")
            return
        self.sprites.cache.clear()
        self.dirty = True
        self._mark_project_changed()
        self._open_plan(plan, made=True)
        self.statusBar().showMessage(f"{cid} starts over. Change anything you like, then press Save chapter.", 10000)

    def delete_chapter(self, cid: str):
        name = self.maker.chapter_name(cid)
        after = self.maker.chapters_after(cid)
        text = (f"Delete {cid} ({name}) from the game?\n\n"
                "Its row in the chapter list, its spot on the world map and its road are taken out. "
                "Chapters listed after it move up one place, so a save file you already played with this "
                "mod may show the wrong chapters as cleared - start a new save to be safe.")
        if after:
            text += (f"\n\nThese chapters appear after {cid}: {', '.join(after)}. Open them and pick another "
                     "chapter under 'When does it appear?', or they will not show up.")
        text += "\n\nNothing is written until you save the project, so closing Paragon without saving brings it back."
        r = QMessageBox.warning(self, "Delete chapter", text, QMessageBox.Yes | QMessageBox.Cancel, QMessageBox.Cancel)
        if r != QMessageBox.Yes:
            return
        try:
            self.maker.delete_chapter(cid)
        except Exception as e:
            logging.exception("Could not delete the chapter")
            QMessageBox.critical(self, "Map Maker", f"Could not delete the chapter:\n{e}")
            return
        if self.plan is not None and self.plan.cid == cid:
            self.plan = None
        self.dirty = False
        self._mark_project_changed()
        self.refresh_home()
        self.statusBar().showMessage(f"{cid} deleted. Save the project to keep the change.", 10000)

    def fill_all(self):
        free = self.maker.free_rows()
        r = QMessageBox.question(
            self, "Map Maker",
            f"Make {free} ready-to-play chapter(s)? Each gets its own map, enemies (from easy to hard), a short "
            "story and a spot on the world map. You can change everything afterwards.")
        if r != QMessageBox.Yes:
            return
        try:
            made = self.maker.fill_free_slots(render_title)
        except Exception as e:
            logging.exception("fill slots")
            QMessageBox.critical(self, "Map Maker", f"Could not make the chapters:\n{e}")
            return
        self._mark_project_changed()
        self._save_project()
        self.refresh_home()
        QMessageBox.information(self, "Map Maker", f"Made {', '.join(made)} and saved your project.")

    def open_chapter(self, cid: Optional[str]):
        if not cid:
            return
        try:
            plan = self.maker.load_plan(cid)
        except Exception as e:
            logging.exception("open chapter")
            QMessageBox.critical(self, "Map Maker", f"Could not open {cid}:\n{e}")
            return
        self._open_plan(plan, made=self.maker.is_made_here(cid))

    def _open_plan(self, plan: cm.ChapterPlan, made: bool):
        self._loading = True
        self.plan = plan
        self.made_here = made
        self.undo_stack.clear()
        self.redo_stack.clear()
        self.mode = "Normal"
        self.mode_combo.setCurrentText("Normal")
        self.editor_title.setText(f"{plan.cid}: {plan.title}")
        for g in (self.step_name, self.step_map, self.step_enemies, self.step_story, self.step_unlock):
            g.setVisible(made)
        for b in self.tool_group.buttons():
            if b.property("tool") == "join":
                b.setEnabled(made)
                b.setToolTip(b.toolTip().split("\n\n")[0] + ("" if made else "\n\nOnly in chapters made with the Map Maker."))
        self.join_who.setEnabled(made)
        self.existing_note.setVisible(not made)
        self.mode_widget.setVisible(not made)
        others = self.maker.other_unit_counts(plan.cid)
        self.other_note.setVisible(bool(others))
        self.other_note.setText(
            "<small>Also in this chapter (not shown, kept as they are): "
            + ", ".join(f"{k} ({v})" for k, v in others.items()) + "</small>")
        if made:
            self.title_edit.setText(plan.title)
            self.label_edit.setText(plan.label)
            self.desc_edit.setText(plan.description)
            self.theme_combo.setCurrentIndex(max(0, self.theme_combo.findData(plan.theme)))
            self.tier_slider.setValue(plan.tier)
            self._tier_label()
            self.win_combo.setCurrentIndex(max(0, self.win_combo.findData(plan.win)))
            self.seize_who.setCurrentIndex(max(0, self.seize_who.findData(plan.seize_who)))
            self.survive_turns.setValue(int(plan.survive_turns or 8))
            self.banner_edit.setText(plan.banner)
            self._win_changed()
            boss = next((u for u in plan.units if u.boss and u.team == "enemy"), None)
            self.boss_name.setText(boss.name if boss and boss.name else plan.boss_name)
            self.boss_face.setCurrentIndex(max(0, self.boss_face.findData(boss.face if boss else plan.boss_face)))
            self.boss_line.setPlainText(plan.boss_line)
            self.opening.set_lines(plan.opening)
            self.ending.set_lines(plan.ending)
            self.unlock_combo.setCurrentIndex(max(0, self.unlock_combo.findData(plan.unlock_after)))
            self._world_spot = list(plan.world_spot or [])
            self._spot_text()
            self._map_text()
        self.canvas.set_map(self.maker.grid(plan.cid) or self._template_grid(plan.template),
                            self.maker.minimap(plan.cid) or self.maker.minimap(plan.template),
                            self.maker.tile_names())
        self.canvas.painted = {}
        self._grid_orig = {}
        self.canvas.set_units(plan.units)
        self._orig_treasures = copy.deepcopy(plan.treasures)
        self.events.set_made(made)
        self.events.refresh()
        self.details.show_unit(None)
        self._update_summary()
        self.pages.setCurrentIndex(1)
        self._loading = False

    def _template_grid(self, tid):
        return self.maker.grid(tid)

    def _map_text(self):
        t = self.maker.templates.get(self.plan.template) if self.plan else None
        if t:
            self.map_label.setText(f"<b>{t.get('label', '')}: {t.get('title', '')}</b><br>{', '.join(t.get('tags', []))}, "
                                   f"{t['size'][0]} x {t['size'][1]} tiles")
        else:
            self.map_label.setText("This chapter's own map.")

    # ================================================================== editing
    def new_unit_job(self) -> Optional[str]:
        return self.new_class.currentData()

    def join_job(self) -> Optional[str]:
        return self._join_jobs.get(self.join_who.currentData() or "")

    STATE = ("units", "talks", "turn_events", "tile_events", "treasures", "seize")

    def snapshot(self):
        state = {k: copy.deepcopy(getattr(self.plan, k)) for k in self.STATE}
        state["painted"] = dict(self.canvas.painted)
        return state

    def _restore(self, state):
        sel = self.canvas.selected
        sel_key = (sel.x, sel.y, sel.team) if sel is not None else None
        for k in self.STATE:
            if k == "units":
                self.plan.units[:] = state[k]
            else:
                setattr(self.plan, k, state[k])
        # painted tiles: put the old tiles back in the grid, then the snapshot's
        if self.canvas.grid:
            raw = self.canvas.grid[2]
            orig = getattr(self, "_grid_orig", {})
            for (x, y) in list(self.canvas.painted):
                if (x, y) in orig:
                    raw[y * 32 + x] = orig[(x, y)]
            for (x, y), t in state["painted"].items():
                raw[y * 32 + x] = t
        self.canvas.painted = dict(state["painted"])
        self.canvas.set_units(self.plan.units)
        self.canvas.selected = next((u for u in self.plan.units if sel_key and (u.x, u.y, u.team) == sel_key), None)
        self.events.refresh()
        self.details.show_unit(self.canvas.selected)
        self._seize_text()

    def before_change(self, _what=""):
        if self.plan is None:
            return
        self.undo_stack.append(self.snapshot())
        self.redo_stack.clear()
        if len(self.undo_stack) > 200:
            self.undo_stack.pop(0)

    def _after_change(self):
        self.dirty = True
        self._update_summary()
        self.canvas.update()
        if self.canvas.selected is not None:
            self.show_unit(self.canvas.selected)

    def undo(self):
        if self.plan is None or not self.undo_stack:
            return
        self.redo_stack.append(self.snapshot())
        self._restore(self.undo_stack.pop())
        self._after_change()

    def redo(self):
        if self.plan is None or not self.redo_stack:
            return
        self.undo_stack.append(self.snapshot())
        self._restore(self.redo_stack.pop())
        self._after_change()

    def add_unit(self, kind: str, x: int, y: int):
        if self.plan is None:
            return
        tier = self.tier_slider.value() if self.made_here else 3
        if kind == "join":
            if not self.made_here:
                QMessageBox.information(self, "Map Maker", "Characters can join your army in chapters made with the Map "
                                        "Maker. (The game's own chapters keep their own events.)")
                return
            pid = self.join_who.currentData()
            if not pid:
                return
            if any(o.pid == pid and o.team in ("join", "player") for o in self.plan.units):
                QMessageBox.information(self, "Map Maker", f"{self.join_who.currentText()} is already on this map.")
                return
            jid = self.join_job()
            if not self.canvas.can_place(x, y, None, jid):
                self.statusBar().showMessage("That character can't stand there.", 4000)
                return
            items = (cm.items_for(jid, 3) if jid else []) + ["IID_傷薬"]
            u = cm.Unit(team="join", x=x, y=y, job=jid or "", level=1, pid=pid, items=items,
                        name=self.join_who.currentText())
            self.before_change("Add unit")
            self.plan.units.append(u)
            self.canvas.selected = u
            self.canvas.set_units(self.plan.units)
            self.show_unit(u)
            self._after_change()
            return
        if kind == "player":
            if not self.canvas.can_place(x, y, None, None):
                self.statusBar().showMessage("Your units can't stand there.", 4000)
                return
            u = cm.Unit(team="player", x=x, y=y, job="")
        else:
            jid = self.new_class.currentData() or "JID_ソルジャー男"
            if not self.canvas.can_place(x, y, None, jid):
                self.statusBar().showMessage("That class can't stand there (try a flier for water and peaks).", 4000)
                return
            lo, hi = cm.TIERS[tier]["levels"]
            boss = kind == "boss"
            if boss:
                for o in self.plan.units:
                    if o.boss and o.team == "enemy" and self.made_here:
                        o.boss = False  # one boss at a time for new chapters
            u = cm.Unit(team="enemy", x=x, y=y, job=jid, level=min(20, hi + 2) if boss else (lo + hi) // 2,
                        boss=boss, behavior="stay" if boss else "charge", items=cm.items_for(jid, tier, boss),
                        name=self.boss_name.text() if boss else "", face=self.boss_face.currentData() if boss else "")
        self.before_change("Add unit")
        self.plan.units.append(u)
        self.canvas.selected = u
        self.canvas.set_units(self.plan.units)
        self.show_unit(u)
        self._after_change()

    def remove_unit(self, u: cm.Unit):
        if self.plan is None or u not in self.plan.units:
            return
        if u.forced:
            QMessageBox.information(self, "Map Maker", "The game always deploys this unit, so it can be moved but not removed.")
            return
        players = [x for x in self.plan.units if x.team == "player"]
        if u.team == "player" and len(players) <= 1:
            QMessageBox.information(self, "Map Maker", "A chapter needs at least one player start.")
            return
        self.before_change("Remove unit")
        self.plan.units.remove(u)
        if self.canvas.selected is u:
            self.canvas.selected = None
            self.details.show_unit(None)
        self.canvas.set_units(self.plan.units)
        self._after_change()

    def describe(self, u: cm.Unit) -> str:
        if u.team == "join":
            rid = self.gs.data.key_to_rid("characters", u.pid) if u.pid else None
            name = (self.gs.data.display(rid) if rid else "") or u.name or u.pid
            return f"Joins your army: {name}"
        if u.team == "player":
            name = ""
            if u.pid:
                rid = self.gs.data.key_to_rid("characters", u.pid)
                name = (self.gs.data.display(rid) if rid else "") or ""
            return f"Player start {('(' + name + ')') if name else ''}".strip()
        cls = self.maker.class_name(u.job) if u.job else "?"
        s = f"{'Boss ' if u.boss else ''}{cls} Lv {u.level}"
        if u.boss and u.name:
            s = f"{u.name}: {s}"
        return s + f" - {cm.BEHAVIOR_NAMES.get(u.behavior, u.behavior)}"

    def show_unit(self, u: Optional[cm.Unit]):
        self.details.show_unit(u)

    def current_tier(self) -> int:
        return self.tier_slider.value() if self.made_here else 3

    def unit_changed(self, u: cm.Unit, refresh: bool):
        """A detail of a unit was changed in the unit panel."""
        if refresh:
            self.sprites.cache.clear()
        self.dirty = True
        self._update_summary()
        self.canvas.update()
        if refresh:
            self.details.show_unit(u)
        else:
            self.details.info.setText(f"<b>{self.describe(u)}</b><br>Tile ({u.x}, {u.y}): {self.canvas.tile_name(u.x, u.y)}")

    def events_changed(self):
        self.dirty = True
        self.events.refresh()
        self.canvas.update()
        self._update_summary()

    # ---------------------------------------------------------------- terrain, chests, tile events
    def paint_tile(self, x: int, y: int):
        g = self.canvas.grid
        if self.plan is None or not g or not (0 <= x < g[0] and 0 <= y < g[1]):
            return
        t = self.paint_tile_box.currentData()
        if t is None:
            return
        raw = g[2]
        orig = self.__dict__.setdefault("_grid_orig", {})
        orig.setdefault((x, y), raw[y * 32 + x])
        if raw[y * 32 + x] == t and (x, y) in self.canvas.painted:
            return
        raw[y * 32 + x] = t
        if orig[(x, y)] == t:
            self.canvas.painted.pop((x, y), None)
        else:
            self.canvas.painted[(x, y)] = t
        self.dirty = True
        self.canvas.update()

    def paint_done(self):
        if self.undo_stack and self.undo_stack[-1].get("painted") == self.canvas.painted:
            self.undo_stack.pop()  # nothing was painted
        self._update_summary()

    def treasure_clicked(self, x: int, y: int):
        if self.plan is None or not self.canvas.grid:
            return
        i = self.events.treasure_at(x, y)
        if i >= 0:
            self.events.edit("treasures", i)
            return
        g = self.canvas.grid
        if not (0 <= x < g[0] and 0 <= y < g[1]):
            return
        tile = g[2][y * 32 + x]
        from paragon.unlimited.map_maker import chapter_events as ce

        village = tile in ce.VILLAGE_TILES
        t = ce.Treasure(x, y, ce.VILLAGE_KIND if village else ce.CHEST_KIND,
                        ce.VILLAGE_MODEL if village else ce.CHEST_MODEL)
        d = md.TreasureDialog(self.maker, t, False, self)
        if d.exec() != QDialog.Accepted:
            return
        t = d.result_treasure()
        self.before_change("Add chest")
        if t.is_chest and tile not in ce.CHEST_TILES:
            chest = next((k for k in ce.CHEST_TILES), None)
            if chest is not None:
                orig = self.__dict__.setdefault("_grid_orig", {})
                orig.setdefault((x, y), tile)
                g[2][y * 32 + x] = chest
                self.canvas.painted[(x, y)] = chest
        self.plan.treasures.append(t)
        self.events_changed()

    def event_tile_clicked(self, x: int, y: int):
        if self.plan is None:
            return
        if not self.made_here:
            QMessageBox.information(self, "Map Maker", "Events can be added to chapters made with the Map Maker.")
            return
        i = self.events.tile_event_at(x, y)
        if i >= 0:
            self.events.edit("tile_events", i)
        else:
            self.events.add("tile_events", x, y)

    def marks_text(self, x: int, y: int) -> str:
        if self.plan is None:
            return ""
        out = []
        i = self.events.treasure_at(x, y)
        if i >= 0:
            out.append(self.events._label("treasures", self.plan.treasures[i]))
        i = self.events.tile_event_at(x, y)
        if i >= 0:
            out.append("Event " + self.events._label("tile_events", self.plan.tile_events[i]))
        if (x, y) in self.canvas.painted:
            out.append("painted")
        return ("  |  " + "; ".join(out)) if out else ""

    def _tool(self, button):
        self.canvas.tool = button.property("tool")
        self.canvas.update()

    def _grid(self, on):
        self.canvas.show_grid = on
        self.canvas.update()

    def _mode_changed(self, mode):
        if self._loading or self.plan is None:
            return
        if self.dirty and not self._ask_discard():
            self._loading = True
            self.mode_combo.setCurrentText(self.mode)
            self._loading = False
            return
        self.mode = mode
        self.plan.units = self.maker.read_units(self.plan.cid, mode)
        self.undo_stack.clear()
        self.redo_stack.clear()
        self.dirty = False
        self.canvas.set_units(self.plan.units)
        self._update_summary()

    def _touched(self, *_):
        if not self._loading:
            self.dirty = True

    # win conditions -----------------------------------------------------------
    WIN_NOTES = {
        "rout": "The chapter is won when no enemy is left.",
        "boss": "The chapter is won when the boss (gold frame) is defeated.",
        "seize": "The chapter is won when one of your units waits on the tile (purple flag). "
                 "Defeating every enemy does not win it.",
        "survive": "When the turns are over, the enemies withdraw at the start of your next turn; "
                   "the chapter is won as soon as one of your units finishes its move. "
                   "Defeating every enemy does not win it.",
    }

    def _win_changed(self, *_):
        kind = self.win_combo.currentData() or "rout"
        form = getattr(self, "_win_form", None)
        if form is not None:
            form.setRowVisible(self.seize_box, kind == "seize")
            form.setRowVisible(self.survive_turns, kind == "survive")
            form.setRowVisible(self.banner_edit, kind in ("seize", "survive"))
        self._banner_hint()
        self.win_note.setText(f"<small>{self.WIN_NOTES.get(kind, '')}</small>")
        plan = getattr(self, "plan", None)
        if plan is not None and self.made_here:
            plan.win = kind
        if kind != "seize" and self.seize_pick.isChecked():
            self.seize_pick.setChecked(False)
        self._seize_text()
        if getattr(self, "canvas", None) is not None:
            self.canvas.update()
        if plan is not None:
            self._update_summary()

    def _banner_hint(self, *_):
        from paragon.unlimited.map_maker import mission_banner as mb

        kind = self.win_combo.currentData() or "rout"
        probe = cm.ChapterPlan(win=kind, survive_turns=self.survive_turns.value())
        self.banner_edit.setPlaceholderText(mb.default_text(probe))

    def _seize_text(self):
        plan = getattr(self, "plan", None)
        st = (plan.seize if plan is not None else None) or []
        self.seize_label.setText(f"({st[0]}, {st[1]})" if len(st) == 2 else "<i>not chosen</i>")

    def seize_picked(self, x: int, y: int):
        """The tile clicked while "Pick the tile on the map" is on."""
        self.seize_pick.setChecked(False)
        if self.plan is None:
            return
        self.before_change("Choose the tile to seize")
        self.plan.seize = [x, y]
        self._touched()
        self._seize_text()
        self.canvas.update()
        self._update_summary()

    def _tier_label(self, *_):
        t = self.tier_slider.value()
        info = cm.TIERS[t]
        lo, hi = info["levels"]
        self.tier_label.setText(f"{stars(t)}  <b>{info['name']}</b> - "
                                f"{'promoted' if info['promoted'] else 'basic'} classes, level {lo}-{hi}")

    def _tier_changed(self):
        if self._loading or self.plan is None or not self.made_here:
            return
        t = self.tier_slider.value()
        if t == self.plan.tier:
            return
        self.before_change("Difficulty")
        self.plan.tier = t
        self.maker.retier(self.plan.units, t)
        self.sprites.cache.clear()
        self._after_change()

    def _boss_name_changed(self, text):
        if self.plan is None:
            return
        for u in self.plan.units:
            if u.boss and u.team == "enemy":
                u.name = text
        self._touched()

    def _boss_face_changed(self, _i):
        if self._loading or self.plan is None:
            return
        for u in self.plan.units:
            if u.boss and u.team == "enemy":
                u.face = self.boss_face.currentData()
        self.boss_line.setEnabled(bool(self.boss_face.currentData()))
        self._touched()

    def regenerate(self):
        if self.plan is None:
            return
        if not self.maker.templates.get(self.plan.template):
            QMessageBox.information(self, "Map Maker", "This chapter's map is not one of the map choices, so the Map "
                                    "Maker has no enemy layout for it. Use 'Choose a different map...' or Clear the "
                                    "chapter on the home page.")
            return
        r = QMessageBox.question(self, "Map Maker", "Replace every enemy with new ones for this map? "
                                 "(Undo brings them back.)")
        if r != QMessageBox.Yes:
            return
        self.before_change("New enemies")
        players = [u for u in self.plan.units if u.team in ("player", "join")]
        fresh = self.maker.template_units(self.plan.template, self.tier_slider.value(),
                                          self.theme_combo.currentData(), seed=len(self.undo_stack))
        enemies = [u for u in fresh if u.team == "enemy"]
        for e in enemies:
            if e.boss:
                e.name = self.boss_name.text() or e.name
                e.face = self.boss_face.currentData()
        self.plan.units[:] = players + enemies
        self.canvas.set_units(self.plan.units)
        self._after_change()

    def choose_map(self):
        if self.plan is None:
            return
        g = TemplateGallery(self.maker, self.plan.template, self)
        if g.exec() != QDialog.Accepted or not g.chosen or g.chosen == self.plan.template:
            return
        r = QMessageBox.question(self, "Map Maker", "Use the new map? Your player starts and enemies are "
                                 "replaced by the ones that come with it (characters who join are removed too).")
        if r != QMessageBox.Yes:
            return
        self.plan.template = g.chosen
        old = {u.spawn_rid for u in self.plan.units}
        self.plan.units[:] = self.maker.template_units(g.chosen, self.tier_slider.value(),
                                                       self.theme_combo.currentData())
        self.maker.change_template(self.plan)
        self.canvas.painted = {}
        self._grid_orig = {}
        self._orig_treasures = copy.deepcopy(self.plan.treasures)
        self.events.refresh()
        self.undo_stack.clear()
        self.redo_stack.clear()
        self.dirty = True
        self._mark_project_changed()
        # the old units are removed from the chapter when it is saved
        self.plan._removed = old  # noqa: SLF001 (documentation only)
        self.canvas.set_map(self.maker.grid(g.chosen), self.maker.minimap(g.chosen), self.maker.tile_names())
        self.canvas.set_units(self.plan.units)
        self._map_text()
        self._update_summary()

    def _update_summary(self):
        if self.plan is None:
            return
        units = self.plan.units
        e = [u for u in units if u.team == "enemy"]
        b = [u for u in e if u.boss]
        p = [u for u in units if u.team == "player"]
        a = [u for u in units if u.team == "ally"]
        j = [u for u in units if u.team == "join"]
        warn = []
        if not p:
            warn.append("no player starts")
        if not e:
            warn.append("no enemies")
        if self.made_here and self.win_combo.currentData() == "boss" and not b:
            warn.append("'Defeat the boss' needs a boss")
        if self.made_here and self.win_combo.currentData() == "seize":
            st = self.plan.seize or []
            if len(st) != 2:
                warn.append("'Seize a tile' needs a tile (Pick the tile on the map)")
            elif any((e.x, e.y) == tuple(st) for e in self.plan.tile_events):
                warn.append("the tile to seize also has a tile event; move one of them")
        from paragon.unlimited.map_maker import chapter_events as ce

        grid = self.canvas.grid
        for t in self.plan.treasures:
            tile = grid[2][t.y * 32 + t.x] if grid else None
            if grid and t.is_chest and tile not in ce.CHEST_TILES:
                warn.append(f"the chest at ({t.x}, {t.y}) is not on a chest tile")
            elif grid and not t.is_chest and tile not in ce.VILLAGE_TILES:
                warn.append(f"the village at ({t.x}, {t.y}) is not on a village / house tile")
        on_map = {u.pid for u in units if u.pid} | {u.character for u in units if u.character}
        if self.made_here:
            for talk in self.plan.talks:
                if talk.b and talk.b not in on_map:
                    warn.append(f"talk: {self.events._who(talk.b)} is not on the map")
            for u in units:
                if u.quotes and not (u.face or u.character):
                    warn.append(f"a unit with battle quotes at ({u.x}, {u.y}) has no portrait")
        txt = f"{len(p)} player starts, {len(e)} enemies ({len(b)} boss)" + (f", {len(a)} allies" if a else "") + (
            f", {len(j)} joining your army" if j else "")
        if warn:
            txt += "   <span style='color:#d33'><b>Check: " + "; ".join(warn) + "</b></span>"
        self.summary.setText(txt)
        self.undo_btn.setEnabled(bool(self.undo_stack))
        self.redo_btn.setEnabled(bool(self.redo_stack))

    # ================================================================== saving
    def _collect_plan(self):
        p = self.plan
        if not self.made_here:
            return
        p.title = self.title_edit.text().strip() or p.cid
        p.label = self.label_edit.text().strip()
        p.description = self.desc_edit.text().strip()
        p.theme = self.theme_combo.currentData()
        p.tier = self.tier_slider.value()
        p.win = self.win_combo.currentData()
        p.seize_who = self.seize_who.currentData() or ""
        p.survive_turns = self.survive_turns.value()
        p.banner = self.banner_edit.text().strip()
        p.boss_name = self.boss_name.text().strip()
        p.boss_face = self.boss_face.currentData() or ""
        p.boss_line = self.boss_line.toPlainText().strip()
        p.opening = self.opening.lines()
        p.ending = self.ending.lines()
        p.unlock_after = self.unlock_combo.currentData() or p.unlock_after
        p.world_spot = list(self._world_spot)

    def _spot_text(self):
        if len(self._world_spot) == 2:
            self.spot_label.setText(f"Chosen ({self._world_spot[0]}, {self._world_spot[1]})")
        else:
            self.spot_label.setText("Automatic: next to the chapter above")

    def _choose_spot(self):
        if self.plan is None:
            return
        from paragon.unlimited.map_maker import world_spot_picker as wsp

        anchor = self.unlock_combo.currentData() or self.plan.unlock_after or "X001"
        try:
            layout = self.maker.world_map_layout()
        except Exception:
            logging.exception("World map layout")
            layout = {}
        if not layout.get("nodes"):
            QMessageBox.warning(self, "World map spot", "The world map could not be read.")
            return
        spot = tuple(self._world_spot) if len(self._world_spot) == 2 else None
        dlg = wsp.WorldSpotDialog(layout, self.plan.cid, anchor, spot, self.unlock_combo.currentText(), self)
        if dlg.exec() != QDialog.Accepted:
            return
        new = dlg.spot()
        self._world_spot = list(new) if new else []
        self._spot_text()
        self._touched()

    def save(self) -> bool:
        if self.plan is None:
            return False
        if self.made_here and self.maker.is_legacy(self.plan.cid):
            r = QMessageBox.warning(
                self, "Save chapter",
                f"{self.plan.cid} was made outside the Map Maker (its script was written by hand).\n\n"
                "Saving here replaces its script with the Map Maker's: anything added to the script by hand "
                "(events, scenes, sounds) is lost. Its world map spot stays where it is.\n\nSave anyway?",
                QMessageBox.Save | QMessageBox.Cancel, QMessageBox.Cancel)
            if r != QMessageBox.Save:
                return False
        try:
            self._collect_plan()
            painted = dict(self.canvas.painted)
            if self.made_here:
                for (x, y), t in painted.items():
                    self.maker.set_tile(self.plan.cid, x, y, t)
                self.maker.save_chapter(self.plan, render_title)
            else:
                from dataclasses import asdict

                changed = [asdict(t) for t in self.plan.treasures] != [asdict(t) for t in self._orig_treasures]
                self.maker.save_existing(self.plan.cid, self.plan.units, self.mode, self.plan.treasures, painted,
                                         changed)
        except Exception as e:
            logging.exception("Map Maker save")
            QMessageBox.critical(self, "Map Maker", f"Could not save the chapter:\n{e}")
            return False
        self._mark_project_changed()
        ok = self._save_project()
        if ok:
            self.dirty = False
            self.editor_title.setText(f"{self.plan.cid}: {self.plan.title}")
            # re-read so every unit is linked to its saved record
            mode = self.mode
            self.plan.units = self.maker.read_units(self.plan.cid, mode)
            self.maker.attach_quotes(self.plan)
            self.canvas.painted = {}
            self._grid_orig = {}
            self._orig_treasures = copy.deepcopy(self.plan.treasures)
            g = self.maker.grid(self.plan.cid)
            if g:
                self.canvas.grid = (g[0], g[1], bytearray(g[2]))
            self.canvas.set_units(self.plan.units)
            self.details.show_unit(None)
            self.events.refresh()
            self.undo_stack.clear()
            self.redo_stack.clear()
            self._update_summary()
            self.statusBar().showMessage("Saved. Use Unlimited -> Copy to Emulator to play it.", 8000)
        return ok

    def save_and_play(self):
        if not self.save():
            return
        mw = self.main_window
        if mw is not None and hasattr(mw, "_on_copy_azahar"):
            if getattr(getattr(mw, "ms", None), "config", None) is not None and getattr(mw.ms.config, "pu_copy_after_save", False):
                return  # the save already copied it
            mw._on_copy_azahar(after_save=False)

    def _mark_project_changed(self):
        try:
            self.gs.data.pu_changed = True
        except Exception:
            pass

    def _save_project(self) -> bool:
        mw = self.main_window
        if mw is not None and hasattr(mw, "_on_save"):
            mw._on_save()
            return True
        # no main window (tests): write directly
        self.maker.edits.apply_world_map()
        self.gs.data.write()
        self.maker.edits.flush(self.gs.project.output_path)
        return True

    def _help(self):
        try:
            from paragon.unlimited.app import help_window

            help_window.show_help(self)
        except Exception:
            logging.exception("help")

    def closeEvent(self, ev):
        if self.dirty and self.pages.currentIndex() == 1 and not self._ask_discard():
            ev.ignore()
            return
        super().closeEvent(ev)
