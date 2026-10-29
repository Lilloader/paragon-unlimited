"""Paragon Unlimited - world map nodes for new chapters (FE13 / Awakening).

How the world map works
-----------------------
gmap/spot.bcres   a CGFX file whose skeleton holds one bone per world map node, named
                  pos_<chapter>_<row> under the bone "pos", and one bone per road, named
                  route_<from>_<to> under "route" (the road's bends are child bones).
                  The game walks this bone tree by name (it does not use the bone index).
gmap/model.bcres  the landmark model drawn on a node, found by the name m_<chapter>.
OtherData         GM_<chapter> (table "ＧＭＡＰ配置"): the node's spot on the flat bottom-screen map.

New bones are appended at the end of spot.bcres and linked into the sibling chains; existing
data is never moved (only two size fields and the sibling links change). A model name is added
by appending a new name dictionary that points to an existing landmark model.

Pure Python (no numpy): the matrices are small.
"""
import math
import struct
from typing import Dict, List, Optional, Sequence, Tuple

BONE_SIZE = 0xE0
GLOBE_RADIUS = 100.0
# The bottom-screen map is a plain longitude / latitude projection of the globe.
# Fitted on the game's own nodes (mean error 2.7 px): x = 2.6626*lon + 300.05, y = -3.3359*lat + 185.35
GM_X = (2.66256951, -0.00451308425, 300.050948)
GM_Y = (-0.0146394335, -3.33593558, 185.353571)
GM_BOUNDS = (40, 30, 440, 215)

Vec = Tuple[float, float, float]
Mat = List[List[float]]  # 4x4


# ----------------------------------------------------------------------------- matrices
def _identity() -> Mat:
    return [[1.0 if i == j else 0.0 for j in range(4)] for i in range(4)]


def _mul(a: Mat, b: Mat) -> Mat:
    return [[sum(a[i][k] * b[k][j] for k in range(4)) for j in range(4)] for i in range(4)]


def _inverse(m: Mat) -> Mat:
    n = 4
    a = [row[:] + [1.0 if i == j else 0.0 for j in range(n)] for i, row in enumerate(m)]
    for c in range(n):
        p = max(range(c, n), key=lambda r: abs(a[r][c]))
        if abs(a[p][c]) < 1e-12:
            raise ValueError("Matrix cannot be inverted.")
        a[c], a[p] = a[p], a[c]
        piv = a[c][c]
        a[c] = [v / piv for v in a[c]]
        for r in range(n):
            if r != c and a[r][c]:
                f = a[r][c]
                a[r] = [x - f * y for x, y in zip(a[r], a[c])]
    return [row[n:] for row in a]


def _apply(m: Mat, p: Vec) -> Vec:
    x, y, z = p
    return tuple(m[i][0] * x + m[i][1] * y + m[i][2] * z + m[i][3] for i in range(3))


def _norm(p: Vec) -> float:
    return math.sqrt(sum(c * c for c in p))


def _on_globe(p: Vec) -> Vec:
    n = _norm(p) or 1.0
    return tuple(c / n * GLOBE_RADIUS for c in p)


def _angle(a: Vec, b: Vec) -> float:
    d = sum(x * y for x, y in zip(a, b)) / ((_norm(a) * _norm(b)) or 1.0)
    return math.degrees(math.acos(max(-1.0, min(1.0, d))))


def lon_lat(p: Vec) -> Tuple[float, float]:
    r = _norm(p) or 1.0
    return math.degrees(math.atan2(p[0], p[2])), math.degrees(math.asin(max(-1.0, min(1.0, p[1] / r))))


def from_lon_lat(lon: float, lat: float) -> Vec:
    lo, la = math.radians(lon), math.radians(lat)
    return (GLOBE_RADIUS * math.cos(la) * math.sin(lo), GLOBE_RADIUS * math.sin(la), GLOBE_RADIUS * math.cos(la) * math.cos(lo))


def gm_spot(p: Vec) -> Tuple[int, int]:
    """Bottom-screen map position for a globe position."""
    lon, lat = lon_lat(p)
    return (
        int(round(GM_X[0] * lon + GM_X[1] * lat + GM_X[2])),
        int(round(GM_Y[0] * lon + GM_Y[1] * lat + GM_Y[2])),
    )


# ----------------------------------------------------------------------------- CGFX helpers
class _Buf:
    def __init__(self, data: bytes):
        self.b = bytearray(data)

    def u32(self, o: int) -> int:
        return struct.unpack_from("<I", self.b, o)[0]

    def i32(self, o: int) -> int:
        return struct.unpack_from("<i", self.b, o)[0]

    def rel(self, o: int) -> int:
        v = self.i32(o)
        return o + v if v else 0

    def set_rel(self, field: int, target: int):
        struct.pack_into("<i", self.b, field, (target - field) if target else 0)

    def cstr(self, o: int) -> str:
        e = self.b.index(b"\0", o)
        return self.b[o:e].decode("utf-8", "replace")

    def dict_at(self, o: int) -> List[Tuple[str, int, int]]:
        """[(name, data_offset, entry_offset)] of a CGFX DICT."""
        _magic, _size, count = struct.unpack_from("<4sII", self.b, o)
        out = []
        for i in range(count):
            e = o + 0x1C + 16 * i
            _ref, _l, _r, no, do = struct.unpack_from("<IHHii", self.b, e)
            out.append((self.cstr(e + 8 + no), e + 12 + do, e))
        return out

    def align(self, n: int = 16):
        while len(self.b) % n:
            self.b.append(0)

    def add_string(self, s: str) -> int:
        o = len(self.b)
        self.b.extend(s.encode("utf-8") + b"\0")
        return o


def _patricia(names: Sequence[str]):
    """CGFX name dictionary tree (bit order: from the first byte, lsb first, highest differing bit)."""

    def bit(name, b):
        if name is None:
            return 0
        p = b >> 3
        if p >= len(name):
            return 0
        return (name[p] >> (b & 7)) & 1

    nodes = [[0xFFFFFFFF, 0, 0, None]]
    maxlen = max((len(n.encode()) for n in names), default=0)
    for i, nm in enumerate(names, 1):
        n = nm.encode()
        cur = nodes[0]
        nxt = nodes[cur[1]]
        while cur[0] > nxt[0]:
            cur = nxt
            nxt = nodes[cur[2] if bit(n, cur[0]) else cur[1]]
        other = nxt[3]
        b = maxlen * 8 - 1
        while b >= 0 and bit(n, b) == bit(other, b):
            b -= 1
        cur = nodes[0]
        cur_i = 0
        nxt_i = cur[1]
        nxt = nodes[nxt_i]
        right = False
        while cur[0] > nxt[0] and nxt[0] > b:
            cur = nxt
            cur_i = nxt_i
            right = bool(bit(n, cur[0]))
            nxt_i = cur[2] if right else cur[1]
            nxt = nodes[nxt_i]
        new = [b, 0, 0, n]
        if bit(n, b):
            new[1] = nxt_i
            new[2] = i
        else:
            new[1] = i
            new[2] = nxt_i
        nodes.append(new)
        if cur_i == 0:
            cur[1] = i
        elif right:
            cur[2] = i
        else:
            cur[1] = i
    return [(x[0] & 0xFFFFFFFF, x[1], x[2]) for x in nodes]


def write_dict(buf: _Buf, entries: List[Tuple[str, int, int]]) -> int:
    """Append a DICT for [(name, name_offset, data_offset)] and return its offset."""
    buf.align()
    at = len(buf.b)
    n = len(entries)
    buf.b.extend(b"\0" * (0x1C + 16 * n))
    tree = _patricia([e[0] for e in entries])
    struct.pack_into("<4sII", buf.b, at, b"DICT", 0x1C + 16 * n, n)
    r = tree[0]
    struct.pack_into("<IHHii", buf.b, at + 0xC, r[0], r[1], r[2], 0, 0)
    for i, ((_nm, no, do), t) in enumerate(zip(entries, tree[1:])):
        e = at + 0x1C + 16 * i
        struct.pack_into("<IHHii", buf.b, e, t[0], t[1], t[2], no - (e + 8), do - (e + 12))
    return at


# ----------------------------------------------------------------------------- spot.bcres
class Spots:
    """World map nodes and roads (gmap/spot.bcres, decompressed)."""

    def __init__(self, data: bytes):
        self.c = _Buf(data)
        self._index()

    def _index(self):
        c = self.c
        # The skeleton's bone dictionary is the biggest DICT in the file.
        # The skeleton's bone dictionary: the one whose 'pos' entry is a bone named 'pos'.
        o = c.b.find(b"DICT")
        while o != -1:
            try:
                ents = c.dict_at(o)
                bones = {n: d for n, d, _e in ents}
                if "pos" in bones and "route" in bones:
                    p, r = bones["pos"], bones["route"]
                    if c.cstr(c.rel(p)) == "pos" and c.cstr(c.rel(r)) == "route":
                        self.pos_root, self.route_root = p, r
                        return
            except (struct.error, ValueError, IndexError):
                pass
            o = c.b.find(b"DICT", o + 4)
        raise ValueError("spot.bcres has no 'pos' / 'route' bones")

    # tree walking --------------------------------------------------------------
    def children(self, parent: int) -> List[int]:
        out = []
        ch = self.c.rel(parent + 0x14)
        while ch:
            out.append(ch)
            ch = self.c.rel(ch + 0x1C)
        return out

    def name(self, bone: int) -> str:
        return self.c.cstr(self.c.rel(bone))

    def local(self, bone: int) -> Mat:
        m = struct.unpack_from("<12f", self.c.b, bone + 0x44)
        return [list(m[0:4]), list(m[4:8]), list(m[8:12]), [0.0, 0.0, 0.0, 1.0]]

    def world(self, bone: int) -> Mat:
        m = _identity()
        o = bone
        while o:
            m = _mul(self.local(o), m)
            o = self.c.rel(o + 0x10)
        return m

    def world_pos(self, bone: int) -> Vec:
        w = self.world(bone)
        return (w[0][3], w[1][3], w[2][3])

    def _all_bones(self) -> List[int]:
        out = []
        stack = [self.pos_root, self.route_root]
        # walk up to the skeleton root so every bone (incl. other trees) is counted
        root = self.pos_root
        while self.c.rel(root + 0x10):
            root = self.c.rel(root + 0x10)
        stack = [root]
        seen = set()
        while stack:
            b = stack.pop()
            if b in seen:
                continue
            seen.add(b)
            out.append(b)
            stack.extend(self.children(b))
            nxt = self.c.rel(b + 0x1C)
            if nxt:
                stack.append(nxt)
        return out

    # queries -------------------------------------------------------------------
    def nodes(self) -> Dict[str, Tuple[int, Vec]]:
        """chapter id (e.g. 'X001', '006') -> (bone offset, world position)."""
        out = {}
        for b in self.children(self.pos_root):
            n = self.name(b)
            if n.startswith("pos_"):
                parts = n.split("_")
                if len(parts) >= 3:
                    out[parts[1]] = (b, self.world_pos(b))
        return out

    def node_name(self, cid: str) -> Optional[str]:
        for b in self.children(self.pos_root):
            n = self.name(b)
            if n.startswith(f"pos_{cid}_"):
                return n
        return None

    def routes(self) -> Dict[str, int]:
        return {self.name(b): b for b in self.children(self.route_root) if self.name(b).startswith("route_")}

    def route_to(self, cid: str) -> Optional[Tuple[str, int]]:
        for n, b in self.routes().items():
            if n.endswith("_" + cid) and n.count("_") >= 2:
                return n, b
        return None

    # editing -------------------------------------------------------------------
    def _new_bone(self, template: int, name: str, parent: int, index: int) -> int:
        c = self.c
        c.align(16)
        o = len(c.b)
        c.b.extend(c.b[template : template + BONE_SIZE])
        parent_index = c.u32(parent + 8)
        struct.pack_into("<II", c.b, o + 8, index, parent_index)
        c.set_rel(o + 0x10, parent)
        c.set_rel(o + 0x14, 0)
        c.set_rel(o + 0x18, 0)
        c.set_rel(o + 0x1C, 0)
        so = c.add_string(name)
        c.set_rel(o, so)
        return o

    def _link_last(self, parent: int, new: int):
        kids = self.children(parent)
        if kids:
            self.c.set_rel(kids[-1] + 0x1C, new)
            self.c.set_rel(new + 0x18, kids[-1])
        else:
            self.c.set_rel(parent + 0x14, new)

    def _put_local(self, bone: int, rot: Optional[Mat], t: Vec):
        m = self.local(bone)
        if rot is not None:
            for i in range(3):
                for j in range(3):
                    m[i][j] = rot[i][j]
        for i in range(3):
            m[i][3] = t[i]
        flat = [m[i][j] for i in range(3) for j in range(4)]
        struct.pack_into("<12f", self.c.b, bone + 0x44, *flat)
        struct.pack_into("<3f", self.c.b, bone + 0x38, *t)

    def _place(self, bone: int, world: Vec, rot: Optional[Mat] = None):
        parent = self.c.rel(bone + 0x10)
        local = _apply(_inverse(self.world(parent)), world)
        self._put_local(bone, rot, local)

    def _next_index(self) -> int:
        return max(self.c.u32(b + 8) for b in self._all_bones()) + 1

    def set_node(self, cid: str, row: int, anchor: str, pos: Vec, points: Sequence[Vec]):
        """Add (or move) node pos_<cid>_<row> and the road route_<anchor>_<cid> with its bends."""
        nodes = self.nodes()
        if anchor not in nodes:
            raise KeyError(f"Chapter {anchor} has no world map node.")
        template_node = nodes[anchor][0]
        template_route = next(
            (b for b in self.routes().values() if self.children(b)), None
        )
        if template_route is None:
            raise ValueError("spot.bcres has no road to copy.")
        template_point = self.children(template_route)[0]
        rot = [row_[:3] for row_ in self.local(template_node)[:3]]
        idx = self._next_index()

        # node
        existing = None
        for b in self.children(self.pos_root):
            if self.name(b).startswith(f"pos_{cid}_"):
                existing = b
        if existing is None:
            nb = self._new_bone(template_node, f"pos_{cid}_{row}", self.pos_root, idx)
            idx += 1
            self._link_last(self.pos_root, nb)
        else:
            nb = existing
            if self.name(nb) != f"pos_{cid}_{row}":
                self.c.set_rel(nb, self.c.add_string(f"pos_{cid}_{row}"))
        self._place(nb, pos, rot)

        # road
        found = self.route_to(cid)
        if found is None:
            rb = self._new_bone(template_route, f"route_{anchor}_{cid}", self.route_root, idx)
            idx += 1
            self._put_local(rb, [[1, 0, 0], [0, 1, 0], [0, 0, 1]], (0.0, 0.0, 0.0))
            struct.pack_into("<3f", self.c.b, rb + 0x20, 1, 1, 1)
            struct.pack_into("<3f", self.c.b, rb + 0x2C, 0, 0, 0)
            self._link_last(self.route_root, rb)
        else:
            name, rb = found
            if name != f"route_{anchor}_{cid}":
                self.c.set_rel(rb, self.c.add_string(f"route_{anchor}_{cid}"))
        kids = self.children(rb)
        for k, p in enumerate(points):
            if k < len(kids):
                pb = kids[k]
            else:
                pb = self._new_bone(template_point, f"route_{k}_90", rb, idx)
                idx += 1
                struct.pack_into("<3f", self.c.b, pb + 0x20, 1, 1, 1)
                struct.pack_into("<3f", self.c.b, pb + 0x2C, 0, 0, 0)
                self._link_last(rb, pb)
            self._place(pb, p, [[1, 0, 0], [0, 1, 0], [0, 0, 1]])
        self._fix_sizes()

    def _fix_sizes(self):
        self.c.align(16)
        struct.pack_into("<I", self.c.b, 0xC, len(self.c.b))
        struct.pack_into("<I", self.c.b, 0x18, len(self.c.b) - 0x14)

    def to_bytes(self) -> bytes:
        return bytes(self.c.b)

    # placement -----------------------------------------------------------------
    def auto_place(self, anchor: str, avoid: Sequence[Vec] = (), distance: float = 7.0) -> Tuple[Vec, List[Vec]]:
        """A free spot near the anchor's node (kept on the visible part of the bottom map)."""
        nodes = self.nodes()
        a = nodes[anchor][1]
        others = [p for k, (_b, p) in nodes.items() if k != anchor] + list(avoid)
        lon0, lat0 = lon_lat(a)
        best = None
        for dist in (distance, distance * 1.4, distance * 0.75, distance * 1.9):
            for step in range(24):
                ang = math.radians(step * 15)
                lat = lat0 + dist * math.sin(ang)
                lon = lon0 + dist * math.cos(ang) / max(0.3, math.cos(math.radians(lat0)))
                if not (-60 <= lat <= 75):
                    continue
                p = from_lon_lat(lon, lat)
                gx, gy = gm_spot(p)
                if not (GM_BOUNDS[0] <= gx <= GM_BOUNDS[2] and GM_BOUNDS[1] <= gy <= GM_BOUNDS[3]):
                    continue
                clearance = min((_angle(p, q) for q in others), default=90.0)
                score = clearance - abs(dist - distance) * 0.2
                if best is None or score > best[0]:
                    best = (score, p)
            if best is not None and best[0] >= distance * 0.6:
                break
        if best is None:
            best = (0, from_lon_lat(lon0 + distance, lat0))
        p = best[1]
        points = [_on_globe(tuple(a[i] + (p[i] - a[i]) * t for i in range(3))) for t in (1 / 3, 2 / 3)]
        return p, points


# ----------------------------------------------------------------------------- model.bcres
class Landmarks:
    """Landmark model names (gmap/model.bcres, decompressed)."""

    def __init__(self, data: bytes):
        self.c = _Buf(data)

    def _entries(self):
        d0 = self.c.rel(0x20)
        return d0, self.c.dict_at(d0)

    def names(self) -> List[str]:
        return [n for n, _d, _e in self._entries()[1]]

    def set_alias(self, name: str, same_as: str):
        """Make model `name` (e.g. m_U002) draw the landmark of `same_as` (e.g. m_X001)."""
        c = self.c
        d0, ents = self._entries()
        target = next((d for n, d, _e in ents if n == same_as), None)
        if target is None:
            raise KeyError(f"No landmark model {same_as}")
        for n, _d, e in ents:
            if n == name:
                c.set_rel(e + 12, target)
                return
        entries = []
        for n, d, e in ents:
            no = e + 8 + c.i32(e + 8)
            entries.append((n, no, d))
        c.align()
        so = c.add_string(name)
        entries.append((name, so, target))
        at = write_dict(c, entries)
        c.align()
        struct.pack_into("<I", c.b, 0x1C, len(entries))
        c.set_rel(0x20, at)
        struct.pack_into("<I", c.b, 0xC, len(c.b))

    def to_bytes(self) -> bytes:
        return bytes(self.c.b)
