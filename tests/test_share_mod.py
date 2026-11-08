"""Share My Mod (share_mod.py + the dialog, offscreen)."""
import os
import shutil
import sys
import tempfile
import types
import zipfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.chdir(os.path.join(os.path.dirname(__file__), ".."))

from paragon.unlimited.tools import share_mod


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
    write(out, "face/Arlen_bu_通常.arc", b"new portrait")  # new: shared
    write(out, "exalt/scripts/U001.exl", b"script source")  # Paragon's own: left out
    write(out, "Thumbs.db", b"junk")
    write(out, "m/E/GameData.bin.lz.bak", b"backup")
    dlc = os.path.join(tmp, "project_output_DLC", "romfs")
    write(dlc, "E001_MAP.arc", b"dlc map")
    write(mods, "00040000000A0500/exefs/code.ips", b"PATCHcodeEOF")  # not a real patch: shared as it is
    return rom, out, dlc, mods


def test_plan_and_zip(tmp):
    rom, out, dlc, mods = make_tree(tmp)
    code = share_mod.find_code_ips(mods)
    check(code and code.endswith("code.ips"), f"code.ips found: {code}")
    check(share_mod.find_code_ips(os.path.join(mods, "00040000000A0500", "romfs")) == code, "any mod folder spelling")
    p = share_mod.plan(out, rom, dlc, code, "My/Mod*")
    arcs = sorted(a for _s, a in p.files)
    check(p.code_bytes == b"PATCHcodeEOF", "code.ips read")
    check(arcs == sorted(["MyMod/0004008C000A0500/romfs/E001_MAP.arc",
                          "MyMod/00040000000A0500/romfs/data/GameData.bin.lz",
                          "MyMod/00040000000A0500/romfs/face/Arlen_bu_通常.arc"]), arcs)
    check(p.same_as_game == 1 and p.has_dlc and p.has_code, p.summary())
    z = os.path.join(tmp, "MyMod.zip")
    share_mod.make_zip(p, z, "My/Mod*", "Lilloader", "Tessa and Arlen join!", "2.2")
    with zipfile.ZipFile(z) as zf:
        names = zf.namelist()
        check("MyMod/HOW_TO_INSTALL.txt" in names and len(names) == 5, names)
        check(zf.read("MyMod/00040000000A0500/code.ips") == b"PATCHcodeEOF", "code.ips where Azahar reads it")
        txt = zf.read("MyMod/HOW_TO_INSTALL.txt").decode()
        check("by Lilloader" in txt and "Tessa and Arlen join!" in txt and "0004008C000A0500" in txt
              and "code.ips" in txt and "Open Mods Location" in txt and "2.2" in txt, txt)
        check(zf.read("MyMod/00040000000A0500/romfs/face/Arlen_bu_通常.arc") == b"new portrait", "file contents")
    check(not os.path.exists(z + ".part"), "no leftover temp file")
    # nothing changed -> nothing to share
    empty = os.path.join(tmp, "empty_out")
    os.makedirs(empty)
    check(not share_mod.plan(empty, rom).files, "empty project")
    # no game folder given: everything in the output is shared (except Paragon's own files)
    check(len(share_mod.plan(out, None).files) == 3, "without the game folder")
    # remembered info
    share_mod.save_info(out, {"name": "MyMod", "author": "Lilloader"})
    check(share_mod.load_info(out)["author"] == "Lilloader", "info remembered next to the output folder")
    print("share plan / zip: ok", p.summary())


def test_dialog(tmp):
    from PySide6.QtWidgets import QApplication

    from paragon.unlimited.tools.share_dialog import ShareDialog

    app = QApplication.instance() or QApplication([])
    rom, out, dlc, mods = make_tree(tmp)
    # another mod's (valid) code patch: the Unlimited patch is merged into it for sharing
    write(mods, "00040000000A0500/exefs/code.ips", b"PATCH\x1b\x2c\xf4\x00\x01\x3cEOF")
    gs = types.SimpleNamespace(data=None, project=types.SimpleNamespace(output_path=out, rom_path=rom))
    dlg = ShareDialog(gs, mods)
    dlg._dlc_romfs = lambda: dlc
    dlg.show()
    QApplication.processEvents()
    check(dlg.code_check.isEnabled() and dlg.code_check.isChecked(), "code.ips offered")
    dlg.name_edit.setText("Awakening Reborn")
    dlg.author_edit.setText("Lilloader")
    dlg.check_first.setChecked(False)
    z = dlg.make(os.path.join(tmp, "share_test"))
    check(z.endswith("share_test.zip") and os.path.isfile(z), z)
    with zipfile.ZipFile(z) as zf:
        from paragon.unlimited.tools import code_patch

        code = zf.read("Awakening Reborn/00040000000A0500/code.ips")
        check(code_patch.status(code) == code_patch.CURRENT, "the shared code.ips has the Unlimited patch")
        check(code_patch.parse_ips(code)[0] == (0x1B2CF4, b"\x3c"), "the other mod's change is kept")
    check("Done" in dlg.status.text(), dlg.status.text())
    check(share_mod.load_info(out)["name"] == "Awakening Reborn", "name remembered")
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
    print("share test: all checks passed")


if __name__ == "__main__":
    main()
