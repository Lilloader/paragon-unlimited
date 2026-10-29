"""Paragon Unlimited: read FE13 (Awakening) battle models (CGFX .m.lz) for previews.

Read-only. Only what is needed to draw the model in its rest pose is read: the meshes,
their vertices (position / normal / UV0 / bone indices / weights), triangle lists, the
skeleton and the name of each material's color texture. Layouts follow the CGFX notes on
3dbrew (CGFX page) and were checked against the game's own models.
"""
import math
import struct
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

GL_BYTE, GL_UBYTE, GL_SHORT, GL_USHORT, GL_FLOAT = 0x1400, 0x1401, 0x1402, 0x1403, 0x1406
_FMT = {GL_BYTE: ("b", 1), GL_UBYTE: ("B", 1), GL_SHORT: ("h", 2), GL_USHORT: ("H", 2), GL_FLOAT: ("f", 4)}

ATTR_POSITION, ATTR_NORMAL, ATTR_TANGENT, ATTR_COLOR = 0, 1, 2, 3
ATTR_UV0, ATTR_UV1, ATTR_UV2, ATTR_INDEX, ATTR_WEIGHT = 4, 5, 6, 7, 8  # 7 = bone index (ubyte), 8 = weight (x0.01)

Matrix = List[float]  # 3x4 row-major: [r00 r01 r02 t0, r10 r11 r12 t1, r20 r21 r22 t2]
IDENTITY: Matrix = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0]


def mat_mul(a: Matrix, b: Matrix) -> Matrix:
    out = [0.0] * 12
    for r in range(3):
        for c in range(4):
            v = sum(a[r * 4 + k] * b[k * 4 + c] for k in range(3))
            if c == 3:
                v += a[r * 4 + 3]
            out[r * 4 + c] = v
    return out


def mat_apply(m: Matrix, x, y, z, w=1.0):
    return (
        m[0] * x + m[1] * y + m[2] * z + m[3] * w,
        m[4] * x + m[5] * y + m[6] * z + m[7] * w,
        m[8] * x + m[9] * y + m[10] * z + m[11] * w,
    )


@dataclass
class Bone:
    name: str
    index: int
    parent: int
    world: Matrix


@dataclass
class Mesh:
    """One drawable part, already in model space (rest pose)."""

    name: str
    material: str
    texture: Optional[str]
    positions: List[Tuple[float, float, float]]
    normals: List[Tuple[float, float, float]]
    uvs: List[Tuple[float, float]]
    triangles: List[Tuple[int, int, int]]


@dataclass
class Model:
    name: str
    meshes: List[Mesh] = field(default_factory=list)
    bones: Dict[str, Bone] = field(default_factory=dict)
    source: bytes = b""  # the CGFX file (weapons keep their textures inside it)

    def bounds(self):
        xs = [p for m in self.meshes for p in m.positions]
        if not xs:
            return (0, 0, 0), (0, 0, 0)
        lo = tuple(min(p[i] for p in xs) for i in range(3))
        hi = tuple(max(p[i] for p in xs) for i in range(3))
        return lo, hi


class _Reader:
    def __init__(self, data: bytes):
        if data[:4] != b"CGFX":
            raise ValueError("Not a CGFX file")
        self.d = data

    def u8(self, o):
        return self.d[o]

    def u32(self, o):
        return struct.unpack_from("<I", self.d, o)[0]

    def i32(self, o):
        return struct.unpack_from("<i", self.d, o)[0]

    def f32s(self, o, n):
        return list(struct.unpack_from(f"<{n}f", self.d, o))

    def rel(self, o) -> int:
        v = self.u32(o)
        return (o + v) & 0xFFFFFFFF if v else 0

    def string(self, o) -> Optional[str]:
        p = self.rel(o)
        if not p:
            return None
        e = self.d.index(b"\0", p)
        return self.d[p:e].decode("utf-8", errors="replace")

    def ptr_list(self, o) -> List[int]:
        n, p = self.u32(o), self.rel(o + 4)
        return [self.rel(p + 4 * i) for i in range(n)] if p else []

    def dict(self, o) -> List[Tuple[str, int]]:
        """o: address of a DICT block."""
        if not o or self.d[o : o + 4] != b"DICT":
            return []
        n = self.u32(o + 8)
        out = []
        for i in range(n):
            e = o + 0x1C + i * 0x10
            out.append((self.string(e + 8), self.rel(e + 12)))
        return out


def _bones(r: _Reader, skel: int) -> List[Bone]:
    """Bones with their rest-pose world matrix. Bone record: 0x20 scale, 0x2C rotation,
    0x38 translation, 0x44 local matrix, 0x74 world (left empty in the files), 0xA4 inverse."""
    raw = []
    for name, b in r.dict(r.rel(skel + 0x1C)):
        idx, parent = r.i32(b + 8), r.i32(b + 0xC)
        raw.append((name, idx, parent, r.f32s(b + 0x44, 12)))
    raw.sort(key=lambda x: x[1])
    by_index = {}
    bones = []
    for name, idx, parent, local in raw:
        world = mat_mul(by_index[parent], local) if parent in by_index else list(local)
        by_index[idx] = world
        bones.append(Bone(name, idx, parent, world))
    return bones


def _material_textures(r: _Reader, materials: List[Tuple[str, int]]) -> Dict[str, Optional[str]]:
    """Color texture of each material: the TXOB references inside the material, skipping
    environment / specular / normal maps."""
    starts = sorted(o for _n, o in materials)
    out = {}
    for name, off in materials:
        nxt = next((s for s in starts if s > off), off + 0x800)
        names = []
        pos = off
        while True:
            i = r.d.find(b"TXOB", pos, nxt)
            if i < 0:
                break
            ref = i - 4
            pos = i + 4
            if r.u32(ref) & 0xFF000000 != 0x20000000:
                continue
            tex = r.string(ref + 0x18) or r.string(ref + 0xC)
            if tex:
                names.append(tex)
        out[name] = _pick_color(names)
    return out


def _pick_color(names: List[str]) -> Optional[str]:
    if not names:
        return None
    for n in names:
        if n.lower().endswith(("_c0", "_c1", "_c", "_col", "_color")):
            return n
    skip = ("envmap", "_s0", "_s1", "_n0", "_n", "_spec", "_nrm", "toon")
    for n in names:
        if not any(n.lower().endswith(s) or n.lower() == s for s in skip):
            return n
    return names[0]


def _read_attributes(r: _Reader, vb: int):
    """Interleaved vertex buffer -> (stride, data offset, size, [(type, fmt, elements, scale, offset)])."""
    size, data = r.u32(vb + 0x14), r.rel(vb + 0x18)
    stride = r.u32(vb + 0x24)
    attrs = []
    for a in r.ptr_list(vb + 0x28):
        if r.u32(a) != 0x40000001:
            continue
        attrs.append((r.u32(a + 4), r.u32(a + 0x24), r.u32(a + 0x28), struct.unpack_from("<f", r.d, a + 0x2C)[0], r.u32(a + 0x30)))
    return stride, data, size, attrs


def _fixed_attribute(r: _Reader, vb: int):
    """Constant attribute (flag 0x80000000): (type, values)."""
    typ = r.u32(vb + 4)
    count = r.u32(vb + 0x14) if r.u32(vb + 0x14) < 8 else 4
    p = r.rel(vb + 0x18)
    vals = r.f32s(p, count) if p else []
    return typ, vals


RIGID_STATS = {}


def read_model(data: bytes, model_index: int = 0) -> Model:
    r = _Reader(data)
    models = r.dict(r.rel(0x14 + 0x0C))
    if not models:
        raise ValueError("No model in this file")
    name, cm = models[min(model_index, len(models) - 1)]
    if r.d[cm + 4 : cm + 8] != b"CMDL":
        raise ValueError("Bad model header")
    model = Model(name or "model", source=data)

    flags = r.u32(cm)
    bones: List[Bone] = []
    if flags & 0x80:
        skel = r.rel(cm + 0xE0)
        if skel and r.d[skel + 4 : skel + 8] == b"SOBJ":
            bones = _bones(r, skel)
    model.bones = {b.name: b for b in bones}
    world = [b.world for b in bones]

    mesh_objs = r.ptr_list(cm + 0xB4)
    materials = r.dict(r.rel(cm + 0xC0))
    shapes = r.ptr_list(cm + 0xC4)
    textures = _material_textures(r, materials)

    for mi, mo in enumerate(mesh_objs):
        shape_i, mat_i = r.u32(mo + 0x18), r.u32(mo + 0x1C)
        if shape_i >= len(shapes):
            continue
        mat_name = materials[mat_i][0] if mat_i < len(materials) else ""
        mesh = _read_shape(r, shapes[shape_i], world)
        if mesh is None:
            continue
        mesh.name = r.string(mo + 0xC) or f"mesh{mi}"
        mesh.material = mat_name
        mesh.texture = textures.get(mat_name)
        model.meshes.append(mesh)
    return model


def _read_shape(r: _Reader, sh: int, world: List[Matrix]) -> Optional[Mesh]:
    offset = r.f32s(sh + 0x20, 3)
    vbs = r.ptr_list(sh + 0x38)
    main = next((vb for vb in vbs if r.u32(vb) == 0x40000002), None)
    if main is None:
        return None
    stride, data, size, attrs = _read_attributes(r, main)
    if not stride:
        return None
    count = size // stride
    fixed = {}
    for vb in vbs:
        if r.u32(vb) & 0x80000000 and r.u32(vb) != 0x40000002:
            t, vals = _fixed_attribute(r, vb)
            fixed[t] = vals

    cols = {}
    for typ, fmt, n, scale, off in attrs:
        if fmt not in _FMT:
            continue
        code, sz = _FMT[fmt]
        st = struct.Struct("<" + code * n)
        vals = []
        for v in range(count):
            raw = st.unpack_from(r.d, data + v * stride + off)
            vals.append(tuple(x * scale for x in raw))
        cols[typ] = vals
    if ATTR_POSITION not in cols:
        return None

    positions = [tuple(p[i] + offset[i] for i in range(3)) for p in cols[ATTR_POSITION]]
    normals = cols.get(ATTR_NORMAL) or [(0.0, 0.0, 1.0)] * count
    uvs = [(u[0], u[1]) for u in cols.get(ATTR_UV0, [])] or [(0.0, 0.0)] * count
    out_pos = list(positions)
    out_nrm = list(normals)
    triangles = []
    skinned = [False] * count

    for sm in r.ptr_list(sh + 0x2C):
        nb = r.u32(sm)
        bp = r.rel(sm + 4)
        bone_ids = [r.u32(bp + 4 * i) for i in range(nb)] if bp else []
        skinning = r.u32(sm + 8)
        sub_tris = []
        for face in r.ptr_list(sm + 0xC):
            for fd in r.ptr_list(face):
                fmt = r.u32(fd)
                mode = r.u8(fd + 4)
                nbytes, ip = r.u32(fd + 8), r.rel(fd + 0xC)
                if not ip:
                    continue
                if fmt == GL_USHORT or (fmt & 2 and fmt not in (GL_UBYTE,)):
                    idx = list(struct.unpack_from(f"<{nbytes // 2}H", r.d, ip))
                else:
                    idx = list(r.d[ip : ip + nbytes])
                if mode == 0:  # triangles
                    sub_tris += [tuple(idx[i : i + 3]) for i in range(0, len(idx) - 2, 3)]
                elif mode == 1:  # strip
                    for i in range(len(idx) - 2):
                        a, b, c = idx[i : i + 3]
                        sub_tris.append((a, b, c) if i % 2 == 0 else (b, a, c))
                elif mode == 2:  # fan
                    sub_tris += [(idx[0], idx[i], idx[i + 1]) for i in range(1, len(idx) - 1)]
        triangles += sub_tris
        # Rest pose: rigid / unskinned parts are stored relative to their bone.
        if skinning != 2 and world and bone_ids:
            used = {v for t in sub_tris for v in t}
            bone_index = cols.get(ATTR_INDEX)
            for v in used:
                if v >= count or skinned[v]:
                    continue
                bi = 0
                if bone_index is not None:
                    bi = int(round(bone_index[v][0]))
                elif ATTR_INDEX in fixed and fixed[ATTR_INDEX]:
                    bi = int(round(fixed[ATTR_INDEX][0]))
                if bi >= len(bone_ids) or bone_ids[bi] >= len(world):
                    continue
                m = world[bone_ids[bi]]
                if m == IDENTITY:
                    skinned[v] = True
                    continue
                out_pos[v] = mat_apply(m, *positions[v])
                nx, ny, nz = normals[v][:3]
                out_nrm[v] = mat_apply(m, nx, ny, nz, 0.0)
                skinned[v] = True

    return Mesh("", "", None, out_pos, [tuple(n[:3]) for n in out_nrm], uvs, triangles)


# --------------------------------------------------------------------------- assembling


ATTACH_BONES = ("head", "Head", "c_head", "neck")


def attach_matrix(body: Model, bone_names=ATTACH_BONES) -> Optional[Matrix]:
    for n in bone_names:
        b = body.bones.get(n)
        if b is not None:
            return b.world
    for b in body.bones.values():
        if "head" in b.name.lower():
            return b.world
    return None


def transformed(mesh: Mesh, m: Matrix, texture: Optional[str] = None) -> Mesh:
    return Mesh(
        mesh.name,
        mesh.material,
        texture or mesh.texture,
        [mat_apply(m, *p) for p in mesh.positions],
        [mat_apply(m, n[0], n[1], n[2], 0.0) for n in mesh.normals],
        list(mesh.uvs),
        list(mesh.triangles),
    )


def assemble(body: Optional[Model], parts: List[Model], name: str = "character") -> Model:
    """Body plus head/hair models placed on the body's head bone (rest pose).
    Head and hair models are built around the head bone, so they only need its position."""
    out = Model(name)
    m = IDENTITY
    if body is not None:
        out.meshes += body.meshes
        out.bones = dict(body.bones)
        m = attach_matrix(body) or IDENTITY
    for part in parts:
        if part is None:
            continue
        out.meshes += [transformed(mesh, m) for mesh in part.meshes]
    return out


# --------------------------------------------------------------------------- camera helpers


def view_matrix(yaw_deg: float, pitch_deg: float) -> Matrix:
    """Rotation: yaw around Y, then pitch around X."""
    cy, sy = math.cos(math.radians(yaw_deg)), math.sin(math.radians(yaw_deg))
    cp, sp = math.cos(math.radians(pitch_deg)), math.sin(math.radians(pitch_deg))
    yaw = [cy, 0, sy, 0, 0, 1, 0, 0, -sy, 0, cy, 0]
    pitch = [1, 0, 0, 0, 0, cp, -sp, 0, 0, sp, cp, 0]
    return mat_mul(pitch, yaw)


# --------------------------------------------------------------------------- rendering


def load_model(gd, name: str) -> Model:
    """Read b/<name>.m.lz from the project (read-only)."""
    raw = bytes(gd.read_file(f"b/{name}.m.lz"))
    if raw[:4] != b"CGFX" and raw[:1] in (b"\x10", b"\x11", b"\x13"):
        from paragon import paragon as pgn

        raw = bytes(pgn.decompress_lz13(raw))
    return read_model(raw)


def safe_read_cgfx(raw: bytes):
    """Textures of a CGFX file; never raises (a bad file must not take Paragon down)."""
    from paragon import paragon as pgn

    try:
        return pgn.read_cgfx(raw)
    except BaseException:  # the native reader can raise a PanicException (not an Exception)
        return []


def texture_from_cgfx(raw: bytes, name: str, fallback_first=True):
    textures = safe_read_cgfx(raw)
    tex = next((t for t in textures if t.filename == name), None)
    if tex is None and fallback_first and textures:
        tex = textures[0]
    if tex is None:
        return None
    return tex.width, tex.height, bytes(tex.pixel_data)


def load_texture(gd, name: str, cgfx: Optional[bytes] = None):
    """(width, height, RGBA bytes) of the texture `name` from b/<name>.t.lz (or the given
    CGFX bytes, e.g. with an unsaved import), or None."""
    from paragon import paragon as pgn

    raw = cgfx
    if raw is None:
        try:
            raw = bytes(gd.read_file(f"b/{name}.t.lz"))
        except Exception:
            return None
    if raw[:4] != b"CGFX" and raw[:1] in (b"\x10", b"\x11", b"\x13"):
        raw = bytes(pgn.decompress_lz13(raw))
    return texture_from_cgfx(raw, name)


def project(model: Model, size: int, yaw: float, pitch: float, zoom: float = 1.0):
    """Mesh arrays for render_meshes: orthographic view, fitted to `size` pixels."""
    import array

    lo, hi = model.bounds()
    center = [(lo[i] + hi[i]) / 2 for i in range(3)]
    radius = max(1e-6, max(math.dist(center, p) for m in model.meshes for p in m.positions) if model.meshes else 1.0)
    scale = size * 0.48 / radius * zoom
    rot = view_matrix(yaw, pitch)
    half = size / 2
    out = []
    for m in model.meshes:
        pos = array.array("f")
        nrm = array.array("f")
        for (x, y, z), (nx, ny, nz) in zip(m.positions, m.normals):
            rx, ry, rz = mat_apply(rot, x - center[0], y - center[1], z - center[2])
            pos.extend((half + rx * scale, half - ry * scale, rz))
            ax, ay, az = mat_apply(rot, nx, ny, nz, 0.0)
            nrm.extend((ax, -ay, az))  # screen space: y points down
        uv = array.array("f", [c for p in m.uvs for c in p])
        idx = array.array("I", [i for t in m.triangles for i in t])
        out.append((m, pos.tobytes(), nrm.tobytes(), uv.tobytes(), idx.tobytes()))
    return out


def render_image(model: Model, textures: Dict[str, Optional[tuple]], size: int, yaw: float = 25.0,
                 pitch: float = 10.0, zoom: float = 1.0, background=(32, 32, 32, 255), supersample: int = 2):
    """PIL image of the model. textures: texture name -> (w, h, rgba) or None."""
    from PIL import Image
    from paragon import paragon as pgn

    big = size * supersample
    meshes = []
    for m, pos, nrm, uv, idx in project(model, big, yaw, pitch, zoom):
        tex = textures.get(m.texture) if m.texture else None
        if tex:
            meshes.append((pos, nrm, uv, idx, tex[2], tex[0], tex[1]))
        else:
            meshes.append((pos, nrm, uv, idx, b"", 0, 0))
    rgba = bytes(pgn.render_meshes(big, big, meshes, (-0.35, -0.55, 0.75), tuple(background)))
    img = Image.frombytes("RGBA", (big, big), rgba)
    if supersample > 1:
        img = img.resize((size, size), Image.LANCZOS)
    return img
