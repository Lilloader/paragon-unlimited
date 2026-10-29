"""Paragon Unlimited: replace battle-model textures (b/<name>.t.lz, CGFX) with your own images.

A texture file holds one or more textures (TXOB). Importing an image re-encodes it in the
texture's own size and format (ETC1, ETC1A4, RGB565 or RGBA8) together with its mipmaps, so
the file layout stays exactly the same. Changes are queued and written when the project is
saved; the previous output file is backed up first.
"""
import datetime
import logging
import os
import struct
import time
import zipfile
from dataclasses import dataclass
from typing import Dict, List, Optional

from paragon.core.services.fe13_portrait_shift import encode_rgba8, _MORTON

ETC1, ETC1A4, RGB565, RGBA8 = 12, 13, 3, 0
BITS = {ETC1: 4, ETC1A4: 8, RGB565: 16, RGBA8: 32}
FORMAT_NAMES = {ETC1: "ETC1 (no transparency)", ETC1A4: "ETC1A4", RGB565: "RGB565 (no transparency)", RGBA8: "RGBA8"}


@dataclass
class TextureInfo:
    name: str
    width: int
    height: int
    mips: int
    fmt: int
    size: int
    data_offset: int


def _u32(d, o):
    return struct.unpack_from("<I", d, o)[0]


def _rel(d, o):
    v = _u32(d, o)
    return o + v if v else 0


def _string(d, o):
    p = _rel(d, o)
    return d[p : d.index(b"\0", p)].decode("utf-8", errors="replace") if p else None


def textures(cgfx: bytes) -> List[TextureInfo]:
    if cgfx[:4] != b"CGFX":
        raise ValueError("Not a CGFX file")
    out = []
    dict_off = _rel(cgfx, 0x14 + 0x0C + 8)  # DATA entry 1 = textures
    if not dict_off:
        return out
    for i in range(_u32(cgfx, dict_off + 8)):
        e = dict_off + 0x1C + i * 0x10
        name, o = _string(cgfx, e + 8), _rel(cgfx, e + 12)
        if cgfx[o + 4 : o + 8] != b"TXOB":
            continue
        out.append(
            TextureInfo(
                name=name,
                height=_u32(cgfx, o + 0x18),
                width=_u32(cgfx, o + 0x1C),
                mips=max(1, _u32(cgfx, o + 0x28)),
                fmt=_u32(cgfx, o + 0x34),
                size=_u32(cgfx, o + 0x44),
                data_offset=_rel(cgfx, o + 0x48),
            )
        )
    return out


def encode_rgb565(rgba: bytes, w: int, h: int) -> bytes:
    out = bytearray(w * h * 2)
    tiles_per_row = w // 8
    for y in range(h):
        ty, iy = divmod(y, 8)
        for x in range(w):
            tx, ix = divmod(x, 8)
            o = ((ty * tiles_per_row + tx) * 64 + _MORTON[iy * 8 + ix]) * 2
            i = (y * w + x) * 4
            r, g, b = rgba[i], rgba[i + 1], rgba[i + 2]
            struct.pack_into("<H", out, o, ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3))
    return bytes(out)


def encode_level(rgba: bytes, w: int, h: int, fmt: int) -> bytes:
    from paragon import paragon as pgn

    if fmt in (ETC1, ETC1A4):
        return bytes(pgn.encode_etc1(rgba, w, h, fmt == ETC1A4))
    if fmt == RGB565:
        return encode_rgb565(rgba, w, h)
    if fmt == RGBA8:
        return encode_rgba8(rgba, w, h)
    raise ValueError(f"Texture format {fmt} is not supported for import.")


def encode_with_mips(img, info: TextureInfo) -> bytes:
    """PIL image (any size) -> pixel data for all mip levels of `info`."""
    from PIL import Image

    img = img.convert("RGBA")
    if img.size != (info.width, info.height):
        img = img.resize((info.width, info.height), Image.LANCZOS)
    data = bytearray()
    for level in range(info.mips):
        w, h = max(8, info.width >> level), max(8, info.height >> level)
        lvl = img if (w, h) == img.size else img.resize((w, h), Image.LANCZOS)
        data += encode_level(lvl.tobytes(), w, h, info.fmt)
    if len(data) != info.size:
        raise ValueError(f"Encoded size {len(data)} does not match the texture ({info.size}).")
    return bytes(data)


def replace_texture(cgfx: bytes, name: str, img) -> bytes:
    info = next((t for t in textures(cgfx) if t.name == name), None)
    if info is None:
        raise ValueError(f"{name} is not in this texture file.")
    pixels = encode_with_mips(img, info)
    return cgfx[: info.data_offset] + pixels + cgfx[info.data_offset + info.size :]


class ModelTextureEdits:
    """Imported battle-model textures, written on save. Keyed by file path (b/<x>.t.lz)."""

    def __init__(self, gd):
        self.gd = gd
        self.pending: Dict[str, bytes] = {}  # path -> new decompressed CGFX
        self.listeners = []

    def path_for(self, name: str) -> str:
        return f"b/{name}.t.lz"

    def current(self, path: str) -> bytes:
        if path in self.pending:
            return self.pending[path]
        raw = bytes(self.gd.read_file(path))  # read_file returns .lz files decompressed
        if raw[:4] != b"CGFX" and raw[:1] in (b"\x10", b"\x11", b"\x13"):
            from paragon import paragon as pgn

            raw = bytes(pgn.decompress_lz13(raw))
        return raw

    def info(self, name: str) -> Optional[TextureInfo]:
        try:
            return next((t for t in textures(self.current(self.path_for(name))) if t.name == name), None)
        except Exception:
            return None

    def import_image(self, name: str, image_path: str) -> str:
        from PIL import Image

        path = self.path_for(name)
        cgfx = self.current(path)
        img = Image.open(image_path)
        info = next((t for t in textures(cgfx) if t.name == name), None)
        if info is None:
            raise ValueError(f"{name} is not in {path}.")
        self.pending[path] = replace_texture(cgfx, name, img)
        notes = []
        if img.size != (info.width, info.height):
            notes.append(f"resized from {img.size[0]}x{img.size[1]}")
        if info.fmt in (ETC1, RGB565) and img.mode in ("RGBA", "LA", "P") and img.convert("RGBA").getextrema()[3][0] < 255:
            notes.append("transparency dropped: this texture has none")
        extra = f" ({', '.join(notes)})" if notes else ""
        return f"{name}: {info.width}x{info.height} {FORMAT_NAMES.get(info.fmt, info.fmt)}{extra}."

    def revert(self, name: str):
        self.pending.pop(self.path_for(name), None)

    def is_pending(self, name: str) -> bool:
        return self.path_for(name) in self.pending

    def has_pending(self) -> bool:
        return bool(self.pending)

    def flush(self, output_path: Optional[str] = None) -> List[str]:
        if not self.pending:
            return []
        lines = []
        backup = None
        for path, cgfx in list(self.pending.items()):
            if output_path:
                existing = os.path.join(output_path, path)
                if os.path.exists(existing):
                    if backup is None:
                        os.makedirs("Backups", exist_ok=True)
                        stamp = datetime.datetime.fromtimestamp(time.time()).strftime("%Y_%m_%d_%H_%M_%S")
                        backup = zipfile.ZipFile(os.path.join("Backups", f"textures-before-{stamp}.zip"), "w", zipfile.ZIP_DEFLATED)
                    backup.write(existing, path)
            self.gd.write_file(path, cgfx)  # compressed automatically (.lz)
            lines.append(path)
            del self.pending[path]
        if backup:
            backup.close()
        for cb in list(self.listeners):
            try:
                cb()
            except Exception:
                logging.exception("Texture refresh failed.")
        logging.info("Model textures written: " + ", ".join(lines))
        return lines


def edits_for(gs) -> ModelTextureEdits:
    edits = getattr(gs, "pu_texture_edits", None)
    if edits is None:
        edits = ModelTextureEdits(gs.data)
        gs.pu_texture_edits = edits
    return edits
