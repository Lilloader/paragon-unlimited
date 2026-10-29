"""Paragon Unlimited - data-driven FE13 skill effects (needs the Paragon Unlimited code.ips, exp04+).

Rules live in an optional block labeled ``PU_SkillFx`` appended to data/GameData.bin:

    u32 count
    count x rule (8 bytes):
        u16 skill      skill id (= position in the skill table)
        u8  effect     see EFFECTS
        u8  when       see CONDITIONS
        u8  and_when   see CONDITIONS
        s8  amount
        u16 reserved   0

The game patch applies every rule whose skill the unit has equipped and whose two conditions
hold, once per battle, on top of the game's own numbers (hit/avoid/crit/dodge, damage,
attack speed). Several rules can belong to the same skill.

The game keeps learned skills in 128 bits per unit, so skill ids 0-127 are usable; the game
itself uses 0-102.
"""
from typing import Dict, List, Optional, Tuple

LABEL = "PU_SkillFx"
MAX_SKILLS = 128  # learned-skill bits per unit in the game (and in save files)
GAME_SKILLS = 103

EFFECTS: Dict[int, str] = {
    0: "(nothing)",
    1: "Damage dealt",
    2: "Damage received",
    3: "Hit",
    4: "Avoid",
    5: "Crit",
    6: "Dodge",
    7: "Attack speed",
}

CONDITIONS: Dict[int, str] = {
    0: "always",
    1: "this unit starts the fight",
    2: "the enemy starts the fight",
    3: "HP is full",
    4: "HP is not full",
    5: "HP is 50% or less",
    6: "on even-numbered turns",
    7: "on odd-numbered turns",
    8: "the enemy is a flier",
    9: "the enemy is on foot",
    10: "the enemy's HP is full",
    11: "the enemy's HP is not full",
    12: "the enemy attacks with magic",
    13: "the enemy attacks with a physical weapon",
    14: "HP is 25% or less",
}

# The game's own simple skills that the patch now runs from rules (their old code was replaced
# by the patch). (RSID, effect, when, and_when, amount)
BUILT_IN_RULES: List[Tuple[str, int, int, int, int]] = [
    ("RSID_命中＋１０", 3, 0, 0, 10),  # Hit Rate +10
    ("RSID_命中＋２０", 3, 0, 0, 20),  # Sure Strike
    ("RSID_回避＋１０", 4, 0, 0, 10),  # Avoid +10
    ("RSID_一発屋", 3, 0, 0, -5),  # Gamble
    ("RSID_一発屋", 5, 0, 0, 10),
]


def root(gd) -> Optional[int]:
    """The PU_SkillFx table record (exists even when the file has no rules yet)."""
    node = None
    try:
        node = gd.node("pu_skill_effects")
    except Exception:
        node = None
    if node is not None and node.rid:
        return node.rid
    # Older Paragon cores do not register the node for an empty optional table: find it.
    try:
        skills = gd.node("skills")
        if skills is None:
            return None
        store = skills.rid >> 32
        base = store << 32
        misses, i = 0, 0
        while misses < 5000:
            try:
                t = gd.type_of(base + i)
            except Exception:
                t = None
            if t is None:
                misses += 1
            else:
                misses = 0
                if t == "PUSkillFxTable":
                    return base + i
            i += 1
    except Exception:
        return None
    return None


def rules(gd) -> List[int]:
    r = root(gd)
    if not r:
        return []
    return gd.items(r, "entries") or []


def rules_for(gd, skill_rid) -> List[int]:
    if not skill_rid:
        return []
    return [e for e in rules(gd) if gd.rid(e, "skill") == skill_rid]


def add_rule(gd, skill_rid, effect=0, when=0, and_when=0, amount=0) -> Optional[int]:
    r = root(gd)
    if not r or not skill_rid:
        return None
    e = gd.list_add(r, "entries")
    gd.set_rid(e, "skill", skill_rid)
    gd.set_int(e, "effect", effect)
    gd.set_int(e, "condition_1", when)
    gd.set_int(e, "condition_2", and_when)
    gd.set_int(e, "value", amount)
    gd.set_store_dirty("gamedata", True)
    return e


def remove_rule(gd, rule_rid) -> bool:
    r = root(gd)
    if not r:
        return False
    n = gd.list_size(r, "entries")
    for i in range(n):
        if gd.list_get(r, "entries", i) == rule_rid:
            gd.list_remove(r, "entries", i)
            gd.set_store_dirty("gamedata", True)
            return True
    return False


def describe(gd, rule_rid, with_skill=True) -> str:
    effect = gd.int(rule_rid, "effect") or 0
    amount = gd.int(rule_rid, "value") or 0
    conds = [gd.int(rule_rid, "condition_1") or 0, gd.int(rule_rid, "condition_2") or 0]
    name = EFFECTS.get(effect, f"effect {effect}")
    if effect == 0:
        text = "(no effect)"
    else:
        text = f"{name} {amount:+d}"
    when = [CONDITIONS.get(c, f"condition {c}") for c in conds if c]
    if when:
        text += " when " + " and ".join(when)
    if with_skill:
        skill = gd.rid(rule_rid, "skill")
        label = gd.display(skill) if skill else "(no skill)"
        text = f"{label}: {text}"
    return text


def skill_by_rsid(gd, rsid) -> Optional[int]:
    try:
        return gd.key_to_rid("skills", rsid)
    except Exception:
        return None


def ensure_built_in_rules(gd) -> int:
    """Add the rules for the game skills whose old code the patch replaced, if missing.
    Returns how many were added."""
    added = 0
    have = set()
    for e in rules(gd):
        s = gd.rid(e, "skill")
        have.add((s, gd.int(e, "effect"), gd.int(e, "condition_1"), gd.int(e, "condition_2"), gd.int(e, "value")))
    for rsid, eff, c1, c2, amt in BUILT_IN_RULES:
        s = skill_by_rsid(gd, rsid)
        if s and (s, eff, c1, c2, amt) not in have:
            if add_rule(gd, s, eff, c1, c2, amt):
                added += 1
    return added


def skill_count(gd) -> int:
    node = gd.node("skills")
    if node is None:
        return 0
    return gd.list_size(node.rid, "skills")


def check(gd) -> List[str]:
    """Problems that would break the game; empty if fine."""
    problems = []
    n = skill_count(gd)
    if n > MAX_SKILLS:
        problems.append(
            f"There are {n} skills; the game can only keep {MAX_SKILLS} (ids 0-{MAX_SKILLS - 1}) per unit. "
            f"Skills after id {MAX_SKILLS - 1} can never be learned."
        )
    for e in rules(gd):
        if not gd.rid(e, "skill"):
            problems.append("A skill effect has no skill set (it does nothing).")
            break
    return problems


def cleanup(gd) -> int:
    """Drop rules with no skill. Returns how many were removed."""
    r = root(gd)
    if not r:
        return 0
    removed, i = 0, 0
    while i < gd.list_size(r, "entries"):
        e = gd.list_get(r, "entries", i)
        if not gd.rid(e, "skill"):
            gd.list_remove(r, "entries", i)
            removed += 1
        else:
            i += 1
    return removed
