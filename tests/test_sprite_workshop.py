"""Sprite Workshop: separate heads and bodies.
Synthetic classes (no game files): a 'test' body class and a 'mage' class whose head sits 2 px
lower, a character head on the mage body, a hand-made parts library. The window runs offscreen."""
import base64
import json
import os
import shutil
import sys
import tempfile
import types
import zlib
from array import array

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.chdir(os.path.join(os.path.dirname(__file__), ".."))

from paragon.unlimited.sprites import sprite_parts as sp
from paragon.unlimited.sprites import sprite_sheets as ws


def check(cond, msg):
    if not cond:
        raise AssertionError(msg)


W, H, CW, CH = 64, 64, 32, 32
BLUE, RED, GREEN = (51, 102, 204), (204, 34, 34), (34, 170, 68)
GEN_HEAD = (153, 153, 153)  # generic grey head
CHROM_HAIR = (34, 51, 119)
SKIN = (238, 204, 170)
A = 136


def sheet(pixels):
    s = ws.Sheet.blank(W, H)
    for (x, y), rgb, a in pixels:
        i = (y * W + x) * 4
        s.rgba[i : i + 4] = bytes(rgb + (a,))
    return s


def class_sheet(head_top, team, head_rgb):
    """Body block (team color) rows 14..27, head block 8x8 from head_top, in every cell."""
    px = []
    for c in range(2):
        for r in range(2):
            ox, oy = c * CW, r * CH
            for y in range(14, 28):
                for x in range(10, 22):
                    px.append(((ox + x, oy + y), team, A))
            if head_rgb:
                for y in range(head_top, head_top + 8):
                    for x in range(12, 20):
                        px.append(((ox + x, oy + y), head_rgb if y > head_top + 1 else SKIN, A))
    return sheet(px)


def parts_entry(stem, sex, head_top, body_sheet):
    union, fill, core = [], [], []
    for c in range(2):
        for r in range(2):
            ox, oy = c * CW, r * CH
            for y in range(head_top - 1, head_top + 9):
                for x in range(11, 21):
                    i = (oy + y) * W + ox + x
                    union.append(i)
                    o = i * 4
                    under = tuple(body_sheet.rgba[o : o + 4]) if not (head_top <= y < head_top + 8 and 12 <= x < 20) else (0, 0, 0, 0)
                    fill.append(under)
                    core.append(head_top <= y < head_top + 8 and 12 <= x < 20)
    order = sorted(range(len(union)), key=lambda k: union[k])
    union = [union[k] for k in order]
    fill = [fill[k] for k in order]
    core = [core[k] for k in order]
    bits = bytearray((len(core) + 7) // 8)
    for k, v in enumerate(core):
        if v:
            bits[k >> 3] |= 0x80 >> (k & 7)
    anchors = {f"{c},{r}": [c * CW + 15.5, r * CH + head_top] for c in range(2) for r in range(2)}
    return {
        "stem": stem, "sex": sex, "generic": stem + sex, "variants": ["クロム"] if stem == "メイジ" else ["リズ"],
        "cell": [CW, CH], "size": [W, H],
        "union": base64.b64encode(zlib.compress(array("I", union).tobytes())).decode(),
        "fill": base64.b64encode(zlib.compress(bytes(v for p in fill for v in p))).decode(),
        "core": base64.b64encode(zlib.compress(bytes(bits))).decode(),
        "anchors": anchors,
    }


def make_library(tmp):
    body_t = class_sheet(4, BLUE, None)
    body_m = class_sheet(6, BLUE, None)
    data = {
        "version": 1, "core": 0.3,
        "classes": {"テスト|男": parts_entry("テスト", "男", 4, body_t), "メイジ|男": parts_entry("メイジ", "男", 6, body_m)},
        "heads": {"クロム": [{"class": "メイジ|男", "sprite": "メイジクロム"}]},
        "job_names": {"テスト男": "Knight", "メイジ男": "Mage"},
        "people": {"クロム": "Chrom"},
    }
    path = os.path.join(tmp, "parts.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    return sp.PartsLibrary(path)


class FakeData:
    def __init__(self, out_root):
        self.out_root = out_root
        self.files = {}
        self.rec = {}
        self.lists = {}
        self.next = 0
        for c, team in (("青", BLUE), ("赤", RED), ("緑", GREEN)):
            self.files[f"map/unit/テスト男{c}.ctpk.lz"] = ws.new_ctpk(W, H, ws.encode_rgba4(class_sheet(4, team, GEN_HEAD)))
            self.files[f"map/unit/メイジ男{c}.ctpk.lz"] = ws.new_ctpk(W, H, ws.encode_rgba4(class_sheet(6, team, GEN_HEAD)))
            self.files[f"map/unit/メイジクロム{c}.ctpk.lz"] = ws.new_ctpk(W, H, ws.encode_rgba4(class_sheet(6, team, CHROM_HAIR)))
        self.icons = self._new()
        anim = self._new()
        self.lists[(anim, "frame_data")] = [self._new(frame_index_x=0, frame_index_y=0, frame_delay=12),
                                            self._new(frame_index_x=1, frame_index_y=0, frame_delay=12)]
        data = self._new(animation_data_1=anim)
        self.lists[(self.icons, "icons")] = [
            self._new(bmi="BMI_テスト男", name="テスト男", frame_width=0, frame_height=0, pointer=data),
            self._new(bmi="BMI_メイジ男", name="メイジ男", frame_width=0, frame_height=0, pointer=data),
        ]
        self.jobs = self._new()
        self.lists[(self.jobs, "jobs")] = [self._new(key="JID_テスト男", disp="Knight"), self._new(key="JID_メイジ男", disp="Mage")]
        self.chars = self._new()
        sd = self._new()
        self.lists[(sd, "entries")] = [self._new(bmap_icon=None), self._new(bmap_icon=None)]
        self.lists[(self.chars, "people")] = [self._new(key="PID_クロム", disp="Chrom", sprite_data=sd)]

    def _new(self, **f):
        self.next += 1
        self.rec[self.next] = dict(f)
        return self.next

    def file_exists(self, path, localized):
        return path in self.files

    def read_file(self, path):
        return self.files[path]

    def write_file(self, path, data):
        self.files[path] = bytes(data)
        p = os.path.join(self.out_root, *path.split("/"))
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "wb") as f:
            f.write(bytes(data))

    def list_files(self, folder, pattern, localized):
        return [p for p in self.files if p.startswith(folder + "/")]

    def table(self, name):
        return {"bmap_icons": (self.icons, "icons"), "jobs": (self.jobs, "jobs"), "characters": (self.chars, "people")}.get(name)

    def items(self, rid, f):
        return list(self.lists.get((rid, f), []))

    def list_add(self, rid, f):
        r = self._new()
        self.lists[(rid, f)].append(r)
        return r

    def list_size(self, rid, f):
        return len(self.lists[(rid, f)])

    def list_get(self, rid, f, i):
        return self.lists[(rid, f)][i]

    def copy(self, src, dst, fields):
        self.rec[dst] = dict(self.rec[src])

    def string(self, rid, f):
        return self.rec[rid].get(f)

    def set_string(self, rid, f, v):
        self.rec[rid][f] = v

    def int(self, rid, f):
        return self.rec[rid].get(f)

    def rid(self, rid, f):
        return self.rec[rid].get(f)

    def set_rid(self, rid, f, v):
        self.rec[rid][f] = v

    def key(self, rid):
        return self.rec[rid].get("key")

    def display(self, rid):
        return self.rec[rid].get("disp")

    def set_store_dirty(self, s, v):
        pass


def px(s, x, y):
    i = (y * s.width + x) * 4
    return tuple(s.rgba[i : i + 4])


def test_parts_and_build(tmp):
    lib = make_library(tmp)
    names = sp.Names(lib=lib)
    check(names.sprite("メイジクロム") == "Mage - Chrom" and names.job("テスト", "男") == "Knight (M)", names.sprite("メイジクロム"))
    gd = FakeData(tmp)
    w = ws.Workshop(gd, parts=lib)
    w._head_sheets = {}  # the head sheets in Data/FE13/PU_Heads are tested in test_head_sheets.py
    check(w.head_choices() == [("Chrom", "クロム")], w.head_choices())
    check(("Knight (M)", "テスト|男") in w.body_choices(), w.body_choices())
    check(w.best_head_source("クロム", "テスト|男") == "メイジ|男", "head source")
    p = ws.WorkshopProject(name="ChromKnight", mode="build", head_char="クロム", head_class="メイジ|男", body_class="テスト|男")
    prep = w.prepare(p)
    sheets = w.build(p, prep=prep)
    b = sheets["青"]
    # Chrom's hair lands where the knight's head is (2 px higher than on the mage)
    check(px(b, 15, 8)[:3] == CHROM_HAIR, f"hair at knight head position {px(b, 15, 8)}")
    check(px(b, 15 + 32, 8 + 32)[:3] == CHROM_HAIR, "every frame")
    check(all(px(b, x, y)[:3] != GEN_HEAD for x in range(W) for y in range(H)), "generic head gone")
    check(px(b, 15, 20)[:3] == BLUE and px(sheets["赤"], 15, 20)[:3] == RED and px(sheets["緑"], 15, 20)[:3] == GREEN,
          "body in the game's own team colors")
    check(px(sheets["赤"], 15, 8)[:3] == CHROM_HAIR, "head keeps its colors")
    # move one frame's head
    p.head_frames = {"1,0": [2, 1]}
    b2 = w.build(p, prep=prep)["青"]
    check(px(b2, 15, 8)[:3] == CHROM_HAIR and px(b2, 32 + 17, 9)[:3] == CHROM_HAIR, "only frame (1,0) moved")
    _s, mask, cut = w.compose_color(prep, "青", {"0,0": [0, -10]})
    check(cut > 0, "head pushed out of its frame is cut")
    # export + register + validate
    lines = w.export(p)
    check(any("BMI_ChromKnight" in l for l in lines), lines)
    w.flush()
    res = w.validate(p, [tmp])
    check(res[0][0] == "ok", res)
    print("parts / build / export: ok")


def test_eraser(tmp):
    lib = make_library(tmp)
    gd = FakeData(tmp)
    w = ws.Workshop(gd, parts=lib)
    p = ws.WorkshopProject(name="ChromKnight", mode="build", head_char="クロム", head_class="メイジ|男", body_class="テスト|男")
    prep = w.prepare(p)
    check(px(w.build(p, prep=prep)["青"], 15, 20)[:3] == BLUE, "body pixel before erasing")
    # erase a body pixel and a pixel under the new head
    p.erased = [[15, 20], [15, 8]]
    sheets = w.build(p, prep=prep)
    for c in ("青", "赤", "緑"):
        check(px(sheets[c], 15, 20) == (0, 0, 0, 0), f"erased in {c}")
        check(px(sheets[c], 15, 8)[:3] == CHROM_HAIR, f"the new head is never erased ({c})")
        check(px(sheets[c], 16, 20)[3] == A, f"neighbors untouched ({c})")
    # a moved head still shows over an erased spot; heads / bodies are not changed by the eraser
    p.head_frames = {"0,0": [0, 12]}
    b = w.build(p, prep=prep)["青"]
    check(px(b, 15, 20)[:3] == CHROM_HAIR, "head moved onto an erased pixel is drawn")
    p.head_frames = {}
    # brush: 3 px square, kept inside its own frame
    br = ws.brush_pixels(31, 5, 3, (CW, CH), (W, H))
    check(sorted(br) == [(30, 4), (30, 5), (30, 6), (31, 4), (31, 5), (31, 6)], br)
    check(ws.brush_pixels(10, 10, 1, (CW, CH), (W, H)) == [(10, 10)], "1 px brush")
    # saved with the project
    pp = os.path.join(tmp, "erase.pusprite")
    p.save(pp)
    check(ws.WorkshopProject.open(pp).erased == [[15, 20], [15, 8]], "erased pixels saved")
    check(w.validate(p, [tmp])[0][0] in ("ok", "error"), "validate runs with erased pixels")
    print("eraser: ok")


def test_sheet_mode(tmp):
    lib = make_library(tmp)
    gd = FakeData(tmp)
    w = ws.Workshop(gd, parts=lib)
    # an opaque PNG drawn on the knight body with a custom head
    s = class_sheet(4, BLUE, (204, 51, 153))
    for i in range(3, len(s.rgba), 4):
        if s.rgba[i]:
            s.rgba[i] = 255
    # one outline pixel
    i = (27 * W + 10) * 4
    s.rgba[i : i + 4] = bytes((34, 34, 34, 255))
    path = os.path.join(tmp, "mine.png")
    s.to_pil().save(path)
    check(sp.is_full_opacity(s), "opaque detected")
    g = sp.game_opacity(s)
    check(px(g, 15, 20)[3] == 136 and px(g, 10, 27)[3] == 68, f"game levels {px(g, 15, 20)} {px(g, 10, 27)}")
    p = ws.WorkshopProject(name="Mine", mode="sheet", sheet=path, sheet_sha256=ws.file_digest(path))
    prep = w.prepare(p)
    check(prep.class_key == "テスト|男", f"class found by shape: {prep.class_key}")
    check(len(prep.heads["青"]) == 4, "a head in every frame")
    p.head_frames = {"0,1": [3, 0]}
    b = w.build(p, prep=prep)["青"]
    check(px(b, 18, 32 + 8)[:3] == (204, 51, 153) and px(b, 15, 8)[:3] == (204, 51, 153), "frame (0,1) moved, (0,0) not")
    check(px(b, 15, 20)[3] == 136, "see-through like the game")
    p.opacity = False
    check(w.build(p, prep=w.prepare(p))["青"].rgba[(20 * W + 15) * 4 + 3] == 255, "opacity off keeps the image")
    p.sheet_class = "-"
    check(w.prepare(p).class_key is None, "no class: heads stay")
    # project file round trip (relative path)
    pp = os.path.join(tmp, "proj", "a.pusprite")
    os.makedirs(os.path.dirname(pp))
    p.save(pp)
    q = ws.WorkshopProject.open(pp)
    check(q.sheet == path and q.head_frames == {"0,1": [3, 0]} and '"../mine.png"' in open(pp, encoding="utf-8").read(), "saved")
    old = ws.WorkshopProject.from_json(json.dumps({"name": "x", "body_kind": "file", "body": path, "head": ""}))
    check(old.mode == "sheet" and old.sheet == path, "v1.12 project opens")
    print("sheet mode / opacity / project: ok")


def test_window(app, tmp):
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtWidgets import QApplication

    from paragon.unlimited.sprites.sprite_workshop_window import SpriteWorkshop

    lib = make_library(tmp)
    gd = FakeData(tmp)
    gs = types.SimpleNamespace(data=gd, project=types.SimpleNamespace(output_path=tmp, rom_path=None))
    gs.pu_sprite_workshop = ws.Workshop(gd, parts=lib)
    gs.pu_sprite_workshop._head_sheets = {}
    dlg = SpriteWorkshop(gs)
    dlg.show()
    QApplication.processEvents()
    check(not dlg.canvas.images, "starts blank")
    dlg.tabs.setCurrentIndex(1)
    dlg._select(dlg.head_combo, "クロム")
    dlg._select(dlg.body_combo, "テスト|男")
    dlg._build_from_parts()
    QApplication.processEvents()
    check(set(dlg.sheets) == {"青", "赤", "緑"} and len(dlg.canvas.images) == 3, "built and shown")
    # drag the head of frame (1,0) in the player image: screen = sheet * zoom (+20 px label row)
    z = dlg.canvas._scale()
    start = QPoint((32 + 15) * z + z // 2, 20 + 8 * z + z // 2)
    check(dlg.canvas.press(start), "press on a head")
    dlg.canvas.move(QPoint(start.x() + 2 * z, start.y() + 1 * z))
    dlg.canvas.release()
    QApplication.processEvents()
    check(dlg.project.head_frames == {"1,0": [2, 1]}, dlg.project.head_frames)
    check(px(dlg.sheets["赤"], 32 + 17, 9)[:3] == CHROM_HAIR, "all colors follow after release")
    check(not dlg.canvas.press(QPoint(2 * z, 20 + 2 * z)), "empty spot does not drag")
    dlg.canvas.press(start, Qt.RightButton)
    check(dlg.project.head_frames == {}, "right-click resets the frame")
    # clean-up eraser: on, erase a body pixel, right-drag puts it back, undo, restore all
    dlg.adjust_tabs.setCurrentIndex(1)  # Erase body
    check(dlg.canvas.eraser == 1, "eraser on, 1 px")
    body_pt = QPoint(15 * z + z // 2, 20 + 20 * z + z // 2)
    check(dlg.canvas.press(body_pt), "eraser press")
    dlg.canvas.move(QPoint(body_pt.x() + z, body_pt.y()))
    dlg.canvas.release()
    QApplication.processEvents()
    check(dlg.project.erased == [[15, 20], [16, 20]], dlg.project.erased)
    check(px(dlg.sheets["赤"], 15, 20) == (0, 0, 0, 0), "erased in every color after release")
    check(not dlg.project.head_frames, "erasing does not move heads")
    dlg.canvas.press(body_pt, Qt.RightButton)
    dlg.canvas.release()
    check(dlg.project.erased == [[16, 20]], "right-drag puts pixels back")
    dlg._erase_undo()
    check(dlg.project.erased == [[15, 20], [16, 20]], "undo erase")
    dlg.eraser_sizes["body"].setCurrentIndex(2)
    check(dlg.canvas.eraser == 3, "3 px eraser")
    dlg.canvas.move(body_pt)
    QApplication.processEvents()
    dlg.grab().save("qt_out/v115_eraser.png") if os.path.isdir("qt_out") else None
    dlg._erase_clear("body")
    check(dlg.project.erased == [] and px(dlg.sheets["青"], 15, 20)[:3] == BLUE, "restore all erased")
    # head eraser: erases head pixels only, in the head's own frame coordinates
    dlg.adjust_tabs.setCurrentIndex(2)
    dlg.eraser_sizes["head"].setCurrentIndex(0)
    head_pt = QPoint((32 + 17) * z + z // 2, 20 + 9 * z + z // 2)
    check(px(dlg.sheets["青"], 32 + 17, 9)[:3] == CHROM_HAIR, "head pixel before")
    dlg.canvas.press(head_pt)
    dlg.canvas.release()
    QApplication.processEvents()
    check(dlg.project.head_erased == [[1, 0, 17, 9]] and dlg.project.erased == [], dlg.project.head_erased)
    check(px(dlg.sheets["赤"], 32 + 17, 9)[:3] != CHROM_HAIR, "head pixel erased in every color")
    dlg._erase_undo()
    check(dlg.project.head_erased == [], "undo head erase")
    dlg.adjust_tabs.setCurrentIndex(0)
    check(dlg.canvas.eraser == 0, "Move head tab: heads drag again")
    # copy the head of frame (1,0) into frame (2,1), then the whole row 1
    dlg.adjust_tabs.setCurrentIndex(3)
    dlg.canvas.selected = (1, 0)
    dlg._copy_head()
    dlg.canvas.selected = (0, 1)
    dlg._paste_head()
    check(dlg.project.head_copies == {"0,1": "1,0"}, dlg.project.head_copies)
    dlg._paste_head(True)
    check(dlg.project.head_copies == {"0,1": "1,0", "1,1": "1,0"}, dlg.project.head_copies)
    dlg._unpaste_head()
    check("0,1" not in dlg.project.head_copies, "remove pasted head")
    dlg.canvas.selected = (0, 0)
    dlg._copy_row()
    dlg.canvas.selected = (1, 1)
    dlg._paste_row()
    check(dlg.project.head_copies == {"0,1": "0,0", "1,1": "1,0"}, dlg.project.head_copies)
    dlg.project.head_copies = {}
    # size / mirror / layer
    dlg.adjust_tabs.setCurrentIndex(4)
    dlg.canvas.selected = (1, 0)
    dlg.scale_spin.setValue(80)
    dlg._set_scale("frame")
    check(dlg.project.head_scale == {"1,0": 0.8}, dlg.project.head_scale)
    dlg._set_scale("all")
    check(len(dlg.project.head_scale) == 4, dlg.project.head_scale)
    dlg.scale_spin.setValue(100)
    dlg._set_scale("all")
    check(dlg.project.head_scale == {}, "back to 100 %")
    dlg._flip("row")
    check(dlg.project.head_flip == ["0,0", "1,0"], dlg.project.head_flip)
    dlg._flip("row")
    check(dlg.project.head_flip == [], "flip twice")
    dlg.layer_combo.setCurrentIndex(1)
    check(dlg.project.head_behind, "heads behind")
    dlg._swap_layer()
    check(dlg.project.head_layer_swap == ["1,0"], dlg.project.head_layer_swap)
    dlg.layer_combo.setCurrentIndex(0)
    dlg._swap_layer()
    dlg.adjust_tabs.setCurrentIndex(0)
    # a sheet dropped on the preview
    s = class_sheet(4, BLUE, (204, 51, 153))
    path = os.path.join(tmp, "dropped.png")
    s.to_pil().save(path)
    dlg.project.name = ""
    dlg.name_edit.setText("")
    dlg._file_dropped(path)
    QApplication.processEvents()
    check(dlg.project.mode == "sheet" and dlg.prep.class_key == "テスト|男", "dropped sheet split")
    check(dlg.name_edit.text() == "dropped", dlg.name_edit.text())
    dlg.view_combo.setCurrentIndex(1)
    dlg._next_frame()
    dlg.view_combo.setCurrentIndex(0)
    dlg.heads_check.setChecked(True)
    dlg._export()
    check("Saved" in dlg.report.toPlainText(), dlg.report.toPlainText())
    dlg.workshop.flush()
    check(dlg._validate()[0][0] == "ok", dlg.report.toPlainText())
    # a second sprite: a saved sprite with characters keeps its sheet, name and list; a new one starts
    first = dlg.project
    dlg._select(dlg.char_combo, "PID_クロム")
    dlg._select(dlg.job_combo, "JID_テスト男")
    dlg._add_assignment()
    path2 = os.path.join(tmp, "second.png")
    class_sheet(4, BLUE, (51, 153, 51)).to_pil().save(path2)
    dlg._file_dropped(path2)
    QApplication.processEvents()
    session = dlg.workshop.session
    check(len(session) == 2 and dlg.project is session[1] and first is session[0], [p.name for p in session])
    check(first.name == "dropped" and first.sheet == path and len(first.assign) == 1, "the first sprite is kept")
    check(dlg.project.name == "second" and dlg.project.sheet == path2 and dlg.project.assign == [], dlg.project.name)
    check(dlg.sprite_list.count() == 2 and dlg.assign_list.count() == 0, "list shows both")
    dlg._select(dlg.job_combo, "JID_メイジ男")
    dlg._add_assignment()
    dlg._export()
    icons = {gd.string(r, "name"): r for r in gd.items(gd.icons, "icons")}
    check({"dropped", "second"} <= set(icons), list(icons))
    sd = gd.rid(gd.items(gd.chars, "people")[0], "sprite_data")
    entries = gd.items(sd, "entries")
    check(gd.rid(entries[0], "bmap_icon") == icons["dropped"] and gd.rid(entries[1], "bmap_icon") == icons["second"],
          "each sprite assigned to its own class")
    check("map/unit/second青.ctpk.lz" in dlg.workshop.pending and "map/unit/dropped青.ctpk.lz" in dlg.workshop.pending,
          "both sprites queued")
    # back to the first: its list; removing a character and saving again unassigns it
    dlg.sprite_list.setCurrentRow(0)
    QApplication.processEvents()
    check(dlg.project is first and dlg.assign_list.count() == 1 and dlg.name_edit.text() == "dropped", "switch back")
    dlg.assign_list.setCurrentRow(0)
    dlg._remove_assignment()
    dlg._export()
    check(gd.rid(entries[0], "bmap_icon") is None and gd.rid(entries[1], "bmap_icon") == icons["second"],
          "removed from the list = unassigned")
    # an unsaved sprite without characters is reused by the next sheet
    dlg._new_sprite()
    check(len(session) == 3 and dlg.name_edit.text() == "", "new sprite")
    dlg._file_dropped(path2)
    dlg._file_dropped(path)
    check(len(session) == 3 and dlg.project.name == "dropped", [p.name for p in session])
    dlg._remove_sprite()
    check(len(session) == 2, "removed from the list")
    dlg.adv_box.setChecked(True)
    os.makedirs("qt_out", exist_ok=True)
    dlg.resize(1240, 800)
    QApplication.processEvents()
    dlg.grab().save("qt_out/v114_sprite_workshop.png")
    dlg.close()
    # autosave: the list is kept next to the output folder (never inside it) and comes back in a new run
    folder = ws.autosave_dir(tmp)
    check(os.path.isfile(os.path.join(folder, ws.AUTOSAVE_FILE)) and not folder.startswith(tmp + os.sep),
          "sprite list autosaved")
    gs.pu_sprite_workshop = ws.Workshop(gd, parts=lib)
    gs.pu_sprite_workshop._head_sheets = {}
    dlg2 = SpriteWorkshop(gs)
    names = [p.name for p in dlg2.workshop.session]
    check(names == ["dropped", "second"] and dlg2.sprite_list.count() == 2, names)
    check(dlg2.workshop.session[0].sheet == path and dlg2.workshop.assigned.get("second"), "sheets and assignments back")
    check("from last time" in dlg2.report.toPlainText(), dlg2.report.toPlainText())
    dlg2.close()
    print("window: ok")


def test_autosave(tmp):
    lib = make_library(tmp)
    gd = FakeData(tmp)
    w = ws.Workshop(gd, parts=lib)
    folder = ws.autosave_dir(os.path.join(tmp, "out"))
    check(ws.restore(w, folder) == 0, "nothing saved yet")
    a = ws.WorkshopProject(name="Alpha", mode="sheet", sheet=os.path.join(tmp, "alpha.png"),
                           assign=[{"pid": "PID_クロム", "jid": "JID_テスト男"}])
    w.session[:] = [a, ws.WorkshopProject()]
    w.assigned["Alpha"] = {("PID_クロム", "JID_テスト男")}
    check(ws.autosave(w, folder), "saved")
    w2 = ws.Workshop(gd, parts=lib)
    check(ws.restore(w2, folder) == 1, "the empty sprite is not kept")
    b = w2.session[0]
    check(b.name == "Alpha" and b.sheet == a.sheet and b.assign == a.assign, b)
    check(w2.assigned == {"Alpha": {("PID_クロム", "JID_テスト男")}}, w2.assigned)
    check(ws.restore(w2, folder) == 0, "a Workshop with sprites is not replaced")
    check(ws.autosave_dir(None) is None and not ws.autosave(w, None), "no project")
    print("autosave: ok")


def test_real_library():
    """The shipped library: every base-game class and the two DLC classes, nothing else."""
    lib = sp.PartsLibrary()
    w = ws.Workshop(FakeData(tempfile.mkdtemp()), parts=lib)
    labels = [l for l, _k in w.body_choices()]
    for want in ("Lord (M)", "Lord (F)", "Great Lord (M)", "Great Lord (F)", "General (M)", "Knight (M)",
                 "Barbarian (M)", "Berserker (M)", "Dancer (F)", "Manakete (F)", "Taguel (F)",
                 "Dread Fighter (M)", "Bride (F)", "Wyvern Lord (F)", "Tactician (M)"):
        check(want in labels, (want, labels))
    vanilla = set(lib.raw["job_names"])
    check(all(lib.parts(k).generic in vanilla or lib.parts(k).generic == "旧マルス" for k in lib.class_keys()),
          "only the game's own classes")
    check("ダミー|男" not in lib.class_keys(), "no placeholder")
    print("class list: ok", len(labels))


def main():
    tmp = tempfile.mkdtemp()
    test_real_library()
    try:
        test_parts_and_build(os.path.join(tmp, "a")) if os.makedirs(os.path.join(tmp, "a")) is None else None
        os.makedirs(os.path.join(tmp, "b"))
        test_sheet_mode(os.path.join(tmp, "b"))
        os.makedirs(os.path.join(tmp, "e"))
        test_eraser(os.path.join(tmp, "e"))
        os.makedirs(os.path.join(tmp, "s"))
        test_autosave(os.path.join(tmp, "s"))
        from PySide6.QtWidgets import QApplication

        app = QApplication.instance() or QApplication([])
        os.makedirs(os.path.join(tmp, "c"))
        test_window(app, os.path.join(tmp, "c"))
    finally:
        shutil.rmtree(tmp)
    print("sprite parts test: all checks passed")


if __name__ == "__main__":
    main()
