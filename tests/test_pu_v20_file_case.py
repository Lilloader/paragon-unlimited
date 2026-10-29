"""Paragon Unlimited v1.11: exact file-name case (the game looks RomFS names up exactly).
Pure Python with temporary folders and a fake data layer."""
import os
import shutil
import sys
import tempfile
import types

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.chdir(os.path.join(os.path.dirname(__file__), ".."))

from paragon.core.services import pu_file_case as fc
from paragon.core.services.fe13_mod_check import ModChecker


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
        return (self.chars_root, "people") if name == "characters" else None

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
        touch(root, "face/edelgard_fc_通常.arc")
        fc.clear_cache()
        check(fc.find(root, "face/edelgard_fc_通常.arc") == ("exact", "face/edelgard_fc_通常.arc"), "exact")
        check(fc.find(root, "face/Edelgard_fc_通常.arc") == ("case", "face/edelgard_fc_通常.arc"), "case")
        check(fc.find(root, "face/Other.arc") == ("missing", None), "missing")
        check(fc.fix_project_name(root, "face/edelgard_fc_通常.arc", "face/Edelgard_fc_通常.arc"), "renamed")
        check(os.listdir(os.path.join(root, "face")) == ["Edelgard_fc_通常.arc"], os.listdir(os.path.join(root, "face")))
        # Copy to Azahar: the destination takes the source's case.
        src_root, dst_root = tempfile.mkdtemp(), tempfile.mkdtemp()
        touch(src_root, "map/unit/Cow緑.ctpk.lz", b"new")
        touch(dst_root, "map/unit/cow緑.ctpk.lz", b"new")
        fc.clear_cache()
        check(fc.match_destination_case(os.path.join(src_root, "map/unit/Cow緑.ctpk.lz"),
                                        os.path.join(dst_root, "map/unit/Cow緑.ctpk.lz")), "dst renamed")
        check(os.listdir(os.path.join(dst_root, "map/unit")) == ["Cow緑.ctpk.lz"], os.listdir(os.path.join(dst_root, "map/unit")))
        from paragon.core.services import pu_azahar

        renamed = []
        todo, same = pu_azahar._plan(src_root, dst_root, renamed)
        check(same == 1 and not todo, (todo, same))
        shutil.rmtree(src_root)
        shutil.rmtree(dst_root)
    finally:
        shutil.rmtree(root)
    print("find / rename: ok")


def test_mod_check():
    project, game = tempfile.mkdtemp(), tempfile.mkdtemp()
    try:
        touch(project, "face/edelgard_fc_通常.arc")  # FaceData says Edelgard_fc
        touch(project, "face/Camilla_fc_通常.arc")
        for c in "青赤緑":
            touch(project, f"map/unit/Edelord{c}.ctpk.lz")  # table says edelord
            touch(project, f"map/unit/ヴァルキュリアシャンブレー{c}.ctpk.lz")  # table has a typo
            touch(game, f"map/unit/ロード男{c}.ctpk.lz")
        touch(project, "map/unit/Athena1緑.ctpk.lz")
        touch(project, "map/unit/Athena1赤.ctpk.lz")  # no 青
        gd = FakeData(
            [("FSID_FC_Edelgard_通常", "Edelgard_fc_通常.arc"), ("FSID_FC_Camilla_通常", "Camilla_fc_通常.arc")],
            [("PID_Edelgard", ["edelord", None, "ロード男"]), ("PID_Athena", ["Athena1"]),
             ("PID_Kid", ["ヴァルキュリアシャンプレー"])],
        )
        mc = ModChecker(gd, None, None, [project, game])
        issues = mc.run()
        text = "\n".join(f"{i.where}: {i.message}" for i in issues)
        check("Edelgard_fc_通常.arc but the file is named edelgard_fc_通常.arc" in text, text)
        check(sum("edelord" in i.where and "letter case" in i.message for i in issues) == 3, text)
        check("Missing Athena1青.ctpk.lz (blue (player))" in text, text)
        check("closest file is ヴァルキュリアシャンブレー青.ctpk.lz" in text, text)
        check("ロード男" not in text and "Camilla" not in text, "game files and correct names are fine")
        check(len(mc.case_fixes) == 4, mc.case_fixes)
        done = mc.fix_name_case()
        check(len(done) == 4, done)
        check(all(f.startswith("edelord") for f in os.listdir(os.path.join(project, "map/unit")) if f.lower().startswith("edelord")), os.listdir(os.path.join(project, "map/unit")))
        check("Edelgard_fc_通常.arc" in os.listdir(os.path.join(project, "face")), os.listdir(os.path.join(project, "face")))
        again = ModChecker(gd, None, None, [project, game]).run()
        check(not any("letter case" in i.message for i in again), [i.message for i in again])
    finally:
        shutil.rmtree(project)
        shutil.rmtree(game)
    print("mod check file names: ok")


def main():
    test_find_and_rename()
    test_mod_check()
    print("v1.11 file name case test: all checks passed")


if __name__ == "__main__":
    main()
