"""Paragon Unlimited - FE13 RelianceList (support conversation list) helpers.

In vanilla Awakening every support conversation entry (RelianceListData) is listed in BOTH
characters' tables (table index = character position), as the same shared record.
"""
from paragon.core.services.fe13_write_preprocessors import next_free_support_number


def _tables(gd):
    node = gd.node("reliance_list")
    if not node or not node.rid:
        return None, []
    return node.rid, gd.items(node.rid, "tables") or []


def _characters(gd):
    t = gd.table("characters")
    return gd.items(t[0], t[1]) if t else []


def owner_of_list(gd, reliance_list_rid):
    """Character whose table holds this RelianceList record (or None)."""
    _, tables = _tables(gd)
    chars = _characters(gd)
    for i, t in enumerate(tables):
        if gd.rid(t, "data") == reliance_list_rid:
            return chars[i] if i < len(chars) else None
    return None


def init_new_entry(gd, reliance_list_rid, pointer_rid):
    """Give a freshly added list item a real record: Character1 = this table's character,
    Support Number = highest number in use + 1, level 1."""
    number = next_free_support_number(gd)
    entry = gd.new_instance("RelianceListData", gd.store_number_of(pointer_rid))
    gd.set_rid(pointer_rid, "data", entry)
    owner = owner_of_list(gd, reliance_list_rid)
    if owner:
        gd.set_rid(entry, "character1", owner)
    gd.set_int(entry, "support_level", 1)
    gd.set_int(entry, "support_number", number)
    gd.set_store_dirty("reliance_list", True)
    return entry


def sync_pairs(gd):
    """Make sure every entry is listed in both characters' tables (as in vanilla).
    Returns the number of list items added."""
    rel, tables = _tables(gd)
    if not rel:
        return 0
    chars = _characters(gd)
    pos = {c: i for i, c in enumerate(chars)}
    listed = {}  # entry rid -> set(table index)
    order = []
    for ti, t in enumerate(tables):
        lst = gd.rid(t, "data")
        if not lst:
            continue
        for p in gd.items(lst, "data") or []:
            e = gd.rid(p, "data")
            if e:
                if e not in listed:
                    listed[e] = set()
                    order.append(e)
                listed[e].add(ti)
    added = 0
    for e in order:
        for c in (gd.rid(e, "character1"), gd.rid(e, "character2")):
            ti = pos.get(c)
            if ti is None or ti >= len(tables) or ti in listed[e]:
                continue
            lst = gd.rid(tables[ti], "data")
            if not lst:
                continue
            p = gd.list_add(lst, "data")
            gd.set_rid(p, "data", e)
            listed[e].add(ti)
            added += 1
    if added:
        gd.set_store_dirty("reliance_list", True)
    return added


def _entries_by_table(gd):
    """[(table index, list rid, [(item index, pointer rid, record rid)])]"""
    rel, tables = _tables(gd)
    out = []
    for ti, t in enumerate(tables):
        lst = gd.rid(t, "data")
        if not lst:
            continue
        items = []
        for i, p in enumerate(gd.items(lst, "data") or []):
            items.append((i, p, gd.rid(p, "data")))
        out.append((ti, lst, items))
    return out


def _remove_items(gd, removals):
    """removals: {list rid: [item index, ...]} (removed from the end so indexes stay valid)."""
    count = 0
    for lst, idx in removals.items():
        for i in sorted(set(idx), reverse=True):
            gd.list_remove(lst, "data", i)
            count += 1
    if count:
        gd.set_store_dirty("reliance_list", True)
    return count


def remove_duplicate_conversations(gd):
    """The same support conversation (same two characters, level and type) stored as more than
    one record: keep the record with the lowest support number, drop the others from every
    table. In the game's own data each conversation is one record listed in both characters'
    tables. Returns [(character1, character2, level, kept number, [dropped numbers])]."""
    tables = _entries_by_table(gd)
    groups = {}
    order = []
    for _ti, _lst, items in tables:
        for _i, _p, e in items:
            if not e:
                continue
            c1, c2 = gd.rid(e, "character1"), gd.rid(e, "character2")
            key = (frozenset((c1, c2)), gd.int(e, "support_level"), gd.int(e, "support_type"))
            if key not in groups:
                groups[key] = []
                order.append(key)
            if e not in groups[key]:
                groups[key].append(e)
    drop = set()
    report = []
    for key in order:
        recs = groups[key]
        if len(recs) < 2:
            continue

        def num(e):
            n = gd.int(e, "support_number")
            return n if n is not None else 1 << 30

        keep = min(recs, key=num)
        dropped = [e for e in recs if e != keep]
        drop.update(dropped)
        report.append(
            (gd.rid(keep, "character1"), gd.rid(keep, "character2"), key[1], gd.int(keep, "support_number"),
             [gd.int(e, "support_number") for e in dropped])
        )
    if drop:
        removals = {}
        for _ti, lst, items in tables:
            for i, _p, e in items:
                if e in drop:
                    removals.setdefault(lst, []).append(i)
        _remove_items(gd, removals)
    return report


def remove_misplaced(gd):
    """A conversation listed in the table of a character it does not involve (in addition to
    its own characters' tables): drop that extra listing. Returns the number removed."""
    chars = _characters(gd)
    pos = {c: i for i, c in enumerate(chars)}
    tables = _entries_by_table(gd)
    listed = {}
    for ti, _lst, items in tables:
        for _i, _p, e in items:
            if e:
                listed.setdefault(e, set()).add(ti)
    removals = {}
    for ti, lst, items in tables:
        for i, _p, e in items:
            if not e:
                continue
            own = {pos.get(gd.rid(e, "character1")), pos.get(gd.rid(e, "character2"))}
            if ti not in own and (listed[e] & own):
                removals.setdefault(lst, []).append(i)
    return _remove_items(gd, removals)
