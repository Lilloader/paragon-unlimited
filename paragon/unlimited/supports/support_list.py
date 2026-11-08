"""Paragon Unlimited - add and remove whole FE13 supports.

A normal support between two characters A and B needs three things in the game files. Adding a
support here writes all of them; removing one takes them out again:

1. Support slots (data/person/static.bin): B in one of A's slots and A in one of B's, with
   the same support type (the C/B/A/S point thresholds). An S rank only exists when the fourth
   threshold is not 99, as in the game's own data (Slow, Medium and Fast have an S; Non-romantic
   does not).
2. Support conversations (data/RelianceList.bin): one record per rank (C, B, A, and S when the
   type has one), each with its own support number, listed in both characters' tables.
3. The conversation text (m/E/A_B.bin.lz) with the messages MID_支援_A_B_Ｃ / Ｂ / Ａ / Ｓ.
   The game looks for m/A_B first and then m/B_A (code.bin 0x1B6304), so an existing file in
   either order is used.

Removing a support clears the slots on both sides and the support conversation records. The
text file is kept, so the conversations are still there if the support is added again.
Family supports (parent / child, siblings) are not touched here.
"""
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from paragon.unlimited.saving.save_checks import next_free_support_number
from paragon.unlimited.supports import extra_slots
from paragon.unlimited.supports import support_tools as st

NORMAL = 0  # RelianceListData support_type: 0 normal, 1 parent / child, 2 siblings
LEVELS = {1: "C", 2: "B", 3: "A", 4: "S"}
LEVEL_KEYS = {1: "Ｃ", 2: "Ｂ", 3: "Ａ", 4: "Ｓ"}
NO_RANK = 0x63  # 99: this rank cannot be reached


@dataclass
class Support:
    partner: int
    thresholds: Optional[int]
    slots: List[int] = field(default_factory=list)  # slot numbers in the owner's list
    partner_lists_owner: bool = True
    conversations: List[int] = field(default_factory=list)  # levels with a record (1-4)


@dataclass
class Result:
    ok: bool = True
    message: str = ""
    slots: Tuple[Optional[int], Optional[int]] = (None, None)
    numbers: List[int] = field(default_factory=list)
    archive: Optional[str] = None


# ----------------------------------------------------------------------------- basics

def has_s(thresholds) -> bool:
    if thresholds is None or st.is_none(thresholds):
        return False
    return ((thresholds & 0xFFFFFFFF) >> 24) != NO_RANK


def levels_for(thresholds) -> List[int]:
    return [1, 2, 3, 4] if has_s(thresholds) else [1, 2, 3]


def name_of(gd, rid) -> Optional[str]:
    """'クロム' for PID_クロム (the name the game uses for conversation files)."""
    key = gd.key(rid) if rid else None
    if not key or len(key) < 5:
        return None
    return key[4:]


def _characters(gd):
    t = gd.table("characters")
    return gd.items(t[0], t[1]) if t else []


def _reliance(gd):
    node = gd.node("reliance_list")
    return node.rid if node and node.rid else None


def _list_of(gd, character, create=True) -> Optional[int]:
    """The character's RelianceList record (its table is at the character's position).
    With create, missing tables up to that position are added."""
    rel = _reliance(gd)
    if not rel:
        return None
    chars = _characters(gd)
    if character not in chars:
        return None
    pos = chars.index(character)
    tables = gd.items(rel, "tables") or []
    if not create:
        return gd.rid(tables[pos], "data") if pos < len(tables) else None
    store = gd.store_number_of(rel)
    while len(tables) <= pos:
        ptr = gd.list_add(rel, "tables")
        gd.set_rid(ptr, "data", gd.new_instance("RelianceList", store))
        tables = gd.items(rel, "tables") or []
    lst = gd.rid(tables[pos], "data")
    if not lst:
        lst = gd.new_instance("RelianceList", store)
        gd.set_rid(tables[pos], "data", lst)
    return lst


def _is_pair(gd, entry, a, b, stype=NORMAL) -> bool:
    c1, c2 = gd.rid(entry, "character1"), gd.rid(entry, "character2")
    return {c1, c2} == {a, b} and (gd.int(entry, "support_type") or 0) == stype


def conversation_records(gd, a, b) -> List[Tuple[int, int]]:
    """[(record, level)] of the normal support conversations between a and b."""
    out, seen = [], set()
    for owner in (a, b):
        lst = _list_of(gd, owner, create=False)
        if not lst:
            continue
        for p in gd.items(lst, "data") or []:
            e = gd.rid(p, "data")
            if e and e not in seen and _is_pair(gd, e, a, b):
                seen.add(e)
                out.append((e, gd.int(e, "support_level") or 0))
    return out


# ----------------------------------------------------------------------------- listing

def supports_of(gd, owner) -> List[Support]:
    """Normal supports of a character, in slot order (one row per partner)."""
    by_partner = {}
    order = []
    for k, p, t in extra_slots.all_slots(gd, owner):
        if p not in by_partner:
            by_partner[p] = Support(p, t)
            order.append(p)
        s = by_partner[p]
        s.slots.append(k)
        if st.is_none(s.thresholds) and not st.is_none(t):
            s.thresholds = t
    out = []
    for p in order:
        s = by_partner[p]
        s.partner_lists_owner = any(q == owner for _k, q, _t in extra_slots.all_slots(gd, p))
        s.conversations = sorted({lvl for _e, lvl in conversation_records(gd, owner, p)})
        out.append(s)
    return out


def current_type(gd, a, b):
    """The support type a slot of the pair already has (a's side first), or None."""
    for owner, partner in ((a, b), (b, a)):
        for _k, p, t in extra_slots.all_slots(gd, owner):
            if p == partner and not st.is_none(t):
                return t
    return None


def free_slots(gd, owner) -> int:
    used = {k for k, _p, _t in extra_slots.all_slots(gd, owner)}
    return extra_slots.TOTAL_SLOTS - len(used)


# ----------------------------------------------------------------------------- text

def find_archive(gd, a, b) -> Optional[str]:
    na, nb = name_of(gd, a), name_of(gd, b)
    if not na or not nb:
        return None
    for path in (f"m/{na}_{nb}.bin.lz", f"m/{nb}_{na}.bin.lz"):
        try:
            gd.open_text_data(path, True)
            return path
        except Exception:
            continue
    return None


def _archive_names(path) -> Tuple[str, str]:
    x, y = st.names_from_archive(path)
    return x, y


def ensure_archive(gd, a, b, levels) -> Optional[str]:
    """The conversation file of the pair, created when there is none; every level in `levels`
    gets a message (the starting text) when it has none yet."""
    path = find_archive(gd, a, b)
    na, nb = name_of(gd, a), name_of(gd, b)
    if not na or not nb:
        return None
    if path is None:
        path = f"m/{na}_{nb}.bin.lz"
        gd.new_text_data(path, True)
        gd.set_text_archive_title(path, True, f"MESS_ARCHIVE_{na}_{nb}")
    x, y = _archive_names(path)
    try:
        existing = set(gd.enumerate_messages(path, True) or [])
    except Exception:
        existing = set()
    for lvl in levels:
        key = f"MID_支援_{x}_{y}_{LEVEL_KEYS[lvl]}"
        if key not in existing:
            gd.set_message(path, True, key, st.starting_text(x, y))
    return path


# ----------------------------------------------------------------------------- conversations

def _add_conversation(gd, a, b, level) -> int:
    number = next_free_support_number(gd)
    lst_a, lst_b = _list_of(gd, a), _list_of(gd, b)
    store = gd.store_number_of(_reliance(gd))
    entry = gd.new_instance("RelianceListData", store)
    gd.set_rid(entry, "character1", a)
    gd.set_rid(entry, "character2", b)
    gd.set_int(entry, "support_type", NORMAL)
    gd.set_int(entry, "support_level", level)
    gd.set_int(entry, "support_number", number)
    for lst in (lst_a, lst_b):
        if lst:
            p = gd.list_add(lst, "data")
            gd.set_rid(p, "data", entry)
    gd.set_store_dirty("reliance_list", True)
    return number


def add_conversations(gd, a, b, levels) -> List[int]:
    """Conversation records for the levels the pair does not have yet. Returns new numbers."""
    have = {lvl for _e, lvl in conversation_records(gd, a, b)}
    return [_add_conversation(gd, a, b, lvl) for lvl in levels if lvl not in have]


def remove_conversations(gd, a, b, levels=None) -> int:
    """Take the pair's normal conversation records (all, or only `levels`) out of every table."""
    rel = _reliance(gd)
    if not rel:
        return 0
    removed = 0
    for t in gd.items(rel, "tables") or []:
        lst = gd.rid(t, "data")
        if not lst:
            continue
        items = gd.items(lst, "data") or []
        for i in range(len(items) - 1, -1, -1):
            e = gd.rid(items[i], "data")
            if e and _is_pair(gd, e, a, b) and (levels is None or gd.int(e, "support_level") in levels):
                gd.list_remove(lst, "data", i)
                removed += 1
    if removed:
        gd.set_store_dirty("reliance_list", True)
    return removed


# ----------------------------------------------------------------------------- add / remove / type

def add_support(gd, a, b, thresholds=None) -> Result:
    """Make a and b support partners: slots on both sides, conversation records for every rank,
    and the conversation text file."""
    if a is None or b is None:
        return Result(False, "Pick a character.")
    if a == b:
        return Result(False, "A character cannot support themself.")
    if not name_of(gd, a) or not name_of(gd, b):
        return Result(False, "Both characters need a PID (PID_name).")
    if thresholds is None or st.is_none(thresholds):
        thresholds = current_type(gd, a, b)
    if thresholds is None or st.is_none(thresholds):
        thresholds = st.default_type(gd, a, b)
    listed_a = any(p == b for _k, p, _t in extra_slots.all_slots(gd, a))
    listed_b = any(p == a for _k, p, _t in extra_slots.all_slots(gd, b))
    for who, listed in ((a, listed_a), (b, listed_b)):
        if not listed and free_slots(gd, who) == 0:
            return Result(False, f"{gd.display(who)} has no free support slot (all {extra_slots.TOTAL_SLOTS} are used).")
    ka = st.add_partner(gd, a, b, thresholds)
    kb = st.add_partner(gd, b, a, thresholds)
    set_type(gd, a, b, thresholds, conversations=False)  # same type on both sides
    levels = levels_for(thresholds)
    numbers = add_conversations(gd, a, b, levels)
    archive = ensure_archive(gd, a, b, levels)
    extra = [k for k in (ka, kb) if k is not None and k >= extra_slots.BASE_SLOTS]
    note = ""
    if extra:
        note = " Uses the Unlimited slots #052-#059, which need the game code patch."
    return Result(True, f"Added.{note}", (ka, kb), numbers, archive)


def remove_support(gd, a, b) -> Result:
    """Clear every slot in which a lists b and b lists a, and the pair's conversation records."""
    cleared = 0
    for owner, partner in ((a, b), (b, a)):
        for k in st.slots_listing(gd, owner, partner):
            rec = st.slot_record(gd, owner, k)
            if rec:
                st.clear_slot(gd, rec, k)
                cleared += 1
    removed = remove_conversations(gd, a, b)
    return Result(True, f"Removed ({cleared} slot(s), {removed} conversation listing(s)).")


def set_type(gd, a, b, thresholds, conversations=True) -> Result:
    """Same support type in every slot where a lists b and b lists a. With conversations, the S
    rank conversation is added or removed to match the type (its text is kept)."""
    for owner, partner in ((a, b), (b, a)):
        for k in st.slots_listing(gd, owner, partner):
            rec = st.slot_record(gd, owner, k)
            if rec:
                gd.set_int(rec, f"support_type_{k:03}", thresholds)
    gd.set_store_dirty("characters", True)
    numbers = []
    if conversations:
        if has_s(thresholds):
            numbers = add_conversations(gd, a, b, [4])
            ensure_archive(gd, a, b, levels_for(thresholds))
        else:
            remove_conversations(gd, a, b, levels={4})
    return Result(True, "Support type changed.", numbers=numbers)


def repair_support(gd, a, b, thresholds=None) -> Result:
    """Fill in whatever the pair is missing (the other side's slot, conversations, text)."""
    return add_support(gd, a, b, thresholds)
