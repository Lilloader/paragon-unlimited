"""Paragon Unlimited: additions to the conversation preview: Play (steps through the lines and plays
the voice lines) and 2x zoom.
"""
import logging
from PySide6.QtGui import QTransform
from paragon.model.game import Game


class DialoguePlayerFeatures:
    """Mixed into DialoguePlayer (paragon/ui/controllers/dialogue_player.py)."""

    # ---------------------------------------------------------------- Paragon Unlimited
    def _voices(self):
        if self.game != Game.FE13 or self.service is None:
            return None
        svc = getattr(self.service, "pu_voices", None)
        if svc is None:
            try:
                from paragon.unlimited.dialogue.voices import FE13Voices

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
