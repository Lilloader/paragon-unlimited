"""Paragon Unlimited: preview for FE13 Asset Definitions / Presets entries.

Shows an English reading of the (Japanese) entry name, 3D views of the battle model
(body + head + hair on the skeleton, the mount and the weapon; drag to turn) and the
textures the entry uses. Click a texture (or drop a PNG on it) to import your own image:
it is re-encoded in the texture's own format and written to b/<texture>.t.lz when you save.
Everything else here is read-only.
"""
import logging
import os
import re

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QFrame,
    QMenu,
    QFileDialog,
    QMessageBox,
    QPushButton,
    QColorDialog,
)

from paragon.ui.controllers.auto.abstract_auto_widget import AbstractAutoWidget

SLOTS = [
    ("Body", "body_texture"),
    ("Head", "head_texture"),
    ("Hair", "hair_texture"),
    ("Mount", "mount_texture"),
]
THUMB = 160
VIEW = 240
IMAGE_FILTER = "Images (*.png *.webp *.bmp *.jpg *.jpeg *.tga)"
IMAGE_EXT = (".png", ".webp", ".bmp", ".jpg", ".jpeg", ".tga")


def _base(tex_name: str) -> str:
    """uBody_M_lod1_0_c2 -> uBody_M_lod1_0 (color variants share a base)."""
    return re.sub(r"_c\d+$", "", tex_name or "")


class ModelView(QLabel):
    """Software-rendered 3D view. Drag to turn, wheel to zoom, double-click to reset."""

    def __init__(self, size=VIEW):
        super().__init__()
        self.size_px = size
        self.setFixedSize(size, size)
        self.setAlignment(Qt.AlignCenter)
        self.setStyleSheet("background-color: #202020; border: 1px solid #555;")
        self.setToolTip("Drag to turn the model, mouse wheel to zoom, double-click to reset.")
        self.model = None
        self.textures = {}
        self.yaw, self.pitch, self.zoom = 20.0, 5.0, 1.0
        self._last = None

    def set_model(self, model, textures, message=None):
        self.model, self.textures = model, textures
        self.yaw, self.pitch, self.zoom = 20.0, 5.0, 1.0
        if model is None:
            self.setPixmap(QPixmap())
            self.setText(message or "No model")
        else:
            self.redraw()

    def redraw(self, fast=False):
        if self.model is None:
            return
        try:
            from paragon.core.services.fe13_models import render_image

            img = render_image(self.model, self.textures, self.size_px, self.yaw, self.pitch, self.zoom,
                               supersample=1 if fast else 2)
            self.setPixmap(img.toqpixmap())
        except Exception:
            logging.exception("Model render failed.")
            self.model = None
            self.setText("Could not draw\nthis model")

    def mousePressEvent(self, e):
        self._last = e.position()

    def mouseMoveEvent(self, e):
        if self._last is None or self.model is None:
            return
        d = e.position() - self._last
        self._last = e.position()
        self.yaw = (self.yaw - d.x() * 0.8) % 360
        self.pitch = max(-89.0, min(89.0, self.pitch + d.y() * 0.6))
        self.redraw(fast=True)

    def mouseReleaseEvent(self, e):
        self._last = None
        self.redraw()

    def mouseDoubleClickEvent(self, e):
        self.yaw, self.pitch, self.zoom = 20.0, 5.0, 1.0
        self.redraw()

    def wheelEvent(self, e):
        if self.model is None:
            return
        self.zoom = max(0.3, min(8.0, self.zoom * (1.15 if e.angleDelta().y() > 0 else 1 / 1.15)))
        self.redraw()


class TextureSlot(QLabel):
    """Texture thumbnail. Click for Import / Export / Undo; drop an image to import it."""

    def __init__(self, preview, tex_name):
        super().__init__()
        self.preview = preview
        self.tex_name = tex_name
        self.setFixedSize(THUMB, THUMB)
        self.setAlignment(Qt.AlignCenter)
        self.setAcceptDrops(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet("background-color: #202020; border: 1px solid #555;")

    def mousePressEvent(self, e):
        menu = QMenu(self)
        menu.addAction("Import image...", lambda: self.preview.import_into(self.tex_name))
        menu.addAction("Export PNG...", lambda: self.preview.export_texture(self.tex_name))
        if self.preview.edits().is_pending(self.tex_name):
            menu.addAction("Undo import", lambda: self.preview.undo_import(self.tex_name))
        menu.exec(e.globalPosition().toPoint())

    def dragEnterEvent(self, e):
        if self._files(e.mimeData()):
            e.acceptProposedAction()

    def dropEvent(self, e):
        files = self._files(e.mimeData())
        if files:
            e.acceptProposedAction()
            self.preview.import_into(self.tex_name, files[0])

    @staticmethod
    def _files(mime):
        if not mime or not mime.hasUrls():
            return []
        return [u.toLocalFile() for u in mime.urls() if u.isLocalFile() and u.toLocalFile().lower().endswith(IMAGE_EXT)]


class FE13AssetPreview(AbstractAutoWidget, QWidget):
    _model_cache = {}

    def __init__(self, state):
        AbstractAutoWidget.__init__(self, state)
        QWidget.__init__(self)
        self.rid = None
        self.model_view = None
        self.views = {}
        self.slots = {}
        self._tex_cache = {}
        self.hair_override = None  # hair color picked in the preview (preview only)
        self._hair_color = None
        self.title = QLabel()
        self.title.setWordWrap(True)
        f = self.title.font()
        f.setPointSize(f.pointSize() + 2)
        f.setBold(True)
        self.title.setFont(f)
        self.detail = QLabel()
        self.detail.setWordWrap(True)
        self.status = QLabel()
        self.status.setWordWrap(True)
        self.row = QHBoxLayout()
        self.row.setAlignment(Qt.AlignLeft)
        holder = QWidget()
        holder.setLayout(self.row)
        scroll = QScrollArea()
        scroll.setWidget(holder)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setMinimumHeight(VIEW + 60)
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.title)
        layout.addWidget(self.detail)
        layout.addWidget(scroll, 1)
        layout.addWidget(self.status)
        self.setLayout(layout)

    def english_name(self, name: str) -> str:
        from paragon.core.services.fe13_asset_names import english_name

        return english_name(self.data, name)

    def edits(self):
        from paragon.core.services.fe13_model_textures import edits_for

        return edits_for(self.gs)

    # ---------------------------------------------------------------- loading
    def _resolve(self, name, ext):
        """Names with '%' are picked at run time by the game (e.g. hair variant _0%):
        show the first variant that exists."""
        if not name or "%" not in name:
            return name
        for d in "0123456789":
            cand = name.replace("%", d)
            try:
                if self.data.file_exists(f"b/{cand}{ext}", False):
                    return cand
            except Exception:
                pass
        return name

    def _load_model(self, name):
        name = self._resolve(name, ".m.lz")
        if not name:
            return None
        if name in self._model_cache:
            return self._model_cache[name]
        model = None
        try:
            from paragon.core.services.fe13_models import load_model

            model = load_model(self.data, name)
            if not model.meshes:
                model = None
        except Exception:
            logging.exception(f"Could not read model {name}")
        self._model_cache[name] = model
        return model

    def _rgba(self, name, model=None):
        """(w, h, rgba) of a texture, including unsaved imports; textures kept inside the
        model file (weapons) are used when there is no b/<name>.t.lz."""
        name = self._resolve(name, ".t.lz")
        if not name:
            return None
        if name in self._tex_cache:
            return self._tex_cache[name]
        from paragon.core.services.fe13_models import load_texture, texture_from_cgfx

        tex = None
        try:
            tex = load_texture(self.data, name, self.edits().current(self.edits().path_for(name)))
        except Exception:
            tex = None
        if tex is None and model is not None and model.source:
            tex = texture_from_cgfx(model.source, name, fallback_first=False)
        self._tex_cache[name] = tex
        return tex

    def _textures_for(self, model, override=None):
        """Texture name -> image for every mesh; the entry's own texture replaces the
        model's default when it is a color variant of it (or the model has one texture)."""
        out = {}
        names = {m.texture for m in model.meshes if m.texture}
        for n in names:
            use = n
            if override and (_base(override) == _base(n) or len(names) == 1):
                use = override
            out[n] = self._rgba(use, model) or self._rgba(n, model)
        return out

    # ---------------------------------------------------------------- display
    def _clear_row(self):
        while self.row.count():
            item = self.row.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.views = {}
        self.slots = {}
        self.model_view = None

    def _boxed(self, widget, caption, extra=None):
        box = QVBoxLayout()
        box.addWidget(widget)
        cap = QLabel(caption)
        cap.setAlignment(Qt.AlignCenter)
        box.addWidget(cap)
        if extra is not None:
            box.addWidget(extra)
        w = QWidget()
        w.setLayout(box)
        self.row.addWidget(w)

    def set_target(self, rid):
        if rid != self.rid:
            self.hair_override = None
        self.rid = rid
        self._clear_row()
        self.status.setText("")
        if not rid:
            self.title.setText("")
            self.detail.setText("")
            return
        name = self.data.string(rid, "name")
        self.title.setText(self.english_name(name))
        bits = []
        for label, fid in (("Voice", "voice"), ("Weapon", "weapon_model"), ("Condition", "conditional")):
            v = self.data.string(rid, fid)
            if v:
                bits.append(f"{label}: {v}")
        self.detail.setText("   ".join(bits))
        self._add_views(rid)
        self._add_slots(rid)

    # ---------------------------------------------------------------- hair color
    def character_hair_color(self, rid):
        """'#rrggbb' from the character's FaceData when the entry is named after a PID."""
        name = self.data.string(rid, "name") or ""
        if not name.startswith("PID_"):
            return None
        try:
            person = self.data.key_to_rid("characters", name)
            fid = self.data.string(person, "fid") if person else None
            if not fid or not fid.startswith("FID_"):
                return None
            fd = self.data.key_to_rid("portraits", f"FSID_BU_{fid[4:]}_通常")
            raw = self.data.bytes(fd, "hair_color") if fd else None
            raw = bytes(raw) if raw else b""
            if len(raw) >= 3 and any(raw[:3]):
                return "#" + raw[:3].hex()
        except Exception:
            logging.exception("Could not read the hair color.")
        return None

    @staticmethod
    def _is_gray(tex) -> bool:
        w, h, px = tex
        step = max(4, (len(px) // 4 // 4000) * 4)
        sat = n = 0
        for i in range(0, len(px) - 3, step):
            if px[i + 3] < 32:
                continue
            r, g, b = px[i], px[i + 1], px[i + 2]
            sat += max(r, g, b) - min(r, g, b)
            n += 1
        return n > 0 and sat / n < 14

    def _tinted(self, tex, color):
        """Hair textures that are gray in the files get their color in game (FaceData)."""
        if not tex or not color or not self._is_gray(tex):
            return tex
        try:
            from PIL import Image
            from paragon.core.services import utils

            img = Image.frombytes("RGBA", (tex[0], tex[1]), tex[2])
            return tex[0], tex[1], utils.image_tint_overlay(img, color).convert("RGBA").tobytes()
        except Exception:
            logging.exception("Hair tint failed.")
            return tex

    def _pick_hair_color(self):
        from PySide6.QtGui import QColor

        start = QColor(self.hair_override or self._hair_color or "#808080")
        color = QColorDialog.getColor(start, self, "Hair color (preview only)")
        if color.isValid():
            self.hair_override = color.name()
            self._refresh_after_change()

    def _add_views(self, rid):
        from paragon.core.services.fe13_models import assemble

        s = lambda f: self.data.string(rid, f)
        self._hair_color = self.character_hair_color(rid)
        hair_color = self.hair_override or self._hair_color
        body = self._load_model(s("body_model"))
        head = self._load_model(s("head_model"))
        hair = self._load_model(s("hair_model"))
        if body or head or hair:
            textures = {}
            for model, override in ((body, s("body_texture")), (head, s("head_texture")), (hair, s("hair_texture"))):
                if model is not None:
                    part = self._textures_for(model, override)
                    if model is hair:
                        part = {k: self._tinted(v, hair_color) for k, v in part.items()}
                    textures.update(part)
            character = assemble(body, [head, hair])
            view = ModelView()
            view.set_model(character, textures)
            parts = [n for n in (s("body_model"), s("head_model"), s("hair_model")) if n]
            missing = [n for n, m in ((s("body_model"), body), (s("head_model"), head), (s("hair_model"), hair)) if n and m is None]
            caption = "Character\n" + " + ".join(parts)
            if missing:
                caption += "\n(not found: " + ", ".join(missing) + ")"
            extra = None
            if hair is not None:
                extra = QPushButton(f"Hair color: {hair_color}" if hair_color else "Hair color...")
                extra.setToolTip(
                    "Gray hair textures are colored by the game with the character's hair color "
                    "(FaceData). Pick a color to preview it; this does not change any data."
                )
                if hair_color:
                    extra.setStyleSheet(f"border-left: 14px solid {hair_color};")
                extra.clicked.connect(self._pick_hair_color)
            self._boxed(view, caption, extra)
            self.views["character"] = view
            self.model_view = view
        for key, field, tex_field, label in (
            ("mount", "mount_model", "mount_texture", "Mount"),
            ("weapon", "weapon_model", None, "Weapon"),
        ):
            name = s(field)
            if not name:
                continue
            model = self._load_model(name)
            view = ModelView(VIEW if key == "mount" else 180)
            if model is None:
                view.set_model(None, {}, f"{name}\nnot found")
            else:
                view.set_model(model, self._textures_for(model, s(tex_field) if tex_field else None))
            self._boxed(view, f"{label}\n{name}")
            self.views[key] = view

    def _add_slots(self, rid):
        shown = 0
        for label, field in SLOTS:
            tex_name = self.data.string(rid, field)
            if not tex_name:
                continue
            slot = TextureSlot(self, tex_name)
            self._fill_slot(slot)
            pending = " (imported, saved on Save)" if self.edits().is_pending(tex_name) else ""
            self._boxed(slot, f"{label}\n{tex_name}{pending}")
            self.slots[tex_name] = slot
            shown += 1
        if not shown and not self.views:
            self.row.addWidget(QLabel("This entry does not set any models or textures."))

    def _fill_slot(self, slot):
        tex = self._rgba(slot.tex_name)
        if tex:
            from PIL import Image

            img = Image.frombytes("RGBA", (tex[0], tex[1]), tex[2])
            pix = img.toqpixmap()
            slot.setPixmap(pix.scaled(THUMB, THUMB, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            info = self.edits().info(slot.tex_name)
            fmt = ""
            if info:
                from paragon.core.services.fe13_model_textures import FORMAT_NAMES

                fmt = f", {FORMAT_NAMES.get(info.fmt, info.fmt)}"
            slot.setToolTip(f"{slot.tex_name} ({tex[0]}x{tex[1]}{fmt})\nClick to import / export, or drop an image here.")
        else:
            slot.setText("not found")

    # ---------------------------------------------------------------- import / export
    def import_into(self, tex_name, path=None):
        if path is None:
            path, _ = QFileDialog.getOpenFileName(self, f"Import image for {tex_name}", "", IMAGE_FILTER)
            if not path:
                return
        try:
            line = self.edits().import_image(tex_name, path)
        except Exception as e:
            logging.exception("Texture import failed.")
            QMessageBox.warning(self, "Paragon Unlimited", f"Could not import {os.path.basename(path)}:\n{e}")
            return
        self._refresh_after_change()
        self.status.setText(f"Imported {line} Written to b/{tex_name}.t.lz when you save.")

    def undo_import(self, tex_name):
        self.edits().revert(tex_name)
        self._refresh_after_change()
        self.status.setText(f"Import of {tex_name} undone.")

    def export_texture(self, tex_name):
        tex = self._rgba(tex_name)
        if not tex:
            return
        fn, _ = QFileDialog.getSaveFileName(self, "Export PNG", f"{tex_name}.png", "PNG (*.png)")
        if fn:
            from PIL import Image

            Image.frombytes("RGBA", (tex[0], tex[1]), tex[2]).save(fn)
            self.status.setText(f"Saved {fn}.")

    def _refresh_after_change(self):
        self._tex_cache.clear()
        if self.rid:
            status = self.status.text()
            self.set_target(self.rid)
            self.status.setText(status)
