import logging
import re
import traceback

from PySide6 import QtGui, QtCore
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QCheckBox, QInputDialog, QMessageBox

from paragon.model.game import Game

from paragon.core.scanner import ScannerError
from paragon.ui.controllers.dialogue_assets_dialog import DialogueAssetsDialog
from paragon.ui.controllers.dialogue_emotions_dialog import DialogueEmotionsDialog
from paragon.ui.controllers.error_dialog import ErrorDialog
from paragon.ui.views.ui_dialogue_editor import Ui_DialogueEditor, DialogueCompleter


# Paragon Unlimited: the "Auto line breaks" choice, shared by every conversation editor window.
_AUTO_BREAKS = {"on": True}


class DialogueEditor(Ui_DialogueEditor):
    def __init__(self, data, service, sprite_animation_svc, game):
        super().__init__()
        self.data = data
        self.service = service
        self.sprite_animation_svc = sprite_animation_svc
        self.path = None
        self.localized = None
        self.message = None
        self.error_dialog = None
        self.assets_dialog = None
        self.emotions_dialog = None
        self.game = game
        self._wrap_metrics = None
        self._wrap_busy = False
        self.auto_break_check = None

        self.setWindowTitle("Paragon")

        self.keys_box.setCurrentIndex(-1)

        backgrounds = self.service.backgrounds()
        windows = self.service.windows()

        self.player.set_backgrounds(backgrounds)
        self.player.set_game(game)
        self.player.set_windows(windows)
        self.player.set_service(self.service, sprite_animation_svc)

        self.editor.set_service(service)
        self.editor.set_completer(DialogueCompleter())

        self.player.redraw()
        self.refresh_buttons()

        self.keys_box.currentIndexChanged.connect(self._on_selection)
        self.preview_button.clicked.connect(self._on_save_and_preview)
        self.new_button.clicked.connect(self._on_new)
        self.delete_button.clicked.connect(self._on_delete)
        self.rename_button.clicked.connect(self._on_rename)
        self.view_assets_action.triggered.connect(self.show_assets_dialog)
        self.view_emotions_action.triggered.connect(self.show_emotions_dialog)
        self.editor.cursorPositionChanged.connect(self._on_cursor_position_changed)
        self.editor.lostFocus.connect(self._on_lost_focus)
        self._pu_setup_line_breaks()
        self._pu_setup_speaker_lines()

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
            from paragon.core.services import fe13_text_wrap

            self._wrap_metrics = fe13_text_wrap.metrics_for(self.data)
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
        from paragon.core.services import fe13_text_wrap as tw

        text = self.editor.toPlainText()[:position]
        return tw.limit_for(tw.conversation_type_before(text))

    def _on_text_changed_wrap(self):
        """While typing: move the word that no longer fits to a new line."""
        if self._wrap_busy or not self._wrap_on():
            return
        from paragon.core.services import fe13_text_wrap as tw

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
        from paragon.core.services import fe13_text_wrap as tw

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

    def set_archive(self, path, localized):
        self.keys_box.clear()
        self.path = path
        self.localized = localized
        if not path:
            self.setWindowTitle("Paragon")
        else:
            self.setWindowTitle("Paragon - " + path)
            self.data.open_text_data(path, localized)
            keys = self.data.enumerate_messages(path, localized)
            for key in keys:
                self.keys_box.addItem(key)
        self.refresh_buttons()

    def event(self, e: QtCore.QEvent):
        if e.type() == QtCore.QEvent.WindowActivate:
            self.editor.refresh_completion_lists()
            return True
        else:
            return super(DialogueEditor, self).event(e)

    def refresh_buttons(self):
        has_selection = self._has_valid_selection()
        self.new_button.setEnabled(self.path is not None)
        self.preview_button.setEnabled(has_selection)
        self.delete_button.setEnabled(has_selection)
        self.rename_button.setEnabled(has_selection)

    def show_assets_dialog(self):
        if not self.assets_dialog:
            self.assets_dialog = DialogueAssetsDialog(self.service)
        self.assets_dialog.show()

    def show_emotions_dialog(self):
        if not self.emotions_dialog:
            self.emotions_dialog = DialogueEmotionsDialog(self.service)
        self.emotions_dialog.show()

    def _select_line(self, line):
        doc = self.editor.document()
        block = doc.findBlockByLineNumber(line)
        if block:
            cursor = QTextCursor(block)
            cursor.select(QtGui.QTextCursor.LineUnderCursor)
            self.editor.setTextCursor(cursor)

    def _on_cursor_position_changed(self):
        block = self.editor.textCursor().blockNumber() + 1
        pos = self.editor.textCursor().positionInBlock() + 1
        text = f"{block} : {pos}"
        if self._wrap_metrics:
            from paragon.core.services import fe13_text_wrap as tw

            cursor = self.editor.textCursor()
            line = cursor.block().text()
            if tw.is_text_line(line):
                width = tw.line_width(line, cursor.positionInBlock(), self._wrap_metrics)
                limit = self._wrap_limit(cursor.block().position())
                text += f"    line width {width} / {limit} px"
                self.cursor_position_label.setStyleSheet("color: #c0392b;" if width > limit else "")
            else:
                self.cursor_position_label.setStyleSheet("")
        self.cursor_position_label.setText(text)

    def _on_selection(self):
        if self._has_valid_selection():
            key = self.keys_box.currentText()
            value = self.data.message(self.path, self.localized, key)
            pretty = self.service.game_to_pretty(value)
            self.editor.setPlainText(pretty)
        else:
            self.editor.setPlainText("")
        self._preview()
        self.refresh_buttons()

    def _on_save_and_preview(self):
        if self._has_valid_selection():
            self._preview()

    def _on_lost_focus(self):
        if self.isActiveWindow() and self._has_valid_selection():
            self._save()

    def _preview(self):
        try:
            self._wrap_whole_text()
            text = self.editor.toPlainText()
            snapshots = self.service.interpret(text)
            self.player.set_snapshots(snapshots)
            return True
        except ScannerError as e:
            self.error_dialog = ErrorDialog(str(e))
            self.error_dialog.show()
            self._select_line(e.line - 1)
        except Exception as e:
            logging.exception("Previewing failed.")
            trace = traceback.format_exception(type(e), e, e.__traceback__)
            self.error_dialog = ErrorDialog("".join(trace))
            self.error_dialog.show()
        return False

    def _save(self):
        try:
            self._wrap_whole_text()
            text = self.editor.toPlainText()
            game_text = self.service.pretty_to_game(text)
            original = self.data.message(
                self.path, self.localized, self.keys_box.currentText()
            )
            if original != game_text:
                self.data.set_message(
                    self.path, self.localized, self.keys_box.currentText(), game_text
                )
                self.status_bar.showMessage(
                    f"Saved changes to message {self.keys_box.currentText()}", 5000
                )
        except ScannerError as e:
            self.error_dialog = ErrorDialog(str(e))
            self.error_dialog.show()
            self._select_line(e.line - 1)
        except Exception as e:
            logging.exception("Previewing failed.")
            trace = traceback.format_exception(type(e), e, e.__traceback__)
            self.error_dialog = ErrorDialog("".join(trace))
            self.error_dialog.show()

    def _on_new(self):
        if not self.path:
            return

        # TODO: Validate naming scheme?
        choice, ok = QInputDialog.getText(self, "Enter Key", "Key")
        if ok:
            self.data.set_message(
                self.path,
                self.localized,
                choice,
                "This is a placeholder message.\\nSee the guide for info on formatting.",
            )
            self.keys_box.addItem(choice)
            self.keys_box.setCurrentIndex(self.keys_box.count() - 1)

    def _on_delete(self):
        if self._has_valid_selection():
            key = self.keys_box.currentText()
            self.data.set_message(self.path, self.localized, key, None)
            self.keys_box.removeItem(self.keys_box.currentIndex())

    def _on_rename(self):
        if self._has_valid_selection():
            choice, ok = QInputDialog.getText(
                self, "Enter Key", "Key", text=self.keys_box.currentText()
            )
            if ok:
                # Verify that the key is unique.
                if not self._key_is_unique(choice):
                    self.message = QMessageBox()
                    self.message.setText(f"The key {choice} is already in use.")
                    self.message.exec_()
                    return
                key = self.keys_box.currentText()
                value = self.data.message(self.path, self.localized, key)
                self.data.set_message(self.path, self.localized, choice, value)
                self.data.set_message(self.path, self.localized, key, None)
                self.keys_box.setItemText(self.keys_box.currentIndex(), choice)

    def _key_is_unique(self, key) -> bool:
        return key not in self.data.enumerate_messages(self.path, self.localized)

    def _has_valid_selection(self):
        return bool(self.path and self.keys_box.currentText())
