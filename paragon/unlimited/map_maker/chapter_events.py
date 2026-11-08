"""Paragon Unlimited - events of Paralogue Maker chapters (FE13).

Everything here becomes part of the chapter's own scripts (exalt), written the way the game's
chapters write the same things:

* Talk events          callback[0x12](A, B, 0, flag)   two characters talk (the "Talk" command);
                        a recruit talk also moves B to your army (as Kellam in Chapter 3).
* Battle quotes        callback[0x13](enemy, opponent, 1, flag)   before a fight with that unit;
                        opponent "" = anyone, or one character (as the Chapter 4 Marth vs Chrom).
* Turn conversations   callback[0xC](turn, turn, 0)   at the start of a player turn.
* Tile events          callback[0x10](x, y, x, y, 0, "")   after a unit (or one character)
                        acts on the tile, as the DLC's tent events: a conversation, then items or gold.
* Chests and villages  callback[0x11](x, y, kind, model, "") in <chapter>_Terrain:
                        kind 15 = chest, 8 = village / house (as in every game chapter); the
                        game's TrickSet then opens the chest or closes the village.

Every event happens once: it sets its own flag (registered in callback[0x6], like the game).

Scenes: talk, turn and tile events can also play a scene the way the DLC does it (Hot Spring
Scramble, E022_Taiki_Tiamo): the map fades out, the dark event stage opens and full-screen
pictures (telops, telop/<name>.r.lz) play one after another, each with its own conversation; then
the map comes back and the "after" conversation plays.
"""
import re
from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional, Tuple

CHEST_KIND = 15
CHEST_MODEL = 19
VILLAGE_KIND = 8
VILLAGE_MODEL = 1
CHEST_TILES = {43}  # TID_宝箱
VILLAGE_TILES = {22, 25, 54, 64}  # village, house, (illusory) village, snowy village


SCENE_STAGE = ("evt006_op2_06", "暗闇_何もなし")  # the dark stage of Chapter 6 and the DLC scenes


@dataclass
class SceneStep:
    picture: str = ""  # telop name ("Tlp_Ev_c001", "Tlp_PU_U001_1"); "" = keep the last one
    lines: list = field(default_factory=list)
    sound: str = ""  # sound effect before the conversation (SE_...)


@dataclass
class TalkEvent:
    a: str = ""  # PID of the one who talks (the "Talk" command is theirs)
    b: str = ""  # PID of the one talked to
    lines: list = field(default_factory=list)  # [Line]
    recruit: bool = False  # b joins your army
    scene: list = field(default_factory=list)  # [SceneStep]
    after: list = field(default_factory=list)  # [Line] on the map after the scene


@dataclass
class TurnEvent:
    turn: int = 1
    lines: list = field(default_factory=list)
    scene: list = field(default_factory=list)
    after: list = field(default_factory=list)


@dataclass
class TileEvent:
    x: int = 0
    y: int = 0
    who: str = ""  # PID that must wait on the tile ("" = any of your units)
    lines: list = field(default_factory=list)
    item: str = ""  # IID given to the unit
    gold: int = 0
    scene: list = field(default_factory=list)
    after: list = field(default_factory=list)
    sparkle: bool = True  # a red flash on the tile (with the camera on it) until the event happens
    flash_every: int = 5  # ... at the start of every Nth player turn (0 = never)


@dataclass
class Treasure:
    """A chest or a village / house visit."""

    x: int = 0
    y: int = 0
    kind: int = CHEST_KIND
    model: int = CHEST_MODEL
    item: str = ""
    gold: int = 0
    lines: list = field(default_factory=list)  # village talk (chests have none)

    @property
    def is_chest(self) -> bool:
        return self.kind == CHEST_KIND


@dataclass
class BattleQuote:
    enemy: str = ""  # PID of the enemy unit (its own person)
    vs: str = ""  # PID of the opponent ("" = anyone)
    face: str = ""  # portrait of the enemy (FID)
    text: str = ""


def lines_to_json(lines) -> list:
    return [asdict(l) if not isinstance(l, dict) else l for l in lines]


def scene_from_json(data, line_cls) -> list:
    out = []
    for st in data or []:
        if isinstance(st, dict):
            st = SceneStep(st.get("picture", ""), lines_from_json(st.get("lines"), line_cls), st.get("sound", ""))
        else:
            st.lines = lines_from_json(st.lines, line_cls)
        out.append(st)
    return out


def lines_from_json(data, line_cls) -> list:
    return [line_cls(**l) if isinstance(l, dict) else l for l in data or []]


def event_from_json(cls, d, line_cls):
    obj = cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})
    if hasattr(obj, "lines"):
        obj.lines = lines_from_json(obj.lines, line_cls)
    if hasattr(obj, "scene"):
        obj.scene = scene_from_json(obj.scene, line_cls)
        obj.after = lines_from_json(obj.after, line_cls)
    return obj


# ----------------------------------------------------------------------------- chapter script


def _flag(name: str) -> str:
    return f"PU_{name}"


def event_flags(plan) -> List[str]:
    out = []
    out += [_flag(f"TK{i}") for i, _e in enumerate(plan.talks, 1)]
    out += [_flag(f"BT{i}") for i, _e in enumerate(plan.quotes, 1)]
    out += [_flag(f"EV{i}") for i, _e in enumerate(plan.tile_events, 1)]
    if seize_tile(plan):
        out.append(_flag("WIN"))
    return out


# ----------------------------------------------------------------------------- win conditions
# The game itself knows two win rules (ChapterSetWinRule; checked after every unit's action,
# code.bin 0x397d80): 0x20000 = no enemy unit is left, 0x40000 = no enemy leader (boss) is left.
# Seize and Survive chapters start with 0x10000 (not a winning rule; it picks their own banner with
# the game code patch) and, when their goal is met, switch to the
# "no enemy left" rule and take the enemy army off the map (ForceUnitDelete, as the game's own
# ending events do): the chapter is won as soon as a unit finishes its action.
RULE_NO_ENEMIES = 0x20000
RULE_NO_LEADER = 0x40000
PLAYER_FORCE, ENEMY_FORCE = 0, 1


def seize_tile(plan) -> Optional[Tuple[int, int]]:
    s = getattr(plan, "seize", None) or []
    if getattr(plan, "win", "") == "seize" and len(s) == 2:
        return int(s[0]), int(s[1])
    return None


def survive_turn(plan) -> Optional[int]:
    """The turn whose start ends a Survive chapter (turns to survive + 1)."""
    if getattr(plan, "win", "") == "survive":
        return max(1, int(getattr(plan, "survive_turns", 8) or 8)) + 1
    return None


def victory_lines() -> List[str]:
    return [
        f"ev::ChapterSetWinRule({RULE_NO_ENEMIES});",
        "ev::FadeOut(3, 0, 500);",
        "ev::FadeWait();",
        f"ev::ForceUnitDelete({ENEMY_FORCE});",
        "ev::FadeIn(3, 0, 500);",
        "ev::FadeWait();",
    ]


SPARKLE = "スポット異界の門"  # an effect the game never plays; its file is the red sparkle (event_sparkle.py)


def flashes(plan, e) -> int:
    """Every how many turns the event tile flashes (0 = never). DLC chapters never flash: they
    have many events of their own."""
    if str(getattr(plan, "cid", "")).startswith("E") or not getattr(e, "sparkle", True):
        return 0
    return max(0, int(getattr(e, "flash_every", 5) or 0))


def event_variables(plan) -> List[str]:
    """Script variables (registered in callback[0x6] with VariableEntry, as the DLC does)."""
    return [_flag(f"NX{i}") for i, e in enumerate(plan.tile_events, 1) if flashes(plan, e)]


def event_messages(plan, conversation, boss_talk) -> Dict[str, Optional[str]]:
    """{message key: text} of every event conversation (the chapter's m/<cid> file)."""
    c = plan.cid
    out = {}
    for i, e in enumerate(plan.talks, 1):
        out[f"MID_{c}_PU_TK{i}"] = conversation(e.lines) or None
        _scene_messages(out, f"MID_{c}_PU_TK{i}", e, conversation)
    for i, q in enumerate(plan.quotes, 1):
        face = q.face[4:] if q.face.startswith("FID_") else q.face
        out[f"MID_{c}_PU_BT{i}"] = boss_talk(face, q.text) if face and q.text.strip() else None
    for i, e in enumerate(plan.turn_events, 1):
        out[f"MID_{c}_PU_TURN{i}"] = conversation(e.lines) or None
        _scene_messages(out, f"MID_{c}_PU_TURN{i}", e, conversation)
    for i, e in enumerate(plan.tile_events, 1):
        out[f"MID_{c}_PU_EV{i}"] = conversation(e.lines) or None
        _scene_messages(out, f"MID_{c}_PU_EV{i}", e, conversation)
    for i, t in enumerate(plan.treasures, 1):
        out[f"MID_{c}_PU_VIL{i}"] = (conversation(t.lines) or None) if not t.is_chest else None
    return out


def _scene_messages(out, key, e, conversation):
    for j, st in enumerate(getattr(e, "scene", []) or [], 1):
        out[f"{key}_S{j}"] = conversation(st.lines) or None
    out[f"{key}_A"] = conversation(getattr(e, "after", []) or []) or None


def scene_function(name: str, key: str, e, messages) -> List[str]:
    """def bev::<name>() playing the event's scene (as E022_Taiki_Tiamo in the DLC)."""
    steps = getattr(e, "scene", []) or []
    if not steps:
        return []
    out = [f"def bev::{name}() {{",
           "    bev::フェードアウト(1000);",
           "    bev::マップ停止();",
           f'    bev::開始("{SCENE_STAGE[0]}", "{SCENE_STAGE[1]}");',
           "    bev::フェードイン(1000);"]
    playing = False
    for j, st in enumerate(steps, 1):
        if st.picture:
            if playing:
                out.append("    bev::テロップ終了();")
            out.append(f'    bev::テロップ再生("{st.picture}");')
            out.append("    bev::全体待ち(1000);")
            playing = True
        if st.sound:
            out.append(f'    ev::SEPlay("{st.sound}");')
            out.append("    bev::全体待ち(1000);")
        if messages.get(f"{key}_S{j}"):
            out.append(f'    bev::会話("{key}_S{j}");')
    out.append("    bev::フェードアウト(1000);")
    if playing:
        out.append("    bev::テロップ終了();")
    out += ["    bev::終了();", "    bev::フェードイン(2000);", "    bev::マップ再開();", "}", ""]
    return out


def _scene_call(name: str, key: str, e, messages) -> List[str]:
    out = []
    if getattr(e, "scene", None):
        out.append(f"    bev::{name}();")
    if messages.get(f"{key}_A"):
        out.append(f'    ev::Talk("{key}_A");')
    return out


def _gain(t, unit="ev::MindGetUnit()") -> List[str]:
    out = []
    if t.item:
        out.append(f'    ev::ItemGain({unit}, "{t.item}");')
    if t.gold:
        out.append(f"    ev::GoldGainSilent(0, {int(t.gold)});")
    return out


def event_script(plan, messages: Dict[str, Optional[str]]) -> List[str]:
    """Script lines for the events (added to the chapter script)."""
    c = plan.cid
    lines: List[str] = []
    for kind, items in (("TK", plan.talks), ("TURN", plan.turn_events), ("EV", plan.tile_events)):
        for i, e in enumerate(items, 1):
            lines += scene_function(f"PU_Scene{kind}{i}", f"MID_{c}_PU_{kind}{i}", e, messages)
    for i, e in enumerate(plan.talks, 1):
        if not e.a or not e.b:
            continue
        f = _flag(f"TK{i}")
        lines.append(f'callback[0x12]("{e.a}", "{e.b}", 0, "{f}") {{')
        if messages.get(f"MID_{c}_PU_TK{i}"):
            lines.append(f'    ev::Talk("MID_{c}_PU_TK{i}");')
        lines += _scene_call(f"PU_SceneTK{i}", f"MID_{c}_PU_TK{i}", e, messages)
        if e.recruit:
            lines.append(f'    v0 = ev::UnitGetByPID("{e.b}");')
            lines.append("    ev::UnitTransferByIndex(v0, 0);")
        lines.append(f'    ev::FlagSet("{f}");')
        lines += ["}", ""]
    for i, q in enumerate(plan.quotes, 1):
        if not q.enemy or not messages.get(f"MID_{c}_PU_BT{i}"):
            continue
        f = _flag(f"BT{i}")
        lines.append(f'callback[0x13]("{q.enemy}", "{q.vs}", 1, "{f}") {{')
        lines.append(f'    ev::Talk("MID_{c}_PU_BT{i}");')
        lines.append(f'    ev::FlagSet("{f}");')
        lines += ["}", ""]
    win_turn = survive_turn(plan)
    for i, e in enumerate(plan.turn_events, 1):
        if not (messages.get(f"MID_{c}_PU_TURN{i}") or e.scene or messages.get(f"MID_{c}_PU_TURN{i}_A")):
            continue
        t = max(2, int(e.turn))  # turn 1 is the opening's (and joining units')
        lines.append(f"callback[0xC]({t}, {t}, 0) {{")
        if messages.get(f"MID_{c}_PU_TURN{i}"):
            lines.append(f'    ev::Talk("MID_{c}_PU_TURN{i}");')
        lines += _scene_call(f"PU_SceneTURN{i}", f"MID_{c}_PU_TURN{i}", e, messages)
        if t == win_turn:  # the conversation plays first, then the chapter is won
            lines += ["    " + l for l in victory_lines()]
            win_turn = None
        lines += ["}", ""]
    if win_turn:
        lines.append(f"callback[0xC]({win_turn}, {win_turn}, 0) {{")
        lines += ["    " + l for l in victory_lines()]
        lines += ["}", ""]
    for i, e in enumerate(plan.tile_events, 1):
        # as the DLC does it (E022, Cordelia's tent: callback[0x10](7, 1, 7, 1, 0, "")): the event
        # belongs to the tile and runs after a unit acts there; the checks are inside it
        f = _flag(f"EV{i}")
        x, y = int(e.x), int(e.y)
        every = flashes(plan, e)
        nx = _flag(f"NX{i}")
        if every:
            # Script effects only last while their event runs (tested in Azahar), so the tile is
            # shown the way the Prologue tutorial shows a tile: when you get control (callback 0xE),
            # the camera goes to it, the red sparkle plays, and the camera comes back to Chrom (or to
            # the unit the event is for). Every `every` turns until the event happens.
            back = [e.who, "PID_クロム"] if e.who and e.who != "PID_クロム" else ["PID_クロム"]
            lines += [
                "callback[0xE](1, -1, 0) {",
                f'    if (!ev::FlagGet("{f}") && ev::TurnGet() >= ev::VariableGet("{nx}")) {{',
                f'        ev::VariableSet("{nx}", ev::TurnGet() + {every});',
                f"        ev::CameraSetPosition({x}, {y});",
                "        ev::CameraWait();",
                f'        v0 = ev::EffectPlay3D("{SPARKLE}", {x}, {y});',
                "        ev::TimeWait(1500);",
                "        ev::EffectFadeOut(v0, 300);",
                "        ev::TimeWait(300);",
            ]
            for pid in back:
                lines += [
                    f'        v1 = ev::UnitGetByPID("{pid}");',
                    "        if (v1) {",
                    "            ev::CameraSetPosition(ev::UnitGetX(v1), ev::UnitGetY(v1));",
                    "            ev::CameraWait();",
                    "            return 0;",
                    "        }",
                ]
            lines += ["    }", "}", ""]
        test = f'!ev::FlagGet("{f}")'
        if e.who:
            test += f' && ev::UnitIsPID(v0, "{e.who}")'
        lines += [
            f'callback[0x10]({x}, {y}, {x}, {y}, 0, "") {{',
            "    v0 = ev::MindGetUnit();",
            "    if (!ev::UnitIsAlive(v0)) {",
            "        return 0;",
            "    }",
            "    if (ev::UnitIsUnitedChild(v0)) {",
            "        return 0;",
            "    }",
            f"    if ({test}) {{",
        ]
        body = []
        if messages.get(f"MID_{c}_PU_EV{i}"):
            body.append(f'    ev::Talk("MID_{c}_PU_EV{i}");')
        body += _scene_call(f"PU_SceneEV{i}", f"MID_{c}_PU_EV{i}", e, messages)
        body += _gain(e, "v0")
        body.append(f'    ev::FlagSet("{f}");')
        lines += ["    " + l for l in body]
        lines += ["    }", "}", ""]
    tile = seize_tile(plan)
    if tile:
        x, y = tile
        f = _flag("WIN")
        test = f'!ev::FlagGet("{f}") && ev::UnitGetForce(v0) == {PLAYER_FORCE}'
        if getattr(plan, "seize_who", ""):
            test += f' && ev::UnitIsPID(v0, "{plan.seize_who}")'
        lines += [
            f'callback[0x10]({x}, {y}, {x}, {y}, 0, "") {{',
            "    v0 = ev::MindGetUnit();",
            "    if (!ev::UnitIsAlive(v0)) {",
            "        return 0;",
            "    }",
            "    if (ev::UnitIsUnitedChild(v0)) {",
            "        return 0;",
            "    }",
            f"    if ({test}) {{",
            f'        ev::FlagSet("{f}");',
        ] + ["        " + l for l in victory_lines()] + ["    }", "}", ""]
    return lines


# ----------------------------------------------------------------------------- terrain script

_BLOCK = re.compile(r"callback\[0x11\]\((\d+),\s*(\d+),\s*(\d+),\s*(\d+),\s*\"[^\"]*\"\)\s*\{(.*?)\n?\}", re.S)


def read_treasures(source: Optional[str], messages=None, parse=None) -> List[Treasure]:
    """Chests and village / house visits of a <chapter>_Terrain script."""
    out = []
    for m in _BLOCK.finditer(source or ""):
        x, y, kind, model, body = int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4)), m.group(5)
        if kind not in (CHEST_KIND, VILLAGE_KIND) or "{" in body:
            continue  # not a chest / village, or more than the plain ones (kept as written)
        item = re.search(r'ItemGain\([^,]+,\s*"([^"]+)"\)', body)
        gold = re.search(r"GoldGain(?:Silent)?\(\s*\d+\s*,\s*(\d+)\)", body)
        talk = re.search(r'ev::Talk\("([^"]+)"\)', body)
        lines = []
        if talk and messages is not None and parse is not None:
            lines = parse(messages.get(talk.group(1)))
        out.append(Treasure(x, y, kind, model, item.group(1) if item else "", int(gold.group(1)) if gold else 0, lines))
    return out


def treasure_block(t: Treasure, talk_key: Optional[str]) -> str:
    body = []
    if talk_key:
        body.append(f'    ev::Talk("{talk_key}");')
    gain = _gain(t)
    trick = "    ev::TrickSet(ev::ArgsGetInt(0), ev::ArgsGetInt(1), ev::ArgsGetInt(2), 2);"
    body += ([trick] + gain) if t.is_chest else (gain + [trick])
    return f'callback[0x11]({t.x}, {t.y}, {t.kind}, {t.model}, "") {{\n' + "\n".join(body) + "\n}"


def write_treasures(source: Optional[str], treasures: List[Treasure], talk_keys: Dict[Tuple[int, int], str]) -> str:
    """The terrain script with its chest / village blocks replaced by `treasures` (doors, walls
    and everything else are kept as they are)."""
    src = source or "include std:fe13:prelude;\n"
    kept = []
    pos = 0
    for m in _BLOCK.finditer(src):
        kind = int(m.group(3))
        kept.append(src[pos : m.start()])
        if kind not in (CHEST_KIND, VILLAGE_KIND) or "{" in m.group(5):
            kept.append(m.group(0))
        pos = m.end()
    kept.append(src[pos:])
    out = "".join(kept).rstrip() + "\n"
    out = re.sub(r"\n{3,}", "\n\n", out)
    for t in treasures:
        out += "\n" + treasure_block(t, talk_keys.get((t.x, t.y))) + "\n"
    return out
