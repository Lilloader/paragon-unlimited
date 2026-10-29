"""Paragon Unlimited v1.14: Sprite Workshop rebuilt around separate heads and bodies.
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

from paragon.core.services import fe13_sprite_parts as sp
from paragon.core.services import fe13_sprite_workshop as ws


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
        self.lists[(self.jobs, "jobs")] = [self._new(key="JID_テスト男", disp="Knight")]
        self.chars = self._new()
        sd = self._new()
        self.lists[(sd, "entries")] = [self._new(bmap_icon=None)]
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

    from paragon.ui.controllers.pu_sprite_workshop import SpriteWorkshop

    lib = make_library(tmp)
    gd = FakeData(tmp)
    gs = types.SimpleNamespace(data=gd, project=types.SimpleNamespace(output_path=tmp, rom_path=None))
    gs.pu_sprite_workshop = ws.Workshop(gd, parts=lib)
    dlg = SpriteWorkshop(gs)
    dlg.show()
    QApplication.processEvents()
    check(not dlg.canvas.images, "starts blank")
    dlg.tabs.setCurrentIndex(1)
    dlg._select(dlg.head_combo, "クロム")
    dlg._select(dlg.body_combo, "テスト|男")
    check(dlg.source_combo.currentData() == "メイジ|男", "head source picked")
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
    dlg.eraser_button.setChecked(True)
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
    dlg.eraser_size.setCurrentIndex(2)
    check(dlg.canvas.eraser == 3, "3 px eraser")
    dlg.canvas.move(body_pt)
    QApplication.processEvents()
    dlg.grab().save("qt_out/v115_eraser.png") if os.path.isdir("qt_out") else None
    dlg._erase_clear()
    check(dlg.project.erased == [] and px(dlg.sheets["青"], 15, 20)[:3] == BLUE, "restore all erased")
    dlg.eraser_button.setChecked(False)
    check(dlg.canvas.eraser == 0, "eraser off: heads drag again")
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
    dlg.adv_box.setChecked(True)
    os.makedirs("qt_out", exist_ok=True)
    dlg.resize(1240, 800)
    QApplication.processEvents()
    dlg.grab().save("qt_out/v114_sprite_workshop.png")
    dlg.close()
    print("window: ok")


def main():
    tmp = tempfile.mkdtemp()
    try:
        test_parts_and_build(os.path.join(tmp, "a")) if os.makedirs(os.path.join(tmp, "a")) is None else None
        os.makedirs(os.path.join(tmp, "b"))
        test_sheet_mode(os.path.join(tmp, "b"))
        os.makedirs(os.path.join(tmp, "e"))
        test_eraser(os.path.join(tmp, "e"))
        from PySide6.QtWidgets import QApplication

        app = QApplication.instance() or QApplication([])
        os.makedirs(os.path.join(tmp, "c"))
        test_window(app, os.path.join(tmp, "c"))
    finally:
        shutil.rmtree(tmp)
    print("v1.14 sprite parts test: all checks passed")


if __name__ == "__main__":
    main()
