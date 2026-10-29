"""Paragon Unlimited v1.7: automatic line breaks in FE13 conversations (pixel widths of the
game font). Core checks use the built-in letter widths (no game files); the Qt part types into
a real conversation editor (offscreen)."""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.chdir(os.path.join(os.path.dirname(__file__), ".."))

from paragon.core.dialogue import convert
from paragon.core.services import fe13_text_wrap as tw


def check(cond, msg):
    if not cond:
        raise AssertionError(msg)


M = tw.Metrics.built_in()


def lines_of(game_text):
    """[(width, text)] of every printed line (avatar = AVATAR_WIDTH)."""
    from paragon.core.dialogue import commands as C
    from paragon.core.dialogue.game_script_parser import GameScriptParser

    out, buf = [], ""
    for c in GameScriptParser().scan(game_text) + [C.PauseCommand()]:
        if isinstance(c, C.PrintCommand):
            buf += c.text
        elif isinstance(c, C.PrintAvatarCommand):
            buf += "\x01"
        elif isinstance(c, (C.NewlineCommand, C.PauseCommand, C.ClearCommand)):
            if buf:
                out.append((M.text(buf.replace("\x01", "")) + buf.count("\x01") * tw.AVATAR_WIDTH, buf))
            buf = ""
    return out


def test_metrics():
    check(M.char("i") == 4 and M.char("W") == 13 and M.char(" ") == 5, (M.char("i"), M.char("W")))
    check(M.text("Chrom") == 11 + 8 + 6 + 9 + 12, M.text("Chrom"))
    check(M.char("あ") == 14, "CJK default width")
    check(tw.limit_for(1) == 320 and tw.limit_for(0) == 285 and tw.limit_for(None) == 312, "limits")
    print("metrics: ok")


def test_wrap():
    # Text that fits is left exactly as it is.
    fits = "$t1$Wmクロム|3$w0|$Wsクロム|$WaSomething on your mind? Or are you just\\nsighing for the sheer joy of it?$k"
    check(tw.wrap_game_text(fits, M) == (fits, 0), "unchanged")

    long = (
        "$t1$Wmカミラ|3$w0|$Wsカミラ|$WaOh, darling, there you are. I was starting to think you had "
        "forgotten all about your poor big sister, and that simply will not do. Come here and let "
        "me look at you, $Nu.$k"
    )
    out, n = tw.wrap_game_text(long, M)
    check(n >= 2, n)
    for w, text in lines_of(out):
        check(w <= 320, (w, text))
    check("$k$p" in out, "third line goes to a new box: " + out)
    check(out.count("\\n") >= 1, out)
    # Breaks go between words, never inside one.
    words = lambda s: s.replace("\\n", " ").replace("$k$p", " ").split()
    check(words(out) == words(long), "same words")
    check(out.split("$k$p")[0].count("\\n") == 1, "2 lines per box")

    # A typed third line only becomes a new box when text follows it.
    trailing = "$t1$Wsクロム|$WaTake out all the soldiers first!\\nWe'll deal with the Mad King later!\\n$k"
    check(tw.wrap_game_text(trailing, M)[1] == 0, "empty third line left alone")
    three = "$t1$Wsクロム|$WaOne.\\nTwo.\\nThree.$k"
    out3, n3 = tw.wrap_game_text(three, M)
    check(out3.endswith("One.\\nTwo.$k$pThree.$k") and n3 == 1, out3)

    # Map boxes ($t0) are narrower.
    t0 = "$t0$Wsクロム|$Wa" + "word " * 60 + "$k"
    for w, text in lines_of(tw.wrap_game_text(t0, M)[0]):
        check(w <= 285, (w, text))

    # Gender text counts as its wider choice; one word longer than a line is split by letters.
    g = "$t1$Wsクロム|$Wa" + "x" * 80 + "$k"
    for w, text in lines_of(tw.wrap_game_text(g, M)[0]):
        check(w <= 320, (w, text))

    # The editor's text format.
    pretty = convert.game_to_pretty(long)
    wrapped, n2 = tw.wrap_pretty_text(pretty, M)
    check(n2 == n and convert.pretty_to_game(wrapped) == out, "pretty text wraps the same")
    print("wrap: ok")


def test_live():
    line = "Oh, darling, there you are. I was starting to think"
    check(tw.line_width(line, len(line), M) == M.text(line), "line width")
    spot = tw.live_break(line, len(line), M, 320)
    check(spot is not None and line[: spot[0]] == "Oh, darling, there you are. I was starting to", spot)
    check(tw.live_break("Short line.", 5, M, 320) is None, "fits")
    two = "First part fits nicely.\\nOh, darling, there you are. I was starting to think"
    spot = tw.live_break(two, len(two), M, 320)
    check(spot and two[spot[0] - 2 : spot[0]] == "to", spot)
    check(tw.live_break(two, 3, M, 320) is None, "the other line fits")
    check(tw.line_width("Hello, $Nu!", 9, M) == M.text("Hello, !") + tw.AVATAR_WIDTH, "avatar")
    check(tw.is_text_line("Hello") and not tw.is_text_line("$Pause") and tw.is_text_line("$Nu, hi"), "text lines")
    check(tw.conversation_type_before("$SetConversationType(0)\nx\n$SetConversationType(1)\n") == 1, "type")
    print("typing: ok")


class FakeData:
    def read_file(self, path):
        raise FileNotFoundError(path)


def test_editor(app):
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QTextCursor
    from PySide6.QtTest import QTest

    from paragon.model.game import Game
    from paragon.ui.controllers.dialogue_editor import DialogueEditor
    from paragon.ui.views.ui_dialogue_editor import Ui_DialogueEditor

    ed = DialogueEditor.__new__(DialogueEditor)
    Ui_DialogueEditor.__init__(ed)
    ed.data = FakeData()
    ed.game = Game.FE13
    ed._wrap_metrics = None
    ed._wrap_busy = False
    ed.auto_break_check = None
    ed.editor.cursorPositionChanged.connect(ed._on_cursor_position_changed)
    ed._pu_setup_line_breaks()
    check(ed.auto_break_check is not None and ed.auto_break_check.isChecked(), "checkbox")
    check(ed._wrap_metrics.source == "built-in table", ed._wrap_metrics.source)

    ed.editor.setPlainText("$SetConversationType(1)\n$SetSpeaker(カミラ)\n")
    ed.editor.moveCursor(QTextCursor.MoveOperation.End)
    ed.show()
    ed.editor.setFocus()
    QTest.keyClicks(ed.editor, "Oh, darling, there you are. I was starting to think you had")
    text = ed.editor.toPlainText()
    check("I was starting to\\n\nthink you had" in text, text)
    check(ed.editor.textCursor().block().text() == "think you had", "cursor on the new line")
    check("line width" in ed.cursor_position_label.text(), ed.cursor_position_label.text())

    # Off: no breaks while typing.
    ed.auto_break_check.setChecked(False)
    QTest.keyClicks(ed.editor, " forgotten all about your poor big sister and that will not do")
    check(ed.editor.toPlainText().count("\\n") == 1, "off")
    ed.auto_break_check.setChecked(True)
    check(ed._wrap_whole_text() >= 1, "whole text on save")
    for w, t in lines_of(convert.pretty_to_game(ed.editor.toPlainText())):
        check(w <= 320, (w, t))
    os.makedirs("qt_out", exist_ok=True)
    ed.resize(1000, 500)
    ed.grab().save("qt_out/v17_line_breaks.png")
    ed.close()
    print("editor: ok")


def main():
    test_metrics()
    test_wrap()
    test_live()
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    test_editor(app)
    print("v1.7 line breaks test: all checks passed")


if __name__ == "__main__":
    main()
