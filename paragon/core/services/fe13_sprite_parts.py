"""Paragon Unlimited: map sprites as separate heads and bodies (FE13), like Fates keeps them.

Awakening stores every class sprite with a head already drawn on it. The game also has, for most
classes, the generic sprite (e.g. ドラゴンナイト男, Wyvern Rider) and many character versions
(ドラゴンナイトクロム...) that differ only in the head. Data/FE13/PU_SpriteParts.json (built from the
game files by scripts/pu_build_sprite_parts.py) holds, per class and sex:

  union    pixels where a character version can differ from the generic sprite (head area)
  fill     the pixel under the head (what the versions agree on) or transparent
  core     the generic head itself
  anchors  per frame cell: centre x / top y of the head, to line heads up between classes

With it a head (taken from any character sprite) can be put on any class body: the body's head
area is cleared, the head is moved by the difference of the two classes' anchors in every frame,
and then each frame can still be moved by hand. Frames correspond by cell (column = frame,
row = animation), which every class shares; fliers use taller cells (32 x 35).
"""
import base64
import json
import os
import zlib
from array import array
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

PARTS_PATH = "Data/FE13/PU_SpriteParts.json"

# Fill and outline transparency of the game's own map sprites (RGBA4 alpha 8/15 and 4/15).
GAME_FILL_ALPHA = 136
GAME_OUTLINE_ALPHA = 68
OUTLINE_LUMA = 48  # the game draws outlines in (34,34,34) and (51,51,68) at alpha 68
OUTLINE_MAX = 90

# Japanese names in sprite file names -> English (characters not in the character table too).
CHARACTER_NAMES = {
    "クロム": "Chrom", "リズ": "Lissa", "フレデリク": "Frederick", "ヴィオール": "Virion", "ソワレ": "Sully",
    "ヴェイク": "Vaike", "ソール": "Stahl", "ミリエル": "Miriel", "カラム": "Kellam", "ロンクー": "Lon'qu",
    "スミア": "Sumia", "ガイア": "Gaius", "マリアベル": "Maribelle", "リヒト": "Ricken", "ベルベット": "Panne",
    "グレゴ": "Gregor", "ノノ": "Nowi", "オリヴィエ": "Olivia", "セルジュ": "Cherche", "ヘンリー": "Henry",
    "サーリャ": "Tharja", "ティアモ": "Cordelia", "ドニ": "Donnel", "アンナ": "Anna", "サイリ": "Say'ri",
    "チキ": "Tiki", "フラヴィア": "Flavia", "バジーリオ": "Basilio", "ギャンレル": "Gangrel", "エメリナ": "Emmeryn",
    "インバース": "Aversa", "レンハ": "Yen'fay", "パリス": "Priam", "エクセライ": "Excellus", "ルキナ": "Lucina",
    "マルス": "Lucina (Marth)", "ウード": "Owain", "アズール": "Inigo", "ブレディ": "Brady", "ジェローム": "Gerome",
    "マーク男": "Morgan (M)", "マーク女": "Morgan (F)", "マーク": "Morgan", "シャンブレー": "Yarne", "ロラン": "Laurent",
    "シンシア": "Cynthia", "セレナ": "Severa", "デジェル": "Kjelle", "ノワール": "Noire", "ンン": "Nah",
    "ファウダー": "Validar", "ムスタファー": "Mustafa", "プレイヤー男": "Robin (M)", "プレイヤー女": "Robin (F)",
    "仮面女": "Lucina (masked)", "ディジェル": "Kjelle", "獣": "Beast", "チキ祈り": "Tiki (praying)",
}


def _luma(r, g, b):
    return (r * 299 + g * 587 + b * 114) // 1000


@dataclass
class ClassParts:
    key: str  # "<stem>|<男/女>"
    stem: str
    sex: str
    generic: str
    variants: List[str]
    cell: Tuple[int, int]
    size: Tuple[int, int]
    union: List[int]
    fill: Dict[int, Tuple[int, int, int, int]]
    core: set
    anchors: Dict[Tuple[int, int], Tuple[float, int]]
    union_set: set = field(default_factory=set)


class PartsLibrary:
    def __init__(self, path: str = PARTS_PATH):
        with open(path, "r", encoding="utf-8") as f:
            self.raw = json.load(f)
        self._cache: Dict[str, ClassParts] = {}

    # ---- lookup
    def class_keys(self) -> List[str]:
        return sorted(self.raw["classes"])

    def has(self, key: str) -> bool:
        return key in self.raw["classes"]

    def parts(self, key: str) -> ClassParts:
        if key in self._cache:
            return self._cache[key]
        c = self.raw["classes"][key]
        union = array("I")
        union.frombytes(zlib.decompress(base64.b64decode(c["union"])))
        fill_b = zlib.decompress(base64.b64decode(c["fill"]))
        core_b = zlib.decompress(base64.b64decode(c["core"]))
        fill, core = {}, set()
        for i, idx in enumerate(union):
            px = tuple(fill_b[i * 4 : i * 4 + 4])
            fill[idx] = px
            if core_b[i >> 3] & (0x80 >> (i & 7)):
                core.add(idx)
        anchors = {}
        for k, (x, y) in c["anchors"].items():
            cc, rr = k.split(",")
            anchors[(int(cc), int(rr))] = (float(x), int(y))
        p = ClassParts(key, c["stem"], c["sex"], c["generic"], list(c["variants"]), tuple(c["cell"]),
                       tuple(c["size"]), list(union), fill, core, anchors, set(union))
        self._cache[key] = p
        return p

    def head_sources(self, character: str) -> List[Tuple[str, str]]:
        """[(class key, sprite name)] the character has a map sprite in."""
        return [(h["class"], h["sprite"]) for h in self.raw["heads"].get(character, [])]

    def characters(self) -> List[str]:
        return sorted(self.raw["heads"])

    def key_for_sprite(self, sprite: str) -> Optional[str]:
        """Class key of a game sprite name (generic or character version)."""
        best = None
        for key, c in self.raw["classes"].items():
            if sprite == c["generic"] or any(sprite == c["stem"] + v for v in c["variants"]):
                return key
            if sprite.startswith(c["stem"]) and (best is None or len(c["stem"]) > len(self.raw["classes"][best]["stem"])):
                best = key
        return best


# ---------------------------------------------------------------------------- names (English)


class Names:
    """English labels for sprite names, classes and characters (display only - files keep their
    Japanese names)."""

    def __init__(self, gd=None, lib: Optional["PartsLibrary"] = None):
        self.jobs: Dict[str, str] = {}
        self.people: Dict[str, str] = dict(CHARACTER_NAMES)
        if lib is not None:
            self.jobs.update(lib.raw.get("job_names", {}))
            for k, v in lib.raw.get("people", {}).items():
                self.people.setdefault(k, v)
        if gd is not None:
            try:
                t = gd.table("jobs")
                for j in gd.items(t[0], t[1]):
                    k = gd.key(j)
                    if k and k.startswith("JID_"):
                        en = gd.display(j)
                        if en and en != k:
                            self.jobs[k[4:]] = en
            except Exception:
                pass
            try:
                t = gd.table("characters")
                for p in gd.items(t[0], t[1]):
                    k = gd.key(p)
                    if k and k.startswith("PID_"):
                        en = gd.display(p)
                        if en and en != k and not en.startswith("PID_"):
                            self.people.setdefault(k[4:], en)
            except Exception:
                pass

    def job(self, stem: str, sex: str = "") -> str:
        en = self.jobs.get(stem + sex) or self.jobs.get(stem + "男") or self.jobs.get(stem + "女") or self.jobs.get(stem)
        if not en:
            return stem + sex
        return en + {"男": " (M)", "女": " (F)"}.get(sex, "")

    def character(self, name: str) -> str:
        if name in self.people:
            return self.people[name]
        if name[:-1].isdigit() and name[-1:] in "男女":
            return f"Robin ({'M' if name[-1] == '男' else 'F'}) hair {name[:-1]}"
        if name[-1:] in "男女" and name[:-1] in self.people:
            return self.people[name[:-1]] + (" (M)" if name[-1] == "男" else " (F)")
        return name

    def sprite(self, sprite: str, lib: Optional[PartsLibrary] = None) -> str:
        """'ドラゴンナイトクロム' -> 'Wyvern Rider - Chrom', 'ドラゴンナイト男' -> 'Wyvern Rider (M)'."""
        stems = sorted({k[:-1] if k[-1:] in "男女" else k for k in self.jobs}, key=len, reverse=True)
        for st in stems:
            if sprite.startswith(st):
                rest = sprite[len(st):]
                if rest in ("男", "女", ""):
                    return self.job(st, rest)
                return f"{self.job(st)} - {self.character(rest)}"
        return sprite


# ---------------------------------------------------------------------------- image helpers
# Sheets are fe13_sprite_workshop.Sheet (width, height, rgba bytearray).


def _px(sheet, i):
    o = i * 4
    return tuple(sheet.rgba[o : o + 4])


def headless_body(sheet, parts: ClassParts):
    """The class body with its head cleared (the head area takes what lies under it)."""
    out = sheet.copy()
    for i in parts.union:
        if i * 4 + 4 <= len(out.rgba):
            out.rgba[i * 4 : i * 4 + 4] = bytes(parts.fill[i])
    return out


def head_pixels(sheet, parts: ClassParts) -> Dict[int, Tuple[int, int, int, int]]:
    """{pixel index: rgba} of the head in a sprite drawn on this class body (pixels in the head
    area that differ from the body under it)."""
    out = {}
    n = sheet.width * sheet.height
    for i in parts.union:
        if i >= n:
            continue
        p = _px(sheet, i)
        if p[3] and p != parts.fill[i]:
            out[i] = p
    return out


def head_area(parts: ClassParts, grow: int = 2) -> set:
    """The generic head area grown by a few pixels (for sheets not drawn on a game body)."""
    w = parts.size[0]
    area = set(parts.core)
    for _ in range(grow):
        nxt = set(area)
        for i in area:
            x, y = i % w, i // w
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                if 0 <= x + dx < w and 0 <= y + dy < parts.size[1]:
                    nxt.add((y + dy) * w + x + dx)
        area = nxt
    return area


def split_sheet(sheet, parts: ClassParts, game_body: bool):
    """(body without head, {cell: {(x, y): rgba}} head pixels per cell in cell coordinates).
    game_body: the sheet is drawn on this class's own body (then the body under the head is
    known); otherwise the head is everything in the grown generic head area."""
    w = sheet.width
    cw, ch = parts.cell
    if game_body:
        heads = head_pixels(sheet, parts)
        body = headless_body(sheet, parts)
    else:
        area = head_area(parts)
        heads = {}
        body = sheet.copy()
        for i in area:
            if i * 4 + 4 > len(sheet.rgba):
                continue
            p = _px(sheet, i)
            if p[3]:
                heads[i] = p
            body.rgba[i * 4 : i * 4 + 4] = b"\0\0\0\0"
    cells: Dict[Tuple[int, int], Dict[Tuple[int, int], tuple]] = {}
    for i, p in heads.items():
        x, y = i % w, i // w
        c, r = x // cw, y // ch
        cells.setdefault((c, r), {})[(x - c * cw, y - r * ch)] = p
    return body, cells


def move_heads(cells, src: ClassParts, dst: ClassParts):
    """Head cells of class src placed in class dst's frames (anchor to anchor). Cells keep
    cell-local coordinates of the destination."""
    out = {}
    for cell, px in cells.items():
        if cell not in dst.anchors or cell not in src.anchors:
            continue
        sx, sy = src.anchors[cell]
        dx, dy = dst.anchors[cell]
        ox = int(round((dx - cell[0] * dst.cell[0]) - (sx - cell[0] * src.cell[0])))
        oy = int(round((dy - cell[1] * dst.cell[1]) - (sy - cell[1] * src.cell[1])))
        out[cell] = {(x + ox, y + oy): p for (x, y), p in px.items()}
    return out


def compose(body, cells, cell_size: Tuple[int, int], offsets: Optional[Dict[str, List[int]]] = None):
    """Body + head cells (each moved by offsets["c,r"]), heads kept inside their frame.
    Returns (sheet, head mask bytearray, cut count)."""
    out = body.copy()
    w, h = out.width, out.height
    cw, ch = cell_size
    mask = bytearray(w * h)
    cut = 0
    offsets = offsets or {}
    for (c, r), px in cells.items():
        ox, oy = offsets.get(f"{c},{r}", (0, 0))
        for (x, y), p in px.items():
            tx, ty = x + int(ox), y + int(oy)
            if not (0 <= tx < cw and 0 <= ty < ch):
                cut += 1
                continue
            X, Y = c * cw + tx, r * ch + ty
            if X >= w or Y >= h:
                cut += 1
                continue
            i = Y * w + X
            out.rgba[i * 4 : i * 4 + 4] = bytes(p)
            mask[i] = 1
    return out, mask, cut


def is_full_opacity(sheet) -> bool:
    """True when the sheet uses plain opaque pixels (a normal image), not the game's levels."""
    a = sheet.rgba[3::4]
    vis = [v for v in a if v]
    return bool(vis) and sum(1 for v in vis if v == 255) > len(vis) * 0.6


def game_opacity(sheet, fill_alpha: int = GAME_FILL_ALPHA, outline_alpha: Optional[int] = None):
    """Opaque pixels -> the game's see-through levels: fill_alpha, near-black outline pixels at half
    (the game's sprites: fill 136 = 53 %, outlines - always (34,34,34) or (51,51,68) - 68 = 27 %).
    Already translucent pixels stay as they are."""
    q = lambda v: max(17, min(255, int(round(v / 17.0)) * 17))  # RGBA4 steps
    fa = q(fill_alpha)
    oa = q(outline_alpha if outline_alpha is not None else fill_alpha / 2)
    out = sheet.copy()
    p = out.rgba
    for i in range(0, len(p), 4):
        if p[i + 3] == 255:
            dark = _luma(p[i], p[i + 1], p[i + 2]) < OUTLINE_LUMA and max(p[i], p[i + 1], p[i + 2]) < OUTLINE_MAX
            p[i + 3] = oa if dark else fa
    return out


_LIB: Optional[PartsLibrary] = None


def library() -> Optional[PartsLibrary]:
    global _LIB
    if _LIB is None and os.path.isfile(PARTS_PATH):
        _LIB = PartsLibrary(PARTS_PATH)
    return _LIB
