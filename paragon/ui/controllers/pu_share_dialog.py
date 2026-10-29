"""Paragon Unlimited: Share My Mod - one zip with everything another player needs."""
import logging
import os

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
)

from paragon.core.services import pu_share


class ShareDialog(QDialog):
    def __init__(self, gs, mod_root=None, parent=None):
        super().__init__(parent)
        self.gs = gs
        self.mod_root = mod_root
        self._pu_help_topic = "share"
        self.setWindowTitle("Paragon Unlimited - Share My Mod")
        self.setWindowIcon(QIcon("paragon.ico"))
        self.resize(620, 470)
        out = gs.project.output_path
        info = pu_share.load_info(out)

        intro = QLabel(
            "<b>Pack your mod into one zip</b> that other players can install. It holds only the files "
            "your mod changes, in Azahar's folder layout, with a short <i>HOW_TO_INSTALL.txt</i>.")
        intro.setWordWrap(True)
        self.name_edit = QLineEdit(info.get("name", ""))
        self.name_edit.setPlaceholderText("e.g. Awakening Reborn")
        self.author_edit = QLineEdit(info.get("author", ""))
        self.author_edit.setPlaceholderText("Your name (optional)")
        self.desc_edit = QPlainTextEdit(info.get("description", ""))
        self.desc_edit.setPlaceholderText("What's in your mod? (optional, goes into HOW_TO_INSTALL.txt)")
        self.desc_edit.setMaximumHeight(90)
        form = QFormLayout()
        form.addRow("Mod name:", self.name_edit)
        form.addRow("Made by:", self.author_edit)
        form.addRow("Description:", self.desc_edit)

        self.code_ips = pu_share.find_code_ips(mod_root)
        self.code_check = QCheckBox("Include the game code patch (code.ips) from your Azahar mod folder")
        self.code_check.setToolTip(
            "Needed when your mod uses Paragon Unlimited's code patches (skill effects, more supports).\n"
            + (self.code_ips or "No code.ips found in your Azahar mod folder."))
        self.code_check.setChecked(bool(self.code_ips))
        self.code_check.setEnabled(bool(self.code_ips))
        self.check_first = QCheckBox("Check my mod for problems first (recommended)")
        self.check_first.setChecked(True)
        self.status = QLabel("")
        self.status.setWordWrap(True)

        self.make_button = QPushButton("Make the zip...")
        self.make_button.setStyleSheet(
            "QPushButton { background: #2e8b57; color: white; font-weight: bold; padding: 8px 18px; border-radius: 6px; }")
        self.make_button.clicked.connect(self.make)
        close = QPushButton("Close")
        close.clicked.connect(self.close)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(close)
        buttons.addWidget(self.make_button)

        lay = QVBoxLayout(self)
        lay.addWidget(intro)
        lay.addLayout(form)
        lay.addWidget(self.code_check)
        lay.addWidget(self.check_first)
        lay.addWidget(self.status, 1)
        lay.addLayout(buttons)

    # ------------------------------------------------------------------ helpers
    def _progress(self, text):
        self.status.setText(text)
        QApplication.processEvents()

    def _dlc_romfs(self):
        try:
            from paragon.core.services import fe13_dlc

            ws = fe13_dlc.workspace(self.gs.project.output_path) / "romfs"
            return str(ws) if ws.is_dir() else None
        except Exception:
            return None

    def _check(self) -> bool:
        """Check My Mod; True when it is fine to go on."""
        try:
            from paragon.core.services.fe13_mod_check import ModChecker, load_baseline

            project = self.gs.project
            checker = ModChecker(self.gs.data, None, self._progress, [project.output_path, project.rom_path])
            issues = checker.run(load_baseline())
        except Exception:
            logging.exception("Share: mod check failed")
            return True  # the check itself failing should not block sharing
        errors = [i for i in issues if i.severity == "error"]
        if not errors:
            return True
        shown = "\n".join(f"- {i.where}: {i.message}" for i in errors[:8])
        r = QMessageBox.question(
            self, "Share My Mod",
            f"Check My Mod found {len(errors)} problem(s) that can crash the game or show nothing:\n\n{shown}"
            + ("\n..." if len(errors) > 8 else "")
            + "\n\nShare anyway? (Unlimited -> Check My Mod shows them all and can fix some.)",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        return r == QMessageBox.Yes

    # ------------------------------------------------------------------ make
    def make(self, zip_path=None) -> str:
        name = pu_share.safe_name(self.name_edit.text())
        self.name_edit.setText(name)
        info = {"name": name, "author": self.author_edit.text().strip(),
                "description": self.desc_edit.toPlainText().strip()}
        pu_share.save_info(self.gs.project.output_path, info)
        if self.check_first.isChecked() and not self._check():
            self.status.setText("Not packed. Fix the problems (Unlimited -> Check My Mod) and try again.")
            return ""
        if not zip_path:
            start = os.path.join(os.path.expanduser("~"), "Desktop")
            if not os.path.isdir(start):
                start = os.path.dirname(os.path.abspath(self.gs.project.output_path))
            zip_path, _ = QFileDialog.getSaveFileName(self, "Save the mod as", os.path.join(start, name + ".zip"),
                                                      "Zip files (*.zip)")
        if not zip_path:
            return ""
        if not zip_path.lower().endswith(".zip"):
            zip_path += ".zip"
        self.make_button.setEnabled(False)
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            p = pu_share.plan(self.gs.project.output_path, self.gs.project.rom_path, self._dlc_romfs(),
                              self.code_ips if self.code_check.isChecked() else None, name, self._progress)
            if not p.files:
                QMessageBox.information(self, "Share My Mod", "Your project has no changes yet, so there is nothing to share.")
                return ""
            from paragon.pu_version import VERSION

            pu_share.make_zip(p, zip_path, name, info["author"], info["description"], VERSION, self._progress)
        except Exception as e:
            logging.exception("Share: packing failed")
            QMessageBox.critical(self, "Share My Mod", f"Could not make the zip:\n{e}")
            return ""
        finally:
            QApplication.restoreOverrideCursor()
            self.make_button.setEnabled(True)
        mb = os.path.getsize(zip_path) / (1024 * 1024)
        self.status.setText(f"Done: {zip_path} ({mb:.1f} MB). {p.summary()}.")
        box = QMessageBox(self)
        box.setWindowTitle("Share My Mod")
        box.setText(f"Your mod is ready to share:\n\n{zip_path}\n({mb:.1f} MB)\n\n{p.summary()}.")
        show = box.addButton("Show in folder", QMessageBox.ActionRole)
        box.addButton(QMessageBox.Ok)
        if os.environ.get("QT_QPA_PLATFORM") != "offscreen":
            box.exec()
            if box.clickedButton() is show:
                QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.dirname(zip_path)))
        return zip_path
