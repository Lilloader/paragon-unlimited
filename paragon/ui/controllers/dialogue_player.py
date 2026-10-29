import logging
from typing import Optional, List

from PySide6.QtCore import QTimer
from PySide6.QtGui import QTransform

from paragon.ui.renderers.fates_standard_dialogue_renderer import (
    FatesStandardDialogueRenderer,
)

from paragon.ui.renderers.fates_mini_dialogue_renderer import FatesMiniDialogueRenderer

from paragon.model.dialogue_snapshot import DialogueSnapshot
from paragon.model.game import Game
from paragon.ui.renderers.awakening_standard_dialogue_renderer import (
    AwakeningStandardDialogueRenderer,
)
from paragon.ui.renderers.sov_mini_dialogue_renderer import SOVMiniDialogueRenderer
from paragon.ui.renderers.sov_standard_dialogue_renderer import (
    SOVStandardDialogueRenderer,
)
from paragon.ui.views.ui_dialogue_player import Ui_DialoguePlayer


class DialoguePlayer(Ui_DialoguePlayer):
    def __init__(self):
        super().__init__()
        self.service = None
        self.sprite_animation_svc = None
        self.game = Game.FE15
        self.snapshots: List[DialogueSnapshot] = []
        self.current: Optional[int] = None

        self.refresh_buttons()

        self.background_box.currentIndexChanged.connect(self.redraw)
        self.window_type_box.currentIndexChanged.connect(self.redraw)
        self.begin_button.clicked.connect(self._on_begin)
        self.end_button.clicked.connect(self._on_end)
        self.next_button.clicked.connect(self._on_next)
        self.previous_button.clicked.connect(self._on_previous)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self._on_tick)
        self.play_button.toggled.connect(self._on_play_toggled)
        self.zoom_box.currentIndexChanged.connect(self._on_zoom)
        self.voice_log = []  # voice lines played (for tests / status)

    def _on_begin(self):
        self._set_current(0)

    def _on_end(self):
        self._set_current(len(self.snapshots) - 1)

    def _on_next(self):
        self._set_current(self.current + 1)

    def _on_previous(self):
        self._set_current(self.current - 1)

    def _set_current(self, index):
        self.current = index
        self.redraw()
        self.refresh_buttons()
        self._play_voices()
        if self.play_button.isChecked():
            self._schedule_next()

    # ---------------------------------------------------------------- Paragon Unlimited
    def _voices(self):
        if self.game != Game.FE13 or self.service is None:
            return None
        svc = getattr(self.service, "pu_voices", None)
        if svc is None:
            try:
                from paragon.core.services.fe13_voices import FE13Voices

                svc = FE13Voices(self.service.data)
                self.service.pu_voices = svc
            except Exception:
                logging.exception("Voices unavailable.")
                return None
        return svc

    def _snapshot(self):
        if self.current is None or not (0 <= self.current < len(self.snapshots)):
            return None
        return self.snapshots[self.current]

    def _play_voices(self):
        snap = self._snapshot()
        self._voice_seconds = 0.0
        if snap is None or not self.voices_check.isChecked():
            return
        voices = getattr(snap, "voices", None) or []
        svc = self._voices() if voices else None
        if not svc:
            return
        for name in voices[:1]:
            try:
                if svc.has(name):
                    svc.play(name)
                    self._voice_seconds = svc.duration(name)
                    self.voice_log.append(name)
            except Exception:
                logging.exception(f"Could not play {name}.")

    def _schedule_next(self):
        snap = self._snapshot()
        if snap is None or self.current >= len(self.snapshots) - 1:
            self.play_button.setChecked(False)
            return
        text = (snap.top_text() + snap.bottom_text()).strip()
        seconds = max(1.2 + 0.045 * len(text), getattr(self, "_voice_seconds", 0.0) + 0.4)
        self.timer.start(int(seconds * 1000))

    def _on_tick(self):
        if self.play_button.isChecked() and self.current is not None and self.current < len(self.snapshots) - 1:
            self._set_current(self.current + 1)
        else:
            self.play_button.setChecked(False)

    def _on_play_toggled(self, on):
        self.play_button.setText("Stop" if on else "Play")
        if on:
            if self.current is None or self.current >= len(self.snapshots) - 1:
                self._set_current(0)
            else:
                self._play_voices()
                self._schedule_next()
        else:
            self.timer.stop()
            svc = getattr(self.service, "pu_voices", None) if self.service else None
            if svc:
                try:
                    svc.stop()
                except Exception:
                    pass

    def _on_zoom(self):
        z = self.zoom_box.currentIndex() + 1
        self.view.setFixedSize(400 * z, 242 * z)
        self.view.setTransform(QTransform.fromScale(z, z))

    def set_service(self, service, sprite_animation_svc):
        self.service = service
        self.sprite_animation_svc = sprite_animation_svc

    def set_backgrounds(self, backgrounds):
        self.background_box.clear()
        for name, pixmap in backgrounds:
            self.background_box.addItem(name, pixmap)

    def set_windows(self, sets):
        self.window_type_box.clear()
        for k, v in sets.items():
            self.window_type_box.addItem(k, v)

    def set_game(self, game: Game):
        self.game = game
        self.redraw()

    def set_snapshots(self, snapshots: List[DialogueSnapshot]):
        self.snapshots = snapshots
        self.current = 0 if self.snapshots else None
        self.redraw()
        self.refresh_buttons()

    def refresh_buttons(self):
        self.begin_button.setEnabled(len(self.snapshots) > 0)
        self.end_button.setEnabled(len(self.snapshots) > 0)
        self.next_button.setEnabled(
            self.current is not None and self.current < len(self.snapshots) - 1
        )
        self.previous_button.setEnabled(self.current is not None and self.current > 0)

    def redraw(self):
        # Clear out the old scene.
        self.scene.clear()

        # Draw the background.
        background = self.background_box.currentData()
        if background:
            self.scene.addPixmap(background)

        # Get the window set.
        window_set = self.window_type_box.currentData()
        if not window_set:
            return  # TODO: Issue a warning maybe?

        # Render.
        if self.current is not None:
            current = self.snapshots[self.current]
            if self.game == Game.FE15 and current.conversation_type == 0:
                renderer = SOVMiniDialogueRenderer()
            elif self.game == Game.FE15:
                renderer = SOVStandardDialogueRenderer()
            elif self.game == Game.FE14 and current.conversation_type == 0:
                renderer = FatesMiniDialogueRenderer()
            elif self.game == Game.FE14:
                renderer = FatesStandardDialogueRenderer()
            elif self.game == Game.FE13:
                renderer = AwakeningStandardDialogueRenderer()
            else:
                raise NotImplementedError(
                    "No renderer available for current game / type."
                )
            renderer.render(
                self.scene,
                window_set,
                self.service,
                self.sprite_animation_svc,
                current,
            )
