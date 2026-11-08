"""Paragon Unlimited - FE13 reclass slots 4-5 and the avatar class list.

Both need the Paragon Unlimited game code patch (code_patch/class_slots). Without it the game
ignores the two tables and behaves as before.

Reclass slots 4-5
    The game's character record has 3 male and 3 female reclass classes. Slots 4 and 5 live in
    the optional ``PU_ClassEx`` table appended to data/person/static.bin, one 20-byte entry per
    character that uses them (u16 owner, u16 0, then JIDs for male 4, male 5, female 4,
    female 5). Entries are made when the editor opens a character and empty ones are dropped
    on save.

Avatar classes
    A unit is an "avatar" when its reclass classes (or a parent's) include Tactician for its
    gender. The game then gives it a fixed list of 13 classes (plus Manakete / Taguel for units
    with those skills, plus its own reclass classes). With the patch the list comes from the
    optional ``PU_AvatarCls`` table in data/GameData.bin (8-byte entries: JID, u8 gender,
    3 bytes 0). An empty table means the game's own 13 classes.

The game's Second Seal list holds 64 classes, including the promotions it adds for each class
once the unit is level 10 or more. The patch stops adding classes at 64 instead of writing past
the end of the list, so ``seal_list_size`` lets the editor warn before that happens.
"""
from typing import Dict, List, Optional

CLASS_EX_LABEL = "PU_ClassEx"
AVATAR_LABEL = "PU_AvatarCls"
SEAL_LIST_MAX = 64
EXTRA_SLOTS = (4, 5)
GENDERS = ("male", "female")
TACTICIAN = {"male": "JID_戦術師男", "female": "JID_戦術師女"}

# The game's own avatar classes (FUN_002CFF38), in the game's order.
GAME_AVATAR_CLASSES: Dict[str, List[str]] = {
    "male": ["JID_戦術師男", "JID_ソシアルナイト男", "JID_アーマーナイト男", "JID_蛮族男", "JID_戦士男",
             "JID_傭兵男", "JID_アーチャー男", "JID_剣士男", "JID_盗賊男", "JID_ドラゴンナイト男",
             "JID_僧侶男", "JID_魔道士男", "JID_ダークマージ男"],
    "female": ["JID_戦術師女", "JID_ソシアルナイト女", "JID_アーマーナイト女", "JID_傭兵女",
               "JID_アーチャー女", "JID_剣士女", "JID_盗賊女", "JID_ペガサスナイト女",
               "JID_ドラゴンナイト女", "JID_トルバドール女", "JID_シスター女", "JID_魔道士女",
               "JID_ダークマージ女"],
}


# ---------------------------------------------------------------------- reclass slots 4-5
def _class_ex_root(gd) -> Optional[int]:
    table = gd.table("characters")
    if not table:
        return None
    try:
        return gd.rid(table[0], "class_ex")
    except Exception:
        return None


def has_class_ex(gd) -> bool:
    return _class_ex_root(gd) is not None


def class_ex_entries(gd) -> List[int]:
    root = _class_ex_root(gd)
    if not root:
        return []
    return gd.items(root, "entries") or []


def find_entry(gd, person_rid) -> Optional[int]:
    if not person_rid:
        return None
    for e in class_ex_entries(gd):
        if gd.rid(e, "owner") == person_rid:
            return e
    return None


def ensure_entry(gd, person_rid) -> Optional[int]:
    """The character's entry, made empty if it has none (that alone is not a change)."""
    if not person_rid:
        return None
    e = find_entry(gd, person_rid)
    if e:
        return e
    root = _class_ex_root(gd)
    if not root:
        return None
    was_dirty = gd.store_is_dirty("characters")
    was_changed = getattr(gd, "pu_changed", None)
    e = gd.list_add(root, "entries")
    gd.set_rid(e, "owner", person_rid)
    if not was_dirty:
        gd.set_store_dirty("characters", False)
    if was_changed is not None:
        gd.pu_changed = was_changed
    return e


def slot_field(gender: str, slot: int) -> str:
    return f"{gender}_reclass_{slot}"


def is_empty(gd, entry_rid) -> bool:
    return all(gd.rid(entry_rid, slot_field(g, k)) is None for g in GENDERS for k in EXTRA_SLOTS)


def cleanup(gd):
    """Drop entries with no class in slots 4-5 or no character. Returns (empty, orphan)."""
    root = _class_ex_root(gd)
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


def reclass_classes(gd, person_rid, gender: str) -> List[int]:
    """All 5 reclass classes of a character for one gender (empty slots left out)."""
    out = []
    for k in (1, 2, 3):
        j = gd.rid(person_rid, slot_field(gender, k))
        if j is not None:
            out.append(j)
    e = find_entry(gd, person_rid)
    if e:
        for k in EXTRA_SLOTS:
            j = gd.rid(e, slot_field(gender, k))
            if j is not None:
                out.append(j)
    return out


def set_slot(gd, person_rid, gender: str, slot: int, job_rid) -> None:
    """Set reclass slot 1-5 of a character (slots 4-5 go to PU_ClassEx)."""
    if slot in (1, 2, 3):
        gd.set_rid(person_rid, slot_field(gender, slot), job_rid)
        gd.set_store_dirty("characters", True)
        return
    e = ensure_entry(gd, person_rid)
    if e is None:
        raise RuntimeError("This data has no PU_ClassEx table (reclass slots 4-5).")
    gd.set_rid(e, slot_field(gender, slot), job_rid)
    gd.set_store_dirty("characters", True)


# ---------------------------------------------------------------------- avatar classes
def _avatar_root(gd) -> Optional[int]:
    try:
        node = gd.node("pu_avatar_classes")
    except Exception:
        node = None
    if node is not None and getattr(node, "rid", None):
        return node.rid
    return None


def has_avatar_table(gd) -> bool:
    return _avatar_root(gd) is not None


def _job_by_jid(gd, jid) -> Optional[int]:
    try:
        return gd.key_to_rid("jobs", jid)
    except Exception:
        return None


def jid(gd, job_rid) -> Optional[str]:
    try:
        return gd.key(job_rid)
    except Exception:
        return None


def job_gender(gd, job_rid) -> Optional[str]:
    """'male' / 'female' from the JID (the game's own classes all end in 男 or 女)."""
    k = jid(gd, job_rid) or ""
    if k.endswith("男"):
        return "male"
    if k.endswith("女"):
        return "female"
    return None


def uses_game_list(gd) -> bool:
    """True when the table has no entries: the game's own 13 classes per gender are used."""
    root = _avatar_root(gd)
    return not root or not (gd.items(root, "entries") or [])


def avatar_classes(gd, gender: str) -> List[int]:
    """The classes avatars of this gender get (the game's own list when the table is empty)."""
    g = GENDERS.index(gender)
    root = _avatar_root(gd)
    entries = gd.items(root, "entries") if root else []
    if not entries:
        return [r for r in (_job_by_jid(gd, j) for j in GAME_AVATAR_CLASSES[gender]) if r is not None]
    out = []
    for e in entries:
        if (gd.int(e, "gender") or 0) == g:
            j = gd.rid(e, "job")
            if j is not None and j not in out:
                out.append(j)
    return out


def set_avatar_classes(gd, gender: str, job_rids: List[int]) -> None:
    """Replace one gender's list. The other gender keeps what it had (the game's list is
    written out as entries the first time, so nothing changes for it)."""
    root = _avatar_root(gd)
    if not root:
        raise RuntimeError("This data has no PU_AvatarCls table (avatar classes).")
    lists = {g: avatar_classes(gd, g) for g in GENDERS}
    lists[gender] = [j for k, j in enumerate(job_rids) if j is not None and j not in job_rids[:k]]
    while gd.list_size(root, "entries"):
        gd.list_remove(root, "entries", gd.list_size(root, "entries") - 1)
    for gi, g in enumerate(GENDERS):
        for j in lists[g]:
            e = gd.list_add(root, "entries")
            gd.set_rid(e, "job", j)
            gd.set_int(e, "gender", gi)
    gd.set_store_dirty("gamedata", True)


def reset_avatar_classes(gd) -> None:
    """Back to the game's own 13 classes per gender (empty table)."""
    root = _avatar_root(gd)
    if not root:
        return
    while gd.list_size(root, "entries"):
        gd.list_remove(root, "entries", gd.list_size(root, "entries") - 1)
    gd.set_store_dirty("gamedata", True)


def is_avatar(gd, person_rid) -> bool:
    """Tactician among the character's own reclass classes (male or female, slots 1-5)."""
    if not person_rid:
        return False
    for g in GENDERS:
        for j in reclass_classes(gd, person_rid, g):
            if jid(gd, j) == TACTICIAN[g]:
                return True
    return False


# The game's enemy / story-only classes: left out by "Tick all" (they can still be ticked).
NOT_PLAYABLE = {"JID_ゾンビ男", "JID_マミー男", "JID_シルエット男", "JID_ダミー男", "JID_ボス男", "JID_ボス女",
                "JID_商人女"}


def base_classes(gd, gender: str) -> List[int]:
    """Every class of a gender that is not a promotion of another class."""
    try:
        table_rid, field = gd.table("jobs")
        jobs = gd.items(table_rid, field) or []
    except Exception:
        return []
    jobs = [j for j in jobs if job_gender(gd, j) == gender]
    promoted = {p for j in jobs for p in promotions(gd, j)}
    return [j for j in jobs if j not in promoted]


def playable_base_classes(gd, gender: str) -> List[int]:
    """base_classes without nameless classes and the game's enemy / story-only ones."""
    out = []
    for j in base_classes(gd, gender):
        if jid(gd, j) in NOT_PLAYABLE:
            continue
        try:
            name = gd.display(j)
        except Exception:
            name = None
        if name and name != "None":
            out.append(j)
    return out


def promotions(gd, job_rid) -> List[int]:
    out = []
    for f in ("promoted_class_1", "promoted_class_2"):
        try:
            p = gd.rid(job_rid, f)
        except Exception:
            p = None
        if p is not None and p != job_rid:
            out.append(p)
    return out


def seal_list_size(gd, person_rid, gender: str) -> int:
    """How many classes the Second Seal list of this character can reach (the most the game
    adds: the avatar list if it is one, its 5 reclass classes and all their promotions)."""
    base = []
    if is_avatar(gd, person_rid):
        base += avatar_classes(gd, gender)
    base += reclass_classes(gd, person_rid, gender)
    seen = []
    for j in base:
        if j not in seen:
            seen.append(j)
    total = list(seen)
    for j in seen:
        for p in promotions(gd, j):
            if p not in total:
                total.append(p)
    return len(total)
