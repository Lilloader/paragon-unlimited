"""Paragon Unlimited: FE13 FaceData "Game preview".

Shows a portrait where the game draws it (layouts in Data/FE13/PU_PortraitLayouts.yml) and lets
you drag it. Dragging does not move anything on screen in the game - Awakening has no position
setting for portraits - so the drag is turned into a shift of the artwork inside the texture.
The shift is queued and written to the portrait .arc when the project is saved
(see core/services/fe13_portrait_shift.py). For FC entries the "menu crop" rectangle edits the
Portrait Menu Position fields directly.

v1.0: images can be imported (button or drag and drop of PNG files), expressions added or
removed, and new portrait files created. Everything is built into the .arc on save.
"""
import json
import logging
import os
from typing import Dict, Optional

import yaml
from PIL import Image
from PySide6 import QtCore
from PySide6.QtCore import Qt, QRectF, QPointF, QEvent
from PySide6.QtGui import QPixmap, QColor, QPen, QBrush, QPainterPath, QTransform
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QComboBox,
    QLabel,
    QPushButton,
    QCheckBox,
    QGraphicsScene,
    QGraphicsView,
    QGraphicsPixmapItem,
    QGraphicsRectItem,
    QGraphicsPathItem,
    QGraphicsItem,
    QFileDialog,
    QMessageBox,
    QMenu,
    QDialog,
    QFormLayout,
    QDialogButtonBox,
    QLineEdit,
)

from paragon.core.services.fe13_portrait_shift import (
    PortraitEdits,
    shift_rgba,
    fit_image,
    ctpk_from_template,
    blank_ctpk,
    new_ctpk,
    CtpkTexture,
    BASIC_EXPRESSIONS,
    EXTRA_PARTS,
    ENTRY_SUFFIX,
    read_original_arc,
    reset_to_original,
)
from paragon.ui.controllers.auto.abstract_auto_widget import AbstractAutoWidget

# Portrait Menu crop (unit info screen) used by every one of the game's own portraits.
DEFAULT_MENU_CROP = (69, 76)

LAYOUT_FILE = os.path.join("Data", "FE13", "PU_PortraitLayouts.yml")
EMOTIONS_FILE = os.path.join("Data", "FE13", "Emotions.json")
IMAGE_FILTER = "Images (*.png *.webp *.bmp *.jpg *.jpeg *.gif *.tga)"
IMAGE_EXT = (".png", ".webp", ".bmp", ".jpg", ".jpeg", ".gif", ".tga")
PART_LABELS = {"頬": "Blush", "汗": "Sweat", "髪": "Hair mask", "髪0": "Hair mask 0", "屍": "Defeated"}
NAME_ALIASES = {
    "normal": "通常", "standard": "通常", "neutral": "通常", "default": "通常",
    "smile": "笑", "happy": "笑", "laugh": "笑",
    "angry": "怒", "anger": "怒", "mad": "怒",
    "pain": "苦", "pained": "苦", "hurt": "苦", "suffering": "苦",
    "posed": "キメ", "determined": "キメ", "pose": "キメ", "serious": "キメ",
    "blush": "頬", "sweat": "汗", "dead": "屍", "defeated": "屍",
}


def load_emotion_names() -> Dict[str, str]:
    """Japanese expression name -> English label (from Data/FE13/Emotions.json)."""
    names = {}
    try:
        with open(EMOTIONS_FILE, "r", encoding="utf-8") as f:
            for en, jp in json.load(f).items():
                names.setdefault(jp, en)
    except Exception:
        logging.exception("Could not load emotion names.")
    names.update(PART_LABELS)
    return names


def expression_label(key: str, names: Dict[str, str]) -> str:
    en = names.get(key)
    if en is None and key.startswith("反") and key[1:] in names:
        en = names[key[1:]] + " (reversed)"
    return f"{key}  ({en})" if en else key


class _FitView(QGraphicsView):
    """Graphics view that can keep the screen fitted to the window while it is resized."""

    def __init__(self, scene):
        super().__init__(scene)
        self.fit_rect = None

    def refit(self):
        if self.fit_rect is not None:
            self.fitInView(self.fit_rect, Qt.KeepAspectRatio)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.refit()


class _AddExpressionDialog(QDialog):
    def __init__(self, parent, existing, names, current):
        super().__init__(parent)
        self.setWindowTitle("Add expression")
        self.name = QComboBox()
        self.name.setEditable(True)
        suggestions = [k for k in BASIC_EXPRESSIONS + list(dict.fromkeys(names)) if k not in existing and k not in EXTRA_PARTS]
        for k in suggestions:
            self.name.addItem(expression_label(k, names), k)
        self.name.setCurrentIndex(-1)
        self.name.setEditText("")
        self.name.lineEdit().setPlaceholderText("Pick one or type a new name (e.g. apron, 照れ)")
        self.source = QComboBox()
        self.source.addItem("Image file...", "file")
        if current:
            self.source.addItem(f"Copy of {current}", "copy")
        self.source.addItem("Blank (transparent, import an image later)", "blank")
        form = QFormLayout()
        form.addRow("Name", self.name)
        form.addRow("Start from", self.source)
        note = QLabel(
            "The name is what dialogue uses to show the expression, e.g. $E<name>|. "
            "Names starting with 反 are the reversed (other direction) set."
        )
        note.setWordWrap(True)
        form.addRow(note)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)
        self.setLayout(form)

    def chosen_name(self) -> str:
        text = self.name.currentText().strip()
        i = self.name.currentIndex()
        if i >= 0 and self.name.itemText(i) == text:
            return self.name.itemData(i)
        # "通常  (Standard)" typed/pasted: keep the part before the label.
        return text.split("  (")[0].strip()


class _NewFileDialog(QDialog):
    def __init__(self, parent, default_name, has_current):
        super().__init__(parent)
        self.setWindowTitle("New portrait file")
        self.file_name = QLineEdit(default_name)
        self.start = QComboBox()
        self.start.addItem("Blank images (import yours afterwards)", "blank")
        if has_current:
            self.start.addItem("Copies of the current images", "copy")
        form = QFormLayout()
        form.addRow("File (in face/)", self.file_name)
        form.addRow("Expressions", self.start)
        note = QLabel(
            "Creates the basic expressions " + ", ".join(BASIC_EXPRESSIONS) +
            " plus blush (頬), sweat (汗) and the hair masks, and points this FaceData entry to the "
            "new file. Add more expressions afterwards with \"Add expression\". "
            "The file is written when you save."
        )
        note.setWordWrap(True)
        form.addRow(note)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)
        self.setLayout(form)


def load_layouts():
    try:
        with open(LAYOUT_FILE, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)["screens"]
    except Exception:
        logging.exception("Could not load portrait layouts.")
        return []


class _DragItem(QGraphicsPixmapItem):
    """Movable portrait. Reports moves (in screen pixels) to the stage."""

    def __init__(self, stage, pixmap):
        super().__init__(pixmap)
        self.stage = stage
        self.setFlag(QGraphicsItem.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)
        self.setCursor(Qt.OpenHandCursor)
        self.origin = QPointF(0, 0)

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionChange:
            step = self.stage.step()
            dx = round((value.x() - self.origin.x()) / step) * step
            dy = round((value.y() - self.origin.y()) / step) * step
            return QPointF(self.origin.x() + dx, self.origin.y() + dy)
        if change == QGraphicsItem.ItemPositionHasChanged:
            self.stage.on_dragged(
                int(round(self.pos().x() - self.origin.x())),
                int(round(self.pos().y() - self.origin.y())),
            )
        return super().itemChange(change, value)


class _OverlayItem(QGraphicsPixmapItem):
    """Blush or sweat overlay, child of the portrait item; dragging edits its FaceData position."""

    def __init__(self, stage, kind, pixmap):
        super().__init__(pixmap)
        self.stage = stage
        self.kind = kind  # "blush" or "sweat"
        self.ready = False
        self.setFlag(QGraphicsItem.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)
        self.setCursor(Qt.SizeAllCursor)
        self.setToolTip("Blush - drag to move" if kind == "blush" else "Sweat - drag to move")

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionChange:
            return QPointF(round(value.x()), round(value.y()))
        if change == QGraphicsItem.ItemPositionHasChanged and self.ready:
            self.stage.on_overlay_moved(self, int(self.pos().x()), int(self.pos().y()))
        return super().itemChange(change, value)


class _CropItem(QGraphicsRectItem):
    def __init__(self, stage, rect):
        super().__init__(rect)
        self.stage = stage
        self.setPen(QPen(QColor("#ffd54a"), 1, Qt.DashLine))
        self.setBrush(QBrush(QColor(255, 213, 74, 40)))
        self.setFlag(QGraphicsItem.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)
        self.setCursor(Qt.SizeAllCursor)

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionChange:
            return QPointF(round(value.x()), round(value.y()))
        if change == QGraphicsItem.ItemPositionHasChanged:
            self.stage.on_crop_moved(int(self.pos().x()), int(self.pos().y()))
        return super().itemChange(change, value)


class FE13PortraitStage(AbstractAutoWidget, QWidget):
    def __init__(self, state):
        AbstractAutoWidget.__init__(self, state)
        QWidget.__init__(self)
        self.rid = None
        self.layouts = load_layouts()
        self.textures: Dict[str, object] = {}
        self.edits: PortraitEdits = self._edits_service()
        self.edits.listeners.append(self._after_save)
        self._building = False
        self._crop_mode = False
        self._crop0 = (0, 0)
        self._overlay_ctx = dict(mirror=False, width=0, shift=(0, 0))

        self.screen_box = QComboBox()
        self.slot_box = QComboBox()
        self.expression_box = QComboBox()
        self.zoom_box = QComboBox()
        for z in ("Fit", "1x", "2x", "3x", "4x"):
            self.zoom_box.addItem(z)
        self.zoom_box.setCurrentIndex(0)
        self.names = load_emotion_names()
        self.snap = QCheckBox("4 px steps (lossless)")
        self.snap.setChecked(True)
        self.snap.setToolTip(
            "Moves whole 4x4 texture blocks, so the image stays pixel-identical.\n"
            "Untick for 1 px steps: the textures are then re-encoded (very small quality loss)."
        )
        self.show_blush = QCheckBox("Blush")
        self.show_sweat = QCheckBox("Sweat")
        for cb in (self.show_blush, self.show_sweat):
            cb.setToolTip("Show it on the portrait. Drag it to change its position.")
        self.reset_button = QPushButton("Reset")
        self.status = QLabel()
        self.status.setWordWrap(True)
        self.accuracy = QLabel()
        self.accuracy.setWordWrap(True)

        self.scene = QGraphicsScene()
        self.view = _FitView(self.scene)
        self.view.setBackgroundBrush(QBrush(QColor("#202020")))
        self.view.setMinimumHeight(200)
        self.view.setAcceptDrops(True)
        self.view.viewport().setAcceptDrops(True)
        self.view.viewport().installEventFilter(self)
        self.view.setToolTip("Drag the portrait to move it. Drop PNG files here to import them.")

        self.import_button = QPushButton("Import image...")
        self.import_menu = QMenu(self)
        self.import_button.setMenu(self.import_menu)
        self.import_menu.aboutToShow.connect(self._fill_import_menu)
        self.export_button = QPushButton("Export PNG...")
        self.add_button = QPushButton("Add expression...")
        self.remove_button = QPushButton("Remove expression")
        self.new_file_button = QPushButton("New portrait file...")
        self.export_button.clicked.connect(self._on_export)
        self.add_button.clicked.connect(self._on_add_expression)
        self.remove_button.clicked.connect(self._on_remove_expression)
        self.new_file_button.clicked.connect(self._on_new_file)

        row1 = QHBoxLayout()
        row1.addWidget(QLabel("Screen"))
        row1.addWidget(self.screen_box, 2)
        row1.addWidget(QLabel("Side"))
        row1.addWidget(self.slot_box, 1)
        row2 = QHBoxLayout()
        row2.addWidget(QLabel("Expression"))
        row2.addWidget(self.expression_box, 2)
        row2.addWidget(QLabel("Zoom"))
        row2.addWidget(self.zoom_box)
        row2.addWidget(self.show_blush)
        row2.addWidget(self.show_sweat)
        row3 = QHBoxLayout()
        row3.addWidget(self.snap)
        row3.addWidget(self.reset_button)
        row3.addStretch(1)
        row4 = QHBoxLayout()
        for b in (self.import_button, self.export_button, self.add_button, self.remove_button, self.new_file_button):
            row4.addWidget(b)
        row4.addStretch(1)
        self.help_button = QPushButton("Help")
        self.help_button.setToolTip("How the preview, dragging and importing work (F1)")
        self.help_button.clicked.connect(self._on_help)
        row4.addWidget(self.help_button)
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(row1)
        layout.addLayout(row2)
        layout.addWidget(self.view, 1)
        layout.addLayout(row3)
        layout.addLayout(row4)
        layout.addWidget(self.status)
        layout.addWidget(self.accuracy)
        self.setLayout(layout)

        self.screen_box.currentIndexChanged.connect(self._on_screen_changed)
        self.slot_box.currentIndexChanged.connect(self._redraw)
        self.expression_box.currentIndexChanged.connect(self._redraw)
        self.zoom_box.currentIndexChanged.connect(self._apply_zoom)
        self.show_blush.toggled.connect(self._redraw)
        self.show_sweat.toggled.connect(self._redraw)
        self.snap.toggled.connect(self._on_snap)
        self.reset_button.clicked.connect(self._on_reset)
        self._apply_zoom()

    # ------------------------------------------------------------------ helpers
    def _edits_service(self) -> PortraitEdits:
        portraits = self.gs.portraits
        if hasattr(portraits, "pu_portrait_edits"):
            return portraits.pu_portrait_edits()
        edits = getattr(portraits, "pu_edits", None)
        if edits is None:
            edits = PortraitEdits(self.data)
            portraits.pu_edits = edits
        return edits

    def step(self):
        if getattr(self, "_crop_mode", False):
            return 1
        return 4 if self.snap.isChecked() else 1

    def _mode(self) -> Optional[str]:
        fsid = self.data.string(self.rid, "fsid") if self.rid else None
        if not fsid:
            return None
        if fsid.startswith("FSID_BU_"):
            return "BU"
        if fsid.startswith("FSID_FC_"):
            return "FC"
        return None

    def _arc_path(self) -> Optional[str]:
        f = self.data.string(self.rid, "portrait_file") if self.rid else None
        return f"face/{f}" if f else None

    def _screen(self):
        i = self.screen_box.currentData()
        return self.layouts[i] if i is not None and 0 <= i < len(self.layouts) else None

    def _slot(self):
        s = self._screen()
        i = self.slot_box.currentIndex()
        if not s or i < 0 or i >= len(s.get("slots", [])):
            return None
        return s["slots"][i]

    def _which(self):
        key = self.expression_box.currentData()
        return "reversed" if key and key.startswith("反") else "normal"

    # ------------------------------------------------------------------ target
    def set_target(self, rid):
        self.rid = rid
        self._building = True
        try:
            self.textures = {}
            mode = self._mode()
            self.screen_box.clear()
            self.expression_box.clear()
            if rid and mode:
                for i, s in enumerate(self.layouts):
                    if s.get("mode") == mode:
                        self.screen_box.addItem(s["name"], i)
                fsid = self.data.string(rid, "fsid")
                try:
                    self.textures = self.gs.portraits.from_fsid(fsid) or {}
                except Exception:
                    logging.exception("Could not load portrait textures.")
                    self.textures = {}
                for key in self.textures:
                    if key in ("頬", "汗"):
                        continue
                    self.expression_box.addItem(expression_label(key, self.names), key)
            self.setEnabled(bool(rid and mode))
            has = bool(self.textures)
            for w in (self.view, self.export_button, self.remove_button, self.add_button,
                      self.snap, self.reset_button, self.show_blush, self.show_sweat, self.import_button):
                w.setEnabled(has)
        finally:
            self._building = False
        self._on_screen_changed()
        if rid and mode and not self.textures:
            self.status.setText(
                f"No portrait file found for this entry ({self._arc_path() or 'no file set'}). "
                "Use \"New portrait file...\" to make one."
            )

    def _after_save(self):
        # Textures on disk changed and the pending moves are gone: reload what we show.
        self._reload()

    def _reload(self, select_key=None):
        if not self.rid:
            return
        screen, slot = self.screen_box.currentIndex(), self.slot_box.currentIndex()
        key = select_key or self.expression_box.currentData()
        self.set_target(self.rid)
        if 0 <= screen < self.screen_box.count():
            self.screen_box.setCurrentIndex(screen)
        if 0 <= slot < self.slot_box.count():
            self.slot_box.setCurrentIndex(slot)
        i = self.expression_box.findData(key) if key else -1
        if i >= 0:
            self.expression_box.setCurrentIndex(i)

    def _on_screen_changed(self):
        if self._building:
            return
        self._building = True
        self.slot_box.clear()
        s = self._screen()
        if s:
            for slot in s.get("slots", []):
                self.slot_box.addItem(slot["name"])
            self.accuracy.setText(
                "Positions measured from in-game screenshots (1:1). The game also tints/darkens "
                "portraits depending on the scene; that is not shown here."
                if s.get("measured")
                else "Positions assumed, not measured yet."
            )
        self._building = False
        self._redraw()

    def _apply_zoom(self):
        z = self.zoom_box.currentIndex()
        if z == 0:
            s = self._screen() if hasattr(self, "layouts") else None
            w, h = (s.get("size", [400, 240]) if s else [400, 240])
            self.view.fit_rect = QRectF(-8, -8, w + 16, h + 16)
            self.view.refit()
        else:
            self.view.fit_rect = None
            self.view.setTransform(QTransform.fromScale(z, z))

    # ------------------------------------------------------------------ drawing
    def _texture_pixmap(self, key, dx=0, dy=0, mirror=False, with_overlays=False) -> Optional[QPixmap]:
        tex = self.textures.get(key)
        if tex is None:
            return None
        img = tex.to_pillow_image()
        if with_overlays and self.rid:
            for name, fx, fy in (("頬", "blush_position_x", "blush_position_y"), ("汗", "sweat_position_x", "sweat_position_y")):
                ov = self.textures.get(name)
                if ov is not None:
                    o = ov.to_pillow_image()
                    img.paste(o, (self.data.int(self.rid, fx) or 0, self.data.int(self.rid, fy) or 0), o)
        if dx or dy:
            img = Image.frombytes("RGBA", img.size, shift_rgba(img.tobytes(), img.width, img.height, dx, dy))
        if mirror:
            img = img.transpose(Image.FLIP_LEFT_RIGHT)
        return img.toqpixmap()

    def _redraw(self):
        if self._building:
            return
        self.scene.clear()
        s, slot, key = self._screen(), self._slot(), self.expression_box.currentData()
        path = self._arc_path()
        if not (s and slot and key and path):
            self.status.setText("")
            return
        w, h = s.get("size", [400, 240])
        screen_rect = QRectF(0, 0, w, h)
        if s.get("background_image") and os.path.exists(s["background_image"]):
            bg = self.scene.addPixmap(QPixmap(s["background_image"]))
            bg.setZValue(-10)
        else:
            self.scene.addRect(screen_rect, QPen(Qt.NoPen), QBrush(QColor(s.get("background_color", "#3a3f4b")))).setZValue(-10)

        which = self._which()
        dx, dy = self.edits.get(path, which)
        mirror = bool(slot.get("mirror"))
        sx, sy = slot["pos"]
        tex = self.textures[key]
        self._crop_mode = bool(s.get("crop_anchor")) and self.rid is not None

        if self._crop_mode:
            # Unit info panel: the game places the FC so that the corner of the Portrait Menu
            # crop lands on a fixed point; dragging here edits the crop, not the texture.
            # v1.5: the whole FC is shown (dimmed outside the window) so it can be seen and
            # dragged even when the crop is far off, and a crop size of 0 uses the game's 69x76.
            ax, ay = s["crop_anchor"]
            cx = self.data.int(self.rid, "portrait_menu_position_x") or 0
            cy = self.data.int(self.rid, "portrait_menu_position_y") or 0
            cw = self.data.int(self.rid, "portrait_menu_size_x") or 0
            ch = self.data.int(self.rid, "portrait_menu_size_y") or 0
            self._crop_missing = not (cw and ch)
            if self._crop_missing:
                cw, ch = DEFAULT_MENU_CROP
            self._crop0 = (cx, cy)
            px = ax - ((tex.width - cx - cw) if mirror else cx)
            py = ay - cy
            wx, wy, ww, wh = s.get("window", [0, 0, w, h])
            pix = self._texture_pixmap(key, dx, dy, mirror=mirror)
            item = _DragItem(self, pix)
            item.origin = QPointF(px, py)
            item.setFlag(QGraphicsItem.ItemSendsGeometryChanges, False)
            item.setPos(px, py)
            item.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)
            item.setZValue(1)
            self.scene.addItem(item)
            # Dim the part of the picture the game does not show; clicks go through to the picture.
            far = QPainterPath()
            far.addRect(QRectF(-600, -600, w + 1200, h + 1200))
            win = QPainterPath()
            win.addRect(QRectF(wx, wy, ww, wh))
            dim = QGraphicsPathItem(far.subtracted(win))
            dim.setBrush(QBrush(QColor(0, 0, 0, 150)))
            dim.setPen(QPen(Qt.NoPen))
            dim.setAcceptedMouseButtons(Qt.NoButton)
            dim.setZValue(2)
            self.scene.addItem(dim)
            frame = QGraphicsRectItem(QRectF(wx, wy, ww, wh))
            frame.setPen(QPen(QColor("#6b3f1f"), 2))
            frame.setAcceptedMouseButtons(Qt.NoButton)
            frame.setZValue(3)
            self.scene.addItem(frame)
        else:
            # Texture frame (the art cannot leave it).
            frame = QGraphicsRectItem(QRectF(sx, sy, tex.width, tex.height))
            frame.setPen(QPen(QColor("#7fb3ff"), 0, Qt.DashLine))
            frame.setFlag(QGraphicsItem.ItemClipsChildrenToShape, True)
            frame.setZValue(0)
            self.scene.addItem(frame)

            # The draggable art: unshifted texture placed at its shifted screen position, clipped
            # to the texture frame - exactly what the saved texture will look like.
            pix = self._texture_pixmap(key, mirror=mirror)
            item = _DragItem(self, pix)
            item.setParentItem(frame)
            item.origin = QPointF(sx, sy)
            item.setFlag(QGraphicsItem.ItemSendsGeometryChanges, False)
            item.setPos(sx + (-dx if mirror else dx), sy + dy)
            item.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)

        # Blush / sweat overlays ride on the portrait item (texture coordinates).
        # In the normal view the item shows the unshifted texture, while the FaceData positions
        # are already in shifted coordinates, so subtract the pending shift there.
        self._overlay_ctx = dict(mirror=mirror, width=tex.width, shift=(0, 0) if self._crop_mode else (dx, dy))
        for kind, cb, tex_key in (("blush", self.show_blush, "頬"), ("sweat", self.show_sweat, "汗")):
            ov = self.textures.get(tex_key)
            if not cb.isChecked() or ov is None or not self.rid:
                continue
            fx = self.data.int(self.rid, f"{kind}_position_x") or 0
            fy = self.data.int(self.rid, f"{kind}_position_y") or 0
            img = ov.to_pillow_image()
            if mirror:
                img = img.transpose(Image.FLIP_LEFT_RIGHT)
            o = _OverlayItem(self, kind, img.toqpixmap())
            o.ow = ov.width
            o.setParentItem(item)
            o.setPos(*self._overlay_local(fx, fy, ov.width))
            o.ready = True

        if slot.get("box"):
            bx, by, bw, bh = slot["box"]
            box = self.scene.addRect(QRectF(bx, by, bw, bh), QPen(QColor("#6b4a2a"), 1), QBrush(QColor(243, 226, 190, 215)))
            box.setZValue(5)
            box.setToolTip("Speech box (covers the portrait in game; position approximate)")

        for d in s.get("decorations", []):
            if os.path.exists(d["image"]):
                deco = self.scene.addPixmap(QPixmap(d["image"]))
                deco.setPos(*d["pos"])
                deco.setZValue(5)

        # Dim everything outside the real screen.
        outside = QPainterPath()
        outside.addRect(QRectF(-300, -300, w + 600, h + 600))
        inner = QPainterPath()
        inner.addRect(screen_rect)
        mask = QGraphicsPathItem(outside.subtracted(inner))
        mask.setBrush(QBrush(QColor(0, 0, 0, 170)))
        mask.setPen(QPen(Qt.NoPen))
        mask.setZValue(10)
        mask.setAcceptedMouseButtons(Qt.NoButton)
        if self._crop_mode:
            mask.setBrush(QBrush(QColor(0, 0, 0, 60)))  # the picture outside is already dimmed
        self.scene.addItem(mask)
        border = self.scene.addRect(screen_rect, QPen(QColor("#ffffff"), 0))
        border.setZValue(11)

        if s.get("show_menu_crop") and self.rid:
            cx = self.data.int(self.rid, "portrait_menu_position_x") or 0
            cy = self.data.int(self.rid, "portrait_menu_position_y") or 0
            cw = self.data.int(self.rid, "portrait_menu_size_x") or 0
            ch = self.data.int(self.rid, "portrait_menu_size_y") or 0
            if cw and ch:
                crop = _CropItem(self, QRectF(0, 0, cw, ch))
                crop.setFlag(QGraphicsItem.ItemSendsGeometryChanges, False)
                crop.setPos(sx + cx, sy + cy)
                crop.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)
                crop.origin = QPointF(sx, sy)
                crop.setZValue(12)
                self.scene.addItem(crop)

        if self._crop_mode:
            r = item.sceneBoundingRect().united(screen_rect)
            self.scene.setSceneRect(r.adjusted(-20, -20, 20, 20))
        else:
            self.scene.setSceneRect(QRectF(-40, -40, w + 80, h + 80))
        self._apply_zoom()
        self._update_status()

    def _update_status(self):
        path = self._arc_path()
        if not path:
            return
        if getattr(self, "_crop_mode", False):
            text = (
                "Unit info: drag the picture to choose the part the game shows (the box). "
                "The dimmed part is not shown in game; to move the artwork itself use the "
                "\"FC texture + menu crop box\" screen."
            )
            if getattr(self, "_crop_missing", False):
                text = (
                    "This face has no Portrait Menu size yet (0 x 0), so the game shows nothing here. "
                    "Drag the picture once to set the game's usual 69 x 76 box. " + text
                )
            self.status.setText(text)
            return
        if self.edits.has_image_edits(path):
            new = path in self.edits.new_arcs
            n = len(self.edits.images.get(path, {}))
            self.status.setText(
                (f"New portrait file {path}" if new else f"{n} image change(s) in {path}")
                + " - built into the .arc when you save."
                + self._shift_text(path)
            )
            return
        shift = self._shift_text(path)
        if shift:
            self.status.setText(shift.strip())
            return
        self.status.setText(
            "Drag the portrait to move the artwork, or drop PNG files here to import them. "
            "Normal and 反 (reversed) expressions move separately; blush and sweat follow the normal ones."
        )

    def _shift_text(self, path) -> str:
        n = self.edits.get(path, "normal")
        r = self.edits.get(path, "reversed")
        parts = []
        if n != (0, 0):
            parts.append(f"normal images {n[0]:+d}, {n[1]:+d}")
        if r != (0, 0):
            parts.append(f"反 (reversed) images {r[0]:+d}, {r[1]:+d}")
        return (" Pending move: " + "; ".join(parts) + f". Written to {path} when you save.") if parts else ""

    # ------------------------------------------------------------------ edits
    def on_dragged(self, screen_dx, screen_dy):
        slot, path = self._slot(), self._arc_path()
        if not slot or not path:
            return
        if getattr(self, "_crop_mode", False):
            tex = self.textures.get(self.expression_box.currentData())
            cw = self.data.int(self.rid, "portrait_menu_size_x") or 0
            ch = self.data.int(self.rid, "portrait_menu_size_y") or 0
            if not (cw and ch):  # v1.5: every game portrait uses 69 x 76
                cw, ch = DEFAULT_MENU_CROP
                self.data.set_int(self.rid, "portrait_menu_size_x", cw)
                self.data.set_int(self.rid, "portrait_menu_size_y", ch)
                self._crop_missing = False
            cx0, cy0 = self._crop0
            cx = cx0 + (screen_dx if slot.get("mirror") else -screen_dx)
            cy = cy0 - screen_dy
            if tex is not None:
                cx = max(0, min(tex.width - cw, cx))
                cy = max(0, min(tex.height - ch, cy))
            self.data.set_int(self.rid, "portrait_menu_position_x", cx)
            self.data.set_int(self.rid, "portrait_menu_position_y", cy)
            self.status.setText(f"Portrait Menu Position: {cx}, {cy} (saved with FaceData).")
            return
        dx = -screen_dx if slot.get("mirror") else screen_dx
        dy = screen_dy
        which = self._which()
        old = self.edits.get(path, which)
        if (dx, dy) == old:
            return
        self.edits.set(path, which, dx, dy)
        if which == "normal":
            self._move_overlay_fields(dx - old[0], dy - old[1])
        self._update_status()

    def _move_overlay_fields(self, ddx, ddy):
        if not self.rid or (ddx == 0 and ddy == 0):
            return
        for fx, fy in (("blush_position_x", "blush_position_y"), ("sweat_position_x", "sweat_position_y")):
            x = self.data.int(self.rid, fx)
            y = self.data.int(self.rid, fy)
            if x is None or y is None:
                continue
            self.data.set_int(self.rid, fx, max(0, min(0xFFFF, x + ddx)))
            self.data.set_int(self.rid, fy, max(0, min(0xFFFF, y + ddy)))

    def _overlay_local(self, fx, fy, ow):
        c = self._overlay_ctx
        lx, ly = fx - c["shift"][0], fy - c["shift"][1]
        if c["mirror"]:
            lx = c["width"] - lx - ow
        return lx, ly

    def on_overlay_moved(self, item, lx, ly):
        if not self.rid:
            return
        c = self._overlay_ctx
        fx = (c["width"] - lx - item.ow) if c["mirror"] else lx
        fx += c["shift"][0]
        fy = ly + c["shift"][1]
        fx, fy = max(0, min(0xFFFF, fx)), max(0, min(0xFFFF, fy))
        self.data.set_int(self.rid, f"{item.kind}_position_x", fx)
        self.data.set_int(self.rid, f"{item.kind}_position_y", fy)
        name = "Blush" if item.kind == "blush" else "Sweat"
        self.status.setText(f"{name} position: {fx}, {fy} (saved with FaceData).")

    def on_crop_moved(self, x, y):
        slot = self._slot()
        if not slot or not self.rid:
            return
        sx, sy = slot["pos"]
        self.data.set_int(self.rid, "portrait_menu_position_x", max(0, x - sx))
        self.data.set_int(self.rid, "portrait_menu_position_y", max(0, y - sy))

    def _on_help(self):
        from paragon.ui import pu_help

        win = self.window()
        if win is not None and not getattr(win, "_pu_help_topic", None):
            win._pu_help_topic = "facedata"
        pu_help.show_help(self)

    def _on_snap(self):
        self.edits.lossless = self.snap.isChecked()

    def _rom_root(self) -> Optional[str]:
        try:
            return self.gs.project.rom_path
        except Exception:
            return None

    def _on_reset(self):
        """Back to where the game has it: drops unsaved moves and, when the saved pictures are
        moved copies of the game's own, puts the game's pictures back (written on save)."""
        path = self._arc_path()
        if not path:
            return
        which = self._which()
        pending = self.edits.get(path, which)
        from PySide6.QtWidgets import QApplication

        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            current = self._raw_arc()
            original = read_original_arc(self._rom_root(), path)
            result = reset_to_original(self.edits, path, which, current, original)
        except Exception:
            logging.exception("Reset to the original position failed.")
            self.edits.set(path, which, 0, 0)
            result = None
        finally:
            QApplication.restoreOverrideCursor()
        total = pending
        if result is not None and result.restored:
            total = (pending[0] + result.saved_shift[0], pending[1] + result.saved_shift[1])
        if which == "normal":
            self._move_overlay_fields(-total[0], -total[1])
        logging.info(f"Portrait reset {path} ({which}): unsaved move {pending}, result {result}")
        if result is not None and result.restored:
            if result.keys:
                self._reload()
                self.status.setText(
                    f"Back to the game's original position ({len(result.keys)} picture(s) restored; "
                    "written when you save)."
                )
            else:
                self._redraw()
                self.status.setText("Already at the game's original position.")
        else:
            self._redraw()
            why = result.reason if result is not None else "see paragon.log"
            self.status.setText(
                f"Unsaved moves undone. Could not go back to the game's original position: {why}"
            )

    # ------------------------------------------------------------------ images (v1.0)
    def _portrait_file(self) -> Optional[str]:
        return self.data.string(self.rid, "portrait_file") if self.rid else None

    def _raw_arc(self) -> Dict[str, bytes]:
        """name -> LZ13 CTPK of the arc this entry uses, including unsaved imports."""
        f = self._portrait_file()
        if not f:
            return {}
        try:
            return self.gs.portraits._read_portrait_arc(f) or {}
        except Exception:
            return {}

    def _raw_ctpk(self, key, arc=None) -> Optional[bytes]:
        from paragon import paragon as pgn

        arc = self._raw_arc() if arc is None else arc
        blob = arc.get(key + ENTRY_SUFFIX)
        return bytes(pgn.decompress_lz13(bytes(blob))) if blob else None

    def _template_for(self, key, arc=None) -> Optional[bytes]:
        """CTPK to copy size/format from: the entry itself, else the normal expression."""
        arc = self._raw_arc() if arc is None else arc
        t = self._raw_ctpk(key, arc)
        if t is not None:
            return t
        if key in EXTRA_PARTS:
            return None
        for k in ["通常"] + [n[: -len(ENTRY_SUFFIX)] for n in arc if n.endswith(ENTRY_SUFFIX)]:
            if k in EXTRA_PARTS:
                continue
            t = self._raw_ctpk(k, arc)
            if t is not None:
                return t
        return None

    def import_image(self, image_path: str, key: str, add_if_missing=True) -> str:
        """Encode an image into the expression/overlay `key`. Returns a status line."""
        path = self._arc_path()
        if not path:
            raise ValueError("This FaceData entry has no portrait file.")
        arc = self._raw_arc()
        exists = (key + ENTRY_SUFFIX) in arc
        if not exists and not add_if_missing:
            raise ValueError(f"{key} is not in this portrait file.")
        template = self._template_for(key, arc)
        if template is None:
            raise ValueError(f"No texture to use as a template for {key}.")
        t = CtpkTexture.parse(template)
        img = Image.open(image_path)
        size = img.size
        rgba = fit_image(img, t.width, t.height, align_bottom=key not in ("頬", "汗"))
        self.edits.set_image(path, key, ctpk_from_template(template, rgba))
        note = "" if size == (t.width, t.height) else f", scaled from {size[0]}x{size[1]}"
        return f"{'Replaced' if exists else 'Added'} {key} ({t.width}x{t.height}{note})."

    def _check_name(self, name: str) -> Optional[str]:
        if not name:
            return "Please enter a name."
        if any(c in name for c in '/\\:*?"<>|') or name != name.strip():
            return "The name cannot contain / \\ : * ? \" < > | or start/end with spaces."
        try:
            name.encode("shift_jis")
        except UnicodeEncodeError:
            return "The game stores names in Shift-JIS; this name has characters it cannot store."
        return None

    def _fill_import_menu(self):
        self.import_menu.clear()
        key = self.expression_box.currentData()
        if key:
            self.import_menu.addAction(f"Into the current expression ({key})...", lambda: self._on_import(key))
        arc = self._raw_arc()
        for k in ("頬", "汗"):
            if (k + ENTRY_SUFFIX) in arc:
                self.import_menu.addAction(f"{PART_LABELS[k]} overlay ({k})...", lambda k=k: self._on_import(k))
        self.import_menu.addSeparator()
        self.import_menu.addAction("Several files (matched by name)...", self._on_import_many)

    def _on_import(self, key):
        fn, _ = QFileDialog.getOpenFileName(self, f"Import image for {key}", "", IMAGE_FILTER)
        if fn:
            self._import_files([fn], default_key=key)

    def _on_import_many(self):
        fns, _ = QFileDialog.getOpenFileNames(self, "Import images", "", IMAGE_FILTER)
        if fns:
            self._import_files(fns, default_key=None)

    def _key_for_file(self, fn: str, keys) -> Optional[str]:
        stem = os.path.splitext(os.path.basename(fn))[0].strip()
        if stem in keys:
            return stem
        low = stem.lower()
        # "Chrom_bu_笑" or "gisselle-smile" -> last part
        for part in [low] + [p for p in low.replace("-", "_").replace(" ", "_").split("_")[::-1] if p]:
            if part in keys:
                return part
            if part in NAME_ALIASES and NAME_ALIASES[part] in keys:
                return NAME_ALIASES[part]
            for jp, en in self.names.items():
                if en.lower() == part and jp in keys:
                    return jp
        return None

    def _import_files(self, files, default_key=None):
        path = self._arc_path()
        if not path:
            return
        arc = self._raw_arc()
        keys = [n[: -len(ENTRY_SUFFIX)] for n in arc if n.endswith(ENTRY_SUFFIX)]
        lines, unmatched = [], []
        last = None
        for fn in files:
            key = default_key if len(files) == 1 and default_key else self._key_for_file(fn, keys)
            if key is None and len(files) == 1:
                key = self.expression_box.currentData()
            if key is None:
                unmatched.append(fn)
                continue
            try:
                lines.append(self.import_image(fn, key))
                last = key if key not in ("頬", "汗") else last
            except Exception as e:
                logging.exception(f"Import of {fn} failed.")
                lines.append(f"{os.path.basename(fn)}: {e}")
        if unmatched:
            names = "\n".join(os.path.basename(f) for f in unmatched)
            answer = QMessageBox.question(
                self,
                "Paragon Unlimited - Import",
                "These files do not match an expression of this portrait:\n\n"
                f"{names}\n\nAdd them as new expressions named after the files?",
            )
            if answer == QMessageBox.Yes:
                for fn in unmatched:
                    key = os.path.splitext(os.path.basename(fn))[0].strip()
                    err = self._check_name(key)
                    if err:
                        lines.append(f"{os.path.basename(fn)}: {err}")
                        continue
                    try:
                        lines.append(self.import_image(fn, key))
                        last = key
                    except Exception as e:
                        lines.append(f"{os.path.basename(fn)}: {e}")
        self._reload(select_key=last)
        if lines:
            self.status.setText(" ".join(lines) + f" Built into {path} when you save.")

    def eventFilter(self, obj, event):
        if obj is self.view.viewport():
            t = event.type()
            if t in (QEvent.DragEnter, QEvent.DragMove):
                if self._image_urls(event.mimeData()):
                    event.acceptProposedAction()
                    return True
            elif t == QEvent.Drop:
                files = self._image_urls(event.mimeData())
                if files:
                    event.acceptProposedAction()
                    self._import_files(files, default_key=self.expression_box.currentData() if len(files) == 1 else None)
                    return True
        return super().eventFilter(obj, event)

    @staticmethod
    def _image_urls(mime):
        if not mime or not mime.hasUrls():
            return []
        return [u.toLocalFile() for u in mime.urls() if u.isLocalFile() and u.toLocalFile().lower().endswith(IMAGE_EXT)]

    def _on_export(self):
        key = self.expression_box.currentData()
        ctpk = self._raw_ctpk(key) if key else None
        if ctpk is None:
            return
        t = CtpkTexture.parse(ctpk)
        default = f"{os.path.splitext(self._portrait_file() or 'portrait')[0]}_{key}.png"
        fn, _ = QFileDialog.getSaveFileName(self, "Export PNG", default, "PNG (*.png)")
        if fn:
            Image.frombytes("RGBA", (t.width, t.height), t.rgba()).save(fn)
            self.status.setText(f"Saved {fn} ({t.width}x{t.height}, the raw texture without hair color).")

    def _on_add_expression(self):
        path = self._arc_path()
        if not path:
            return
        arc = self._raw_arc()
        existing = [n[: -len(ENTRY_SUFFIX)] for n in arc if n.endswith(ENTRY_SUFFIX)]
        current = self.expression_box.currentData()
        dlg = _AddExpressionDialog(self, existing, self.names, current)
        if not dlg.exec():
            return
        name = dlg.chosen_name()
        err = self._check_name(name)
        if not err and name in existing:
            err = f"{name} already exists. Use Import image to replace it."
        if err:
            QMessageBox.warning(self, "Paragon Unlimited", err)
            return
        source = dlg.source.currentData()
        try:
            if source == "file":
                fn, _ = QFileDialog.getOpenFileName(self, f"Image for {name}", "", IMAGE_FILTER)
                if not fn:
                    return
                line = self.import_image(fn, name)
            else:
                template = self._template_for(current or "通常", arc)
                if template is None:
                    raise ValueError("No texture to copy the size from.")
                if source == "copy" and current:
                    self.edits.set_image(path, name, self._raw_ctpk(current, arc))
                    line = f"Added {name} as a copy of {current}."
                else:
                    self.edits.set_image(path, name, blank_ctpk(template))
                    line = f"Added {name} (blank - import an image into it)."
        except Exception as e:
            logging.exception("Add expression failed.")
            QMessageBox.warning(self, "Paragon Unlimited", str(e))
            return
        self._reload(select_key=name)
        self.status.setText(line + f" Built into {path} when you save.")

    def _on_remove_expression(self):
        path, key = self._arc_path(), self.expression_box.currentData()
        if not path or not key:
            return
        if key == "通常":
            QMessageBox.warning(self, "Paragon Unlimited", "通常 (Standard) is required by the game and cannot be removed.")
            return
        answer = QMessageBox.question(
            self,
            "Paragon Unlimited",
            f"Remove the expression {key} from {path}?\n\nDialogue that uses it will show nothing. "
            "The file is only changed when you save (a backup of it is kept in Backups/).",
        )
        if answer != QMessageBox.Yes:
            return
        self.edits.remove_image(path, key)
        self._reload(select_key="通常")
        self.status.setText(f"Removed {key}. Written to {path} when you save.")

    def _default_new_name(self) -> str:
        fsid = self.data.string(self.rid, "fsid") or ""
        mode = (self._mode() or "BU").lower()
        parts = fsid.split("_")
        # FSID_BU_<name>_通常 -> <name>_bu_通常.arc
        name = "_".join(parts[2:-1]) if len(parts) >= 4 else (parts[-1] if parts else "New")
        tail = parts[-1] if len(parts) >= 4 else "通常"
        return f"{name}_{mode}_{tail}.arc"

    def _on_new_file(self):
        if not self.rid:
            return
        arc = self._raw_arc()
        dlg = _NewFileDialog(self, self._default_new_name(), bool(arc))
        if not dlg.exec():
            return
        name = dlg.file_name.text().strip()
        if not name.lower().endswith(".arc"):
            name += ".arc"
        err = self._check_name(name[:-4])
        if err:
            QMessageBox.warning(self, "Paragon Unlimited", err)
            return
        full = f"face/{name}"
        exists = False
        try:
            exists = bool(self.data.file_exists(full, False))
        except Exception:
            pass
        if exists or full in self.edits.new_arcs:
            answer = QMessageBox.question(
                self,
                "Paragon Unlimited",
                f"{full} already exists. Replace it with a new file when you save?\n"
                "(The current file is backed up to Backups/ first.)",
            )
            if answer != QMessageBox.Yes:
                return
        parts = self._new_file_parts(arc, dlg.start.currentData() == "copy")
        self.edits.create_arc(full, parts)
        self.data.set_string(self.rid, "portrait_file", name)
        self._reload(select_key="通常")
        self.status.setText(
            f"New portrait file {full} with " + ", ".join(parts) +
            ". Portrait File now points to it. Import your images (drop PNGs here), then save."
        )

    def _new_file_parts(self, arc, copy_current) -> Optional[Dict[str, bytes]]:
        template_arc = arc
        if not arc or self._template_for("通常", arc) is None:
            template_arc = self._fallback_arc()
            copy_current = False
        template = self._template_for("通常", template_arc) if template_arc else None
        if template is None:
            # No portrait to copy from: make game-style textures from scratch.
            size = 256 if (self._mode() or "BU") == "BU" else 128
            parts = {k: new_ctpk(size, size) for k in BASIC_EXPRESSIONS}
            parts.update({"頬": new_ctpk(64, 32), "汗": new_ctpk(16, 16), "髪": new_ctpk(32, 32), "髪0": new_ctpk(32, 32)})
            return parts
        parts = {}
        for k in BASIC_EXPRESSIONS:
            src = self._raw_ctpk(k, template_arc) if copy_current else None
            parts[k] = src if src is not None else blank_ctpk(template)
        for k in EXTRA_PARTS:
            src = self._raw_ctpk(k, template_arc)
            if src is not None:
                parts[k] = src  # blush, sweat and hair masks are copied (replace them with Import)
        return parts

    def _fallback_arc(self) -> Dict[str, bytes]:
        """A vanilla portrait of the same kind (BU/FC) to copy texture sizes from."""
        mode = self._mode() or "BU"
        for fsid in (f"FSID_{mode}_クロム_通常", f"FSID_{mode}_リズ_通常"):
            try:
                rid = self.data.key_to_rid("portraits", fsid)
                f = self.data.string(rid, "portrait_file") if rid else None
                if f:
                    a = self.data.read_arc(f"face/{f}")
                    if a:
                        return a
            except Exception:
                continue
        return {}
