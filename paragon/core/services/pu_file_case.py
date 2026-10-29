"""Paragon Unlimited: exact file-name letter case.

The game (and Azahar's mod loading) finds RomFS files by their exact name: "Edelgard_fc_通常.arc"
and "edelgard_fc_通常.arc" are different files. Windows treats them as the same file, so two
things go wrong easily:

* a reference (FaceData portrait file, map sprite name) and the file on disk differ only in case:
  fine in Paragon, "file not found" in game (crash or invisible unit);
* a file renamed in the project only by case keeps its OLD case in the Azahar mod folder, because
  copying over an existing file on Windows keeps the existing name.
"""
import logging
import os
import uuid
from typing import Dict, List, Optional, Tuple

_listing_cache: Dict[str, Dict[str, str]] = {}


def _names(folder: str) -> Dict[str, str]:
    """{lower-case name: exact name} of a folder (cached)."""
    folder = os.path.normpath(folder)
    if folder not in _listing_cache:
        try:
            _listing_cache[folder] = {n.lower(): n for n in os.listdir(folder)}
        except OSError:
            _listing_cache[folder] = {}
    return _listing_cache[folder]


def clear_cache():
    _listing_cache.clear()


def find(root: str, rel: str) -> Tuple[str, Optional[str]]:
    """("exact", rel) | ("case", actual rel) | ("missing", None) for a path below root."""
    parts = [p for p in rel.replace("\\", "/").split("/") if p]
    cur = root
    actual = []
    exact = True
    for p in parts:
        names = _names(cur)
        if p in names.values():
            name = p
        elif p.lower() in names:
            name = names[p.lower()]
            exact = False
        else:
            return "missing", None
        actual.append(name)
        cur = os.path.join(cur, name)
    return ("exact" if exact else "case"), "/".join(actual)


def resolve(roots: List[str], rel: str) -> Tuple[str, Optional[str], Optional[str]]:
    """Look in the roots in order (the project output first, then the game). Returns
    (status, root, actual rel). An exact match in any root wins."""
    first_case = None
    for root in roots:
        if not root:
            continue
        status, actual = find(root, rel)
        if status == "exact":
            return "exact", root, actual
        if status == "case" and first_case is None:
            first_case = (root, actual)
    if first_case:
        return "case", first_case[0], first_case[1]
    return "missing", None, None


def rename_case(folder: str, actual: str, wanted: str) -> bool:
    """Rename folder/actual to folder/wanted when they differ only in case (two steps, because
    Windows ignores a rename that only changes case)."""
    if actual == wanted or actual.lower() != wanted.lower():
        return False
    src = os.path.join(folder, actual)
    tmp = os.path.join(folder, f".pu_case_{uuid.uuid4().hex}")
    os.rename(src, tmp)
    try:
        os.rename(tmp, os.path.join(folder, wanted))
    except Exception:
        os.rename(tmp, src)
        raise
    _listing_cache.pop(os.path.normpath(folder), None)
    return True


def fix_project_name(root: str, rel_actual: str, rel_wanted: str) -> bool:
    """Rename the file at root/rel_actual so that its name matches rel_wanted exactly (only the
    last part; folders are left alone)."""
    folder = os.path.join(root, *rel_actual.split("/")[:-1])
    return rename_case(folder, rel_actual.split("/")[-1], rel_wanted.split("/")[-1])


def match_destination_case(src: str, dst: str) -> bool:
    """When dst exists under a name that differs from src's only in case, rename it to src's
    name. Returns True when renamed."""
    folder = os.path.dirname(dst)
    wanted = os.path.basename(src)
    names = _names(folder)
    actual = names.get(wanted.lower())
    if actual is None or actual == wanted:
        return False
    try:
        return rename_case(folder, actual, wanted)
    except OSError:
        logging.exception(f"Could not rename {actual} to {wanted}.")
        return False
