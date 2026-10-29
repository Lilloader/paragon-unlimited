"""Paragon Unlimited: import a PNG as a skill icon (FE13). The icon goes into the next free cell
of skill.tga (or replaces this skill's own added icon) and the skill's Icon field is set to it."""
import logging

from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QFileDialog, QHBoxLayout, QLabel, QPushButton, QWidget

from paragon.core.services import fe13_skill_icons as si
from paragon.ui.controllers.auto.abstract_auto_widget import AbstractAutoWidget

GAME_ICON_CELLS = 105  # cells 0-104 hold the game's own icons


class FE13SkillIconImport(AbstractAutoWidget, QWidget):
    def __init__(self, state):
        AbstractAutoWidget.__init__(self, state)
        QWidget.__init__(self)
        self.rid = None
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        self.button = QPushButton("Import icon (PNG)...")
        self.button.setToolTip(
            "Use a PNG (24x24 is best; other sizes are scaled) as this skill's icon.\n"
            "It goes into a free icon cell and is written to systems/icon*.ctpk.lz when you save."
        )
        self.button.clicked.connect(self._on_import)
        self.status = QLabel("")
        self.status.setWordWrap(True)
        layout.addWidget(self.button)
        layout.addWidget(self.status, 1)
        self.setLayout(layout)

    def set_target(self, rid):
        self.rid = rid
        self.status.setText("")
        self.button.setEnabled(rid is not None)

    def _on_import(self):
        if not self.rid:
            return
        path, _ = QFileDialog.getOpenFileName(self, "Skill icon", "", "Images (*.png *.bmp *.gif *.jpg)")
        if not path:
            return
        try:
            from PIL import Image

            rgba = si.fit_icon(Image.open(path))
            edits = si.edits_for(self.gs)
            current = self.data.int(self.rid, "icon")
            # Re-importing for a skill that already has its own added icon reuses that cell.
            reuse = current if current is not None and current >= GAME_ICON_CELLS and not self._shared(current) else None
            cell = edits.import_icon(rgba, reuse)
            self.data.set_int(self.rid, "icon", cell)
            self._refresh_model(cell, rgba)
            self.status.setText(f"Icon cell {cell}. Written when you save.")
        except Exception as e:
            logging.exception("Skill icon import failed.")
            self.status.setText(f"Could not import: {e}")

    def _shared(self, cell) -> bool:
        node = self.data.node("skills")
        if node is None:
            return False
        users = [r for r in self.data.items(node.rid, "skills") if self.data.int(r, "icon") == cell]
        return len([r for r in users if r != self.rid]) > 0

    def _refresh_model(self, cell, rgba):
        try:
            model = self.gs.icons.model("skill")
            if model is None:
                return
            img = QImage(rgba, si.CELL, si.CELL, si.CELL * 4, QImage.Format.Format_RGBA8888).copy()
            pix = QPixmap.fromImage(img)
            if cell < len(model.icons):
                model.icons[cell] = pix
                idx = model.index(cell, 0)
                model.dataChanged.emit(idx, idx)
        except Exception:
            logging.exception("Could not refresh the icon list.")
