"""Paragon Unlimited: additions to the conversation editor (FE13).

- Auto line breaks: a line that gets too wide for the game's text box continues on a new line.
- Pressing Enter after $SetSpeaker(...) adds the speaker's $Emotions and $PlayVoice lines.
"""
import logging
import re
from PySide6 import QtCore
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QCheckBox
from paragon.model.game import Game

# Paragon Unlimited: the "Auto line breaks" choice, shared by every conversation editor window.
_AUTO_BREAKS = {"on": True}


class DialogueEditorFeatures:
    """Mixed into DialogueEditor (paragon/ui/controllers/dialogue_editor.py)."""

    # ------------------------------------------------------------------ Paragon Unlimited: speaker lines
    def _pu_setup_speaker_lines(self):
        """FE13: pressing Enter after $SetSpeaker(...) adds the speaker's $Emotions and $PlayVoice."""
        self._speaker_busy = False
        if self.game != Game.FE13:
            return
        self.editor.document().contentsChange.connect(self._on_contents_change_speaker)

    def _on_contents_change_speaker(self, position, removed, added):
        if self._speaker_busy or added != 1 or removed != 0:
            return
        doc = self.editor.document()
        if doc.characterAt(position) != "\u2029":  # a new line was typed
            return
        block = doc.findBlock(position)
        if not re.fullmatch(r"\s*\$SetSpeaker\(.+\)\s*", block.text()):
            return
        QtCore.QTimer.singleShot(0, lambda: self._add_speaker_lines(block.blockNumber()))

    def _add_speaker_lines(self, speaker_block_number):
        doc = self.editor.document()
        block = doc.findBlockByNumber(speaker_block_number)
        new_line = block.next()
        if not block.isValid() or not new_line.isValid() or new_line.text().strip():
            return
        # Leave it alone when the speaker already has these lines below.
        following = new_line.next()
        while following.isValid() and not following.text().strip():
            following = following.next()
        if following.isValid() and following.text().strip().startswith(("$Emotions", "$PlayVoice", "$Synchronize")):
            return
        lines = ["$Emotions(Standard)"]
        voice = self._first_voice_for_speaker()
        if voice:
            lines.append(f"$PlayVoice({voice})")
        self._speaker_busy = True
        try:
            cursor = QTextCursor(new_line)
            cursor.beginEditBlock()
            cursor.insertText("\n".join(lines) + "\n")
            cursor.endEditBlock()
            self.editor.setTextCursor(cursor)  # ready for the text
        finally:
            self._speaker_busy = False
        if voice:
            self.status_bar.showMessage(
                "Added $Emotions and $PlayVoice for the speaker. Change the voice line: type inside "
                "$PlayVoice( ) for the list of this character's lines.",
                8000,
            )

    def _first_voice_for_speaker(self):
        """First event voice line of the speaker at the cursor (None: no voice lines)."""
        try:
            voices = self.editor._voice_completions()
            if not voices or self.editor._current_speaker() is None:
                return None
            all_voices = None
            svc = getattr(self.service, "pu_voices", None)
            if svc is not None:
                all_voices = svc.all_voices()
            if all_voices is not None and len(voices) == len(all_voices):
                return None  # the speaker has no voice of their own; do not guess one
            events = [v for v in voices if "_EVT_" in v]
            return (events or voices)[0]
        except Exception:
            logging.exception("Could not find a voice line for the speaker.")
            return None

    # ------------------------------------------------------------------ Paragon Unlimited: line breaks
    def _pu_setup_line_breaks(self):
        """FE13: break lines automatically at the width the game's text box holds."""
        self._wrap_metrics = None
        self._wrap_busy = False
        self.auto_break_check = None
        if self.game != Game.FE13:
            return
        try:
            from paragon.unlimited.dialogue import line_breaks

            self._wrap_metrics = line_breaks.metrics_for(self.data)
        except Exception:
            logging.exception("Line breaks: could not load the letter widths.")
            return
        self.auto_break_check = QCheckBox("Auto line breaks")
        self.auto_break_check.setChecked(_AUTO_BREAKS["on"])
        self.auto_break_check.setToolTip(
            "Starts a new line (\\n) when the text would be wider than the game's text box,\n"
            "before the word that does not fit. Measured with the game's own font: supports\n"
            "and most cutscenes hold 320 pixels per line (about 40-48 letters), 2 lines per box.\n"
            "When saving, a box that would get a third line continues in a new box ($Pause $Clear)."
        )
        self.auto_break_check.toggled.connect(self._on_auto_break_toggled)
        self.status_bar.addPermanentWidget(self.auto_break_check)
        self.editor.textChanged.connect(self._on_text_changed_wrap)

    def _wrap_on(self) -> bool:
        return bool(self._wrap_metrics and self.auto_break_check and self.auto_break_check.isChecked())

    def _on_auto_break_toggled(self, on):
        _AUTO_BREAKS["on"] = bool(on)
        self._on_cursor_position_changed()

    def _wrap_limit(self, position) -> int:
        from paragon.unlimited.dialogue import line_breaks as tw

        text = self.editor.toPlainText()[:position]
        return tw.limit_for(tw.conversation_type_before(text))

    def _on_text_changed_wrap(self):
        """While typing: move the word that no longer fits to a new line."""
        if self._wrap_busy or not self._wrap_on():
            return
        from paragon.unlimited.dialogue import line_breaks as tw

        cursor = self.editor.textCursor()
        block = cursor.block()
        line = block.text()
        if not tw.is_text_line(line):
            return
        try:
            spot = tw.live_break(line, cursor.positionInBlock(), self._wrap_metrics, self._wrap_limit(block.position()))
        except Exception:
            logging.exception("Line breaks: could not measure the line.")
            return
        if not spot:
            return
        self._wrap_busy = True
        try:
            edit = QTextCursor(block)
            edit.setPosition(block.position() + spot[0])
            edit.setPosition(block.position() + spot[1], QTextCursor.MoveMode.KeepAnchor)
            edit.insertText("\\n\n")
        finally:
            self._wrap_busy = False

    def _wrap_whole_text(self) -> int:
        """Before saving / previewing: add the line breaks the whole message needs."""
        if not self._wrap_on():
            return 0
        from paragon.unlimited.dialogue import line_breaks as tw

        text = self.editor.toPlainText()
        try:
            wrapped, count = tw.wrap_pretty_text(text, self._wrap_metrics)
        except Exception:
            return 0  # The normal save reports script errors.
        if count and wrapped != text:
            line = self.editor.textCursor().blockNumber()
            scroll = self.editor.verticalScrollBar().value()
            self._wrap_busy = True
            try:
                cursor = QTextCursor(self.editor.document())
                cursor.select(QTextCursor.SelectionType.Document)
                cursor.insertText(wrapped)  # one undo step
            finally:
                self._wrap_busy = False
            block = self.editor.document().findBlockByNumber(min(line, self.editor.document().blockCount() - 1))
            self.editor.setTextCursor(QTextCursor(block))
            self.editor.verticalScrollBar().setValue(scroll)
            self.status_bar.showMessage(f"Added {count} line break(s) so the text fits the text box.", 6000)
        return count
