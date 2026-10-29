"""Offscreen Qt test for Paragon Unlimited v1.5: FaceData Reset goes back to the game's original
position (also after a saved move), and the unsaved-changes question on closing. No game files."""
import os
import sys
import tempfile
import types

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.chdir(os.path.join(os.path.dirname(__file__), ".."))

from PIL import Image, ImageDraw
from PySide6.QtWidgets import QApplication, QLineEdit, QWidget, QVBoxLayout

from paragon import paragon as pgn

OUT = "qt_out"


def check(cond, msg):
    if not cond:
        raise AssertionError(msg)


def figure(size, color):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    s = size / 256
    d.ellipse([90 * s, 40 * s, 170 * s, 130 * s], fill=color + (255,))
    d.rectangle([60 * s, 130 * s, 200 * s, 250 * s], fill=(80, 80, 140, 255))
    d.ellipse([105 * s, 80 * s, 113 * s, 88 * s], fill=(0, 0, 0, 255))
    return img.tobytes()


def test_reset():
    from paragon.core.services import fe13_portrait_shift as ps

    lz = lambda b: bytes(pgn.compress_lz13(b))
    w = 256
    pics = {
        "通常": figure(w, (240, 200, 170)),
        "笑": figure(w, (250, 190, 160)),
        "反通常": figure(w, (230, 210, 180)),
    }
    original_entries = ps.sort_entries([(k + ps.ENTRY_SUFFIX, 0, lz(ps.new_ctpk(w, w, v))) for k, v in pics.items()])
    original = {n: b for n, _i, b in original_entries}

    # the game's file on disk, for read_original_arc
    with tempfile.TemporaryDirectory() as rom:
        os.makedirs(os.path.join(rom, "face"))
        with open(os.path.join(rom, "face", "T_bu_通常.arc"), "wb") as f:
            f.write(ps.build_arc(original_entries))
        read = ps.read_original_arc(rom, "face/T_bu_通常.arc")
        check(read is not None and set(read) == set(original), "original arc read from the game folder")
        check(ps.read_original_arc(rom, "face/New_bu_通常.arc") is None, "no original for a new file")

    # a saved move of the normal pictures by (8, -4); the reversed ones were not moved
    saved_entries, _ = ps.shift_entries(original_entries, {"normal": (8, -4)})
    saved = {n: b for n, _i, b in saved_entries}

    class FakeData:
        def read_file(self, path):
            return ps.build_arc(saved_entries)

    edits = ps.PortraitEdits(FakeData())
    edits.set("face/T_bu_通常.arc", "normal", 4, 4)  # plus an unsaved move
    res = ps.reset_to_original(edits, "face/T_bu_通常.arc", "normal", saved, original)
    check(res.restored and res.saved_shift == (8, -4), res)
    check(sorted(res.keys) == sorted(["通常", "笑"]), res.keys)
    check(edits.get("face/T_bu_通常.arc", "normal") == (0, 0), "unsaved move dropped")
    final = {n: b for n, _i, b in edits.entries("face/T_bu_通常.arc")}
    for k in ("通常", "笑", "反通常"):
        got = bytes(pgn.decompress_lz13(final[k + ps.ENTRY_SUFFIX]))
        want = bytes(pgn.decompress_lz13(original[k + ps.ENTRY_SUFFIX]))
        check(got == want, f"{k} is back to the game's picture")

    # moved down, saved, moved back up, saved: the bottom of the picture was lost; Reset brings it back
    down, _ = ps.shift_entries(original_entries, {"normal": (0, 64)})
    lost, _ = ps.shift_entries(down, {"normal": (-12, -64)})
    lost_map = {n: b for n, _i, b in lost}
    edits_l = ps.PortraitEdits(types.SimpleNamespace(read_file=lambda p: ps.build_arc(lost)))
    res = ps.reset_to_original(edits_l, "face/T_bu_通常.arc", "normal", lost_map, original)
    check(res.restored and res.saved_shift == (-12, 0), res)
    final = {n: b for n, _i, b in edits_l.entries("face/T_bu_通常.arc")}
    check(bytes(pgn.decompress_lz13(final["通常" + ps.ENTRY_SUFFIX])) == bytes(pgn.decompress_lz13(original["通常" + ps.ENTRY_SUFFIX])),
          "lost rows restored")

    # already at the original position: nothing to restore
    edits2 = ps.PortraitEdits(FakeData())
    res = ps.reset_to_original(edits2, "face/T_bu_通常.arc", "reversed", saved, original)
    check(res.restored and res.saved_shift == (0, 0) and not res.keys, res)

    # an imported (different) picture is kept
    replaced = dict(saved)
    replaced["通常" + ps.ENTRY_SUFFIX] = lz(ps.new_ctpk(w, w, Image.new("RGBA", (w, w), (10, 200, 10, 255)).tobytes()))
    edits3 = ps.PortraitEdits(FakeData())
    res = ps.reset_to_original(edits3, "face/T_bu_通常.arc", "normal", replaced, original)
    check(not res.restored and "replaced" in res.reason, res)
    check(not edits3.has_pending(), "nothing queued for an imported picture")

    # new character: no original
    res = ps.reset_to_original(ps.PortraitEdits(FakeData()), "face/T_bu_通常.arc", "normal", saved, None)
    check(not res.restored, res)
    print("reset to original: ok")


class FakeBox:
    """Stands in for QMessageBox in MainWindow._confirm_unsaved."""

    Warning = AcceptRole = DestructiveRole = Cancel = 0
    shown = []
    answer = "discard"

    def __init__(self, parent):
        self.buttons = {}
        self.detail = ""

    def setIcon(self, *_):
        pass

    setWindowTitle = setText = setInformativeText = setDefaultButton = setIcon

    def setDetailedText(self, text):
        self.detail = text

    def addButton(self, *args):
        b = object()
        self.buttons[args[0] if isinstance(args[0], str) else "Cancel"] = b
        return b

    def exec(self):
        FakeBox.shown.append(self.detail)

    def clickedButton(self):
        return self.buttons["Don't Save" if FakeBox.answer == "discard" else "Cancel"]


def test_close_question(app):
    from paragon.core.pu_change_tracker import TrackedGameData, commit_open_editors, unsaved_reasons
    from paragon.ui.controllers import main_window as mw

    class Raw:
        def __init__(self):
            self.v = {}

        def int(self, rid, f):
            return self.v.get((rid, f))

        def set_int(self, rid, f, value):
            self.v[(rid, f)] = value

    gd = TrackedGameData(Raw())
    edits = types.SimpleNamespace(has_pending=lambda: False)
    gs = types.SimpleNamespace(data=gd, portraits=types.SimpleNamespace(pu_edits=edits))
    fake = types.SimpleNamespace(gs=gs)
    old_box = mw.QMessageBox
    mw.QMessageBox = FakeBox
    try:
        check(mw.MainWindow._confirm_unsaved(fake, "closing") is True and not FakeBox.shown, "nothing unsaved: no question")

        # a portrait move that is not saved
        edits.has_pending = lambda: True
        FakeBox.answer = "cancel"
        check(mw.MainWindow._confirm_unsaved(fake, "closing") is False, "Cancel keeps the program open")
        check(FakeBox.shown and "portrait" in FakeBox.shown[-1], FakeBox.shown)
        edits.has_pending = lambda: False

        # a field edit
        gd.set_int(1, "blush_position_x", 5)
        FakeBox.answer = "discard"
        check(mw.MainWindow._confirm_unsaved(fake, "closing") is True, "Don't Save closes")
        check("game data" in FakeBox.shown[-1], FakeBox.shown[-1])

        # text still being typed is applied before the check
        gd.pu_changed = False
        win = QWidget()
        lay = QVBoxLayout(win)
        line = QLineEdit()
        other = QLineEdit()
        lay.addWidget(line)
        lay.addWidget(other)
        line.editingFinished.connect(lambda: gd.set_int(2, "name", 1))
        win.show()
        win.activateWindow()
        line.setFocus()
        app.processEvents()
        line.setText("typed")
        if app.focusWidget() is line:
            commit_open_editors()
            app.processEvents()
            check("edits to the game data (tables, text, FaceData fields...)" in unsaved_reasons(gs),
                  "typed text counted as a change")
        else:
            print("(focus not available on this platform; typed-text check skipped)")
        win.close()

        # closeEvent: a declined question keeps the window open
        class Ev:
            ignored = False

            def ignore(self):
                self.ignored = True

        ev = Ev()
        mw.MainWindow.closeEvent(types.SimpleNamespace(_confirm_unsaved=lambda doing="closing": False), ev)
        check(ev.ignored, "close is canceled")
    finally:
        mw.QMessageBox = old_box
    print("unsaved changes on close: ok")


def test_unit_info_zero_crop(app):
    """A face with Portrait Menu size 0 x 0 (common for hand-made entries): the picture is
    still shown in the unit info view, and dragging sets the game's 69 x 76."""
    sys.path.insert(0, os.path.dirname(__file__))
    import test_portrait_stage_qt as t
    from PySide6.QtCore import QPointF
    from paragon.ui.controllers.auto.fe13_portrait_stage import FE13PortraitStage, _DragItem

    data = t.FakeData()
    data.rec[2].update(portrait_menu_position_x=0, portrait_menu_position_y=0, portrait_menu_size_x=0, portrait_menu_size_y=0)
    gs = types.SimpleNamespace(data=data, portraits=t.FakePortraits())
    stage = FE13PortraitStage(types.SimpleNamespace(main_state=None, game_state=gs))
    stage.set_target(2)
    idx = [i for i in range(stage.screen_box.count()) if "Unit info" in stage.screen_box.itemText(i)][0]
    stage.screen_box.setCurrentIndex(idx)
    item = t.find(stage, _DragItem)[0]
    check(item.parentItem() is None, "the picture is not clipped to the small window")
    check(stage.scene.sceneRect().contains(item.sceneBoundingRect()), "the whole picture is in view")
    check("0 x 0" in stage.status.text(), stage.status.text())
    t.render(stage, "v15_unit_info_zero_crop")
    item.setPos(item.origin + QPointF(-20, -30))
    r = data.rec[2]
    check((r["portrait_menu_size_x"], r["portrait_menu_size_y"]) == (69, 76), r)
    check(0 <= r["portrait_menu_position_x"] <= 128 - 69 and 0 <= r["portrait_menu_position_y"] <= 128 - 76, r)
    t.render(stage, "v15_unit_info_after_drag")
    print("unit info with a 0 x 0 crop: ok")


def test_no_console():
    with open("paragon.spec", "r", encoding="utf-8") as f:
        spec = f.read()
    check("console=False" in spec, "the exe is built without a console window")
    print("no console window: ok")


def main():
    app = QApplication.instance() or QApplication([])
    os.makedirs(OUT, exist_ok=True)
    test_reset()
    test_close_question(app)
    test_unit_info_zero_crop(app)
    test_no_console()
    print("v1.5 Qt test: all checks passed")


if __name__ == "__main__":
    main()
