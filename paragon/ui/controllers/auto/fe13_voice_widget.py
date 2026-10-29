"""Paragon Unlimited: hear a character's English voice lines (Characters editor tab)."""
import logging

from PySide6 import QtCore
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QCheckBox,
    QApplication,
)

from paragon.ui.controllers.auto.abstract_auto_widget import AbstractAutoWidget


def voices_service(gs):
    """One shared FE13Voices per project (kept on the dialogue service)."""
    holder = gs.dialogue
    svc = getattr(holder, "pu_voices", None)
    if svc is None:
        from paragon.core.services.fe13_voices import FE13Voices

        svc = FE13Voices(gs.data)
        holder.pu_voices = svc
    return svc


class FE13VoiceWidget(AbstractAutoWidget, QWidget):
    def __init__(self, state):
        AbstractAutoWidget.__init__(self, state)
        QWidget.__init__(self)
        self.rid = None
        self.info = QLabel()
        self.info.setWordWrap(True)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Filter (e.g. EVT, ATTACK, DAMAGE)")
        self.show_all = QCheckBox("All characters")
        self.list = QListWidget()
        self.play_button = QPushButton("Play")
        self.stop_button = QPushButton("Stop")
        self.copy_button = QPushButton("Copy $PlayVoice(...)")
        top = QHBoxLayout()
        top.addWidget(self.search, 1)
        top.addWidget(self.show_all)
        buttons = QHBoxLayout()
        buttons.addWidget(self.play_button)
        buttons.addWidget(self.stop_button)
        buttons.addWidget(self.copy_button)
        buttons.addStretch(1)
        layout = QVBoxLayout()
        layout.addWidget(self.info)
        layout.addLayout(top)
        layout.addWidget(self.list, 1)
        layout.addLayout(buttons)
        self.setLayout(layout)
        self.search.textChanged.connect(self._filter)
        self.show_all.toggled.connect(self._refresh)
        self.list.itemDoubleClicked.connect(lambda _i: self._play())
        self.play_button.clicked.connect(self._play)
        self.stop_button.clicked.connect(self._stop)
        self.copy_button.clicked.connect(self._copy)
        self._loaded_for = None

    def set_target(self, rid):
        self.rid = rid
        self._loaded_for = None
        if self.isVisible():
            self._refresh()

    def showEvent(self, e):
        super().showEvent(e)
        if self._loaded_for != (self.rid, self.show_all.isChecked()):
            self._refresh()

    def _refresh(self):
        self.list.clear()
        if not self.rid and not self.show_all.isChecked():
            self.info.setText("")
            return
        QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
        try:
            svc = voices_service(self.gs)
            pid = self.data.string(self.rid, "pid") if self.rid else None
            if self.show_all.isChecked():
                names = svc.all_voices()
                self.info.setText(f"All {len(names)} English voice lines.")
            else:
                codes = svc.voice_codes_for_pid(pid) if pid else []
                names = svc.voices_for_codes(codes)
                if svc.error:
                    self.info.setText(f"Could not read the voice archive: {svc.error}")
                elif not codes:
                    self.info.setText(
                        f"{pid} has no voice set in Asset Definitions (an entry named {pid} with a Voice). "
                        "Tick 'All characters' to browse every line."
                    )
                else:
                    self.info.setText(
                        f"Voice set: {', '.join(codes)} - {len(names)} English lines. Double-click to play."
                    )
            self.list.addItems(names)
            self._filter()
            self._loaded_for = (self.rid, self.show_all.isChecked())
        except Exception:
            logging.exception("Could not list voice lines.")
            self.info.setText("Could not list voice lines (see paragon.log).")
        finally:
            QApplication.restoreOverrideCursor()

    def _filter(self):
        text = self.search.text().strip().upper()
        for i in range(self.list.count()):
            item = self.list.item(i)
            item.setHidden(bool(text) and text not in item.text().upper())

    def _current(self):
        item = self.list.currentItem()
        return item.text() if item else None

    def _play(self):
        name = self._current()
        if not name:
            return
        try:
            voices_service(self.gs).play(name)
        except Exception:
            logging.exception(f"Could not play {name}.")
            self.info.setText(f"Could not play {name} (see paragon.log).")

    def _stop(self):
        try:
            voices_service(self.gs).stop()
        except Exception:
            pass

    def _copy(self):
        name = self._current()
        if name:
            QGuiApplication.clipboard().setText(f"$PlayVoice({name})")
