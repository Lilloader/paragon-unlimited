"""Exact file-name case (the game looks RomFS names up exactly).
Pure Python with temporary folders and a fake data layer."""
import os
import shutil
import sys
import tempfile
import types

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.chdir(os.path.join(os.path.dirname(__file__), ".."))

from paragon.unlimited.tools import file_case as fc
from paragon.unlimited.tools.mod_check import ModChecker


def check(cond, msg):
    if not cond:
        raise AssertionError(msg)


def touch(root, rel, data=b"x"):
    p = os.path.join(root, *rel.split("/"))
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "wb") as f:
        f.write(data)


class FakeData:
    def __init__(self, portraits, characters):
        self.rec = {}
        self.next = 0
        self.lists = {}
        self.facedata = self._new()
        self.lists[(self.facedata, "portraits")] = [self._new(fsid=f, portrait_file=p) for f, p in portraits]
        self.chars_root = self._new()
        chars = []
        for pid, icons in characters:
            sd = self._new()
            self.lists[(sd, "entries")] = [self._new(bmap_icon=self._new(name=n) if n else None) for n in icons]
            chars.append(self._new(key=pid, sprite_data=sd))
        self.lists[(self.chars_root, "people")] = chars

    def _new(self, **f):
        self.next += 1
        self.rec[self.next] = f
        return self.next

    def node(self, name):
        return types.SimpleNamespace(rid=self.facedata) if name == "facedata" else None

    def table(self, name):
        if name == "characters":
            return (self.chars_root, "people")
        return getattr(self, "tables", {}).get(name)

    def list_size(self, rid, f):
        return len(self.lists[(rid, f)])

    def list_get(self, rid, f, i):
        return self.lists[(rid, f)][i]

    def items(self, rid, f):
        return list(self.lists.get((rid, f), []))

    def rid(self, rid, f):
        return self.rec[rid].get(f)

    def string(self, rid, f):
        return self.rec[rid].get(f)

    def key(self, rid):
        return self.rec[rid].get("key")

    def file_exists(self, path, localized):
        return True

    def read_arc(self, path):
        return ["通常.ctpk.lz"]


def test_find_and_rename():
    root = tempfile.mkdtemp()
    try:
        touch(root, "face/arlen_fc_通常.arc")
        fc.clear_cache()
        check(fc.find(root, "face/arlen_fc_通常.arc") == ("exact", "face/arlen_fc_通常.arc"), "exact")
        check(fc.find(root, "face/Arlen_fc_通常.arc") == ("case", "face/arlen_fc_通常.arc"), "case")
        check(fc.find(root, "face/Other.arc") == ("missing", None), "missing")
        check(fc.fix_project_name(root, "face/arlen_fc_通常.arc", "face/Arlen_fc_通常.arc"), "renamed")
        check(os.listdir(os.path.join(root, "face")) == ["Arlen_fc_通常.arc"], os.listdir(os.path.join(root, "face")))
        # Copy to Emulator: the destination takes the source's case.
        src_root, dst_root = tempfile.mkdtemp(), tempfile.mkdtemp()
        touch(src_root, "map/unit/Knight緑.ctpk.lz", b"new")
        touch(dst_root, "map/unit/knight緑.ctpk.lz", b"new")
        fc.clear_cache()
        check(fc.match_destination_case(os.path.join(src_root, "map/unit/Knight緑.ctpk.lz"),
                                        os.path.join(dst_root, "map/unit/Knight緑.ctpk.lz")), "dst renamed")
        check(os.listdir(os.path.join(dst_root, "map/unit")) == ["Knight緑.ctpk.lz"], os.listdir(os.path.join(dst_root, "map/unit")))
        from paragon.unlimited.tools import azahar

        renamed = []
        todo, same = azahar._plan(src_root, dst_root, renamed)
        check(same == 1 and not todo, (todo, same))
        shutil.rmtree(src_root)
        shutil.rmtree(dst_root)
    finally:
        shutil.rmtree(root)
    print("find / rename: ok")


def test_mod_check():
    project, game = tempfile.mkdtemp(), tempfile.mkdtemp()
    try:
        touch(project, "face/arlen_fc_通常.arc")  # FaceData says Arlen_fc
        touch(project, "face/Tessa_fc_通常.arc")
        for c in "青赤緑":
            touch(project, f"map/unit/Arlenlord{c}.ctpk.lz")  # table says arlenlord
            touch(project, f"map/unit/ValkyrieHero{c}.ctpk.lz")  # table has a typo
            touch(game, f"map/unit/ロード男{c}.ctpk.lz")
        touch(project, "map/unit/Mira1緑.ctpk.lz")
        touch(project, "map/unit/Mira1赤.ctpk.lz")  # no 青
        gd = FakeData(
            [("FSID_FC_Arlen_通常", "Arlen_fc_通常.arc"), ("FSID_FC_Tessa_通常", "Tessa_fc_通常.arc")],
            [("PID_Arlen", ["arlenlord", None, "ロード男"]), ("PID_Mira", ["Mira1"]),
             ("PID_Kid", ["ValkyrleHero"])],
        )
        mc = ModChecker(gd, None, None, [project, game])
        issues = mc.run()
        text = "\n".join(f"{i.where}: {i.message}" for i in issues)
        check("Arlen_fc_通常.arc but the file is named arlen_fc_通常.arc" in text, text)
        check(sum("arlenlord" in i.where and "letter case" in i.message for i in issues) == 3, text)
        check("Missing Mira1青.ctpk.lz (blue (player))" in text, text)
        check("closest file is ValkyrieHero青.ctpk.lz" in text, text)
        check("ロード男" not in text and "Tessa" not in text, "game files and correct names are fine")
        check(len(mc.case_fixes) == 4, mc.case_fixes)
        done = mc.fix_name_case()
        check(len(done) == 4, done)
        check(all(f.startswith("arlenlord") for f in os.listdir(os.path.join(project, "map/unit")) if f.lower().startswith("arlenlord")), os.listdir(os.path.join(project, "map/unit")))
        check("Arlen_fc_通常.arc" in os.listdir(os.path.join(project, "face")), os.listdir(os.path.join(project, "face")))
        again = ModChecker(gd, None, None, [project, game]).run()
        check(not any("letter case" in i.message for i in again), [i.message for i in again])
    finally:
        shutil.rmtree(project)
        shutil.rmtree(game)
    print("mod check file names: ok")


def test_sprite_and_voice_checks():
    project, game = tempfile.mkdtemp(), tempfile.mkdtemp()
    try:
        for c in "青赤緑":
            touch(project, f"map/unit/Used{c}.ctpk.lz")
            touch(game, f"map/unit/ロード男{c}.ctpk.lz")
        gd = FakeData([], [("PID_A", ["Used", "Used"]), ("PID_B", ["Used"])])
        jobs = gd._new()
        gd.lists[(jobs, "jobs")] = [gd._new() for _ in range(2)]
        icons = gd._new()
        gd.lists[(icons, "icons")] = [gd._new(name=n) for n in ("ダミー", "Used", "ロード男", "Twice", "Twice", "Lost")]
        gd.tables = {"jobs": (jobs, "jobs"), "bmap_icons": (icons, "icons")}
        specs = gd._new()
        gd.lists[(specs, "specs")] = [gd._new(name="PID_A", voice="CHROM"), gd._new(name="PID_B", voice="NOBODY")]
        gd.node = lambda name: types.SimpleNamespace(rid=specs) if name == "asset_definitions" else (
            types.SimpleNamespace(rid=gd.facedata) if name == "facedata" else None)

        class Voices:
            def voices_for_codes(self, codes):
                return ["SE_VOICE_CHROM_ATK_1"] if codes == ["CHROM"] else []

        mc = ModChecker(gd, Voices(), None, [project, game])
        mc.check_map_sprites()
        mc.check_voice_sets()
        text = "\n".join(f"{i.category} | {i.where}: {i.message}" for i in mc.issues)
        check("1 character(s): PID_B" in text and "shorter than the class list (2 classes)" in text, text)
        check("2 BMap Icons are named Twice" in text, text)
        check("BMap Icon Lost: No file map/unit/Lost" in text and "BMap Icon Twice: No file" in text, text)
        check("Icon Used:" not in text and "ロード男" not in text and "ダミー" not in text, "used / game / dummy icons are fine")
        check("voice NOBODY (PID_B)" in text and "voice CHROM" not in text, text)
        check(sum(i.category == "Voices" for i in mc.issues) == 1, text)
    finally:
        shutil.rmtree(project)
        shutil.rmtree(game)
    print("mod check sprites and voices: ok")


def main():
    test_find_and_rename()
    test_mod_check()
    test_sprite_and_voice_checks()
    print("file name case test: all checks passed")


if __name__ == "__main__":
    main()
