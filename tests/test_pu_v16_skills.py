"""Offscreen Qt test for Paragon Unlimited v1.6 skills: effect lines editor, skill icon import
(skill.tga cell writer) and the save checks. No game files: a small fake data layer."""
import os
import struct
import sys
import types

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.chdir(os.path.join(os.path.dirname(__file__), ".."))

from PySide6.QtWidgets import QApplication

from paragon.core.services import fe13_skill_fx as fx
from paragon.core.services import fe13_skill_icons as si


def check(cond, msg):
    if not cond:
        raise AssertionError(msg)


class FakeData:
    """Records keyed by rid; lists as python lists of rids."""

    def __init__(self, n_skills=105):
        self.rec = {}
        self.lists = {}
        self.dirty = set()
        self.next = 1000
        self.skills_root = self._new("SkillTable")
        self.lists[(self.skills_root, "skills")] = []
        rsids = {8: "RSID_命中＋１０", 9: "RSID_命中＋２０", 10: "RSID_回避＋１０", 26: "RSID_一発屋"}
        for i in range(n_skills):
            r = self._new("Skill", rsid=rsids.get(i, f"RSID_{i}"), id=i, icon=i, name=f"Skill {i}", unknown=b"\0\0\0")
            self.lists[(self.skills_root, "skills")].append(r)
        self.fx_root = self._new("PUSkillFxTable")
        self.lists[(self.fx_root, "entries")] = []
        self.files = {}

    def _new(self, t, **fields):
        self.next += 1
        self.rec[self.next] = dict(_type=t, **fields)
        return self.next

    # --- API used by the code under test
    def node(self, nid):
        if nid == "skills":
            return types.SimpleNamespace(rid=self.skills_root)
        if nid == "pu_skill_effects":
            return types.SimpleNamespace(rid=self.fx_root)
        return None

    def type_of(self, rid):
        return self.rec.get(rid, {}).get("_type")

    def items(self, rid, f):
        return list(self.lists.get((rid, f), []))

    def list_size(self, rid, f):
        return len(self.lists[(rid, f)])

    def list_get(self, rid, f, i):
        return self.lists[(rid, f)][i]

    def list_add(self, rid, f):
        r = self._new("PUSkillFx", skill=None, effect=0, condition_1=0, condition_2=0, value=0)
        self.lists[(rid, f)].append(r)
        return r

    def list_remove(self, rid, f, i):
        del self.lists[(rid, f)][i]

    def rid(self, rid, f):
        return self.rec[rid].get(f)

    def set_rid(self, rid, f, v):
        self.rec[rid][f] = v

    def int(self, rid, f):
        return self.rec[rid].get(f)

    def set_int(self, rid, f, v):
        self.rec[rid][f] = v

    def bytes(self, rid, f):
        return self.rec[rid].get(f)

    def set_bytes(self, rid, f, v):
        self.rec[rid][f] = bytes(v)

    def string(self, rid, f):
        return self.rec[rid].get(f)

    def display(self, rid):
        return self.rec[rid].get("name")

    def key_to_rid(self, table, key):
        if table == "skills":
            for r in self.lists[(self.skills_root, "skills")]:
                if self.rec[r]["rsid"] == key:
                    return r
        return None

    def set_store_dirty(self, s, v):
        (self.dirty.add if v else self.dirty.discard)(s)

    def store_is_dirty(self, s):
        return s in self.dirty

    def file_exists(self, path, localized):
        return path in self.files

    def read_file(self, path):
        return self.files[path]

    def write_file(self, path, data):
        self.files[path] = bytes(data)


def fake_icon_ctpk():
    """CTPK with one RGBA4 256x512 texture named skill.tga; cells 0-104 filled."""
    w, h = 256, 512
    pixels = bytearray(w * h * 2)
    name_off = 0x40
    base = 0x80
    hdr = bytearray(base)
    hdr[0:4] = b"CTPK"
    struct.pack_into("<HH", hdr, 4, 1, 1)
    struct.pack_into("<I", hdr, 8, base)
    struct.pack_into("<IIIIHH", hdr, 0x20, name_off, len(pixels), 0, 4, w, h)
    hdr[name_off:name_off + 10] = b"skill.tga\0"
    ctpk = bytes(hdr) + bytes(pixels)
    full = b"\xff" * (24 * 24 * 4)
    for c in range(105):
        ctpk = si.write_cell(ctpk, c, full)
    return ctpk


def test_rules_and_checks():
    gd = FakeData()
    check(fx.root(gd) == gd.fx_root, "root")
    check(fx.ensure_built_in_rules(gd) == 5, "built-in rules")
    check(fx.ensure_built_in_rules(gd) == 0, "not added twice")
    skill = gd.lists[(gd.skills_root, "skills")][104]
    e = fx.add_rule(gd, skill, 4, 1, 0, 30)
    check(fx.describe(gd, e) == "Skill 104: Avoid +30 when this unit starts the fight", fx.describe(gd, e))
    e2 = fx.add_rule(gd, skill, 2, 1, 13, -10)
    check("Damage received -10 when this unit starts the fight and the enemy attacks with a physical weapon" in fx.describe(gd, e2), fx.describe(gd, e2))
    check(len(fx.rules_for(gd, skill)) == 2, "rules for skill")
    check(fx.remove_rule(gd, e2) and len(fx.rules_for(gd, skill)) == 1, "remove")
    check(fx.check(gd) == [], fx.check(gd))
    bad = fx.add_rule(gd, skill)
    gd.set_rid(bad, "skill", None)
    check(fx.cleanup(gd) == 1, "cleanup orphans")
    gd2 = FakeData(n_skills=130)
    check(any("128" in p for p in fx.check(gd2)), "too many skills reported")
    # save preprocessor: order byte for added skills, built-in rules once
    from paragon.core.services.fe13_write_preprocessors import ValidationReport, tidy_skills

    gd3 = FakeData()
    gd3.set_store_dirty("gamedata", True)
    rep = ValidationReport()
    tidy_skills(gd3, rep)
    new = gd3.lists[(gd3.skills_root, "skills")][104]
    check(gd3.bytes(new, "unknown")[1] == 104, gd3.bytes(new, "unknown"))
    check(len(fx.rules(gd3)) == 5, "built-in rules added on first save")
    print("rules and checks: ok")


def test_icons():
    ctpk = fake_icon_ctpk()
    check(si.cell_count(ctpk) == 210, si.cell_count(ctpk))
    check(not si.is_free(ctpk, 104) and si.is_free(ctpk, 105), "free cells")
    px = bytes([(i * 7) & 0xF0 | 0x0F for i in range(24 * 24 * 4)])
    out = si.write_cell(ctpk, 120, px)
    back = si.read_cell(out, 120)
    check(back == bytes((((b * 15 + 127) // 255) * 17) for b in px), "cell round trip (RGBA4)")
    check(si.read_cell(out, 119) == si.read_cell(ctpk, 119), "neighbour untouched")
    gd = FakeData()
    gd.files["systems/icon_E.ctpk.lz"] = ctpk
    gd.files["systems/icon_U.ctpk.lz"] = ctpk
    edits = si.SkillIconEdits(gd)
    check(edits.files() == ["systems/icon_E.ctpk.lz", "systems/icon_U.ctpk.lz"], edits.files())
    cell = edits.import_icon(b"\x80" * (24 * 24 * 4))
    check(cell == 105 and edits.has_pending(), cell)
    check(edits.import_icon(b"\x40" * (24 * 24 * 4)) == 106, "next free cell")
    written = edits.flush()
    check(sorted(written) == sorted(gd.files) and not edits.has_pending(), written)
    check(not si.is_free(gd.files["systems/icon_U.ctpk.lz"], 106), "both languages written")
    from PIL import Image

    check(len(si.fit_icon(Image.new("RGBA", (48, 30), (255, 0, 0, 255)))) == 24 * 24 * 4, "fit")
    print("skill icons: ok")


def test_widget(app):
    from paragon.ui.controllers.auto.fe13_skill_fx_widget import FE13SkillFxWidget

    gd = FakeData()
    state = types.SimpleNamespace(main_state=None, game_state=types.SimpleNamespace(data=gd))
    w = FE13SkillFxWidget(state)
    skill = gd.lists[(gd.skills_root, "skills")][104]
    w.set_target(skill)
    check(w.list.count() == 0 and w.add_button.isEnabled(), "empty")
    w.add_button.click()
    check(w.list.count() == 1, "added")
    w.effect.setCurrentIndex(w.effect.findData(5))
    w.amount.setValue(20)
    w.when.setCurrentIndex(w.when.findData(1))
    rule = fx.rules_for(gd, skill)[0]
    check((gd.int(rule, "effect"), gd.int(rule, "value"), gd.int(rule, "condition_1")) == (5, 20, 1), gd.rec[rule])
    check(w.list.item(0).text() == "Crit +20 when this unit starts the fight", w.list.item(0).text())
    check("gamedata" in gd.dirty, "dirty")
    w.add_button.click()
    check(w.list.count() == 2 and w.list.currentRow() == 1, "second")
    w.remove_button.click()
    check(w.list.count() == 1, "removed")
    other = gd.lists[(gd.skills_root, "skills")][103]
    w.set_target(other)
    check(w.list.count() == 0 and not w.effect.isEnabled(), "other skill has none")
    w.set_target(skill)
    check(w.list.count() == 1, "back")
    w.resize(520, 360)
    os.makedirs("qt_out", exist_ok=True)
    w.grab().save("qt_out/v16_skill_effects.png")
    print("effects widget: ok")


def main():
    app = QApplication.instance() or QApplication([])
    test_rules_and_checks()
    test_icons()
    test_widget(app)
    print("v1.6 skills test: all checks passed")


if __name__ == "__main__":
    main()
