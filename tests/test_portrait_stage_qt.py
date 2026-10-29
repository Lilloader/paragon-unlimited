"""Offscreen Qt smoke test for the FE13 FaceData game preview (runs in CI on Windows).

Uses synthetic textures (no game files). Renders each screen to qt_out/*.png for review.
"""
import os
import sys
import types

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.chdir(os.path.join(os.path.dirname(__file__), ".."))

from PIL import Image, ImageDraw
from PySide6.QtCore import QPointF
from PySide6.QtGui import QImage, QPainter
from PySide6.QtWidgets import QApplication

from paragon.core.textures.texture import Texture
from paragon.ui.controllers.auto.fe13_portrait_stage import FE13PortraitStage, _DragItem, _CropItem, _OverlayItem


def figure(size, color, facing_left=True):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    s = size / 256
    d.ellipse([90 * s, 40 * s, 170 * s, 130 * s], fill=color + (255,))  # head
    d.rectangle([60 * s, 130 * s, 200 * s, 255 * s], fill=(80, 80, 140, 255))  # body
    ex = 105 * s if facing_left else 150 * s
    d.ellipse([ex, 80 * s, ex + 8 * s, 88 * s], fill=(0, 0, 0, 255))  # eye
    return Texture.from_pillow_image("Tex", img)


class FakeData:
    def __init__(self):
        self.rec = {
            1: dict(fsid="FSID_BU_Test_通常", portrait_file="Test_bu_通常.arc", blush_position_x=100, blush_position_y=60,
                    sweat_position_x=130, sweat_position_y=70, portrait_menu_position_x=0, portrait_menu_position_y=0,
                    portrait_menu_size_x=0, portrait_menu_size_y=0),
            2: dict(fsid="FSID_FC_Test_通常", portrait_file="Test_fc_通常.arc", blush_position_x=35, blush_position_y=38,
                    sweat_position_x=62, sweat_position_y=51, portrait_menu_position_x=30, portrait_menu_position_y=5,
                    portrait_menu_size_x=69, portrait_menu_size_y=76),
        }

    def string(self, rid, f):
        return self.rec[rid].get(f)

    def int(self, rid, f):
        return self.rec[rid].get(f)

    def set_int(self, rid, f, v):
        self.rec[rid][f] = v


class FakePortraits:
    def from_fsid(self, fsid):
        size = 256 if "_BU_" in fsid else 128
        blush = Texture.from_pillow_image("b", Image.new("RGBA", (64, 32), (255, 120, 120, 160)))
        sweat = Texture.from_pillow_image("s", Image.new("RGBA", (16, 16), (120, 180, 255, 200)))
        return {"通常": figure(size, (240, 200, 170)), "反通常": figure(size, (240, 200, 170), False), "頬": blush, "汗": sweat}


def render(stage, name):
    scene = stage.scene
    r = scene.sceneRect()
    img = QImage(int(r.width()) * 2, int(r.height()) * 2, QImage.Format_ARGB32)
    img.fill(0)
    p = QPainter(img)
    scene.render(p)
    p.end()
    os.makedirs("qt_out", exist_ok=True)
    img.save(os.path.join("qt_out", name + ".png"))


def find(stage, cls):
    return [i for i in stage.scene.items() if isinstance(i, cls)]


def main():
    app = QApplication.instance() or QApplication([])
    data = FakeData()
    gs = types.SimpleNamespace(data=data, portraits=FakePortraits())
    state = types.SimpleNamespace(main_state=None, game_state=gs)
    stage = FE13PortraitStage(state)

    # ---- BU
    stage.set_target(1)
    names = [stage.screen_box.itemText(i) for i in range(stage.screen_box.count())]
    assert names and all(stage.layouts[stage.screen_box.itemData(i)]["mode"] == "BU" for i in range(stage.screen_box.count())), names
    for i in range(stage.screen_box.count()):
        stage.screen_box.setCurrentIndex(i)
        render(stage, f"bu_{i}_{stage._screen()['id']}")
    stage.screen_box.setCurrentIndex(0)
    stage.slot_box.setCurrentIndex(stage.slot_box.findText("Right"))  # not mirrored
    item = find(stage, _DragItem)[0]
    item.setPos(item.origin + QPointF(9, 5))  # snaps to 8, 4
    assert stage.edits.get("face/Test_bu_通常.arc", "normal") == (8, 4), stage.edits.pending
    assert (data.rec[1]["blush_position_x"], data.rec[1]["blush_position_y"]) == (108, 64)
    render(stage, "bu_dragged_right")

    # Blush / sweat: independent toggles, draggable.
    stage.show_blush.setChecked(True)
    ovs = {o.kind: o for o in find(stage, _OverlayItem)}
    assert set(ovs) == {"blush"}, ovs
    stage.show_sweat.setChecked(True)
    ovs = {o.kind: o for o in find(stage, _OverlayItem)}
    assert set(ovs) == {"blush", "sweat"}, ovs
    b = ovs["blush"]
    assert (b.scenePos().x(), b.scenePos().y()) == (172 + 108, 64), b.scenePos()
    b.setPos(b.pos() + QPointF(3, -2))
    assert (data.rec[1]["blush_position_x"], data.rec[1]["blush_position_y"]) == (111, 62), data.rec[1]
    assert (data.rec[1]["sweat_position_x"], data.rec[1]["sweat_position_y"]) == (138, 74), data.rec[1]
    render(stage, "bu_overlays_right")
    stage.show_sweat.setChecked(False)
    assert {o.kind for o in find(stage, _OverlayItem)} == {"blush"}
    stage.slot_box.setCurrentIndex(stage.slot_box.findText("Left"))
    b = find(stage, _OverlayItem)[0]
    b.setPos(b.pos() + QPointF(2, 0))  # mirrored: screen +2 = texture -2
    assert data.rec[1]["blush_position_x"] == 109, data.rec[1]
    render(stage, "bu_overlays_left")
    stage.show_blush.setChecked(False)
    stage.slot_box.setCurrentIndex(stage.slot_box.findText("Right"))

    stage.slot_box.setCurrentIndex(stage.slot_box.findText("Left"))  # mirrored: screen +4 = texture -4
    item = find(stage, _DragItem)[0]
    assert abs(item.pos().x() - (item.origin.x() - 8)) < 0.01, (item.pos(), item.origin)
    item.setPos(item.origin + QPointF(4, 4))
    assert stage.edits.get("face/Test_bu_通常.arc", "normal") == (-4, 4), stage.edits.pending
    assert data.rec[1]["blush_position_x"] == 97

    stage.snap.setChecked(False)
    stage.expression_box.setCurrentIndex(stage.expression_box.findData("反通常"))
    item = find(stage, _DragItem)[0]
    item.setPos(item.origin + QPointF(-3, 1))
    assert stage.edits.get("face/Test_bu_通常.arc", "reversed") == (3, 1), stage.edits.pending
    assert data.rec[1]["blush_position_x"] == 97  # reversed set does not move blush

    stage._on_reset()
    assert stage.edits.get("face/Test_bu_通常.arc", "reversed") == (0, 0)

    # ---- FC
    stage.set_target(2)
    names = [stage.screen_box.itemText(i) for i in range(stage.screen_box.count())]
    assert names and all(stage.layouts[stage.screen_box.itemData(i)]["mode"] == "FC" for i in range(stage.screen_box.count())), names
    idx = [i for i in range(stage.screen_box.count()) if "Unit info" in stage.screen_box.itemText(i)][0]
    stage.screen_box.setCurrentIndex(idx)
    item = find(stage, _DragItem)[0]
    assert (item.pos().x(), item.pos().y()) == (1 - (128 - 30 - 69), -3 - 5), item.pos()
    item.setPos(item.origin + QPointF(2, 1))
    assert (data.rec[2]["portrait_menu_position_x"], data.rec[2]["portrait_menu_position_y"]) == (32, 4), data.rec[2]
    render(stage, "fc_unit_info_dragged")
    data.rec[2]["portrait_menu_position_x"], data.rec[2]["portrait_menu_position_y"] = 30, 5
    idx = [i for i in range(stage.screen_box.count()) if "crop box" in stage.screen_box.itemText(i)][0]
    stage.screen_box.setCurrentIndex(idx)
    crop = find(stage, _CropItem)[0]
    crop.setPos(crop.pos() + QPointF(-4, 3))
    assert (data.rec[2]["portrait_menu_position_x"], data.rec[2]["portrait_menu_position_y"]) == (26, 8), data.rec[2]
    for i in range(stage.screen_box.count()):
        stage.screen_box.setCurrentIndex(i)
        render(stage, f"fc_{i}_{stage._screen()['id']}")
    print("portrait stage Qt test: all checks passed")


if __name__ == "__main__":
    main()
