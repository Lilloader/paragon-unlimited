"""Paragon Unlimited: Sprite Workshop window (FE13 map sprites).

Two ways to start:
  - drop a sprite sheet you have (PNG or .ctpk.lz) on the big preview, or
  - build one: pick a character's head and a class body (heads and bodies come from the game's
    own sprites, see paragon/core/services/fe13_sprite_parts.py).
Then drag any head in the preview to line it up in that frame, pick how see-through it is, and
save it to the mod in the player (blue), enemy (red) and ally (green) colors.
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

from paragon.core.services import fe13_sprite_workshop as ws

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
        self.project = ws.WorkshopProject()
        self.project_path = None
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
        self.source_combo = QComboBox()
        self.source_combo.setToolTip("The character's game sprite the head is taken from (picked automatically).")
        bt.addRow("Head taken from", self.source_combo)
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
        tip = QLabel("Drag a head in the preview to move it in that frame. Right-click a frame to put its head back.")
        tip.setWordWrap(True)
        al.addWidget(tip)
        r = QHBoxLayout()
        self.reset_frame_button = QPushButton("Reset selected frame")
        self.reset_all_button = QPushButton("Reset all frames")
        r.addWidget(self.reset_frame_button)
        r.addWidget(self.reset_all_button)
        al.addLayout(r)
        r = QHBoxLayout()
        self.eraser_button = QPushButton("Eraser")
        self.eraser_button.setCheckable(True)
        self.eraser_button.setToolTip(
            "Clean up leftovers of the old head or body.\n"
            "Left-drag erases, right-drag puts the pixels back. Works on all three colors.\n"
            "The new head is never erased: it is always drawn on top. Turn the eraser off to drag heads again."
        )
        self.eraser_size = QComboBox()
        for n in (1, 2, 3):
            self.eraser_size.addItem(f"{n} px", n)
        self.eraser_size.setToolTip("Eraser size")
        self.erase_undo_button = QPushButton("Undo erase")
        self.erase_clear_button = QPushButton("Restore all erased")
        r.addWidget(self.eraser_button, 1)
        r.addWidget(QLabel("Size"))
        r.addWidget(self.eraser_size)
        al.addLayout(r)
        r = QHBoxLayout()
        r.addWidget(self.erase_undo_button)
        r.addWidget(self.erase_clear_button)
        al.addLayout(r)
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
        self.export_button = QPushButton("Save sprite")
        self.export_button.setToolTip(
            "Makes map/unit/<name>青/赤/緑.ctpk.lz (written when you save the project), adds the BMap\n"
            "icon entry and sets the chosen characters' sprite for the chosen classes."
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
        self.eraser_button.toggled.connect(self._eraser_toggled)
        self.eraser_size.currentIndexChanged.connect(lambda _i: self._eraser_toggled(self.eraser_button.isChecked()))
        self.erase_undo_button.clicked.connect(self._erase_undo)
        self.erase_clear_button.clicked.connect(self._erase_clear)
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
        self.name_edit.textChanged.connect(lambda t: setattr(self.project, "name", t.strip()))
        self.register_check.toggled.connect(lambda v: setattr(self.project, "register", v))

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
            self._fill_sources()
            self._select(self.source_combo, p.head_class)
            self._select(self.team_combo, p.team_color)
            self._select(self.ref_combo, p.reference)
            self._select(self.head_mode_combo, p.head_mode)
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
        p = self.project
        p.mode, p.sheet, p.sheet_sha256 = "sheet", path, ws.file_digest(path)
        p.head_frames = {}
        p.erased = []
        self._erase_undo_stack = []
        if not p.name:
            base = os.path.splitext(os.path.basename(path))[0]
            if base.endswith(".ctpk"):
                base = base[:-5]
            p.name = base.rstrip("青赤緑")[:20]
            self.name_edit.setText(p.name)
        self.sheet_label.setText(os.path.basename(path))
        self.tabs.setCurrentIndex(0)
        self._prepare()

    def _fill_sources(self):
        code = self.head_combo.currentData() or ""
        body = self.body_combo.currentData() or ""
        self.source_combo.blockSignals(True)
        self.source_combo.clear()
        for label, key in self.workshop.head_source_choices(code) if code else []:
            self.source_combo.addItem(label, key)
        if code and body:
            self._select(self.source_combo, self.workshop.best_head_source(code, body))
        self.source_combo.blockSignals(False)

    def _head_changed(self, *_):
        if self._loading:
            return
        self._fill_sources()

    def _build_from_parts(self):
        code, body, src = self.head_combo.currentData(), self.body_combo.currentData(), self.source_combo.currentData()
        if not code or not body or not src:
            QMessageBox.information(self, "Sprite Workshop", "Pick a head (character) and a body (class) first.")
            return
        self._read_common()
        p = self.project
        p.mode, p.head_char, p.body_class, p.head_class = "build", code, body, src
        p.head_frames = {}
        p.erased = []
        self._erase_undo_stack = []
        if not p.name:
            p.name = "Custom" + str(sum(ord(c) for c in code + body) % 10000)
            self.name_edit.setText(p.name)
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
            _s, self.mask, cut = self.workshop.compose_color(self.prep, "青", self.project.head_frames,
                                                             self.project.erased)
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
            parts.append(f"{len(self.project.erased)} pixel(s) erased")
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
            blue, self.mask, _cut = self.workshop.compose_color(self.prep, "青", self.project.head_frames,
                                                                self.project.erased)
            self.sheets["青"] = blue
        except Exception:
            return
        self._show()

    # ================================================================ clean-up eraser
    def _eraser_toggled(self, on):
        self.canvas.set_eraser(self.eraser_size.currentData() if on else 0)
        self.eraser_button.setText("Eraser (on)" if on else "Eraser")

    def _erase_at(self, x, y, restore):
        if self.prep is None or not self.sheets:
            return
        if self._erase_stroke is None:  # start of a stroke: remember for Undo
            self._erase_stroke = [list(p) for p in self.project.erased]
            if self._playing and self.view_combo.currentData():
                self._toggle_play()
        b = self.sheets["青"]
        done = {tuple(p) for p in self.project.erased}
        before = len(done)
        for px in self.workshop_brush(x, y, (b.width, b.height)):
            if restore:
                done.discard(px)
            else:
                done.add(px)
        if len(done) == before and not restore:
            return
        self.project.erased = [list(p) for p in sorted(done)]
        try:  # live: the player color only (the others follow when the mouse is released)
            blue, self.mask, _cut = self.workshop.compose_color(self.prep, "青", self.project.head_frames,
                                                                self.project.erased)
            self.sheets["青"] = blue
        except Exception:
            return
        self._show()

    def workshop_brush(self, x, y, wh):
        from paragon.core.services.fe13_sprite_workshop import brush_pixels

        return brush_pixels(x, y, self.eraser_size.currentData() or 1, self.prep.cell, wh)

    def _erase_finished(self):
        if self._erase_stroke is not None:
            if self._erase_stroke != self.project.erased:
                self._erase_undo_stack.append(self._erase_stroke)
                del self._erase_undo_stack[:-50]
            self._erase_stroke = None
            self._recompose()

    def _erase_undo(self):
        if self._erase_undo_stack:
            self.project.erased = self._erase_undo_stack.pop()
            self._recompose()

    def _erase_clear(self):
        if self.project.erased:
            self._erase_undo_stack.append([list(p) for p in self.project.erased])
            self.project.erased = []
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

    def _remove_assignment(self):
        row = self.assign_list.currentRow()
        if 0 <= row < len(self.project.assign):
            del self.project.assign[row]
            self.assign_list.takeItem(row)

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
        try:
            lines = self.workshop.export(self.project, self._roots()[0])
        except Exception as e:
            logging.exception("Sprite Workshop export failed.")
            QMessageBox.warning(self, "Sprite Workshop", f"Could not save the sprite: {e}")
            return
        self.report.setPlainText("Saved (written to the mod when you save the project):\n" + "\n".join("  " + l for l in lines))

    def _validate(self):
        self._read_common()
        results = self.workshop.validate(self.project, self._roots())
        lines = [("OK: " if s == "ok" else s.upper() + ": ") + m for s, m in results] + self._mod_folder_check()
        self.report.setPlainText("\n".join(lines))
        return results

    def _mod_folder_check(self):
        """Info: are the files in the Azahar mod folder yet?"""
        try:
            from paragon.core.services import pu_azahar, pu_file_case

            root = pu_azahar.detect_mod_root()
            if not root or not self.project.name:
                return []
            romfs = os.path.join(root, pu_azahar.BASE_TITLE, "romfs")
            pu_file_case.clear_cache()
            missing = [
                c for c, _e, _l in ws.COLORS
                if pu_file_case.find(romfs, f"{ws.UNIT_DIR}/{self.project.name}{c}.ctpk.lz")[0] != "exact"
            ]
            if missing:
                return ["INFO: not in the Azahar mod folder yet (save, then Copy to Azahar)."]
            return ["INFO: all three files are in the Azahar mod folder."]
        except Exception:
            return []

    # ================================================================ project files
    def _new(self):
        self.project = ws.WorkshopProject()
        self.project_path = None
        self._erase_undo_stack = []
        self._load_project(self.project)

    def _open(self, path=None):
        if not path:
            path, _ = QFileDialog.getOpenFileName(self, "Open Sprite Workshop project", "", PROJECT_FILTER)
        if not path:
            return
        try:
            self.project = ws.WorkshopProject.open(path)
        except Exception as e:
            QMessageBox.warning(self, "Sprite Workshop", f"Could not open: {e}")
            return
        self.project_path = path
        self._erase_undo_stack = []
        self._load_project(self.project)

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
        super().closeEvent(e)
