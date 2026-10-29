"""Offscreen Qt test for Paragon Unlimited v1.4: help (per-window topics, F1, acknowledgments)
and the unsaved-changes tracker. No game files."""
import os
import sys
import types

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.chdir(os.path.join(os.path.dirname(__file__), ".."))

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication, QWidget

OUT = "qt_out"


def check(cond, msg):
    if not cond:
        raise AssertionError(msg)


def test_help(app):
    from paragon.ui import pu_help

    topics = pu_help.load_topics("FE13")
    for needed in ("main", "characters", "facedata", "assets", "dialogue", "chapters"):
        check(needed in topics, f"topic {needed} missing")
    html = pu_help.topic_html("dialogue")
    check("$PlayVoice" in html and "$LoadAssets" in html and "通常" in html, "commands and emotions listed")
    check("{{" not in html, "placeholders filled")
    check("text box" in pu_help.topic_html("facedata"), "FaceData explains the text box")
    check("Sprite Data" in pu_help.topic_html("characters"), "characters explain sprite data")

    w = QWidget()
    w._pu_help_topic = "facedata"
    check(pu_help.topic_for_window(w) == "facedata", pu_help.topic_for_window(w))
    w2 = QWidget()
    pu_help.add_help_action(w2, "some_node_without_help", "ComboTbl")
    check(pu_help.topic_for_window(w2) == "assets", pu_help.topic_for_window(w2))

    class DialogueEditor(QWidget):
        pass

    check(pu_help.topic_for_window(DialogueEditor()) == "dialogue", "class name lookup")
    check(pu_help.topic_for_window(QWidget()) == "main", "fallback")

    main = QWidget()
    m = pu_help.install("FE13", main)
    editor = QWidget()
    editor._pu_help_topic = "characters"
    editor.show()
    m.last_window = editor
    m.show_for_last()
    check(m.dialog.isVisible(), "help shown")
    check("Characters" in m.dialog.text.toPlainText(), m.dialog.text.toPlainText()[:80])
    m.dialog.grab().save(os.path.join(OUT, "v14_help_characters.png"))
    handled = m.eventFilter(editor, QKeyEvent(QEvent.KeyPress, Qt.Key_F1, Qt.NoModifier))
    check(handled, "F1 handled")
    m.show_acknowledgments()
    check(m.dialog.tabs.currentIndex() == 1, "acknowledgments tab")
    m.dialog.grab().save(os.path.join(OUT, "v14_acknowledgments.png"))
    m.show_topics()
    check(m.dialog.tabs.currentIndex() == 0 and "Getting started" in m.dialog.text.toPlainText(), "topics")
    m.dialog.close()
    print("help: ok")


def test_tracker():
    from paragon.core.pu_change_tracker import TrackedGameData, has_unsaved_changes, mark_saved

    class Raw:
        def __init__(self):
            self.v = {(1, "level"): 3}
            self.msgs = {"MPID_A": "A"}

        def int(self, rid, f):
            return self.v.get((rid, f))

        def set_int(self, rid, f, value):
            self.v[(rid, f)] = value

        def message(self, path, loc, key):
            return self.msgs.get(key)

        def set_message(self, path, loc, key, value):
            self.msgs[key] = value

        def list_add(self, rid, f):
            return 99

        def set_store_dirty(self, s, d):
            pass

    gd = TrackedGameData(Raw())
    gs = types.SimpleNamespace(data=gd, portraits=types.SimpleNamespace(pu_edits=None))
    gd.set_int(1, "level", 3)
    check(not has_unsaved_changes(gs), "same value is not a change")
    gd.set_message("m", True, "MPID_A", "A")
    check(not has_unsaved_changes(gs), "same text is not a change")
    gd.set_int(1, "level", 4)
    check(has_unsaved_changes(gs), "change noticed")
    mark_saved(gs)
    check(not has_unsaved_changes(gs), "saved")
    gd.list_add(1, "x")
    check(has_unsaved_changes(gs), "list change noticed")
    mark_saved(gs)
    gd.set_store_dirty("characters", False)
    check(not has_unsaved_changes(gs), "marking clean is not a change")
    pending = types.SimpleNamespace(has_pending=lambda: True)
    gs.portraits.pu_edits = pending
    check(has_unsaved_changes(gs), "pending portrait edits count")
    print("unsaved changes: ok")


def main():
    app = QApplication.instance() or QApplication([])
    os.makedirs(OUT, exist_ok=True)
    test_help(app)
    test_tracker()
    print("v1.4 Qt test: all checks passed")


if __name__ == "__main__":
    main()
