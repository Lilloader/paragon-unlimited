"""Map Maker (chapter slots, map templates, easy unit editing) and the
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

from paragon.unlimited.map_maker import chapter_builder as cm


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


def test_win_conditions():
    from paragon.unlimited.map_maker import chapter_events as ce

    plan = cm.ChapterPlan(cid="U004", win="seize", seize=[5, 7])
    src = cm.chapter_script(plan, True, "PID_U004_ボス", False, False, False)
    check("ev::ChapterSetWinRule(65536);" in src, "seize starts with the mission-banner bit, no win rule")
    check('callback[0x10](5, 7, 5, 7, 0, "")' in src, "seize tile event")
    block = src[src.index('callback[0x10](5, 7'):]
    check("ev::UnitGetForce(v0) == 0" in block and "ev::ForceUnitDelete(1);" in block
          and "ev::ChapterSetWinRule(131072);" in block and 'ev::FlagSet("PU_WIN");' in block, block)
    check('ev::FlagEntry("PU_WIN");' in src, "seize flag registered")
    plan.seize_who = "PID_クロム"
    check('ev::UnitIsPID(v0, "PID_クロム")' in cm.chapter_script(plan, True, None, False, False, False), "only Chrom")
    plan.seize = []
    check("ChapterSetWinRule(131072);" in cm.chapter_script(plan, True, None, False, False, False).split("callback[0x8]")[0],
          "seize without a tile falls back to rout")

    plan = cm.ChapterPlan(cid="U004", win="survive", survive_turns=6)
    src = cm.chapter_script(plan, True, None, False, False, False)
    check("ev::ChapterSetWinRule(65536);" in src and "callback[0xC](7, 7, 0)" in src, "survive 6 turns -> turn 7")
    check(src.count("ev::ForceUnitDelete(1);") == 1 and "PU_WIN" not in src, "one victory, no flag")
    # a turn conversation on the same turn: one callback, the conversation first
    plan.turn_events = [ce.TurnEvent(turn=7)]
    src = cm.chapter_script(plan, True, None, False, False, False, event_messages={"MID_U004_PU_TURN1": "x"})
    check(src.count("callback[0xC](7, 7, 0)") == 1, "merged into the turn conversation")
    cb = src[src.index("callback[0xC](7, 7, 0)"):]
    check(cb.index('ev::Talk("MID_U004_PU_TURN1")') < cb.index("ev::ForceUnitDelete(1);"), "talk, then victory")
    again = cm.plan_from_script(src)
    check(again.win == "survive" and again.survive_turns == 6, "win settings kept in the plan")
    check(set(cm.WIN_KINDS) == {"rout", "boss", "seize", "survive"}, cm.WIN_KINDS)
    # the banner at the start of the battle (game code patch): text, and the picture files
    from paragon.unlimited.map_maker import mission_banner as mb

    check(mb.text_of(again) == "Survive 6 turns", mb.text_of(again))
    check(mb.text_of(cm.ChapterPlan(win="seize", seize=[1, 1])) == "Seize the goal", "seize text")
    check(mb.text_of(cm.ChapterPlan(win="seize", banner=" Take the fort ")) == "Take the fort", "own text")
    check(mb.paths("U004") == ("telop/Tlp_PUM_U004.r.lz", "telop/Tlp_PUM_U004_E.r.lz"), mb.paths("U004"))
    files = {}
    check(not mb.write(files, lambda p: None, again, lambda t: None) and not files, "no game banner: nothing")
    # chapters saved by earlier versions (rule bits the wrong way round) are corrected on save
    from paragon.unlimited.saving import save_checks as sc

    plan = cm.ChapterPlan(cid="U001")
    good = cm.chapter_script(plan, True, None, False, False, False)
    check(sc.fixed_win_rule(good) is None, "a current rout chapter is left alone")
    check(sc.fixed_win_rule(good.replace("WinRule(131072)", "WinRule(262144)")) == good, "old rout chapter fixed")
    plan.win = "boss"
    good = cm.chapter_script(plan, True, "PID_U001_ボス", False, False, False)
    check(sc.fixed_win_rule(good) is None, "a current boss chapter is left alone")
    check(sc.fixed_win_rule(good.replace("WinRule(262144)", "WinRule(131072)")) == good, "old boss chapter fixed")
    print("win conditions: ok")


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
                   "ev::ChapterSetWinRule(131072);"):
        check(needle in src, needle)
    again = cm.plan_from_script(src)
    check(again.title == "Snow Fight" and again.opening[1].speaker == "フレデリク", "plan stored in the script")
    plan.win = "boss"
    js = cm.chapter_script(plan, True, None, False, False, False, True)
    check('callback[0xC](1, 1, 0)' in js and 'ev::Dispos("Join", 8);' in js, "joining characters appear on turn 1")
    check('"Join"' not in cm.chapter_script(plan, True, None, False, False, False), "no join event without joiners")
    check("ChapterSetWinRule(262144)" in cm.chapter_script(plan, True, "PID_U003_ボス", False, False, False),
          "defeat-the-boss rule")
    check("ChapterSetWinRule(131072)" in cm.chapter_script(plan, True, None, False, False, False),
          "defeat-the-boss without a boss falls back to rout")
    print("text + script: ok")
    check(cm.SLOT_IDS == [f"U00{n}" for n in range(1, 10)] and cm.MAX_CHAPTERS - cm.GAME_CHAPTERS == 9, "9 slots")
    # green allies: their faction is placed when the chapter loads (the game only places factions the
    # script names); joiners and enemies are not listed twice
    plan.units = [cm.Unit(team="ally", x=1, y=1, character="PID_リズ"), cm.Unit(team="ally", x=2, y=1, faction="Ally02"),
                  cm.Unit(team="join", x=3, y=1, pid="PID_ドニ"), cm.Unit(team="enemy", x=4, y=1)]
    check(cm.ally_factions(plan) == ["Support01", "Ally02"], cm.ally_factions(plan))
    asrc = cm.chapter_script(plan, True, None, False, False, False, True)
    load = asrc[asrc.index("callback[0x7]()"):asrc.index("callback[0x8]()")]
    check('ev::Dispos("Support01", 4);' in load and 'ev::Dispos("Ally02", 4);' in load and '"Join"' not in load, load)
    check(asrc.count(cm.JOIN_CALLBACK.split("\n")[1]) == 1, "join callback once")
    check(cm.MOODS["Blush"] == "通常,頬" and "$E苦,頬|" in cm.conversation([cm.Line("クロム", "Flustered", "Mother!")]),
          "blush moods")


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

    def write_file(self, path, blob):
        self.files_written = getattr(self, "files_written", []) + [path]

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
        # a plain grass field (the screenshots in the lessons are taken from these renders)
        px = bytearray()
        for y in range(256):
            for x in range(256):
                n = ((x * 73856093) ^ (y * 19349663)) % 23
                px += bytes((86 + n, 132 + n * 2, 60 + n // 2, 255))
        self.mini = bytes(px)

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

    def is_legacy(self, cid):
        return False

    def world_map_layout(self):
        nodes = {"003": (343, 101), "006": (365, 159), "X001": (402, 195), "001": (347, 153), "016": (104, 89)}
        names = {k: dict(self.GAME).get(k, k) for k in nodes}
        return {"nodes": nodes, "routes": [("001", "003"), ("003", "006"), ("003", "X001")], "names": names}

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
        return [("Tessa", "PID_Tessa", "JID_戦士男"), ("Arlen", "PID_Arlen", "JID_ペガサスナイト女")]

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

    # details, terrain, chests
    def item_choices(self):
        return [("Iron Sword", "IID_鉄の剣"), ("Silver Sword", "IID_銀の剣"), ("Vulnerary", "IID_傷薬"),
                ("Master Seal", "IID_マスタープルフ")]

    def skill_choices(self):
        return [("HP +5", "RSID_最大ＨＰ＋５"), ("Strength +2", "RSID_力＋２"), ("Vantage", "RSID_先の先")]

    def class_stats(self, jid):
        return [20, 6, 0, 5, 5, 2, 4, 1], [60, 30, 25, 30, 30, 30, 30, 25]

    def set_tile(self, cid, x, y, tile):
        self.tiles = getattr(self, "tiles", {})
        self.tiles[(cid, x, y)] = tile
        return True

    def clear_chapter(self, plan, render_title=None):
        self.cleared = getattr(self, "cleared", []) + [plan.cid]
        self.chapters[plan.cid] = copy.deepcopy(plan)
        return plan.cid

    def delete_chapter(self, cid):
        self.chapters.pop(cid)

    def chapters_after(self, cid):
        return [c for c, p in self.chapters.items() if p.unlock_after == cid]

    def save_existing(self, cid, units, mode="Normal", treasures=None, painted=None, treasures_changed=False):
        self.existing = (cid, len(units), dict(painted or {}), treasures_changed)


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
    from paragon.unlimited.map_maker import map_maker_window as pm

    return pm.CELL


def test_window(tmp):
    from PySide6.QtWidgets import QApplication, QDialog, QMessageBox

    from paragon.unlimited.map_maker import map_maker_window as pm

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
    check(w.details.cls.isEnabled() and w.details.level.value() >= 1, "unit box shows it")
    w.details.level.setValue(17)
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
    # win conditions: seize shows the tile row, the tile is picked on the map; survive shows the turns
    w.win_combo.setCurrentIndex(w.win_combo.findData("seize"))
    check(w._win_form.isRowVisible(w.seize_box) and not w._win_form.isRowVisible(w.survive_turns), "seize row")
    check("needs a tile" in w.summary.text(), "seize without a tile is flagged")
    w.seize_pick.setChecked(True)
    n = len(w.plan.units)
    mouse(w.canvas, "press", *free)
    check(w.plan.seize == list(free) and len(w.plan.units) == n and not w.seize_pick.isChecked(), "seize tile picked")
    check(str(free[0]) in w.seize_label.text() and "needs a tile" not in w.summary.text(), w.seize_label.text())
    QApplication.processEvents()
    w.grab().save("qt_out/v24_map_maker_seize.png")
    w.undo()
    check(w.plan.seize == [], "undo the seize tile")
    w.redo()
    w.win_combo.setCurrentIndex(w.win_combo.findData("survive"))
    check(w._win_form.isRowVisible(w.survive_turns) and not w._win_form.isRowVisible(w.seize_box), "survive row")
    w.survive_turns.setValue(5)
    w._collect_plan()
    check(w.plan.win == "survive" and w.plan.survive_turns == 5 and w.plan.seize == list(free), "win settings collected")
    check(w._win_form.isRowVisible(w.banner_edit) and w.banner_edit.placeholderText() == "Survive 5 turns",
          w.banner_edit.placeholderText())
    img = pm.render_banner("Survive 5 turns")
    check(img.size == (256, 32) and img.convert("L").getextrema() == (0, 255), "banner text: white on black")
    img.resize((768, 96)).save("qt_out/v25_mission_banner.png")
    w.win_combo.setCurrentIndex(w.win_combo.findData("rout"))
    check(not w._win_form.isRowVisible(w.banner_edit), "no banner row for rout")
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

    # ★ joins your army: Tessa on a free tile, once only
    free = next((x, y) for y in range(17) for x in range(1, 23) if (x, y) not in {(u.x, u.y) for u in w.plan.units})
    w.canvas.tool = "join"
    w.join_who.setCurrentIndex(w.join_who.findData("PID_Tessa"))
    check(w.join_who.isEnabled(), "join tool on in a Map Maker chapter")
    mouse(w.canvas, "press", *free)
    joiners = [u for u in w.plan.units if u.team == "join"]
    check(len(joiners) == 1 and joiners[0].pid == "PID_Tessa" and joiners[0].job == "JID_戦士男", "Tessa joins")
    check("Joins your army" in w.describe(joiners[0]), w.describe(joiners[0]))
    check("joining your army" in w.summary.text(), w.summary.text())
    free2 = next((x, y) for y in range(17) for x in range(1, 23) if (x, y) not in {(u.x, u.y) for u in w.plan.units})
    mouse(w.canvas, "press", *free2)
    check(len([u for u in w.plan.units if u.team == "join"]) == 1, "the same character only once")
    w.canvas.tool = "move"

    details_and_events(w, maker)

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
    check(any(u.team == "join" and u.pid == "PID_Tessa" for u in saved.units), "joining character saved")
    check(gd.written >= 1, "project written")
    check("telop/Tlp_PU_U001_1.r.lz" in getattr(gd, "files_written", []), "your picture is written with the project")
    check(len(saved.talks) == 1 and saved.talks[0].recruit, "talk event saved")
    check(len(saved.turn_events) == 1 and len(saved.tile_events) == 1, "turn and tile events saved")
    check(any(t.item == "IID_銀の剣" for t in saved.treasures), "chest saved")
    check(any(k[0] == "U001" and v == 7 for k, v in maker.tiles.items()), "painted tiles written")
    w.tier_slider.setValue(4)
    QApplication.processEvents()
    w.grab().save("qt_out/v20_map_maker_editor.png")

    clear_chapter(w, maker)

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
    # any chapter of your own can be deleted (with a warning); the slot is free again
    from PySide6.QtWidgets import QPushButton

    from paragon.unlimited.map_maker import map_maker_window as pm

    dels = [b for b in w.findChildren(QPushButton) if b.text() == "Delete" and b.isVisible()]
    check(len(dels) == 9, f"{len(dels)} delete buttons")
    real_warn = pm.QMessageBox.warning
    pm.QMessageBox.warning = staticmethod(lambda *a, **k: QMessageBox.Yes)
    try:
        w.delete_chapter("U009")
    finally:
        pm.QMessageBox.warning = real_warn
    QApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    QApplication.processEvents()
    check("U009" not in maker.chapters and w.fill_button.isEnabled(), "deleted, slot free")
    w.grab().save("qt_out/v20_map_maker_home_full.png")
    w.close()
    print("map maker window: ok", tiers)


def details_and_events(w, maker):
    """Unit details (stats, items, skills, quotes, character), player starts, terrain, chests, events."""
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication, QDialog

    from paragon.unlimited.map_maker import chapter_events as ce
    from paragon.unlimited.map_maker import map_maker_details as md

    d = w.details
    enemy = next(u for u in w.plan.units if u.team == "enemy" and not u.boss)
    mouse(w.canvas, "press", enemy.x, enemy.y)
    mouse(w.canvas, "release", enemy.x, enemy.y)
    check(d.unit is enemy, "panel shows the clicked enemy")
    # one page like Paragon's spawn editor
    for key in ("core", "unit", "stats", "skills", "items", "flags", "ai", "quotes", "misc"):
        check(not d.sections[key].isHidden(), f"{key} section shown for an enemy")
    # stats
    check(d.stat_base[0].text() == "20", "class base shown")
    d.stats_own.setChecked(True)
    d.stat_spin[1].setValue(4)
    check(enemy.stats is not None and enemy.stats[1] == 4, f"stat bonus {enemy.stats}")
    check(d.stat_total[1].text() == "<b>10</b>", d.stat_total[1].text())
    QApplication.processEvents()
    w.grab().save("qt_out/v22_unit_stats.png")
    # items + drops
    md.set_combo(d.item_boxes[0], "IID_銀の剣")
    md.set_combo(d.item_boxes[1], "IID_傷薬")
    d.drop_boxes[1].setChecked(True)
    d._items_changed()
    check(enemy.items[:2] == ["IID_銀の剣", "IID_傷薬"] and enemy.drops[:2] == [False, True], (enemy.items, enemy.drops))
    check(d.bit_edits[1].text() == "01 01 01 01", d.bit_edits[1].text())
    # item bitflags typed by hand: the drop box follows
    d.bit_edits[1].setText("00 01 01 03")
    d._raw_hex_changed("item_bitflags_2", d.bit_edits[1])
    check(enemy.drops[1] is False and enemy.raw_edits["item_bitflags_2"] == [0, 1, 1, 3], enemy.raw_edits)
    check(not d.drop_boxes[1].isChecked(), "drop box follows the bitflags")
    # spawn flags: Can't move (flags 2, 0x10); the boss box follows flags 2 as well
    d.flags2.boxes[4].setChecked(True)
    check(enemy.raw_edits["spawn_flags_2"] & 0x10, enemy.raw_edits)
    d.flags2.boxes[3].setChecked(True)
    check(enemy.boss and d.boss.isChecked(), "Boss (?) flag makes it the boss")
    d.flags2.boxes[3].setChecked(False)
    check(not enemy.boss, "and back")
    # AI: a value typed in the AI fields makes the behavior Custom; a preset puts the preset back
    d.ai["mission"].setEditText("AI_MI_Treasure")
    d._ai_changed("mission")
    check(enemy.behavior == "custom" and d.behavior.currentData() == "custom", enemy.behavior)
    d.behavior.setCurrentIndex(d.behavior.findData("stay"))
    d._behavior_changed()
    check(enemy.behavior == "stay" and "mission" not in enemy.raw_edits, enemy.raw_edits)
    check(d.ai["move"].currentText() == "AI_MV_Null", d.ai["move"].currentText())
    # misc: wrong hex is refused
    d.misc["unknown_1"].setText("zz")
    d._raw_hex_changed("unknown_1", d.misc["unknown_1"])
    check("unknown_1" not in enemy.raw_edits, "bad hex refused")
    QApplication.processEvents()
    w.grab().save("qt_out/v22_unit_items.png")
    # skills
    md.set_combo(d.skill_boxes[0], "RSID_先の先")
    d.skill_boxes[0].activated.emit(0)
    check(enemy.skills == ["RSID_先の先"] and enemy.own, enemy.skills)
    # name + portrait + quotes
    d.name.setText("Gruff")
    d._name_changed()
    md.set_combo(d.face, "FID_クロム")
    d._face_changed()
    check(enemy.name == "Gruff" and enemy.face == "FID_クロム", (enemy.name, enemy.face))
    d._add_quote_row({"vs": "", "text": "You'll fall here!"}, False)
    d._add_quote_row({"vs": "PID_Arlen", "text": "Arlen! Traitor!"}, False)
    d._quotes_changed()
    check(len(enemy.quotes) == 2 and enemy.quotes[1]["vs"] == "PID_Arlen", enemy.quotes)
    QApplication.processEvents()
    w.grab().save("qt_out/v22_unit_quotes.png")
    # undo the quotes, redo
    w.undo()
    enemy2 = next(u for u in w.plan.units if (u.x, u.y) == (enemy.x, enemy.y) and u.team == "enemy")
    check(len(enemy2.quotes) == 0, "undo takes the quotes back")
    w.redo()
    enemy = next(u for u in w.plan.units if (u.x, u.y) == (enemy2.x, enemy2.y) and u.team == "enemy")
    check(len(enemy.quotes) == 2 and enemy.stats[1] == 4, "redo")
    check(enemy.raw_edits.get("spawn_flags_2", 0) & 0x10, "undo / redo keep the spawn fields")
    # an enemy who is a real character (to recruit)
    other = next(u for u in w.plan.units if u.team == "enemy" and not u.boss and u is not enemy)
    w.canvas.selected = other
    w.show_unit(other)
    md.set_combo(d.character, "PID_Tessa")
    d._character_changed()
    check(other.character == "PID_Tessa" and other.pid == "PID_Tessa" and other.job == "JID_戦士男",
          (other.character, other.pid, other.job))
    check(d.sections["stats"].isHidden() and d.sections["skills"].isHidden(), "a character keeps their own stats and skills")
    # player start: who starts there, always deployed
    p = next(u for u in w.plan.units if u.team == "player")
    w.canvas.selected = p
    w.show_unit(p)
    check(not d.start.isHidden() and d.sections["unit"].isHidden() and not d.sections["flags"].isHidden(), "player controls")
    md.set_combo(d.start, "PID_Arlen")
    d._start_changed()
    d.forced.setChecked(True)
    check(p.pid == "PID_Arlen" and p.forced, (p.pid, p.forced))
    check(d.flags1.boxes[1].isChecked(), "Forced Unit flag follows Always deployed")
    d.flags1.boxes[1].setChecked(False)
    check(not p.forced and not d.forced.isChecked(), "and the other way")
    d.forced.setChecked(True)
    QApplication.processEvents()
    w.grab().save("qt_out/v22_player_start.png")
    p.forced = False  # so the test can still remove units later

    # terrain: paint two water tiles in one stroke (one undo step)
    free = [(x, y) for y in range(1, 17) for x in range(1, 22)
            if (x, y) not in {(u.x, u.y) for u in w.plan.units} and (x + 1, y) not in {(u.x, u.y) for u in w.plan.units}]
    tx, ty = free[0]
    w.canvas.tool = "terrain"
    w.paint_tile_box.setCurrentIndex(w.paint_tile_box.findData(7))
    n_undo = len(w.undo_stack)
    mouse(w.canvas, "press", tx, ty)
    from PySide6.QtCore import QEvent, QPointF
    from PySide6.QtGui import QMouseEvent

    pos = QPointF((tx + 1) * pm_cell() + 5, ty * pm_cell() + 5)
    w.canvas.mouseMoveEvent(QMouseEvent(QEvent.MouseMove, pos, pos, Qt.NoButton, Qt.LeftButton, Qt.NoModifier))
    mouse(w.canvas, "release", tx + 1, ty)
    check(w.canvas.painted == {(tx, ty): 7, (tx + 1, ty): 7}, w.canvas.painted)
    check(w.canvas.grid[2][ty * 32 + tx] == 7, "grid changed")
    check(len(w.undo_stack) == n_undo + 1, "one undo step per stroke")
    w.undo()
    check(w.canvas.painted == {} and w.canvas.grid[2][ty * 32 + tx] == 1, "undo paint")
    w.redo()
    check(len(w.canvas.painted) == 2, "redo paint")

    # chest: click a plain tile, the dialog gives a Silver Sword; the tile becomes a chest
    cx, cy = free[3]

    def accept_treasure(self):
        md.set_combo(self.item, "IID_銀の剣")
        self.gold.setValue(300)
        return QDialog.Accepted

    real = md.TreasureDialog.exec
    md.TreasureDialog.exec = accept_treasure
    try:
        w.canvas.tool = "treasure"
        mouse(w.canvas, "press", cx, cy)
    finally:
        md.TreasureDialog.exec = real
    check(len(w.plan.treasures) == 1 and w.plan.treasures[0].item == "IID_銀の剣" and w.plan.treasures[0].gold == 300,
          w.plan.treasures)
    check(w.canvas.painted.get((cx, cy)) in ce.CHEST_TILES, "chest tile painted")
    check(w.events.lists["treasures"][0].count() == 1, "chest listed")
    dlg = md.TreasureDialog(maker, ce.Treasure(cx, cy, ce.VILLAGE_KIND, ce.VILLAGE_MODEL, "IID_傷薬", 0,
                                                [cm.Line("クロム", "Normal", "Take this.")]), True, w)
    dlg.show()
    QApplication.processEvents()
    dlg.grab().save("qt_out/v22_village_dialog.png")
    check(dlg.talk.isVisible() and dlg.result_treasure().lines[0].text == "Take this.", "village talk")
    dlg.close()

    # tile event: Arlen waits on a tile -> conversation, Master Seal and gold
    ex, ey = free[6]

    def accept_tile(self):
        md.set_combo(self.who, "PID_Arlen")
        md.set_combo(self.item, "IID_マスタープルフ")
        self.gold.setValue(1000)
        self.talk.add_line(cm.Line("クロム", "Smile", "Look what Arlen found!"))
        self.scene.add_step(ce.SceneStep("Tlp_Ev_c040", [cm.Line("クロム", "Normal", "Let me try it on.")]))
        self.scene.add_step(ce.SceneStep("", [cm.Line("クロム", "Smile", "How do I look?\nBe honest.")],
                                         "SE_BTL_EFF_CHANGE_FOOT2"))
        self.after.add_line(cm.Line("フレデリク", "Normal", "Milord...?"))
        return QDialog.Accepted

    real = md.TileEventDialog.exec
    md.TileEventDialog.exec = accept_tile
    try:
        w.canvas.tool = "event"
        mouse(w.canvas, "press", ex, ey)
    finally:
        md.TileEventDialog.exec = real
    e = w.plan.tile_events[0]
    check((e.x, e.y, e.who, e.item, e.gold) == (ex, ey, "PID_Arlen", "IID_マスタープルフ", 1000) and e.lines, e)
    check("Event" in w.marks_text(ex, ey), w.marks_text(ex, ey))
    check(e.sparkle, "sparkle on by default")
    from types import SimpleNamespace as NS

    code = "\n".join(ce.event_script(NS(cid="U001", talks=[], quotes=[], turn_events=[], tile_events=[e], treasures=[]),
                                     {"MID_U001_PU_EV1": "x"}))
    check(f'callback[0x10]({e.x}, {e.y}, {e.x}, {e.y}, 0, "")' in code and 'EffectPlay3D("スポット異界の門"' in code
          and "callback[0xE](1, -1, 0)" in code and 'ev::TurnGet() + 5' in code and f"CameraSetPosition({e.x}, {e.y})" in code
          and ce.event_variables(NS(cid="U001", tile_events=[e])) == ["PU_NX1"], code)
    e3 = copy.deepcopy(e)
    e3.flash_every = 0
    check("callback[0xE]" not in "\n".join(ce.event_script(NS(cid="U001", talks=[], quotes=[], turn_events=[],
                                                              tile_events=[e3], treasures=[]), {})), "never flash")
    check(ce.flashes(NS(cid="E022"), e) == 0, "no flash in the DLC")
    check([s.picture for s in e.scene] == ["Tlp_Ev_c040", ""] and e.scene[1].sound == "SE_BTL_EFF_CHANGE_FOOT2"
          and e.scene[1].lines[0].text == "How do I look?\nBe honest." and e.after, e.scene)
    check("scene" in w.events.lists["tile_events"][0].item(0).text(), "scene shown in the list")

    # talk (recruit Tessa) and a turn conversation
    def accept_talk(self):
        md.set_combo(self.a, "PID_Arlen")
        md.set_combo(self.b, "PID_Tessa")
        self.recruit.setChecked(True)
        self.talk.add_line(cm.Line("クロム", "Normal", "Join us!"))
        return QDialog.Accepted

    def accept_turn(self):
        self.turn.setValue(3)
        self.talk.add_line(cm.Line("フレデリク", "Normal", "Reinforcements!"))
        return QDialog.Accepted

    for cls, fn, kind in ((md.TalkDialog, accept_talk, "talks"), (md.TurnDialog, accept_turn, "turn_events")):
        real = cls.exec
        cls.exec = fn
        try:
            w.events.add(kind)
        finally:
            cls.exec = real
    check(w.plan.talks[0].b == "PID_Tessa" and w.plan.talks[0].recruit, w.plan.talks)
    check(w.plan.turn_events[0].turn == 3, w.plan.turn_events)
    check(w.events.lists["talks"][0].count() == 1 and w.events.lists["turn_events"][0].count() == 1, "listed")
    w.canvas.tool = "move"
    QApplication.processEvents()
    w.grab().save("qt_out/v22_events.png")
    dlg = md.TileEventDialog(maker, e, w.events.chars, w.canvas.grid, True, w, "U001")
    dlg.show()
    QApplication.processEvents()
    dlg.grab().save("qt_out/v22_tile_event_dialog.png")
    dlg.tabs.setCurrentIndex(1)
    QApplication.processEvents()
    dlg.grab().save("qt_out/v22_tile_event_scene.png")
    check(len(dlg.scene.steps) == 2, "scene steps shown")
    dlg.close()

    # multi-line text: your own rows and boxes, shown in the preview
    ed = w.opening
    ed.add_line(cm.Line("クロム", "Normal", "Row one.\nRow two.\n\nA new box."))
    entry = ed.rows[-1]
    check("2 text boxes" in entry[4].text(), entry[4].text())
    check(ed.lines()[-1].text == "Row one.\nRow two.\n\nA new box.", repr(ed.lines()[-1].text))
    w.grab().save("qt_out/v22_story_editor.png")
    entry[3].deleteLater()
    ed.rows.remove(entry)
    # make your own picture (the picture itself is made from the game's files; here a stand-in)
    from paragon.unlimited.map_maker import telop_pictures as tp

    real_make = tp.make_picture
    tp.make_picture = lambda *a, **k: b"CGFX-test"
    try:
        pd = md.MakePictureDialog(maker, "U001", w)
        pd.chara_path = os.path.abspath("paragon.ico") if os.path.exists("paragon.ico") else ""
        if pd.chara_path:
            from PIL import Image

            png = os.path.join("qt_out", "chara_test.png")
            Image.new("RGBA", (64, 64), (200, 30, 60, 255)).save(png)
            pd.chara_path = png
            pd.accept()
            check(pd.name == "Tlp_PU_U001_1" and maker.edits.files.get("telop/Tlp_PU_U001_1.r.lz") == b"CGFX-test",
                  pd.name)
            check(any(n == "Tlp_PU_U001_1" for _l, n in tp.choices(maker.gd, None, maker.edits.files)), "listed")
    finally:
        tp.make_picture = real_make
    print("unit details, terrain, chests and events: ok")


def clear_chapter(w, maker):
    """Clear (start over) on a chapter card."""
    from PySide6.QtWidgets import QDialog, QMessageBox

    from paragon.unlimited.map_maker import map_maker_window as pm

    class PickSnow(pm.TemplateGallery):
        def exec(self):
            self.chosen = "003"
            return QDialog.Accepted

    real_gallery, real_warn = pm.TemplateGallery, pm.QMessageBox.warning
    pm.TemplateGallery = PickSnow
    pm.QMessageBox.warning = staticmethod(lambda *a, **k: QMessageBox.Yes)
    try:
        w.dirty = False
        w.clear_chapter("U001")
    finally:
        pm.TemplateGallery, pm.QMessageBox.warning = real_gallery, real_warn
    check(maker.cleared == ["U001"] and w.plan.cid == "U001" and not w.plan.tile_events, "cleared")
    check(w.made_here and not w.events.lists["tile_events"][1].isHidden(), "all features after clearing")
    print("clear chapter: ok")

    # world map spot: the picker returns a spot, the plan keeps it, Automatic clears it
    from PySide6.QtWidgets import QApplication, QDialog

    from paragon.unlimited.map_maker import world_spot_picker as wsp
    from paragon.unlimited.map_maker import world_map as wm

    check(wm.gm_spot(wm.from_gm(230, 200)) == (230, 200), "bottom map <-> globe")
    dlg = wsp.WorldSpotDialog(maker.world_map_layout(), "U001", "003", None, "Chapter 3", w)
    dlg.show()
    QApplication.processEvents()
    check(dlg.spot() is None and "Automatic" in dlg.status.text(), "starts automatic")
    dlg.canvas.set_spot((345, 103))
    check(dlg.spot() == (345, 103) and "close to" in dlg.status.text(), dlg.status.text())
    dlg.canvas.set_spot((1000, -5))
    check(dlg.spot() == (wm.GM_BOUNDS[2], wm.GM_BOUNDS[1]), "kept on the map")
    dlg.canvas.set_spot((230, 200))
    dlg.grab().save("qt_out/v23_world_spot.png")
    dlg.auto_button.click()
    check(dlg.spot() is None, "automatic again")
    dlg.close()

    class PickSpot(wsp.WorldSpotDialog):
        def exec(self):
            self.canvas.set_spot((230, 200))
            return QDialog.Accepted

    real_dlg = wsp.WorldSpotDialog
    wsp.WorldSpotDialog = PickSpot
    try:
        w._choose_spot()
    finally:
        wsp.WorldSpotDialog = real_dlg
    check("230, 200" in w.spot_label.text(), w.spot_label.text())
    check(w.save(), "saved with a spot")
    check(maker.chapters["U001"].world_spot == [230, 200], maker.chapters["U001"].world_spot)
    check(cm.ChapterPlan.from_json(maker.chapters["U001"].to_json()).world_spot == [230, 200], "spot in the plan json")
    check(cm.ChapterMaker._spot(maker.chapters["U001"]) == (230, 200), "spot used on save")
    print("world map spot: ok")


def pm_cell():
    return cm_cell()


def test_help():
    from PySide6.QtWidgets import QApplication

    from paragon.unlimited.app import help_window

    app = QApplication.instance() or QApplication([])
    topics = help_window.load_topics("FE13")
    lessons = sorted((t["tutorial"], k) for k, t in topics.items() if t.get("tutorial"))
    check(len(lessons) >= 8 and [n for n, _k in lessons] == list(range(1, len(lessons) + 1)), lessons)
    check("map_maker" in topics, "map maker reference page")
    html = help_window.topic_html("lesson_first_chapter")
    check("Next lesson" in html and "topic:lesson_edit_map" in html and "Lesson 2" in html, "lesson links")
    for _n, k in lessons:
        for link in __import__("re").findall(r"topic:([a-z_0-9]+)", topics[k]["body"]):
            check(link in topics, f"{k} links to missing {link}")
    for name in [n for n in os.listdir("Data/FE13/Help") if n.endswith(".txt")]:
        check("colour" not in open(os.path.join("Data/FE13/Help", name), encoding="utf-8").read().lower(), "US spelling")
    dlg = help_window.HelpDialog("FE13")
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
        test_win_conditions()
        test_help()
        test_window(tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("map maker test: all checks passed")


if __name__ == "__main__":
    main()
