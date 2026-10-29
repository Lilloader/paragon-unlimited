"""Paragon Unlimited - FE13 Sprite Workshop: build a map sprite from a body sheet and a head
layer, and generate its player / enemy / ally colors the way the game's own sprites do.

How Awakening stores map sprites (measured on the game's files)
---------------------------------------------------------------
* map/unit/<name>青.ctpk.lz, <name>赤.ctpk.lz, <name>緑.ctpk.lz: blue = player, red = enemy,
  green = ally (some enemy-only sprites, e.g. Risen "…屍", exist in red only).
* Each is a CTPK with one full-color RGBA4 texture (format 4), usually 128 x 512: a sheet of all
  animation frames (cells of 32 x 32, or the size given in the BMap icon entry). There is no
  palette and no separate palette data; the three colors are three separate full images with the
  same size, frames, alignment and transparency.
* The head is drawn into the sheet. The animation (which cell is shown when, frame timing) is in
  the BMap icon entry (GameData "BMap Icons"), shared by all three colors.
* Only team-colored parts change between the colors: in all 693 blue/red/green sets of the
  game, 34 % of the visible pixels change, almost all of them blue-hued; skin, hair, metal and
  outlines stay the same. Within one sprite, one blue color always becomes the same red/green;
  across sprites the game uses slightly different reds/greens for the same blue.

How the Workshop converts colors (in this order, for every visible pixel)
---------------------------------------------------------------------------
1. Pixels of the head layer are never changed.
2. Where the body is the reference sprite's own pixel (same position, same color), the
   reference sprite's red / green pixel is used: exactly what the game does for that body.
3. Otherwise the reference sprite's own color mapping (blue color -> red/green color), then
   the mapping measured over all game sprites (Data/FE13/PU_FactionColors.json).
4. A blue-hued color the game never uses is converted like the closest game color (same hue
   change, same saturation and brightness ratios). Any other color stays as it is.
The output is the game's own format: CTPK, RGBA4, the reference sprite's size and texture name.
"""
import colorsys
import hashlib
import json
import logging
import os
import struct
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

COLORS = [("青", "blue", "Player"), ("赤", "red", "Enemy"), ("緑", "green", "Ally")]
TABLE_PATH = os.path.join("Data", "FE13", "PU_FactionColors.json")
UNIT_DIR = "map/unit"
RGBA4 = 4
DEFAULT_CELL = 32
PROJECT_VERSION = 2


# ----------------------------------------------------------------------------- images


@dataclass
class Sheet:
    """RGBA8 image (values are multiples of 17 once quantized to the game's RGBA4)."""

    width: int
    height: int
    rgba: bytearray

    @staticmethod
    def blank(w: int, h: int) -> "Sheet":
        return Sheet(w, h, bytearray(w * h * 4))

    def copy(self) -> "Sheet":
        return Sheet(self.width, self.height, bytearray(self.rgba))

    def quantized(self) -> "Sheet":
        """Round every channel to 4 bits, as the game stores it."""
        q = bytearray(len(self.rgba))
        for i, v in enumerate(self.rgba):
            q[i] = ((v * 15 + 127) // 255) * 17
        return Sheet(self.width, self.height, q)

    def to_pil(self):
        from PIL import Image

        return Image.frombytes("RGBA", (self.width, self.height), bytes(self.rgba))

    @staticmethod
    def from_pil(img) -> "Sheet":
        img = img.convert("RGBA")
        return Sheet(img.width, img.height, bytearray(img.tobytes()))

    def digest(self) -> str:
        return hashlib.sha256(bytes(self.rgba)).hexdigest()


def _morton(x: int, y: int) -> int:
    m = 0
    for k in range(3):
        m |= ((x >> k) & 1) << (2 * k)
        m |= ((y >> k) & 1) << (2 * k + 1)
    return m


_M = [[_morton(x, y) for x in range(8)] for y in range(8)]


def _addr(x: int, y: int, w: int) -> int:
    return ((y // 8) * (w // 8) + (x // 8)) * 64 + _M[y % 8][x % 8]


def decode_rgba4(data: bytes, w: int, h: int) -> Sheet:
    out = bytearray(w * h * 4)
    for y in range(h):
        for x in range(w):
            v = struct.unpack_from("<H", data, 2 * _addr(x, y, w))[0]
            o = (y * w + x) * 4
            out[o] = ((v >> 12) & 15) * 17
            out[o + 1] = ((v >> 8) & 15) * 17
            out[o + 2] = ((v >> 4) & 15) * 17
            out[o + 3] = (v & 15) * 17
    return Sheet(w, h, out)


def encode_rgba4(sheet: Sheet) -> bytes:
    w, h = sheet.width, sheet.height
    out = bytearray(w * h * 2)
    p = sheet.rgba
    for y in range(h):
        for x in range(w):
            o = (y * w + x) * 4
            v = (
                ((p[o] * 15 + 127) // 255) << 12
                | ((p[o + 1] * 15 + 127) // 255) << 8
                | ((p[o + 2] * 15 + 127) // 255) << 4
                | ((p[o + 3] * 15 + 127) // 255)
            )
            struct.pack_into("<H", out, 2 * _addr(x, y, w), v)
    return bytes(out)


def ctpk_info(ctpk: bytes) -> Tuple[int, int, int, int, int]:
    """(pixel offset, length, format, width, height) of the first texture of a CTPK."""
    if ctpk[:4] != b"CTPK":
        raise ValueError("Not a CTPK texture file.")
    base = struct.unpack_from("<I", ctpk, 8)[0]
    _fn, length, off, fmt, w, h = struct.unpack_from("<IIIIHH", ctpk, 0x20)
    return base + off, length, fmt, w, h


def sheet_from_ctpk(ctpk: bytes) -> Sheet:
    off, length, fmt, w, h = ctpk_info(ctpk)
    if fmt != RGBA4:
        raise ValueError(f"This sprite uses texture format {fmt}; the game's map sprites use RGBA4 (4).")
    return decode_rgba4(ctpk[off : off + length], w, h)


def ctpk_with_sheet(template: bytes, sheet: Sheet) -> bytes:
    """A copy of the template CTPK (same header, texture name, size and format) with new pixels."""
    off, length, fmt, w, h = ctpk_info(template)
    if (sheet.width, sheet.height) != (w, h):
        raise ValueError(f"The sheet is {sheet.width} x {sheet.height}; the game's file is {w} x {h}.")
    if fmt != RGBA4:
        raise ValueError(f"The template uses texture format {fmt}, not RGBA4.")
    pixels = encode_rgba4(sheet)
    if len(pixels) != length:
        raise ValueError("Unexpected texture size.")
    out = bytearray(template)
    out[off : off + length] = pixels
    return bytes(out)


# Header of a single-texture CTPK as the game writes them (texture name "Tex").
_CTPK_HEADER = bytes.fromhex(
    "4354504b010001008000000000400000480000005000000000000000000000004400000000400000"
    "000000000d000000800080000102000010000000" "9d30434e004000005465780092 39a0d2"
    "000000000d010100".replace(" ", "")
)


def new_ctpk(w: int, h: int, pixels: bytes, fmt: int = RGBA4) -> bytes:
    """A new single-texture CTPK laid out like the game's files (used when there is no
    reference sprite to copy the header from)."""
    hdr = bytearray(_CTPK_HEADER) + b"\0" * (0x80 - len(_CTPK_HEADER))
    section = (len(pixels) + 0x7F) & ~0x7F
    struct.pack_into("<I", hdr, 0x0C, section)
    struct.pack_into("<I", hdr, 0x24, len(pixels))
    struct.pack_into("<I", hdr, 0x2C, fmt)
    struct.pack_into("<HH", hdr, 0x30, w, h)
    struct.pack_into("<I", hdr, 0x40, len(pixels))
    hdr[0x50] = fmt
    return bytes(hdr) + pixels + b"\0" * (section - len(pixels))


def _decompress(data: bytes) -> bytes:
    if data[:4] == b"CTPK":
        return data
    from paragon import paragon as pgn

    return bytes(pgn.decompress_lz13(data))


def load_sheet_file(path: str) -> Sheet:
    """A sheet from a PNG (or any image Pillow reads) or a .ctpk / .ctpk.lz file."""
    low = path.lower()
    if low.endswith(".ctpk") or low.endswith(".ctpk.lz") or low.endswith(".lz"):
        with open(path, "rb") as f:
            return sheet_from_ctpk(_decompress(f.read()))
    from PIL import Image

    with Image.open(path) as img:
        return Sheet.from_pil(img)


def file_digest(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ----------------------------------------------------------------------------- composition


def compose(body: Sheet, head: Optional[Sheet], dx: int = 0, dy: int = 0,
            frames: Optional[Dict[str, List[int]]] = None, cell_w: int = 0, cell_h: int = 0,
            src: Optional[list] = None, info: Optional[dict] = None) -> Tuple[Sheet, bytearray]:
    """Head layer over body (head on top), head moved by (dx, dy). Returns (sheet, head mask)
    where head mask[i] = 1 for pixels that come from the head layer. The body is not moved.
    Every visible head pixel replaces the body pixel exactly (color and alpha level).

    Per-frame head positions: with a frame size (cell_w x cell_h), the head pixels of each frame
    cell move by (dx, dy) plus frames["col,row"] for that cell, and stay inside that cell (a pixel
    pushed past the cell edge is cut off instead of landing in the next frame; counted in
    info["cut"]). src, when given, receives for every head pixel of the result the index of the
    head-layer pixel it came from."""
    out = body.quantized()
    mask = bytearray(body.width * body.height)
    if src is not None:
        src.clear()
        src.extend([-1] * (body.width * body.height))
    if head is None:
        return out, mask
    hq = head.quantized()
    w, h = body.width, body.height
    frames = frames or {}
    cut = 0
    for y in range(hq.height):
        for x in range(hq.width):
            s = (y * hq.width + x) * 4
            a = hq.rgba[s + 3]
            if a == 0:
                continue
            ox, oy = dx, dy
            if cell_w and cell_h:
                cx, cy = x // cell_w, y // cell_h
                f = frames.get(f"{cx},{cy}")
                if f:
                    ox, oy = ox + int(f[0]), oy + int(f[1])
                tx, ty = x + ox, y + oy
                if not (cx * cell_w <= tx < (cx + 1) * cell_w and cy * cell_h <= ty < (cy + 1) * cell_h):
                    cut += 1
                    continue
            else:
                tx, ty = x + ox, y + oy
            if not (0 <= tx < w and 0 <= ty < h):
                cut += 1
                continue
            t = (ty * w + tx) * 4
            # Pixel art: the head pixel replaces the body pixel, alpha included. The game's map
            # sprites use alpha as a few fixed levels (0, 68, 136, 255), so nothing is blended.
            out.rgba[t : t + 4] = hq.rgba[s : s + 4]
            mask[ty * w + tx] = 1
            if src is not None:
                src[ty * w + tx] = y * hq.width + x
    if info is not None:
        info["cut"] = cut
    return out, mask


def extract_layer(sheet: Sheet, base: Sheet) -> Sheet:
    """The pixels of sheet that differ from base (e.g. a character's head on a class body: the
    character's game sprite minus the generic class sprite). Same size required."""
    if (sheet.width, sheet.height) != (base.width, base.height):
        raise ValueError("Both sheets must have the same size.")
    out = Sheet.blank(sheet.width, sheet.height)
    a, b = sheet.rgba, base.rgba
    for i in range(0, len(a), 4):
        if a[i + 3] and a[i : i + 4] != b[i : i + 4]:
            out.rgba[i : i + 4] = a[i : i + 4]
    return out


# ----------------------------------------------------------------------------- color conversion


def _key(r: int, g: int, b: int) -> int:
    return ((r * 15 + 127) // 255) << 8 | ((g * 15 + 127) // 255) << 4 | ((b * 15 + 127) // 255)


def _rgb(key: int) -> Tuple[int, int, int]:
    return ((key >> 8) & 15) * 17, ((key >> 4) & 15) * 17, (key & 15) * 17


def _hsv(key: int):
    r, g, b = _rgb(key)
    return colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)


def is_team_blue(key: int) -> bool:
    h, s, v = _hsv(key)
    return 0.5 <= h <= 0.72 and s >= 0.25 and v >= 0.12


class FactionTable:
    """Blue color -> red / green color, measured on the game's sprites."""

    def __init__(self, data: dict):
        self.source = data.get("source", "")
        self.maps: Dict[str, Dict[int, List[Tuple[int, int]]]] = {}
        for name in ("red", "green"):
            m = {}
            for k, targets in data.get(name, {}).items():
                m[int(k, 16)] = [(int(t, 16), n) for t, n in targets]
            self.maps[name] = m
        self._team = {}

    @classmethod
    def load(cls, path: str = TABLE_PATH) -> "FactionTable":
        with open(path, "r", encoding="utf-8") as f:
            return cls(json.load(f))

    def dominant(self, name: str, key: int, min_share: Optional[float] = None) -> Optional[int]:
        """The color the game turns this blue color into, or the color itself when the game
        mostly keeps it. A blue-hued color counts as a team color when the game changes it in
        at least 35 % of its uses, any other color at 60 % (measured: 84 % of team pixels within
        two color steps of the game's own, 99 % of kept pixels kept). None: color not in the table."""
        targets = self.maps[name].get(key)
        if not targets:
            return None
        total = sum(n for _t, n in targets)
        changed = [(t, n) for t, n in targets if t != key]
        share = sum(n for _t, n in changed) / total if total else 0.0
        if min_share is None:
            min_share = 0.35 if is_team_blue(key) else 0.6
        if changed and share >= min_share:
            return max(changed, key=lambda tn: tn[1])[0]
        return key

    def team_colors(self, name: str) -> List[Tuple[int, int]]:
        """[(blue key, target key)] of game colors that change (for the closest-color rule)."""
        if name not in self._team:
            out = []
            for k in self.maps[name]:
                t = self.dominant(name, k)
                if t is not None and t != k and is_team_blue(k):
                    out.append((k, t))
            self._team[name] = out
        return self._team[name]

    def closest_rule(self, name: str, key: int) -> Optional[int]:
        """Convert an unknown blue color like the closest game color (HSV)."""
        h, s, v = _hsv(key)
        best, bd = None, 9.0
        for k, t in self.team_colors(name):
            hk, sk, vk = _hsv(k)
            d = min(abs(h - hk), 1 - abs(h - hk)) * 4 + abs(s - sk) + abs(v - vk) * 1.5
            if d < bd:
                best, bd = (k, t), d
        if best is None:
            return None
        k, t = best
        hk, sk, vk = _hsv(k)
        ht, st, vt = _hsv(t)
        ns = min(1.0, s * (st / sk if sk else 1.0))
        nv = min(1.0, v * (vt / vk if vk else 1.0))
        r, g, b = colorsys.hsv_to_rgb(ht, ns, nv)
        return _key(round(r * 255), round(g * 255), round(b * 255))


def is_team_red(key: int) -> bool:
    h, s, v = _hsv(key)
    return (h <= 0.04 or h >= 0.94) and s >= 0.35 and v >= 0.15


def red_to_blue(sheet: Sheet, table: FactionTable, head_mask: Optional[bytearray] = None) -> Tuple[Sheet, bytearray]:
    """For a sheet drawn with RED as its team color (e.g. a red cape): the player (blue) version,
    using the game's measured blue -> red pairs backwards. Returns (blue sheet, changed mask)."""
    inverse: Dict[int, Tuple[int, int]] = {}
    for k, targets in table.maps["red"].items():
        t = table.dominant("red", k)
        if t is None or t == k or not is_team_blue(k):
            continue
        n = sum(c for tt, c in targets if tt == t)
        if t not in inverse or n > inverse[t][1]:
            inverse[t] = (k, n)
    reds = [(t, k) for t, (k, _n) in inverse.items()]
    out = sheet.copy()
    changed = bytearray(sheet.width * sheet.height)
    memo: Dict[int, int] = {}
    p = out.rgba
    for i in range(0, len(p), 4):
        if p[i + 3] == 0 or (head_mask is not None and head_mask[i // 4]):
            continue
        k = _key(p[i], p[i + 1], p[i + 2])
        if not is_team_red(k):
            continue
        if k not in memo:
            if k in inverse:
                memo[k] = inverse[k][0]
            else:  # closest game red, same hue change and saturation / brightness ratios
                h, s_, v = _hsv(k)
                best, bd = None, 9.0
                for t, b in reds:
                    ht, st, vt = _hsv(t)
                    d = min(abs(h - ht), 1 - abs(h - ht)) * 4 + abs(s_ - st) + abs(v - vt) * 1.5
                    if d < bd:
                        best, bd = (t, b), d
                if best is None:
                    memo[k] = k
                else:
                    t, b = best
                    ht, st, vt = _hsv(t)
                    hb, sb, vb = _hsv(b)
                    r, g, bb = colorsys.hsv_to_rgb(hb, min(1.0, s_ * (sb / st if st else 1)), min(1.0, v * (vb / vt if vt else 1)))
                    memo[k] = _key(round(r * 255), round(g * 255), round(bb * 255))
        nk = memo[k]
        if nk != k:
            p[i], p[i + 1], p[i + 2] = _rgb(nk)
            changed[i // 4] = 1
    return out, changed


@dataclass
class Reference:
    """A game sprite in all three colors (the body the custom sprite is built on)."""

    name: str
    sheets: Dict[str, Sheet]  # "青"/"赤"/"緑" -> sheet
    template: bytes  # decompressed CTPK of the blue file (header, texture name, format)
    templates: Dict[str, bytes] = field(default_factory=dict)  # per color (own texture name)

    def local_map(self, color: str) -> Dict[int, int]:
        """Blue color -> this sprite's own red/green color (dominant, at least 60 %)."""
        cache = getattr(self, "_local", None)
        if cache is None:
            cache = self._local = {}
        if color in cache:
            return cache[color]
        counts: Dict[int, Dict[int, int]] = {}
        b, o = self.sheets["青"].rgba, self.sheets[color].rgba
        for i in range(0, len(b), 4):
            if b[i + 3] == 0 or o[i + 3] == 0:
                continue
            k = _key(b[i], b[i + 1], b[i + 2])
            t = _key(o[i], o[i + 1], o[i + 2])
            d = counts.setdefault(k, {})
            d[t] = d.get(t, 0) + 1
        m = {}
        for k, d in counts.items():
            t, n = max(d.items(), key=lambda kv: kv[1])
            if n / sum(d.values()) >= 0.6:
                m[k] = t
        cache[color] = m
        return m


HEAD_KEEP = "keep"  # head pixels never change (custom heads: hair / skin / eyes kept)
HEAD_TEAM = "team"  # blue-hued team colors in the head change like the body's (helmets, hats)
HEAD_MODES = (HEAD_KEEP, HEAD_TEAM)


def convert(blue: Sheet, head_mask: Optional[bytearray], color: str, table: FactionTable,
            ref: Optional[Reference] = None, stats: Optional[dict] = None,
            head_ref: Optional[Reference] = None, head_dx: int = 0, head_dy: int = 0,
            head_mode: str = HEAD_KEEP, head_src: Optional[list] = None) -> Sheet:
    """Red (赤) or green (緑) version of a blue sheet. Size, frames, alignment and transparency
    stay exactly the same; only RGB changes.

    Head pixels: when the head comes from a game sprite (head_ref, in all three colors), each
    head pixel takes that sprite's own red / green pixel (so a hat the game recolors is
    recolored and blue hair the game keeps is kept). Otherwise head_mode decides: keep (default)
    or convert team colors like the body."""
    if color == "青":
        return blue.copy()
    name = {"赤": "red", "緑": "green"}[color]
    out = blue.copy()
    p = out.rgba
    rb = ro = None
    if ref is not None and (ref.sheets["青"].width, ref.sheets["青"].height) == (blue.width, blue.height):
        rb, ro = ref.sheets["青"].rgba, ref.sheets[color].rgba
    local = ref.local_map(color) if ref is not None else {}
    memo: Dict[int, Tuple[int, str]] = {}
    st = stats if stats is not None else {}
    hw = hb = ho = None
    if head_ref is not None:
        hw = head_ref.sheets["青"].width
        hh = head_ref.sheets["青"].height
        hb, ho = head_ref.sheets["青"].rgba, head_ref.sheets[color].rgba
    w = blue.width
    for i in range(0, len(p), 4):
        if p[i + 3] == 0:
            continue
        k = _key(p[i], p[i + 1], p[i + 2])
        if head_mask is not None and head_mask[i // 4]:
            if hb is not None:
                if head_src is not None:
                    q = head_src[i // 4]
                    px, py = (q % hw, q // hw) if q >= 0 else (-1, -1)
                else:
                    px, py = (i // 4) % w - head_dx, (i // 4) // w - head_dy
                if 0 <= px < hw and 0 <= py < hh:
                    j = (py * hw + px) * 4
                    if hb[j + 3] and _key(hb[j], hb[j + 1], hb[j + 2]) == k:
                        p[i : i + 3] = ho[j : j + 3]
                        st["head (game colors)"] = st.get("head (game colors)", 0) + 1
                        continue
            if head_mode != HEAD_TEAM or not is_team_blue(k):
                st["head kept"] = st.get("head kept", 0) + 1
                continue
            t = table.dominant(name, k)
            if t is None:
                t = table.closest_rule(name, k)
            if t is None:
                continue
            p[i], p[i + 1], p[i + 2] = _rgb(t)
            st["head team color"] = st.get("head team color", 0) + 1
            continue
        if rb is not None and rb[i + 3] and _key(rb[i], rb[i + 1], rb[i + 2]) == k:
            p[i : i + 3] = ro[i : i + 3]
            st["reference pixel"] = st.get("reference pixel", 0) + 1
            continue
        if k not in memo:
            if k in local:
                memo[k] = (local[k], "reference color")
            else:
                t = table.dominant(name, k)
                if t is not None:
                    memo[k] = (t, "game color")
                elif is_team_blue(k):
                    t = table.closest_rule(name, k)
                    memo[k] = (t if t is not None else k, "closest game color")
                else:
                    memo[k] = (k, "kept")
        t, how = memo[k]
        st[how] = st.get(how, 0) + 1
        p[i], p[i + 1], p[i + 2] = _rgb(t)
    return out


# ----------------------------------------------------------------------------- project


@dataclass
class WorkshopProject:
    """Everything needed to rebuild a sprite (saved as .pusprite, JSON).

    mode "sheet": a finished sheet (PNG / .ctpk.lz) is used; its head can still be moved per frame
    (the head area comes from the class body it is drawn on, found by shape or picked).
    mode "build": a character's head (from one of their game sprites) on a class body."""

    name: str = ""
    mode: str = "sheet"  # "sheet" or "build"
    # mode "sheet"
    sheet: str = ""
    sheet_sha256: str = ""
    sheet_class: str = ""  # class key "<stem>|<男/女>" the sheet is drawn on; "" = find by shape; "-" = none
    opacity: bool = True  # turn plain opaque pixels into the game's see-through levels
    fill_alpha: int = 136  # 0-255 for normal pixels (the game uses 136 = 53 %, outlines half of it)
    # mode "build"
    head_char: str = ""  # character code in sprite names, e.g. クロム
    head_class: str = ""  # class key the head is taken from
    body_class: str = ""  # class key of the body
    # both
    head_frames: Dict[str, List[int]] = field(default_factory=dict)  # "col,row" -> [dx, dy]
    # clean-up eraser: sheet pixels [x, y] cleared from the body (all three colors). Heads are put on
    # afterwards, so erasing never removes a head pixel - only leftovers of the old head / body.
    erased: List[List[int]] = field(default_factory=list)
    team_color: str = "blue"  # the team color the sheet was drawn with: "blue" (game) or "red"
    head_mode: str = HEAD_KEEP
    reference: str = ""  # game sprite used for team colors and the BMap animation ("" = automatic)
    register: bool = True
    assign: List[dict] = field(default_factory=list)  # [{"pid": ..., "jid": ...}]

    def to_json(self, base_dir: Optional[str] = None) -> str:
        d = dict(self.__dict__)
        d["version"] = PROJECT_VERSION
        if base_dir and d["sheet"] and os.path.isabs(d["sheet"]):
            try:
                d["sheet"] = os.path.relpath(d["sheet"], base_dir).replace("\\", "/")
            except ValueError:
                pass  # other drive: keep absolute
        return json.dumps(d, ensure_ascii=False, indent=2)

    @classmethod
    def from_json(cls, text: str, base_dir: Optional[str] = None) -> "WorkshopProject":
        d = json.loads(text)
        d.pop("version", None)
        if "sheet" not in d and d.get("body_kind") == "file":  # v1.12 project
            d["sheet"], d["sheet_sha256"] = d.get("body", ""), d.get("body_sha256", "")
        p = cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})
        if base_dir and p.sheet and not os.path.isabs(p.sheet):
            p.sheet = os.path.normpath(os.path.join(base_dir, p.sheet))
        return p

    def save(self, path: str):
        with open(path, "w", encoding="utf-8") as f:
            f.write(self.to_json(os.path.dirname(os.path.abspath(path))))

    @classmethod
    def open(cls, path: str) -> "WorkshopProject":
        with open(path, "r", encoding="utf-8") as f:
            return cls.from_json(f.read(), os.path.dirname(os.path.abspath(path)))


def erase_pixels(sheet: Sheet, pixels) -> Sheet:
    """A copy of the sheet with the given [x, y] pixels made fully transparent."""
    out = sheet.copy()
    w, h = out.width, out.height
    for xy in pixels:
        x, y = int(xy[0]), int(xy[1])
        if 0 <= x < w and 0 <= y < h:
            i = (y * w + x) * 4
            out.rgba[i : i + 4] = b"\0\0\0\0"
    return out


def brush_pixels(x: int, y: int, size: int, cell: Tuple[int, int], sheet_wh: Tuple[int, int]) -> List[Tuple[int, int]]:
    """Pixels a square eraser of the given size covers at (x, y), kept inside that frame."""
    cw, ch = cell
    c0, r0 = (x // cw) * cw, (y // ch) * ch
    lo = -(size // 2)
    out = []
    for dy in range(lo, lo + size):
        for dx in range(lo, lo + size):
            px, py = x + dx, y + dy
            if c0 <= px < c0 + cw and r0 <= py < r0 + ch and px < sheet_wh[0] and py < sheet_wh[1]:
                out.append((px, py))
    return out


def valid_sprite_name(name: str) -> Optional[str]:
    """None when fine, else the reason."""
    if not name:
        return "Give the sprite a name."
    if any(c in name for c in '\\/:*?"<>|'):
        return 'The name cannot contain \\ / : * ? " < > |'
    if name[-1] in "青赤緑":
        return "Leave the color out of the name (青/赤/緑 are added for you)."
    if len(name.encode("utf-8")) > 40:
        return "The name is too long."
    return None


@dataclass
class Prepared:
    """A sprite split into body and head, ready to compose with per-frame head moves."""

    bodies: Dict[str, Sheet]  # color -> body without head ("青" always; "赤"/"緑" in build mode)
    heads: Dict[str, dict]  # color -> {(col, row): {(x, y): rgba}}
    cell: Tuple[int, int]
    class_key: Optional[str]  # body class (None: the head cannot be moved)
    reference: str  # game sprite for colors / animation
    note: str = ""


class Workshop:
    """Builds sprites against the open project (gd = Paragon's GameData)."""

    def __init__(self, gd, table: Optional[FactionTable] = None, parts=None):
        self.gd = gd
        self.table = table or FactionTable.load()
        self.pending: Dict[str, bytes] = {}  # path -> CTPK (decompressed), written on save
        self._refs: Dict[str, Reference] = {}
        self._sheets: Dict[str, Sheet] = {}
        self._detected: Dict[str, Optional[str]] = {}
        from paragon.core.services import fe13_sprite_parts as sp

        self.sp = sp
        self.lib = parts if parts is not None else sp.library()
        self.names = sp.Names(gd, self.lib)

    # --- game sprites
    def _read(self, path: str) -> Optional[bytes]:
        if path in self.pending:
            return _decompress(self.pending[path])
        try:
            if not self.gd.file_exists(path, False):
                return None
            return _decompress(bytes(self.gd.read_file(path)))
        except Exception:
            return None

    def game_sheet(self, name: str, color: str = "青") -> Optional[Sheet]:
        key = name + color
        if key not in self._sheets:
            data = self._read(f"{UNIT_DIR}/{name}{color}.ctpk.lz")
            self._sheets[key] = sheet_from_ctpk(data) if data else None
        s = self._sheets[key]
        return s.copy() if s else None

    def game_sprite_names(self) -> List[str]:
        """Names of sprites in the project / game with all three colors."""
        try:
            files = self.gd.list_files(UNIT_DIR, "*.ctpk.lz", False)
        except Exception:
            files = []
        have = {}
        for f in files or []:
            base = os.path.basename(str(f))[: -len(".ctpk.lz")]
            if base and base[-1] in "青赤緑":
                have.setdefault(base[:-1], set()).add(base[-1])
        return sorted(n for n, cs in have.items() if cs >= {"青", "赤", "緑"})

    def reference(self, name: str) -> Optional[Reference]:
        if name in self._refs:
            return self._refs[name]
        sheets, templates = {}, {}
        for c, _e, _l in COLORS:
            data = self._read(f"{UNIT_DIR}/{name}{c}.ctpk.lz")
            if data is None:
                return None
            sheets[c] = sheet_from_ctpk(data)
            templates[c] = data
        ref = Reference(name, sheets, templates["青"], templates)
        self._refs[name] = ref
        return ref

    def auto_reference(self, body: Sheet, candidates: Optional[List[str]] = None, step: int = 5) -> Optional[str]:
        """The game sprite whose shape (visible pixels) matches the body best."""
        cands = candidates if candidates is not None else self.game_sprite_names()
        enc = encode_rgba4(body)
        mine = enc[0::2]
        idx = range(0, len(mine), step)
        mask = [mine[i] & 15 for i in idx]
        best, score = None, -1.0
        for n in cands:
            data = self._read(f"{UNIT_DIR}/{n}青.ctpk.lz")
            if data is None:
                continue
            try:
                off, length, fmt, w, h = ctpk_info(data)
            except ValueError:
                continue
            if (w, h) != (body.width, body.height) or fmt != RGBA4:
                continue
            other = data[off : off + length : 2]
            inter = union = 0
            for m, i in zip(mask, idx):
                o = other[i] & 15
                if m or o:
                    union += 1
                    if m and o:
                        inter += 1
            iou = inter / union if union else 0.0
            if iou > score:
                best, score = n, iou
        return best

    # --- choices for the window (English labels)
    def body_choices(self) -> List[Tuple[str, str]]:
        """[(label, class key)] classes a head can be put on."""
        if not self.lib:
            return []
        out = [(self.names.job(self.lib.parts(k).stem, self.lib.parts(k).sex), k) for k in self.lib.class_keys()]
        return sorted(out)

    def head_choices(self) -> List[Tuple[str, str]]:
        """[(label, character code)]."""
        if not self.lib:
            return []
        return sorted((self.names.character(c), c) for c in self.lib.characters())

    def head_source_choices(self, char: str) -> List[Tuple[str, str]]:
        if not self.lib:
            return []
        return [(self.names.job(self.lib.parts(k).stem, self.lib.parts(k).sex), k) for k, _s in self.lib.head_sources(char)]

    def best_head_source(self, char: str, body_key: str) -> Optional[str]:
        """The class the character's head is taken from: same frame size as the body (fliers /
        others) and the closest head position, then the most character versions."""
        if not self.lib:
            return None
        srcs = [k for k, _s in self.lib.head_sources(char)]
        if not srcs:
            return None
        T = self.lib.parts(body_key)

        def score(k):
            S = self.lib.parts(k)
            same = S.cell == T.cell
            common = [c for c in T.anchors if c in S.anchors]
            dist = 0.0
            for c in common:
                (sx, sy), (tx, ty) = S.anchors[c], T.anchors[c]
                dist += abs((ty - c[1] * T.cell[1]) - (sy - c[1] * S.cell[1]))
            dist = dist / len(common) if common else 99
            return (0 if same else 1, dist, -len(S.variants))

        return min(srcs, key=score)

    def class_label(self, key: Optional[str]) -> str:
        if not key or not self.lib or not self.lib.has(key):
            return "-"
        P = self.lib.parts(key)
        return self.names.job(P.stem, P.sex)

    def detect_class(self, sheet: Sheet) -> Optional[str]:
        """Class key of the game body the sheet looks drawn on (by shape)."""
        if not self.lib:
            return None
        cands = sorted({self.lib.parts(k).generic for k in self.lib.class_keys()})
        best = self.auto_reference(sheet, cands, step=3)
        return self.lib.key_for_sprite(best) if best else None

    def outline_match(self, sheet: Sheet, sprite: str) -> float:
        """Share of visible pixels the sheet and a game sprite have in common (0..1)."""
        g = self.game_sheet(sprite)
        if g is None or (g.width, g.height) != (sheet.width, sheet.height):
            return 0.0
        a, b = sheet.rgba[3::4], g.rgba[3::4]
        both = sum(1 for x, y in zip(a, b) if x and y)
        either = sum(1 for x, y in zip(a, b) if x or y) or 1
        return both / either

    # --- building
    def source_sheet(self, p: WorkshopProject) -> Sheet:
        s = load_sheet_file(p.sheet)
        if p.opacity and self.sp.is_full_opacity(s):
            s = self.sp.game_opacity(s, p.fill_alpha)
        return s

    def prepare(self, p: WorkshopProject) -> Prepared:
        sp = self.sp
        if p.mode == "build":
            if not self.lib:
                raise ValueError("The head / body data (Data/FE13/PU_SpriteParts.json) is missing.")
            if not (p.head_char and p.head_class and p.body_class):
                raise ValueError("Pick a head and a body.")
            S, T = self.lib.parts(p.head_class), self.lib.parts(p.body_class)
            src = S.stem + p.head_char
            bodies, heads = {}, {}
            blue_cells = None
            for c, _e, _l in COLORS:
                X, G = self.game_sheet(src, c), self.game_sheet(T.generic, c)
                if X is None or G is None:
                    raise ValueError(f"The game sprite {src if X is None else T.generic}{c} was not found.")
                if c == "青":
                    _b, cells = sp.split_sheet(X, S, True)
                    blue_cells = cells
                    bodies[c] = sp.headless_body(G, T)
                else:
                    # same head pixels, this team's colors; body: the generic's own pixels, and
                    # under its head the blue fill in this team's colors
                    w = X.width
                    cells = {
                        cell: {(x, y): tuple(X.rgba[((cell[1] * S.cell[1] + y) * w + cell[0] * S.cell[0] + x) * 4:((cell[1] * S.cell[1] + y) * w + cell[0] * S.cell[0] + x) * 4 + 4])
                               for (x, y) in px}
                        for cell, px in blue_cells.items()
                    }
                    bodies[c] = self._body_in_color(G, T, c)
                heads[c] = sp.move_heads(cells, S, T)
            return Prepared(bodies, heads, T.cell, p.body_class, p.reference or T.generic)
        # a sheet
        if not p.sheet:
            raise ValueError("Drop a sprite sheet on the preview, or build one from a head and a class.")
        s = self.source_sheet(p)
        if p.sheet_class == "-":
            key = None
        elif p.sheet_class:
            key = p.sheet_class
        else:
            ck = (p.sheet_sha256 or p.sheet) + f"|{s.width}x{s.height}"
            if ck not in self._detected:
                self._detected[ck] = self.detect_class(s)
            key = self._detected[ck]
        ref = p.reference or (self.lib.parts(key).generic if key and self.lib else "") or (self.auto_reference(s) or "")
        if not key or not self.lib or not self.lib.has(key):
            return Prepared({"青": s}, {"青": {}}, self.cell_size_for(ref), None, ref,
                            "The head cannot be moved: no class body found for this sheet.")
        P = self.lib.parts(key)
        if (s.width, s.height) != tuple(P.size):
            return Prepared({"青": s}, {"青": {}}, self.cell_size_for(ref), None, ref,
                            f"The sheet is {s.width} x {s.height}; the game's are {P.size[0]} x {P.size[1]}.")
        G = self.game_sheet(P.generic)
        on_game_body = False
        if G is not None:
            same = sum(1 for i in range(0, len(s.rgba), 4) if s.rgba[i + 3] and s.rgba[i:i + 4] == G.rgba[i:i + 4])
            vis = sum(1 for v in s.rgba[3::4] if v) or 1
            on_game_body = same / vis > 0.5
        body, cells = sp.split_sheet(s, P, on_game_body)
        note = ""
        if not on_game_body:
            m = self.outline_match(s, P.generic)
            if m < 0.75:
                note = (f"This sheet is not drawn on a game body (closest: {self.class_label(key)}, "
                        f"{round(m * 100)} % alike), so the head area is a guess - turn on Highlight heads "
                        "to check it, or pick the body under Start.")
        return Prepared({"青": body}, {"青": cells}, P.cell, key, ref, note)

    def _body_in_color(self, G: Sheet, T, color: str) -> Sheet:
        """Generic body in a team color with its head cleared: where the blue generic shows its
        own head, the body under it (fill) in this color via the generic's color mapping."""
        blue = self.game_sheet(T.generic)
        ref = self.reference(T.generic)
        cmap = ref.local_map(color) if ref else {}
        out = G.copy()
        for i in T.union:
            o = i * 4
            if o + 4 > len(out.rgba):
                continue
            f = T.fill[i]
            if blue is not None and tuple(blue.rgba[o:o + 4]) == f:
                continue  # the generic shows the body here: keep this color's pixel
            if not f[3]:
                out.rgba[o:o + 4] = b"\0\0\0\0"
            else:
                k = _key(*f[:3])
                t = cmap.get(k, k)
                out.rgba[o:o + 4] = bytes(_rgb(t) + (f[3],))
        return out

    def cell_size_for(self, sprite: str) -> Tuple[int, int]:
        icon = self.find_icon(sprite) if sprite else None
        if icon is None:
            return DEFAULT_CELL, DEFAULT_CELL
        return (self.gd.int(icon, "frame_width") or DEFAULT_CELL, self.gd.int(icon, "frame_height") or DEFAULT_CELL)

    def compose_color(self, prep: Prepared, color: str, offsets, erased=None) -> Tuple[Sheet, bytearray, int]:
        body = prep.bodies.get(color) or prep.bodies["青"]
        cells = prep.heads.get(color) if color in prep.heads else prep.heads["青"]
        if erased:
            body = erase_pixels(body, erased)
        return self.sp.compose(body, cells, prep.cell, offsets)

    def build(self, p: WorkshopProject, stats: Optional[dict] = None, prep: Optional[Prepared] = None) -> Dict[str, Sheet]:
        """{"青": sheet, "赤": sheet, "緑": sheet} for the project."""
        prep = prep or self.prepare(p)
        blue, mask, _cut = self.compose_color(prep, "青", p.head_frames, p.erased)
        if "赤" in prep.bodies:  # built from game sprites: the game's own team colors
            return {"青": blue, "赤": self.compose_color(prep, "赤", p.head_frames, p.erased)[0],
                    "緑": self.compose_color(prep, "緑", p.head_frames, p.erased)[0]}
        ref = self.reference(prep.reference) if prep.reference else None
        if ref is not None and (ref.sheets["青"].width, ref.sheets["青"].height) != (blue.width, blue.height):
            ref = None
        if p.team_color == "red":
            b2, _ch = red_to_blue(blue, self.table, mask)
            return {"青": b2, "赤": blue, "緑": convert(b2, mask, "緑", self.table, ref, stats, None, 0, 0, p.head_mode)}
        return {"青": blue, "赤": convert(blue, mask, "赤", self.table, ref, stats, None, 0, 0, p.head_mode),
                "緑": convert(blue, mask, "緑", self.table, ref, stats, None, 0, 0, p.head_mode)}

    def template_for(self, p: WorkshopProject, sheet: Sheet, color: str = "青", reference: str = "") -> bytes:
        ref = self.reference(reference) if reference else None
        if ref is not None:
            return ref.templates.get(color) or ref.template
        return new_ctpk(sheet.width, sheet.height, b"\0" * (sheet.width * sheet.height * 2))

    # --- BMap icon registration
    def icon_table(self):
        return self.gd.table("bmap_icons")

    def find_icon(self, name: str):
        t = self.icon_table()
        if not t:
            return None
        for r in self.gd.items(t[0], t[1]):
            if self.gd.string(r, "name") == name:
                return r
        return None

    def register(self, p: WorkshopProject, reference: str) -> Tuple[object, bool]:
        """(icon rid, created). A new entry copies the reference's entry (frame size, all
        animations), so the sprite animates exactly like its body."""
        existing = self.find_icon(p.name)
        if existing is not None:
            return existing, False
        src = self.find_icon(reference) if reference else None
        if src is None:
            raise ValueError("No game sprite to copy the animation from (Advanced: Color reference).")
        t = self.icon_table()
        rid = self.gd.list_add(t[0], t[1])
        self.gd.copy(src, rid, [])
        self.gd.set_string(rid, "bmi", f"BMI_{p.name}")
        self.gd.set_string(rid, "name", p.name)
        self.gd.set_store_dirty("gamedata", True)
        return rid, True

    def assign(self, p: WorkshopProject, icon_rid) -> List[str]:
        """Point the characters' sprite list entries (per class) at the sprite."""
        done = []
        chars = self.gd.table("characters")
        jobs = self.gd.table("jobs")
        if not chars or not jobs:
            return done
        job_rows = {self.gd.key(j): i for i, j in enumerate(self.gd.items(jobs[0], jobs[1]))}
        people = {self.gd.key(c): c for c in self.gd.items(chars[0], chars[1])}
        for a in p.assign:
            c, row = people.get(a.get("pid")), job_rows.get(a.get("jid"))
            if c is None or row is None:
                done.append(f"skipped {a.get('pid')} / {a.get('jid')} (not found)")
                continue
            sd = self.gd.rid(c, "sprite_data")
            entries = self.gd.items(sd, "entries") if sd else []
            if row >= len(entries):
                done.append(f"skipped {a.get('pid')} / {a.get('jid')} (sprite list too short)")
                continue
            self.gd.set_rid(entries[row], "bmap_icon", icon_rid)
            done.append(f"{a.get('pid')} as {a.get('jid')}")
        if done:
            self.gd.set_store_dirty("characters", True)
        return done

    # --- export
    @staticmethod
    def overwrites_source(p: WorkshopProject, out_root: Optional[str]) -> Optional[str]:
        """The source file Export would overwrite (the sheet = one of the output files)."""
        if not out_root or p.mode != "sheet" or not p.sheet:
            return None
        outs = {
            os.path.normcase(os.path.abspath(os.path.join(out_root, *UNIT_DIR.split("/"), f"{p.name}{c}.ctpk.lz")))
            for c, _e, _l in COLORS
        }
        return p.sheet if os.path.normcase(os.path.abspath(p.sheet)) in outs else None

    def export(self, p: WorkshopProject, out_root: Optional[str] = None) -> List[str]:
        """Build the three colors, queue the files (written on save), register the icon and
        assign it. Returns a report."""
        err = valid_sprite_name(p.name)
        if err:
            raise ValueError(err)
        src = self.overwrites_source(p, out_root)
        if src:
            raise ValueError(
                f"Saving would overwrite the source sheet {os.path.basename(src)}. Give the sprite "
                "another name, or keep the source outside the mod folder."
            )
        prep = self.prepare(p)
        sheets = self.build(p, prep=prep)
        lines = []
        for c, _e, label in COLORS:
            path = f"{UNIT_DIR}/{p.name}{c}.ctpk.lz"
            self.pending[path] = ctpk_with_sheet(self.template_for(p, sheets[c], c, prep.reference), sheets[c])
            lines.append(f"{path} ({label})")
        if p.register:
            rid, created = self.register(p, prep.reference)
            lines.append(("Added" if created else "Uses the existing") + f" BMap icon entry BMI_{p.name}.")
            lines += ["Assigned: " + x for x in self.assign(p, rid)]
        return lines

    def has_pending(self) -> bool:
        return bool(self.pending)

    def flush(self) -> List[str]:
        """Write queued sprite files into the project output (called on save)."""
        written = []
        for path, data in list(self.pending.items()):
            self.gd.write_file(path, data)  # Paragon compresses .lz paths itself
            written.append(path)
            del self.pending[path]
        return written

    # --- validation
    def validate(self, p: WorkshopProject, roots: Optional[List[str]] = None) -> List[Tuple[str, str]]:
        """[(severity, message)] - every color generated, named exactly, registered, included."""
        out = []
        err = valid_sprite_name(p.name)
        if err:
            return [("error", err)]
        try:
            prep = self.prepare(p)
            sheets = self.build(p, prep=prep)
            _b, _m, cut = self.compose_color(prep, "青", p.head_frames, p.erased)
        except Exception as e:
            return [("error", f"Cannot build the sprite: {e}")]
        blue = sheets["青"]
        if cut:
            out.append(("warning", f"{cut} head pixels are moved past the edge of their frame and cut off."))
        for c, _e, label in COLORS:
            s = sheets[c]
            if (s.width, s.height) != (blue.width, blue.height):
                out.append(("error", f"{label} sheet has a different size."))
        if p.mode == "sheet" and p.sheet_sha256 and os.path.isfile(p.sheet) and file_digest(p.sheet) != p.sheet_sha256:
            out.append(("warning", "The sheet file changed since the project was saved."))
        for c, _e, label in COLORS:
            path = f"{UNIT_DIR}/{p.name}{c}.ctpk.lz"
            if path in self.pending:
                continue
            in_project = False
            if roots:
                from paragon.core.services import pu_file_case

                pu_file_case.clear_cache()
                status, _r, actual = pu_file_case.resolve(roots[:1], path)
                if status == "case":
                    out.append(("error", f"{label}: the file is named {actual} (letter case differs from {path})."))
                in_project = status == "exact"
            if not in_project:
                out.append(("error", f"{label}: {path} is not saved yet (Save sprite, then save the project)."))
        icon = self.find_icon(p.name)
        if p.register and icon is None:
            out.append(("error", f"No BMap icon entry named {p.name} (Save sprite adds it)."))
        for a in p.assign:
            out += self._check_assignment(a, icon)
        if not out:
            out.append(("ok", "All three colors are made, named exactly, registered and in the mod."))
        return out

    def _check_assignment(self, a, icon):
        chars, jobs = self.gd.table("characters"), self.gd.table("jobs")
        people = {self.gd.key(c): c for c in self.gd.items(chars[0], chars[1])} if chars else {}
        rows = {self.gd.key(j): i for i, j in enumerate(self.gd.items(jobs[0], jobs[1]))} if jobs else {}
        c, row = people.get(a.get("pid")), rows.get(a.get("jid"))
        if c is None or row is None:
            return [("warning", f"Assignment {a.get('pid')} / {a.get('jid')}: not found.")]
        sd = self.gd.rid(c, "sprite_data")
        entries = self.gd.items(sd, "entries") if sd else []
        if row >= len(entries) or icon is None or self.gd.rid(entries[row], "bmap_icon") != icon:
            return [("error", f"{a.get('pid')} as {a.get('jid')} does not use this sprite yet (Save sprite).")]
        return []

    # --- animation (preview)
    def animation(self, sprite: str, which: int = 1) -> Tuple[int, int, List[Tuple[int, int, int]]]:
        """(cell width, cell height, [(x cell, y cell, delay)]) of a sprite's BMap animation."""
        icon = self.find_icon(sprite) if sprite else None
        if icon is None:
            return DEFAULT_CELL, DEFAULT_CELL, []
        w = self.gd.int(icon, "frame_width") or DEFAULT_CELL
        h = self.gd.int(icon, "frame_height") or DEFAULT_CELL
        data = self.gd.rid(icon, "pointer")
        anim = self.gd.rid(data, f"animation_data_{which}") if data else None
        frames = []
        if anim:
            for fr in self.gd.items(anim, "frame_data") or []:
                frames.append(
                    (self.gd.int(fr, "frame_index_x") or 0, self.gd.int(fr, "frame_index_y") or 0,
                     self.gd.int(fr, "frame_delay") or 1)
                )
        return w, h, frames


def workshop_for(gs) -> Workshop:
    ws = getattr(gs, "pu_sprite_workshop", None)
    if ws is None:
        ws = Workshop(gs.data)
        gs.pu_sprite_workshop = ws
    return ws
