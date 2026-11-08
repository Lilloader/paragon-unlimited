"""Paragon Unlimited: pack a mod into one zip that other players can install.

The zip holds exactly what the game needs, in Azahar's mod folder layout:

    <Mod name>/HOW_TO_INSTALL.txt
    <Mod name>/00040000000A0500/romfs/...      changed game files (from the project's output folder)
    <Mod name>/00040000000A0500/code.ips       the game code patch (60 supports, skill effects, ...)
    <Mod name>/0004008C000A0500/romfs/...      rebuilt DLC maps, when there are any

Files that are byte-identical to the original game are left out (the player has them already),
and so are Paragon's own working files (script sources, backups, logs).
"""
import datetime
import json
import os
import zipfile
from dataclasses import dataclass, field
from typing import Callable, List, Optional, Tuple

from paragon.unlimited.tools.azahar import BASE_TITLE, DLC_TITLE, SKIP_NAMES, SKIP_SUFFIXES

# Folders of the output folder that are Paragon's, not the game's.
PARAGON_DIRS = {"exalt"}
INFO_FILE = "share_info.json"  # remembered name / author / description (next to the output folder)


@dataclass
class SharePlan:
    files: List[Tuple[str, str]] = field(default_factory=list)  # (source path, path inside the zip)
    same_as_game: int = 0
    total_bytes: int = 0
    has_dlc: bool = False
    has_code: bool = False
    code_bytes: Optional[bytes] = None  # the code.ips, written into the zip as CODE_ARC

    def summary(self) -> str:
        mb = self.total_bytes / (1024 * 1024)
        parts = [f"{len(self.files) + bool(self.code_bytes)} file(s), {mb:.1f} MB before zipping"]
        if self.same_as_game:
            parts.append(f"{self.same_as_game} unchanged game file(s) left out")
        if self.has_dlc:
            parts.append("DLC maps included")
        if self.has_code:
            parts.append("game code patch (code.ips) included")
        return "; ".join(parts)


def safe_name(name: str) -> str:
    keep = "".join(c for c in (name or "").strip() if c not in '\\/:*?"<>|').strip(". ")
    return keep or "My Awakening Mod"


def _same(a: str, b: str) -> bool:
    if os.path.getsize(a) != os.path.getsize(b):
        return False
    with open(a, "rb") as fa, open(b, "rb") as fb:
        while True:
            x, y = fa.read(1 << 20), fb.read(1 << 20)
            if x != y:
                return False
            if not x:
                return True


def _wanted(name: str) -> bool:
    return name not in SKIP_NAMES and not name.lower().endswith(SKIP_SUFFIXES)


def find_code_ips(mod_root: Optional[str]) -> Optional[str]:
    """The game code patch in Azahar's mod folder (mods/00040000000A0500/code.ips or
    .../exefs/code.ips), if any."""
    from paragon.unlimited.tools.code_patch import installed_paths

    found = installed_paths(mod_root)
    return found[0] if found else None


CODE_ARC = f"{BASE_TITLE}/code.ips"  # where Azahar (and Luma) read it; Paragon looks there too


def plan(output_path: str, rom_path: Optional[str], dlc_romfs: Optional[str] = None,
         code_ips=None, name: str = "", progress: Optional[Callable[[str], None]] = None) -> SharePlan:
    progress = progress or (lambda s: None)
    top = safe_name(name)
    res = SharePlan()

    def add(src, arc):
        res.files.append((src, arc))
        res.total_bytes += os.path.getsize(src)

    if output_path and os.path.isdir(output_path):
        for root, dirs, files in os.walk(output_path):
            rel_root = os.path.relpath(root, output_path)
            if rel_root == ".":
                dirs[:] = [d for d in dirs if d.lower() not in PARAGON_DIRS and not d.startswith(".")]
            else:
                dirs[:] = [d for d in dirs if not d.startswith(".")]
            for fn in sorted(files):
                if not _wanted(fn):
                    continue
                src = os.path.join(root, fn)
                rel = os.path.relpath(src, output_path).replace("\\", "/")
                progress(f"Checking {rel}")
                if rom_path:
                    orig = os.path.join(rom_path, *rel.split("/"))
                    if os.path.isfile(orig) and _same(src, orig):
                        res.same_as_game += 1
                        continue
                add(src, f"{top}/{BASE_TITLE}/romfs/{rel}")
    if dlc_romfs and os.path.isdir(dlc_romfs):
        for root, _dirs, files in os.walk(dlc_romfs):
            for fn in sorted(files):
                if _wanted(fn):
                    src = os.path.join(root, fn)
                    rel = os.path.relpath(src, dlc_romfs).replace("\\", "/")
                    add(src, f"{top}/{DLC_TITLE}/romfs/{rel}")
                    res.has_dlc = True
    if isinstance(code_ips, (bytes, bytearray)) and code_ips:
        res.code_bytes = bytes(code_ips)
    elif code_ips and os.path.isfile(code_ips):
        with open(code_ips, "rb") as f:
            res.code_bytes = f.read()
    if res.code_bytes:
        res.has_code = True
        res.total_bytes += len(res.code_bytes)
    return res


def install_text(name: str, author: str, description: str, p: SharePlan, version: str) -> str:
    lines = [name]
    if author:
        lines.append(f"by {author}")
    lines.append("")
    if description:
        lines += [description.strip(), ""]
    lines += [
        "A mod for Fire Emblem Awakening (North American version), made with Paragon Unlimited "
        f"{version}.",
        "",
        "HOW TO INSTALL (Azahar)",
        "1. In Azahar, right-click Fire Emblem Awakening and choose \"Open Mods Location\".",
        f"2. Copy the folder 00040000000A0500 from this zip into that folder.",
    ]
    step = 3
    if p.has_dlc:
        lines.append(f"{step}. Also copy the folder 0004008C000A0500 (the DLC maps) into the same place.")
        step += 1
    lines += [
        f"{step}. Start the game. That's it.",
        "",
        "If a folder with the same name is already there, Windows asks whether to merge it: say yes.",
        "To remove the mod, delete those folders again.",
        "",
    ]
    if p.has_code:
        lines += [
            "This mod also changes the game's code (00040000000A0500/code.ips): 60 support partners,",
            "skill effects and room for 4096 support conversations. It is made for the North American",
            "version 1.0 of the game. If Windows asks to replace a code.ips from another mod, say yes:",
            "this mod needs its own (the other mod's code changes then stop working).",
            "",
        ]
    lines += [
        "Start a new save file when the mod adds characters, chapters or supports.",
        "",
        f"Packed on {datetime.date.today().isoformat()}: {p.summary()}.",
    ]
    return "\r\n".join(lines) + "\r\n"


def make_zip(p: SharePlan, zip_path: str, name: str, author: str = "", description: str = "",
             version: str = "", progress: Optional[Callable[[str], None]] = None) -> str:
    progress = progress or (lambda s: None)
    top = safe_name(name)
    tmp = zip_path + ".part"
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        z.writestr(f"{top}/HOW_TO_INSTALL.txt", install_text(top, author, description, p, version))
        if p.code_bytes:
            z.writestr(f"{top}/{CODE_ARC}", p.code_bytes)
        for k, (src, arc) in enumerate(p.files):
            progress(f"Packing {k + 1} / {len(p.files)}: {arc.split('/', 1)[-1]}")
            z.write(src, arc)
    with zipfile.ZipFile(tmp) as z:  # read it back before calling it done
        bad = z.testzip()
        if bad:
            raise IOError(f"The zip is damaged ({bad}).")
        if len(z.namelist()) != len(p.files) + 1 + bool(p.code_bytes):
            raise IOError("Not every file made it into the zip.")
    os.replace(tmp, zip_path)
    return zip_path


def load_info(output_path: str) -> dict:
    try:
        with open(os.path.join(os.path.dirname(os.path.abspath(output_path)), INFO_FILE), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_info(output_path: str, info: dict):
    try:
        with open(os.path.join(os.path.dirname(os.path.abspath(output_path)), INFO_FILE), "w", encoding="utf-8") as f:
            json.dump(info, f, ensure_ascii=False, indent=2)
    except Exception:
        pass
