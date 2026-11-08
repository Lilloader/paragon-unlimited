"""Paragon Unlimited - the sparkle that marks Map Maker event tiles.

The game has a "reward tile" sparkle (effect ごほうびマス1, EFF_BMP_REWARD1: glittering grains and a
light streak), but the game itself uses it, so event tiles get their own copy in red.

The game finds effects by name in data/effect.bin, and that list cannot grow: with one more record
the game found no effect at all (tested in Azahar). So the red sparkle takes the file of an effect
the game lists but never plays: スポット異界の門 (a world map spot effect that no code, script or data
file uses; same flags as ごほうびマス1, no sound). Scripts play it with
ev::EffectPlay3D("スポット異界の門", x, y), and effect/スポット異界の門.bcres.lz is the red sparkle.

An earlier version added a record "PU_EventTile" to data/effect.bin; strip_added() takes it out again.

data/effect.bin layout (the usual Intelligent Systems .bin):
  header 0x20: file size, data size, pointer count, label count
  data: [0] -> "エフェクト", [4] record count, [8] -> first record; records of 16 bytes:
        name ->, file ->, sound -> (or 0), flags
  pointer table (data offsets of every pointer), label table (data offset, name offset), strings.
"""
import struct
from typing import Tuple

EFFECT = "スポット異界の門"  # unused by the game: its file becomes the red sparkle
OLD_EFFECT = "PU_EventTile"  # the record an earlier version added to data/effect.bin
BASE = "ごほうびマス1"
FILE = f"effect/{EFFECT}.bcres.lz"
LIST = "data/effect.bin"
RED = (255, 60, 60)
HEADER = 0x20


def _parse(b: bytes):
    size, dsize, pcount, lcount = struct.unpack_from("<4I", b, 0)
    data = bytearray(b[HEADER : HEADER + dsize])
    pt = HEADER + dsize
    ptrs = [struct.unpack_from("<I", b, pt + 4 * i)[0] for i in range(pcount)]
    lt = pt + 4 * pcount
    labels = [struct.unpack_from("<II", b, lt + 8 * i) for i in range(lcount)]
    st = lt + 8 * lcount
    strings = bytearray(b[st:])
    return data, ptrs, labels, strings, st - HEADER


def _string_at(strings: bytes, off: int) -> str:
    end = strings.find(b"\0", off)
    return strings[off:end].decode("cp932")


def records(b: bytes):
    """[(name, file, sound, flags)] of the effect list."""
    data, ptrs, _labels, strings, sbase = _parse(b)
    count = struct.unpack_from("<I", data, 4)[0]
    first = struct.unpack_from("<I", data, 8)[0]
    pset = set(ptrs)
    out = []
    for i in range(count):
        o = first + 16 * i
        name, file, sound, flags = struct.unpack_from("<4I", data, o)
        get = lambda field, v: _string_at(strings, v - sbase) if (o + field) in pset and v else ""
        out.append((get(0, name), get(4, file), get(8, sound), flags))
    return out


def has_effect(b: bytes, name: str = EFFECT) -> bool:
    return any(r[0] == name for r in records(b))


def add_effect(b: bytes, name: str = EFFECT, file: str = EFFECT, like: str = BASE) -> bytes:
    """effect.bin with one more record (at the end), with the flags of `like`."""
    if has_effect(b, name):
        return b
    data, ptrs, labels, strings, sbase = _parse(b)
    count = struct.unpack_from("<I", data, 4)[0]
    first = struct.unpack_from("<I", data, 8)[0]
    flags = next((r[3] for r in records(b) if r[0] == like), 0x200)
    assert first + 16 * count == len(data), "unexpected effect.bin layout"
    # new strings at the end of the string table
    name_off = len(strings)
    strings += name.encode("cp932") + b"\0"
    file_off = name_off
    if file != name:
        file_off = len(strings)
        strings += file.encode("cp932") + b"\0"
    rec = len(data)
    data += struct.pack("<4I", 0, 0, 0, flags)
    struct.pack_into("<I", data, 4, count + 1)
    new_ptrs = ptrs + [rec, rec + 4]
    new_labels = labels + [(rec, name_off)]
    # the strings move by the growth of the data and the two tables
    shift = 16 + 4 * 2 + 8
    pset = set(ptrs)
    for p in ptrs:
        v = struct.unpack_from("<I", data, p)[0]
        if v >= sbase:  # pointers into the strings (the others point into the data)
            struct.pack_into("<I", data, p, v + shift)
    new_sbase = sbase + shift
    struct.pack_into("<I", data, rec, new_sbase + name_off)
    struct.pack_into("<I", data, rec + 4, new_sbase + file_off)
    assert rec not in pset
    out = bytearray()
    out += struct.pack("<4I", 0, len(data), len(new_ptrs), len(new_labels)) + b"\0" * 16
    out += data
    for p in new_ptrs:
        out += struct.pack("<I", p)
    for a, n in new_labels:
        out += struct.pack("<II", a, n)
    out += strings
    struct.pack_into("<I", out, 0, len(out))
    return bytes(out)


def tinted(cgfx: bytes, color: Tuple[int, int, int] = RED) -> bytes:
    """The effect's textures tinted to `color` (brightness and transparency kept)."""
    from PIL import Image

    from paragon import paragon as pgn
    from paragon.unlimited.models import model_textures as mt

    layers = {t.filename: t for t in pgn.read_cgfx(cgfx)}
    out = cgfx
    for info in mt.textures(cgfx):
        t = layers.get(info.name)
        if t is None:
            continue
        im = Image.frombytes("RGBA", (t.width, t.height), bytes(t.pixel_data))
        r, g, b, a = im.split()
        lum = Image.merge("RGB", (r, g, b)).convert("L")
        # white stays a bright pink-white in the middle of the light, everything else takes the color
        tint = Image.merge("RGB", [lum.point(lambda v, c=c: min(255, int(v * c / 255 + max(0, v - 200) * 0.8)))
                                   for c in color])
        out = mt.replace_texture(out, info.name, Image.merge("RGBA", (*tint.split(), a)))
    return out


def strip_added(b: bytes, prefix: str = "PU_") -> bytes:
    """effect.bin without the records an earlier version appended (their names start with
    `prefix`); the result is the list as it was before (same bytes)."""
    recs = records(b)
    keep = len(recs)
    while keep and recs[keep - 1][0].startswith(prefix):
        keep -= 1
    if keep == len(recs):
        return b
    data, ptrs, labels, strings, sbase = _parse(b)
    first = struct.unpack_from("<I", data, 8)[0]
    end = first + 16 * keep
    removed_ptrs = [p for p in ptrs if p >= end]
    removed_labels = [l for l in labels if l[0] >= end]
    cut = min(o for _a, o in removed_labels)  # their strings are the last ones
    shift = 16 * (len(recs) - keep) + 4 * len(removed_ptrs) + 8 * len(removed_labels)
    data = bytearray(data[:end])
    struct.pack_into("<I", data, 4, keep)
    kept_ptrs = [p for p in ptrs if p < end]
    for p in kept_ptrs:
        v = struct.unpack_from("<I", data, p)[0]
        if v >= sbase:
            struct.pack_into("<I", data, p, v - shift)
    out = bytearray(struct.pack("<4I", 0, len(data), len(kept_ptrs), len(labels) - len(removed_labels)) + b"\0" * 16)
    out += data
    for p in kept_ptrs:
        out += struct.pack("<I", p)
    for a, n in labels:
        if a < end:
            out += struct.pack("<II", a, n)
    out += strings[:cut]
    struct.pack_into("<I", out, 0, len(out))
    return bytes(out)


def ensure(gd, files: dict, read_file) -> bool:
    """Put the red event sparkle in the project (in `files`: path -> decompressed contents).
    read_file(path) -> plain bytes or None. Returns True when something was added or repaired."""
    changed = False
    lst = files.get(LIST) or read_file(LIST)
    if lst is not None and has_effect(lst, OLD_EFFECT):
        files[LIST] = strip_added(lst)  # the game's list as it was (a longer list breaks every effect)
        changed = True
    cur = files.get(FILE) or read_file(FILE)
    base = read_file(f"effect/{BASE}.bcres.lz")
    if base is not None and (cur is None or not _is_ours(cur)):
        files[FILE] = tinted(base)
        changed = True
    return changed


def _is_ours(cgfx: bytes) -> bool:
    """The file is the sparkle (the game's own スポット異界の門 is a different model)."""
    return b"EFF_BMP_REWARD1" in cgfx
