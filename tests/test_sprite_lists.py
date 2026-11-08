"""Sprite Data lists padded to the class list on save (paragon/unlimited/saving/save_checks.py
pad_sprite_lists). A small fake data layer; no game files."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.chdir(os.path.join(os.path.dirname(__file__), ".."))

from paragon.unlimited.saving.save_checks import ValidationReport, pad_sprite_lists


def check(cond, msg):
    if not cond:
        raise AssertionError(msg)


class FakeData:
    def __init__(self, jobs, lists):
        self.rec, self.lists, self.next, self.dirty = {}, {}, 100, set()
        self.icons_root = self._new()
        self.lists[(self.icons_root, "icons")] = [self._new(name="ダミー男"), self._new(name="ロード女")]
        self.jobs_root = self._new()
        self.lists[(self.jobs_root, "jobs")] = [self._new() for _ in range(jobs)]
        self.chars_root = self._new()
        self.lists[(self.chars_root, "people")] = []
        shared = None
        for spec in lists:
            sd = self._new()
            self.lists[(sd, "entries")] = []
            for icon in spec:
                e = self._new()
                self.rec[e]["bmap_icon"] = None if icon is None else self.lists[(self.icons_root, "icons")][icon]
                self.lists[(sd, "entries")].append(e)
            p = self._new(sprite_data=sd)
            self.lists[(self.chars_root, "people")].append(p)
            shared = shared or sd
        self.lists[(self.chars_root, "people")].append(self._new(sprite_data=shared))  # a shared list
        self.lists[(self.chars_root, "people")].append(self._new(sprite_data=None))

    def _new(self, **f):
        self.next += 1
        self.rec[self.next] = dict(f)
        return self.next

    def table(self, name):
        return {"jobs": (self.jobs_root, "jobs"), "characters": (self.chars_root, "people"),
                "bmap_icons": (self.icons_root, "icons")}.get(name)

    def items(self, rid, f):
        return list(self.lists.get((rid, f), []))

    def list_size(self, rid, f):
        return len(self.lists[(rid, f)])

    def list_get(self, rid, f, i):
        return self.lists[(rid, f)][i]

    def list_add(self, rid, f):
        r = self._new()
        self.lists[(rid, f)].append(r)
        return r

    def rid(self, rid, f):
        return self.rec[rid].get(f)

    def set_rid(self, rid, f, v):
        self.rec[rid][f] = v

    def string(self, rid, f):
        return self.rec[rid].get(f)

    def set_store_dirty(self, s, v):
        (self.dirty.add if v else self.dirty.discard)(s)


def test_pad():
    # 137 classes; a 124-entry list, a 134-entry list ending in the padding entry (sprite 0), an empty one
    d = FakeData(137, [[1] * 124, [None] * 133 + [0], []])
    r = ValidationReport()
    pad_sprite_lists(d, r)
    sizes = [d.list_size(d.rid(p, "sprite_data"), "entries") for p in d.items(d.chars_root, "people")[:3]]
    check(sizes == [138, 138, 0], sizes)
    second = d.items(d.rid(d.items(d.chars_root, "people")[1], "sprite_data"), "entries")
    check(d.rid(second[133], "bmap_icon") is None, "stray padding entry cleared")
    first = d.items(d.rid(d.items(d.chars_root, "people")[0], "sprite_data"), "entries")
    check(d.rid(first[0], "bmap_icon") is not None and d.rid(first[130], "bmap_icon") is None, "kept / new entries")
    check("characters" in d.dirty and len(r.by_severity("fixed")) == 2, r.to_text())
    r2 = ValidationReport()
    d.dirty.clear()
    pad_sprite_lists(d, r2)
    check(not d.dirty and not r2.by_severity("fixed"), "nothing to do the second time")
    print("sprite lists: ok")


if __name__ == "__main__":
    test_pad()
    print("sprite list test: all checks passed")
