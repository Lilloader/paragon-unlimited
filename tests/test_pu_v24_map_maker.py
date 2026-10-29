"""Paragon Unlimited v2.0: Map Maker (chapter slots, map templates, easy unit editing) and the
tutorial help. Runs without game files: the real template library, the real Map Maker window, and
a stand-in for the game data (so units are drawn as colored dots). The window runs offscreen."""
import copy
import os
import shutil
import sys
import tempfile
import types

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.chdir(os.path.join(os.path.dirname(__file__), ".."))

from paragon.core.services import fe13_chapter_maker as cm  # noqa: E402


def check(cond, what):
    if not cond:
        raise AssertionError(what)


# ----------------------------------------------------------------------------- pure checks
def test_templates():
    t = cm.Templates.load()
    maps = list(t.maps.values())
    check(len(maps) >= 70, f"{len(maps)} templates")
    tiers = {n: [m for m in maps if m["tier"] == n] for n in range(1, 7)}
    for n, ms in tiers.items():
        check(len(ms) >= 4, f"tier {n} has only {len(ms)} maps")
    for m in maps:
        w, h = m["size"]
        check(m["players"], f"{m['id']} has player starts")
        check(m["enemies"], f"{m['id']} has enemies")
        for (x, y) in m["players"]:
            check(0 <= x < w and 0 <= y < h, f"{m['id']} player start inside the map")
        for e in m["enemies"]:
            check(0 <= e["x"] < w and 0 <= e["y"] < h, f"{m['id']} enemy inside the map")
            check(e["cls"].startswith("JID_"), f"{m['id']} enemy class")
        check(m["theme"] in cm.THEMES, f"{m['id']} theme")
    print("templates:", len(maps), {n: len(v) for n, v in tiers.items()})


def test_text_and_script():
    lines = [cm.Line("クロム", "Normal", "Something feels off about this place. " * 3),
             cm.Line("フレデリク", "Angry", "Enemies ahead, milord."),
             cm.Line("リズ", "Happy", "Let's go!"),
             cm.Line("クロム", "Happy", "Shepherds, to arms!")]
    raw = cm.conversation(lines)
    check(raw.startswith("$t1$Wmクロム|3$Wmフレデリク|7"), raw[:40])
    check("$Wsリズ|" in raw and "$E笑,|" in raw, "speaker switch and mood")
    back = cm.parse_conversation(raw)
    check([l.speaker for l in back] == ["クロム", "フレデリク", "リズ", "クロム"], [l.speaker for l in back])
    check(back[0].text.startswith("Something feels off"), back[0].text)
    plan = cm.ChapterPlan(cid="U003", title="Snow Fight", opening=lines[:2], ending=lines[2:])
    src = cm.chapter_script(plan, True, "PID_U003_ボス", True, True, True)
    for needle in ("callback[0x7]()", "bev::U003_OP1();", "bev::U003_ED1();", 'ev::Talk("MID_U003_BOSS_DIE1")',
                   "ev::ChapterSetWinRule(262144);"):
        check(needle in src, needle)
    again = cm.plan_from_script(src)
    check(again.title == "Snow Fight" and again.opening[1].speaker == "フレデリク", "plan stored in the script")
    plan.win = "boss"
    js = cm.chapter_script(plan, True, None, False, False, False, True)
    check('callback[0xC](1, 1, 0)' in js and 'ev::Dispos("Join", 8);' in js, "joining characters appear on turn 1")
    check('"Join"' not in cm.chapter_script(plan, True, None, False, False, False), "no join event without joiners")
    check("ChapterSetWinRule(131072)" in cm.chapter_script(plan, True, "PID_U003_ボス", False, False, False),
          "defeat-the-boss rule")
    check(cm.SLOT_IDS == [f"U00{n}" for n in range(1, 10)] and cm.MAX_CHAPTERS - cm.GAME_CHAPTERS == 9, "9 slots")
    print("text + script: ok")


# ----------------------------------------------------------------------------- stand-ins
class FakeData:
    """Just enough of GameData for the window: every key exists, nothing has a sprite."""

    def __init__(self):
        self.written = 0

    def key_to_rid(self, table, key):
        return key or None

    def display(self, rid):
        return str(rid).replace("JID_", "").replace("IID_", "") if rid else None

    def rid(self, rid, field):
        return None

    def string(self, rid, field):
        return None

    def int(self, rid, field):
        return None

    def table(self, name):
        raise KeyError(name)

    def multi_open(self, store, key):
        raise KeyError(key)

    def file_exists(self, path, localized):
        return False

    def open_text_data(self, path, localized):
        pass

    def write(self):
        self.written += 1
        return types.SimpleNamespace(script_compile_result=None)


class FakeMaker(cm.ChapterMaker):
    GAME = [("003", "Chapter 3: Warrior Realm"), ("006", "Chapter 6: Emmeryn"), ("X001", "Paralogue 1: Lost Sister")]

    def __init__(self, gd):
        super().__init__(gd, cm.Templates.load(), None, None)
        self.chapters = {}
        self.saved = []
        self.written_units = []
        self.mini = bytes(((x * 7) % 256, (y * 5) % 256, 120, 255)[i] for y in range(256) for x in range(256)
                          for i in range(4))

    # chapter table
    def chapter_ids(self):
        return [c for c, _n in self.GAME] + list(self.chapters)

    def custom_chapters(self):
        return [{"cid": c, "row": 55 + i, "name": p.title, "made_here": True} for i, (c, p) in enumerate(self.chapters.items())]

    def free_rows(self):
        return 9 - len(self.chapters)

    def story_chapters(self):
        return list(self.GAME)

    def chapter_name(self, cid):
        return dict(self.GAME).get(cid) or (self.chapters[cid].title if cid in self.chapters else cid)

    def is_made_here(self, cid):
        return cid in self.chapters

    # map data
    def template_available(self, tid):
        return tid in self.templates.maps

    def minimap(self, cid):
        return 256, 256, self.mini

    def grid(self, cid):
        tid = self.chapters[cid].template if cid in self.chapters else cid
        t = self.templates.get(tid)
        if not t:
            return None
        w, h = t["size"]
        raw = bytearray(32 * 32)
        for y in range(32):
            for x in range(32):
                raw[y * 32 + x] = 1  # plains
        raw[0] = 7  # one water tile in the corner (fliers only)
        return w, h, bytes(raw)

    def tile_names(self):
        return ["", "Plains"] + ["Tile"] * 5 + ["Water"] + ["Tile"] * 70

    def enemy_classes(self):
        return [("Fighter", "JID_戦士男"), ("Mercenary (M)", "JID_傭兵男"), ("Pegasus Knight", "JID_ペガサスナイト女")]

    def joinable_characters(self):
        return [("Camilla", "PID_Camilla", "JID_戦士男"), ("Azura", "PID_Azura", "JID_ペガサスナイト女")]

    def speakers(self):
        return [("Your avatar (Robin)", "username"), ("Chrom", "クロム"), ("Frederick", "フレデリク")]

    def class_name(self, jid):
        return jid.replace("JID_", "")

    def other_unit_counts(self, cid):
        return {}

    # chapters
    def create_chapter(self, plan, render_title=None):
        if render_title is not None:
            rgba = render_title(plan.label, plan.title)
            check(len(rgba) == 256 * 64 * 4, "title card size")
        self.chapters[plan.cid] = copy.deepcopy(plan)
        return plan.cid

    def save_chapter(self, plan, render_title=None, new=False):
        self.chapters[plan.cid] = copy.deepcopy(plan)
        self.saved.append(plan.cid)

    def load_plan(self, cid):
        return copy.deepcopy(self.chapters[cid])

    def read_units(self, cid, mode="Normal"):
        return copy.deepcopy(self.chapters[cid].units) if cid in self.chapters else []

    def write_units(self, cid, units, mode="Normal", tier_hint=3, theme=None):
        self.written_units.append((cid, len(units)))

    def change_template(self, plan):
        pass


def mouse(canvas, kind, x, y, button=None):
    from PySide6.QtCore import QEvent, QPointF, Qt
    from PySide6.QtGui import QMouseEvent

    button = button or Qt.LeftButton
    pos = QPointF(x * cm_cell() + cm_cell() / 2, y * cm_cell() + cm_cell() / 2)
    t = {"press": QEvent.MouseButtonPress, "move": QEvent.MouseMove, "release": QEvent.MouseButtonRelease}[kind]
    held = Qt.NoButton if kind == "release" else button
    ev = QMouseEvent(t, pos, canvas.mapToGlobal(pos.toPoint()).toPointF(), button if kind != "move" else Qt.NoButton,
                     held, Qt.NoModifier)
    {"press": canvas.mousePressEvent, "move": canvas.mouseMoveEvent, "release": canvas.mouseReleaseEvent}[kind](ev)


def cm_cell():
    from paragon.ui.controllers import pu_map_maker as pm

    return pm.CELL


def test_window(tmp):
    from PySide6.QtWidgets import QApplication, QDialog, QMessageBox

    from paragon.ui.controllers import pu_map_maker as pm

    app = QApplication.instance() or QApplication([])
    problems = []
    pm.QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)
    pm.QMessageBox.information = staticmethod(lambda *a, **k: None)
    pm.QMessageBox.critical = staticmethod(lambda *a, **k: problems.append(a))
    gd = FakeData()
    gs = types.SimpleNamespace(data=gd, project=types.SimpleNamespace(output_path=tmp))
    maker = FakeMaker(gd)
    gs.pu_chapter_maker = maker
    os.makedirs("qt_out", exist_ok=True)

    w = pm.MapMaker(gs)
    w.resize(1400, 900)
    w.show()
    QApplication.processEvents()
    check(w.pages.currentIndex() == 0, "opens on the home page")
    check(w.fill_button.isEnabled(), "fill button on")
    check("0 of 9" in w.slot_info.text(), w.slot_info.text())
    w.grab().save("qt_out/v20_map_maker_home_empty.png")

    # template gallery: every template shows up, filters work
    g = pm.TemplateGallery(maker, "", w)
    g.resize(1000, 700)
    g.show()
    QApplication.processEvents()
    check(g.list.count() == len(maker.templates.maps), f"gallery shows {g.list.count()}")
    g.filter_tier.setCurrentIndex(1)  # very easy
    QApplication.processEvents()
    check(0 < g.list.count() < len(maker.templates.maps), "tier filter")
    g.filter_tier.setCurrentIndex(0)
    g.grab().save("qt_out/v20_map_gallery.png")
    g.close()

    # new chapter: the gallery returns the snow map from chapter 3
    class PickSnow(pm.TemplateGallery):
        def exec(self):
            self.chosen = "003"
            return QDialog.Accepted

    real_gallery = pm.TemplateGallery
    pm.TemplateGallery = PickSnow
    try:
        w.new_chapter()
    finally:
        pm.TemplateGallery = real_gallery
    QApplication.processEvents()
    check(not problems, problems)
    check(w.pages.currentIndex() == 1 and w.plan.cid == "U001", "editor opened for U001")
    check(w.plan.template == "003", w.plan.template)
    enemies = [u for u in w.plan.units if u.team == "enemy"]
    players = [u for u in w.plan.units if u.team == "player"]
    check(len(players) == len(maker.templates.get("003")["players"]), "player starts from the template")
    check(len(enemies) == len(maker.templates.get("003")["enemies"]), "enemies from the template")
    check(sum(u.boss for u in enemies) == 1, "exactly one boss")

    # drag an enemy one tile to a free spot
    occupied = {(u.x, u.y) for u in w.plan.units}
    mover = next(u for u in enemies if not u.boss and any(
        (u.x + dx, u.y) not in occupied and 0 <= u.x + dx < 23 for dx in (1, -1)))
    dx = 1 if (mover.x + 1, mover.y) not in occupied and mover.x + 1 < 23 else -1
    start = (mover.x, mover.y)
    mouse(w.canvas, "press", *start)
    mouse(w.canvas, "move", start[0] + dx, start[1])
    mouse(w.canvas, "release", start[0] + dx, start[1])
    check((mover.x, mover.y) == (start[0] + dx, start[1]), f"moved to {(mover.x, mover.y)}")
    check(w.dirty and w.undo_btn.isEnabled(), "undo available")
    w.undo()
    moved_back = next(u for u in w.plan.units if (u.x, u.y) == start)
    check(moved_back.team == "enemy", "undo puts it back")
    w.redo()
    check(any((u.x, u.y) == (start[0] + dx, start[1]) for u in w.plan.units), "redo")

    # add an enemy with the + Enemy tool on a free tile, then remove it with a right-click
    free = next((x, y) for y in range(17) for x in range(1, 23) if (x, y) not in {(u.x, u.y) for u in w.plan.units})
    w.canvas.tool = "enemy"
    n = len(w.plan.units)
    mouse(w.canvas, "press", *free)
    check(len(w.plan.units) == n + 1 and w.canvas.selected is w.plan.units[-1], "enemy added and selected")
    check(w.unit_class.isEnabled() and w.unit_level.value() >= 1, "unit box shows it")
    w.unit_level.setValue(17)
    check(w.plan.units[-1].level == 17, "level changed from the unit box")
    from PySide6.QtCore import Qt

    mouse(w.canvas, "press", *free, button=Qt.RightButton)
    check(len(w.plan.units) == n, "right-click removes")
    # water tile: only fliers
    w.canvas.tool = "enemy"
    w.new_class.setCurrentIndex(w.new_class.findData("JID_戦士男"))
    if (0, 0) not in {(u.x, u.y) for u in w.plan.units}:
        mouse(w.canvas, "press", 0, 0)
        check(len(w.plan.units) == n, "a fighter can't stand in water")
    w.canvas.tool = "move"

    # difficulty: brutal = promoted classes, high levels
    w.tier_slider.setValue(6)
    QApplication.processEvents()
    lv = [u.level for u in w.plan.units if u.team == "enemy" and not u.boss]
    check(min(lv) >= 15, f"brutal levels {min(lv)}")
    check(any("勇者" in u.job or "バーサーカー" in u.job or "ウォーリアー" in u.job or "ソードマスター" in u.job
              for u in w.plan.units if u.team == "enemy"), "promoted classes")
    w.tier_slider.setValue(1)
    QApplication.processEvents()
    check(max(u.level for u in w.plan.units if u.team == "enemy" and not u.boss) <= 3, "very easy levels")

    # ★ joins your army: Camilla on a free tile, once only
    free = next((x, y) for y in range(17) for x in range(1, 23) if (x, y) not in {(u.x, u.y) for u in w.plan.units})
    w.canvas.tool = "join"
    w.join_who.setCurrentIndex(w.join_who.findData("PID_Camilla"))
    check(w.join_who.isEnabled(), "join tool on in a Map Maker chapter")
    mouse(w.canvas, "press", *free)
    joiners = [u for u in w.plan.units if u.team == "join"]
    check(len(joiners) == 1 and joiners[0].pid == "PID_Camilla" and joiners[0].job == "JID_戦士男", "Camilla joins")
    check("Joins your army" in w.describe(joiners[0]), w.describe(joiners[0]))
    check("joining your army" in w.summary.text(), w.summary.text())
    free2 = next((x, y) for y in range(17) for x in range(1, 23) if (x, y) not in {(u.x, u.y) for u in w.plan.units})
    mouse(w.canvas, "press", *free2)
    check(len([u for u in w.plan.units if u.team == "join"]) == 1, "the same character only once")
    w.canvas.tool = "move"

    # story + name, then save
    w.title_edit.setText("The Frozen Pass")
    w.label_edit.setText("Side Story 1")
    w.opening.add_line(cm.Line("クロム", "Angry", "Brigands in the snow!"))
    w.boss_name.setText("Grisly Gus")
    w._boss_name_changed("Grisly Gus")
    check(w.save(), "saved")
    check(not problems, problems)
    saved = maker.chapters["U001"]
    check(saved.title == "The Frozen Pass" and saved.tier == 1, "plan saved")
    check(any(l.text == "Brigands in the snow!" for l in saved.opening), "story saved")
    check(next(u for u in saved.units if u.boss).name == "Grisly Gus", "boss name saved")
    check(any(u.team == "join" and u.pid == "PID_Camilla" for u in saved.units), "joining character saved")
    check(gd.written >= 1, "project written")
    w.tier_slider.setValue(4)
    QApplication.processEvents()
    w.grab().save("qt_out/v20_map_maker_editor.png")

    # back home, fill the other 8 slots
    w.dirty = False
    w.go_home()
    w.fill_all()
    from PySide6.QtCore import QEvent

    QApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    QApplication.processEvents()
    check(w.cards.count() == 9, f"{w.cards.count()} cards")
    check(len(maker.chapters) == 9 and maker.free_rows() == 0, f"{len(maker.chapters)} chapters")
    tiers = [p.tier for p in maker.chapters.values()]
    check(len(set(tiers)) >= 4, f"slots spread over difficulties {tiers}")
    check(not w.fill_button.isEnabled(), "no free slots left")
    w.grab().save("qt_out/v20_map_maker_home_full.png")
    w.close()
    print("map maker window: ok", tiers)


def test_help():
    from PySide6.QtWidgets import QApplication

    from paragon.ui import pu_help

    app = QApplication.instance() or QApplication([])
    topics = pu_help.load_topics("FE13")
    lessons = sorted((t["tutorial"], k) for k, t in topics.items() if t.get("tutorial"))
    check(len(lessons) >= 8 and [n for n, _k in lessons] == list(range(1, len(lessons) + 1)), lessons)
    check("map_maker" in topics, "map maker reference page")
    html = pu_help.topic_html("lesson_first_chapter")
    check("Next lesson" in html and "topic:lesson_edit_map" in html and "Lesson 2" in html, "lesson links")
    for _n, k in lessons:
        for link in __import__("re").findall(r"topic:([a-z_0-9]+)", topics[k]["body"]):
            check(link in topics, f"{k} links to missing {link}")
    check("colour" not in open("Data/FE13/PU_Help.yml", encoding="utf-8").read().lower(), "US spelling")
    dlg = pu_help.HelpDialog("FE13")
    dlg.show_topic("lesson_first_chapter")
    QApplication.processEvents()
    check("Make your first chapter" in dlg.text.toHtml(), "lesson shown")
    dlg._on_link(__import__("PySide6.QtCore", fromlist=["QUrl"]).QUrl("topic:lesson_edit_map"))
    check("Move, add and remove" in dlg.text.toHtml(), "next-lesson link works")
    dlg.show_topic("lesson_first_chapter")
    QApplication.processEvents()
    os.makedirs("qt_out", exist_ok=True)
    dlg.grab().save("qt_out/v20_help_lesson.png")
    dlg.close()
    print("help: ok", len(lessons), "lessons")


def main():
    tmp = tempfile.mkdtemp()
    try:
        test_templates()
        test_text_and_script()
        test_help()
        test_window(tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("v2.0 map maker test: all checks passed")


if __name__ == "__main__":
    main()
