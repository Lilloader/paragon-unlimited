"""Paragon Unlimited - FE13 skill icons: put new 24x24 icons into the free cells of skill.tga.

skill.tga lives in systems/icon*.ctpk.lz (one per language, e.g. icon_E and icon_U). It is a
256x512 RGBA4 texture holding 10 x 21 cells of 24x24; the game uses cells 0-104, the rest are
empty. A skill's "icon" field is its cell number. Imports are kept in memory and written on save
to every icon file the project has, so all languages show the same icon.
"""
import logging
import struct
from typing import Dict, List, Optional, Tuple

ICON_FILES = [
    "systems/icon.ctpk.lz",
    "systems/icon_E.ctpk.lz",
    "systems/icon_U.ctpk.lz",
    "systems/icon_S.ctpk.lz",
    "systems/icon_F.ctpk.lz",
    "systems/icon_G.ctpk.lz",
    "systems/icon_i.ctpk.lz",
]
TEXTURE = "skill.tga"
CELL = 24
RGBA4 = 4


def _morton(x: int, y: int) -> int:
    m = 0
    for k in range(3):
        m |= ((x >> k) & 1) << (2 * k)
        m |= ((y >> k) & 1) << (2 * k + 1)
    return m


_M = [[_morton(x, y) for x in range(8)] for y in range(8)]


def find_texture(ctpk: bytes, name: str = TEXTURE) -> Optional[Tuple[int, int, int, int, int]]:
    """(pixel offset, length, format, width, height) of a texture in a CTPK."""
    if ctpk[:4] != b"CTPK":
        return None
    count = struct.unpack_from("<H", ctpk, 6)[0]
    base = struct.unpack_from("<I", ctpk, 8)[0]
    for i in range(count):
        fn, length, off, fmt, w, h = struct.unpack_from("<IIIIHH", ctpk, 0x20 + 0x20 * i)
        end = ctpk.index(b"\0", fn)
        if ctpk[fn:end].decode("ascii", "replace") == name:
            return base + off, length, fmt, w, h
    return None


def _addr(x: int, y: int, w: int) -> int:
    return ((y // 8) * (w // 8) + (x // 8)) * 64 + _M[y % 8][x % 8]


def read_cell(ctpk: bytes, cell: int) -> bytes:
    """RGBA bytes (24x24) of one cell."""
    off, length, fmt, w, h = find_texture(ctpk)
    if fmt != RGBA4:
        raise ValueError(f"{TEXTURE} has format {fmt}, expected RGBA4.")
    cols = w // CELL
    x0, y0 = (cell % cols) * CELL, (cell // cols) * CELL
    out = bytearray()
    for y in range(y0, y0 + CELL):
        for x in range(x0, x0 + CELL):
            v = struct.unpack_from("<H", ctpk, off + 2 * _addr(x, y, w))[0]
            out += bytes((((v >> 12) & 15) * 17, ((v >> 8) & 15) * 17, ((v >> 4) & 15) * 17, (v & 15) * 17))
    return bytes(out)


def write_cell(ctpk: bytes, cell: int, rgba: bytes) -> bytes:
    off, length, fmt, w, h = find_texture(ctpk)
    if fmt != RGBA4:
        raise ValueError(f"{TEXTURE} has format {fmt}, expected RGBA4.")
    cols = w // CELL
    if not 0 <= cell < cols * (h // CELL):
        raise ValueError(f"Icon cell {cell} is outside skill.tga.")
    x0, y0 = (cell % cols) * CELL, (cell // cols) * CELL
    out = bytearray(ctpk)
    i = 0
    for y in range(y0, y0 + CELL):
        for x in range(x0, x0 + CELL):
            r, g, b, a = rgba[i : i + 4]
            i += 4
            v = ((r * 15 + 127) // 255) << 12 | ((g * 15 + 127) // 255) << 8 | ((b * 15 + 127) // 255) << 4 | ((a * 15 + 127) // 255)
            struct.pack_into("<H", out, off + 2 * _addr(x, y, w), v)
    return bytes(out)


def cell_count(ctpk: bytes) -> int:
    t = find_texture(ctpk)
    return (t[3] // CELL) * (t[4] // CELL) if t else 0


def is_free(ctpk: bytes, cell: int) -> bool:
    px = read_cell(ctpk, cell)
    return all(px[k] == 0 for k in range(3, len(px), 4))


def fit_icon(image) -> bytes:
    """PIL image -> 24x24 RGBA bytes (scaled to fit, centered)."""
    from PIL import Image

    img = image.convert("RGBA")
    if img.size != (CELL, CELL):
        scale = min(CELL / img.width, CELL / img.height)
        nw, nh = max(1, round(img.width * scale)), max(1, round(img.height * scale))
        img = img.resize((nw, nh), Image.LANCZOS)
        canvas = Image.new("RGBA", (CELL, CELL), (0, 0, 0, 0))
        canvas.paste(img, ((CELL - nw) // 2, (CELL - nh) // 2))
        img = canvas
    return img.tobytes()


class SkillIconEdits:
    def __init__(self, gd):
        self.gd = gd
        self.pending: Dict[str, bytes] = {}  # path -> decompressed CTPK

    def files(self) -> List[str]:
        out = []
        for p in ICON_FILES:
            try:
                if p in self.pending or self.gd.file_exists(p, False):
                    out.append(p)
            except Exception:
                try:
                    self.gd.read_file(p)
                    out.append(p)
                except Exception:
                    pass
        return out

    def current(self, path: str) -> bytes:
        if path in self.pending:
            return self.pending[path]
        raw = bytes(self.gd.read_file(path))
        if raw[:4] != b"CTPK":
            from paragon import paragon as pgn

            raw = bytes(pgn.decompress_lz13(raw))
        return raw

    def first_file(self) -> Optional[str]:
        f = self.files()
        return f[0] if f else None

    def free_cells(self) -> List[int]:
        p = self.first_file()
        if not p:
            return []
        ctpk = self.current(p)
        return [c for c in range(cell_count(ctpk)) if is_free(ctpk, c)]

    def import_icon(self, rgba: bytes, cell: Optional[int] = None) -> int:
        """Put a 24x24 RGBA icon into cell (or the first free cell) of every icon file. Returns the cell."""
        files = self.files()
        if not files:
            raise ValueError("This project has no systems/icon*.ctpk.lz file.")
        if cell is None:
            free = self.free_cells()
            if not free:
                raise ValueError("skill.tga has no free icon cell left.")
            cell = free[0]
        for p in files:
            self.pending[p] = write_cell(self.current(p), cell, rgba)
        return cell

    def cell_rgba(self, cell: int) -> Optional[bytes]:
        p = self.first_file()
        return read_cell(self.current(p), cell) if p else None

    def has_pending(self) -> bool:
        return bool(self.pending)

    def flush(self) -> List[str]:
        lines = []
        for path, ctpk in list(self.pending.items()):
            self.gd.write_file(path, ctpk)  # compressed automatically (.lz)
            lines.append(path)
            del self.pending[path]
        if lines:
            logging.info("Skill icons written: " + ", ".join(lines))
        return lines


def edits_for(gs) -> SkillIconEdits:
    edits = getattr(gs, "pu_skill_icon_edits", None)
    if edits is None:
        edits = SkillIconEdits(gs.data)
        gs.pu_skill_icon_edits = edits
    return edits
