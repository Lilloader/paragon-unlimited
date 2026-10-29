"""Paragon Unlimited - FE13 support slot tools: clear a slot, assign partners for support
conversations that no slot reaches, the default support type for a pair, and the starting
text of a new support conversation.

Support types (the C/B/A/S point thresholds of a slot) used by the game itself:
    both characters female -> Non-romantic (90 slots in vanilla)
    both male              -> Non-romantic (94)
    one female, one male   -> mostly Slow (388; a few Fast/Medium for story pairs)
"""
from typing import List, Optional, Tuple

from paragon.core.services import fe13_support_ex

BASE_SLOTS = fe13_support_ex.BASE_SLOTS
TYPE_NONE = 0x63636363  # 1667457891: no support
TYPE_NON_ROMANTIC = 1662126596
TYPE_SLOW = 370149893
FEMALE_FLAG = 0x01  # bitflags_1 bit 0


def is_female(gd, rid) -> bool:
    try:
        return bool((gd.int(rid, "bitflags_1") or 0) & FEMALE_FLAG)
    except Exception:
        return False


def default_type(gd, a, b) -> int:
    """Non-romantic for two women or two men, Slow for a woman and a man (as in the game)."""
    return TYPE_NON_ROMANTIC if is_female(gd, a) == is_female(gd, b) else TYPE_SLOW


def is_none(value) -> bool:
    return value is None or (value & 0xFFFFFFFF) == TYPE_NONE


def slot_record(gd, owner, k) -> Optional[int]:
    """Record that holds slot k of a character: the character itself (#000-#051) or its
    Unlimited extra-slot entry (#052-#059, created when needed)."""
    if k < BASE_SLOTS:
        return owner
    return fe13_support_ex.ensure_entry(gd, owner)


def owner_of(gd, rid):
    """The character a slot record belongs to (an extra-slot entry belongs to its owner)."""
    try:
        if gd.type_of(rid) == "PUSupportEx":
            return gd.rid(rid, "owner")
    except Exception:
        pass
    return rid


def clear_slot(gd, record, k):
    gd.set_rid(record, f"support_character_{k:03}", None)
    gd.set_int(record, f"support_type_{k:03}", TYPE_NONE)
    gd.set_store_dirty("characters", True)


def slots_listing(gd, owner, partner) -> List[int]:
    """Slot numbers in owner's list that hold partner."""
    return [k for k, p, _t in fe13_support_ex.all_slots(gd, owner) if p == partner]


def clear(gd, record, k, both_sides: bool) -> List[Tuple[int, int]]:
    """Clear slot k of record. With both_sides, also clear the partner's slot(s) that list this
    character. Returns [(character, slot)] cleared."""
    owner = owner_of(gd, record)
    partner = gd.rid(record, f"support_character_{k:03}")
    clear_slot(gd, record, k)
    done = [(owner, k)]
    if both_sides and partner is not None and owner is not None:
        for pk in slots_listing(gd, partner, owner):
            rec = slot_record(gd, partner, pk)
            if rec:
                clear_slot(gd, rec, pk)
                done.append((partner, pk))
    return done


def add_partner(gd, owner, partner, thresholds) -> Optional[int]:
    """Put partner into owner's first free slot (#000-#051, then the Unlimited #052-#059).
    A slot that already lists partner with type None gets the type instead. Returns the slot
    number, or None when the list is full."""
    for k, p, t in fe13_support_ex.all_slots(gd, owner):
        if p == partner:
            if is_none(t):
                rec = slot_record(gd, owner, k)
                gd.set_int(rec, f"support_type_{k:03}", thresholds)
                gd.set_store_dirty("characters", True)
            return k
    for k in range(BASE_SLOTS):
        if gd.rid(owner, f"support_character_{k:03}") is None:
            gd.set_rid(owner, f"support_character_{k:03}", partner)
            gd.set_int(owner, f"support_type_{k:03}", thresholds)
            gd.set_store_dirty("characters", True)
            return k
    entry = fe13_support_ex.ensure_entry(gd, owner)
    if entry:
        for k in fe13_support_ex.EXTRA_RANGE:
            if fe13_support_ex.slot_partner(gd, entry, k) is None:
                gd.set_rid(entry, f"support_character_{k:03}", partner)
                gd.set_int(entry, f"support_type_{k:03}", thresholds)
                gd.set_store_dirty("characters", True)
                return k
    return None


def assign_pairs(gd, pairs):
    """For support conversations no slot reaches: list each character in the other's slots
    with the default type for the pair. pairs: [(a, b)].
    Returns (assigned [(a, b, type, slot_a, slot_b)], full [(a, b, character with no free slot)])."""
    assigned, full = [], []
    seen = set()
    for a, b in pairs:
        key = frozenset((a, b))
        if key in seen or a is None or b is None or a == b:
            continue
        seen.add(key)
        t = default_type(gd, a, b)
        ka = add_partner(gd, a, b, t)
        kb = add_partner(gd, b, a, t)
        if ka is None:
            full.append((a, b, a))
        if kb is None:
            full.append((a, b, b))
        if ka is not None or kb is not None:
            assigned.append((a, b, t, ka, kb))
    return assigned, full


def clear_placeholder_slots(gd, characters) -> List[Tuple[int, int]]:
    """Slots that all list the same partner with support type None (seen on characters added
    to the list in some older editors: every slot = the male avatar, type None). They do nothing
    in game but fill the list. Clears every slot of such a partner when it fills 4 or more
    slots of one character. Returns [(character, number of slots cleared)]."""
    out = []
    for c in characters:
        slots = fe13_support_ex.all_slots(gd, c)
        by_partner = {}
        for k, p, t in slots:
            by_partner.setdefault(p, []).append((k, t))
        cleared = 0
        for p, ks in by_partner.items():
            if len(ks) >= 4 and all(is_none(t) for _k, t in ks):
                for k, _t in ks:
                    rec = slot_record(gd, c, k)
                    if rec:
                        clear_slot(gd, rec, k)
                        cleared += 1
        if cleared:
            out.append((c, cleared))
    return out


def compact(gd, owner) -> bool:
    """Move owner's supports up so there are no empty slots between them (same order;
    #000-#051 first, then the Unlimited #052-#059). Returns True when something moved."""
    slots = fe13_support_ex.all_slots(gd, owner)
    wanted = [(i, p, t) for i, (_k, p, t) in enumerate(slots)]
    if all(k == i for i, (k, _p, _t) in enumerate(slots)):
        return False
    for k, _p, _t in slots:
        clear_slot(gd, slot_record(gd, owner, k), k)
    for i, p, t in wanted:
        rec = slot_record(gd, owner, i)
        gd.set_rid(rec, f"support_character_{i:03}", p)
        gd.set_int(rec, f"support_type_{i:03}", t if t is not None else TYPE_NONE)
    gd.set_store_dirty("characters", True)
    return True


def type_name(value) -> str:
    return {
        TYPE_NONE: "None",
        TYPE_NON_ROMANTIC: "Non-romantic",
        TYPE_SLOW: "Slow",
        336464132: "Medium",
        302843907: "Fast",
    }.get((value or 0) & 0xFFFFFFFF, str(value))


# ----------------------------------------------------------------------------- new conversations

OLD_PLACEHOLDER = (
    "$t1$Wmアンナ|3$w0|$Wsアンナ|$E通常,|This message was generated\\nby Paragon.$k"
)


def names_from_archive(path: str) -> Tuple[Optional[str], Optional[str]]:
    """('クロム', 'リズ') from m/クロム_リズ.bin.lz (also m/クロム_ルキナ_親子.bin.lz)."""
    name = path.replace("\\", "/").split("/")[-1]
    for ext in (".bin.lz", ".bin"):
        if name.endswith(ext):
            name = name[: -len(ext)]
    if name.endswith("_親子"):
        name = name[: -len("_親子")]
    parts = name.split("_")
    if len(parts) < 2:
        return None, None
    # Character names never contain "_" in vanilla; a name with one keeps its tail on y.
    return parts[0], "_".join(parts[1:])


def asset_name(name: str) -> str:
    """The avatar's supports load the portrait as "username" (as in the game's own text)."""
    return "username" if "プレイヤー" in name or "マイユニ" in name else name


def starting_text(x: str, y: str) -> str:
    """Game text of a new support: type 1 box, x on the left (3), y on the right (7),
    x speaks first with the standard expression.

        $SetConversationType(1)
        $LoadAssets(x, 3)
        $Wait(0)
        $LoadAssets(y, 7)
        $SetSpeaker(x)
        $Emotions(Standard)
    """
    x, y = asset_name(x), asset_name(y)
    return f"$t1$Wm{x}|3$w0|$Wm{y}|7$Ws{x}|$E通常,|"


def fill_new_conversations(gd, path: str, localized: bool = True) -> int:
    """Give every message of a support archive that is still Paragon's placeholder (or empty)
    the starting text. Returns how many were filled."""
    x, y = names_from_archive(path)
    if not x or not y:
        return 0
    filled = 0
    for key in gd.enumerate_messages(path, localized) or []:
        value = gd.message(path, localized, key)
        if not value or value == OLD_PLACEHOLDER:
            gd.set_message(path, localized, key, starting_text(x, y))
            filled += 1
    return filled
