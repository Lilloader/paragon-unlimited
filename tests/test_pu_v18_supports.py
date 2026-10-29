"""Paragon Unlimited v1.8: support slot Clear button, Assign support partners, default support
type by gender, starting text of new supports, $Emotions/$PlayVoice after $SetSpeaker.
Offscreen Qt; a small fake data layer (no game files)."""
import os
import sys
import types

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.chdir(os.path.join(os.path.dirname(__file__), ".."))

from paragon.core.services import fe13_support_tools as st


def check(cond, msg):
    if not cond:
        raise AssertionError(msg)


class FakeData:
    def __init__(self):
        self.rec = {}
        self.lists = {}
        self.next = 100
        self.dirty = set()
        self.chars_root = self._new("PersonTable", support_ex=None)
        self.lists[(self.chars_root, "people")] = []
        self.ex_root = self._new("PUSupportExTable")
        self.lists[(self.ex_root, "entries")] = []
        self.rec[self.chars_root]["support_ex"] = self.ex_root
        self.messages = {}

    def _new(self, t, **f):
        self.next += 1
        self.rec[self.next] = dict(_type=t, **f)
        return self.next

    def person(self, name, female):
        r = self._new("Person", name=name, bitflags_1=1 if female else 0)
        for k in range(52):
            self.rec[r][f"support_character_{k:03}"] = None
            self.rec[r][f"support_type_{k:03}"] = st.TYPE_NONE
        self.lists[(self.chars_root, "people")].append(r)
        return r

    def table(self, name):
        return (self.chars_root, "people") if name == "characters" else None

    def items(self, rid, f):
        return list(self.lists.get((rid, f), []))

    def list_add(self, rid, f):
        r = self._new("PUSupportEx", owner=None)
        for k in range(52, 60):
            self.rec[r][f"support_character_{k:03}"] = None
        self.lists[(rid, f)].append(r)
        return r

    def list_size(self, rid, f):
        return len(self.lists[(rid, f)])

    def type_of(self, rid):
        return self.rec[rid]["_type"]

    def rid(self, rid, f):
        return self.rec[rid].get(f)

    def set_rid(self, rid, f, v):
        self.rec[rid][f] = v

    def int(self, rid, f):
        return self.rec[rid].get(f)

    def set_int(self, rid, f, v):
        self.rec[rid][f] = v

    def display(self, rid):
        return self.rec[rid].get("name")

    def store_is_dirty(self, s):
        return s in self.dirty

    def set_store_dirty(self, s, v):
        (self.dirty.add if v else self.dirty.discard)(s)

    # messages
    def enumerate_messages(self, path, loc):
        return list(self.messages.get(path, {}))

    def message(self, path, loc, key):
        return self.messages.get(path, {}).get(key)

    def set_message(self, path, loc, key, value):
        self.messages.setdefault(path, {})[key] = value


def test_core():
    gd = FakeData()
    lucina = gd.person("Lucina", True)
    morgan = gd.person("Morgan", True)
    inigo = gd.person("Inigo", False)
    marc = gd.person("Marc", False)
    check(st.default_type(gd, lucina, morgan) == st.TYPE_NON_ROMANTIC, "two women")
    check(st.default_type(gd, inigo, marc) == st.TYPE_NON_ROMANTIC, "two men")
    check(st.default_type(gd, lucina, inigo) == st.TYPE_SLOW, "woman and man")

    assigned, full = st.assign_pairs(gd, [(morgan, lucina), (lucina, morgan), (marc, lucina)])
    check(len(assigned) == 2 and not full, (assigned, full))
    check(gd.rid(morgan, "support_character_000") == lucina and gd.rid(lucina, "support_character_000") == morgan, "both listed")
    check(gd.int(morgan, "support_type_000") == st.TYPE_NON_ROMANTIC, "type F/F")
    check(gd.rid(marc, "support_character_000") == lucina and gd.int(marc, "support_type_000") == st.TYPE_SLOW, "type F/M")
    check(gd.rid(lucina, "support_character_001") == marc, "next free slot")
    check("characters" in gd.dirty, "dirty")

    # Full list -> Unlimited slots, then nothing.
    for k in range(52):
        gd.set_rid(inigo, f"support_character_{k:03}", marc)
    k = st.add_partner(gd, inigo, lucina, st.TYPE_SLOW)
    check(k == 52, k)
    for k in range(53, 60):
        st.add_partner(gd, inigo, gd.person(f"x{k}", True), st.TYPE_SLOW)
    a2, full2 = st.assign_pairs(gd, [(inigo, morgan)])
    check(full2 and full2[0][2] == inigo, full2)

    # Clear one side / both sides.
    st.clear(gd, morgan, 0, both_sides=False)
    check(gd.rid(morgan, "support_character_000") is None and gd.int(morgan, "support_type_000") == st.TYPE_NONE, "cleared")
    check(gd.rid(lucina, "support_character_000") == morgan, "other side kept")
    st.clear(gd, marc, 0, both_sides=True)
    check(gd.rid(lucina, "support_character_001") is None, "other side cleared")
    entry = st.slot_record(gd, inigo, 52)
    st.clear(gd, entry, 52, both_sides=False)
    check(gd.rid(entry, "support_character_052") is None and st.owner_of(gd, entry) == inigo, "extra slot")
    print("core: ok")


def test_starting_text():
    check(st.names_from_archive("m/クロム_リズ.bin.lz") == ("クロム", "リズ"), "names")
    check(st.names_from_archive("m/ルキナ_クロム_親子.bin.lz") == ("ルキナ", "クロム"), "family")
    t = st.starting_text("クロム", "リズ")
    check(t == "$t1$Wmクロム|3$w0|$Wmリズ|7$Wsクロム|$E通常,|", t)
    check("$Wmusername|7" in st.starting_text("Camilla", "プレイヤー女"), "avatar")
    from paragon.core.dialogue import convert

    pretty = convert.game_to_pretty(t).strip().splitlines()
    check(
        pretty
        == [
            "$SetConversationType(1)",
            "$LoadAssets(クロム, 3)",
            "$Wait(0)",
            "$LoadAssets(リズ, 7)",
            "$SetSpeaker(クロム)",
            "$Emotions(通常)",
        ],
        pretty,
    )
    gd = FakeData()
    path = "m/クロム_リズ.bin.lz"
    gd.set_message(path, True, "MID_支援_クロム_リズ_Ｃ", st.OLD_PLACEHOLDER)
    gd.set_message(path, True, "MID_支援_クロム_リズ_Ｂ", "$t1real text$k")
    check(st.fill_new_conversations(gd, path) == 1, "only the placeholder")
    check(gd.message(path, True, "MID_支援_クロム_リズ_Ｃ") == t, "filled")
    check(gd.message(path, True, "MID_支援_クロム_リズ_Ｂ") == "$t1real text$k", "kept")
    print("starting text: ok")


def test_slot_widget(app):
    from PySide6.QtWidgets import QMessageBox, QVBoxLayout, QWidget

    from paragon.ui.controllers.auto import fe13_support_slot_tools as mod

    gd = FakeData()
    a = gd.person("Lucina", True)
    b = gd.person("Inigo", False)
    gd.set_rid(a, "support_character_003", b)
    gd.set_int(a, "support_type_003", st.TYPE_SLOW)
    gd.set_rid(b, "support_character_000", a)
    gd.set_int(b, "support_type_000", st.TYPE_SLOW)

    class Box(QWidget):
        """Stands in for the partner / type boxes of the slot."""
        from PySide6.QtCore import Signal

        currentIndexChanged = Signal(int)

        def __init__(self, field_id):
            super().__init__()
            self.field_id = field_id
            self.targets = []

        def set_target(self, rid):
            self.targets.append(rid)

    state = types.SimpleNamespace(main_state=None, game_state=types.SimpleNamespace(data=gd))
    group = QWidget()
    lay = QVBoxLayout(group)
    partner_box, type_box = Box("support_character_003"), Box("support_type_003")
    lay.addWidget(partner_box)
    lay.addWidget(type_box)
    row = QWidget()
    QVBoxLayout(row)
    w = mod.FE13SupportSlotTools(state, types.SimpleNamespace(field_id="support_character_003"))
    row.layout().addWidget(w)
    lay.addWidget(row)
    w.set_target(a)
    check(w._partner_box is partner_box and w._type_box is type_box, "siblings found")

    # Clear: answer "Clear both".
    def fake_exec(box):
        box.clickedButton = lambda: [x for x in box.buttons() if x.text() == "Clear both"][0]
        return 0

    QMessageBox.exec = fake_exec
    w.clear_button.click()
    check(gd.rid(a, "support_character_003") is None and gd.int(a, "support_type_003") == st.TYPE_NONE, "cleared")
    check(gd.rid(b, "support_character_000") is None, "both sides")
    check(type_box.targets and partner_box.targets, "boxes refreshed")

    # Picking a partner for an empty slot sets the type for the pair.
    c = gd.person("Morgan", True)
    gd.set_rid(a, "support_character_003", c)
    partner_box.currentIndexChanged.emit(1)
    check(gd.int(a, "support_type_003") == st.TYPE_NON_ROMANTIC, gd.int(a, "support_type_003"))
    gd.set_int(a, "support_type_003", 302843907)  # Fast, chosen by hand: kept
    gd.set_rid(a, "support_character_003", b)
    partner_box.currentIndexChanged.emit(2)
    check(gd.int(a, "support_type_003") == 302843907, "type chosen by hand is kept")
    print("slot tools: ok")


def test_speaker_lines(app):
    from PySide6.QtGui import QTextCursor
    from PySide6.QtTest import QTest
    from PySide6.QtCore import Qt

    from paragon.model.game import Game
    from paragon.ui.controllers.dialogue_editor import DialogueEditor
    from paragon.ui.views.ui_dialogue_editor import Ui_DialogueEditor

    ed = DialogueEditor.__new__(DialogueEditor)
    Ui_DialogueEditor.__init__(ed)
    ed.data = types.SimpleNamespace(read_file=lambda p: (_ for _ in ()).throw(FileNotFoundError(p)))
    ed.game = Game.FE13
    ed.service = types.SimpleNamespace(pu_voices=types.SimpleNamespace(all_voices=lambda: ["A", "B", "C", "D"]))
    ed._wrap_metrics = None
    ed._wrap_busy = False
    ed.auto_break_check = None
    ed._pu_setup_speaker_lines()
    ed.editor.service = types.SimpleNamespace(asset_translations=lambda: {})  # used on window activate
    ed.editor._voice_completions = lambda: ["SE_VOICE_CHROM_BATTLE_1", "SE_VOICE_CHROM_EVT_1", "SE_VOICE_CHROM_EVT_2"]
    ed.editor._current_speaker = lambda: "Chrom"
    ed.show()
    ed.editor.setFocus()
    ed.editor.setPlainText("$SetConversationType(1)\n")
    ed.editor.moveCursor(QTextCursor.MoveOperation.End)
    QTest.keyClicks(ed.editor, "$SetSpeaker(Chrom)")
    QTest.keyClick(ed.editor, Qt.Key_Return)
    QTest.qWait(50)
    text = ed.editor.toPlainText()
    check("$SetSpeaker(Chrom)\n$Emotions(Standard)\n$PlayVoice(SE_VOICE_CHROM_EVT_1)\n" in text, repr(text))
    check(ed.editor.textCursor().block().text() == "", "cursor on the text line")
    QTest.keyClicks(ed.editor, "Hello.")
    check(text.count("$Emotions") == 1, "once")

    # Speaker without own voices: only $Emotions.
    ed.editor._voice_completions = lambda: ["A", "B", "C", "D"]
    ed.editor.moveCursor(QTextCursor.MoveOperation.End)
    QTest.keyClick(ed.editor, Qt.Key_Return)
    QTest.keyClicks(ed.editor, "$SetSpeaker(Camilla)")
    QTest.keyClick(ed.editor, Qt.Key_Return)
    QTest.qWait(50)
    text = ed.editor.toPlainText()
    check(text.endswith("$SetSpeaker(Camilla)\n$Emotions(Standard)\n"), repr(text))
    # Enter on a speaker line that already has its lines: nothing added.
    cursor = ed.editor.textCursor()
    block = ed.editor.document().findBlockByNumber(1)
    cursor.setPosition(block.position() + len(block.text()))
    ed.editor.setTextCursor(cursor)
    before = ed.editor.toPlainText().count("$Emotions")
    QTest.keyClick(ed.editor, Qt.Key_Return)
    QTest.qWait(50)
    check(ed.editor.toPlainText().count("$Emotions") == before, "not added twice")
    os.makedirs("qt_out", exist_ok=True)
    ed.resize(1000, 500)
    ed.grab().save("qt_out/v18_speaker_lines.png")
    ed.close()
    print("speaker lines: ok")


def main():
    test_core()
    test_starting_text()
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    test_slot_widget(app)
    test_speaker_lines(app)
    print("v1.8 supports test: all checks passed")


if __name__ == "__main__":
    main()
