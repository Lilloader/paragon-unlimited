"""Offscreen Qt test for the Paragon Unlimited v1.0 features (runs in CI on Windows).

* FaceData: import images (button / several files / drag and drop), add and remove
  expressions, new portrait files, arc rebuilt on save.
* Remembered window and splitter sizes.
* Voice widget (fake voice service) and Asset Definitions preview (fake data).

No game files: portrait arcs are synthesised with the same CTPK layout as the game's.
"""
import os
import sys
import tempfile
import types

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.chdir(os.path.join(os.path.dirname(__file__), ".."))

from PIL import Image, ImageDraw
from PySide6.QtCore import QMimeData, QUrl, QPointF, Qt
from PySide6.QtGui import QDropEvent
from PySide6.QtWidgets import QApplication, QMessageBox, QWidget, QLabel

from paragon import paragon as pgn
from paragon.core.textures.texture import Texture
from paragon.core.services import fe13_portrait_shift as ps
from paragon.ui.controllers.auto import fe13_portrait_stage as stage_mod
from paragon.ui.controllers.auto.fe13_portrait_stage import FE13PortraitStage

OUT = "qt_out"


def check(cond, msg):
    if not cond:
        raise AssertionError(msg)


def figure_rgba(size, color):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    s = size / 256
    d.ellipse([90 * s, 40 * s, 170 * s, 130 * s], fill=color + (255,))
    d.rectangle([60 * s, 130 * s, 200 * s, 255 * s], fill=(80, 80, 140, 255))
    return img


def make_arc(size):
    entries = []
    for k in ps.BASIC_EXPRESSIONS:
        rgba = figure_rgba(size, (240, 200, 170)).tobytes()
        entries.append((k + ps.ENTRY_SUFFIX, 0, bytes(pgn.compress_lz13(ps.new_ctpk(size, size, rgba)))))
    for k, (w, h) in {"頬": (64, 32), "汗": (16, 16), "髪0": (32, 32)}.items():
        entries.append((k + ps.ENTRY_SUFFIX, 0, bytes(pgn.compress_lz13(ps.new_ctpk(w, h)))))
    return ps.build_arc(ps.sort_entries(entries))


class FakeData:
    def __init__(self):
        self.files = {"face/Test_bu_通常.arc": make_arc(256), "face/Test_fc_通常.arc": make_arc(128)}
        self.rec = {
            1: dict(fsid="FSID_BU_Test_通常", portrait_file="Test_bu_通常.arc", blush_position_x=100,
                    blush_position_y=60, sweat_position_x=130, sweat_position_y=70),
            2: dict(fsid="FSID_BU_Gisselle_通常", portrait_file="Missing.arc", blush_position_x=100,
                    blush_position_y=60, sweat_position_x=130, sweat_position_y=70),
        }

    def string(self, rid, f):
        return self.rec[rid].get(f)

    def int(self, rid, f):
        return self.rec[rid].get(f)

    def set_int(self, rid, f, v):
        self.rec[rid][f] = v

    def set_string(self, rid, f, v):
        self.rec[rid][f] = v

    def key_to_rid(self, table, key):
        return None

    def file_exists(self, path, localized):
        return path in self.files

    def read_file(self, path):
        return self.files[path]

    def write_file(self, path, contents):
        self.files[path] = bytes(contents)

    def read_arc(self, path):
        return {n: b for n, _i, b in ps.parse_arc(self.files[path])}


class FakePortraits:
    """Same hooks as FE13Portraits: reads go through the pending edits."""

    def __init__(self, data):
        self.data = data
        self.pu_edits = ps.PortraitEdits(data)

    def pu_portrait_edits(self):
        return self.pu_edits

    def _read_portrait_arc(self, path):
        full = f"face/{path}"
        if self.pu_edits.has_image_edits(full):
            try:
                arc = self.data.read_arc(full)
            except Exception:
                arc = None
            return self.pu_edits.overlay(full, arc)
        return self.data.read_arc(full)

    def from_fsid(self, fsid):
        rid = 1 if fsid == "FSID_BU_Test_通常" else 2
        try:
            arc = self._read_portrait_arc(self.data.rec[rid]["portrait_file"])
        except Exception:
            return None
        out = {}
        for name, blob in sorted(arc.items()):
            key = name[: -len(ps.ENTRY_SUFFIX)]
            if key.startswith("髪"):
                continue
            tex = pgn.read_ctpk(bytes(pgn.decompress_lz13(blob)))[0]
            out[key] = Texture.from_core_texture(tex)
        return out


def png(path, size, color):
    img = Image.new("RGBA", size, (0, 0, 0, 0))
    ImageDraw.Draw(img).ellipse([size[0] * 0.2, size[1] * 0.2, size[0] * 0.8, size[1] * 0.95], fill=color + (255,))
    img.save(path)
    return path


def texture_pixel(data, arc_path, key, xy):
    arc = {n: b for n, _i, b in ps.parse_arc(data.files[arc_path])}
    tex = pgn.read_ctpk(bytes(pgn.decompress_lz13(arc[key + ps.ENTRY_SUFFIX])))[0]
    img = Image.frombytes("RGBA", (tex.width, tex.height), bytes(tex.pixel_data))
    return img.getpixel(xy)


def test_face_data(app, tmp):
    data = FakeData()
    portraits = FakePortraits(data)
    gs = types.SimpleNamespace(data=data, portraits=portraits)
    state = types.SimpleNamespace(main_state=None, game_state=gs)
    stage = FE13PortraitStage(state)
    stage.resize(900, 700)
    stage.show()
    app.processEvents()
    stage.set_target(1)
    keys = [stage.expression_box.itemData(i) for i in range(stage.expression_box.count())]
    check(set(keys) == set(ps.BASIC_EXPRESSIONS), keys)
    check("Standard" in stage.expression_box.itemText(stage.expression_box.findData("通常")), "English labels")
    check(stage.zoom_box.currentText() == "Fit", "fit zoom default")

    # 1) Import into the current expression (image of another size: scaled to fit).
    stage.expression_box.setCurrentIndex(stage.expression_box.findData("笑"))
    red = png(os.path.join(tmp, "red.png"), (300, 400), (220, 30, 30))
    stage._import_files([red], default_key="笑")
    check(portraits.pu_edits.has_image_edits("face/Test_bu_通常.arc"), "pending import")
    check("scaled from 300x400" in stage.status.text(), stage.status.text())
    tex = stage.textures["笑"]
    px = tex.to_pillow_image().getpixel((128, 200))
    check(px[0] > 150 and px[1] < 90 and px[3] > 200, f"preview shows the import {px}")

    # 2) Several files matched by name, one unknown -> added as a new expression.
    blue = png(os.path.join(tmp, "Test_angry.png"), (256, 256), (30, 30, 220))
    green = png(os.path.join(tmp, "apron.png"), (256, 256), (30, 200, 30))
    orig_q = QMessageBox.question
    QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)
    try:
        stage._import_files([blue, green])
    finally:
        QMessageBox.question = orig_q
    keys = [stage.expression_box.itemData(i) for i in range(stage.expression_box.count())]
    check("apron" in keys, keys)
    check(stage.expression_box.currentData() == "apron", stage.expression_box.currentData())

    # 3) Drag and drop a PNG onto the preview -> current expression.
    stage.expression_box.setCurrentIndex(stage.expression_box.findData("苦"))
    yellow = png(os.path.join(tmp, "whatever.png"), (256, 256), (230, 220, 20))
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(yellow)])
    vp = stage.view.viewport()
    drop = QDropEvent(QPointF(50, 50), Qt.CopyAction, mime, Qt.LeftButton, Qt.NoModifier)
    handled = stage.eventFilter(vp, drop)
    check(handled, "drop handled")
    check(stage.expression_box.currentData() == "苦", "drop keeps expression")

    # 4) Add a blank expression through the dialog.
    def fake_exec(dlg):
        dlg.name.setEditText("照れ")
        dlg.source.setCurrentIndex(dlg.source.findData("blank"))
        return 1

    stage_mod._AddExpressionDialog.exec = fake_exec
    stage._on_add_expression()
    check(stage.expression_box.currentData() == "照れ", "added expression selected")

    # 5) Remove one.
    QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)
    try:
        stage.expression_box.setCurrentIndex(stage.expression_box.findData("キメ"))
        stage._on_remove_expression()
        stage.expression_box.setCurrentIndex(stage.expression_box.findData("通常"))
        stage._on_remove_expression()  # refused (warning); keep 通常
    finally:
        QMessageBox.question = orig_q
    keys = [stage.expression_box.itemData(i) for i in range(stage.expression_box.count())]
    check("キメ" not in keys and "通常" in keys, keys)
    stage.grab().save(os.path.join(OUT, "v1_facedata_imported.png"))

    # 6) Save: arc rebuilt with the changes, sorted, indexes = position.
    lines = portraits.pu_edits.flush(None)
    check(lines, "flush wrote something")
    names = [n for n, _i, _b in ps.parse_arc(data.files["face/Test_bu_通常.arc"])]
    check(names == sorted(names), names)
    check("apron.ctpk.lz" in names and "照れ.ctpk.lz" in names and "キメ.ctpk.lz" not in names, names)
    p = texture_pixel(data, "face/Test_bu_通常.arc", "怒", (128, 160))
    check(p[2] > 150 and p[0] < 90, f"angry is blue {p}")
    p = texture_pixel(data, "face/Test_bu_通常.arc", "苦", (128, 160))
    check(p[0] > 150 and p[1] > 150 and p[2] < 90, f"pained is yellow {p}")
    p = texture_pixel(data, "face/Test_bu_通常.arc", "照れ", (128, 160))
    check(p[3] == 0, f"blank is transparent {p}")
    check(not portraits.pu_edits.has_pending(), "nothing pending after save")

    # 7) New portrait file for an entry whose file does not exist.
    stage.set_target(2)
    check(stage.expression_box.count() == 0 and "New portrait file" in stage.status.text(), stage.status.text())

    def fake_new(dlg):
        return 1

    stage_mod._NewFileDialog.exec = fake_new
    stage._on_new_file()
    check(data.rec[2]["portrait_file"] == "Gisselle_bu_通常.arc", data.rec[2]["portrait_file"])
    keys = [stage.expression_box.itemData(i) for i in range(stage.expression_box.count())]
    check(set(keys) == set(ps.BASIC_EXPRESSIONS), keys)
    stage._import_files([png(os.path.join(tmp, "normal.png"), (256, 256), (200, 120, 60))])
    portraits.pu_edits.flush(None)
    names = [n for n, _i, _b in ps.parse_arc(data.files["face/Gisselle_bu_通常.arc"])]
    check(set(names) == {k + ps.ENTRY_SUFFIX for k in ps.BASIC_EXPRESSIONS + ["頬", "汗", "髪", "髪0"]}, names)
    p = texture_pixel(data, "face/Gisselle_bu_通常.arc", "通常", (128, 160))
    check(p[0] > 150 and p[3] > 200, f"normal imported {p}")
    stage.grab().save(os.path.join(OUT, "v1_facedata_new_file.png"))
    stage.close()
    print("FaceData import / expressions: ok")


def test_window_memory(app):
    from paragon.ui import pu_window_memory as wm
    from paragon.ui.controllers.auto.splitter import Splitter

    config = types.SimpleNamespace(pu_window_sizes=None)
    wm.set_config(config)
    w = QWidget()
    w.resize(500, 400)
    wm.remember_window(w, "facedata")
    w.show()
    app.processEvents()
    w.resize(777, 555)
    app.processEvents()
    w._pu_window_watcher._save()
    check(config.pu_window_sizes["window:facedata"][:2] == [777, 555], config.pu_window_sizes)
    w.close()
    w2 = QWidget()
    w2.resize(300, 300)
    wm.remember_window(w2, "facedata")
    check((w2.width(), w2.height()) == (777, 555), (w2.width(), w2.height()))

    class Gen:
        def generate_top_level(self, state, spec):
            lab = QLabel(spec)
            lab.set_target = lambda rid: None
            return lab

    state = types.SimpleNamespace(main_state=None, game_state=types.SimpleNamespace(data=None), generator=Gen())
    spec = types.SimpleNamespace(inner=["a", "b"], orientation="vertical", sizes=[300, 100], remember="FaceData")
    sp = Splitter(state, spec)
    sp.resize(200, 400)
    sp.show()
    app.processEvents()
    sp.setSizes([100, 300])
    sp.splitterMoved.emit(100, 1)
    saved = config.pu_window_sizes["splitter:FaceData"]
    sp2 = Splitter(state, spec)
    check(sp2.sizes() == saved or sum(sp2.sizes()) == 0 or saved == sp.sizes(), (sp2.sizes(), saved))
    sp.close()
    print("window / splitter memory: ok")


def test_voice_widget(app):
    from paragon.ui.controllers.auto import fe13_voice_widget as vw

    class FakeVoices:
        error = None
        played = []

        def all_voices(self):
            return ["SE_VOICE_CHROM_EVT_1", "SE_VOICE_CHROM_ATTACK_1", "SE_VOICE_LISSA_EVT_1"]

        def voice_codes_for_pid(self, pid):
            return ["CHROM"] if pid == "PID_クロム" else []

        def voices_for_codes(self, codes):
            return [v for v in self.all_voices() if any(f"_{c}_" in v for c in codes)]

        def play(self, name):
            self.played.append(name)

        def stop(self):
            pass

    class Data:
        def string(self, rid, f):
            return "PID_クロム" if rid == 1 else "PID_Nobody"

    gs = types.SimpleNamespace(data=Data(), dialogue=types.SimpleNamespace(pu_voices=FakeVoices()))
    state = types.SimpleNamespace(main_state=None, game_state=gs)
    w = vw.FE13VoiceWidget(state)
    w.show()
    w.set_target(1)
    app.processEvents()
    items = [w.list.item(i).text() for i in range(w.list.count())]
    check(items == ["SE_VOICE_CHROM_EVT_1", "SE_VOICE_CHROM_ATTACK_1"], items)
    w.search.setText("evt")
    visible = [w.list.item(i).text() for i in range(w.list.count()) if not w.list.item(i).isHidden()]
    check(visible == ["SE_VOICE_CHROM_EVT_1"], visible)
    w.list.setCurrentRow(0)
    w._play()
    check(gs.dialogue.pu_voices.played == ["SE_VOICE_CHROM_EVT_1"], gs.dialogue.pu_voices.played)
    w._copy()
    check(QApplication.clipboard().text() in ("$PlayVoice(SE_VOICE_CHROM_EVT_1)", ""), QApplication.clipboard().text())
    w.set_target(2)
    check("no voice set" in w.info.text(), w.info.text())
    w.show_all.setChecked(True)
    check(w.list.count() == 3, w.list.count())
    w.close()
    print("voice widget: ok")


def test_asset_preview(app):
    from paragon.ui.controllers.auto.fe13_asset_preview import FE13AssetPreview

    class Data:
        rec = {"name": "クロム_剣", "voice": "CHROM", "weapon_model": "", "conditional": "",
               "body_texture": "", "head_texture": "uHead_M_c001_c0", "hair_texture": "", "mount_texture": ""}
        reads = []

        def string(self, rid, f):
            return self.rec.get(f)

        def read_file(self, path):
            # Like the real GameData: .lz files come back already decompressed.
            self.reads.append(path)
            return b"CGFX" + b"\0" * 60

    class CoreTex:
        filename = "uHead_M_c001_c0"
        width = 64
        height = 64
        pixel_data = bytes([200, 150, 120, 255]) * (64 * 64)

    import paragon.paragon as pgn_mod

    orig_read_cgfx = pgn_mod.read_cgfx
    try:
        pgn_mod.read_cgfx = lambda raw: [CoreTex()] if raw[:4] == b"CGFX" else []
    except (AttributeError, TypeError):
        orig_read_cgfx = None

    gs = types.SimpleNamespace(data=Data())
    state = types.SimpleNamespace(main_state=None, game_state=gs)
    w = FE13AssetPreview(state)
    w.english_name = lambda name: "Chrom - Sword"
    w.set_target(1)
    check(w.title.text() == "Chrom - Sword", w.title.text())
    check("Voice: CHROM" in w.detail.text(), w.detail.text())
    if orig_read_cgfx is not None:
        labels = [lab for lab in w.findChildren(QLabel) if lab.pixmap() is not None and not lab.pixmap().isNull()]
        check(labels, "head texture thumbnail shown")
        check(set(Data.reads) == {"b/uHead_M_c001_c0.t.lz"}, Data.reads)
        pgn_mod.read_cgfx = orig_read_cgfx
    print("asset preview: ok")


def synthetic_cgfx(name="test_c0", w=16, h=16, mips=2, fmt=12):
    """Minimal CGFX texture file with the layout of the game's b/*.t.lz files."""
    import struct as st

    bpp = {12: 4, 13: 8, 3: 16, 0: 32}[fmt]
    size = sum(max(8, w >> i) * max(8, h >> i) * bpp // 8 for i in range(mips))
    d = bytearray(0x140 + size)
    d[0:4] = b"CGFX"
    st.pack_into("<HHIII", d, 4, 0xFEFF, 0x14, 0x05000000, len(d), 1)
    d[0x14:0x18] = b"DATA"
    st.pack_into("<I", d, 0x18, 0x88)
    st.pack_into("<II", d, 0x24, 1, 0xA0 - 0x28)
    d[0xA0:0xA4] = b"DICT"
    st.pack_into("<II", d, 0xA4, 0x2C, 1)
    st.pack_into("<II", d, 0xC4, 0x120 - 0xC4, 0xD0 - 0xC8)
    st.pack_into("<I", d, 0xD0, 0x20000011)
    d[0xD4:0xD8] = b"TXOB"
    st.pack_into("<I", d, 0xDC, 0x120 - 0xDC)
    st.pack_into("<II", d, 0xE8, h, w)
    st.pack_into("<I", d, 0xF8, mips)
    st.pack_into("<I", d, 0x104, fmt)
    st.pack_into("<II", d, 0x10C, h, w)
    st.pack_into("<II", d, 0x114, size, 0x140 - 0x118)
    d[0x120 : 0x120 + len(name)] = name.encode()
    return bytes(d)


def test_texture_import(app, tmp):
    from paragon.core.services import fe13_model_textures as mt
    from paragon.ui.controllers.auto.fe13_asset_preview import FE13AssetPreview

    files = {"b/test_c0.t.lz": synthetic_cgfx()}

    class Data:
        rec = {"name": "テスト", "head_texture": "test_c0"}
        written = {}

        def string(self, rid, f):
            return self.rec.get(f)

        def read_file(self, path):
            if path not in files:
                raise FileNotFoundError(path)
            return files[path]

        def write_file(self, path, contents):
            self.written[path] = bytes(contents)

        def file_exists(self, path, localized):
            return path in files

    data = Data()
    info = mt.textures(files["b/test_c0.t.lz"])
    check(len(info) == 1 and (info[0].width, info[0].mips, info[0].size) == (16, 2, 160), info)
    check(pgn.read_cgfx(files["b/test_c0.t.lz"])[0].width == 16, "synthetic file readable")

    gs = types.SimpleNamespace(data=data)
    state = types.SimpleNamespace(main_state=None, game_state=gs)
    w = FE13AssetPreview(state)
    w.english_name = lambda n: "Test"
    w.set_target(1)
    check("test_c0" in w.slots, w.slots)
    red = png(os.path.join(tmp, "red_tex.png"), (40, 40), (230, 20, 20))
    Image.new("RGBA", (40, 40), (230, 20, 20, 255)).save(red)
    w.import_into("test_c0", red)
    edits = mt.edits_for(gs)
    check(edits.is_pending("test_c0"), "import queued")
    check("resized from 40x40" in w.status.text(), w.status.text())
    tex = w._rgba("test_c0")
    px = tex[2][(8 * 16 + 8) * 4 : (8 * 16 + 8) * 4 + 4]
    check(px[0] > 180 and px[1] < 70, f"preview shows the imported color {tuple(px)}")
    new = edits.current("b/test_c0.t.lz")
    check(len(new) == len(files["b/test_c0.t.lz"]), "same file layout")
    w.undo_import("test_c0")
    check(not edits.is_pending("test_c0"), "undo")
    w.import_into("test_c0", red)
    lines = edits.flush(None)
    check(lines == ["b/test_c0.t.lz"] and "b/test_c0.t.lz" in Data.written, (lines, list(Data.written)))
    w.grab().save(os.path.join(OUT, "v1_texture_import.png"))
    print("texture import: ok")


def test_model_view(app):
    """3D view: a textured cube drawn by the Rust rasterizer, turned by dragging."""
    from paragon.core.services import fe13_models as fm
    from paragon.ui.controllers.auto.fe13_asset_preview import ModelView
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtCore import QEvent

    pos, uvs, tris = [], [], []
    for axis in range(3):
        for sign in (-1, 1):
            base = len(pos)
            for a, b in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
                v = [0.0, 0.0, 0.0]
                v[axis] = sign
                v[(axis + 1) % 3] = a
                v[(axis + 2) % 3] = b
                pos.append(tuple(v))
                uvs.append(((a + 1) / 2, (b + 1) / 2))
            tris += [(base, base + 1, base + 2), (base, base + 2, base + 3)]
    normals = [tuple(1.0 if abs(c) == 1 and i == 0 else 0.0 for i, c in enumerate(p)) for p in pos]
    mesh = fm.Mesh("cube", "mat", "tex", pos, normals, uvs, tris)
    model = fm.Model("cube", [mesh])
    tex = (2, 2, bytes([255, 0, 0, 255, 0, 255, 0, 255, 0, 0, 255, 255, 255, 255, 0, 255]))
    img = fm.render_image(model, {"tex": tex}, 120, yaw=30, pitch=20)
    check(img.size == (120, 120), img.size)
    center = img.getpixel((60, 60))
    corner = img.getpixel((2, 2))
    check(center != corner, f"cube drawn {center} vs background {corner}")
    img.save(os.path.join(OUT, "v1_model_cube.png"))

    view = ModelView()
    view.set_model(model, {"tex": tex})
    view.show()
    app.processEvents()
    before = view.pixmap().toImage()
    yaw0 = view.yaw
    press = QMouseEvent(QEvent.MouseButtonPress, QPointF(10, 10), QPointF(10, 10), Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
    move = QMouseEvent(QEvent.MouseMove, QPointF(60, 30), QPointF(60, 30), Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
    release = QMouseEvent(QEvent.MouseButtonRelease, QPointF(60, 30), QPointF(60, 30), Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
    view.mousePressEvent(press)
    view.mouseMoveEvent(move)
    view.mouseReleaseEvent(release)
    check(view.yaw != yaw0, "drag turns the model")
    check(view.pixmap().toImage() != before, "image changed after turning")
    view.grab().save(os.path.join(OUT, "v1_model_view.png"))
    view.set_model(None, {}, "Model x\nnot found")
    check("not found" in view.text(), view.text())
    view.close()
    print("3D model view: ok")


def main():
    app = QApplication.instance() or QApplication([])
    # Never block on a modal box in CI.
    QMessageBox.warning = staticmethod(lambda *a, **k: QMessageBox.Ok)
    QMessageBox.information = staticmethod(lambda *a, **k: QMessageBox.Ok)
    os.makedirs(OUT, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        test_face_data(app, tmp)
    test_window_memory(app)
    test_voice_widget(app)
    test_asset_preview(app)
    test_model_view(app)
    with tempfile.TemporaryDirectory() as tmp:
        test_texture_import(app, tmp)
    print("v1 Qt test: all checks passed")


if __name__ == "__main__":
    main()
