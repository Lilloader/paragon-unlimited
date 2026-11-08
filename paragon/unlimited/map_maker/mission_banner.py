"""Paragon Unlimited - the turn-1 mission banner of Seize and Survive chapters.

The game shows "Rout the enemy" (telop/Tlp_Mission02) or "Defeat commander" (Tlp_Mission01) when a
battle starts. With the game code patch (code_patch/mission_banner/), a chapter whose win rule is
0x10000 - what the Map Maker gives Seize and Survive chapters - shows telop/Tlp_PUM_<chapter>
instead. That picture is a copy of the game's banner with its text layer (256 x 32, gray levels:
white letters on black) replaced by the chapter's own text, so it moves and glows like the game's.
"""
from typing import Callable, Optional

BASE = "telop/Tlp_Mission02_E.r.lz"
TEXT_LAYER = "Tlp_Mission02"
SIZE = (256, 32)


def name(cid: str) -> str:
    return f"Tlp_PUM_{cid}"


def paths(cid: str):
    """The banner file and its English version (the game asks for <name>_E first)."""
    return f"telop/{name(cid)}.r.lz", f"telop/{name(cid)}_E.r.lz"


def default_text(plan) -> str:
    if plan.win == "seize":
        return "Seize the goal"
    if plan.win == "survive":
        n = int(getattr(plan, "survive_turns", 8) or 8)
        return f"Survive {n} turn{'s' if n != 1 else ''}"
    return ""


def text_of(plan) -> str:
    return (getattr(plan, "banner", "") or "").strip() or default_text(plan)


def make(base_cgfx: bytes, text_img) -> bytes:
    """The game's banner (decompressed CGFX) with the text layer replaced by text_img (PIL image,
    white text on black, 256 x 32)."""
    from paragon.unlimited.models import model_textures as mt

    return mt.replace_texture(base_cgfx, TEXT_LAYER, text_img)


def write(files: dict, read: Callable[[str], Optional[bytes]], plan, render: Callable[[str], object]) -> bool:
    """Put the chapter's banner into the pending files. render(text) -> PIL image."""
    base = read(BASE)
    if base is None:
        return False
    data = make(base, render(text_of(plan)))
    for p in paths(plan.cid):
        files[p] = data
    return True
