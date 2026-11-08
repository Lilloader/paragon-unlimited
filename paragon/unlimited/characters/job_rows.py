"""Paragon Unlimited - keep the characters' sprite lists in step with the class list (FE13).

A character's sprite list (Sprite Data) has one entry per class, in class-list order: entry N is
the map sprite for class N. When classes are moved, inserted or deleted in the class list, the
same is done to every sprite list, so each sprite stays with its class."""
import logging


def is_job_list(gd, rid, field_id) -> bool:
    try:
        t = gd.table("jobs")
        return bool(t) and t[0] == rid and t[1] == field_id and _sprite_lists(gd) is not None
    except Exception:
        return False


def _sprite_lists(gd):
    chars = gd.table("characters")
    if not chars:
        return None
    out, seen = [], set()
    for c in gd.items(chars[0], chars[1]) or []:
        try:
            sd = gd.rid(c, "sprite_data")
        except Exception:
            return None  # not FE13 character data
        if sd and sd not in seen:
            seen.add(sd)
            out.append(sd)
    return out


def _pad(gd, sd, n):
    while gd.list_size(sd, "entries") < n:
        e = gd.list_add(sd, "entries")
        gd.set_rid(e, "bmap_icon", None)


def _each(gd, fn):
    try:
        lists = _sprite_lists(gd) or []
        for sd in lists:
            if gd.list_size(sd, "entries"):
                fn(sd)
        if lists:
            gd.set_store_dirty("characters", True)
    except Exception:
        logging.exception("Could not update the sprite lists for the class list change.")


def moved(gd, src: int, dst: int):
    """A class moved from row src to row dst (dst counted after removing it)."""
    if src == dst:
        return

    def f(sd):
        _pad(gd, sd, max(src, dst) + 1)
        e = gd.list_get(sd, "entries", src)
        gd.list_remove(sd, "entries", src)
        gd.list_insert_existing(sd, "entries", e, dst)

    _each(gd, f)


def inserted(gd, row: int, count: int = 1):
    """count empty classes inserted at row (not at the end)."""
    def f(sd):
        if gd.list_size(sd, "entries") <= row:
            return  # past the end: the save pads it
        for _ in range(count):
            e = gd.list_insert(sd, "entries", row)
            gd.set_rid(e, "bmap_icon", None)

    _each(gd, f)


def removed(gd, row: int, count: int = 1):
    def f(sd):
        for _ in range(count):
            if gd.list_size(sd, "entries") > row:
                gd.list_remove(sd, "entries", row)

    _each(gd, f)
