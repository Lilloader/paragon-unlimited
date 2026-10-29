"""Paragon Unlimited - extra FE13 support slots #052-#059.

The slots live in an optional table labeled ``PU_SupportEx2`` appended to
data/person/static.bin. The game only reads it with the Paragon Unlimited code.ips
(exp03 or later). Layout (all little endian):

    u32 count
    count x entry (68 bytes):
        u16 owner        static position of the character (Paragon keeps it in sync)
        u16 reserved     0
        8 x { PID pointer (or 0), u32 C/B/A/S thresholds }

A character without an entry simply has empty extra slots. Entries are created on demand
by the character editor and empty ones are dropped on save.
"""

from typing import List, Optional

BASE_SLOTS = 52
EXTRA_SLOTS = 8
TOTAL_SLOTS = BASE_SLOTS + EXTRA_SLOTS
EXTRA_RANGE = range(BASE_SLOTS, TOTAL_SLOTS)
LABEL = "PU_SupportEx2"
NO_SUPPORT_THRESHOLDS = 0x63636363  # "None" in the support type list


def _root(gd):
    table = gd.table("characters")
    if not table:
        return None
    try:
        return gd.rid(table[0], "support_ex")
    except Exception:
        return None


def entries(gd) -> List[int]:
    root = _root(gd)
    if not root:
        return []
    return gd.items(root, "entries") or []


def find_entry(gd, person_rid) -> Optional[int]:
    if not person_rid:
        return None
    for e in entries(gd):
        if gd.rid(e, "owner") == person_rid:
            return e
    return None


def ensure_entry(gd, person_rid) -> Optional[int]:
    """Return the entry for person_rid, creating an empty one if needed.

    Creating an empty entry does not mark the file dirty: it is only written when one of
    its slots is actually edited (or the file is saved for another reason, in which case
    empty entries are removed again by cleanup()).
    """
    if not person_rid:
        return None
    e = find_entry(gd, person_rid)
    if e:
        return e
    root = _root(gd)
    if not root:
        return None
    was_dirty = gd.store_is_dirty("characters")
    was_changed = getattr(gd, "pu_changed", None)
    e = gd.list_add(root, "entries")
    gd.set_rid(e, "owner", person_rid)
    for k in EXTRA_RANGE:
        gd.set_int(e, f"support_type_{k:03}", NO_SUPPORT_THRESHOLDS)
    if not was_dirty:
        gd.set_store_dirty("characters", False)
    if was_changed is not None:
        gd.pu_changed = was_changed  # an empty entry is not a change
    return e


def slot_partner(gd, entry_rid, k):
    return gd.rid(entry_rid, f"support_character_{k:03}")


def slot_type(gd, entry_rid, k):
    return gd.int(entry_rid, f"support_type_{k:03}")


def is_empty(gd, entry_rid) -> bool:
    return all(slot_partner(gd, entry_rid, k) is None for k in EXTRA_RANGE)


def cleanup(gd):
    """Drop entries with no slots in use or no character. Returns (removed_empty, removed_orphan)."""
    root = _root(gd)
    if not root:
        return 0, 0
    empty = orphan = 0
    i = 0
    while i < gd.list_size(root, "entries"):
        e = gd.list_get(root, "entries", i)
        if gd.rid(e, "owner") is None:
            gd.list_remove(root, "entries", i)
            orphan += 1
        elif is_empty(gd, e):
            gd.list_remove(root, "entries", i)
            empty += 1
        else:
            i += 1
    return empty, orphan


def all_slots(gd, person_rid):
    """[(slot_index, partner_rid, thresholds)] for all 60 slots that have a partner."""
    out = []
    for k in range(BASE_SLOTS):
        p = gd.rid(person_rid, f"support_character_{k:03}")
        if p is not None:
            out.append((k, p, gd.int(person_rid, f"support_type_{k:03}")))
    e = find_entry(gd, person_rid)
    if e:
        for k in EXTRA_RANGE:
            p = slot_partner(gd, e, k)
            if p is not None:
                out.append((k, p, slot_type(gd, e, k)))
    return out
