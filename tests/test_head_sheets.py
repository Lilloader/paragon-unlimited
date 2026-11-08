"""Head sheets (Data/FE13/PU_Heads): every sheet is listed, has the game's size and transparency,
and its heads can be put on a class body. No game files: a stand-in class for the target body."""
import os
import sys
import types

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.chdir(os.path.join(os.path.dirname(__file__), ".."))

from PIL import Image

from paragon.unlimited.sprites import sprite_parts as sp


def check(cond, msg):
    if not cond:
        raise AssertionError(msg)


def test_sheets():
    sheets = sp.head_sheets()
    check(len(sheets) >= 75, len(sheets))
    names = {h.name for h in sheets}
    for n in ("Chrom", "Frederick", "Nowi", "Nah", "Gangrel", "Robin (M) hair 10", "Robin (F) hair 34", "Lissa"):
        check(n in names, n)
    for h in sheets:
        with Image.open(h.path) as im:
            check(im.size == (128, 512), (h.name, im.size))
            alphas = set(im.convert("RGBA").split()[3].tobytes()) - {0}
        allowed = {68, 119, 136, 255} if h.character[:2].isdigit() else {68, 136}  # Robin: opaque hair (tinted in game), as the game
        check(alphas <= allowed, (h.name, sorted(alphas - allowed)))
        check(len(h.anchors) >= 36, (h.name, len(h.anchors)))
        cells, layout = sp.head_sheet_cells(h)
        check(all(0 <= x < h.cell[0] and 0 <= y < h.cell[1] for px in cells.values() for (x, y) in px), h.name)
        check(not any(r >= 12 for (_c, r) in cells), (h.name, "shadow rows"))
    walhart = [h for h in sheets if h.name == "Walhart"][0]
    check(walhart.cell == (32, 35), "flier layout: 32 x 35 frames")
    print(f"{len(sheets)} head sheets: ok")


def test_move_and_fill_rows():
    nah = [h for h in sp.head_sheets() if h.name == "Nah"][0]
    cells, layout = sp.head_sheet_cells(nah)
    check((0, 10) in cells and cells[(0, 10)] == cells[(0, 0)], "rows 11-12 take the head of rows 1-2")
    # a body whose heads sit 3 pixels lower and 1 to the right in every frame
    T = types.SimpleNamespace(cell=(32, 32), anchors={k: (x + 1, y + 3) for k, (x, y) in layout.anchors.items()})
    moved = sp.move_heads(cells, layout, T)
    a = sorted(cells[(1, 4)])[0]
    check((a[0] + 1, a[1] + 3) in moved[(1, 4)], "moved by the anchor difference")
    print("move and rows 11-12: ok")


def test_edit_heads():
    from paragon.unlimited.sprites import sprite_sheets as ws

    cells = {(0, 0): {(1, 1): "a", (2, 2): "b"}, (1, 0): {(5, 5): "c"}}
    out = ws.edit_heads(cells, [[0, 0, 1, 1], [0, 10, 2, 2]], {"0,10": "0,0", "1,1": "1,0"})
    check(out[(0, 0)] == {(2, 2): "b"}, "erased in its frame")
    check(out[(0, 10)] == {}, "a copy keeps what was erased in the source, minus its own")
    check(out[(1, 1)] == {(5, 5): "c"} and cells[(0, 0)] == {(1, 1): "a", (2, 2): "b"}, "copy; input untouched")
    p = ws.WorkshopProject(name="X", head_erased=[[0, 0, 1, 1]], head_copies={"0,10": "0,0"})
    q = ws.WorkshopProject.from_json(p.to_json())
    check(q.head_erased == [[0, 0, 1, 1]] and q.head_copies == {"0,10": "0,0"}, "saved in the project")
    check(ws.WorkshopProject.from_json('{"name": "old"}').head_copies == {}, "old projects open")
    # mirror and resize keep the head on its neck (the middle of the bottom row)
    head = {(x, y): "h" for x in range(10, 16) for y in range(4, 12)}
    head[(10, 4)] = "L"
    f = ws._flip(head)
    check(f[(15, 4)] == "L" and len(f) == len(head), "mirrored")
    big = ws._scale(head, 1.5)
    ys = [y for _x, y in big]
    xs = [x for x, _y in big]
    check(max(ys) == 11 and max(ys) - min(ys) + 1 == 12 and max(xs) - min(xs) + 1 == 9, (min(xs), max(xs), min(ys), max(ys)))
    small = ws._scale(head, 0.75)
    ys = [y for _x, y in small]
    check(max(ys) == 11 and max(ys) - min(ys) + 1 == 6, (min(ys), max(ys)))
    out = ws.edit_heads({(0, 0): head}, head_flip=["0,0"], head_scale={"0,0": 0.75})
    check(len(out[(0, 0)]) < len(head), "flip + resize")
    # head behind the body: only where the body is empty
    from paragon.unlimited.sprites import sprite_parts as sp
    body = ws.Sheet.blank(32, 32)
    body.rgba[(5 * 32 + 12) * 4 : (5 * 32 + 12) * 4 + 4] = bytes((1, 2, 3, 136))
    cells = {(0, 0): {(12, 5): (9, 9, 9, 136), (13, 5): (9, 9, 9, 136)}}
    front, _m, _c = sp.compose(body, cells, (32, 32))
    back, _m, _c = sp.compose(body, cells, (32, 32), behind={(0, 0)})
    check(tuple(front.rgba[(5 * 32 + 12) * 4:(5 * 32 + 12) * 4 + 3]) == (9, 9, 9), "in front")
    check(tuple(back.rgba[(5 * 32 + 12) * 4:(5 * 32 + 12) * 4 + 3]) == (1, 2, 3), "behind: the body stays")
    check(tuple(back.rgba[(5 * 32 + 13) * 4:(5 * 32 + 13) * 4 + 3]) == (9, 9, 9), "behind: head where the body is empty")
    p = ws.WorkshopProject(head_behind=True, head_layer_swap=["1,0"])
    check(ws.Workshop.behind_frames(p, {(0, 0), (1, 0)}) == {(0, 0)}, "per-frame layer switch")
    print("head erase / copy / mirror / size / layer: ok")


if __name__ == "__main__":
    test_sheets()
    test_move_and_fill_rows()
    test_edit_heads()
    print("ALL OK")
