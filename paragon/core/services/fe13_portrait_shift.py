"""Paragon Unlimited - move FE13 (Awakening) portrait artwork inside its textures.

Awakening has no position setting for BU portraits: the game draws the whole 256x256 (BU) or
128x128 (FC) texture at a fixed place on screen. To move a character you have to move the
artwork inside every expression texture of the portrait .arc. This module does that:

* parse / rebuild the face .arc (byte-identical round trip for vanilla files),
* shift ETC1A4 textures either losslessly (multiples of 4 px: whole 4x4 blocks are moved)
  or by re-encoding (any amount; small quality loss, see encode_etc1 in the Rust core),
* keep blush / sweat overlay positions (FaceData fields) in step with the normal set.

Textures in an arc:
    "<emotion>.ctpk.lz"     normal set (shifted together)
    "反<emotion>.ctpk.lz"   reversed set: separately drawn art facing the other way
    "頬" blush, "汗" sweat  small overlays placed by FaceData coordinates (never shifted)
    "髪", "髪0"             hair color masks (32x32, never shifted)
"""

import dataclasses
import logging
import os
import struct
import zipfile
import datetime
import time
from typing import Dict, List, Optional, Tuple

from paragon import paragon as pgn

OVERLAYS = ("頬", "汗")
REVERSED_PREFIX = "反"
ETC1A4 = 13
ETC1 = 12
RGBA8 = 0


def _key(name: str) -> str:
    return name[:-8] if name.endswith(".ctpk.lz") else name


def texture_set(name: str) -> Optional[str]:
    """'normal', 'reversed' or None (overlay / hair, never shifted)."""
    k = _key(name)
    if k in OVERLAYS or k.startswith("髪"):
        return None
    return "reversed" if k.startswith(REVERSED_PREFIX) else "normal"


# ----------------------------------------------------------------------------- arc


def arc_alignment(raw: bytes) -> int:
    """Largest power-of-two alignment shared by all file offsets in the arc (4..0x80)."""
    fsize, dsize, pcount, lcount = struct.unpack_from("<4I", raw, 0)
    data = raw[0x20 : 0x20 + dsize]
    lt = 0x20 + dsize + 4 * pcount
    st = lt + 8 * lcount
    info = None
    for i in range(lcount):
        a, n = struct.unpack_from("<II", raw, lt + 8 * i)
        if raw[st + n : st + n + 5] == b"Info\0":
            info = a
        if raw[st + n : st + n + 6] == b"Count\0":
            count = struct.unpack_from("<I", data, a)[0]
    best = 0x80
    for i in range(count):
        addr = struct.unpack_from("<I", data, info + 16 * i + 12)[0]
        while best > 4 and addr % best:
            best //= 2
    return best


def parse_arc(raw: bytes) -> List[Tuple[str, int, bytes]]:
    """[(name, index, file bytes)] in file order."""
    fsize, dsize, pcount, lcount = struct.unpack_from("<4I", raw, 0)
    data = raw[0x20 : 0x20 + dsize]
    lt = 0x20 + dsize + 4 * pcount
    st = lt + 8 * lcount

    def s(off):
        e = raw.index(b"\0", st + off)
        return raw[st + off : e].decode("shift_jis")

    labels = {}
    for i in range(lcount):
        a, n = struct.unpack_from("<II", raw, lt + 8 * i)
        labels.setdefault(s(n), a)
    pad = 0x60 if struct.unpack_from("<I", data, 0)[0] == 0 else 0
    count = struct.unpack_from("<I", data, labels["Count"])[0]
    out = []
    for i in range(count):
        name_ptr, idx, size, addr = struct.unpack_from("<IIII", data, labels["Info"] + 16 * i)
        name = s(name_ptr - dsize - 4 * pcount - 8 * lcount)
        out.append((name, idx, bytes(data[addr + pad : addr + pad + size])))
    return out


def build_arc(entries: List[Tuple[str, int, bytes]], align: int = 4) -> bytes:
    """align: file data alignment (4 in face arcs, 0x20 in DLC map arcs)."""
    data = bytearray()
    addrs = []
    for _name, _idx, blob in entries:
        while len(data) % align:
            data.append(0)
        addrs.append(len(data))
        data += blob
    while len(data) % align:
        data.append(0)
    count_off = len(data)
    data += struct.pack("<I", len(entries))
    info_off = len(data)
    strings = bytearray()
    soff = {}

    def add(s):
        if s not in soff:
            soff[s] = len(strings)
            strings.extend(s.encode("shift_jis") + b"\0")
        return soff[s]

    for n in ("Data", "Count", "Info"):
        add(n)
    for name, _, _ in entries:
        add(name)
    ptrs = []
    labels = [(0, soff["Data"]), (count_off, soff["Count"]), (info_off, soff["Info"])]
    for (name, idx, blob), a in zip(entries, addrs):
        o = len(data)
        ptrs.append(o)
        labels.append((o, soff[name]))
        data += struct.pack("<IIII", 0, idx, len(blob), a)
    dsize = len(data)
    base = dsize + 4 * len(ptrs) + 8 * len(labels)
    for o, (name, _, _) in zip(ptrs, entries):
        struct.pack_into("<I", data, o, base + soff[name])
    body = (
        bytes(data)
        + b"".join(struct.pack("<I", p) for p in ptrs)
        + b"".join(struct.pack("<II", a, n) for a, n in labels)
        + bytes(strings)
    )
    return struct.pack("<4I", 0x20 + len(body), dsize, len(ptrs), len(labels)) + b"\0" * 16 + body


# ----------------------------------------------------------------------------- ctpk


@dataclasses.dataclass
class CtpkTexture:
    ctpk: bytes  # decompressed
    fmt: int
    width: int
    height: int
    pixel_offset: int
    pixel_length: int

    @staticmethod
    def parse(ctpk: bytes) -> "CtpkTexture":
        count = struct.unpack_from("<H", ctpk, 6)[0]
        if count != 1:
            raise ValueError(f"Expected 1 texture in CTPK, found {count}")
        tex_base = struct.unpack_from("<I", ctpk, 8)[0]
        _fn, tlen, tptr, fmt, w, h = struct.unpack_from("<IIIIHH", ctpk, 0x20)
        if not tlen:
            # Some community tools leave the size field empty; the pixels then fill the
            # rest of the texture section.
            tlen = struct.unpack_from("<I", ctpk, 0x0C)[0] or (len(ctpk) - tex_base - tptr)
        return CtpkTexture(ctpk, fmt, w, h, tex_base + tptr, tlen)

    def pixels(self) -> bytes:
        return self.ctpk[self.pixel_offset : self.pixel_offset + self.pixel_length]

    def with_pixels(self, pixels: bytes) -> bytes:
        if len(pixels) != self.pixel_length:
            raise ValueError("Encoded size does not match the texture.")
        return self.ctpk[: self.pixel_offset] + pixels + self.ctpk[self.pixel_offset + self.pixel_length :]

    def rgba(self) -> bytes:
        return bytes(pgn.read_ctpk(self.ctpk)[0].pixel_data)


def _morton(x: int, y: int) -> int:
    m = 0
    for k in range(3):
        m |= ((x >> k) & 1) << (2 * k)
        m |= ((y >> k) & 1) << (2 * k + 1)
    return m


_MORTON = [_morton(i % 8, i // 8) for i in range(64)]


def encode_rgba8(rgba: bytes, w: int, h: int) -> bytes:
    """3DS RGBA8 (CTPK format 0): 8x8 tiles, Morton order inside a tile, bytes A,B,G,R."""
    out = bytearray(w * h * 4)
    tiles_per_row = w // 8
    for y in range(h):
        ty, iy = divmod(y, 8)
        for x in range(w):
            tx, ix = divmod(x, 8)
            o = ((ty * tiles_per_row + tx) * 64 + _MORTON[iy * 8 + ix]) * 4
            i = (y * w + x) * 4
            r, g, b, a = rgba[i : i + 4]
            out[o : o + 4] = bytes((a, b, g, r))
    return bytes(out)


SUPPORTED_FORMATS = (ETC1A4, ETC1, RGBA8)


def encode_pixels(rgba: bytes, w: int, h: int, fmt: int) -> bytes:
    if fmt in (ETC1A4, ETC1):
        return bytes(pgn.encode_etc1(rgba, w, h, fmt == ETC1A4))
    if fmt == RGBA8:
        return encode_rgba8(rgba, w, h)
    raise ValueError(f"Unsupported texture format {fmt} (ETC1, ETC1A4 and RGBA8 are supported).")


def fit_image(img, w: int, h: int, align_bottom: bool = True) -> bytes:
    """PIL image -> RGBA bytes of exactly w x h. Larger/smaller images are scaled to fit
    (aspect kept), centered horizontally and placed at the bottom (portraits are busts)."""
    from PIL import Image

    img = img.convert("RGBA")
    if img.size == (w, h):
        return img.tobytes()
    scale = min(w / img.width, h / img.height)
    nw, nh = max(1, round(img.width * scale)), max(1, round(img.height * scale))
    img = img.resize((nw, nh), Image.LANCZOS)
    canvas = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    canvas.paste(img, ((w - nw) // 2, (h - nh) if align_bottom else (h - nh) // 2))
    return canvas.tobytes()


def ctpk_from_template(template_ctpk: bytes, rgba: bytes) -> bytes:
    """A copy of template_ctpk (same size and format) holding the given RGBA pixels."""
    t = CtpkTexture.parse(template_ctpk)
    return t.with_pixels(encode_pixels(rgba, t.width, t.height, t.fmt))


# Header of a vanilla single-texture CTPK ("Tex"), as found in the game's face arcs.
_CTPK_HEADER = bytes.fromhex(
    "4354504b010001008000000000400000480000005000000000000000000000004400000000400000"
    "000000000d000000800080000102000010000000" "9d30434e004000005465780092 39a0d2"
    "000000000d010100".replace(" ", "")
)


def make_ctpk(w: int, h: int, fmt: int, pixels: bytes) -> bytes:
    """A new single-texture CTPK laid out like the game's own files."""
    hdr = bytearray(_CTPK_HEADER) + b"\0" * (0x80 - len(_CTPK_HEADER))
    section = (len(pixels) + 0x7F) & ~0x7F
    struct.pack_into("<I", hdr, 0x0C, section)
    struct.pack_into("<I", hdr, 0x24, len(pixels))
    struct.pack_into("<I", hdr, 0x2C, fmt)
    struct.pack_into("<HH", hdr, 0x30, w, h)
    struct.pack_into("<I", hdr, 0x40, len(pixels))
    hdr[0x50] = fmt
    return bytes(hdr) + pixels + b"\0" * (section - len(pixels))


def new_ctpk(w: int, h: int, rgba: Optional[bytes] = None, fmt: int = ETC1A4) -> bytes:
    rgba = rgba if rgba is not None else b"\0" * (w * h * 4)
    return make_ctpk(w, h, fmt, encode_pixels(rgba, w, h, fmt))


def blank_ctpk(template_ctpk: bytes) -> bytes:
    t = CtpkTexture.parse(template_ctpk)
    return ctpk_from_template(template_ctpk, b"\0" * (t.width * t.height * 4))


def shift_rgba(rgba: bytes, w: int, h: int, dx: int, dy: int) -> bytes:
    out = bytearray(w * h * 4)
    row = w * 4
    for y in range(h):
        sy = y - dy
        if not 0 <= sy < h:
            continue
        x0 = max(0, dx)
        x1 = min(w, w + dx)
        if x1 <= x0:
            continue
        sx0 = x0 - dx
        out[y * row + x0 * 4 : y * row + x1 * 4] = rgba[sy * row + sx0 * 4 : sy * row + (sx0 + x1 - x0) * 4]
    return bytes(out)


def shift_blocks_lossless(pixels: bytes, w: int, h: int, dx: int, dy: int, block_size: int) -> bytes:
    """Move whole 4x4 ETC blocks (dx, dy multiples of 4). Uncovered blocks become transparent."""
    assert dx % 4 == 0 and dy % 4 == 0
    bw, bh = w // 4, h // 4
    tiles_per_row = w // 8

    def off(bx, by):
        tile = (by // 2) * tiles_per_row + (bx // 2)
        sub = (by % 2) * 2 + (bx % 2)
        return (tile * 4 + sub) * block_size

    empty = b"\0" * block_size
    out = bytearray(len(pixels))
    sbx, sby = dx // 4, dy // 4
    for by in range(bh):
        for bx in range(bw):
            ox, oy = bx - sbx, by - sby
            o = off(bx, by)
            if 0 <= ox < bw and 0 <= oy < bh:
                s = off(ox, oy)
                out[o : o + block_size] = pixels[s : s + block_size]
            else:
                out[o : o + block_size] = empty
    return bytes(out)


def shift_ctpk(ctpk: bytes, dx: int, dy: int, lossless_if_possible: bool = True) -> Tuple[bytes, bool]:
    """Returns (new ctpk, lossless?)."""
    t = CtpkTexture.parse(ctpk)
    if t.fmt not in SUPPORTED_FORMATS:
        raise ValueError(f"Unsupported texture format {t.fmt} (ETC1, ETC1A4 and RGBA8 are supported).")
    if dx == 0 and dy == 0:
        return ctpk, True
    if t.fmt == RGBA8:  # uncompressed: always exact
        rgba = shift_rgba(t.rgba(), t.width, t.height, dx, dy)
        return t.with_pixels(encode_rgba8(rgba, t.width, t.height)), True
    bsize = 16 if t.fmt == ETC1A4 else 8
    if lossless_if_possible and dx % 4 == 0 and dy % 4 == 0:
        return t.with_pixels(shift_blocks_lossless(t.pixels(), t.width, t.height, dx, dy, bsize)), True
    rgba = shift_rgba(t.rgba(), t.width, t.height, dx, dy)
    enc = bytes(pgn.encode_etc1(rgba, t.width, t.height, t.fmt == ETC1A4))
    return t.with_pixels(enc), False


def shift_entries(entries, shifts: Dict[str, Tuple[int, int]], lossless_if_possible=True):
    out = []
    report = []
    for name, idx, blob in entries:
        which = texture_set(name)
        dx, dy = shifts.get(which, (0, 0)) if which else (0, 0)
        if (dx, dy) != (0, 0):
            ctpk = bytes(pgn.decompress_lz13(blob))
            new, lossless = shift_ctpk(ctpk, dx, dy, lossless_if_possible)
            blob = bytes(pgn.compress_lz13(new))
            report.append(f"{name}: moved {dx:+d},{dy:+d} ({'lossless' if lossless else 're-encoded'})")
        out.append((name, idx, blob))
    return out, report


def shift_arc(raw: bytes, shifts: Dict[str, Tuple[int, int]], lossless_if_possible=True):
    """shifts: {'normal': (dx,dy), 'reversed': (dx,dy)}. Returns (new arc bytes, report lines)."""
    out, report = shift_entries(parse_arc(raw), shifts, lossless_if_possible)
    return build_arc(out), report


def sort_entries(entries):
    """Face arcs list their files sorted by name (code point order), index = position."""
    ordered = sorted(entries, key=lambda e: e[0])
    return [(name, i, blob) for i, (name, _idx, blob) in enumerate(ordered)]


# Basic expressions every Awakening portrait has (plus the blush/sweat overlays and hair masks).
BASIC_EXPRESSIONS = ["通常", "笑", "怒", "苦", "キメ"]
EXTRA_PARTS = ["頬", "汗", "髪", "髪0"]
ENTRY_SUFFIX = ".ctpk.lz"


# ----------------------------------------------------------------------------- pending edits


class PortraitEdits:
    """Edits queued in the editor and written to the output folder when the project is saved:
    artwork shifts, imported images, added/removed expressions and new portrait files."""

    def __init__(self, gd):
        self.gd = gd
        self.pending: Dict[str, Dict[str, Tuple[int, int]]] = {}  # arc path -> set -> (dx, dy)
        # arc path -> entry key ("通常") -> LZ13-compressed CTPK, or None = remove
        self.images: Dict[str, Dict[str, Optional[bytes]]] = {}
        self.new_arcs = set()  # arc paths that do not exist in the game files yet
        self.lossless = True
        self.listeners = []  # called after flush()

    # shifts
    def get(self, arc_path: str, which: str) -> Tuple[int, int]:
        return self.pending.get(arc_path, {}).get(which, (0, 0))

    def set(self, arc_path: str, which: str, dx: int, dy: int):
        self.pending.setdefault(arc_path, {})[which] = (dx, dy)
        if all(v == (0, 0) for v in self.pending[arc_path].values()):
            del self.pending[arc_path]

    # images
    def set_image(self, arc_path: str, key: str, ctpk: bytes):
        """ctpk: decompressed CTPK bytes."""
        self.images.setdefault(arc_path, {})[key] = bytes(pgn.compress_lz13(ctpk))

    def remove_image(self, arc_path: str, key: str):
        if arc_path in self.new_arcs:
            self.images.get(arc_path, {}).pop(key, None)
        else:
            self.images.setdefault(arc_path, {})[key] = None

    def create_arc(self, arc_path: str, parts: Dict[str, bytes]):
        """New portrait file. parts: key -> decompressed CTPK."""
        self.new_arcs.add(arc_path)
        self.images[arc_path] = {}
        for k, v in parts.items():
            self.set_image(arc_path, k, v)

    def has_image_edits(self, arc_path: str) -> bool:
        return arc_path in self.new_arcs or bool(self.images.get(arc_path))

    def overlay(self, arc_path: str, arc: Optional[Dict[str, bytes]]) -> Dict[str, bytes]:
        """The arc contents (name -> file bytes) with the pending image edits applied."""
        out = {} if arc_path in self.new_arcs or arc is None else dict(arc)
        for key, blob in self.images.get(arc_path, {}).items():
            if blob is None:
                out.pop(key + ENTRY_SUFFIX, None)
            else:
                out[key + ENTRY_SUFFIX] = blob
        return out

    def keys(self, arc_path: str) -> List[str]:
        """Entry keys of the arc as it will be saved."""
        return [n[: -len(ENTRY_SUFFIX)] if n.endswith(ENTRY_SUFFIX) else n for n, _, _ in self.entries(arc_path)]

    def entries(self, arc_path: str):
        if arc_path in self.new_arcs:
            base = []
        else:
            base = parse_arc(bytes(self.gd.read_file(arc_path)))
        edits = self.images.get(arc_path)
        if not edits:
            return base
        by_name = {n: b for n, _i, b in base}
        for key, blob in edits.items():
            if blob is None:
                by_name.pop(key + ENTRY_SUFFIX, None)
            else:
                by_name[key + ENTRY_SUFFIX] = blob
        return sort_entries([(n, 0, b) for n, b in by_name.items()])

    def has_pending(self) -> bool:
        return bool(self.pending) or any(self.has_image_edits(p) for p in set(self.images) | self.new_arcs)

    def discard(self, arc_path: str):
        self.pending.pop(arc_path, None)
        self.images.pop(arc_path, None)
        self.new_arcs.discard(arc_path)

    def flush(self, output_path: Optional[str] = None) -> List[str]:
        """Write every arc with pending edits. Backs up existing output files first."""
        lines = []
        paths = [p for p in dict.fromkeys(list(self.images) + list(self.new_arcs) + list(self.pending))
                 if p in self.pending or self.has_image_edits(p)]
        if not paths:
            return lines
        backup_zip = None
        for arc_path in paths:
            if output_path:
                existing = os.path.join(output_path, arc_path)
                if os.path.exists(existing):
                    if backup_zip is None:
                        os.makedirs("Backups", exist_ok=True)
                        stamp = datetime.datetime.fromtimestamp(time.time()).strftime("%Y_%m_%d_%H_%M_%S")
                        backup_zip = zipfile.ZipFile(
                            os.path.join("Backups", f"portraits-before-{stamp}.zip"), "w", zipfile.ZIP_DEFLATED
                        )
                    backup_zip.write(existing, arc_path)
            entries = self.entries(arc_path)
            report = []
            edits = self.images.get(arc_path, {})
            if arc_path in self.new_arcs:
                report.append(f"new portrait file with {len(entries)} images")
            for key, blob in edits.items():
                if arc_path not in self.new_arcs:
                    report.append(f"{key}: {'removed' if blob is None else 'new image'}")
            entries, shift_report = shift_entries(entries, self.pending.get(arc_path, {}), self.lossless)
            report += shift_report
            self.gd.write_file(arc_path, build_arc(entries))
            lines.append(f"{arc_path}:")
            lines.extend("  " + r for r in report)
            self.discard(arc_path)
        if backup_zip:
            backup_zip.close()
        for cb in list(self.listeners):
            try:
                cb()
            except Exception:
                logging.exception("Portrait refresh failed.")
        logging.info("Portrait edits written:\n" + "\n".join(lines))
        return lines


# ----------------------------------------------------------------------------- reset (v1.5)


def read_original_arc(rom_root: Optional[str], arc_path: str) -> Optional[Dict[str, bytes]]:
    """The game's own copy of a portrait file (name -> LZ13 CTPK), or None when the
    game has no such file (a new character) or the ROM folder is not available."""
    if not rom_root:
        return None
    path = os.path.join(rom_root, *arc_path.split("/"))
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "rb") as f:
            raw = f.read()
        return {n: b for n, _i, b in parse_arc(raw)}
    except Exception:
        logging.exception(f"Could not read the original {arc_path}.")
        return None


def detect_shift(orig_rgba: bytes, cur_rgba: bytes, w: int, h: int, tolerance: float = 12.0) -> Optional[Tuple[int, int]]:
    """How far the artwork in cur was moved from orig: (dx, dy) such that
    cur[x + dx, y + dy] == orig[x, y]. None when cur is not a moved copy of orig
    (for example a different, imported picture).

    The search asks "where in the original does every bit of artwork in cur come from?", so
    artwork lost at the edges by earlier saved moves does not stop it from being recognized.
    Coarse-to-fine: every offset on a 4x smaller copy, then the best candidates at full size,
    each confirmed by verify_shift."""
    from PIL import Image, ImageChops, ImageStat

    def premultiplied(im):
        r, g, bl, al = im.split()
        return Image.merge("RGBA", [ImageChops.multiply(c, al) for c in (r, g, bl)] + [al])

    def art(im):
        return im.getchannel("A").point(lambda v: 255 if v > 24 else 0)

    a = premultiplied(Image.frombytes("RGBA", (w, h), orig_rgba))
    b = premultiplied(Image.frombytes("RGBA", (w, h), cur_rgba))
    if not a.getbbox():
        return (0, 0) if not b.getbbox() else None
    if not b.getbbox():
        return None

    def make_score(ia, ib, iw, ih):
        mb = art(ib)
        total = mb.histogram()[255]

        def score(dx, dy):
            x0, x1 = max(0, dx), min(iw, iw + dx)
            y0, y1 = max(0, dy), min(ih, ih + dy)
            if x1 <= x0 or y1 <= y0:
                return None
            here = mb.crop((x0, y0, x1, y1))
            inside = here.histogram()[255]
            if inside == 0:
                return None
            moved = ia.crop((x0 - dx, y0 - dy, x1 - dx, y1 - dy))
            diff = ImageStat.Stat(ImageChops.difference(moved, ib.crop((x0, y0, x1, y1))), mask=here).mean
            return sum(diff) / 4.0 + 255.0 * (1.0 - inside / total)

        return score

    f = 4 if min(w, h) >= 64 else 1
    sw, sh = max(1, w // f), max(1, h // f)
    small = make_score(a.resize((sw, sh), Image.BOX), b.resize((sw, sh), Image.BOX), sw, sh)
    coarse = []
    for dy in range(-sh + 1, sh):
        for dx in range(-sw + 1, sw):
            sc = small(dx, dy)
            if sc is not None:
                coarse.append((sc, dx, dy))
    if not coarse:
        return None
    coarse.sort()
    full = make_score(a, b, w, h)
    refined = {}
    for _sc, cx, cy in coarse[:8]:
        for dy in range(cy * f - f, cy * f + f + 1):
            for dx in range(cx * f - f, cx * f + f + 1):
                if (dx, dy) not in refined:
                    sc = full(dx, dy)
                    if sc is not None:
                        refined[(dx, dy)] = sc
    for (dx, dy), sc in sorted(refined.items(), key=lambda kv: kv[1])[:6]:
        if sc > 3 * tolerance:
            break
        if verify_shift(orig_rgba, cur_rgba, w, h, (dx, dy)):
            return dx, dy
    return None


def verify_shift(orig_rgba: bytes, cur_rgba: bytes, w: int, h: int, shift: Tuple[int, int],
                 tolerance: float = 16.0) -> bool:
    """Strict check that cur is orig moved by shift, judged on the artwork only (transparent
    background is ignored, so a different picture that happens to line up with empty space is
    not accepted):
    - nearly all of the artwork in cur comes from the moved original, with the same colors,
    - a good part of the original artwork is there.
    Artwork the original has but cur lacks is allowed: earlier saved moves can push parts of
    the picture out of the texture, and restoring the game's picture brings them back."""
    from PIL import Image, ImageChops, ImageStat

    dx, dy = shift
    a = Image.frombytes("RGBA", (w, h), orig_rgba)
    b = Image.frombytes("RGBA", (w, h), cur_rgba)
    moved = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    moved.paste(a, (dx, dy))

    def mask(im):
        return im.getchannel("A").point(lambda v: 255 if v > 24 else 0)

    def count(m):
        return m.histogram()[255]

    ma, mm, mb = mask(a), mask(moved), mask(b)
    total, here = count(ma), count(mb)
    if total == 0:
        return here == 0
    if here == 0:
        return False
    both = ImageChops.darker(mm, mb)
    if count(both) < 0.25 * total:
        return False
    if count(ImageChops.subtract(mb, mm)) > 0.04 * here:  # artwork the original does not explain
        return False

    def pm(im):
        r, g, bl, al = im.split()
        return Image.merge("RGBA", [ImageChops.multiply(c, al) for c in (r, g, bl)] + [al])

    mean = ImageStat.Stat(ImageChops.difference(pm(moved), pm(b)), mask=both).mean
    return sum(mean[:3]) / 3.0 <= tolerance


def shift_matches(orig_rgba: bytes, cur_rgba: bytes, w: int, h: int, shift: Tuple[int, int]) -> bool:
    """True when cur is orig moved by shift (one check instead of a search)."""
    return verify_shift(orig_rgba, cur_rgba, w, h, shift)


def _set_keys(entries: Dict[str, bytes], which: str) -> List[str]:
    return [
        n[: -len(ENTRY_SUFFIX)]
        for n in entries
        if n.endswith(ENTRY_SUFFIX) and texture_set(n) == which
    ]


@dataclasses.dataclass
class ResetResult:
    restored: bool  # True: the game's original pictures were put back
    saved_shift: Tuple[int, int] = (0, 0)  # how far the saved file had been moved
    keys: List[str] = dataclasses.field(default_factory=list)
    reason: str = ""


def reset_to_original(edits: "PortraitEdits", arc_path: str, which: str, current: Dict[str, bytes],
                      original: Optional[Dict[str, bytes]]) -> ResetResult:
    """Put a portrait set back where the game has it.

    current: the arc as the editor shows it (saved file + unsaved image edits), name -> LZ13 CTPK.
    original: the game's own arc (read_original_arc) or None.
    Unsaved moves are always dropped. When the saved pictures are moved copies of the game's,
    the game's pictures are queued to replace them (exact pixels, nothing lost at the edges).
    """
    edits.set(arc_path, which, 0, 0)
    if not original:
        return ResetResult(False, reason="The game has no original of this portrait file.")
    keys = [k for k in _set_keys(current, which) if k + ENTRY_SUFFIX in original]
    if not keys:
        return ResetResult(False, reason="None of these pictures exist in the game's original file.")
    ref = next((k for k in keys if k.lstrip(REVERSED_PREFIX) == "通常"), keys[0])

    def tex(blob):
        return CtpkTexture.parse(bytes(pgn.decompress_lz13(bytes(blob))))

    try:
        o, c = tex(original[ref + ENTRY_SUFFIX]), tex(current[ref + ENTRY_SUFFIX])
    except Exception as e:
        return ResetResult(False, reason=f"Could not read the pictures ({e}).")
    if (o.width, o.height) != (c.width, c.height):
        return ResetResult(False, reason="The picture size differs from the game's.")
    shift = detect_shift(o.rgba(), c.rgba(), o.width, o.height)
    if shift is None:
        return ResetResult(False, reason="The picture is not the game's original artwork (it was replaced).")
    restored = []
    for k in keys:
        if bytes(current[k + ENTRY_SUFFIX]) != bytes(original[k + ENTRY_SUFFIX]):
            try:
                ko, kc = tex(original[k + ENTRY_SUFFIX]), tex(current[k + ENTRY_SUFFIX])
                if (ko.width, ko.height) != (kc.width, kc.height):
                    k_shift = None
                elif shift_matches(ko.rgba(), kc.rgba(), ko.width, ko.height, shift):
                    k_shift = shift  # moved together with the main picture (the usual case)
                else:
                    k_shift = detect_shift(ko.rgba(), kc.rgba(), ko.width, ko.height)
            except Exception:
                k_shift = None
            if k_shift is None:
                continue  # a replaced picture: keep it
            edits.set_image(arc_path, k, bytes(pgn.decompress_lz13(bytes(original[k + ENTRY_SUFFIX]))))
            restored.append(k)
    return ResetResult(True, shift, restored)
