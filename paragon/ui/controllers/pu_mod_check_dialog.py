"""Paragon Unlimited: "Check My Mod" window."""
import logging

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication, QColor, QBrush
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QPushButton,
    QComboBox,
    QHeaderView,
    QApplication,
    QFileDialog,
    QAbstractItemView,
)

from paragon.core.services.fe13_mod_check import ModChecker, load_baseline, report_text


class ModCheckDialog(QDialog):
    def __init__(self, gs, parent=None):
        super().__init__(parent)
        self.gs = gs
        self.issues = []
        self.hidden = 0
        self.setWindowTitle("Paragon Unlimited - Check My Mod")
        self.resize(1000, 560)
        self.summary = QLabel("Press Run to scan your project.")
        self.summary.setWordWrap(True)
        self.filter = QComboBox()
        self.filter.addItems(["All", "Errors", "Warnings"])
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["", "Area", "Where", "Problem"])
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Interactive)
        self.table.setColumnWidth(0, 70)
        self.table.setColumnWidth(1, 120)
        self.table.setColumnWidth(2, 300)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setWordWrap(True)
        self.run_button = QPushButton("Run")
        self.fix_case_button = QPushButton("Fix name case")
        self.fix_case_button.setToolTip(
            "Rename project files whose name differs from what the game asks for only in letter\n"
            "case (for example Edelord青 vs edelord青). Then use Copy to Azahar."
        )
        self.fix_case_button.setEnabled(False)
        self.checker = None
        self.copy_button = QPushButton("Copy report")
        self.save_button = QPushButton("Save report...")
        self.close_button = QPushButton("Close")
        top = QHBoxLayout()
        top.addWidget(self.summary, 1)
        top.addWidget(QLabel("Show"))
        top.addWidget(self.filter)
        buttons = QHBoxLayout()
        buttons.addWidget(self.run_button)
        buttons.addWidget(self.fix_case_button)
        buttons.addStretch(1)
        buttons.addWidget(self.copy_button)
        buttons.addWidget(self.save_button)
        buttons.addWidget(self.close_button)
        layout = QVBoxLayout()
        layout.addLayout(top)
        layout.addWidget(self.table, 1)
        layout.addLayout(buttons)
        self.setLayout(layout)
        self.run_button.clicked.connect(self.run)
        self.fix_case_button.clicked.connect(self._fix_case)
        self.filter.currentIndexChanged.connect(self._fill)
        self.copy_button.clicked.connect(lambda: QGuiApplication.clipboard().setText(report_text(self._shown())))
        self.save_button.clicked.connect(self._save)
        self.close_button.clicked.connect(self.close)

    def _voices(self):
        holder = getattr(self.gs, "dialogue", None)
        svc = getattr(holder, "pu_voices", None) if holder is not None else None
        if svc is None:
            try:
                from paragon.core.services.fe13_voices import FE13Voices

                svc = FE13Voices(self.gs.data)
                if holder is not None:
                    holder.pu_voices = svc
            except Exception:
                svc = None
        return svc

    def run(self):
        self.run_button.setEnabled(False)
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            def progress(text):
                self.summary.setText(text)
                QApplication.processEvents()

            checker = ModChecker(self.gs.data, self._voices(), progress, self._roots())
            self.issues = checker.run(load_baseline())
            self.hidden = getattr(checker, "hidden", 0)
            self.checker = checker
        except Exception:
            logging.exception("Mod check failed.")
            self.summary.setText("The check failed (see paragon.log).")
            self.issues = []
        finally:
            QApplication.restoreOverrideCursor()
            self.run_button.setEnabled(True)
        self._fill()
        fixes = len(self.checker.case_fixes) if self.checker else 0
        self.fix_case_button.setEnabled(fixes > 0)
        self.fix_case_button.setText(f"Fix name case ({fixes})" if fixes else "Fix name case")
        return self.issues

    def _roots(self):
        project = getattr(self.gs, "project", None)
        return [getattr(project, "output_path", None), getattr(project, "rom_path", None)]

    def _fix_case(self):
        from PySide6.QtWidgets import QMessageBox

        if not self.checker or not self.checker.case_fixes:
            return
        done = self.checker.fix_name_case()
        QMessageBox.information(
            self,
            "Fix name case",
            "Renamed in your project:\n" + "\n".join(done[:30])
            + ("\n..." if len(done) > 30 else "")
            + "\n\nNow use Copy to Azahar (it also fixes the names in the mod folder).",
        )
        self.run()

    def errors(self):
        return [i for i in self.issues if i.severity == "error"]

    def _shown(self):
        f = self.filter.currentIndex()
        if f == 1:
            return [i for i in self.issues if i.severity == "error"]
        if f == 2:
            return [i for i in self.issues if i.severity == "warning"]
        return list(self.issues)

    def _fill(self):
        shown = self._shown()
        self.table.setRowCount(len(shown))
        for row, issue in enumerate(shown):
            sev = QTableWidgetItem("Error" if issue.severity == "error" else "Warning")
            sev.setForeground(QBrush(QColor("#ff6b6b" if issue.severity == "error" else "#f0c050")))
            self.table.setItem(row, 0, sev)
            self.table.setItem(row, 1, QTableWidgetItem(issue.category))
            self.table.setItem(row, 2, QTableWidgetItem(issue.where))
            self.table.setItem(row, 3, QTableWidgetItem(issue.message))
        self.table.resizeRowsToContents()
        n_err = len(self.errors())
        n_warn = len(self.issues) - n_err
        if not self.issues:
            text = "No problems found."
        else:
            text = f"{n_err} error(s), {n_warn} warning(s). Errors can crash the game or show nothing."
        if self.hidden:
            text += f" ({self.hidden} problems the unmodified game already has are hidden.)"
        self.summary.setText(text)

    def _save(self):
        fn, _ = QFileDialog.getSaveFileName(self, "Save report", "mod_check.txt", "Text (*.txt)")
        if fn:
            with open(fn, "w", encoding="utf-8") as f:
                f.write(report_text(self.issues))
