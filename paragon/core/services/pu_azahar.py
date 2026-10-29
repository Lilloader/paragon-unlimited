"""Paragon Unlimited: copy the project's output into Azahar's mod folders in one click.

    <output folder>/...            -> <mods>/00040000000A0500/romfs/...   (base game)
    <output>_DLC/romfs/E*_MAP.arc  -> <mods>/0004008C000A0500/romfs/      (DLC maps)

Only files that differ are copied. Files in Azahar that are replaced are first stored in
Backups/azahar-before-<time>.zip. Nothing is ever deleted from the mod folder.
"""
import datetime
import os
import shutil
import time
import zipfile
from dataclasses import dataclass, field
from typing import Callable, List, Optional

BASE_TITLE = "00040000000A0500"
DLC_TITLE = "0004008C000A0500"
SKIP_NAMES = {"Thumbs.db", "desktop.ini", ".DS_Store"}
SKIP_SUFFIXES = (".bak", ".tmp", ".log")


def candidate_mod_roots() -> List[str]:
    """Usual places of the emulator's load/mods folder (Azahar first)."""
    out = []
    bases = []
    if os.name == "nt":
        appdata = os.environ.get("APPDATA")
        if appdata:
            bases.append(appdata)
    else:
        home = os.path.expanduser("~")
        bases += [os.path.join(home, ".local", "share"), os.path.join(home, "Library", "Application Support")]
    for base in bases:
        for emu in ("Azahar", "azahar-emu", "Lime3DS", "Citra", "citra-emu"):
            out.append(os.path.join(base, emu, "load", "mods"))
    return out


def detect_mod_root() -> Optional[str]:
    for path in candidate_mod_roots():
        if os.path.isdir(path):
            return path
    # Azahar installed but no mods folder yet: offer the standard place.
    for path in candidate_mod_roots():
        if os.path.isdir(os.path.dirname(os.path.dirname(path))):
            return path
    return None


def normalize_mod_root(path: str) -> str:
    """Accept .../load/mods, .../mods/<title>, or .../mods/<title>/romfs."""
    p = os.path.normpath(path)
    if os.path.basename(p).lower() == "romfs":
        p = os.path.dirname(p)
    if os.path.basename(p).upper() in (BASE_TITLE, DLC_TITLE):
        p = os.path.dirname(p)
    return p


@dataclass
class CopyResult:
    copied: List[str] = field(default_factory=list)
    unchanged: int = 0
    backup: Optional[str] = None
    destinations: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)
    renamed: List[str] = field(default_factory=list)

    def summary(self) -> str:
        lines = [f"Copied {len(self.copied)} changed file(s); {self.unchanged} were already up to date."]
        if self.renamed:
            lines.append(
                f"Fixed the letter case of {len(self.renamed)} file name(s) in the mod folder "
                "(the game needs the exact name):"
            )
            lines += ["  " + r for r in self.renamed[:15]]
            if len(self.renamed) > 15:
                lines.append(f"  ... and {len(self.renamed) - 15} more")
        if self.copied:
            shown = self.copied[:15]
            lines += ["  " + c for c in shown]
            if len(self.copied) > len(shown):
                lines.append(f"  ... and {len(self.copied) - len(shown)} more")
        if self.backup:
            lines.append(f"Replaced files were backed up to {self.backup}")
        lines += self.notes
        lines.append("To: " + "; ".join(self.destinations))
        return "\n".join(lines)


def _same_content(a: str, b: str) -> bool:
    """Byte comparison (no caching: filecmp's cache can go stale within one second)."""
    with open(a, "rb") as fa, open(b, "rb") as fb:
        while True:
            x, y = fa.read(1 << 20), fb.read(1 << 20)
            if x != y:
                return False
            if not x:
                return True


def _wanted(name: str) -> bool:
    return name not in SKIP_NAMES and not name.lower().endswith(SKIP_SUFFIXES)


def _plan(src_root: str, dst_root: str, renamed: Optional[List[str]] = None):
    """[(src, dst, rel)] of files that are new or different. A file in the mod folder whose name
    differs from the project's only in letter case is renamed first (Windows keeps the old case
    when a file is copied over it, but the game looks names up exactly)."""
    from paragon.core.services import pu_file_case

    pu_file_case.clear_cache()
    todo, same = [], 0
    for root, dirs, files in os.walk(src_root):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for fn in files:
            if not _wanted(fn):
                continue
            src = os.path.join(root, fn)
            rel = os.path.relpath(src, src_root)
            dst = os.path.join(dst_root, rel)
            if os.path.exists(dst) and pu_file_case.match_destination_case(src, dst):
                if renamed is not None:
                    renamed.append(rel.replace("\\", "/"))
            if os.path.exists(dst) and os.path.getsize(dst) == os.path.getsize(src) and _same_content(src, dst):
                same += 1
                continue
            todo.append((src, dst, rel))
    return todo, same


def copy_to_mods(output_path: str, mod_root: str, dlc_romfs: Optional[str] = None,
                 backups_dir: str = "Backups", progress: Optional[Callable[[str], None]] = None) -> CopyResult:
    progress = progress or (lambda s: None)
    res = CopyResult()
    mod_root = normalize_mod_root(mod_root)
    jobs = []
    base_dst = os.path.join(mod_root, BASE_TITLE, "romfs")
    if os.path.isdir(output_path):
        if os.path.normcase(os.path.abspath(output_path)) == os.path.normcase(os.path.abspath(base_dst)):
            res.notes.append("Your output folder already is Azahar's mod folder; nothing to copy for the base game.")
        else:
            jobs.append((output_path, base_dst))
            res.destinations.append(base_dst)
    if dlc_romfs and os.path.isdir(dlc_romfs) and os.listdir(dlc_romfs):
        dlc_dst = os.path.join(mod_root, DLC_TITLE, "romfs")
        jobs.append((dlc_romfs, dlc_dst))
        res.destinations.append(dlc_dst)

    plans = []
    for src, dst in jobs:
        progress(f"Comparing {src} ...")
        todo, same = _plan(src, dst, res.renamed)
        res.unchanged += same
        plans.append(todo)

    replaced = [(d, rel) for todo in plans for (_s, d, rel) in todo if os.path.exists(d)]
    if replaced:
        os.makedirs(backups_dir, exist_ok=True)
        stamp = datetime.datetime.fromtimestamp(time.time()).strftime("%Y_%m_%d_%H_%M_%S")
        res.backup = os.path.abspath(os.path.join(backups_dir, f"azahar-before-{stamp}.zip"))
        with zipfile.ZipFile(res.backup, "w", zipfile.ZIP_DEFLATED) as z:
            for d, rel in replaced:
                z.write(d, os.path.relpath(d, mod_root))

    for todo in plans:
        for src, dst, rel in todo:
            progress(f"Copying {rel}")
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(src, dst)
            res.copied.append(rel.replace("\\", "/"))
    return res
