"""Offscreen Qt test for Paragon Unlimited v1.3: Check My Mod, Copy to Azahar, New Character
dialog, conversation preview with voices, hair color in the 3D preview. No game files."""
import os
import sys
import tempfile
import types

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.chdir(os.path.join(os.path.dirname(__file__), ".."))

from PySide6.QtWidgets import QApplication, QMessageBox

OUT = "qt_out"


def check(cond, msg):
    if not cond:
        raise AssertionError(msg)


class Node:
    def __init__(self, rid):
        self.rid = rid


class FakeData:
    """Just enough GameData for the mod check."""

    def __init__(self):
        self.rec = {
            # FaceData
            10: dict(fsid="FSID_BU_クロム_通常", portrait_file="クロム_bu_通常.arc"),
            11: dict(fsid="FSID_BU_Test_通常", portrait_file="Missing.arc"),
            # characters
            20: dict(pid="PID_クロム", fid="FID_クロム"),
            # asset definitions
            30: dict(name="PID_クロム", head_model="uHead_M_c001", body_model="uBody_nope"),
        }
        self.lists = {("facedata", "portraits"): [10, 11], ("characters", "people"): [20], ("asset_definitions", "specs"): [30]}
        self.files = {"face/クロム_bu_通常.arc", "b/uHead_M_c001.m.lz"}
        self.messages = {
            "m/E/Test.bin.lz": {
                "MID_OK": "$Wmクロム|3$Wsクロム|$E笑,汗|Fine.$k",
                "MID_BAD": "$Wmクロム|3$Wsクロム|$E悲しみ|Oops.$k$SvpSE_VOICE_NOPE|",
            }
        }

    def node(self, node_id):
        return Node(node_id) if any(k[0] == node_id for k in self.lists) else None

    def list_size(self, rid, field):
        return len(self.lists[(rid, field)])

    def list_get(self, rid, field, i):
        return self.lists[(rid, field)][i]

    def string(self, rid, field):
        return self.rec.get(rid, {}).get(field)

    def key_to_rid(self, table, key):
        for rid, r in self.rec.items():
            if key in (r.get("fsid"), r.get("pid")):
                return rid
        return None

    def file_exists(self, path, localized):
        return path in self.files

    def read_arc(self, path):
        return {k + ".ctpk.lz": b"" for k in ("通常", "笑", "怒", "苦", "キメ", "頬", "汗")}

    def enumerate_text_archives(self):
        return list(self.messages)

    def open_text_data(self, path, localized):
        pass

    def enumerate_messages(self, path, localized):
        return list(self.messages[path])

    def message(self, path, localized, key):
        return self.messages[path][key]


class FakeVoices:
    def __init__(self):
        self.played = []

    def all_voices(self):
        return ["SE_VOICE_CHROM_EVT_2", "SE_VOICE_PLAYER_M1_EVT_1"]

    def has(self, name):
        return name in self.all_voices()

    def play(self, name):
        self.played.append(name)

    def duration(self, name):
        return 0.2

    def stop(self):
        pass


def test_mod_check(app):
    from paragon.core.services.fe13_mod_check import ModChecker
    from paragon.ui.controllers.pu_mod_check_dialog import ModCheckDialog

    data = FakeData()
    issues = ModChecker(data, FakeVoices()).run()
    text = "\n".join(f"{i.severity} {i.category} {i.where} {i.message}" for i in issues)
    check("悲しみ" in text and "error Dialogue" in text, text)
    check("Missing.arc does not exist" in text, text)
    check("SE_VOICE_NOPE" in text, text)
    check("body model b/uBody_nope.m.lz" in text, text)
    check("MID_OK" not in text, "blush+sweat and smile exist")
    check(ModChecker(data, FakeVoices())._voice_exists("SE_VOICE_PLAYER_M#_EVT_1", set(FakeVoices().all_voices())), "wildcard voice")

    gs = types.SimpleNamespace(data=data, dialogue=types.SimpleNamespace(pu_voices=FakeVoices()))
    dlg = ModCheckDialog(gs)
    dlg.show()
    dlg.run()
    check(dlg.table.rowCount() == len(dlg.issues) and dlg.errors(), (dlg.table.rowCount(), dlg.issues))
    dlg.filter.setCurrentIndex(1)
    check(dlg.table.rowCount() == len(dlg.errors()), "errors filter")
    dlg.grab().save(os.path.join(OUT, "v13_mod_check.png"))
    dlg.close()
    print("mod check: ok")


def test_azahar(tmp):
    from paragon.core.services import pu_azahar as az

    out = os.path.join(tmp, "out")
    mods = os.path.join(tmp, "mods")
    os.makedirs(os.path.join(out, "data"))
    os.makedirs(os.path.join(mods, az.BASE_TITLE, "romfs", "data"))
    open(os.path.join(out, "data", "a.bin"), "w").write("new")
    open(os.path.join(mods, az.BASE_TITLE, "romfs", "data", "a.bin"), "w").write("old")
    open(os.path.join(mods, az.BASE_TITLE, "romfs", "keep.bin"), "w").write("keep")
    res = az.copy_to_mods(out, os.path.join(mods, az.BASE_TITLE, "romfs"), backups_dir=os.path.join(tmp, "Backups"))
    check(res.copied == ["data/a.bin"] and res.backup, res.summary())
    check(open(os.path.join(mods, az.BASE_TITLE, "romfs", "data", "a.bin")).read() == "new", "copied")
    check(os.path.exists(os.path.join(mods, az.BASE_TITLE, "romfs", "keep.bin")), "nothing deleted")
    res = az.copy_to_mods(out, mods, backups_dir=os.path.join(tmp, "Backups"))
    check(not res.copied and res.unchanged == 1, res.summary())
    print("copy to Azahar: ok")


def test_player(app):
    from paragon.core.dialogue.pretty_script_parser import PrettyScriptParser, DialogueInterpreterState
    from paragon.ui.controllers.dialogue_player import DialoguePlayer
    from paragon.model.game import Game

    text = (
        "$LoadAssets(クロム, 3)\n$SetSpeaker(クロム)\n$PlayVoice(SE_VOICE_CHROM_EVT_2)\n$Emotions(通常)\nHello.\n$Pause\n\n"
        "$Clear\n$LoadAssets(リズ, 7)\n$SetSpeaker(リズ)\nHi!\n$Pause\n"
    )
    state = DialogueInterpreterState(None)
    for c in PrettyScriptParser().scan(text):
        c.interpret(state)
    state.commit()
    check([s.voices for s in state.snapshots] == [["SE_VOICE_CHROM_EVT_2"], []], [s.voices for s in state.snapshots])

    voices = FakeVoices()
    service = types.SimpleNamespace(pu_voices=voices, data=None)
    player = DialoguePlayer()
    player.set_service(service, None)
    player.game = Game.FE13
    player.set_snapshots(state.snapshots)
    player._set_current(0)
    check(voices.played == ["SE_VOICE_CHROM_EVT_2"], voices.played)
    player.play_button.setChecked(True)
    check(player.timer.isActive(), "auto-advance scheduled")
    player._on_tick()
    check(player.current == 1, player.current)
    check(not player.play_button.isChecked(), "stops at the end")
    player.zoom_box.setCurrentIndex(1)
    check(player.view.width() == 800, player.view.width())
    print("conversation preview: ok")


def test_hair_tint(app):
    from paragon.ui.controllers.auto.fe13_asset_preview import FE13AssetPreview

    class Data:
        def string(self, rid, f):
            return {"name": "PID_Test", "fid": "FID_Test"}.get(f)

        def key_to_rid(self, table, key):
            return 1

        def bytes(self, rid, f):
            return bytes([0xC0, 0x30, 0x30, 0xFF])

    gs = types.SimpleNamespace(data=Data())
    w = FE13AssetPreview(types.SimpleNamespace(main_state=None, game_state=gs))
    check(w.character_hair_color(1) == "#c03030", w.character_hair_color(1))
    gray = (8, 8, bytes([128, 128, 128, 255]) * 64)
    tinted = w._tinted(gray, "#c03030")
    check(tinted[2][0] > tinted[2][1] + 40, tinted[2][:4])
    colored = (8, 8, bytes([200, 60, 60, 255]) * 64)
    check(w._tinted(colored, "#3030c0") == colored, "already colored hair is left alone")
    print("hair color: ok")


def test_new_character_dialog(app):
    from paragon.ui.controllers.pu_new_character_dialog import NewCharacterDialog

    class Data:
        def table(self, name):
            return (1, "people")

        def items(self, rid, field):
            return [5, 6]

        def string(self, rid, f):
            return {5: {"pid": "PID_リズ", "name": "MPID_リズ"}, 6: {"pid": "PID_クロム", "name": "MPID_クロム"}}[rid].get(f)

        def message(self, path, localized, key):
            return {"MPID_リズ": "Lissa", "MPID_クロム": "Chrom"}.get(key)

        def key_to_rid(self, table, key):
            return {"PID_リズ": 5, "PID_クロム": 6}.get(key)

    gs = types.SimpleNamespace(data=Data(), portraits=None)
    dlg = NewCharacterDialog(gs)
    check(dlg.template.currentData() == "PID_リズ", dlg.template.currentData())
    check("Lissa" in dlg.template.currentText(), dlg.template.currentText())
    dlg.ident.setText("Gisselle")
    check(dlg.name.text() == "Gisselle", "name follows the ID")
    from paragon.core.services import fe13_new_character as nc

    check(nc.validate(gs.data, dlg.request()) is None, nc.validate(gs.data, dlg.request()))
    dlg.ident.setText("Gis selle")
    check(nc.validate(gs.data, dlg.request()), "bad ID rejected")
    dlg.ident.setText("Gisselle")
    dlg.grab().save(os.path.join(OUT, "v13_new_character.png"))
    print("new character dialog: ok")


def main():
    app = QApplication.instance() or QApplication([])
    QMessageBox.warning = staticmethod(lambda *a, **k: QMessageBox.Ok)
    QMessageBox.information = staticmethod(lambda *a, **k: QMessageBox.Ok)
    os.makedirs(OUT, exist_ok=True)
    test_mod_check(app)
    with tempfile.TemporaryDirectory() as tmp:
        test_azahar(tmp)
    test_player(app)
    test_hair_tint(app)
    test_new_character_dialog(app)
    print("v1.3 Qt test: all checks passed")


if __name__ == "__main__":
    main()
