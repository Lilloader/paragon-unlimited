"""Paragon Unlimited – FE13 (Awakening) save-time consistency fixes and validation.

Background (verified against Awakening USA v0.0.0 code.bin, see docs/PARAGON_UNLIMITED.md):

* The game stores the static-list position of PID_ダミー in a global (0x4D0BA8) and treats
  every character position below it as "may have a RelianceList table".
* gameMainMenu::extra::ProcSupportTalk (0x1B3DAC) loops over all those positions and
  dereferences RelianceList.tables[pos] without a null check.
* Therefore RelianceList MUST contain one table pointer for every static position below
  PID_ダミー, otherwise Extras -> Support crashes before a save is loaded.
* Every character has exactly 52 support partner slots (Person +0x88). The game loops
  0..0x33 in several places and keeps support points in a fixed 52 byte array per unit.

The preprocessor fixes the first point automatically (adds empty tables, same as vanilla
does for characters without supports) and reports problems it cannot fix safely.
"""

import logging
from dataclasses import dataclass, field
from typing import List, Optional

from paragon.unlimited.supports import extra_slots
from paragon.core.services.write_preprocessors import WritePreprocessors

DUMMY_PID = "PID_ダミー"
BASE_SUPPORT_SLOTS = extra_slots.BASE_SLOTS  # built into every character record
SUPPORT_SLOTS = extra_slots.TOTAL_SLOTS  # with the Paragon Unlimited code.ips
VANILLA_MAX_SUPPORT_NUMBER = 1829
# The game keeps a "seen" flag per support number in a 0x780-bit (1920) array (created in
# 0x108AE4, object +0x14; set by 0x2B43C4 without a range check). Numbers 1920+ write past it.
SUPPORT_NUMBER_LIMIT = 1920
# With the Paragon Unlimited code patch the array has 4096 bits (0x108B30: movne r1, #0x1000).
SUPPORT_NUMBER_LIMIT_PATCHED = 4096
_PATCH_HINT = "the game code patch (Unlimited -> Install Game Code Patch)"
_PATCH_OFFSET = 0x108B30 - 0x100000
_PATCH_BYTES = bytes.fromhex("011aa013")


def ips_has_support_number_patch(ips: bytes) -> bool:
    """True when an IPS patch for code.bin contains the 4096 support-number change."""
    if ips[:5] != b"PATCH":
        return False
    p = 5
    while p + 3 <= len(ips) and ips[p : p + 3] != b"EOF":
        off = int.from_bytes(ips[p : p + 3], "big")
        n = int.from_bytes(ips[p + 3 : p + 5], "big")
        p += 5
        if n == 0:
            p += 3
            continue
        data = ips[p : p + n]
        p += n
        if off <= _PATCH_OFFSET and _PATCH_OFFSET + 4 <= off + n:
            k = _PATCH_OFFSET - off
            if data[k : k + 4] == _PATCH_BYTES:
                return True
    return False


_limit_cache = {}


def support_number_limit(force=None) -> int:
    """1920, or 4096 when the code.ips in the emulator's mod folder has the 4096 change."""
    if force is not None:
        return force
    if "v" in _limit_cache:
        return _limit_cache["v"]
    limit = SUPPORT_NUMBER_LIMIT
    try:
        from paragon.unlimited.tools import azahar
        from paragon.unlimited.tools import code_patch

        for path in code_patch.installed_paths(azahar.detect_mod_root()):
            with open(path, "rb") as f:
                if ips_has_support_number_patch(f.read()):
                    limit = SUPPORT_NUMBER_LIMIT_PATCHED
            break  # the first one found (mods/<title>/code.ips, then exefs/code.ips)
    except Exception:
        logging.exception("Could not read the installed code.ips.")
    _limit_cache["v"] = limit
    return limit
NO_SUPPORT_THRESHOLDS = 0x63636363  # all four thresholds = 99 -> rank never reached


@dataclass
class ValidationIssue:
    severity: str  # "fixed", "error", "warning", "info"
    message: str


@dataclass
class ValidationReport:
    issues: List[ValidationIssue] = field(default_factory=list)
    # (character rid, partner rid, thresholds) where the partner does not list the character back.
    one_sided: List[tuple] = field(default_factory=list)
    # (character1 rid, character2 rid) of support conversations no support slot reaches.
    unassigned: List[tuple] = field(default_factory=list)

    def add(self, severity: str, message: str):
        self.issues.append(ValidationIssue(severity, message))
        log = {
            "error": logging.error,
            "warning": logging.warning,
        }.get(severity, logging.info)
        log(f"[FE13 validation] {severity.upper()}: {message}")

    def by_severity(self, severity: str) -> List[ValidationIssue]:
        return [i for i in self.issues if i.severity == severity]

    def needs_attention(self) -> bool:
        return any(i.severity in ("error", "warning", "fixed") for i in self.issues)

    def to_text(self, limit_per_section: int = 40) -> str:
        lines = []
        titles = {
            "fixed": "Fixed automatically",
            "error": "Errors (will misbehave in game)",
            "warning": "Warnings",
            "info": "Info",
        }
        for sev in ("fixed", "error", "warning", "info"):
            items = self.by_severity(sev)
            if not items:
                continue
            lines.append(f"== {titles[sev]} ({len(items)}) ==")
            for it in items[:limit_per_section]:
                lines.append(" - " + it.message)
            if len(items) > limit_per_section:
                lines.append(f" ... and {len(items) - limit_per_section} more (see paragon.log)")
            lines.append("")
        return "\n".join(lines) if lines else "No problems found."


class FE13WritePreprocessors(WritePreprocessors):
    def __init__(self):
        self.last_report: Optional[ValidationReport] = None

    def invoke(self, gd):
        report = ValidationReport()
        try:
            ctx = _Context.create(gd, report)
            if ctx is not None:
                pad_reliance_tables(ctx)
                tidy_reliance(ctx)
                sync_reliance_pairs(ctx)
                tidy_placeholder_slots(ctx)
                tidy_support_ex(ctx)
                validate(ctx)
        except Exception:
            logging.exception("FE13 support validation failed (save continues).")
            report.add("warning", "Support validation crashed - see paragon.log.")
        try:
            tidy_skills(gd, report)
        except Exception:
            logging.exception("FE13 skill checks failed (save continues).")
            report.add("warning", "Skill checks crashed - see paragon.log.")
        try:
            tidy_class_slots(gd, report)
        except Exception:
            logging.exception("FE13 class slot checks failed (save continues).")
            report.add("warning", "Class slot checks crashed - see paragon.log.")
        try:
            pad_sprite_lists(gd, report)
        except Exception:
            logging.exception("FE13 sprite list check failed (save continues).")
            report.add("warning", "Sprite list check crashed - see paragon.log.")
        try:
            fix_win_rules(gd, report)
        except Exception:
            logging.exception("FE13 win rule check failed (save continues).")
            report.add("warning", "Win rule check crashed - see paragon.log.")
        self.last_report = report
        return report


class _Context:
    def __init__(self, gd, report, chars_rid, chars_field, rel_rid):
        self.gd = gd
        self.report = report
        self.chars_rid = chars_rid
        self.chars_field = chars_field
        self.rel_rid = rel_rid
        self.characters = gd.items(chars_rid, chars_field) or []
        self.position = {rid: i for i, rid in enumerate(self.characters)}

    @staticmethod
    def create(gd, report):
        table = gd.table("characters")
        if not table:
            report.add("warning", "Character table not found; skipped support checks.")
            return None
        node = gd.node("reliance_list")
        if not node or not node.rid:
            report.add("warning", "RelianceList not loaded; skipped support checks.")
            return None
        return _Context(gd, report, table[0], table[1], node.rid)

    def name(self, rid) -> str:
        if rid is None:
            return "<none>"
        key = self.gd.key(rid)
        disp = None
        try:
            disp = self.gd.display(rid)
        except Exception:
            pass
        pos = self.position.get(rid)
        base = key or "<no PID>"
        if disp and disp != key:
            base = f"{disp} ({base})"
        return f"{base} #{pos}" if pos is not None else base

    def dummy_position(self) -> Optional[int]:
        for i, rid in enumerate(self.characters):
            if self.gd.key(rid) == DUMMY_PID:
                return i
        return None

    def tables(self):
        return self.gd.items(self.rel_rid, "tables") or []

    def table_entries(self, table_ptr_rid):
        rel = self.gd.rid(table_ptr_rid, "data")
        if not rel:
            return None
        out = []
        for p in self.gd.items(rel, "data") or []:
            d = self.gd.rid(p, "data")
            if d:
                out.append(d)
        return out


def pad_reliance_tables(ctx: _Context):
    gd, report = ctx.gd, ctx.report
    dummy = ctx.dummy_position()
    if dummy is None:
        report.add(
            "error",
            f"{DUMMY_PID} is missing from the static character list. The game uses its position "
            "as the character count; supports will not work correctly.",
        )
        return
    tables = ctx.tables()
    # Repair table pointers that lost their record (would serialize as NULL).
    store = gd.store_number_of(ctx.rel_rid)
    repaired = 0
    for t in tables:
        if not gd.rid(t, "data"):
            gd.set_rid(t, "data", gd.new_instance("RelianceList", store))
            repaired += 1
    added = 0
    while len(tables) + added < dummy:
        ptr = gd.list_add(ctx.rel_rid, "tables")
        gd.set_rid(ptr, "data", gd.new_instance("RelianceList", store))
        added += 1
    if added or repaired:
        gd.set_store_dirty("reliance_list", True)
        msg = []
        if added:
            msg.append(
                f"added {added} empty RelianceList table(s) (now {len(tables) + added}, "
                f"one per character before {DUMMY_PID} at #{dummy})"
            )
        if repaired:
            msg.append(f"repaired {repaired} table(s) with no list")
        report.add("fixed", "; ".join(msg) + ". This prevents the Extras -> Support crash.")


def tidy_reliance(ctx: _Context):
    from paragon.unlimited.supports import reliance_repair

    dups = reliance_repair.remove_duplicate_conversations(ctx.gd)
    if dups:
        lines = []
        for c1, c2, lvl, kept, dropped in dups[:12]:
            lines.append(
                f"{ctx.name(c1)} x {ctx.name(c2)} level {lvl}: kept #{kept}, removed "
                + ", ".join(f"#{n}" for n in dropped)
            )
        more = f"; ... and {len(dups) - 12} more" if len(dups) > 12 else ""
        ctx.report.add(
            "fixed",
            f"removed duplicate copies of {len(dups)} support conversation(s) (the same two characters "
            "and level stored more than once; the copy with the lowest support number is kept): "
            + "; ".join(lines) + more,
        )
    misplaced = reliance_repair.remove_misplaced(ctx.gd)
    if misplaced:
        ctx.report.add(
            "fixed",
            f"removed {misplaced} support conversation listing(s) from the list of a character "
            "the conversation does not involve.",
        )


def tidy_placeholder_slots(ctx: _Context):
    from paragon.unlimited.supports import support_tools

    cleared = support_tools.clear_placeholder_slots(ctx.gd, ctx.characters)
    if cleared:
        names = ", ".join(f"{ctx.name(c)} ({n})" for c, n in cleared[:10])
        ctx.report.add(
            "fixed",
            f"cleared placeholder support slots (one partner repeated in many slots with support "
            f"type None, which does nothing in game): {names}.",
        )


def sync_reliance_pairs(ctx: _Context):
    from paragon.unlimited.supports import reliance_repair

    added = reliance_repair.sync_pairs(ctx.gd)
    if added:
        ctx.report.add(
            "fixed",
            f"listed {added} support conversation(s) in the partner's list too "
            "(each conversation belongs in both characters' lists, as in vanilla).",
        )


def tidy_support_ex(ctx: _Context):
    gd, report = ctx.gd, ctx.report
    try:
        dirty = gd.store_is_dirty("characters")
    except Exception:
        dirty = False
    if not dirty:
        return  # static.bin is not being written; leave it alone
    _empty, orphan = extra_slots.cleanup(gd)
    if orphan:
        report.add(
            "fixed",
            f"removed {orphan} extra-slot set(s) (#052-#059) whose character no longer exists.",
        )


def fixed_win_rule(source: str) -> Optional[str]:
    """A Map Maker chapter script with the win rule of earlier versions, which had the game's two
    rule bits the wrong way round (0x20000 is "no enemy left", 0x40000 "no boss left"): the
    corrected script, or None when it is fine."""
    import json

    from paragon.unlimited.map_maker import chapter_builder as cm

    plan_line = next((l for l in source.splitlines() if l.startswith(cm.PLAN_MARK)), None)
    if plan_line is None:
        return None
    try:
        win = json.loads(plan_line[len(cm.PLAN_MARK):]).get("win", "rout")
    except ValueError:
        return None
    swap = {"rout": (cm.WIN_BOSS, cm.WIN_ROUT), "boss": (cm.WIN_ROUT, cm.WIN_BOSS)}.get(win)
    if not swap:
        return None
    old = f"    ev::ChapterSetWinRule({swap[0]});"
    if old not in source.split("callback[0x8]")[0]:
        return None
    return source.replace(old, f"    ev::ChapterSetWinRule({swap[1]});", 1)


def fix_win_rules(gd, report):
    """Corrects the win rule of chapters saved by earlier Map Maker versions (U001-U009)."""
    from paragon.unlimited.map_maker import chapter_builder as cm

    if not hasattr(gd, "get_script_nodes"):
        return
    names = {f"exalt/scripts/{c}.exl".lower(): c for c in cm.SLOT_IDS}
    fixed = []
    for n in gd.get_script_nodes():
        cid = names.get(n.path.replace("\\", "/").lower())
        if not cid:
            continue
        try:
            src = gd.open_script(n)
        except Exception:
            continue
        new = fixed_win_rule(src or "")
        if new:
            gd.update_script(n, new)
            fixed.append(cid)
    if fixed:
        report.add("fixed", "Map Maker chapters " + ", ".join(fixed) + ": win condition corrected "
                   "(earlier versions mixed up 'Defeat every enemy' and 'Defeat the boss').")


def pad_sprite_lists(gd, report):
    """Every character's sprite list (Sprite Data: one entry per class) as long as the class
    list. The game reads the entry for the unit's class without checking the list's length, so a
    class added after the lists were made would read past the end of a short list.

    Lists are kept at an even length: an odd one is followed by 2 zero bytes of padding, which
    reads back as one more entry pointing at sprite 0 (the dummy). Such a trailing entry is
    cleared."""
    try:
        jobs = gd.table("jobs")
        chars = gd.table("characters")
        icons = gd.table("bmap_icons")
    except Exception:
        return
    if not jobs or not chars:
        return
    need = len(gd.items(jobs[0], jobs[1]) or [])
    need += need % 2
    dummy = None
    try:
        first = (gd.items(icons[0], icons[1]) or [None])[0] if icons else None
        if first is not None and (gd.string(first, "name") or "").startswith("ダミー"):
            dummy = first
    except Exception:
        dummy = None
    seen, grown, cleared = set(), 0, 0
    for c in gd.items(chars[0], chars[1]) or []:
        try:
            sd = gd.rid(c, "sprite_data")
        except Exception:
            sd = None
        if not sd or sd in seen:
            continue
        seen.add(sd)
        n = gd.list_size(sd, "entries")
        if n == 0:
            continue
        last = gd.list_get(sd, "entries", n - 1)
        if dummy is not None and gd.rid(last, "bmap_icon") == dummy:
            gd.set_rid(last, "bmap_icon", None)
            cleared += 1
        target = max(need, n + n % 2)
        if n < target:
            for _ in range(n, target):
                e = gd.list_add(sd, "entries")
                gd.set_rid(e, "bmap_icon", None)
            grown += 1
    if grown or cleared:
        gd.set_store_dirty("characters", True)
    if grown:
        report.add("fixed", f"made {grown} character sprite list(s) as long as the class list ({need} entries).")
    if cleared:
        report.add("fixed", f"cleared a stray last sprite list entry (left by padding) for {cleared} character(s).")


def tidy_class_slots(gd, report):
    """Reclass slots 4-5: drop empty / orphaned entries. Second Seal lists over 64 classes."""
    from paragon.unlimited.characters import class_slots as cs

    try:
        chars_dirty = gd.store_is_dirty("characters")
    except Exception:
        chars_dirty = False
    if chars_dirty:
        _empty, orphan = cs.cleanup(gd)
        if orphan:
            report.add("fixed", f"removed {orphan} reclass 4-5 set(s) whose character no longer exists.")
    try:
        table = gd.table("characters")
        people = gd.items(table[0], table[1]) if table else []
    except Exception:
        people = []
    for p in people:
        for g in cs.GENDERS:
            try:
                n = cs.seal_list_size(gd, p, g)
            except Exception:
                n = 0
            if n > cs.SEAL_LIST_MAX:
                try:
                    who = gd.display(p) or gd.key(p)
                except Exception:
                    who = "a character"
                report.add(
                    "warning",
                    f"{who} ({g}): a Second Seal list could have {n} classes with promotions; "
                    f"the game holds {cs.SEAL_LIST_MAX} and leaves the rest out.",
                )


def tidy_skills(gd, report):
    """Paragon Unlimited skills: id limit, list order byte for added skills, effect rules."""
    from paragon.unlimited.skills import skill_effects as fx

    try:
        dirty = gd.store_is_dirty("gamedata")
    except Exception:
        dirty = False
    if not dirty:
        return
    node = gd.node("skills")
    if node is not None:
        for r in gd.items(node.rid, "skills") or []:
            sid = gd.int(r, "id") or 0
            if sid < fx.GAME_SKILLS:
                continue
            raw = bytearray(gd.bytes(r, "unknown") or b"\0\0\0")
            if len(raw) >= 2 and raw[1] == 0 and sid < 256:
                raw[1] = sid  # list order in the skill menus (the game sorts by it)
                gd.set_bytes(r, "unknown", bytes(raw))
    if not fx.rules(gd) and fx.root(gd) is not None:
        added = fx.ensure_built_in_rules(gd)
        if added:
            report.add(
                "info",
                f"added the {added} effect lines for Hit Rate +10, Sure Strike, Avoid +10 and Gamble "
                "(with the game code patch these skills work from their effect lines).",
            )
    removed = fx.cleanup(gd)
    if removed:
        report.add("fixed", f"removed {removed} skill effect line(s) with no skill.")
    for msg in fx.check(gd):
        report.add("error", msg)


def validate(ctx: _Context):
    gd, report = ctx.gd, ctx.report
    dummy = ctx.dummy_position()
    tables = ctx.tables()

    # ---- Person support slots -------------------------------------------------
    slots = {}  # rid -> {partner_rid: thresholds}
    extra_users = []
    owners_seen = {}
    for e in extra_slots.entries(gd):
        owner = gd.rid(e, "owner")
        if owner is None:
            continue
        if owner in owners_seen:
            report.add(
                "warning",
                f"{ctx.name(owner)} has more than one set of extra slots #052-#059; "
                "the game only uses the first one.",
            )
        else:
            owners_seen[owner] = e
    for rid in ctx.characters:
        mine = {}
        all_slots = extra_slots.all_slots(gd, rid)
        used = len(all_slots)
        if any(k >= BASE_SUPPORT_SLOTS for k, _p, _t in all_slots):
            extra_users.append(rid)
        for k, partner, thr in all_slots:
            if thr is not None and (thr & 0xFFFFFFFF) == NO_SUPPORT_THRESHOLDS:
                continue
            if partner in mine:
                report.add(
                    "warning",
                    f"{ctx.name(rid)} lists {ctx.name(partner)} in more than one support slot; "
                    "only the first one is used.",
                )
                continue
            mine[partner] = thr
        slots[rid] = mine
        if used >= SUPPORT_SLOTS:
            report.add(
                "warning",
                f"{ctx.name(rid)} uses all {SUPPORT_SLOTS} support slots (Paragon Unlimited limit).",
            )
        elif used >= SUPPORT_SLOTS - 4:
            report.add(
                "info",
                f"{ctx.name(rid)} uses {used}/{SUPPORT_SLOTS} support slots.",
            )
        for partner in mine:
            if partner == rid:
                report.add("warning", f"{ctx.name(rid)} lists themself as a support partner.")
    if extra_users:
        names = ", ".join(ctx.name(r) for r in extra_users[:10])
        more = f" and {len(extra_users) - 10} more" if len(extra_users) > 10 else ""
        report.add(
            "info",
            f"{len(extra_users)} character(s) use extra slots #052-#059 ({names}{more}). "
            f"These only work in game with {_PATCH_HINT}.",
        )

    for rid, mine in slots.items():
        for partner in mine:
            other = slots.get(partner)
            if other is not None and rid not in other:
                report.one_sided.append((rid, partner, mine[partner]))
                report.add(
                    "warning",
                    f"{ctx.name(rid)} lists {ctx.name(partner)} as a partner, but not the other way round.",
                )

    # ---- RelianceList ----------------------------------------------------------
    by_number = {}
    for ti, t in enumerate(tables):
        entries = ctx.table_entries(t)
        if entries is None:
            continue
        for e in entries:
            c1, c2 = gd.rid(e, "character1"), gd.rid(e, "character2")
            p1, p2 = ctx.position.get(c1), ctx.position.get(c2)
            num = gd.int(e, "support_number")
            lvl = gd.int(e, "support_level")
            if p1 is None or p2 is None:
                report.add("error", f"RelianceList table #{ti}: entry references a missing character.")
                continue
            if ti not in (p1, p2):
                report.add(
                    "warning",
                    f"RelianceList table #{ti} contains {ctx.name(c1)} x {ctx.name(c2)}, "
                    f"which belongs in table #{p1} or #{p2}.",
                )
            if dummy is not None and (p1 >= dummy or p2 >= dummy):
                report.add(
                    "error",
                    f"Support {ctx.name(c1)} x {ctx.name(c2)} uses a character placed after {DUMMY_PID}; "
                    "the game will ignore it. Move the character above PID_ダミー.",
                )
            stype = gd.int(e, "support_type")
            # Type 0 = normal support (needs a slot). Types 1/2 are family supports that the
            # game unlocks through parent/sibling relations instead of slots.
            if stype == 0 and c2 not in slots.get(c1, {}) and c1 not in slots.get(c2, {}):
                if (c1, c2) not in report.unassigned and (c2, c1) not in report.unassigned:
                    report.unassigned.append((c1, c2))
                report.add(
                    "warning",
                    f"Support conversation {ctx.name(c1)} x {ctx.name(c2)} level {lvl} exists, but neither "
                    "character has the other in a support slot, so it can never be reached.",
                )
            if num is not None:
                by_number.setdefault(num, set()).add(
                    (min(p1, p2), max(p1, p2), gd.int(e, "support_type"), lvl)
                )

    for num, pairs in sorted(by_number.items()):
        if len(pairs) > 1:
            desc = ", ".join(
                f"{ctx.name(ctx.characters[a])} x {ctx.name(ctx.characters[b])} L{lv}"
                for a, b, _t, lv in sorted(pairs)
            )
            report.add(
                "warning",
                f"Support number {num} is shared by different supports ({desc}); "
                "viewing one marks the other as seen.",
            )
    limit = support_number_limit(getattr(ctx, "number_limit", None))
    too_high = sorted(n for n in by_number if n is not None and n >= limit)
    if too_high:
        if limit == SUPPORT_NUMBER_LIMIT:
            fix = (
                f"Install {_PATCH_HINT}: it makes room for 4096. Or give them "
                "numbers below the limit."
            )
        else:
            fix = "Give them numbers below the limit."
        report.add(
            "error",
            f"{len(too_high)} support conversation number(s) are {limit} or higher "
            f"(#{too_high[0]}-#{too_high[-1]}). The game has 'seen' flags for numbers 0-"
            f"{limit - 1} only; viewing one of these writes past them (memory corruption "
            f"or a crash). {fix}",
        )
    over = [n for n in by_number if n is not None and VANILLA_MAX_SUPPORT_NUMBER < n < limit]
    if over:
        extra = (
            " (the game code patch is installed: room for 4096)"
            if limit == SUPPORT_NUMBER_LIMIT_PATCHED
            else ""
        )
        report.add(
            "info",
            f"{len(over)} support numbers are above the game's own maximum {VANILLA_MAX_SUPPORT_NUMBER}; "
            f"the limit is {limit - 1}{extra}.",
        )
    if limit == SUPPORT_NUMBER_LIMIT_PATCHED and any(
        n is not None and n >= SUPPORT_NUMBER_LIMIT for n in by_number
    ):
        report.add(
            "info",
            f"Support numbers 1920 and up only work with {_PATCH_HINT}; "
            "without it they can crash the game.",
        )

    # ---- Sort ids --------------------------------------------------------------
    seen = {}
    for rid in ctx.characters:
        v = gd.int(rid, "id")
        if v is None:
            continue
        if v in seen:
            report.add(
                "info",
                f"{ctx.name(rid)} and {ctx.name(seen[v])} share sort id {v} (only affects list order).",
            )
        else:
            seen[v] = rid


def used_support_numbers(gd) -> set:
    node = gd.node("reliance_list")
    used = set()
    if node and node.rid:
        for t in gd.items(node.rid, "tables") or []:
            rel = gd.rid(t, "data")
            if not rel:
                continue
            for p in gd.items(rel, "data") or []:
                d = gd.rid(p, "data")
                if d:
                    n = gd.int(d, "support_number")
                    if n is not None:
                        used.add(n)
    return used


def next_free_support_number(gd, limit=None) -> int:
    """Lowest support number above every number in use; when that would reach the game's limit
    (1920, or 4096 with the code patch), the lowest unused number below the limit; when none
    is left, the highest number in use + 1 (the support check then reports it)."""
    limit = support_number_limit(limit)
    used = used_support_numbers(gd)
    nxt = (max(used) + 1) if used else 0
    if nxt < limit:
        return nxt
    for n in range(limit):
        if n not in used:
            return n
    return nxt


def add_missing_partners(gd, one_sided):
    """For every (A, B, thresholds) where A lists B but B does not list A, put A into B's first
    free support slot (#000-#051, then the Unlimited slots #052-#059) with the same thresholds.

    If B already has A with support type "None", that slot gets A's support type instead.
    Returns (added, failed): lists of (A, B, slot index) and (A, B) for which B had no free slot.
    """
    added, failed = [], []
    done = set()
    for a, b, thr in one_sided:
        if (a, b) in done:
            continue
        done.add((a, b))
        existing = [(k, t) for k, p, t in extra_slots.all_slots(gd, b) if p == a]
        if any(t is None or (t & 0xFFFFFFFF) != NO_SUPPORT_THRESHOLDS for _k, t in existing):
            continue  # already listed for real (an earlier fix in this run may have added it)
        if existing:
            # B lists A, but with "None" (99/99/99/99): give that slot A's support type.
            k = existing[0][0]
            target = b if k < BASE_SUPPORT_SLOTS else extra_slots.find_entry(gd, b)
            gd.set_int(target, f"support_type_{k:03}", thr if thr is not None else NO_SUPPORT_THRESHOLDS)
            added.append((a, b, k))
            continue
        slot = None
        for k in range(BASE_SUPPORT_SLOTS):
            if gd.rid(b, f"support_character_{k:03}") is None:
                gd.set_rid(b, f"support_character_{k:03}", a)
                gd.set_int(b, f"support_type_{k:03}", thr if thr is not None else NO_SUPPORT_THRESHOLDS)
                slot = k
                break
        if slot is None:
            entry = extra_slots.ensure_entry(gd, b)
            if entry:
                for k in extra_slots.EXTRA_RANGE:
                    if extra_slots.slot_partner(gd, entry, k) is None:
                        gd.set_rid(entry, f"support_character_{k:03}", a)
                        gd.set_int(entry, f"support_type_{k:03}", thr if thr is not None else NO_SUPPORT_THRESHOLDS)
                        slot = k
                        break
        if slot is None:
            failed.append((a, b))
        else:
            added.append((a, b, slot))
    if added:
        gd.set_store_dirty("characters", True)
    return added, failed
