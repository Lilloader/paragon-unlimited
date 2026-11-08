"""Paragon Unlimited: Sprite Workshop window (FE13 map sprites).

Two ways to start:
  - drop a sprite sheet you have (PNG or .ctpk.lz) on the big preview, or
  - build one: pick a head (the head sheets in Data/FE13/PU_Heads) and a class body (the game's
    own sprite with its head taken off, see sprite_parts.py).
Then adjust it: drag any head to line it up in that frame, erase bits of the body or of the head,
copy a frame's head into another frame (classes with extra rows, like Dancer or Sage), and save it
to the mod in the player (blue), enemy (red) and ally (green) colors.
All names are shown in English; the game files keep their own names."""
import logging
import os

from PySide6.QtCore import QPoint, QRect, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPen
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSlider,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from paragon.unlimited.sprites import sprite_sheets as ws

SHEET_FILTER = "Sprite sheets (*.png *.bmp *.gif *.ctpk *.lz);;All files (*)"
SHEET_EXTS = (".png", ".bmp", ".gif", ".ctpk", ".lz")
PROJECT_FILTER = "Sprite Workshop project (*.pusprite)"
VARIANTS = (("青", "Player"), ("赤", "Enemy"), ("緑", "Ally"))
EMPTY_TEXT = (
    "Drop a sprite sheet here\n(PNG or .ctpk.lz)\n\n"
    "or build one from a head and a class on the left"
)


def _is_sheet(path: str) -> bool:
    return path.lower().endswith(SHEET_EXTS)


def _searchable(combo: QComboBox):
    combo.setEditable(True)
    combo.setInsertPolicy(QComboBox.NoInsert)
    combo.completer().setFilterMode(Qt.MatchContains)
    combo.completer().setCaseSensitivity(Qt.CaseInsensitive)


def _qimage(sheet, mask=None, show_heads=False, solid=True) -> QImage:
    data = bytearray(sheet.rgba)
    if solid:  # the game draws its see-through sprites solid on the map; show them that way
        for i in range(3, len(data), 4):
            if data[i]:
                data[i] = 255
    if show_heads and mask is not None:
        for i, m in enumerate(mask):
            if m and data[i * 4 + 3]:
                r, g, b = data[i * 4 : i * 4 + 3]
                data[i * 4 : i * 4 + 3] = bytes(((r + 255) // 2, g // 2, (b + 255) // 2))
    return QImage(bytes(data), sheet.width, sheet.height, sheet.width * 4, QImage.Format_RGBA8888).copy()


class SheetCanvas(QWidget):
    """The big preview: drop sheets here, drag heads per frame, right-click a frame to reset it."""

    fileDropped = Signal(str)
    headDragged = Signal(object, int, int)  # cell (col, row), offset x, offset y
    headDragFinished = Signal()
    cellReset = Signal(object)
    erasePixel = Signal(int, int, bool)  # sheet x, y, restore (right button)
    eraseFinished = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setMouseTracking(True)
        self.images = []  # [(label, QImage)]
        self.zoom = 3
        self.cell = (32, 32)
        self.mask = None  # head mask (sheet pixels)
        self.size_wh = (0, 0)
        self.frame = None  # (col, row) when one animation frame is shown
        self.offsets = {}
        self.selected = None
        self._drag = None
        self._hover = False
        self.eraser = 0  # brush size in pixels; 0 = eraser off (drag heads)
        self._erasing = None  # True = restoring (right button), False = erasing, None = not painting
        self._brush_at = None  # sheet pixel under the mouse while the eraser is on
        self.setMinimumSize(420, 420)

    # ---- content
    def set_content(self, images, cell, mask, size_wh, offsets, frame=None):
        self.images, self.cell, self.mask, self.size_wh, self.offsets, self.frame = images, cell, mask, size_wh, offsets, frame
        self._resize()
        self.update()

    def clear(self):
        self.images = []
        self.mask = None
        self._resize()
        self.update()

    def _view_rect(self):
        if self.frame is None:
            return QRect(0, 0, self.size_wh[0], self.size_wh[1])
        return QRect(self.frame[0] * self.cell[0], self.frame[1] * self.cell[1], self.cell[0], self.cell[1])

    def _scale(self):
        return self.zoom * (4 if self.frame is not None else 1)

    def _resize(self):
        if not self.images:
            self.setMinimumSize(420, 420)
            return
        r, z = self._view_rect(), self._scale()
        n = len(self.images)
        self.setMinimumSize(n * r.width() * z + (n - 1) * 12 + 2, r.height() * z + 24)

    # ---- painting
    def paintEvent(self, _e):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(64, 66, 74))
        if not self.images:
            p.setPen(QPen(QColor(200, 200, 210), 2, Qt.DashLine))
            box = self.rect().adjusted(14, 14, -14, -14)
            p.drawRoundedRect(box, 10, 10)
            p.drawText(box, Qt.AlignCenter, EMPTY_TEXT)
            p.end()
            return
        r, z = self._view_rect(), self._scale()
        for n, (label, img) in enumerate(self.images):
            ox = n * (r.width() * z + 12)
            for yy in range(0, r.height() * z, 8 * z):
                for xx in range(0, r.width() * z, 8 * z):
                    c = QColor(84, 86, 96) if (xx // (8 * z) + yy // (8 * z)) % 2 else QColor(74, 76, 86)
                    p.fillRect(ox + xx, 20 + yy, 8 * z, 8 * z, c)
            p.drawImage(QRect(ox, 20, r.width() * z, r.height() * z), img.copy(r))
            p.setPen(QColor(230, 230, 235))
            p.drawText(ox, 14, label)
            if self.frame is None:
                p.setPen(QColor(255, 255, 255, 40))
                cw, ch = self.cell
                for gx in range(0, r.width() + 1, cw):
                    p.drawLine(ox + gx * z, 20, ox + gx * z, 20 + r.height() * z)
                for gy in range(0, r.height() + 1, ch):
                    p.drawLine(ox, 20 + gy * z, ox + r.width() * z, 20 + gy * z)
                if self.selected is not None:
                    c, rr = self.selected
                    p.setPen(QPen(QColor(255, 210, 0), 2))
                    p.drawRect(ox + c * cw * z, 20 + rr * ch * z, cw * z, ch * z)
            if self.eraser and self._brush_at is not None:  # the eraser's square, in every color
                bx, by = self._brush_at
                lo = -(self.eraser // 2)
                x0, y0 = (bx + lo - r.x()) * z, (by + lo - r.y()) * z
                p.setPen(QPen(QColor(255, 255, 255), 1))
                p.setBrush(Qt.NoBrush)
                p.drawRect(ox + x0, 20 + y0, self.eraser * z - 1, self.eraser * z - 1)
                p.setPen(QPen(QColor(0, 0, 0), 1))
                p.drawRect(ox + x0 - 1, 20 + y0 - 1, self.eraser * z + 1, self.eraser * z + 1)
        p.end()

    # ---- mouse
    def _hit(self, pos: QPoint):
        """(sheet x, sheet y) under the mouse, or None."""
        if not self.images:
            return None
        r, z = self._view_rect(), self._scale()
        step = r.width() * z + 12
        n = pos.x() // step
        lx, ly = pos.x() - n * step, pos.y() - 20
        if n >= len(self.images) or not (0 <= lx < r.width() * z) or not (0 <= ly < r.height() * z):
            return None
        return r.x() + lx // z, r.y() + ly // z

    def _on_head(self, x, y) -> bool:
        if self.mask is None:
            return False
        w, h = self.size_wh
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                xx, yy = x + dx, y + dy
                if 0 <= xx < w and 0 <= yy < h and self.mask[yy * w + xx]:
                    return True
        return False

    def press(self, pos: QPoint, button=Qt.LeftButton):
        hit = self._hit(pos)
        if hit is None:
            return False
        cell = (hit[0] // self.cell[0], hit[1] // self.cell[1])
        self.selected = cell
        self.update()
        if self.eraser:
            self._erasing = button == Qt.RightButton
            self.erasePixel.emit(hit[0], hit[1], self._erasing)
            return True
        if button == Qt.RightButton:
            self.cellReset.emit(cell)
            return True
        if self._on_head(*hit):
            off = self.offsets.get(f"{cell[0]},{cell[1]}", [0, 0])
            self._drag = (cell, pos, int(off[0]), int(off[1]))
            self.setCursor(Qt.ClosedHandCursor)
            return True
        return False

    def move(self, pos: QPoint):
        if self.eraser:
            hit = self._hit(pos)
            if hit != self._brush_at:
                self._brush_at = hit
                self.update()
            if hit is not None and self._erasing is not None:
                self.erasePixel.emit(hit[0], hit[1], self._erasing)
            return
        if self._drag:
            cell, start, ox, oy = self._drag
            z = self._scale()
            self.headDragged.emit(cell, ox + round((pos.x() - start.x()) / z), oy + round((pos.y() - start.y()) / z))
            return
        hit = self._hit(pos)
        on = hit is not None and self._on_head(*hit)
        if on != self._hover:
            self._hover = on
            self.setCursor(Qt.OpenHandCursor if on else Qt.ArrowCursor)

    def release(self):
        if self._erasing is not None:
            self._erasing = None
            self.eraseFinished.emit()
            return
        if self._drag:
            self._drag = None
            self.setCursor(Qt.OpenHandCursor)
            self.headDragFinished.emit()

    def mousePressEvent(self, e):
        self.press(e.position().toPoint() if hasattr(e, "position") else e.pos(), e.button())

    def mouseMoveEvent(self, e):
        self.move(e.position().toPoint() if hasattr(e, "position") else e.pos())

    def mouseReleaseEvent(self, _e):
        self.release()

    def leaveEvent(self, _e):
        if self._brush_at is not None:
            self._brush_at = None
            self.update()

    def set_eraser(self, size: int):
        self.eraser = size
        self._brush_at = None
        self.setCursor(Qt.CrossCursor if size else Qt.ArrowCursor)
        self.update()

    # ---- drop
    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls() and any(
            _is_sheet(u.toLocalFile()) or u.toLocalFile().lower().endswith(".pusprite") for u in e.mimeData().urls()
        ):
            e.acceptProposedAction()

    def dropEvent(self, e):
        for u in e.mimeData().urls():
            path = u.toLocalFile()
            if _is_sheet(path) or path.lower().endswith(".pusprite"):
                self.fileDropped.emit(path)
                e.acceptProposedAction()
                return


class SpriteWorkshop(QDialog):
    def __init__(self, gs, parent=None):
        super().__init__(parent)
        self.gs = gs
        self.gd = gs.data
        self.workshop = ws.workshop_for(gs)
        # the sprite list of the last run comes back (autosaved next to the project's output folder)
        self._autosave_dir = ws.autosave_dir(self._roots()[0])
        self._restored = ws.restore(self.workshop, self._autosave_dir)
        if not self.workshop.session:
            self.workshop.session.append(ws.WorkshopProject())
        self.project = self.workshop.session[-1]
        self.project_path = None
        self._paths = {}  # id(project) -> .pusprite path
        self._auto_name = set()  # ids of projects whose name came from the sheet / head + class
        self._saved = set()  # ids of projects saved to the mod in this session
        self.prep = None
        self.sheets = {}
        self.mask = None
        self._frame = 0
        self._loading = False
        self.setWindowTitle("Paragon Unlimited - Sprite Workshop")
        self.setAcceptDrops(True)
        self.resize(1300, 820)

        # ================================================================ left: steps
        left = QVBoxLayout()

        list_box = QGroupBox("Sprites")
        ll = QVBoxLayout()
        self.sprite_list = QListWidget()
        self.sprite_list.setMaximumHeight(110)
        self.sprite_list.setToolTip(
            "Every sprite you make here. Pick one to work on it; each has its own sheet, name and\n"
            "characters / classes. \"Save all sprites\" saves every sprite in this list."
        )
        ll.addWidget(self.sprite_list)
        r = QHBoxLayout()
        self.new_sprite_button = QPushButton("New sprite")
        self.new_sprite_button.setToolTip("Start another sprite (the ones in the list stay).")
        self.remove_sprite_button = QPushButton("Remove from list")
        self.remove_sprite_button.setToolTip(
            "Takes the sprite off the list. One you already saved stays in the mod (unassign it in\n"
            "Characters -> Sprite Data, or remove its characters here first and save again)."
        )
        r.addWidget(self.new_sprite_button)
        r.addWidget(self.remove_sprite_button)
        r.addStretch(1)
        ll.addLayout(r)
        list_box.setLayout(ll)
        left.addWidget(list_box)

        start_box = QGroupBox("1. Start")
        sl = QVBoxLayout()
        self.tabs = QTabWidget()
        sheet_tab = QWidget()
        st = QVBoxLayout(sheet_tab)
        st.addWidget(QLabel("Drop a sheet you have on the big preview (PNG or .ctpk.lz), or:"))
        r = QHBoxLayout()
        self.browse_button = QPushButton("Browse...")
        r.addWidget(self.browse_button)
        self.sheet_label = QLabel("No sheet yet")
        self.sheet_label.setWordWrap(True)
        r.addWidget(self.sheet_label, 1)
        st.addLayout(r)
        r = QHBoxLayout()
        r.addWidget(QLabel("Drawn on the body of"))
        self.sheet_class_combo = QComboBox()
        _searchable(self.sheet_class_combo)
        self.sheet_class_combo.setToolTip(
            "The class body the sheet is drawn on. It tells the Workshop where the head is in each\n"
            "frame so you can drag it. Automatic finds the class with the closest outline."
        )
        r.addWidget(self.sheet_class_combo, 1)
        st.addLayout(r)
        st.addStretch(1)
        self.tabs.addTab(sheet_tab, "Use a sheet I have")
        build_tab = QWidget()
        bt = QFormLayout(build_tab)
        self.head_combo = QComboBox()
        _searchable(self.head_combo)
        bt.addRow("Head", self.head_combo)
        self.body_combo = QComboBox()
        _searchable(self.body_combo)
        bt.addRow("Body (class)", self.body_combo)
        self.build_button = QPushButton("Build sprite")
        bt.addRow(self.build_button)
        self.tabs.addTab(build_tab, "Build from a head and a class")
        sl.addWidget(self.tabs)
        start_box.setLayout(sl)
        left.addWidget(start_box)

        adj_box = QGroupBox("2. Adjust")
        al = QVBoxLayout()
        r = QHBoxLayout()
        self.opacity_check = QCheckBox("See-through like the game")
        self.opacity_check.setToolTip(
            "The game's map sprites are see-through: normal pixels 53 %, outlines 27 %.\n"
            "Plain (fully opaque) images are turned into that. Sheets already see-through stay as they are."
        )
        r.addWidget(self.opacity_check)
        self.opacity_slider = QSlider(Qt.Horizontal)
        self.opacity_slider.setRange(1, 15)  # RGBA4 steps of 1/15
        r.addWidget(self.opacity_slider, 1)
        self.opacity_label = QLabel("")
        r.addWidget(self.opacity_label)
        al.addLayout(r)
        self.adjust_tabs = QTabWidget()
        # move
        move_tab = QWidget()
        ml = QVBoxLayout(move_tab)
        tip = QLabel("Drag a head in the preview to move it in that frame. Right-click a frame to put its head back.")
        tip.setWordWrap(True)
        ml.addWidget(tip)
        r = QHBoxLayout()
        self.reset_frame_button = QPushButton("Reset selected frame")
        self.reset_all_button = QPushButton("Reset all frames")
        r.addWidget(self.reset_frame_button)
        r.addWidget(self.reset_all_button)
        ml.addLayout(r)
        ml.addStretch(1)
        self.adjust_tabs.addTab(move_tab, "Move head")
        # erase body / erase head
        self.eraser_sizes = {}
        for mode, title, text in (
            ("body", "Erase body", "Clean up leftovers of the old head or the body. Left-drag erases, right-drag puts "
                                   "the pixels back. Works on all three colors. The head is not touched."),
            ("head", "Erase head", "Erase part of the head in a frame. Left-drag erases, right-drag puts the pixels "
                                   "back. What you erase moves with the head when you drag it."),
        ):
            tab = QWidget()
            tl = QVBoxLayout(tab)
            lab = QLabel(text)
            lab.setWordWrap(True)
            tl.addWidget(lab)
            r = QHBoxLayout()
            r.addWidget(QLabel("Size"))
            size = QComboBox()
            for n in (1, 2, 3):
                size.addItem(f"{n} px", n)
            size.currentIndexChanged.connect(lambda _i: self._adjust_tab_changed())
            self.eraser_sizes[mode] = size
            r.addWidget(size)
            r.addStretch(1)
            undo = QPushButton("Undo")
            undo.clicked.connect(self._erase_undo)
            r.addWidget(undo)
            clear = QPushButton("Restore all")
            clear.setToolTip("Put back everything erased " + ("from the body" if mode == "body" else "from the heads"))
            clear.clicked.connect(lambda _c=False, m=mode: self._erase_clear(m))
            r.addWidget(clear)
            tl.addLayout(r)
            tl.addStretch(1)
            self.adjust_tabs.addTab(tab, title)
        self.eraser_size = self.eraser_sizes["body"]
        # copy head
        copy_tab = QWidget()
        cl = QVBoxLayout(copy_tab)
        lab = QLabel("Some classes have extra frames (Dancer, Sage...). Click a frame, Copy, click another "
                     "frame, Paste: it shows the same head (Ctrl+C / Ctrl+V work too).")
        lab.setWordWrap(True)
        cl.addWidget(lab)
        r = QHBoxLayout()
        self.copy_head_button = QPushButton("Copy head")
        self.paste_head_button = QPushButton("Paste head")
        self.paste_row_button = QPushButton("Paste in whole row")
        self.paste_row_button.setToolTip("Paste the copied head into every frame of the selected frame's row.")
        self.unpaste_button = QPushButton("Remove pasted head")
        self.unpaste_button.setToolTip("The selected frame shows its own head again.")
        for w_ in (self.copy_head_button, self.paste_head_button, self.paste_row_button):
            r.addWidget(w_)
        cl.addLayout(r)
        r = QHBoxLayout()
        self.copy_row_button = QPushButton("Copy row")
        self.copy_row_button.setToolTip("Copy the heads of the selected frame's whole row.")
        self.paste_rowwise_button = QPushButton("Paste row")
        self.paste_rowwise_button.setToolTip("The selected row shows the copied row's heads, frame by frame.")
        r.addWidget(self.copy_row_button)
        r.addWidget(self.paste_rowwise_button)
        cl.addLayout(r)
        r = QHBoxLayout()
        r.addWidget(self.unpaste_button)
        self.copy_label = QLabel("Nothing copied")
        r.addWidget(self.copy_label, 1)
        cl.addLayout(r)
        cl.addStretch(1)
        self.adjust_tabs.addTab(copy_tab, "Copy head")
        # size, flip, layer
        shape_tab = QWidget()
        sl2 = QVBoxLayout(shape_tab)
        r = QHBoxLayout()
        r.addWidget(QLabel("Head size"))
        self.scale_spin = QSpinBox()
        self.scale_spin.setRange(50, 150)
        self.scale_spin.setSingleStep(5)
        self.scale_spin.setSuffix(" %")
        self.scale_spin.setValue(100)
        self.scale_spin.setToolTip("Make the head smaller or bigger; it stays on the neck.")
        r.addWidget(self.scale_spin)
        self.scale_frame_button = QPushButton("Selected frame")
        self.scale_row_button = QPushButton("Row")
        self.scale_all_button = QPushButton("All frames")
        for w_ in (self.scale_frame_button, self.scale_row_button, self.scale_all_button):
            r.addWidget(w_)
        sl2.addLayout(r)
        r = QHBoxLayout()
        r.addWidget(QLabel("Mirror head"))
        self.flip_frame_button = QPushButton("Selected frame")
        self.flip_row_button = QPushButton("Row")
        self.flip_frame_button.setToolTip("Flip the head left-right (again to undo).")
        self.flip_row_button.setToolTip("Flip the heads of the selected frame's row left-right (again to undo).")
        r.addWidget(self.flip_frame_button)
        r.addWidget(self.flip_row_button)
        r.addStretch(1)
        sl2.addLayout(r)
        r = QHBoxLayout()
        r.addWidget(QLabel("Head layer"))
        self.layer_combo = QComboBox()
        self.layer_combo.addItem("In front of the body", False)
        self.layer_combo.addItem("Behind the body", True)
        self.layer_combo.setToolTip("Behind: the body (collar, hands, weapon) covers the head where they overlap.")
        r.addWidget(self.layer_combo)
        self.layer_frame_button = QPushButton("Switch for selected frame")
        r.addWidget(self.layer_frame_button)
        sl2.addLayout(r)
        sl2.addStretch(1)
        self.adjust_tabs.addTab(shape_tab, "Size / mirror / layer")
        al.addWidget(self.adjust_tabs)
        adj_box.setLayout(al)
        left.addWidget(adj_box)

        save_box = QGroupBox("3. Save to your mod")
        vl = QVBoxLayout()
        form = QFormLayout()
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("e.g. ChromWyvern  (the file names get 青/赤/緑 added)")
        form.addRow("Sprite name", self.name_edit)
        vl.addLayout(form)
        r = QHBoxLayout()
        self.char_combo = QComboBox()
        _searchable(self.char_combo)
        self.job_combo = QComboBox()
        _searchable(self.job_combo)
        self._fill_people()
        r.addWidget(QLabel("Use for"))
        r.addWidget(self.char_combo, 1)
        r.addWidget(QLabel("as"))
        r.addWidget(self.job_combo, 1)
        self.assign_add = QPushButton("Add")
        r.addWidget(self.assign_add)
        vl.addLayout(r)
        self.assign_list = QListWidget()
        self.assign_list.setMaximumHeight(60)
        vl.addWidget(self.assign_list)
        r = QHBoxLayout()
        self.assign_remove = QPushButton("Remove selected")
        self.export_button = QPushButton("Save all sprites")
        self.export_button.setToolTip(
            "For every sprite in the list: makes map/unit/<name>青/赤/緑.ctpk.lz (written when you save\n"
            "the project), adds its BMap icon entry and sets its characters' sprite for its classes."
        )
        r.addWidget(self.assign_remove)
        r.addStretch(1)
        r.addWidget(self.export_button)
        vl.addLayout(r)
        save_box.setLayout(vl)
        left.addWidget(save_box)

        self.adv_box = QGroupBox("Advanced")
        self.adv_box.setCheckable(True)
        self.adv_box.setChecked(False)
        adv = QFormLayout()
        self.team_combo = QComboBox()
        self.team_combo.addItem("Blue (as the game draws player units)", "blue")
        self.team_combo.addItem("Red (the sheet is the enemy look)", "red")
        adv.addRow("Team color in the sheet", self.team_combo)
        r = QHBoxLayout()
        self.ref_combo = QComboBox()
        _searchable(self.ref_combo)
        self.ref_combo.setToolTip(
            "The game sprite whose red / green pixels and BMap animation are used (automatic: the body)."
        )
        r.addWidget(self.ref_combo, 1)
        self.auto_ref_button = QPushButton("Find by shape")
        r.addWidget(self.auto_ref_button)
        adv.addRow("Color reference", r)
        self.head_mode_combo = QComboBox()
        self.head_mode_combo.addItem("Keep (hair, skin, eyes)", ws.HEAD_KEEP)
        self.head_mode_combo.addItem("Change team colors too (helmets, hats)", ws.HEAD_TEAM)
        adv.addRow("Head colors for enemy / ally", self.head_mode_combo)
        self.register_check = QCheckBox("Add a BMap icon entry (animation copied from the reference)")
        adv.addRow(self.register_check)
        r = QHBoxLayout()
        self.new_button = QPushButton("New")
        self.open_button = QPushButton("Open...")
        self.save_button = QPushButton("Save")
        self.save_as_button = QPushButton("Save As...")
        for b in (self.new_button, self.open_button, self.save_button, self.save_as_button):
            r.addWidget(b)
        adv.addRow("Workshop project", r)
        self.validate_button = QPushButton("Check")
        adv.addRow(self.validate_button)
        self.adv_inner = QWidget()
        self.adv_inner.setLayout(adv)
        al2 = QVBoxLayout()
        al2.addWidget(self.adv_inner)
        self.adv_box.setLayout(al2)
        self.adv_inner.setVisible(False)
        left.addWidget(self.adv_box)

        self.report = QPlainTextEdit()
        self.report.setReadOnly(True)
        self.report.setMaximumHeight(110)
        left.addWidget(self.report)
        if self._restored:
            self.report.setPlainText(
                f"Your sprite list from last time is back ({self._restored} sprite"
                f"{'s' if self._restored > 1 else ''}). Click Save all sprites to put them in the mod again "
                "if you closed Paragon without saving the project.")
        left.addStretch(1)

        left_widget = QWidget()
        left_widget.setLayout(left)
        left_scroll = QScrollArea()
        left_scroll.setWidgetResizable(True)
        left_scroll.setWidget(left_widget)
        left_scroll.setMinimumWidth(470)
        left_scroll.setMaximumWidth(560)

        # ================================================================ right: preview
        right = QVBoxLayout()
        bar = QHBoxLayout()
        self.variant_group = QButtonGroup(self)
        self.variant_buttons = {}
        for key, label in (("青", "Player"), ("赤", "Enemy"), ("緑", "Ally"), ("all", "All three")):
            b = QRadioButton(label)
            self.variant_group.addButton(b)
            self.variant_buttons[key] = b
            bar.addWidget(b)
        self.variant_buttons["all"].setChecked(True)
        bar.addSpacing(12)
        self.view_combo = QComboBox()
        self.view_combo.addItem("Whole sheet", 0)
        for i in range(1, 14):
            self.view_combo.addItem(f"Animation {i}", i)
        bar.addWidget(self.view_combo)
        self.play_button = QPushButton("Pause")
        bar.addWidget(self.play_button)
        bar.addWidget(QLabel("Zoom"))
        self.zoom_spin = QSpinBox()
        self.zoom_spin.setRange(1, 8)
        self.zoom_spin.setValue(3)
        bar.addWidget(self.zoom_spin)
        self.heads_check = QCheckBox("Highlight heads")
        bar.addWidget(self.heads_check)
        bar.addStretch(1)
        right.addLayout(bar)
        self.canvas = SheetCanvas()
        self.canvas_scroll = QScrollArea()
        self.canvas_scroll.setWidgetResizable(True)
        self.canvas_scroll.setWidget(self.canvas)
        right.addWidget(self.canvas_scroll, 1)
        self.status = QLabel("")
        self.status.setWordWrap(True)
        right.addWidget(self.status)
        right_widget = QWidget()
        right_widget.setLayout(right)

        layout = QHBoxLayout()
        layout.addWidget(left_scroll, 0)
        layout.addWidget(right_widget, 1)
        self.setLayout(layout)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._next_frame)
        self.autosave_timer = QTimer(self)
        self.autosave_timer.timeout.connect(self._autosave)
        self.autosave_timer.start(20000)
        self._playing = True

        self._fill_choices()

        # ================================================================ signals
        self.canvas.fileDropped.connect(self._file_dropped)
        self.canvas.headDragged.connect(self._head_dragged)
        self.canvas.headDragFinished.connect(self._recompose)
        self.canvas.cellReset.connect(self._reset_cell)
        self.browse_button.clicked.connect(self._browse)
        self.build_button.clicked.connect(self._build_from_parts)
        self.head_combo.currentIndexChanged.connect(self._head_changed)
        self.body_combo.currentIndexChanged.connect(self._head_changed)
        self.sheet_class_combo.currentIndexChanged.connect(self._sheet_inputs_changed)
        self.opacity_check.toggled.connect(self._sheet_inputs_changed)
        self.opacity_slider.valueChanged.connect(self._opacity_moved)
        self.opacity_slider.sliderReleased.connect(self._sheet_inputs_changed)
        self.reset_frame_button.clicked.connect(lambda: self._reset_cell(self.canvas.selected))
        self.reset_all_button.clicked.connect(self._reset_all)
        self.adjust_tabs.currentChanged.connect(lambda _i: self._adjust_tab_changed())
        self.copy_head_button.clicked.connect(self._copy_head)
        self.paste_head_button.clicked.connect(lambda: self._paste_head(False))
        self.paste_row_button.clicked.connect(lambda: self._paste_head(True))
        self.unpaste_button.clicked.connect(self._unpaste_head)
        self.copy_row_button.clicked.connect(self._copy_row)
        self.paste_rowwise_button.clicked.connect(self._paste_row)
        self.scale_frame_button.clicked.connect(lambda: self._set_scale("frame"))
        self.scale_row_button.clicked.connect(lambda: self._set_scale("row"))
        self.scale_all_button.clicked.connect(lambda: self._set_scale("all"))
        self.flip_frame_button.clicked.connect(lambda: self._flip("frame"))
        self.flip_row_button.clicked.connect(lambda: self._flip("row"))
        self.layer_combo.currentIndexChanged.connect(self._layer_changed)
        self.layer_frame_button.clicked.connect(self._swap_layer)
        self._copied_row = None
        from PySide6.QtGui import QKeySequence, QShortcut

        QShortcut(QKeySequence.Copy, self, activated=self._copy_head)
        QShortcut(QKeySequence.Paste, self, activated=lambda: self._paste_head(False))
        self._copied = None
        self.canvas.erasePixel.connect(self._erase_at)
        self.canvas.eraseFinished.connect(self._erase_finished)
        self._erase_undo_stack = []
        self._erase_stroke = None
        self.assign_add.clicked.connect(self._add_assignment)
        self.assign_remove.clicked.connect(self._remove_assignment)
        self.export_button.clicked.connect(self._export)
        self.adv_box.toggled.connect(self.adv_inner.setVisible)
        self.team_combo.currentIndexChanged.connect(self._colors_changed)
        self.ref_combo.currentIndexChanged.connect(self._colors_changed)
        self.head_mode_combo.currentIndexChanged.connect(self._colors_changed)
        self.auto_ref_button.clicked.connect(self._auto_reference)
        self.new_button.clicked.connect(self._new)
        self.open_button.clicked.connect(self._open)
        self.save_button.clicked.connect(self._save)
        self.save_as_button.clicked.connect(lambda: self._save(True))
        self.validate_button.clicked.connect(self._validate)
        self.variant_group.buttonToggled.connect(lambda *_: self._show())
        self.view_combo.currentIndexChanged.connect(self._view_changed)
        self.play_button.clicked.connect(self._toggle_play)
        self.zoom_spin.valueChanged.connect(lambda *_: self._show())
        self.heads_check.toggled.connect(lambda *_: self._show())
        self.name_edit.textEdited.connect(self._name_typed)
        self.name_edit.textChanged.connect(lambda t: (setattr(self.project, "name", t.strip()), self._update_label()))
        self.register_check.toggled.connect(lambda v: setattr(self.project, "register", v))
        self.sprite_list.currentRowChanged.connect(self._sprite_selected)
        self.new_sprite_button.clicked.connect(self._new_sprite)
        self.remove_sprite_button.clicked.connect(self._remove_sprite)

        self._refresh_sprite_list()
        self._load_project(self.project)

    # ================================================================ lists
    def _fill_choices(self):
        w = self.workshop
        self.head_combo.addItem("- pick a character -", "")
        for label, code in w.head_choices():
            self.head_combo.addItem(label, code)
        self.body_combo.addItem("- pick a class -", "")
        for label, key in w.body_choices():
            self.body_combo.addItem(label, key)
        self.sheet_class_combo.addItem("Automatic (closest outline)", "")
        self.sheet_class_combo.addItem("None (don't move heads)", "-")
        for label, key in w.body_choices():
            self.sheet_class_combo.addItem(label, key)
        self.ref_combo.addItem("Automatic (the body)", "")
        try:
            for n in w.game_sprite_names():
                self.ref_combo.addItem(w.names.sprite(n), n)
        except Exception:
            logging.exception("Sprite Workshop: could not list game sprites.")

    def _fill_people(self):
        try:
            chars = self.gd.table("characters")
            for c in self.gd.items(chars[0], chars[1]):
                pid = self.gd.key(c)
                if pid:
                    self.char_combo.addItem(f"{self.gd.display(c) or pid}", pid)
            jobs = self.gd.table("jobs")
            for j in self.gd.items(jobs[0], jobs[1]):
                jid = self.gd.key(j)
                if jid:
                    sex = " (F)" if jid.endswith("女") else " (M)" if jid.endswith("男") else ""
                    self.job_combo.addItem(f"{self.gd.display(j) or jid}{sex}", jid)
        except Exception:
            logging.exception("Sprite Workshop: could not list characters / classes.")

    @staticmethod
    def _select(combo: QComboBox, data):
        i = combo.findData(data)
        if i >= 0:
            combo.setCurrentIndex(i)

    # ================================================================ project <-> widgets
    def _load_project(self, p: ws.WorkshopProject):
        self._loading = True
        try:
            self.name_edit.setText(p.name)
            self.tabs.setCurrentIndex(1 if p.mode == "build" else 0)
            self.sheet_label.setText(os.path.basename(p.sheet) if p.sheet else "No sheet yet")
            self._select(self.sheet_class_combo, p.sheet_class)
            self.opacity_check.setChecked(p.opacity)
            self.opacity_slider.setValue(max(1, min(15, round(p.fill_alpha / 17))))
            self._opacity_moved(self.opacity_slider.value())
            self._select(self.head_combo, p.head_char)
            self._select(self.body_combo, p.body_class)
            self._select(self.team_combo, p.team_color)
            self._select(self.ref_combo, p.reference)
            self._select(self.head_mode_combo, p.head_mode)
            self._select(self.layer_combo, bool(p.head_behind))
            self.register_check.setChecked(p.register)
            self.assign_list.clear()
            for a in p.assign:
                self.assign_list.addItem(f"{a['pid']} as {a['jid']}")
        finally:
            self._loading = False
        has_input = (p.mode == "build" and p.head_char and p.body_class) or (p.mode == "sheet" and p.sheet)
        if has_input:
            self._prepare()
        else:
            self.prep = None
            self.sheets = {}
            self.canvas.clear()
            self.status.setText("")

    def _read_common(self):
        p = self.project
        p.name = self.name_edit.text().strip()
        p.team_color = self.team_combo.currentData() or "blue"
        p.reference = self.ref_combo.currentData() or ""
        p.head_mode = self.head_mode_combo.currentData() or ws.HEAD_KEEP
        p.register = self.register_check.isChecked()
        p.opacity = self.opacity_check.isChecked()
        p.fill_alpha = self.opacity_slider.value() * 17
        p.sheet_class = self.sheet_class_combo.currentData() or ""

    # ================================================================ sprite list
    def _label(self, p) -> str:
        n = len(p.assign)
        text = p.name or "(no name yet)"
        if n:
            text += f"  - {n} character/class" + ("es" if n > 1 else "")
        if id(p) in self._saved:
            text += "  (saved)"
        return text

    def _refresh_sprite_list(self):
        self.sprite_list.blockSignals(True)
        try:
            self.sprite_list.clear()
            for p in self.workshop.session:
                self.sprite_list.addItem(self._label(p))
            if self.project in self.workshop.session:
                self.sprite_list.setCurrentRow(self.workshop.session.index(self.project))
        finally:
            self.sprite_list.blockSignals(False)
        self._autosave(read=False)

    def _autosave(self, read=True):
        """Keeps the sprite list on disk, so closing Paragon (or a crash) loses nothing."""
        if not self._autosave_dir:
            return
        try:
            if read and not self._loading:
                self._read_common()
            ws.autosave(self.workshop, self._autosave_dir)
        except Exception:
            logging.exception("Sprite Workshop autosave failed.")

    def _update_label(self):
        if self.project in self.workshop.session:
            item = self.sprite_list.item(self.workshop.session.index(self.project))
            if item is not None:
                item.setText(self._label(self.project))

    def _switch_to(self, p):
        self.project_path = self._paths.get(id(p))
        self.project = p
        self._erase_undo_stack = []
        self._refresh_sprite_list()
        self._load_project(p)

    def _sprite_selected(self, row):
        if self._loading or not (0 <= row < len(self.workshop.session)):
            return
        p = self.workshop.session[row]
        if p is self.project:
            return
        self._read_common()
        self._paths[id(self.project)] = self.project_path
        self._switch_to(p)

    def _new_sprite(self):
        self._read_common()
        self._paths[id(self.project)] = self.project_path
        p = ws.WorkshopProject()
        self.workshop.session.append(p)
        self._switch_to(p)

    def _remove_sprite(self):
        if self.project not in self.workshop.session:
            return
        i = self.workshop.session.index(self.project)
        del self.workshop.session[i]
        if not self.workshop.session:
            self.workshop.session.append(ws.WorkshopProject())
        self._switch_to(self.workshop.session[min(i, len(self.workshop.session) - 1)])

    def _name_typed(self, _text):
        self._auto_name.discard(id(self.project))
        self._update_label()

    def _start_input(self):
        """Before a new sheet / head + class: a sprite that already has characters or was saved
        stays as it is and a new sprite is started; otherwise the current one is reused."""
        p = self.project
        if ws.has_input(p) and (p.assign or id(p) in self._saved):
            self._read_common()
            self._paths[id(p)] = self.project_path
            n = ws.WorkshopProject()
            n.team_color, n.opacity, n.fill_alpha = p.team_color, p.opacity, p.fill_alpha
            self.workshop.session.append(n)
            self.project = n
            self.project_path = None
            self._refresh_sprite_list()
            self._loading = True
            try:
                self.name_edit.setText("")
                self.assign_list.clear()
            finally:
                self._loading = False
            return True
        return False

    def _auto_set_name(self, name):
        p = self.project
        if not p.name or id(p) in self._auto_name:
            p.name = name
            self._auto_name.add(id(p))
            self.name_edit.setText(p.name)
        self._update_label()

    # ================================================================ start
    def _browse(self):
        path, _ = QFileDialog.getOpenFileName(self, "Sprite sheet", "", SHEET_FILTER)
        if path:
            self._set_sheet(path)

    def _file_dropped(self, path):
        if path.lower().endswith(".pusprite"):
            self._open(path)
        else:
            self._set_sheet(path)

    def _set_sheet(self, path):
        self._read_common()
        self._start_input()
        p = self.project
        p.mode, p.sheet, p.sheet_sha256 = "sheet", path, ws.file_digest(path)
        p.head_frames = {}
        p.erased = []
        p.head_erased = []
        p.head_copies = {}
        p.head_scale = {}
        p.head_flip = []
        p.head_layer_swap = []
        self._erase_undo_stack = []
        base = os.path.splitext(os.path.basename(path))[0]
        if base.endswith(".ctpk"):
            base = base[:-5]
        self._auto_set_name(base.rstrip("青赤緑")[:20])
        self.sheet_label.setText(os.path.basename(path))
        self.tabs.setCurrentIndex(0)
        self._prepare()

    def _head_changed(self, *_):
        pass

    def _build_from_parts(self):
        code, body = self.head_combo.currentData(), self.body_combo.currentData()
        src = self.workshop.best_head_source(code, body) if code and body else None
        if not code or not body or not src:
            QMessageBox.information(self, "Sprite Workshop", "Pick a head (character) and a body (class) first.")
            return
        self._read_common()
        self._start_input()
        p = self.project
        p.mode, p.head_char, p.body_class, p.head_class = "build", code, body, src
        p.head_frames = {}
        p.erased = []
        p.head_erased = []
        p.head_copies = {}
        p.head_scale = {}
        p.head_flip = []
        p.head_layer_swap = []
        self._erase_undo_stack = []
        self._auto_set_name("Custom" + str(sum(ord(c) for c in code + body) % 10000))
        self._prepare()

    def _sheet_inputs_changed(self, *_):
        if self._loading or self.opacity_slider.isSliderDown():
            return
        self._read_common()
        if self.project.mode == "sheet" and self.project.sheet:
            self._prepare()

    def _opacity_moved(self, v):
        self.opacity_label.setText(f"{round(v * 100 / 15)} %")
        if not self._loading and not self.opacity_slider.isSliderDown():
            self._sheet_inputs_changed()

    def _colors_changed(self, *_):
        if self._loading:
            return
        self._read_common()
        if self.prep is not None:
            if self.project.reference and self.prep.reference != self.project.reference:
                self._prepare()
            else:
                self._recompose()

    # ================================================================ build + preview
    def _prepare(self):
        """Split the sprite into body + heads (the slow part), then compose."""
        self.setCursor(Qt.WaitCursor)
        try:
            self.prep = self.workshop.prepare(self.project)
        except Exception as e:
            logging.exception("Sprite Workshop: prepare failed.")
            self.prep = None
            self.sheets = {}
            self.canvas.clear()
            self.status.setText(f"Cannot build the sprite: {e}")
            return
        finally:
            self.unsetCursor()
        self._recompose()

    def _recompose(self):
        if self.prep is None:
            return
        try:
            self.sheets = self.workshop.build(self.project, prep=self.prep)
            _s, self.mask, cut = self.workshop.compose_project(self.prep, "青", self.project)
        except Exception as e:
            logging.exception("Sprite Workshop: build failed.")
            self.status.setText(f"Cannot build the sprite: {e}")
            return
        b = self.sheets["青"]
        parts = []
        if self.prep.class_key:
            parts.append(f"Body: {self.workshop.class_label(self.prep.class_key)}")
        if self.prep.reference:
            parts.append(f"colors / animation from {self.workshop.names.sprite(self.prep.reference)}")
        parts.append(f"{b.width} x {b.height}")
        n = len(self.project.head_frames)
        if n:
            parts.append(f"{n} frame(s) with a moved head")
        if self.project.erased:
            parts.append(f"{len(self.project.erased)} body pixel(s) erased")
        if self.project.head_erased:
            parts.append(f"{len(self.project.head_erased)} head pixel(s) erased")
        if self.project.head_copies:
            parts.append(f"{len(self.project.head_copies)} frame(s) with a copied head")
        if self.project.head_scale:
            parts.append(f"{len(self.project.head_scale)} frame(s) resized")
        if self.project.head_flip:
            parts.append(f"{len(self.project.head_flip)} frame(s) mirrored")
        if self.project.head_behind or self.project.head_layer_swap:
            parts.append("heads behind the body" if self.project.head_behind else "some heads behind the body")
        if cut:
            parts.append(f"{cut} head pixels pushed out of their frame are cut off")
        if self.prep.note:
            parts.append(self.prep.note)
        self.status.setText(" - ".join(parts))
        self._show()

    def _show(self):
        if not self.sheets or self.prep is None:
            return
        keys = [k for k, _l in VARIANTS] if self.variant_buttons["all"].isChecked() else [
            k for k, _l in VARIANTS if self.variant_buttons[k].isChecked()
        ]
        labels = dict(VARIANTS)
        images = [(labels[k], _qimage(self.sheets[k], self.mask, self.heads_check.isChecked())) for k in keys]
        frame = None
        anim = self._anim()
        if anim and anim[2]:
            x, y, _d = anim[2][self._frame % len(anim[2])]
            frame = (x, y)
        b = self.sheets["青"]
        self.canvas.zoom = self.zoom_spin.value()
        self.canvas.set_content(images, self.prep.cell, self.mask if self.prep.class_key else None,
                                (b.width, b.height), self.project.head_frames, frame)

    def _anim(self):
        which = self.view_combo.currentData() or 0
        if not which or self.prep is None:
            return None
        try:
            return self.workshop.animation(self.prep.reference, which)
        except Exception:
            return None

    def _view_changed(self, *_):
        self.timer.stop()
        self._frame = 0
        if self.view_combo.currentData() and self._playing:
            self.timer.start(100)
        self._show()

    def _next_frame(self):
        anim = self._anim()
        if not anim or not anim[2]:
            return
        self._frame = (self._frame + 1) % len(anim[2])
        self.timer.setInterval(max(16, int(anim[2][self._frame][2] * 1000 / 60)))
        self._show()

    def _toggle_play(self):
        self._playing = not self._playing
        self.play_button.setText("Pause" if self._playing else "Play")
        if self._playing and self.view_combo.currentData():
            self.timer.start(100)
        else:
            self.timer.stop()

    # ================================================================ head moves
    def _head_dragged(self, cell, dx, dy):
        key = f"{cell[0]},{cell[1]}"
        if dx or dy:
            self.project.head_frames[key] = [dx, dy]
        else:
            self.project.head_frames.pop(key, None)
        if self._playing and self.view_combo.currentData():
            self._toggle_play()  # hold the frame while dragging
        try:  # live: the player color only (the others follow when the mouse is released)
            blue, self.mask, _cut = self.workshop.compose_project(self.prep, "青", self.project)
            self.sheets["青"] = blue
        except Exception:
            return
        self._show()

    # ================================================================ clean-up eraser
    def _erase_mode(self):
        return {1: "body", 2: "head"}.get(self.adjust_tabs.currentIndex())

    def _adjust_tab_changed(self):
        mode = self._erase_mode()
        self.canvas.set_eraser(self.eraser_sizes[mode].currentData() if mode else 0)

    def _snapshot(self):
        return ([list(p) for p in self.project.erased], [list(p) for p in self.project.head_erased])

    def _erase_at(self, x, y, restore):
        if self.prep is None or not self.sheets:
            return
        mode = self._erase_mode() or "body"
        if self._erase_stroke is None:  # start of a stroke: remember for Undo
            self._erase_stroke = self._snapshot()
            if self._playing and self.view_combo.currentData():
                self._toggle_play()
        b = self.sheets["青"]
        pts = self.workshop_brush(x, y, (b.width, b.height))
        if mode == "head":
            cw, ch = self.prep.cell
            items = []
            for px, py in pts:
                c, r = px // cw, py // ch
                ox, oy = self.project.head_frames.get(f"{c},{r}", (0, 0))
                items.append((c, r, px - c * cw - int(ox), py - r * ch - int(oy)))
            target = "head_erased"
        else:
            items, target = pts, "erased"
        done = {tuple(p) for p in getattr(self.project, target)}
        before = set(done)
        for it in items:
            if restore:
                done.discard(it)
            else:
                done.add(it)
        if done == before:
            return
        setattr(self.project, target, [list(p) for p in sorted(done)])
        try:  # live: the player color only (the others follow when the mouse is released)
            blue, self.mask, _cut = self.workshop.compose_project(self.prep, "青", self.project)
            self.sheets["青"] = blue
        except Exception:
            return
        self._show()

    def workshop_brush(self, x, y, wh):
        from paragon.unlimited.sprites.sprite_sheets import brush_pixels

        size = self.eraser_sizes[self._erase_mode() or "body"].currentData() or 1
        return brush_pixels(x, y, size, self.prep.cell, wh)

    def _erase_finished(self):
        if self._erase_stroke is not None:
            if self._erase_stroke != self._snapshot():
                self._erase_undo_stack.append(self._erase_stroke)
                del self._erase_undo_stack[:-50]
            self._erase_stroke = None
            self._recompose()

    def _erase_undo(self):
        if self._erase_undo_stack:
            self.project.erased, self.project.head_erased = self._erase_undo_stack.pop()
            self._recompose()

    def _erase_clear(self, mode="body"):
        target = "head_erased" if mode == "head" else "erased"
        if getattr(self.project, target):
            self._erase_undo_stack.append(self._snapshot())
            setattr(self.project, target, [])
            self._recompose()

    # ================================================================ copy / paste a frame's head
    def _copy_head(self):
        cell = self.canvas.selected
        if cell is None or self.prep is None:
            self.copy_label.setText("Click a frame first")
            return
        # a frame that shows a copied head passes on the original
        self._copied = self.project.head_copies.get(f"{cell[0]},{cell[1]}", f"{cell[0]},{cell[1]}")
        c, r = (int(v) for v in self._copied.split(","))
        self.copy_label.setText(f"Copied: row {r + 1}, frame {c + 1}")

    def _paste_head(self, whole_row=False):
        cell = self.canvas.selected
        if cell is None or self.prep is None or not self._copied:
            self.copy_label.setText("Copy a head, then click a frame" if not self._copied else "Click a frame first")
            return
        cols = range(self.sheets["青"].width // self.prep.cell[0]) if whole_row else [cell[0]]
        src = self._copied
        offset = self.project.head_frames.get(src)
        for c in cols:
            key = f"{c},{cell[1]}"
            if key == src:
                continue
            self.project.head_copies[key] = src
            if offset:  # start where the copied head sits in its own frame
                self.project.head_frames[key] = list(offset)
        self._recompose()

    def _frames(self, scope):
        """Frame keys "col,row" for the selected frame, its row or the whole sheet."""
        cell = self.canvas.selected
        if self.prep is None or not self.sheets:
            return []
        cw, ch = self.prep.cell
        b = self.sheets["青"]
        cols, rows = b.width // cw, b.height // ch
        if scope == "all":
            return [f"{c},{r}" for r in range(rows) for c in range(cols)]
        if cell is None:
            self.status.setText("Click a frame first.")
            return []
        if scope == "row":
            return [f"{c},{cell[1]}" for c in range(cols)]
        return [f"{cell[0]},{cell[1]}"]

    def _set_scale(self, scope):
        f = self.scale_spin.value() / 100.0
        for k in self._frames(scope):
            if abs(f - 1.0) < 1e-6:
                self.project.head_scale.pop(k, None)
            else:
                self.project.head_scale[k] = f
        self._recompose()

    def _flip(self, scope):
        flips = set(self.project.head_flip)
        for k in self._frames(scope):
            flips ^= {k}
        self.project.head_flip = sorted(flips)
        self._recompose()

    def _layer_changed(self, *_):
        if self._loading:
            return
        self.project.head_behind = bool(self.layer_combo.currentData())
        self._recompose()

    def _swap_layer(self):
        swap = set(self.project.head_layer_swap)
        for k in self._frames("frame"):
            swap ^= {k}
        self.project.head_layer_swap = sorted(swap)
        self._recompose()

    def _copy_row(self):
        cell = self.canvas.selected
        if cell is None or self.prep is None:
            self.copy_label.setText("Click a frame first")
            return
        self._copied_row = cell[1]
        self.copy_label.setText(f"Copied: row {cell[1] + 1}")

    def _paste_row(self):
        cell = self.canvas.selected
        if cell is None or self.prep is None or self._copied_row is None:
            self.copy_label.setText("Copy a row, then click a frame of the row to paste in")
            return
        src_r, dst_r = self._copied_row, cell[1]
        if src_r == dst_r:
            return
        cols = self.sheets["青"].width // self.prep.cell[0]
        for c in range(cols):
            src = self.project.head_copies.get(f"{c},{src_r}", f"{c},{src_r}")
            self.project.head_copies[f"{c},{dst_r}"] = src
            off = self.project.head_frames.get(src)
            if off:
                self.project.head_frames[f"{c},{dst_r}"] = list(off)
        self._recompose()

    def _unpaste_head(self):
        cell = self.canvas.selected
        if cell is not None and self.project.head_copies.pop(f"{cell[0]},{cell[1]}", None) is not None:
            self._recompose()

    def _reset_cell(self, cell):
        if cell is None:
            return
        if self.project.head_frames.pop(f"{cell[0]},{cell[1]}", None) is not None:
            self._recompose()

    def _reset_all(self):
        if self.project.head_frames:
            self.project.head_frames.clear()
            self._recompose()

    # ================================================================ save
    def _add_assignment(self):
        pid, jid = self.char_combo.currentData(), self.job_combo.currentData()
        if not pid or not jid:
            return
        a = {"pid": pid, "jid": jid}
        if a not in self.project.assign:
            self.project.assign.append(a)
            self.assign_list.addItem(f"{self.char_combo.currentText()} as {self.job_combo.currentText()}")
            self._update_label()

    def _remove_assignment(self):
        row = self.assign_list.currentRow()
        if 0 <= row < len(self.project.assign):
            del self.project.assign[row]
            self.assign_list.takeItem(row)
            self._update_label()

    def _auto_reference(self):
        if not self.sheets:
            return
        self.setCursor(Qt.WaitCursor)
        try:
            best = self.workshop.auto_reference(self.sheets["青"])
        finally:
            self.unsetCursor()
        if best:
            self._select(self.ref_combo, best)

    def _roots(self):
        project = getattr(self.gs, "project", None)
        return [getattr(project, "output_path", None), getattr(project, "rom_path", None)]

    def _export(self):
        self._read_common()
        todo = [p for p in self.workshop.session if ws.has_input(p)]
        if not todo:
            QMessageBox.information(self, "Sprite Workshop", "Load a sheet or build a sprite first.")
            return
        self.setCursor(Qt.WaitCursor)
        try:
            lines = self.workshop.export_all(self.workshop.session, self._roots()[0])
        except Exception as e:
            logging.exception("Sprite Workshop export failed.")
            QMessageBox.warning(self, "Sprite Workshop", f"Could not save the sprites: {e}")
            return
        finally:
            self.unsetCursor()
        for p in todo:
            self._saved.add(id(p))
        self._refresh_sprite_list()
        self.report.setPlainText(
            "Saved (written to the mod when you save the project):\n" + "\n".join("  " + l for l in lines)
        )

    def _validate(self):
        self._read_common()
        results = self.workshop.validate(self.project, self._roots())
        lines = [("OK: " if s == "ok" else s.upper() + ": ") + m for s, m in results] + self._mod_folder_check()
        self.report.setPlainText("\n".join(lines))
        return results

    def _mod_folder_check(self):
        """Info: are the files in the Azahar mod folder yet?"""
        try:
            from paragon.unlimited.tools import azahar
            from paragon.unlimited.tools import file_case

            root = azahar.detect_mod_root()
            if not root or not self.project.name:
                return []
            romfs = os.path.join(root, azahar.BASE_TITLE, "romfs")
            file_case.clear_cache()
            missing = [
                c for c, _e, _l in ws.COLORS
                if file_case.find(romfs, f"{ws.UNIT_DIR}/{self.project.name}{c}.ctpk.lz")[0] != "exact"
            ]
            if missing:
                return ["INFO: not in the Azahar mod folder yet (save, then Copy to Emulator)."]
            return ["INFO: all three files are in the Azahar mod folder."]
        except Exception:
            return []

    # ================================================================ project files
    def _new(self):
        self._new_sprite()

    def _open(self, path=None):
        if not path:
            path, _ = QFileDialog.getOpenFileName(self, "Open Sprite Workshop project", "", PROJECT_FILTER)
        if not path:
            return
        try:
            p = ws.WorkshopProject.open(path)
        except Exception as e:
            QMessageBox.warning(self, "Sprite Workshop", f"Could not open: {e}")
            return
        self._read_common()
        self._paths[id(self.project)] = self.project_path
        if ws.has_input(self.project) or self.project.assign:
            self.workshop.session.append(p)
        else:
            self.workshop.session[self.workshop.session.index(self.project)] = p
        self._paths[id(p)] = path
        self._switch_to(p)

    def _save(self, ask=False):
        self._read_common()
        path = self.project_path
        if ask or not path:
            path, _ = QFileDialog.getSaveFileName(
                self, "Save Sprite Workshop project", (self.project.name or "sprite") + ".pusprite", PROJECT_FILTER
            )
        if not path:
            return
        try:
            self.project.save(path)
        except Exception as e:
            QMessageBox.warning(self, "Sprite Workshop", f"Could not save: {e}")
            return
        self.project_path = path
        self._paths[id(self.project)] = path

    # ================================================================ window-wide drop
    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            paths = [u.toLocalFile() for u in e.mimeData().urls()]
            if any(_is_sheet(p) or p.lower().endswith(".pusprite") for p in paths):
                e.acceptProposedAction()

    def dropEvent(self, e):
        for u in e.mimeData().urls():
            path = u.toLocalFile()
            if _is_sheet(path) or path.lower().endswith(".pusprite"):
                self._file_dropped(path)
                e.acceptProposedAction()
                return

    def closeEvent(self, e):
        self.timer.stop()
        self.autosave_timer.stop()
        self._autosave()
        super().closeEvent(e)
