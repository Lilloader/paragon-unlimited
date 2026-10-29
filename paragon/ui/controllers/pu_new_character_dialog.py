"""Paragon Unlimited: New Character helper (FE13)."""
import logging

from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QLineEdit,
    QComboBox,
    QCheckBox,
    QDialogButtonBox,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
)

from paragon.core.services import fe13_new_character as nc


class NewCharacterDialog(QDialog):
    def __init__(self, gs, parent=None):
        super().__init__(parent)
        self.gs = gs
        self.result_info = None
        self.setWindowTitle("Paragon Unlimited - New Character")
        self.ident = QLineEdit()
        self.ident.setPlaceholderText("e.g. Gisselle  (letters, numbers, _)")
        self.name = QLineEdit()
        self.name.setPlaceholderText("Name shown in game")
        self.description = QPlainTextEdit()
        self.description.setPlaceholderText("Description shown in the unit screen")
        self.description.setFixedHeight(60)
        self.template = QComboBox()
        self.template.setEditable(False)
        self._fill_templates()
        self.portraits = QComboBox()
        self.portraits.addItem("Blank expressions (import your images afterwards)", "blank")
        self.portraits.addItem("Copies of the template's portraits", "copy")
        self.portraits.addItem("No portrait files (set them up later)", "none")
        self.battle_model = QCheckBox("Copy the template's battle model (Asset Definitions)")
        self.battle_model.setChecked(True)
        self.ident.textChanged.connect(self._sync_name)
        form = QFormLayout()
        form.addRow("ID", self.ident)
        form.addRow("Name", self.name)
        form.addRow("Description", self.description)
        form.addRow("Start from", self.template)
        form.addRow("Portraits", self.portraits)
        form.addRow("", self.battle_model)
        note = QLabel(
            "Creates the character (a copy of the one you start from, with no supports), its two "
            "FaceData entries, portrait files with the basic expressions 通常, 笑, 怒, 苦, キメ and an "
            "Asset Definitions entry. Nothing is written until you save. To make the character join "
            "your army you still place them in a chapter."
        )
        note.setWordWrap(True)
        form.addRow(note)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._on_ok)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)
        self.setLayout(form)
        self.resize(560, 360)
        self._name_touched = False
        self.name.textEdited.connect(lambda _t: setattr(self, "_name_touched", True))

    def _fill_templates(self):
        gd = self.gs.data
        try:
            rid, field = gd.table("characters")
            for r in gd.items(rid, field):
                pid = gd.string(r, "pid")
                if not pid:
                    continue
                label = pid
                try:
                    key = gd.string(r, "name")
                    shown = gd.message("m/GameData.bin.lz", True, key) if key else None
                    if shown:
                        label = f"{shown}  ({pid})"
                except Exception:
                    pass
                self.template.addItem(label, pid)
        except Exception:
            logging.exception("Could not list characters.")
        i = self.template.findData("PID_リズ")
        if i >= 0:
            self.template.setCurrentIndex(i)

    def _sync_name(self, text):
        if not self._name_touched:
            self.name.setText(text.replace("_", " "))

    def request(self):
        return nc.NewCharacterRequest(
            ident=self.ident.text().strip(),
            name=self.name.text().strip(),
            description=self.description.toPlainText().strip(),
            template_pid=self.template.currentData() or "",
            portraits=self.portraits.currentData(),
            battle_model=self.battle_model.isChecked(),
        )

    def _on_ok(self):
        req = self.request()
        err = nc.validate(self.gs.data, req)
        if err:
            QMessageBox.warning(self, "Paragon Unlimited", err)
            return
        try:
            edits = self.gs.portraits.pu_portrait_edits() if hasattr(self.gs.portraits, "pu_portrait_edits") else None
            self.result_info = nc.create(self.gs.data, req, edits, getattr(self.gs, "models", None))
        except Exception as e:
            logging.exception("New character failed.")
            QMessageBox.critical(self, "Paragon Unlimited", f"Could not create the character:\n{e}")
            return
        self.accept()
