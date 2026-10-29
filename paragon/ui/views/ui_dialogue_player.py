from PySide6 import QtGui
from PySide6.QtCore import QRectF
from PySide6.QtWidgets import (
    QWidget,
    QGraphicsView,
    QGraphicsScene,
    QPushButton,
    QHBoxLayout,
    QVBoxLayout,
    QGroupBox,
    QFormLayout,
    QComboBox,
    QCheckBox,
)

from paragon.ui.controllers.scene_graphics_view import DialogueGraphicsView


class Ui_DialoguePlayer(QWidget):
    def __init__(self):
        super().__init__()
        self.view = DialogueGraphicsView()
        self.view.setFixedSize(400, 242)
        self.view.setHorizontalScrollBarPolicy(QtGui.Qt.ScrollBarAlwaysOff)
        self.view.setVerticalScrollBarPolicy(QtGui.Qt.ScrollBarAlwaysOff)

        self.scene = QGraphicsScene()
        self.scene.setSceneRect(0, 0, 400, 242)
        self.view.setScene(self.scene)

        self.begin_button = QPushButton("<<")
        self.previous_button = QPushButton("<")
        self.next_button = QPushButton(">")
        self.end_button = QPushButton(">>")

        self.buttons_layout = QHBoxLayout()
        self.buttons_layout.setContentsMargins(0, 0, 0, 0)
        self.buttons_layout.addWidget(self.begin_button)
        self.buttons_layout.addWidget(self.previous_button)
        self.buttons_layout.addWidget(self.next_button)
        self.buttons_layout.addWidget(self.end_button)
        # Paragon Unlimited: play the conversation like the game (voices, auto-advance).
        self.play_button = QPushButton("Play")
        self.play_button.setCheckable(True)
        self.play_button.setToolTip("Step through the conversation automatically, with voice lines.")
        self.voices_check = QCheckBox("Voices")
        self.voices_check.setChecked(True)
        self.voices_check.setToolTip("Play $PlayVoice lines (English) when a line is shown.")
        self.zoom_box = QComboBox()
        self.zoom_box.addItems(["1x", "2x"])
        self.buttons_layout.addSpacing(12)
        self.buttons_layout.addWidget(self.play_button)
        self.buttons_layout.addWidget(self.voices_check)
        self.buttons_layout.addWidget(self.zoom_box)
        self.buttons_layout.setAlignment(QtGui.Qt.AlignHCenter)

        self.background_box = QComboBox()
        self.window_type_box = QComboBox()
        config_layout = QFormLayout()
        config_layout.addRow("Background", self.background_box)
        config_layout.addRow("Window Type", self.window_type_box)
        config_box = QGroupBox("Configure Preview")
        config_box.setLayout(config_layout)

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.view)
        layout.addLayout(self.buttons_layout)
        layout.addWidget(config_box)
        layout.addStretch()
        self.setLayout(layout)
