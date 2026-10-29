"""Paragon Unlimited v1.9: save-time support repairs (duplicate conversation records, listings in
the wrong table, placeholder slots), slot compaction and the 1920 support-number limit.
No Qt, no game files: a small fake data layer."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.chdir(os.path.join(os.path.dirname(__file__), ".."))

from paragon.core.services import fe13_reliance as fr
from paragon.core.services import fe13_support_tools as st
from paragon.core.services import fe13_write_preprocessors as wp


def check(cond, msg):
    if not cond:
        raise AssertionError(msg)


class Node:
    def __init__(self, rid):
        self.rid = rid


class FakeData:
    def __init__(self, n_chars):
        self.rec, self.lists, self.next, self.dirty = {}, {}, 1000, set()
        self.chars_root = self._new("Table", support_ex=None)
        self.ex_root = self._new("ExTable")
        self.rec[self.chars_root]["support_ex"] = self.ex_root
        self.lists[(self.ex_root, "entries")] = []
        self.chars = []
        for i in range(n_chars):
            c = self._new("Person", name=f"C{i}", bitflags_1=i % 2)
            for k in range(52):
                self.rec[c][f"support_character_{k:03}"] = None
                self.rec[c][f"support_type_{k:03}"] = st.TYPE_NONE
            self.chars.append(c)
        self.lists[(self.chars_root, "people")] = list(self.chars)
        self.rel = self._new("RelianceListTable")
        self.lists[(self.rel, "tables")] = []
        for _ in range(n_chars):
            t = self._new("Ptr")
            lst = self._new("RelianceList")
            self.rec[t]["data"] = lst
            self.lists[(lst, "data")] = []
            self.lists[(self.rel, "tables")].append(t)

    def _new(self, t, **f):
        self.next += 1
        self.rec[self.next] = dict(_type=t, **f)
        return self.next

    def conversation(self, a, b, level, number, tables, stype=0):
        e = self._new("RelianceListData", character1=a, character2=b, support_level=level,
                      support_number=number, support_type=stype)
        for ti in tables:
            lst = self.rec[self.lists[(self.rel, "tables")][ti]]["data"]
            p = self._new("Pointer", data=e)
            self.lists[(lst, "data")].append(p)
        return e

    def listing(self, ti):
        lst = self.rec[self.lists[(self.rel, "tables")][ti]]["data"]
        return [self.rec[p]["data"] for p in self.lists[(lst, "data")]]

    # API
    def node(self, name):
        return Node(self.rel) if name == "reliance_list" else None

    def table(self, name):
        return (self.chars_root, "people") if name == "characters" else None

    def items(self, rid, f):
        return list(self.lists.get((rid, f), []))

    def list_remove(self, rid, f, i):
        del self.lists[(rid, f)][i]

    def list_add(self, rid, f):
        r = self._new("PUSupportEx", owner=None)
        for k in range(52, 60):
            self.rec[r][f"support_character_{k:03}"] = None
            self.rec[r][f"support_type_{k:03}"] = st.TYPE_NONE
        self.lists[(rid, f)].append(r)
        return r

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

    def store_is_dirty(self, s):
        return s in self.dirty

    def set_store_dirty(self, s, v):
        (self.dirty.add if v else self.dirty.discard)(s)


def test_duplicates_and_misplaced():
    gd = FakeData(6)
    a, b, c = gd.chars[0], gd.chars[1], gd.chars[2]
    keep = gd.conversation(a, b, 1, 100, [0, 1])
    gd.conversation(a, b, 1, 100, [0, 1])  # exact copy
    gd.conversation(b, a, 1, 150, [0, 1])  # same conversation, other number
    other = gd.conversation(a, b, 2, 101, [0, 1])
    stray = gd.conversation(a, c, 1, 102, [0, 2, 5])  # also listed in table 5
    rep = fr.remove_duplicate_conversations(gd)
    check(len(rep) == 1 and rep[0][3] == 100 and sorted(rep[0][4]) == [100, 150], rep)
    check(gd.listing(0) == [keep, other, stray] and gd.listing(1) == [keep, other], (gd.listing(0), gd.listing(1)))
    check(fr.remove_misplaced(gd) == 1 and gd.listing(5) == [], gd.listing(5))
    check(gd.listing(2) == [stray], "own table kept")
    check("reliance_list" in gd.dirty, "dirty")
    check(fr.remove_duplicate_conversations(gd) == [] and fr.remove_misplaced(gd) == 0, "nothing left")
    print("duplicates and stray listings: ok")


def test_placeholders_and_compact():
    gd = FakeData(4)
    a, b, c, d = gd.chars
    for k in range(52):
        gd.set_rid(d, f"support_character_{k:03}", a)  # every slot = the same partner, type None
    gd.set_rid(c, "support_character_005", a)  # one real-looking slot with type None: kept
    cleared = st.clear_placeholder_slots(gd, gd.chars)
    check(cleared == [(d, 52)], cleared)
    check(gd.rid(c, "support_character_005") == a, "single None slot kept")

    gd.set_rid(b, "support_character_003", a)
    gd.set_int(b, "support_type_003", st.TYPE_SLOW)
    gd.set_rid(b, "support_character_010", c)
    gd.set_int(b, "support_type_010", st.TYPE_NON_ROMANTIC)
    check(st.compact(gd, b), "moved")
    check(gd.rid(b, "support_character_000") == a and gd.int(b, "support_type_000") == st.TYPE_SLOW, "first")
    check(gd.rid(b, "support_character_001") == c and gd.int(b, "support_type_001") == st.TYPE_NON_ROMANTIC, "second")
    check(gd.rid(b, "support_character_003") is None and gd.rid(b, "support_character_010") is None, "old slots empty")
    check(not st.compact(gd, b), "already compact")
    print("placeholder slots and compaction: ok")


def test_number_limit():
    gd = FakeData(3)
    a, b, _c = gd.chars
    check(wp.SUPPORT_NUMBER_LIMIT == 1920, wp.SUPPORT_NUMBER_LIMIT)
    gd.conversation(a, b, 1, 5, [0, 1])
    check(wp.next_free_support_number(gd, 1920) == 6, "after the highest")
    gd.conversation(a, b, 2, 1919, [0, 1])
    check(wp.next_free_support_number(gd, 1920) == 0, "lowest free below the limit")
    check(wp.next_free_support_number(gd, 4096) == 1920, "room above 1919 with exp05")
    report = wp.ValidationReport()
    gd.conversation(a, b, 3, 1925, [0, 1])
    ctx = wp._Context(gd, report, gd.chars_root, "people", gd.rel)
    ctx.number_limit = 1920
    gd.key = lambda r: f"PID_{gd.rec[r].get('name')}"
    gd.display = lambda r: gd.rec[r].get("name")
    wp.validate(ctx)
    errs = [i.message for i in report.by_severity("error")]
    check(any("1920 or higher" in m and "#1925" in m and "exp05" in m for m in errs), errs)
    report2 = wp.ValidationReport()
    ctx2 = wp._Context(gd, report2, gd.chars_root, "people", gd.rel)
    ctx2.number_limit = 4096
    wp.validate(ctx2)
    check(not [i for i in report2.by_severity("error") if "support conversation number" in i.message], "fine with exp05")
    # IPS detection
    rec = (0x8B30).to_bytes(3, "big") + (4).to_bytes(2, "big") + bytes.fromhex("011aa013")
    check(wp.ips_has_support_number_patch(b"PATCH" + rec + b"EOF"), "found")
    check(not wp.ips_has_support_number_patch(b"PATCH" + rec[:5] + bytes.fromhex("1e1da013") + b"EOF"), "original bytes")
    big = (0x8B20).to_bytes(3, "big") + (0x20).to_bytes(2, "big") + bytes(16) + bytes.fromhex("011aa013") + bytes(12)
    check(wp.ips_has_support_number_patch(b"PATCH" + big + b"EOF"), "inside a longer record")
    print("support number limit: ok")


def main():
    test_duplicates_and_misplaced()
    test_placeholders_and_compact()
    test_number_limit()
    print("v1.9 support repairs test: all checks passed")


if __name__ == "__main__":
    main()
