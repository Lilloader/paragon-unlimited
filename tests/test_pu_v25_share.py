"""Paragon Unlimited v2.2: Share My Mod (pu_share + the dialog, offscreen)."""
import os
import shutil
import sys
import tempfile
import types
import zipfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.chdir(os.path.join(os.path.dirname(__file__), ".."))

from paragon.core.services import pu_share  # noqa: E402


def check(cond, what):
    if not cond:
        raise AssertionError(what)


def write(root, rel, data):
    p = os.path.join(root, *rel.split("/"))
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "wb") as f:
        f.write(data)
    return p


def make_tree(tmp):
    rom, out, mods = os.path.join(tmp, "rom"), os.path.join(tmp, "project_output"), os.path.join(tmp, "mods")
    write(rom, "data/GameData.bin.lz", b"original game data")
    write(rom, "face/クロム_bu_通常.arc", b"chrom portrait")
    write(out, "data/GameData.bin.lz", b"changed game data")  # changed: shared
    write(out, "face/クロム_bu_通常.arc", b"chrom portrait")  # same as the game: left out
    write(out, "face/Azura_bu_通常.arc", b"new portrait")  # new: shared
    write(out, "exalt/scripts/U001.exl", b"script source")  # Paragon's own: left out
    write(out, "Thumbs.db", b"junk")
    write(out, "m/E/GameData.bin.lz.bak", b"backup")
    dlc = os.path.join(tmp, "project_output_DLC", "romfs")
    write(dlc, "E001_MAP.arc", b"dlc map")
    write(mods, "00040000000A0500/exefs/code.ips", b"PATCHcodeEOF")
    return rom, out, dlc, mods


def test_plan_and_zip(tmp):
    rom, out, dlc, mods = make_tree(tmp)
    code = pu_share.find_code_ips(mods)
    check(code and code.endswith("code.ips"), f"code.ips found: {code}")
    check(pu_share.find_code_ips(os.path.join(mods, "00040000000A0500", "romfs")) == code, "any mod folder spelling")
    p = pu_share.plan(out, rom, dlc, code, "My/Mod*")
    arcs = sorted(a for _s, a in p.files)
    check(arcs == sorted(["MyMod/0004008C000A0500/romfs/E001_MAP.arc",
                          "MyMod/00040000000A0500/exefs/code.ips",
                          "MyMod/00040000000A0500/romfs/data/GameData.bin.lz",
                          "MyMod/00040000000A0500/romfs/face/Azura_bu_通常.arc"]), arcs)
    check(p.same_as_game == 1 and p.has_dlc and p.has_code, p.summary())
    z = os.path.join(tmp, "MyMod.zip")
    pu_share.make_zip(p, z, "My/Mod*", "Andy", "Azura and Camilla join!", "2.2")
    with zipfile.ZipFile(z) as zf:
        names = zf.namelist()
        check("MyMod/HOW_TO_INSTALL.txt" in names and len(names) == 5, names)
        txt = zf.read("MyMod/HOW_TO_INSTALL.txt").decode()
        check("by Andy" in txt and "Azura and Camilla join!" in txt and "0004008C000A0500" in txt
              and "code.ips" in txt and "Open Mods Location" in txt and "2.2" in txt, txt)
        check(zf.read("MyMod/00040000000A0500/romfs/face/Azura_bu_通常.arc") == b"new portrait", "file contents")
    check(not os.path.exists(z + ".part"), "no leftover temp file")
    # nothing changed -> nothing to share
    empty = os.path.join(tmp, "empty_out")
    os.makedirs(empty)
    check(not pu_share.plan(empty, rom).files, "empty project")
    # no game folder given: everything in the output is shared (except Paragon's own files)
    check(len(pu_share.plan(out, None).files) == 3, "without the game folder")
    # remembered info
    pu_share.save_info(out, {"name": "MyMod", "author": "Andy"})
    check(pu_share.load_info(out)["author"] == "Andy", "info remembered next to the output folder")
    print("share plan / zip: ok", p.summary())


def test_dialog(tmp):
    from PySide6.QtWidgets import QApplication

    from paragon.ui.controllers.pu_share_dialog import ShareDialog

    app = QApplication.instance() or QApplication([])
    rom, out, dlc, mods = make_tree(tmp)
    gs = types.SimpleNamespace(data=None, project=types.SimpleNamespace(output_path=out, rom_path=rom))
    dlg = ShareDialog(gs, mods)
    dlg._dlc_romfs = lambda: dlc
    dlg.show()
    QApplication.processEvents()
    check(dlg.code_check.isEnabled() and dlg.code_check.isChecked(), "code.ips offered")
    dlg.name_edit.setText("Awakening Reborn")
    dlg.author_edit.setText("Andy")
    dlg.check_first.setChecked(False)
    z = dlg.make(os.path.join(tmp, "share_test"))
    check(z.endswith("share_test.zip") and os.path.isfile(z), z)
    with zipfile.ZipFile(z) as zf:
        check("Awakening Reborn/00040000000A0500/exefs/code.ips" in zf.namelist(), zf.namelist())
    check("Done" in dlg.status.text(), dlg.status.text())
    check(pu_share.load_info(out)["name"] == "Awakening Reborn", "name remembered")
    os.makedirs("qt_out", exist_ok=True)
    dlg.grab().save("qt_out/v22_share.png")
    dlg.close()
    print("share dialog: ok")


def main():
    tmp = tempfile.mkdtemp()
    try:
        os.makedirs(os.path.join(tmp, "a"))
        test_plan_and_zip(os.path.join(tmp, "a"))
        os.makedirs(os.path.join(tmp, "b"))
        test_dialog(os.path.join(tmp, "b"))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("v2.2 share test: all checks passed")


if __name__ == "__main__":
    main()
