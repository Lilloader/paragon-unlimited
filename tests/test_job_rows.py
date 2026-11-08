"""Moving / inserting / deleting classes keeps every character's sprite list in step
(paragon/unlimited/characters/job_rows.py, paragon/model/list_field_model.py). A small fake
data layer; the list model part runs offscreen when Qt is there."""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.chdir(os.path.join(os.path.dirname(__file__), ".."))

from paragon.unlimited.characters import job_rows


def check(cond, msg):
    if not cond:
        raise AssertionError(msg)


class FakeData:
    """6 classes A-F; two characters with sprite lists (one shorter than the class list)."""

    def __init__(self):
        self.rec, self.lists, self.next, self.dirty = {}, {}, 100, set()
        self.jobs_root, self.chars_root = self._new(), self._new()
        self.lists[(self.jobs_root, "jobs")] = [self._new(jid=f"JID_{c}") for c in "ABCDEF"]
        self.lists[(self.chars_root, "people")] = []
        for n in (6, 4):
            sd = self._new()
            self.lists[(sd, "entries")] = [self._new(bmap_icon=f"sprite_{c}") for c in "ABCDEF"[:n]]
            self.lists[(self.chars_root, "people")].append(self._new(sprite_data=sd))

    def _new(self, **f):
        self.next += 1
        self.rec[self.next] = dict(f)
        return self.next

    def table(self, name):
        return {"jobs": (self.jobs_root, "jobs"), "characters": (self.chars_root, "people")}.get(name)

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

    def list_insert(self, rid, f, i):
        r = self._new()
        self.lists[(rid, f)].insert(i, r)
        return r

    def list_insert_existing(self, rid, f, r, i):
        self.lists[(rid, f)].insert(i, r)

    def list_remove(self, rid, f, i):
        del self.lists[(rid, f)][i]

    def rid(self, rid, f):
        return self.rec[rid].get(f)

    def set_rid(self, rid, f, v):
        self.rec[rid][f] = v

    def key(self, rid):
        return self.rec[rid].get("jid")

    def display(self, rid):
        return self.key(rid)

    def set_store_dirty(self, s, v):
        (self.dirty.add if v else self.dirty.discard)(s)

    # helpers
    def jobs(self):
        return "".join((self.key(j) or "?")[-1] for j in self.items(self.jobs_root, "jobs"))

    def sprites(self, k):
        sd = self.rid(self.items(self.chars_root, "people")[k], "sprite_data")
        return [(self.rid(e, "bmap_icon") or "-")[-1] for e in self.items(sd, "entries")]


def in_step(d):
    jobs = d.jobs()
    for k in (0, 1):
        s = d.sprites(k)
        for i, c in enumerate(s):
            if c != "-" and (i >= len(jobs) or jobs[i] != c):
                return False
    return True


def test_job_rows():
    d = FakeData()
    check(job_rows.is_job_list(d, d.jobs_root, "jobs") and not job_rows.is_job_list(d, d.chars_root, "people"), "job list")
    # move E (row 4) to row 1, as the list does it
    jl = d.lists[(d.jobs_root, "jobs")]
    jl.insert(1, jl.pop(4))
    job_rows.moved(d, 4, 1)
    check(d.jobs() == "AEBCDF" and in_step(d) and "characters" in d.dirty, (d.jobs(), d.sprites(0), d.sprites(1)))
    check(d.sprites(1)[1] == "-", "the short list was made long enough first")
    jl.insert(2, d._new(jid="JID_X"))
    job_rows.inserted(d, 2)
    check(in_step(d) and d.sprites(0)[2] == "-", d.sprites(0))
    del jl[0]
    job_rows.removed(d, 0)
    check(d.jobs() == "EXBCDF" and in_step(d), (d.jobs(), d.sprites(0)))
    print("job rows: ok")


def test_list_model():
    try:
        from PySide6.QtCore import QByteArray, QMimeData, QModelIndex, Qt
        from PySide6.QtWidgets import QApplication
    except ImportError:
        print("class list model: skipped (no Qt)")
        return
    from paragon.model.list_field_model import ListFieldModel

    app = QApplication.instance() or QApplication([])

    class Icons:
        def icon(self, rid):
            return None

    d = FakeData()
    m = ListFieldModel(d, Icons(), d.jobs_root, "jobs")
    md = QMimeData()
    md.setData("application/paragon-model-row", QByteArray((4).to_bytes(8, "little")))
    asked = []
    m.confirm_job_move = lambda: asked.append(1) or False  # "No": nothing moves
    check(not m.dropMimeData(md, Qt.MoveAction, 1, 0, QModelIndex()) and d.jobs() == "ABCDEF" and asked, d.jobs())
    m.confirm_job_move = lambda: True
    check(m.dropMimeData(md, Qt.MoveAction, 1, 0, QModelIndex()), "drop")
    check(d.jobs() == "AEBCDF" and in_step(d), (d.jobs(), d.sprites(0)))
    md = QMimeData()
    md.setData("application/paragon-model-row", QByteArray((0).to_bytes(8, "little")))
    check(m.dropMimeData(md, Qt.MoveAction, -1, 0, QModelIndex()), "drop below the last row")
    check(d.jobs() == "EBCDFA" and in_step(d), d.jobs())
    check(m.moveRows(QModelIndex(), 5, 1, QModelIndex(), 0) and d.jobs() == "AEBCDF" and in_step(d), d.jobs())
    check(not m.moveRows(QModelIndex(), 2, 1, QModelIndex(), 3), "moving a row onto itself does nothing")
    m.insertRows(2, 1, QModelIndex())
    check(m.rowCount() == 7 and in_step(d) and d.sprites(0)[2] == "-", d.sprites(0))
    m.removeRows(0, 1, QModelIndex())
    check(in_step(d), d.sprites(0))
    n0 = len(d.sprites(0))
    m.add_item()
    check(len(d.sprites(0)) == n0, "adding a class at the end leaves the lists to the save")
    app.processEvents()
    print("class list model: ok")


if __name__ == "__main__":
    test_job_rows()
    test_list_model()
    print("job rows test: all checks passed")
