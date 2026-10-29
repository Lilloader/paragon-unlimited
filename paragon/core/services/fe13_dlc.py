"""Paragon Unlimited - edit Fire Emblem Awakening DLC maps (E001-E027) like normal chapters.

How the DLC is built
--------------------
Each DLC episode is one content of title 0004008C000A0500. Its RomFS holds Exxx_MAP.arc
(plus _GLB/_SND/_SNL). Exxx_MAP.arc is a mini file system with the chapter stored under the
generic name E000: data/dispos/E000.bin.lz, data/person/E000.bin.lz, scripts/E000.cmb,
m/E/E000.bin.lz, ...  The game mounts the arc of the episode you play as chapter E000.

What Paragon Unlimited does
---------------------------
Workspace next to the project output folder:  <output>_DLC/
    original/Exxx_MAP.arc   untouched copies (from the DLC .cia or a folder of arcs)
    unpacked/               the chapter files renamed E000 -> Exxx; added to Paragon as an
                            extra read-only layer, so every DLC map opens like a chapter
    romfs/Exxx_MAP.arc      rebuilt on save from original + your edits; copy this folder's
                            contents to  Azahar/load/mods/0004008C000A0500/romfs/
Edits are saved by Paragon as normal files (data/dispos/E001.bin.lz, ...) in the output folder.
The game itself never sees those loose files; it only reads the rebuilt arcs.
"""
import json
import logging
import os
import re
import struct
from pathlib import Path
from typing import Dict, List, Optional

from paragon.core.services.fe13_portrait_shift import parse_arc, build_arc

DLC_ARC_ALIGN = 0x20
EPISODE_RE = re.compile(r"^(E\d{3})_MAP\.arc$", re.IGNORECASE)
# Chapter files inside a MAP arc that Paragon edits (E000 is replaced by the episode id).
EDITABLE = [
    re.compile(r"^data/dispos/E000\.bin\.lz$"),
    re.compile(r"^data/person/E000\.bin\.lz$"),
    re.compile(r"^data/terrain/E000\.bin\.lz$"),
    re.compile(r"^data/landscape/E000\.bin\.lz$"),
    re.compile(r"^map/data/E000\.bin$"),
    re.compile(r"^m/[^/]+/E000\.bin\.lz$"),
    re.compile(r"^scripts/E000\.cmb$"),
    re.compile(r"^scripts/E000_Terrain\.cmb$"),
]


def workspace(output_path: str) -> Path:
    return Path(str(output_path).rstrip("/\\") + "_DLC")


def unpacked_layer(output_path: str) -> Optional[str]:
    p = workspace(output_path) / "unpacked"
    return str(p) if p.is_dir() else None


def _editable(name: str) -> bool:
    return any(r.match(name) for r in EDITABLE)


def _renamed(name: str, ep: str) -> str:
    return name.replace("E000", ep)


# ----------------------------------------------------------------------------- CIA reading


def _ncch_romfs_files(f, base):
    """Yield (path, bytes) from a decrypted NCCH's RomFS."""
    f.seek(base)
    h = f.read(0x200)
    if h[0x100:0x104] != b"NCCH":
        raise ValueError("Not an NCCH content")
    flags = h[0x188:0x190]
    if not (flags[7] & 0x4):
        raise ValueError("This DLC is encrypted. Please use a decrypted DLC .cia.")
    mu = 0x200
    romfs_off = base + struct.unpack_from("<I", h, 0x1B0)[0] * mu
    romfs_size = struct.unpack_from("<I", h, 0x1B4)[0] * mu
    if not romfs_size:
        return
    f.seek(romfs_off)
    ivfc = f.read(0x60)
    if ivfc[:4] != b"IVFC":
        raise ValueError("Bad RomFS")
    mhs = struct.unpack_from("<I", ivfc, 0x08)[0]
    bs3 = struct.unpack_from("<I", ivfc, 0x4C)[0]
    l3 = romfs_off + ((0x60 + mhs + (1 << bs3) - 1) // (1 << bs3)) * (1 << bs3)
    f.seek(l3)
    v = struct.unpack("<10I", f.read(0x28))
    f.seek(l3 + v[3])
    dm = f.read(v[4])
    f.seek(l3 + v[7])
    fm = f.read(v[8])
    data_off = l3 + v[9]

    def walk(doff, path):
        _p, _s, child, ffile, _h, nlen = struct.unpack_from("<6I", dm, doff)
        name = dm[doff + 0x18 : doff + 0x18 + nlen].decode("utf-16le")
        p = (path + "/" + name) if doff else ""
        fo = ffile
        while fo != 0xFFFFFFFF:
            _p2, sib, do, sz, _h2, nl = struct.unpack_from("<IIQQII", fm, fo)
            fn = fm[fo + 0x20 : fo + 0x20 + nl].decode("utf-16le")
            f.seek(data_off + do)
            yield (p + "/" + fn).lstrip("/"), f.read(sz)
            fo = sib
        c = child
        while c != 0xFFFFFFFF:
            yield from walk(c, p)
            c = struct.unpack_from("<I", dm, c + 4)[0]

    yield from walk(0, "")


def arcs_from_cia(cia_path: str) -> Dict[str, bytes]:
    """{'E001_MAP.arc': bytes, ...} from a decrypted DLC .cia."""
    al = lambda x: (x + 63) & ~63
    out = {}
    with open(cia_path, "rb") as f:
        hs, _t, _v, cs, ts, tmds, _ms, _csz = struct.unpack("<IHHIIIIQ", f.read(0x20))
        off_tmd = al(al(al(hs) + cs) + ts)
        pos = al(off_tmd + tmds)
        f.seek(off_tmd)
        tmd = f.read(tmds)
        sig = struct.unpack(">I", tmd[:4])[0]
        hdr = {0x10003: 0x240, 0x10004: 0x140, 0x10005: 0x80}.get(sig)
        if hdr is None:
            raise ValueError("Unknown TMD signature type")
        count = struct.unpack(">H", tmd[hdr + 0x9E : hdr + 0xA0])[0]
        rec = hdr + 0xC4 + 0x900
        for i in range(count):
            _cid, _idx, _ctype, size = struct.unpack(">IHHQ", tmd[rec : rec + 16])
            rec += 0x30
            try:
                for name, data in _ncch_romfs_files(f, pos):
                    if EPISODE_RE.match(os.path.basename(name)):
                        out[os.path.basename(name)] = data
            except ValueError as e:
                if "encrypted" in str(e):
                    raise
                logging.info(f"DLC content {i}: {e}")
            pos += size
    return out


# ----------------------------------------------------------------------------- workspace


def import_arcs(output_path: str, arcs: Dict[str, bytes]) -> List[str]:
    """Store original MAP arcs and unpack them. Returns the episode ids."""
    ws = workspace(output_path)
    (ws / "original").mkdir(parents=True, exist_ok=True)
    for name, data in arcs.items():
        if EPISODE_RE.match(name):
            (ws / "original" / name).write_bytes(data)
    return unpack(output_path)


def import_from_folder(output_path: str, folder: str) -> List[str]:
    arcs = {}
    for root, _dirs, files in os.walk(folder):
        for fn in files:
            if EPISODE_RE.match(fn):
                arcs[fn] = Path(root, fn).read_bytes()
    return import_arcs(output_path, arcs)


def episodes(output_path: str) -> List[dict]:
    ws = workspace(output_path)
    try:
        return json.loads((ws / "episodes.json").read_text(encoding="utf-8"))
    except Exception:
        return []


def _title_from_text(raw_lz: bytes) -> Optional[str]:
    try:
        from paragon import paragon as pgn

        t = bytes(pgn.decompress_lz13(raw_lz))
        # FE13 text archive: title string, then the first message (UTF-16) = chapter name.
        start = 0x20 + t[0x20:].index(b"\0")
        while start < len(t) and t[start] == 0:
            start += 1
        if start % 2:
            start += 1
        end = start
        while end + 1 < len(t) and t[end : end + 2] != b"\0\0":
            end += 2
        s = t[start:end].decode("utf-16le", errors="ignore").strip()
        return s if 0 < len(s) < 60 else None
    except Exception:
        return None


def unpack(output_path: str) -> List[str]:
    ws = workspace(output_path)
    eps = []
    for arc in sorted((ws / "original").glob("*_MAP.arc")):
        m = EPISODE_RE.match(arc.name)
        if not m:
            continue
        ep = m.group(1).upper()
        title = None
        for name, _idx, blob in parse_arc(arc.read_bytes()):
            if not _editable(name):
                continue
            dest = ws / "unpacked" / _renamed(name, ep)
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(blob)
            if name.startswith("m/") and title is None:
                title = _title_from_text(blob)
        eps.append({"id": ep, "arc": arc.name, "name": title or ep})
    (ws / "episodes.json").write_text(json.dumps(eps, ensure_ascii=False, indent=1), encoding="utf-8")
    return [e["id"] for e in eps]


def _fix_cmb_name(blob: bytes, ep: str) -> bytes:
    """Compiled scripts store their own file name; inside the arc it must stay E000."""
    for suffix in (".cmb", "_Terrain.cmb"):
        new = (ep + suffix).encode()
        old = ("E000" + suffix).encode()
        i = blob.find(new, 0, 0x80)
        if i >= 0:
            blob = blob[:i] + old + blob[i + len(new):]
    return blob


def repack(output_path: str) -> List[str]:
    """Rebuild every MAP arc that has edited files in the output folder. Returns written paths."""
    ws = workspace(output_path)
    written = []
    out_root = Path(output_path)
    for ep_info in episodes(output_path):
        ep = ep_info["id"]
        src = ws / "original" / ep_info["arc"]
        if not src.exists():
            continue
        entries = parse_arc(src.read_bytes())
        changed = False
        new_entries = []
        for name, idx, blob in entries:
            if _editable(name):
                rel = _renamed(name, ep)
                edited = out_root / rel
                if not edited.exists() and rel.startswith("scripts/"):
                    edited = out_root / ("Scripts/" + rel[len("scripts/"):])  # Paragon writes "Scripts"
                if edited.exists():
                    nb = edited.read_bytes()
                    if name.endswith(".cmb"):
                        nb = _fix_cmb_name(nb, ep)
                    if nb != blob:
                        blob = nb
                        changed = True
            new_entries.append((name, idx, blob))
        dest = ws / "romfs" / ep_info["arc"]
        if changed:
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(build_arc(new_entries, DLC_ARC_ALIGN))
            written.append(str(dest))
        elif dest.exists():
            dest.unlink()  # edits were undone: the original DLC file is used again
    return written


def is_dlc_cid(cid: str) -> bool:
    return bool(re.match(r"^CID_E\d{3}$", cid or "")) and cid != "CID_E000"
