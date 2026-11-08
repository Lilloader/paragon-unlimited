"""Reclass slots 4-5 and the avatar class checklist (paragon/unlimited/characters/class_slots*.py).
A small fake data layer (no game files); the checklist widget runs offscreen when Qt is there."""
import os
import sys
import types

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.chdir(os.path.join(os.path.dirname(__file__), ".."))

from paragon.unlimited.characters import class_slots as cs


def check(cond, msg):
    if not cond:
        raise AssertionError(msg)


class FakeData:
    def __init__(self):
        self.rec, self.lists, self.next, self.dirty = {}, {}, 100, set()
        self.chars = self._new("PersonTable")
        self.lists[(self.chars, "people")] = []
        self.ex = self._new("PUClassExFile")
        self.lists[(self.ex, "entries")] = []
        self.rec[self.chars]["class_ex"] = self.ex
        self.jobs_root = self._new("JobTable")
        self.lists[(self.jobs_root, "jobs")] = []
        self.av = self._new("PUAvatarClsTable")
        self.lists[(self.av, "entries")] = []
        self.keys = {}

    def _new(self, t, **f):
        self.next += 1
        self.rec[self.next] = dict(_type=t, **f)
        return self.next

    def job(self, jid, name, promo=()):
        r = self._new("Job", name=name)
        for k, p in enumerate(promo, 1):
            self.rec[r][f"promoted_class_{k}"] = p
        self.keys[r] = jid
        self.lists[(self.jobs_root, "jobs")].append(r)
        return r

    def person(self, pid, male=(), female=()):
        r = self._new("Person", name=pid)
        for g, js in (("male", male), ("female", female)):
            for k in (1, 2, 3):
                self.rec[r][f"{g}_reclass_{k}"] = js[k - 1] if k <= len(js) else None
        self.keys[r] = pid
        self.lists[(self.chars, "people")].append(r)
        return r

    # --- the calls class_slots makes
    def table(self, name):
        return {"characters": (self.chars, "people"), "jobs": (self.jobs_root, "jobs")}.get(name)

    def node(self, name):
        return types.SimpleNamespace(rid=self.av) if name == "pu_avatar_classes" else None

    def items(self, rid, f):
        return list(self.lists.get((rid, f), []))

    def list_add(self, rid, f):
        r = self._new("PUClassEx" if rid == self.ex else "PUAvatarCls")
        self.lists[(rid, f)].append(r)
        return r

    def list_size(self, rid, f):
        return len(self.lists[(rid, f)])

    def list_get(self, rid, f, i):
        return self.lists[(rid, f)][i]

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

    def key(self, rid):
        return self.keys.get(rid)

    def key_to_rid(self, table, key):
        for r, k in self.keys.items():
            if k == key:
                return r
        return None

    def display(self, rid):
        return self.rec[rid].get("name")

    def string(self, rid, f):
        return self.rec[rid].get(f)

    def store_is_dirty(self, s):
        return s in self.dirty

    def set_store_dirty(self, s, v):
        (self.dirty.add if v else self.dirty.discard)(s)


def game():
    d = FakeData()
    promoted = {}
    for g in ("男", "女"):
        promoted[g] = d.job(f"JID_グランドマスター{g}", "Grandmaster")
    for g in ("男", "女"):
        for jid in cs.GAME_AVATAR_CLASSES["male" if g == "男" else "female"]:
            if not d.key_to_rid("jobs", jid):
                d.job(jid, jid[4:-1], (promoted[g],) if "戦術師" in jid else ())
    d.job("JID_ペガサスナイト男", "Pegasus Knight")
    d.job("JID_村人女", "Villager")
    d.job("JID_ロード男", "Lord")
    d.job("JID_ゾンビ男", "Revenant")
    d.job("JID_予約０１男", None)
    return d


def test_reclass_slots():
    d = game()
    lord = d.key_to_rid("jobs", "JID_ロード男")
    chrom = d.person("PID_クロム", male=(lord,))
    check(cs.reclass_classes(d, chrom, "male") == [lord], "slots 1-3")
    e = cs.ensure_entry(d, chrom)
    check(e and "characters" not in d.dirty, "an empty entry is not a change")
    check(cs.ensure_entry(d, chrom) == e, "one entry per character")
    sword = d.key_to_rid("jobs", "JID_剣士男")
    cs.set_slot(d, chrom, "male", 5, sword)
    check(cs.reclass_classes(d, chrom, "male") == [lord, sword] and "characters" in d.dirty, "slot 5")
    cs.set_slot(d, chrom, "male", 2, d.key_to_rid("jobs", "JID_盗賊男"))
    check(len(cs.reclass_classes(d, chrom, "male")) == 3, "slot 2 is on the character record")
    other = d.person("PID_リズ")
    cs.ensure_entry(d, other)
    orphan = d.list_add(d.ex, "entries")
    check(cs.cleanup(d) == (1, 1) and cs.class_ex_entries(d) == [e], "empty / orphan entries dropped")
    print("reclass slots 4-5: ok")


def test_avatar_list():
    d = game()
    tac = d.key_to_rid("jobs", "JID_戦術師男")
    robin = d.person("PID_Robin", male=(tac,), female=(d.key_to_rid("jobs", "JID_戦術師女"),))
    chrom = d.person("PID_クロム", male=(d.key_to_rid("jobs", "JID_ロード男"),))
    check(cs.is_avatar(d, robin) and not cs.is_avatar(d, chrom), "avatar = Tactician as a reclass class")
    other = d.person("PID_X")
    cs.set_slot(d, other, "female", 4, d.key_to_rid("jobs", "JID_戦術師女"))
    check(cs.is_avatar(d, other), "Tactician in slot 4 counts")
    check(cs.uses_game_list(d) and [d.key(j) for j in cs.avatar_classes(d, "male")] == cs.GAME_AVATAR_CLASSES["male"],
          "no entries: the game's own list")
    peg = d.key_to_rid("jobs", "JID_ペガサスナイト男")
    cs.set_avatar_classes(d, "male", cs.avatar_classes(d, "male") + [peg, peg])
    check(len(cs.avatar_classes(d, "male")) == 14 and cs.avatar_classes(d, "male")[-1] == peg, "added once")
    check([d.key(j) for j in cs.avatar_classes(d, "female")] == cs.GAME_AVATAR_CLASSES["female"],
          "the other gender keeps the game's list (written out)")
    check(len(d.items(d.av, "entries")) == 27 and "gamedata" in d.dirty, "27 entries")
    check(all(d.int(e, "gender") == (0 if i < 14 else 1) for i, e in enumerate(d.items(d.av, "entries"))), "genders")
    # Tactician + its promotion (Grandmaster): 14 + 1
    check(cs.seal_list_size(d, robin, "male") == 15, cs.seal_list_size(d, robin, "male"))
    cs.reset_avatar_classes(d)
    check(cs.uses_game_list(d), "reset")
    print("avatar list: ok")


def test_widget():
    try:
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QApplication
    except ImportError:
        print("avatar checklist widget: skipped (no Qt)")
        return
    from paragon.unlimited.characters.class_slots_widget import FE13AvatarClassesWidget

    app = QApplication.instance() or QApplication([])
    d = game()
    robin = d.person("PID_Robin", male=(d.key_to_rid("jobs", "JID_戦術師男"),))
    chrom = d.person("PID_クロム", male=(d.key_to_rid("jobs", "JID_ロード男"),))
    state = types.SimpleNamespace(main_state=None, game_state=types.SimpleNamespace(data=d))
    w = FE13AvatarClassesWidget(state)
    w.set_target(chrom)
    check(w.isHidden(), "hidden for a character that is not an avatar")
    w.set_target(robin)
    check(not w.isHidden(), "shown for an avatar")
    lw = w.lists["male"]
    ticked = [lw.item(i).text() for i in range(lw.count()) if lw.item(i).checkState() == Qt.Checked]
    check(len(ticked) == 13, ticked)
    peg = [i for i in range(lw.count()) if lw.item(i).data(Qt.UserRole) == d.key_to_rid("jobs", "JID_ペガサスナイト男")][0]
    lw.item(peg).setCheckState(Qt.Checked)
    check(d.key_to_rid("jobs", "JID_ペガサスナイト男") in cs.avatar_classes(d, "male"), "ticking adds the class")
    w._tick_all("male")
    males = [j for j in d.items(d.jobs_root, "jobs") if cs.job_gender(d, j) == "male"]
    check(len(cs.avatar_classes(d, "male")) == len(males) - 3,
          "tick all = every class but the promotion, Revenant and the nameless one")
    w._reset()
    check(cs.uses_game_list(d), "Game's own list")
    check("64" in w.size_label.text(), w.size_label.text())
    app.processEvents()
    print("avatar checklist widget: ok")


if __name__ == "__main__":
    test_reclass_slots()
    test_avatar_list()
    test_widget()
    print("class slots test: all checks passed")
