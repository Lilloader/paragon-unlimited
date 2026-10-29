"""Pure-Python tests for FE13WritePreprocessors using a fake GameData (no Rust/Qt needed)."""
import itertools, sys, os, types
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from paragon.core.services.fe13_write_preprocessors import FE13WritePreprocessors, DUMMY_PID, add_missing_partners
from paragon.core.services import fe13_support_ex

class FakeGD:
    def __init__(self):
        self.ids = itertools.count(1)
        self.rec = {}      # rid -> dict(type, fields)
        self.dirty = set()
        self.nodes = {}
    def new(self, typ, **f):
        r = next(self.ids); self.rec[r] = {"type": typ, **f}; return r
    # --- API subset used by the preprocessor
    def table(self, name): return (self.chars_root, "people") if name == "characters" else None
    def node(self, name): return types.SimpleNamespace(rid=self.nodes.get(name))
    def items(self, rid, f): return list(self.rec[rid].get(f) or [])
    def rid(self, rid, f): return self.rec[rid].get(f)
    def int(self, rid, f): return self.rec[rid].get(f)
    def key(self, rid): return self.rec[rid].get("pid")
    def display(self, rid): return self.rec[rid].get("pid")
    def store_number_of(self, rid): return 0
    def new_instance(self, typ, store): return self.new(typ, data=[])
    def set_rid(self, rid, f, v): self.rec[rid][f] = v; self.dirty.add("characters" if self.rec[rid]["type"] == "PUSupportEx" else "x")
    def set_int(self, rid, f, v): self.rec[rid][f] = v
    def list_add(self, rid, f):
        typ = "PUSupportEx" if self.rec[rid]["type"] == "PUSupportExFile" else "RelianceListPointer"
        r = self.new(typ, data=None); self.rec[rid].setdefault(f, []).append(r)
        if typ == "PUSupportEx": self.dirty.add("characters")
        return r
    def list_size(self, rid, f): return len(self.rec[rid].get(f) or [])
    def list_get(self, rid, f, i): return self.rec[rid][f][i]
    def list_remove(self, rid, f, i): del self.rec[rid][f][i]
    def set_store_dirty(self, s, d):
        if d: self.dirty.add(s)
        else: self.dirty.discard(s)
    def store_is_dirty(self, s): return s in self.dirty

def build(n_chars, n_tables, dummy_at):
    gd = FakeGD()
    people = []
    for i in range(n_chars):
        pid = DUMMY_PID if i == dummy_at else f"PID_C{i}"
        p = gd.new("Person", pid=pid, id=i)
        people.append(p)
    # A <-> B support in slots + a reliance entry
    for k in range(52):
        gd.rec[people[0]][f"support_character_{k:03}"] = people[1] if k == 0 else None
        gd.rec[people[0]][f"support_type_{k:03}"] = 0x63110304 if k == 0 else 0x63636363
        gd.rec[people[1]][f"support_character_{k:03}"] = people[0] if k == 0 else None
        gd.rec[people[1]][f"support_type_{k:03}"] = 0x63110304 if k == 0 else 0x63636363
    for p in people[2:]:
        for k in range(52):
            gd.rec[p][f"support_character_{k:03}"] = None; gd.rec[p][f"support_type_{k:03}"] = 0x63636363
    gd.support_ex = gd.new("PUSupportExFile", entries=[])
    gd.chars_root = gd.new("PersonFile", people=people, support_ex=gd.support_ex)
    tables = []
    d = gd.new("RelianceListData", character1=people[0], character2=people[1], support_type=0, support_level=1, support_number=0)
    gd.shared_entry = d
    for t in range(n_tables):
        entries = []
        if t in (0, 1):  # listed in both characters' tables, as in vanilla
            entries.append(gd.new("RelianceListDataPointer", data=d))
        rl = gd.new("RelianceList", data=entries)
        tables.append(gd.new("RelianceListPointer", data=rl))
    gd.nodes["reliance_list"] = gd.new("RelianceListFile", tables=tables)
    return gd

def test_pads_to_dummy_position():
    gd = build(n_chars=70, n_tables=61, dummy_at=68)
    rep = FE13WritePreprocessors().invoke(gd)
    tables = gd.items(gd.nodes["reliance_list"], "tables")
    assert len(tables) == 68, len(tables)
    assert all(gd.rid(t, "data") is not None for t in tables)
    assert "reliance_list" in gd.dirty
    assert rep.by_severity("fixed")

def test_vanilla_like_untouched():
    gd = build(n_chars=57, n_tables=53, dummy_at=53)
    rep = FE13WritePreprocessors().invoke(gd)
    assert len(gd.items(gd.nodes["reliance_list"], "tables")) == 53
    assert "reliance_list" not in gd.dirty
    assert not rep.by_severity("fixed") and not rep.by_severity("error"), rep.to_text()

def test_null_table_repaired():
    gd = build(n_chars=57, n_tables=53, dummy_at=53)
    t = gd.items(gd.nodes["reliance_list"], "tables")[5]; gd.rec[t]["data"] = None
    rep = FE13WritePreprocessors().invoke(gd)
    assert gd.rid(t, "data") is not None and rep.by_severity("fixed")

def test_missing_dummy_is_error():
    gd = build(n_chars=10, n_tables=10, dummy_at=-1)
    rep = FE13WritePreprocessors().invoke(gd)
    assert rep.by_severity("error")

def _vanilla():
    return build(n_chars=57, n_tables=53, dummy_at=53)

def test_ensure_entry_does_not_dirty():
    gd = _vanilla(); p = gd.items(gd.chars_root, "people")[2]
    e = fe13_support_ex.ensure_entry(gd, p)
    assert e and gd.rid(e, "owner") == p and "characters" not in gd.dirty
    assert fe13_support_ex.ensure_entry(gd, p) == e  # reused, not duplicated
    assert gd.int(e, "support_type_052") == 0x63636363

def test_extra_slots_counted_and_empty_dropped():
    gd = _vanilla(); people = gd.items(gd.chars_root, "people")
    a, b, c = people[0], people[1], people[2]
    ea = fe13_support_ex.ensure_entry(gd, a)
    gd.set_rid(ea, "support_character_052", c); gd.rec[ea]["support_type_052"] = 0x63110304
    ec = fe13_support_ex.ensure_entry(gd, c)
    gd.set_rid(ec, "support_character_052", a); gd.rec[ec]["support_type_052"] = 0x63110304
    fe13_support_ex.ensure_entry(gd, people[3])           # empty -> removed on save
    gd.set_store_dirty("characters", True)
    rep = FE13WritePreprocessors().invoke(gd)
    owners = [gd.rid(e, "owner") for e in fe13_support_ex.entries(gd)]
    assert owners == [a, c], owners
    assert [k for k, *_ in fe13_support_ex.all_slots(gd, a)] == [0, 52]
    txt = rep.to_text()
    assert "extra slots #052-#059" in txt and "not the other way round" not in txt, txt

def test_one_sided_extra_slot_warned():
    gd = _vanilla(); people = gd.items(gd.chars_root, "people")
    ea = fe13_support_ex.ensure_entry(gd, people[0])
    gd.set_rid(ea, "support_character_055", people[4]); gd.rec[ea]["support_type_055"] = 0x63110304
    rep = FE13WritePreprocessors().invoke(gd)
    assert "not the other way round" in rep.to_text()

def test_orphan_entry_removed():
    gd = _vanilla(); people = gd.items(gd.chars_root, "people")
    e = fe13_support_ex.ensure_entry(gd, people[5]); gd.set_rid(e, "support_character_052", people[6])
    gd.rec[e]["owner"] = None
    rep = FE13WritePreprocessors().invoke(gd)
    assert fe13_support_ex.entries(gd) == [] and rep.by_severity("fixed")

def test_add_missing_partners():
    gd = _vanilla(); people = gd.items(gd.chars_root, "people")
    a, b, c = people[2], people[3], people[4]
    gd.rec[a]["support_character_000"] = b; gd.rec[a]["support_type_000"] = 0x63110304
    gd.rec[a]["support_character_001"] = c; gd.rec[a]["support_type_001"] = 0x16100A05
    gd.rec[c]["support_character_005"] = a  # placeholder: listed with "None"
    full = people[5]
    for k in range(52):
        # A real support type: 52 copies of one partner with type None are placeholder slots,
        # which the save clears since v1.9.
        gd.rec[full][f"support_character_{k:03}"] = people[6]; gd.rec[full][f"support_type_{k:03}"] = 0x63110304
    gd.rec[a]["support_character_002"] = full; gd.rec[a]["support_type_002"] = 0x63110304
    rep = FE13WritePreprocessors().invoke(gd)
    added, failed = add_missing_partners(gd, rep.one_sided)
    assert not failed, failed
    assert gd.rec[b]["support_character_000"] == a and gd.rec[b]["support_type_000"] == 0x63110304
    assert gd.rec[c]["support_type_005"] == 0x16100A05  # placeholder slot updated, not duplicated
    e = fe13_support_ex.find_entry(gd, full)
    assert e and gd.rid(e, "support_character_052") == a  # base slots full -> Unlimited slot
    assert not FE13WritePreprocessors().invoke(gd).one_sided

def test_sync_reliance_pairs():
    gd = _vanilla()
    tables = gd.items(gd.nodes["reliance_list"], "tables")
    t0 = gd.rid(tables[0], "data")
    gd.rec[t0]["data"] = []  # entry now only in character 1's table
    rep = FE13WritePreprocessors().invoke(gd)
    assert [gd.rid(p, "data") for p in gd.items(t0, "data")] == [gd.shared_entry]
    assert "reliance_list" in gd.dirty and rep.by_severity("fixed")

if __name__ == "__main__":
    for n, f in list(globals().items()):
        if n.startswith("test_"): f(); print("PASS", n)
