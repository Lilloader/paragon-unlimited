"""Paragon Unlimited: the game code patch (code.ips) for Fire Emblem Awakening (NA, v1.0).

Data/FE13/PU_CodePatch.ips holds only Paragon Unlimited's own changes to the game's code:

- 60 support partners per character (the extra slots #052-#059 live in the PU_SupportEx2
  table that Paragon writes into data/person/static.bin),
- skill effects (the effect lines Paragon writes for each skill),
- room for 4096 support conversations instead of 1920 (0x108B30: movne r1, #0x1000),
- 5 reclass classes per gender (slots 4-5 in the PU_ClassEx table in data/person/static.bin),
  the avatar class list from the PU_AvatarCls table in data/GameData.bin, and a 64-class limit
  for Second Seal lists.

Azahar reads the patch from mods/00040000000A0500/code.ips (or .../exefs/code.ips).
Another mod may already have a code.ips there, so installing *merges*: records of other
patches are kept as they are, records at the places Paragon Unlimited patches (including older
Paragon Unlimited versions) are replaced, and the old file is kept as a backup next to it.
"""
import datetime
import hashlib
import os
import shutil
from typing import List, Optional, Tuple

BASE_TITLE = "00040000000A0500"
CODE_BASE = 0x100000  # code.bin is loaded at 0x100000; IPS offsets are file offsets
PATCH_FILE = os.path.join("Data", "FE13", "PU_CodePatch.ips")
GAME = "Fire Emblem Awakening, North American version 1.0 (00040000000A0500)"

Record = Tuple[int, bytes]


# ---------------------------------------------------------------------- IPS
def parse_ips(data: bytes) -> List[Record]:
    """(offset, bytes) for every record; RLE records are expanded."""
    if data[:5] != b"PATCH":
        raise ValueError("Not an IPS patch (it does not start with PATCH).")
    p, out = 5, []
    while True:
        if p + 3 > len(data):
            raise ValueError("The IPS patch is cut off (no EOF).")
        if data[p:p + 3] == b"EOF" and len(data) - (p + 3) in (0, 3):
            return out
        if p + 5 > len(data):
            raise ValueError("The IPS patch is cut off.")
        off = int.from_bytes(data[p:p + 3], "big")
        n = int.from_bytes(data[p + 3:p + 5], "big")
        p += 5
        if n == 0:
            run = int.from_bytes(data[p:p + 2], "big")
            out.append((off, data[p + 2:p + 3] * run))
            p += 3
        else:
            if p + n > len(data):
                raise ValueError("The IPS patch is cut off.")
            out.append((off, bytes(data[p:p + n])))
            p += n


def build_ips(records: List[Record]) -> bytes:
    parts = [b"PATCH"]
    for off, b in records:
        for k in range(0, len(b), 0xFFFF):
            chunk = b[k:k + 0xFFFF]
            if off + k == 0x454F46:  # would read as "EOF"
                raise ValueError("A record at offset 0x454F46 cannot be stored in an IPS patch.")
            parts.append((off + k).to_bytes(3, "big") + len(chunk).to_bytes(2, "big") + chunk)
    parts.append(b"EOF")
    return b"".join(parts)


def _overlaps(a: Record, b: Record) -> bool:
    return a[0] < b[0] + len(b[1]) and b[0] < a[0] + len(a[1])


# ---------------------------------------------------------------------- bundled patch
def bundled_path() -> Optional[str]:
    here = os.path.dirname(os.path.abspath(__file__))
    for base in (os.getcwd(), os.path.join(here, "..", "..", "..")):
        p = os.path.normpath(os.path.join(base, PATCH_FILE))
        if os.path.isfile(p):
            return p
    return None


def bundled_records() -> List[Record]:
    p = bundled_path()
    if not p:
        raise FileNotFoundError(f"{PATCH_FILE} is missing from the Paragon Unlimited folder.")
    with open(p, "rb") as f:
        return parse_ips(f.read())


def bundled_bytes() -> bytes:
    return build_ips(bundled_records())


# ---------------------------------------------------------------------- status
NONE, CURRENT, OLD, OTHER = "none", "current", "old", "other"


def status(ips: Optional[bytes], ours: Optional[List[Record]] = None) -> str:
    """none: no code.ips; current: has this Paragon Unlimited patch; old: has an older (or
    partial) one; other: a code.ips from something else only."""
    if not ips:
        return NONE
    ours = ours if ours is not None else bundled_records()
    try:
        theirs = parse_ips(ips)
    except ValueError:
        return OTHER
    patched = _apply(theirs)
    if all(_reads(patched, off, b) for off, b in ours):
        return CURRENT
    if any(_overlaps(t, o) for t in theirs for o in ours):
        return OLD
    return OTHER


def _apply(records: List[Record]) -> dict:
    mem = {}
    for off, b in records:
        for k, v in enumerate(b):
            mem[off + k] = v
    return mem


def _reads(mem: dict, off: int, b: bytes) -> bool:
    return all(mem.get(off + k) == v for k, v in enumerate(b))


def merge(existing: Optional[bytes], ours: Optional[List[Record]] = None) -> Tuple[bytes, int]:
    """New code.ips = the other patches' records + ours. Returns (bytes, records kept)."""
    ours = ours if ours is not None else bundled_records()
    kept = []
    if existing:
        kept = [r for r in parse_ips(existing) if not any(_overlaps(r, o) for o in ours)]
    return build_ips(kept + list(ours)), len(kept)


def unmerge(existing: bytes, ours: Optional[List[Record]] = None) -> Tuple[bytes, int]:
    """code.ips without Paragon Unlimited's records. Returns (bytes, records kept)."""
    ours = ours if ours is not None else bundled_records()
    kept = [r for r in parse_ips(existing) if not any(_overlaps(r, o) for o in ours)]
    return build_ips(kept), len(kept)


# ---------------------------------------------------------------------- the mod folder
def target_path(mod_root: str) -> str:
    """Where the code.ips goes: the one that is already there, else mods/<title>/code.ips."""
    from paragon.unlimited.tools.azahar import normalize_mod_root

    title = os.path.join(normalize_mod_root(mod_root), BASE_TITLE)
    root_ips = os.path.join(title, "code.ips")
    exefs_ips = os.path.join(title, "exefs", "code.ips")
    if not os.path.isfile(root_ips) and os.path.isfile(exefs_ips):
        return exefs_ips
    return root_ips


def installed_paths(mod_root: Optional[str]) -> List[str]:
    if not mod_root:
        return []
    from paragon.unlimited.tools.azahar import normalize_mod_root

    title = os.path.join(normalize_mod_root(mod_root), BASE_TITLE)
    return [p for p in (os.path.join(title, "code.ips"), os.path.join(title, "exefs", "code.ips"))
            if os.path.isfile(p)]


def installed_status(mod_root: Optional[str]) -> Tuple[str, Optional[str]]:
    for p in installed_paths(mod_root):
        with open(p, "rb") as f:
            return status(f.read()), p
    return NONE, None


def _backup(path: str) -> str:
    stamp = datetime.datetime.now().strftime("%Y_%m_%d_%H_%M_%S")
    dst = f"{path}.before_PU_{stamp}"
    shutil.copy2(path, dst)
    return dst


def _write_checked(path: str, data: bytes):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".part"
    with open(tmp, "wb") as f:
        f.write(data)
    os.replace(tmp, path)
    with open(path, "rb") as f:
        if hashlib.sha256(f.read()).digest() != hashlib.sha256(data).digest():
            raise IOError(f"The installed file does not match what was written: {path}")


def _forget_limit():
    try:
        from paragon.unlimited.saving import save_checks as wp

        wp._limit_cache.clear()
    except Exception:
        pass


def install(mod_root: str) -> dict:
    """Install or update the patch. Returns {path, backup, kept, status_before}."""
    path = target_path(mod_root)
    existing = None
    if os.path.isfile(path):
        with open(path, "rb") as f:
            existing = f.read()
    before = status(existing)
    data, kept = merge(existing)
    backup = _backup(path) if existing is not None and existing != data else None
    if existing != data:
        _write_checked(path, data)
    _forget_limit()
    return {"path": path, "backup": backup, "kept": kept, "status_before": before}


def uninstall(mod_root: str) -> dict:
    """Take Paragon Unlimited's records out again; other patches stay. Returns {path, backup, kept}."""
    st, path = installed_status(mod_root)
    if not path or st not in (CURRENT, OLD):
        return {"path": path, "backup": None, "kept": None}
    with open(path, "rb") as f:
        existing = f.read()
    data, kept = unmerge(existing)
    backup = _backup(path)
    if kept:
        _write_checked(path, data)
    else:
        os.remove(path)
    _forget_limit()
    return {"path": path, "backup": backup, "kept": kept}


def patch_for_sharing(mod_root: Optional[str]) -> Tuple[Optional[bytes], str]:
    """The code.ips that goes into a shared mod and where it came from.

    The installed one when it already has the current Paragon Unlimited patch (it may also hold
    another mod's patches that this mod needs), else the bundled patch merged into the installed one,
    else the bundled patch alone."""
    st, path = installed_status(mod_root)
    existing = None
    if path:
        with open(path, "rb") as f:
            existing = f.read()
    if st == CURRENT:
        return existing, f"your installed code.ips ({path})"
    try:
        if existing and st in (OLD, OTHER):
            return merge(existing)[0], "your installed code.ips + the Paragon Unlimited patch"
        return bundled_bytes(), "the Paragon Unlimited patch"
    except (FileNotFoundError, ValueError):
        return existing, (f"your installed code.ips ({path})" if existing else "")


FEATURES = ("- 60 support partners per character (Unlimited slots #052-#059)\n"
            "- skill effects (the Effects lines of your skills)\n"
            "- room for 4096 support conversations (the game has 1920)")


def describe(mod_root: str) -> Tuple[str, bool, bool]:
    """(message, can install/update, can remove) for the install dialog."""
    st, path = installed_status(mod_root)
    where = path or target_path(mod_root)
    head = f"The game code patch adds:\n{FEATURES}\n\nFor {GAME}.\n\n"
    if st == CURRENT:
        return head + f"It is installed and up to date:\n{where}", False, True
    if st == OLD:
        return (head + f"An older Paragon Unlimited patch is installed:\n{where}\n\n"
                "Update it? Changes from other patches in that file are kept, and the old file is "
                "kept as a backup next to it."), True, True
    if st == OTHER:
        return (head + f"There is a code.ips from another mod:\n{where}\n\n"
                "Install? Paragon Unlimited's changes are added to it, its own changes are kept "
                "(where both change the same place, Paragon Unlimited's change is used), and the "
                "old file is kept as a backup next to it."), True, False
    return head + f"Not installed. Install it to:\n{where}", True, False
