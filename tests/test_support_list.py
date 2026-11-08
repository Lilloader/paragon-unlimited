"""Supports tab: add, remove, fix and change the type of a whole support (slots on both sides,
support conversation records in both tables, conversation file with C/B/A(/S) messages).
Offscreen Qt for the widget; a small fake data layer (no game files)."""
import os
import sys
import types

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.chdir(os.path.join(os.path.dirname(__file__), ".."))

from paragon.unlimited.saving import save_checks as wp
from paragon.unlimited.supports import support_list as sl
from paragon.unlimited.supports import support_tools as st


def check(cond, msg):
    if not cond:
        raise AssertionError(msg)


class Node:
    def __init__(self, rid):
        self.rid = rid


class FakeData:
    def __init__(self, names):
        self.rec, self.lists, self.next, self.dirty = {}, {}, 1000, set()
        self.archives = {}
        self.chars_root = self._new("Table", support_ex=None)
        self.ex_root = self._new("ExTable")
        self.rec[self.chars_root]["support_ex"] = self.ex_root
        self.lists[(self.ex_root, "entries")] = []
        self.chars = []
        for name, female in names:
            c = self._new("Person", name=name, key=f"PID_{name}", bitflags_1=1 if female else 0)
            for k in range(52):
                self.rec[c][f"support_character_{k:03}"] = None
                self.rec[c][f"support_type_{k:03}"] = st.TYPE_NONE
            self.chars.append(c)
        self.lists[(self.chars_root, "people")] = list(self.chars)
        self.rel = self._new("RelianceListFile")
        self.lists[(self.rel, "tables")] = []
        for _ in range(len(names) - 1):  # one table short: the code adds the missing one
            self._table()

    def _table(self):
        t = self._new("RelianceListPointer")
        lst = self._new("RelianceList")
        self.rec[t]["data"] = lst
        self.lists[(lst, "data")] = []
        self.lists[(self.rel, "tables")].append(t)
        return t

    def _new(self, t, **f):
        self.next += 1
        self.rec[self.next] = dict(_type=t, **f)
        return self.next

    def listing(self, c):
        ti = self.chars.index(c)
        lst = self.rec[self.lists[(self.rel, "tables")][ti]]["data"]
        return [self.rec[p]["data"] for p in self.lists[(lst, "data")]]

    # API used by the code
    def node(self, name):
        return Node(self.rel) if name == "reliance_list" else None

    def table(self, name):
        return (self.chars_root, "people") if name == "characters" else None

    def items(self, rid, f):
        return list(self.lists.get((rid, f), []))

    def list_size(self, rid, f):
        return len(self.lists[(rid, f)])

    def list_get(self, rid, f, i):
        return self.lists[(rid, f)][i]

    def list_remove(self, rid, f, i):
        del self.lists[(rid, f)][i]

    def list_add(self, rid, f):
        if rid == self.ex_root:
            r = self._new("PUSupportEx", owner=None)
            for k in range(52, 60):
                self.rec[r][f"support_character_{k:03}"] = None
                self.rec[r][f"support_type_{k:03}"] = st.TYPE_NONE
        else:
            r = self._new("Pointer", data=None)
        self.lists.setdefault((rid, f), []).append(r)
        return r

    def new_instance(self, typ, store):
        r = self._new(typ)
        if typ == "RelianceList":
            self.lists[(r, "data")] = []
        return r

    def store_number_of(self, rid):
        return 0

    def type_of(self, rid):
        return self.rec[rid]["_type"]

    def key(self, rid):
        return self.rec[rid].get("key")

    def display(self, rid):
        return self.rec[rid].get("name")

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

    # text
    def open_text_data(self, path, loc):
        if path not in self.archives:
            raise KeyError(path)

    def new_text_data(self, path, loc):
        self.archives[path] = {}

    def set_text_archive_title(self, path, loc, title):
        self.archives[path]["__title__"] = title

    def enumerate_messages(self, path, loc):
        return [k for k in self.archives.get(path, {}) if k != "__title__"]

    def message(self, path, loc, key):
        return self.archives.get(path, {}).get(key)

    def set_message(self, path, loc, key, value):
        self.archives.setdefault(path, {})[key] = value


def pair_levels(gd, a, b):
    return sorted(lvl for _e, lvl in sl.conversation_records(gd, a, b))


def test_add_remove():
    gd = FakeData([("クロム", False), ("リズ", True), ("スミア", True), ("フレデリク", False)])
    chrom, lissa, sumia, fred = gd.chars
    wp.support_number_limit = lambda force=None: 1920

    # Two men: Non-romantic, C/B/A, no S.
    r = sl.add_support(gd, chrom, fred)
    check(r.ok and r.slots == (0, 0), r)
    check(gd.rid(chrom, "support_character_000") == fred and gd.rid(fred, "support_character_000") == chrom, "slots")
    check(gd.int(chrom, "support_type_000") == st.TYPE_NON_ROMANTIC == gd.int(fred, "support_type_000"), "type")
    check(pair_levels(gd, chrom, fred) == [1, 2, 3], pair_levels(gd, chrom, fred))
    check(len(gd.listing(chrom)) == 3 and gd.listing(chrom) == gd.listing(fred), "listed in both tables (missing table added)")
    check(r.numbers == [0, 1, 2], r.numbers)
    path = "m/クロム_フレデリク.bin.lz"
    check(r.archive == path and sorted(gd.enumerate_messages(path, True)) == sorted(
        [f"MID_支援_クロム_フレデリク_{x}" for x in "ＣＢＡ"]), gd.archives.get(path))
    check(gd.archives[path]["__title__"] == "MESS_ARCHIVE_クロム_フレデリク", "title")
    check(gd.message(path, True, "MID_支援_クロム_フレデリク_Ｃ") == st.starting_text("クロム", "フレデリク"), "text")
    check({"characters", "reliance_list"} <= gd.dirty, gd.dirty)

    # A man and a woman: Slow, with S; an existing file in the other order is used.
    gd.new_text_data("m/スミア_クロム.bin.lz", True)
    gd.set_message("m/スミア_クロム.bin.lz", True, "MID_支援_スミア_クロム_Ｃ", "$t1written$k")
    r = sl.add_support(gd, sumia, chrom)
    check(r.ok and gd.int(sumia, "support_type_000") == st.TYPE_SLOW, r)
    check(pair_levels(gd, chrom, sumia) == [1, 2, 3, 4], pair_levels(gd, chrom, sumia))
    check(r.archive == "m/スミア_クロム.bin.lz" and "m/クロム_スミア.bin.lz" not in gd.archives, r.archive)
    check(gd.message(r.archive, True, "MID_支援_スミア_クロム_Ｃ") == "$t1written$k", "existing text kept")
    check(len(gd.enumerate_messages(r.archive, True)) == 4, gd.archives[r.archive])
    check(r.numbers == [3, 4, 5, 6], r.numbers)

    rows = sl.supports_of(gd, chrom)
    check([s.partner for s in rows] == [fred, sumia] and rows[1].conversations == [1, 2, 3, 4], rows)
    check(all(s.partner_lists_owner for s in rows), "both sides")

    # Type change: Non-romantic drops the S conversation, Medium brings it back.
    sl.set_type(gd, chrom, sumia, st.TYPE_NON_ROMANTIC)
    check(gd.int(sumia, "support_type_000") == st.TYPE_NON_ROMANTIC and gd.int(chrom, "support_type_001") == st.TYPE_NON_ROMANTIC, "type both")
    check(pair_levels(gd, chrom, sumia) == [1, 2, 3], "S removed")
    sl.set_type(gd, chrom, sumia, 336464132)
    check(pair_levels(gd, chrom, sumia) == [1, 2, 3, 4], "S back")

    # Remove: slots on both sides and every listing; the text stays.
    r = sl.remove_support(gd, chrom, sumia)
    check(r.ok and gd.rid(chrom, "support_character_001") is None and gd.rid(sumia, "support_character_000") is None, "slots cleared")
    check(pair_levels(gd, chrom, sumia) == [] and len(gd.listing(sumia)) == 0, "conversations gone")
    check(pair_levels(gd, chrom, fred) == [1, 2, 3], "other support untouched")
    check("m/スミア_クロム.bin.lz" in gd.archives, "text kept")

    # Added again: fills the freed slot, new records, same file.
    r = sl.add_support(gd, chrom, sumia)
    check(r.slots == (1, 0) and pair_levels(gd, chrom, sumia) == [1, 2, 3, 4], r)
    print("add / type / remove: ok")


def test_fix_and_limits():
    gd = FakeData([("クロム", False), ("リズ", True), ("ガイア", False)])
    chrom, lissa, gaius = gd.chars
    wp.support_number_limit = lambda force=None: 1920
    # Only one side lists the other, with Medium, and nothing else: Fix keeps Medium.
    gd.set_rid(lissa, "support_character_000", gaius)
    gd.set_int(lissa, "support_type_000", 336464132)
    row = sl.supports_of(gd, lissa)[0]
    check(not row.partner_lists_owner and row.conversations == [], row)
    r = sl.repair_support(gd, lissa, gaius)
    check(r.ok and gd.rid(gaius, "support_character_000") == lissa and gd.int(gaius, "support_type_000") == 336464132, "fixed")
    check(pair_levels(gd, lissa, gaius) == [1, 2, 3, 4], "conversations")
    check(sl.add_support(gd, chrom, chrom).ok is False, "self")
    # Full list: the error names the character, nothing changes.
    for k in range(52):
        gd.set_rid(chrom, f"support_character_{k:03}", gaius)
    entry = st.slot_record(gd, chrom, 52)
    for k in range(52, 60):
        gd.set_rid(entry, f"support_character_{k:03}", gaius)
    before = len(gd.listing(lissa))
    r = sl.add_support(gd, lissa, chrom)
    check(not r.ok and "クロム" in r.message and len(gd.listing(lissa)) == before, r)
    print("fix and limits: ok")


def test_widget():
    from PySide6.QtWidgets import QApplication, QMessageBox

    app = QApplication.instance() or QApplication([])
    from paragon.unlimited.supports import support_list_widget as mod

    gd = FakeData([("クロム", False), ("リズ", True), ("ソワレ", True)])
    chrom, lissa, sully = gd.chars
    wp.support_number_limit = lambda force=None: 1920
    state = types.SimpleNamespace(main_state=None, game_state=types.SimpleNamespace(data=gd))
    w = mod.FE13SupportListWidget(state)
    w.set_target(chrom)
    check(w.table.rowCount() == 0 and w.partner_box.count() == 2, w.partner_box.count())
    w.partner_box.setCurrentIndex(w.partner_box.findData(sully))
    w._on_add()
    w.resize(980, 360)
    os.makedirs("qt_out", exist_ok=True)
    w.grab().save("qt_out/support_list.png")
    check(w.table.rowCount() == 1 and w.table.item(0, mod.COL_STATUS).text() == "OK", w.table.item(0, mod.COL_STATUS).text())
    check(w.table.item(0, mod.COL_RANKS).text() == "C B A S", w.table.item(0, mod.COL_RANKS).text())
    # One-sided support shows what is missing and Fix repairs it.
    gd.set_rid(lissa, "support_character_000", chrom)
    gd.set_int(lissa, "support_type_000", st.TYPE_NON_ROMANTIC)
    w.set_target(chrom)
    w.set_target(lissa)
    check(w.table.item(0, mod.COL_STATUS).text().startswith("Missing"), w.table.item(0, mod.COL_STATUS).text())
    w._on_fix(chrom)
    check(w.table.item(0, mod.COL_STATUS).text() == "OK", w.table.item(0, mod.COL_STATUS).text())
    QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)
    w._on_remove(chrom)
    check(w.table.rowCount() == 0 and gd.rid(chrom, "support_character_001") is None, "removed")
    print("widget: ok")


if __name__ == "__main__":
    test_add_remove()
    test_fix_and_limits()
    test_widget()
    print("ALL OK")
