"""Paragon Unlimited - Chapter Maker / Map Maker for Fire Emblem Awakening (FE13).

What it does
------------
* New chapters ("chapter slots"): the game's save data keeps flags for 64 chapters and the
  game itself uses 55, so a project has room for 9 chapters of its own (rows 55-63 of the
  chapter table). Paragon Unlimited calls them U001-U009 and builds each one completely:
  chapter row + names, title card, world map node and road (world_map.py), map files copied
  from a template map, enemies and player starts, an opening and ending conversation and the
  chapter script.
* Easy map editing for any chapter: every unit is shown as a simple Unit (class, level,
  position, boss, behavior). Units read from the game keep their original spawn record, so
  everything the editor does not show (difficulty flags, AI details, spawn conditions) is kept.

Map templates (Data/FE13/PU_MapTemplates.json, made by scripts/build_map_templates.py) list
every Awakening map (main story, paralogues, and DLC maps when the DLC is imported) with its
player starts and an enemy layout. The enemies are generics and are rebuilt for any difficulty.

Nothing here writes files directly except through ChapterMakerEdits.flush() (binary files:
world map, landmarks, title card, map models) which the main window calls after a save.
"""
import json
import logging
import os
import random
import re
from dataclasses import dataclass, field, asdict
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from paragon import paragon as pgn
from paragon.unlimited.map_maker import chapter_events as ce
from paragon.unlimited.map_maker import world_map as wm

GAME_CHAPTERS = 55  # rows the original game uses (CID_000 ... CID_aDebug)
GAME_CIDS = (
    {"000", "P001", "P002", "E000", "ENDING", "aDebug"}
    | {f"{n:03d}" for n in range(1, 27)}
    | {f"X{n:03d}" for n in range(1, 24)}
)
MAX_CHAPTERS = 64  # chapter flags the save data can hold (global save: 64-bit sets + 64-entry table)
SLOT_IDS = [f"U{n:03d}" for n in range(1, 10)]
TEMPLATES_PATH = os.path.join("Data", "FE13", "PU_MapTemplates.json")
PLAN_MARK = "// PU-CHAPTER "

# Spawn flags: byte 1 = 0x80 Normal, 0x40 Hard; byte 2 = 0x01 Lunatic, 0x08 boss.
NORMAL, HARD, LUNATIC = 0x80, 0x40, 0x01
BOSS_FLAG = 0x08
MODES = {"Normal": (NORMAL, 0), "Hard": (HARD, 0), "Lunatic": (0, LUNATIC)}

# ChapterSetWinRule bits, as the game checks them (code.bin 0x397d80, after every unit's action):
# 0x20000 = won when no enemy unit is left, 0x40000 = won when no enemy leader (boss) is left.
# Seize and Survive chapters start with 0x10000, a bit the game does not check for winning; with the
# game code patch it shows the chapter's own banner (mission_banner.py). chapter_events.victory_lines
# ends those chapters.
WIN_ROUT = 131072
WIN_BOSS = 262144
WIN_MISSION = 65536
WIN_KINDS = ("rout", "boss", "seize", "survive")

# Tiles any unit may stand on (taken from where the game itself places units) and extra
# tiles only fliers may use.
GROUND_TILES = {1, 2, 3, 4, 5, 6, 14, 15, 19, 20, 21, 22, 23, 24, 25, 26, 27, 31, 33, 34, 36, 45, 49, 50,
                51, 53, 54, 57, 58, 59, 60, 61, 62, 63, 64, 65, 66, 68, 69}
FLIER_TILES = GROUND_TILES | {7, 10, 16, 17, 18, 70}
FLIERS = ("ペガサス", "ファルコン", "ダークペガサス", "ドラゴン", "グリフォン")

# Behaviors shown in the editor -> spawn AI fields (action, mission, attack, move, end_1).
BEHAVIORS = {
    "charge": ("AI_AC_Everytime", "AI_MI_Null", "AI_AT_Attack", "AI_MV_NearestEnemy", 0x69),
    "wait": ("AI_AC_AttackRange", "AI_MI_Null", "AI_AT_Attack", "AI_MV_NearestEnemy", 0xE9),
    "stay": ("AI_AC_Everytime", "AI_MI_Null", "AI_AT_Attack", "AI_MV_Null", 0x69),
}
BEHAVIOR_NAMES = {
    "charge": "Charge at you",
    "wait": "Wait until you come close",
    "stay": "Stay in place",
    "custom": "Custom (the AI fields below)",
}
# AI values the game's chapters use (offered in the AI fields; any other value can be typed)
AI_VALUES = {
    "action": [
        "AI_AC_Everytime",
        "AI_AC_AttackRange",
        "AI_AC_TurnAttackRange",
        "AI_AC_Null",
        "AI_AC_FlagTrueAttackRange",
        "AI_AC_BandRange",
        "AI_AC_FlagTrue",
        "AI_AC_Turn",
        "AI_AC_TurnBandRange",
        "AI_AC_TurnAttackRangeHealRange",
        "AI_AC_AttackRangeExcludePerson",
        "AI_AC_FlagTrueAttackRangeExcludePerson"
    ],
    "mission": [
        "AI_MI_Null",
        "AI_MI_Village",
        "AI_MI_Irregular",
        "AI_MI_Treasure",
        "AI_MI_EscapeSlow",
        "AI_MI_Talk",
        "AI_MI_X009Boss",
        "AI_MI_X010Serena"
    ],
    "attack": [
        "AI_AT_Attack",
        "AI_AT_Null",
        "AI_AT_Person",
        "AI_AT_X017Enemy",
        "AI_AT_MustAttack",
        "AI_AT_AttackToHeal",
        "AI_AT_AttackToMustHeal",
        "AI_AT_ExcludePerson",
        "AI_AT_MustAttackToMustHeal",
        "AI_AT_Heal",
        "AI_AT_HealToAttack",
        "AI_AT_Idle",
        "AI_AT_X002Anna"
    ],
    "move": [
        "AI_MV_NearestEnemy",
        "AI_MV_Null",
        "AI_MV_Person",
        "AI_MV_NearestEnemyExcludePerson",
        "AI_MV_X017Enemy",
        "AI_MV_VillageToAttack",
        "AI_MV_Irregular",
        "AI_MV_TrasureToEscape",
        "AI_MV_EscapeSlow",
        "AI_MV_VillageNoThroughToAttack",
        "AI_MV_Position",
        "AI_MV_X009Boss",
        "AI_MV_X010Serena"
    ]
}
# Spawn fields kept as they are (Paragon's spawn editor shows them); edited ones win on save
RAW_FIELDS = {
    "spawn_condition": "string", "spawn_flags_1": "int", "spawn_flags_2": "int", "spawn_flags_3": "int",
    "spawn_flags_4": "int", "unknown_1": "bytes", "unknown_2": "bytes", "unknown_3": "bytes",
    "padding_?": "bytes", "action": "string", "action_param": "string", "mission": "string",
    "mission_param": "string", "attack": "string", "attack_param": "string", "move": "string",
    "move_param": "string", "end_section_1": "bytes", "end_section_2": "bytes", "end_section_3": "bytes",
    "end_section_4": "bytes", "item_bitflags_1": "bytes", "item_bitflags_2": "bytes",
    "item_bitflags_3": "bytes", "item_bitflags_4": "bytes", "item_bitflags_5": "bytes",
}
SPAWN_FLAGS_1 = ("Unknown 01", "Forced Unit", "Unknown 04", "Unknown 08", "Deployment Slot",
                 "Recruit at End of Chapter", "Normal", "Hard")
SPAWN_FLAGS_2 = ("Lunatic", "Unknown 02", "New Player Unit (?)", "Boss (?)", "Can't move", "Unknown 20",
                 "Unknown 40", "Unknown 80")


def read_raw(gd, sp) -> dict:
    out = {}
    for k, kind in RAW_FIELDS.items():
        if kind == "string":
            out[k] = gd.string(sp, k) or ""
        elif kind == "int":
            out[k] = gd.int(sp, k) or 0
        else:
            out[k] = list(gd.bytes(sp, k) or [])
    return out


def write_raw(gd, sp, values: dict):
    for k, v in values.items():
        kind = RAW_FIELDS.get(k)
        if kind == "string":
            gd.set_string(sp, k, v or None)
        elif kind == "int":
            gd.set_int(sp, k, int(v) & 0xFF)
        elif kind == "bytes":
            gd.set_bytes(sp, k, [int(b) & 0xFF for b in v])


def behavior_of_ai(action: str, mission: str, attack: str, move: str, end1: int) -> str:
    """The Map Maker preset these AI values are, or "custom"."""
    for k, b in BEHAVIORS.items():
        if (action, mission, attack, move) == b[:4]:
            return k
    return "custom"

# Difficulty tiers. levels = (min, max) for normal enemies; promoted = use promoted classes.
TIERS = {
    1: {"name": "Very easy", "levels": (1, 3), "promoted": False, "weapon": 0, "hard": 4, "lunatic": 10},
    2: {"name": "Easy", "levels": (4, 7), "promoted": False, "weapon": 1, "hard": 5, "lunatic": 12},
    3: {"name": "Normal", "levels": (9, 14), "promoted": False, "weapon": 1, "hard": 6, "lunatic": 15},
    4: {"name": "Hard", "levels": (3, 8), "promoted": True, "weapon": 2, "hard": 7, "lunatic": 18},
    5: {"name": "Very hard", "levels": (9, 14), "promoted": True, "weapon": 2, "hard": 8, "lunatic": 20},
    6: {"name": "Brutal", "levels": (15, 20), "promoted": True, "weapon": 3, "hard": 8, "lunatic": 20},
}

# Enemy armies: generic name + army (belong) of the game's own generics.
THEMES = {
    "ruffian": {"name": "Brigands", "mpid": "MPID_ならず者", "army": "BID_ならずもの", "boss": "Bandit Leader"},
    "plegia": {"name": "Plegian army", "mpid": "MPID_ペレジア兵", "army": "BID_ペレジア軍", "boss": "Plegian Captain"},
    "valm": {"name": "Valmese army", "mpid": "MPID_ヴァルム兵", "army": "BID_ヴァルム帝国軍", "boss": "Valmese General"},
    "risen": {"name": "Risen", "mpid": "MPID_屍兵", "army": "BID_屍兵", "boss": "Risen Chief"},
    "grimleal": {"name": "Grimleal", "mpid": "MPID_ギムレー教兵", "army": "BID_ギムレー教軍", "boss": "Grimleal Priest"},
    "mercenary": {"name": "Mercenaries", "mpid": "MPID_傭兵", "army": "BID_その他", "boss": "Mercenary Captain"},
}

# Weapon kinds per class (JID without the 男/女 ending) and the weapons per tier.
CLASS_WEAPONS = {
    "剣士": "sword", "傭兵": "sword", "盗賊": "sword", "ソードマスター": "sword", "勇者": "sword",
    "アサシン": "sword", "トリックスター": "sword", "ロード": "sword", "マスターロード": "sword",
    "ソシアルナイト": "lance", "アーマーナイト": "lance", "ペガサスナイト": "lance", "パラディン": "lance",
    "グレートナイト": "lance", "ジェネラル": "lance", "ファルコンナイト": "lance", "ダークペガサス": "lance",
    "ソルジャー": "lance", "ソルジャー2": "lance", "村人": "lance",
    "蛮族": "axe", "戦士": "axe", "バーサーカー": "axe", "ウォーリアー": "axe", "ドラゴンナイト": "axe",
    "ドラゴンマスター": "axe", "グリフォンナイト": "axe",
    "アーチャー": "bow", "スナイパー": "bow", "ボウナイト": "bow",
    "魔道士": "fire", "賢者": "fire", "ダークナイト": "fire", "ヴァルキュリア": "wind",
    "ダークマージ": "dark", "ソーサラー": "dark", "ダークナイト2": "dark",
    "僧侶": "staff", "シスター": "staff", "トルバドール": "staff", "バトルモンク": "axe", "バトルシスター": "axe",
    "戦術師": "sword", "神軍師": "sword",
}
WEAPONS = {
    "sword": ["IID_青銅の剣", "IID_鉄の剣", "IID_鋼の剣", "IID_銀の剣"],
    "lance": ["IID_青銅の槍", "IID_鉄の槍", "IID_鋼の槍", "IID_銀の槍"],
    "axe": ["IID_青銅の斧", "IID_鉄の斧", "IID_鋼の斧", "IID_銀の斧"],
    "bow": ["IID_青銅の弓", "IID_鉄の弓", "IID_鋼の弓", "IID_銀の弓"],
    "fire": ["IID_ファイアー", "IID_ファイアー", "IID_エルファイアー", "IID_ギガファイアー"],
    "wind": ["IID_ウインド", "IID_ウインド", "IID_エルウインド", "IID_ギガウインド"],
    "dark": ["IID_ミィル", "IID_ミィル", "IID_ミィル", "IID_ルイン"],
    "staff": ["IID_ライブ", "IID_ライブ", "IID_リライブ", "IID_リカバー"],
}
SECOND_WEAPON = {"ボウナイト": "sword", "勇者": "axe", "アサシン": "bow", "パラディン": "sword",
                 "グレートナイト": "axe", "ジェネラル": "axe", "ドラゴンマスター": "lance",
                 "賢者": "staff", "トルバドール": None, "バトルモンク": "staff", "バトルシスター": "staff",
                 "ヴァルキュリア": "staff", "ダークナイト": "sword", "ファルコンナイト": "staff", "ウォーリアー": "bow"}
ITEM_FLAGS = bytes.fromhex("00010103")
DROP_FLAGS = bytes.fromhex("01010101")

# Classes the "Add enemy" list offers (generic-looking, have map sprites for both teams).
ENEMY_CLASSES = [
    "JID_ソルジャー男", "JID_戦士男", "JID_蛮族男", "JID_傭兵男", "JID_剣士男", "JID_盗賊男", "JID_アーチャー男",
    "JID_魔道士男", "JID_ダークマージ男", "JID_僧侶男", "JID_ソシアルナイト男", "JID_アーマーナイト男",
    "JID_ペガサスナイト女", "JID_ドラゴンナイト男", "JID_トルバドール女",
    "JID_勇者男", "JID_ウォーリアー男", "JID_バーサーカー男", "JID_ソードマスター男", "JID_アサシン男",
    "JID_トリックスター男", "JID_スナイパー男", "JID_ボウナイト男", "JID_パラディン男", "JID_グレートナイト男",
    "JID_ジェネラル男", "JID_賢者男", "JID_ソーサラー男", "JID_ダークナイト男", "JID_バトルモンク男",
    "JID_ヴァルキュリア女", "JID_ファルコンナイト女", "JID_ダークペガサス女", "JID_ドラゴンマスター男",
    "JID_グリフォンナイト男",
    "JID_剣士女", "JID_傭兵女", "JID_アーチャー女", "JID_魔道士女", "JID_ダークマージ女", "JID_シスター女",
    "JID_ソシアルナイト女", "JID_アーマーナイト女", "JID_ドラゴンナイト女", "JID_ソードマスター女",
    "JID_スナイパー女", "JID_パラディン女", "JID_ジェネラル女", "JID_賢者女", "JID_ソーサラー女",
    "JID_バトルシスター女", "JID_ダークナイト女",
]
# Promoted -> unpromoted (for lowering a template's difficulty).
DEMOTE = {
    "ソードマスター": "剣士", "アサシン": "盗賊", "トリックスター": "盗賊", "勇者": "傭兵", "ボウナイト": "アーチャー",
    "スナイパー": "アーチャー", "バーサーカー": "蛮族", "ウォーリアー": "戦士", "パラディン": "ソシアルナイト",
    "グレートナイト": "ソシアルナイト", "ジェネラル": "アーマーナイト", "ファルコンナイト": "ペガサスナイト",
    "ダークペガサス": "ペガサスナイト", "ドラゴンマスター": "ドラゴンナイト", "グリフォンナイト": "ドラゴンナイト",
    "賢者": "魔道士", "ダークナイト": "魔道士", "ソーサラー": "ダークマージ", "ダークナイト2": "ダークマージ",
    "バトルモンク": "僧侶", "バトルシスター": "シスター", "ヴァルキュリア": "トルバドール", "ソルジャー2": "ソルジャー",
}
PROMOTE = {
    "剣士": "ソードマスター", "盗賊": "アサシン", "傭兵": "勇者", "アーチャー": "スナイパー", "蛮族": "バーサーカー",
    "戦士": "ウォーリアー", "ソシアルナイト": "パラディン", "アーマーナイト": "ジェネラル",
    "ペガサスナイト": "ファルコンナイト", "ドラゴンナイト": "ドラゴンマスター", "魔道士": "賢者",
    "ダークマージ": "ソーサラー", "僧侶": "バトルモンク", "シスター": "バトルシスター", "トルバドール": "ヴァルキュリア",
    "ソルジャー": "ソルジャー2",
}
MALE_ONLY = {"ソルジャー", "戦士", "蛮族", "僧侶", "ウォーリアー", "バーサーカー", "バトルモンク", "ソルジャー2"}
FEMALE_ONLY = {"ペガサスナイト", "ファルコンナイト", "ダークペガサス", "シスター", "トルバドール", "ヴァルキュリア", "バトルシスター"}

MOODS = {
    "Normal": "通常,",
    "Happy": "笑,",
    "Angry": "怒,",
    "Pained": "苦,汗",
    "Sad": "苦,",
    "Smug": "キメ,",
    "Troubled": "困る,",
    "Shocked": "衝撃,",
    "Blush": "通常,頬",
    "Flustered": "苦,頬",
}
AVATAR_SPEAKER = "username"
JOIN_FACTION = "Join"  # units that join your army on turn 1 (the way Donnel joins in Paralogue 1)
ALLY_TEAM = 2  # spawn team of green units (0 = yours, 1 = enemy)
JOIN_FLAGS = (0xC0, 0x05)  # spawn flags of the game's own recruits (Donnel, Sumia, Miriel)
NOT_JOINABLE = ("PID_プレイヤー", "PID_ダミー", "PID_魔物", "PID_商人", "PID_GRIMA", "PID_旧マルス")


def class_stem(jid: str) -> Tuple[str, str]:
    """('JID_剣士男') -> ('剣士', '男')."""
    s = jid[4:] if jid.startswith("JID_") else jid
    if s and s[-1] in "男女":
        return s[:-1], s[-1]
    return s, ""


def class_jid(stem: str, sex: str) -> str:
    if stem in MALE_ONLY:
        sex = "男"
    elif stem in FEMALE_ONLY:
        sex = "女"
    return f"JID_{stem}{sex or '男'}"


def is_flier(jid: Optional[str]) -> bool:
    return bool(jid) and any(f in jid for f in FLIERS)


def weapon_kind(jid: str) -> str:
    stem, _ = class_stem(jid)
    return CLASS_WEAPONS.get(stem, "sword")


def items_for(jid: str, tier: int, boss: bool = False) -> List[str]:
    stem, _ = class_stem(jid)
    t = TIERS.get(tier, TIERS[3])["weapon"]
    if boss:
        t = min(3, t + 1)
    out = [WEAPONS[weapon_kind(jid)][t]]
    second = SECOND_WEAPON.get(stem)
    if second and tier >= 4:
        out.append(WEAPONS[second][max(1, t - 1)])
    if boss and tier >= 3:
        out.append("IID_傷薬")
    return out


# ----------------------------------------------------------------------------- simple model
@dataclass
class Unit:
    team: str = "enemy"  # "player", "enemy", "ally", "join" (a character who joins your army), "other"
    x: int = 0
    y: int = 0
    job: str = "JID_ソルジャー男"
    level: int = 1
    boss: bool = False
    behavior: str = "charge"
    items: List[str] = field(default_factory=list)
    pid: str = ""
    name: str = ""  # boss name (English) for new bosses
    face: str = ""  # boss portrait FID ("" = generic)
    modes: Tuple[bool, bool, bool] = (True, True, True)  # Normal, Hard, Lunatic
    faction: str = ""
    # links to the game record this unit came from (None for new units)
    spawn_rid: Optional[int] = None
    person_rid: Optional[int] = None
    forced: bool = False  # player unit the game always deploys (e.g. Chrom)
    # details (enemies / allies): skills, stat bonuses (HP Str Mag Skl Spd Lck Def Res; None = automatic),
    # which items drop when defeated, and a real character instead of a generic (PID)
    skills: List[str] = field(default_factory=list)
    stats: Optional[List[int]] = None
    drops: List[bool] = field(default_factory=list)
    character: str = ""
    own: bool = False  # needs its own person record (battle quotes are tied to it)
    quotes: List[dict] = field(default_factory=list)  # battle quotes [{"vs": PID or "", "text": ...}]
    raw: dict = field(default_factory=dict)  # every spawn field as read (RAW_FIELDS)
    raw_edits: dict = field(default_factory=dict)  # spawn fields changed by hand (written last)

    def key(self):
        return (self.team, self.x, self.y, self.pid)


@dataclass
class Line:
    speaker: str = "クロム"  # FID without "FID_"; "username" = your avatar
    mood: str = "Normal"
    text: str = ""


@dataclass
class ChapterPlan:
    cid: str = "U001"  # without CID_
    title: str = "New Chapter"
    label: str = "New Chapter"  # small text above the title ("Paralogue 25", "Side Story")
    description: str = ""
    template: str = ""  # map template id ("X001", "E003", ...)
    unlock_after: str = "006"  # chapter id (without CID_) that must be cleared first
    world_spot: list = field(default_factory=list)  # [x, y] on the bottom-screen map; empty = next to unlock_after
    theme: str = "ruffian"
    tier: int = 2
    win: str = "rout"  # "rout", "boss", "seize" or "survive" (WIN_KINDS)
    seize: list = field(default_factory=list)  # [x, y] of the tile to seize
    seize_who: str = ""  # PID that must seize it ("" = any of your units)
    survive_turns: int = 8
    banner: str = ""  # Seize / Survive banner text at the start of the battle ("" = automatic)
    boss_name: str = "Bandit Leader"
    boss_face: str = ""
    boss_line: str = ""
    opening: List[Line] = field(default_factory=list)
    ending: List[Line] = field(default_factory=list)
    units: List[Unit] = field(default_factory=list)
    # events (chapter_events.py); treasures are read from / written to the terrain script
    talks: list = field(default_factory=list)  # [ce.TalkEvent]
    quotes: list = field(default_factory=list)  # [ce.BattleQuote]
    turn_events: list = field(default_factory=list)  # [ce.TurnEvent]
    tile_events: list = field(default_factory=list)  # [ce.TileEvent]
    treasures: list = field(default_factory=list)  # [ce.Treasure]

    def to_json(self) -> str:
        d = asdict(self)
        d.pop("units", None)
        d.pop("treasures", None)
        return json.dumps(d, ensure_ascii=False)

    @classmethod
    def from_json(cls, text: str) -> "ChapterPlan":
        d = json.loads(text)
        d.pop("units", None)
        d.pop("treasures", None)
        p = cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})
        p.opening = [Line(**l) if isinstance(l, dict) else l for l in p.opening]
        p.ending = [Line(**l) if isinstance(l, dict) else l for l in p.ending]
        p.talks = [ce.event_from_json(ce.TalkEvent, e, Line) for e in p.talks]
        p.quotes = [ce.event_from_json(ce.BattleQuote, e, Line) for e in p.quotes]
        p.turn_events = [ce.event_from_json(ce.TurnEvent, e, Line) for e in p.turn_events]
        p.tile_events = [ce.event_from_json(ce.TileEvent, e, Line) for e in p.tile_events]
        return p


# ----------------------------------------------------------------------------- templates
class Templates:
    def __init__(self, data: dict):
        self.data = data
        self.maps: Dict[str, dict] = {m["id"]: m for m in data.get("maps", [])}

    @classmethod
    def load(cls, path: str = TEMPLATES_PATH) -> "Templates":
        try:
            with open(path, encoding="utf-8") as f:
                return cls(json.load(f))
        except OSError:
            logging.warning("Map templates not found at %s", path)
            return cls({"maps": []})

    def get(self, tid: str) -> Optional[dict]:
        return self.maps.get(tid)

    def ids(self) -> List[str]:
        return list(self.maps)


# ----------------------------------------------------------------------------- text helpers
def conversation(lines: Sequence[Line]) -> str:
    """Build an FE13 conversation from simple lines (two portraits on screen, swapped as needed)."""
    lines = [l for l in lines if (l.text or "").strip()]
    if not lines:
        return ""
    slots = {3: None, 7: None}
    order = []
    for l in lines:
        if l.speaker not in order:
            order.append(l.speaker)
    out = "$t1"
    first = order[:2]
    slots[3] = first[0]
    out += f"$Wm{first[0]}|3"
    if len(first) > 1:
        slots[7] = first[1]
        out += f"$Wm{first[1]}|7"
    out += "$w0|"
    last = None
    for l in lines:
        if l.speaker not in slots.values():
            # replace the portrait that is not the one who just spoke
            slot = 7 if slots[3] == last else 3
            old = slots[slot]
            if old:
                out += f"$Ws{old}|$Wd$w0|"
            out += f"$Wm{l.speaker}|{slot}$w0|"
            slots[slot] = l.speaker
        text = _wrap(l.text.strip())
        mood = MOODS.get(l.mood, MOODS["Normal"])
        if l.speaker != last:
            if last is not None:
                out += "\\n"
            out += f"$Ws{l.speaker}|$Wa$E{mood}|{text}$k"
        else:
            out += f"$p$E{mood}|{text}$k"
        last = l.speaker
    return out


def boss_talk(face: str, text: str) -> str:
    return f"$t0$Wm{face}|0$w0|$Ws{face}|$Wa{_wrap(text.strip())}$k"


BOX_WIDTH = 38  # characters per row of a text box (two rows per box)


def text_boxes(text: str, width: int = BOX_WIDTH) -> List[List[str]]:
    """The text boxes the game shows for one line of text: [[row, row], ...].

    Your own line breaks are kept: Enter starts a new row, an empty row (Enter twice) starts a
    new text box. Rows longer than `width` are wrapped at a space; every box has two rows."""
    text = (text or "").replace("\r", "").strip()
    if not text:
        return []
    boxes: List[List[str]] = []
    for para in re.split(r"\n\s*\n", text):
        rows: List[str] = []
        for raw_row in para.split("\n"):
            words = raw_row.split()
            cur = ""
            for w in words:
                if cur and len(cur) + 1 + len(w) > width:
                    rows.append(cur)
                    cur = w
                else:
                    cur = f"{cur} {w}" if cur else w
            if cur:
                rows.append(cur)
        boxes += [rows[i : i + 2] for i in range(0, len(rows), 2)]
    return boxes


def _wrap(text: str, width: int = BOX_WIDTH) -> str:
    """Game text for one line: rows joined by a line break, boxes by $k$p (see text_boxes)."""
    return "$k$p".join("\\n".join(rows) for rows in text_boxes(text, width))


_TOKEN = re.compile(
    r"\$Wm([^|$]*)\|\d*"      # put a portrait on screen (name|slot)
    r"|\$Ws([^|$]*)\|"         # select a portrait (the speaker when $Wa follows)
    r"|(\$Wa)"                  # the selected portrait talks
    r"|\$Wd|\$w\d+\||\$t\d"     # remove portrait / wait / text box style
    r"|\$E([^|$]*)\|"          # expression
    r"|(\$k\$p|\$k|\$p)"        # end of a text box
    r"|(\\n)"                   # line break inside a box
    r"|\$[A-Za-z]+[^|$\s]*\|?"  # anything else
)


def parse_conversation(raw: Optional[str]) -> List[Line]:
    """Inverse of conversation() (good enough for text written by it or by the game).

    A new line starts when someone else talks or a new expression is set; text boxes that
    simply continue (long text split by conversation()) are joined again."""
    if not raw:
        return []
    rev_moods = {v: k for k, v in MOODS.items()}
    out: List[Line] = []
    speaker = selected = None
    mood = "Normal"
    new_line = True
    buf = ""

    def flush():
        nonlocal buf, new_line
        txt = "\n".join(" ".join(row.split()) for row in buf.split("\n")).strip()
        buf = ""
        if not txt or not speaker:
            return
        if out and not new_line and out[-1].speaker == speaker:
            out[-1].text += "\n\n" + txt  # the next text box of the same line
        else:
            out.append(Line(speaker, mood, txt))
        new_line = False

    pos = 0
    for m in _TOKEN.finditer(raw):
        buf += raw[pos : m.start()]
        pos = m.end()
        if m.group(2) is not None:
            selected = m.group(2)
        elif m.group(3):
            if selected and selected != speaker:
                flush()
                speaker = selected
                new_line = True
        elif m.group(4) is not None:
            flush()
            mood = rev_moods.get(m.group(4), mood if m.group(4) == "" else "Normal")
            new_line = True
        elif m.group(5):
            flush()
        elif m.group(6):
            buf += "\n"
    buf += raw[pos:]
    flush()
    return out


# ----------------------------------------------------------------------------- script
def ally_factions(plan: ChapterPlan) -> List[str]:
    """The factions of the plan's allies (green units), in order: they are placed with the
    Player and Enemy factions when the chapter loads."""
    out = []
    for u in plan.units:
        if u.team == "ally":
            f = u.faction or "Support01"
            if f not in out and f not in ("Player", "Enemy", JOIN_FACTION):
                out.append(f)
    return out


JOIN_CALLBACK = ("callback[0xC](1, 1, 0) {\n"
                 f'    ev::Dispos("{JOIN_FACTION}", 8);\n'
                 "    ev::DisposWait();\n"
                 "}\n")


def chapter_script(plan: ChapterPlan, terrain_script: bool, boss_pid: Optional[str], has_opening: bool,
                   has_ending: bool, has_boss_line: bool, has_join: bool = False,
                   event_messages: Optional[Dict[str, Optional[str]]] = None) -> str:
    c = plan.cid
    if plan.win == "boss" and boss_pid:
        win = WIN_BOSS
    elif ce.seize_tile(plan) or ce.survive_turn(plan):
        win = WIN_MISSION
    else:
        win = WIN_ROUT
    lines = [
        "include std:fe13:prelude;",
        "",
        f"{PLAN_MARK}{plan.to_json()}",
        "// Made with the Paragon Unlimited Chapter Maker. Edit the chapter there (changes here are",
        "// replaced when the Chapter Maker saves this chapter).",
        "",
    ]
    if has_opening:
        lines += [
            f"def bev::{c}_OP1() {{",
            '    bev::開始("evtx001_op1", "緑の街道_街道");',
            "    bev::フェードイン(2000);",
            f'    bev::場面("MCID_T_{c}");',
            '    bev::カメラ("op1_01cam");',
            "    bev::全体待ち(1000);",
            f'    bev::会話("MID_{c}_OP1");',
            "    bev::フェードアウト(1000);",
            "    bev::終了();",
            "}",
            "",
        ]
    if has_ending:
        lines += [
            f"def bev::{c}_ED1() {{",
            '    bev::開始("evtx001_op1", "緑の街道_街道");',
            "    bev::フェードイン(1000);",
            '    bev::カメラ("op1_01cam");',
            f'    bev::場面("MCID_T_{c}");',
            '    ev::BGMPlay("STRM_BGM_EVT_NAKAMA1", 0);',
            "    bev::全体待ち(1000);",
            f'    bev::会話("MID_{c}_ED1");',
            "    ev::BGMStop(1000);",
            "    bev::フェードアウト(1000);",
            "    bev::終了();",
            "}",
            "",
        ]
    lines += [
        "callback[0x6]() {",
        '    ev::FlagEntry("戦闘会話");',
    ] + [f'    ev::FlagEntry("{f}");' for f in ce.event_flags(plan)] + [
        f'    ev::VariableEntry("{v}", 0);' for v in ce.event_variables(plan)] + [
        "}",
        "",
        "callback[0x7]() {",
        f"    ev::ChapterSetWinRule({win});",
        "    ev::PersonLoad(ev::ChapterGetName());",
        "    ev::TerrainLoad(ev::ChapterGetName());",
        "    ev::DisposLoad(ev::ChapterGetName());",
        '    ev::Dispos("Player", 4);',
        '    ev::Dispos("Enemy", 4);',
    ] + [f'    ev::Dispos("{f}", 4);' for f in ally_factions(plan)] + [
        "}",
        "",
        "callback[0x8]() {",
        "    ev::DisposFree();",
        "    ev::TerrainFree();",
        "    ev::PersonFree(ev::ChapterGetName());",
        "}",
        "",
        "callback[0x9]() {",
        f"    bev::{c}_OP1();" if has_opening else "",
        "}",
        "",
        "callback[0xA]() {}",
        "",
        "callback[0xB]() {",
        f"    bev::{c}_ED1();" if has_ending else "",
        "}",
        "",
    ]
    if has_join:  # characters who join your army appear at the start of turn 1 (like Donnel)
        lines += JOIN_CALLBACK.rstrip("\n").split("\n") + [""]
    if boss_pid and has_boss_line:
        lines += [
            f'callback[0x15]("{boss_pid}", 1, "") {{',
            f'    ev::Talk("MID_{c}_BOSS_DIE1");',
            "}",
            "",
        ]
    lines += ce.event_script(plan, event_messages or {})
    return "\n".join(l for l in lines if l is not None) + "\n"


def plan_from_script(source: str) -> Optional[ChapterPlan]:
    for line in source.splitlines():
        if line.startswith(PLAN_MARK):
            try:
                return ChapterPlan.from_json(line[len(PLAN_MARK) :])
            except Exception:
                logging.exception("Bad Chapter Maker plan line")
    return None


# ----------------------------------------------------------------------------- the service
class ChapterMaker:
    """Reads and writes chapters for the Chapter Maker / Map Maker window."""

    def __init__(self, gd, templates: Optional[Templates] = None, output_path: Optional[str] = None,
                 dlc_original: Optional[str] = None):
        self.gd = gd
        self.templates = templates or Templates.load()
        self.output_path = output_path
        self.dlc_original = dlc_original  # folder with Exxx_MAP.arc (DLC workspace "original")
        self.edits = ChapterMakerEdits(gd)
        self.banner_renderer = None  # text -> PIL image (white on black, 256 x 32); set by the window
        self._arc_cache: Dict[str, Dict[str, bytes]] = {}
        self._msg_path = "m/GameData.bin.lz"
        try:
            self.gd.open_text_data(self._msg_path, True)
        except Exception:
            pass

    # ------------------------------------------------------------------ chapter table
    def chapter_rows(self) -> List[int]:
        r, f = self.gd.table("chapters")
        return self.gd.items(r, f)

    def chapter_ids(self) -> List[str]:
        return [self._cid(c) for c in self.chapter_rows()]

    def _cid(self, rid) -> str:
        k = self.gd.key(rid) or ""
        return k[4:] if k.startswith("CID_") else k

    def chapter_rid(self, cid: str):
        return self.gd.key_to_rid("chapters", "CID_" + cid)

    def message(self, key: Optional[str]) -> Optional[str]:
        if not key:
            return None
        try:
            if self.gd.has_message(self._msg_path, True, key):
                return self.gd.message(self._msg_path, True, key)
        except Exception:
            pass
        return None

    def chapter_name(self, cid: str) -> str:
        rid = self.chapter_rid(cid)
        if rid is None:
            return cid
        key = self.gd.string(rid, "name")
        label = self.message((key or "") + "_T") if key else None
        name = self.message(key) or cid
        return f"{label}: {name}" if label else name

    def story_chapters(self) -> List[Tuple[str, str]]:
        """Chapters a new chapter can unlock after: (cid, display name)."""
        out = []
        for c in self.chapter_rows():
            cid = self._cid(c)
            if cid in ("ENDING", "aDebug", "E000", "P001", "000"):
                continue
            out.append((cid, self.chapter_name(cid)))
        return out

    def free_rows(self) -> int:
        return max(0, MAX_CHAPTERS - len(self.chapter_rows()))

    def custom_chapters(self) -> List[dict]:
        """Chapters after the game's own 55: the project's own chapters."""
        out = []
        for i, c in enumerate(self.chapter_rows()):
            cid = self._cid(c)
            if cid in GAME_CIDS:
                continue
            out.append({"cid": cid, "row": i, "name": self.chapter_name(cid), "made_here": self.is_made_here(cid)})
        return out

    def next_slot_id(self) -> Optional[str]:
        have = set(self.chapter_ids())
        for s in SLOT_IDS:
            if s not in have:
                return s
        return None

    def is_made_here(self, cid: str) -> bool:
        """Chapters made with the Map Maker, and every chapter in your own slots (U001-U009),
        also ones made before the Map Maker existed: they get every Map Maker feature."""
        if cid in SLOT_IDS:
            return True
        src = self._script_source(cid)
        return bool(src and PLAN_MARK in src)

    # ------------------------------------------------------------------ files
    def _exists(self, path: str) -> bool:
        try:
            return self.gd.file_exists(path, False)
        except Exception:
            return False

    def _read(self, path: str) -> Optional[bytes]:
        try:
            return bytes(self.gd.read_file(path))
        except Exception:
            return None

    def _dlc_arc(self, ep: str) -> Dict[str, bytes]:
        if ep in self._arc_cache:
            return self._arc_cache[ep]
        files = {}
        if self.dlc_original:
            p = os.path.join(self.dlc_original, f"{ep}_MAP.arc")
            if os.path.isfile(p):
                from paragon.unlimited.portraits.portrait_files import parse_arc

                with open(p, "rb") as f:
                    for name, _i, blob in parse_arc(f.read()):
                        files[name] = bytes(blob)
        self._arc_cache[ep] = files
        return files

    def template_file(self, tid: str, kind: str) -> Optional[bytes]:
        """Raw file of a template map. kind: terrain/height/mini/config."""
        rel = {
            "terrain": f"map/terrain/{{}}.bcres.lz",
            "height": f"map/height/{{}}.bin",
            "mini": f"map/mini/{{}}.ctpk.lz",
            "config": f"map/data/{{}}.bin",
        }[kind]
        t = self.templates.get(tid) or {}
        if t.get("source") == "dlc":
            blob = self._dlc_arc(tid).get(rel.format("E000"))
            return _plain(rel, blob)
        return self._read(rel.format(tid))

    def template_available(self, tid: str) -> bool:
        t = self.templates.get(tid)
        if not t:
            return False
        if t.get("source") == "dlc":
            arc = self._dlc_arc(tid)
            return "map/terrain/E000.bcres.lz" in arc and self._exists(f"data/terrain/{tid}.bin.lz")
        return self._exists(f"map/terrain/{tid}.bcres.lz") and self._exists(f"data/terrain/{tid}.bin.lz")

    def available_templates(self) -> List[dict]:
        return [t for t in self.templates.maps.values() if self.template_available(t["id"])]

    def minimap(self, cid: str) -> Optional[Tuple[int, int, bytes]]:
        """(width, height, RGBA) of a chapter's or template's minimap."""
        raw = self._read(f"map/mini/{cid}.ctpk.lz")
        if raw is None and (self.templates.get(cid) or {}).get("source") == "dlc":
            raw = _plain(".lz", self._dlc_arc(cid).get("map/mini/E000.ctpk.lz"))
        if raw is None:
            return None
        try:
            tex = pgn.read_ctpk(raw)[0]
            return tex.width, tex.height, bytes(tex.pixel_data)
        except Exception:
            logging.exception("Could not read minimap of %s", cid)
            return None

    # ------------------------------------------------------------------ terrain
    def grid(self, cid: str) -> Optional[Tuple[int, int, bytes]]:
        try:
            g = self.gd.multi_open("grids", f"data/terrain/{cid}.bin.lz")
            return self.gd.int(g, "map_width"), self.gd.int(g, "map_height"), bytes(self.gd.bytes(g, "grid"))
        except Exception:
            return None

    def tile_names(self) -> List[str]:
        r, f = self.gd.table("tiles")
        return [self.gd.display(t) or "" for t in self.gd.items(r, f)]

    @staticmethod
    def can_stand(grid: Tuple[int, int, bytes], x: int, y: int, jid: Optional[str] = None) -> bool:
        w, h, raw = grid
        if not (0 <= x < w and 0 <= y < h):
            return False
        t = raw[y * 32 + x]
        return t in (FLIER_TILES if is_flier(jid) else GROUND_TILES)

    # ------------------------------------------------------------------ names
    def class_name(self, jid: str) -> str:
        rid = self.gd.key_to_rid("jobs", jid)
        name = (self.gd.display(rid) if rid else None) or jid
        _stem, sex = class_stem(jid)
        if sex and class_stem(jid)[0] not in MALE_ONLY | FEMALE_ONLY:
            name += " (M)" if sex == "男" else " (F)"
        return name

    def enemy_classes(self) -> List[Tuple[str, str]]:
        out = []
        for j in ENEMY_CLASSES:
            if self.gd.key_to_rid("jobs", j):
                out.append((self.class_name(j), j))
        return sorted(out)

    def speakers(self) -> List[Tuple[str, str]]:
        """(English name, speaker code) for conversations: your avatar + characters with a portrait."""
        out = [("Your avatar (Robin)", AVATAR_SPEAKER)]
        seen = {AVATAR_SPEAKER}
        r, f = self.gd.table("characters")
        for c in self.gd.items(r, f):
            fid = self.gd.string(c, "fid")
            pid = self.gd.string(c, "pid") or ""
            if not fid or not fid.startswith("FID_") or "プレイヤー" in pid:
                continue
            code = fid[4:]
            if code in seen:
                continue
            name = self.gd.display(c)
            if not name or name.startswith("PID_") or "?" in name:
                continue
            seen.add(code)
            out.append((name, code))
        return out

    def joinable_characters(self) -> List[Tuple[str, str, str]]:
        """(English name, PID, class JID) of the characters that can join your army."""
        out = []
        r, f = self.gd.table("characters")
        for c in self.gd.items(r, f):
            pid = self.gd.string(c, "pid") or ""
            if not pid or pid.startswith(NOT_JOINABLE):
                continue
            name = self.gd.display(c)
            if not name or name.startswith("PID_") or "?" in name:
                continue
            job = self.gd.rid(c, "job")
            out.append((name, pid, self.gd.key(job) if job else ""))
        return out

    def item_choices(self) -> List[Tuple[str, str]]:
        """(English name, IID) of every item, sorted by name."""
        out = []
        r, f = self.gd.table("items")
        for it in self.gd.items(r, f):
            iid = self.gd.key(it) or ""
            if not iid.startswith("IID_"):
                continue
            name = self.gd.display(it) or iid
            out.append((name if name != iid else iid[4:], iid))
        return sorted(out, key=lambda t: t[0].lower())

    def skill_choices(self) -> List[Tuple[str, str]]:
        """(English name, skill key) of every skill (the keys are the game's RSID_ names)."""
        out = []
        r, f = self.gd.table("skills")
        for sk in self.gd.items(r, f):
            key = self.gd.key(sk) or ""
            if not key or key.endswith("無し"):
                continue
            name = self.gd.display(sk) or key
            out.append((name, key))
        return sorted(out, key=lambda t: t[0].lower())

    def class_stats(self, jid: str) -> Tuple[List[int], List[int]]:
        """(base stats, max stats) of a class, HP Str Mag Skl Spd Lck Def Res."""
        job = self.gd.key_to_rid("jobs", jid) if jid else None
        if not job:
            return [0] * 8, [0] * 8
        base = [v - 256 if v > 127 else v for v in list(self.gd.bytes(job, "base_stats") or [0] * 8)[:8]]
        top = list(self.gd.bytes(job, "max_stats") or [0] * 8)[:8]
        return base, top

    def character_choices(self) -> List[Tuple[str, str, str]]:
        """(English name, PID, class JID) of the game's characters, sorted by name."""
        return sorted(self.joinable_characters(), key=lambda t: t[0].lower())

    def save_existing(self, cid: str, units: List[Unit], mode: str = "Normal", treasures=None,
                      painted: Optional[Dict[Tuple[int, int], int]] = None, treasures_changed: bool = False):
        """Save a game chapter (or one made outside the Map Maker): units, painted tiles and, when
        they were changed, its chests and villages. Its story and other scripts stay as they are."""
        self.write_units(cid, units, mode)
        if any(u.team == "join" for u in units):
            src = self._script_source(cid)
            if src is not None and f'ev::Dispos("{JOIN_FACTION}"' not in src:
                # a game chapter only places the factions its script names
                self._set_script(cid, src.rstrip("\n") + "\n\n" + JOIN_CALLBACK)
        for (x, y), t in (painted or {}).items():
            self.set_tile(cid, x, y, t)
        if treasures_changed and treasures is not None:
            tpath = f"m/{cid}.bin.lz"
            if not self._text_exists(tpath):
                self.gd.new_text_data(tpath, True)
            else:
                self.gd.open_text_data(tpath, True)
            keys = {}
            for i, t in enumerate(treasures, 1):
                text = conversation(t.lines) if not t.is_chest else ""
                k = f"MID_{cid}_PU_VIL{i}"
                self.gd.set_message(tpath, True, k, text or None)
                if text:
                    keys[(t.x, t.y)] = k
            self._set_script(f"{cid}_Terrain", ce.write_treasures(self._script_source(f"{cid}_Terrain"), treasures, keys))

    # ------------------------------------------------------------------ reading units
    def dispos_key(self, cid: str) -> str:
        return f"data/dispos/{cid}.bin.lz"

    def person_key(self, cid: str) -> str:
        return f"data/person/{cid}.bin.lz"

    def read_units(self, cid: str, mode: str = "Normal") -> List[Unit]:
        """Units of a chapter for one difficulty mode (each unit keeps its game record)."""
        gd = self.gd
        try:
            d = gd.multi_open("dispos", self.dispos_key(cid))
        except Exception:
            return []
        people = self._people(cid)
        m1, m2 = MODES.get(mode, MODES["Normal"])
        out = []
        for fac in gd.items(d, "factions") or []:
            fname = gd.string(fac, "name") or ""
            team = "player" if fname == "Player" else "enemy" if fname == "Enemy" else "join" if fname == JOIN_FACTION else (
                "ally" if fname.startswith(("Support", "Ally")) else "other")
            tb = gd.rid(fac, "table")
            for sp in gd.items(tb, "spawns") or []:
                f1, f2 = gd.int(sp, "spawn_flags_1") or 0, gd.int(sp, "spawn_flags_2") or 0
                if team != "player" and not ((f1 & m1) or (f2 & m2)):
                    continue
                pid = gd.string(sp, "pid") or ""
                c1 = gd.bytes(sp, "coord_1") or [0, 0]
                person = people.get(pid) or gd.key_to_rid("characters", pid)
                job = gd.rid(person, "job") if person else None
                items, drops = [], []
                for i in range(1, 6):
                    it = gd.rid(sp, f"item_{i}")
                    if it:
                        items.append(gd.key(it))
                        drops.append(bytes(gd.bytes(sp, f"item_bitflags_{i}") or b"\0")[:1] == b"\x01")
                own_person = person in people.values() if person else False
                skills, stats = [], None
                if person and own_person:
                    for k in range(1, 6):
                        sk = gd.rid(person, f"skill_{k}")
                        if sk and not (gd.key(sk) or "").endswith("無し"):  # RSID_無し = no skill
                            skills.append(gd.key(sk))
                    add = list(gd.bytes(person, "additions") or [])
                    if any(add):
                        stats = [v - 256 if v > 127 else v for v in add[:8]]
                u = Unit(
                    team=team,
                    x=c1[0],
                    y=c1[1],
                    job=gd.key(job) if job else "",
                    level=(gd.int(person, "level") or 1) if person else 1,
                    boss=bool(f2 & BOSS_FLAG),
                    behavior=self._behavior_of(sp, exact=True),
                    items=items,
                    pid=pid,
                    modes=(bool(f1 & NORMAL), bool(f1 & HARD), bool(f2 & LUNATIC)),
                    faction=fname,
                    spawn_rid=sp,
                    person_rid=person if person in people.values() else None,
                    forced=team == "player" and bool(f1 & 0x02),
                    skills=skills,
                    stats=stats,
                    drops=drops,
                    character=pid if (team in ("enemy", "ally") and person and not own_person) else "",
                    raw=read_raw(gd, sp),
                )
                if person and (u.boss or (own_person and gd.string(person, "fid"))):
                    u.name = self.message(gd.string(person, "name")) or ""
                    u.face = gd.string(person, "fid") or ""
                out.append(u)
        return out

    def _people(self, cid: str) -> Dict[str, int]:
        try:
            p = self.gd.multi_open("person", self.person_key(cid))
        except Exception:
            return {}
        return {self.gd.string(r, "pid"): r for r in self.gd.items(p, "people") or []}

    def _behavior_of(self, sp, exact: bool = False) -> str:
        gd = self.gd
        if exact:
            return behavior_of_ai(gd.string(sp, "action") or "", gd.string(sp, "mission") or "",
                                  gd.string(sp, "attack") or "", gd.string(sp, "move") or "", 0)
        move = gd.string(sp, "move") or ""
        act = gd.string(sp, "action") or ""
        if move == "AI_MV_Null":
            return "stay"
        if act in ("AI_AC_Everytime",):
            return "charge"
        return "wait"

    def other_unit_counts(self, cid: str) -> Dict[str, int]:
        """Factions the editor does not show (reinforcements, events) and their unit counts."""
        gd = self.gd
        out = {}
        try:
            d = gd.multi_open("dispos", self.dispos_key(cid))
        except Exception:
            return out
        for fac in gd.items(d, "factions") or []:
            n = gd.string(fac, "name") or ""
            if n in ("Player", "Enemy", JOIN_FACTION) or n.startswith(("Support", "Ally")):
                continue
            out[n] = len(gd.items(gd.rid(fac, "table"), "spawns") or [])
        return out

    # ------------------------------------------------------------------ writing units
    def write_units(self, cid: str, units: List[Unit], mode: str = "Normal", tier_hint: int = 3,
                    theme: Optional[str] = None):
        """Apply the editor's units to the chapter's dispos + person files.

        Units with a spawn_rid update that record; units without one are new records cloned
        from a prototype; records of units that were removed in the editor are deleted. Only
        the factions the editor shows (Player, Enemy, Support/Ally) and only spawns that are
        visible in `mode` are touched."""
        gd = self.gd
        d = gd.multi_open("dispos", self.dispos_key(cid))
        people_file = self._person_file(cid)
        people = self._people(cid)
        shown = {u.spawn_rid for u in self.read_units(cid, mode) if u.spawn_rid is not None}
        keep = {u.spawn_rid for u in units if u.spawn_rid is not None}
        factions = {gd.string(f, "name"): f for f in gd.items(d, "factions") or []}

        # 1. delete removed spawns
        for fac in factions.values():
            tb = gd.rid(fac, "table")
            spawns = gd.items(tb, "spawns") or []
            for i in reversed(range(len(spawns))):
                if spawns[i] in shown and spawns[i] not in keep:
                    gd.list_remove(tb, "spawns", i)

        # 2. persons: one per (class, level, boss, face, name) for enemies that need a new one
        person_for = {}
        counter = [0]

        def details_match(r, u: Unit) -> bool:
            have = [k2 for k2 in (gd.key(gd.rid(r, f"skill_{k}")) for k in range(1, 6) if gd.rid(r, f"skill_{k}"))
                    if k2 and not k2.endswith("無し")]
            add = [v - 256 if v > 127 else v for v in list(gd.bytes(r, "additions") or [0] * 8)[:8]]
            return have == list(u.skills) and (u.stats is None or add == list(u.stats))

        def person_pid(u: Unit) -> str:
            k = (u.job, u.level, u.boss, u.face, u.name if (u.boss or u.name) else "", tuple(u.skills),
                 tuple(u.stats) if u.stats is not None else None, id(u) if u.own else None)
            if k in person_for:
                return person_for[k]
            # reuse an unchanged person of this chapter
            for pid, r in people.items():
                if u.own and pid != u.pid:
                    continue
                job = gd.rid(r, "job")
                if (job and gd.key(job) == u.job and (gd.int(r, "level") or 0) == u.level
                        and bool(u.boss) == pid.endswith(("ボス", "_BOSS")) and (gd.string(r, "fid") or "") == (u.face or "")
                        and details_match(r, u)):
                    if not (u.boss or u.name) or (self.message(gd.string(r, "name")) or "") == (u.name or ""):
                        person_for[k] = pid
                        return pid
            pid = self._new_person(cid, people_file, people, u, tier_hint, theme, counter)
            person_for[k] = pid
            return pid

        # 3. write each unit
        player_index = {id(u): i for i, u in enumerate([u for u in units if u.team == "player"])}
        for u in units:
            if u.team == "other":
                continue
            fac_name = {"player": "Player", "enemy": "Enemy", "join": JOIN_FACTION}.get(u.team) or u.faction or "Support01"
            fac = factions.get(fac_name)
            if fac is None:
                fac = self._add_faction(d, fac_name)
                factions[fac_name] = fac
            sp = u.spawn_rid
            new_spawn = sp is None
            if sp is None:
                sp = gd.list_add(gd.rid(fac, "table"), "spawns")
                gd.copy(self._prototype_spawn(u, player_index.get(id(u), 1)), sp, [])
                u.spawn_rid = sp
            gd.set_bytes(sp, "coord_1", [u.x, u.y])
            gd.set_bytes(sp, "coord_2", [u.x, u.y])
            if u.team == "player":
                if u.spawn_rid is not None and new_spawn:
                    self._set_items(sp, [], False)  # deploy slots carry no items
                if u.pid:  # a set character starts here
                    gd.set_string(sp, "pid", u.pid)
                f1 = gd.int(sp, "spawn_flags_1") or 0
                gd.set_int(sp, "spawn_flags_1", (f1 | 0x02) if u.forced else (f1 & ~0x02))
                continue
            if u.team == "join":
                gd.set_string(sp, "pid", u.pid)
                gd.set_int(sp, "team", 0)
                gd.set_int(sp, "spawn_flags_1", JOIN_FLAGS[0])
                gd.set_int(sp, "spawn_flags_2", JOIN_FLAGS[1])
                if u.items or new_spawn:
                    self._set_items(sp, u.items, False)
                continue
            if u.team == "ally" and new_spawn:
                # green, as the game's own allies (Kellam in Chapter 3). Spawns read from a chapter keep
                # their team: the game's Support factions also hold units that join (Ricken, Chapter 5).
                gd.set_int(sp, "team", ALLY_TEAM)
            if u.character:  # one of the game's characters (keeps their own stats)
                gd.set_string(sp, "pid", u.character)
                u.pid = u.character
                self._set_ai(sp, u.behavior, u.boss)
                self._set_items(sp, u.items, u.boss, u.drops)
                continue
            # class / level / details changes give the unit its own person
            current = people.get(gd.string(sp, "pid") or "")
            same = False
            if current is not None:
                job = gd.rid(current, "job")
                same = (job and gd.key(job) == u.job and (gd.int(current, "level") or 0) == u.level
                        and (not (u.boss or u.name) or (self.message(gd.string(current, "name")) or "") == (u.name or ""))
                        and (gd.string(current, "fid") or "") == (u.face or "")
                        and details_match(current, u)
                        and (not u.own or sum(1 for o in units if o.pid == u.pid and o is not u) == 0))
            if not same:
                gd.set_string(sp, "pid", person_pid(u))
            u.pid = gd.string(sp, "pid") or ""
            self._set_ai(sp, u.behavior, u.boss)
            f1 = gd.int(sp, "spawn_flags_1") or 0
            f2 = gd.int(sp, "spawn_flags_2") or 0
            was_boss = bool(f2 & BOSS_FLAG)
            f2 = (f2 | BOSS_FLAG) if u.boss else (f2 & ~(BOSS_FLAG | 0x10) if was_boss else f2 & ~BOSS_FLAG)
            gd.set_int(sp, "spawn_flags_2", f2)
            self._set_items(sp, u.items, u.boss, u.drops)
        # 4. fields changed by hand (Spawn Flags, AI, item bitflags, ...) win
        for u in units:
            if u.team != "other" and u.spawn_rid is not None and u.raw_edits:
                write_raw(gd, u.spawn_rid, u.raw_edits)
            if u.spawn_rid is not None:
                u.raw = read_raw(gd, u.spawn_rid)
                u.raw_edits = {}
        self.mark_dirty(cid)

    def _person_file(self, cid: str):
        try:
            return self.gd.multi_open("person", self.person_key(cid))
        except Exception:
            # chapter without a person file: make one from Paralogue 1's
            return self.gd.multi_duplicate("person", self.person_key("X001"), self.person_key(cid))

    def _add_faction(self, d, name: str):
        gd = self.gd
        facs = gd.items(d, "factions") or []
        f = gd.list_add(d, "factions")
        if facs:
            gd.copy(facs[0], f, [])
        gd.set_string(f, "name", name)
        tb = gd.rid(f, "table")
        for i in reversed(range(len(gd.items(tb, "spawns") or []))):
            gd.list_remove(tb, "spawns", i)
        return f

    def _prototype_spawn(self, u: Unit, player_slot: int = 1):
        """A game spawn record to copy for a new unit.

        Player slots copy the game's standard deploy list (Paralogue 23 has all 30: slot 0 is
        Chrom, whom the game always deploys, then Robin, Lissa, Frederick, ...)."""
        gd = self.gd
        cache = self.__dict__.setdefault("_proto_cache", {})
        if u.team == "player":
            key = ("player", min(player_slot, 29))
        elif u.team == "join":
            key = ("join",)
        else:
            key = ("boss",) if u.boss else ("enemy",)
        if key in cache:
            return cache[key]
        if u.team == "join":
            d = gd.multi_open("dispos", self.dispos_key("X001"))
            facs = {gd.string(f, "name"): f for f in gd.items(d, "factions")}
            sp = gd.items(gd.rid(facs["Support01"], "table"), "spawns")[0]  # Donnel
            cache[key] = sp
            return sp
        if u.team == "player":
            d = gd.multi_open("dispos", self.dispos_key("X023"))
            facs = {gd.string(f, "name"): f for f in gd.items(d, "factions")}
            spawns = gd.items(gd.rid(facs["Player"], "table"), "spawns")
            sp = spawns[min(key[1], len(spawns) - 1)]
        else:
            d = gd.multi_open("dispos", self.dispos_key("X001"))
            facs = {gd.string(f, "name"): f for f in gd.items(d, "factions")}
            spawns = gd.items(gd.rid(facs["Enemy"], "table"), "spawns")
            sp = spawns[0] if u.boss else spawns[2]
        cache[key] = sp
        return sp

    def _set_ai(self, sp, behavior: str, boss: bool):
        gd = self.gd
        if behavior == "custom" or behavior not in BEHAVIORS:
            return  # the unit's own AI (set in the AI fields) stays as it is
        b = BEHAVIORS[behavior]
        if self._behavior_of(sp, exact=True) == behavior:
            return  # already this preset: keep its details (parameters, end sections)
        for k, v in zip(("action", "mission", "attack", "move"), b[:4]):
            gd.set_string(sp, k, v)
        for k in ("action_param", "mission_param", "attack_param", "move_param"):
            gd.set_string(sp, k, None)
        e1 = list(gd.bytes(sp, "end_section_1") or [0, 0, 0, 0])
        e1[0] = b[4]
        gd.set_bytes(sp, "end_section_1", e1)
        e2 = list(gd.bytes(sp, "end_section_2") or [0x32, 0, 0, 0])
        e2[0] = 0x32
        if behavior == "wait" and not e2[1]:
            e2[1] = 1
        gd.set_bytes(sp, "end_section_2", e2)

    def _set_items(self, sp, items: List[str], boss: bool, drops: Optional[List[bool]] = None):
        gd = self.gd
        for i in range(1, 6):
            iid = items[i - 1] if i <= len(items) else None
            rid = gd.key_to_rid("items", iid) if iid else None
            old_item = gd.rid(sp, f"item_{i}")
            old_flags = bytes(gd.bytes(sp, f"item_bitflags_{i}") or b"\0\0\0\0")
            flags = ITEM_FLAGS if rid else b"\0\0\0\0"
            if drops is not None and i <= len(drops) and len(drops) == len(items):
                if rid and drops[i - 1]:
                    flags = DROP_FLAGS
                if rid and rid == old_item and (old_flags[:1] == b"\x01") == bool(drops[i - 1]):
                    flags = old_flags  # same item, same drop: keep the game's own bitflags
            elif iid in ("IID_宝の鍵", "IID_扉の鍵") or (boss and iid == "IID_傷薬"):
                flags = DROP_FLAGS
            gd.set_rid(sp, f"item_{i}", rid)
            gd.set_bytes(sp, f"item_bitflags_{i}", list(flags))

    def _prototype_person(self, boss: bool):
        people = self._people("X001")
        return people.get("PID_X001_ボス" if boss else "PID_X001_蛮族")

    def _new_person(self, cid, people_file, people, u: Unit, tier: int, theme: Optional[str], counter) -> str:
        gd = self.gd
        while True:
            counter[0] += 1
            pid = f"PID_{cid}_ボス" if u.boss and counter[0] == 1 and f"PID_{cid}_ボス" not in people else f"PID_{cid}_PU{counter[0]:02d}"
            if pid not in people and not gd.key_to_rid("characters", pid):
                break
        r = gd.list_add(people_file, "people")
        proto = self._prototype_person(u.boss)
        if proto is not None:
            gd.copy(proto, r, [])
        gd.set_string(r, "pid", pid)
        job = gd.key_to_rid("jobs", u.job)
        if job:
            gd.set_rid(r, "job", job)
        gd.set_int(r, "level", max(1, min(20, int(u.level))))
        th = THEMES.get(theme or "", THEMES["ruffian"])
        army = gd.key_to_rid("belong", th["army"])
        if army:
            gd.set_rid(r, "army", army)
        t = TIERS.get(tier, TIERS[3])
        gd.set_int(r, "hard_bonus", t["hard"])
        gd.set_int(r, "lunatic_bonus", t["lunatic"])
        for k in range(1, 6):
            sk = gd.key_to_rid("skills", u.skills[k - 1]) if k <= len(u.skills) else None
            gd.set_rid(r, f"skill_{k}", sk)
        if u.boss or u.name or u.face:
            name_key = f"MPID_{cid}_ボス" if pid.endswith("ボス") else f"MPID_{pid[4:]}"
            self.gd.set_message(self._msg_path, True, name_key, u.name or th["boss"])
            gd.set_string(r, "name", name_key)
            gd.set_string(r, "description", name_key)
            gd.set_string(r, "fid", u.face or None)
            boost = min(30, 3 + tier * 3) if u.boss else 0
            gd.set_bytes(r, "additions", [boost, boost // 3, boost // 4, boost // 3, boost // 4, 1 if boost else 0,
                                          boost // 3, boost // 4])
        else:
            gd.set_string(r, "name", th["mpid"])
            gd.set_string(r, "description", th["mpid"].replace("MPID_", "MPID_H_"))
            gd.set_string(r, "fid", None)
            gd.set_bytes(r, "additions", [0] * 8)
        if u.stats is not None:
            gd.set_bytes(r, "additions", [int(v) & 0xFF for v in (list(u.stats) + [0] * 8)[:8]])
        people[pid] = r
        return pid

    def mark_dirty(self, cid: str):
        for store, key in (("dispos", self.dispos_key(cid)), ("person", self.person_key(cid))):
            try:
                self.gd.multi_set_dirty(store, key, True)
            except Exception:
                pass

    # ------------------------------------------------------------------ layouts from templates
    def template_units(self, tid: str, tier: int, theme: str, seed: int = 0) -> List[Unit]:
        """Fresh units for a template map at a difficulty tier."""
        t = self.templates.get(tid)
        if not t:
            return []
        rnd = random.Random(f"{tid}-{tier}-{seed}")
        lo, hi = TIERS[tier]["levels"]
        units = []
        for (x, y) in t.get("players", []):
            units.append(Unit(team="player", x=x, y=y, job="", level=1))
        for e in t.get("enemies", []):
            jid = self._tiered_class(e.get("cls") or "JID_ソルジャー男", tier)
            boss = bool(e.get("boss"))
            lvl = rnd.randint(lo, hi)
            if boss:
                lvl = min(20, hi + 2)
            units.append(Unit(team="enemy", x=e["x"], y=e["y"], job=jid, level=lvl, boss=boss,
                              behavior=e.get("behavior", "charge") if not boss else "stay",
                              items=items_for(jid, tier, boss), name=THEMES.get(theme, THEMES["ruffian"])["boss"] if boss else ""))
        if not any(u.boss for u in units) and any(u.team == "enemy" for u in units):
            # every template gets a boss: the enemy farthest from the player start
            px = sum(u.x for u in units if u.team == "player") / max(1, len([u for u in units if u.team == "player"]))
            py = sum(u.y for u in units if u.team == "player") / max(1, len([u for u in units if u.team == "player"]))
            far = max((u for u in units if u.team == "enemy"), key=lambda u: (u.x - px) ** 2 + (u.y - py) ** 2)
            far.boss = True
            far.behavior = "stay"
            far.level = min(20, hi + 2)
            far.items = items_for(far.job, tier, True)
            far.name = THEMES.get(theme, THEMES["ruffian"])["boss"]
        return units

    def _tiered_class(self, jid: str, tier: int) -> str:
        stem, sex = class_stem(jid)
        if TIERS[tier]["promoted"]:
            stem = PROMOTE.get(stem, stem)
        else:
            stem = DEMOTE.get(stem, stem)
        out = class_jid(stem, sex)
        return out if self.gd.key_to_rid("jobs", out) else jid

    def retier(self, units: List[Unit], tier: int, seed: int = 0) -> List[Unit]:
        """Change the difficulty of all enemies (keeps positions and behaviors)."""
        rnd = random.Random(f"retier-{tier}-{seed}")
        lo, hi = TIERS[tier]["levels"]
        for u in units:
            if u.team != "enemy":
                continue
            u.job = self._tiered_class(u.job, tier)
            u.level = min(20, hi + 2) if u.boss else rnd.randint(lo, hi)
            u.items = items_for(u.job, tier, u.boss)
        return units

    # ------------------------------------------------------------------ chapter creation
    def default_plan(self, slot: str, index: int = 0) -> ChapterPlan:
        """A ready-to-play chapter for an empty slot (the n-th one gets a later unlock + harder enemies)."""
        unlock = ["003", "005", "007", "009", "011", "013", "015", "017", "019"][index % 9]
        tier = [1, 2, 2, 3, 3, 4, 4, 5, 6][index % 9]
        choices = [t for t in self.available_templates() if t.get("tier", 3) == tier] or self.available_templates()
        choices.sort(key=lambda t: t["id"])
        template = choices[index % len(choices)]["id"] if choices else "X001"
        theme = (self.templates.get(template) or {}).get("theme", "ruffian")
        n = SLOT_IDS.index(slot) + 1 if slot in SLOT_IDS else index + 1
        plan = ChapterPlan(
            cid=slot,
            title=f"New Chapter {n}",
            label=f"Side Story {n}",
            description="A new adventure.",
            template=template,
            unlock_after=unlock,
            theme=theme,
            tier=tier,
            win="rout",
            boss_name=THEMES.get(theme, THEMES["ruffian"])["boss"],
            opening=[
                Line("クロム", "Normal", "Something feels off about this place."),
                Line("フレデリク", "Angry", "Enemies ahead, milord. Shall we?"),
                Line("クロム", "Angry", "Shepherds, to arms!"),
            ],
            ending=[
                Line("クロム", "Happy", "That's the last of them."),
                Line("フレデリク", "Normal", "Well fought, milord."),
            ],
        )
        plan.units = self.template_units(template, tier, theme)
        return plan

    def create_chapter(self, plan: ChapterPlan, render_title: Optional[Callable[[str, str], bytes]] = None) -> str:
        """Make a brand-new chapter from a plan. Returns the CID (without CID_)."""
        gd = self.gd
        if self.chapter_rid(plan.cid) is not None:
            raise ValueError(f"Chapter {plan.cid} already exists.")
        if self.free_rows() <= 0:
            raise ValueError(f"The game can only keep {MAX_CHAPTERS} chapters; there is no free slot.")
        # chapter row (a copy of Paralogue 1)
        r, f = gd.table("chapters")
        src = gd.key_to_rid("chapters", "CID_X001")
        row_rid = gd.list_add(r, f)
        gd.copy(src, row_rid, [])
        c = plan.cid
        gd.set_string(row_rid, "cid", f"CID_{c}")
        gd.set_string(row_rid, "ceid", f"CEID_{c}E")
        gd.set_string(row_rid, "name", f"MCID_{c}")
        gd.set_string(row_rid, "description", f"MCID_T_{c}")
        gd.set_string(row_rid, "parent", None)
        gd.set_store_dirty("gamedata", True)
        self._copy_map(plan.template, c)
        plan.treasures = self.read_treasures(c)  # the map's own chests and villages
        self.save_chapter(plan, render_title=render_title, new=True)
        return c

    def row_index(self, cid: str) -> int:
        return self.chapter_ids().index(cid)

    def _copy_map(self, tid: str, cid: str):
        """Copy a template's map files (model, height, minimap, grid, landscape, config, terrain script)."""
        gd = self.gd
        t = self.templates.get(tid) or {"id": tid}
        dlc = t.get("source") == "dlc"
        # gameplay grid / landscape / config through Paragon's stores
        for store, src, dst in (
            ("grids", f"data/terrain/{tid}.bin.lz", f"data/terrain/{cid}.bin.lz"),
            ("landscape", f"data/landscape/{tid}.bin.lz", f"data/landscape/{cid}.bin.lz"),
        ):
            if self._exists(src):
                if self._exists(dst):
                    self._replace_multi(store, src, dst)
                else:
                    gd.multi_duplicate(store, src, dst)
        # map config (lighting, camera, music): through Paragon's store, renamed
        src_cfg, dst_cfg = f"map/data/{tid}.bin", f"map/data/{cid}.bin"
        if self._exists(src_cfg):
            if self._exists(dst_cfg):
                self._replace_multi("map_configs", src_cfg, dst_cfg)
                cfg = gd.multi_open("map_configs", dst_cfg)
            else:
                cfg = gd.multi_duplicate("map_configs", src_cfg, dst_cfg)
            gd.set_string(cfg, "name", cid)
            gd.multi_set_dirty("map_configs", dst_cfg, True)
        for kind, path in (("terrain", f"map/terrain/{cid}.bcres.lz"), ("height", f"map/height/{cid}.bin"),
                           ("mini", f"map/mini/{cid}.ctpk.lz")):
            blob = self.template_file(tid, kind)
            if blob is not None:
                self.edits.files[path] = blob
        if dlc:
            # effects / map objects the DLC map brings along (not in the base game)
            for name, blob in self._dlc_arc(tid).items():
                if name.startswith(("effect/", "map/object/")) and not self._exists(name):
                    self.edits.files[name] = _plain(name, blob)
        # terrain script (villages, chests, doors) + the messages it uses
        self._copy_terrain_script(tid, cid)
        # the 'E' dispos (deploy positions with placeholder units) is rebuilt in save_chapter

    def _replace_multi(self, store: str, src: str, dst: str):
        gd = self.gd
        s = gd.multi_open(store, src)
        d = gd.multi_open(store, dst)
        gd.copy(s, d, [])
        gd.multi_set_dirty(store, dst, True)

    def _script_node(self, name: str):
        for n in self.gd.get_script_nodes():
            if n.path.replace("\\", "/").lower() == f"exalt/scripts/{name}.exl".lower():
                return n
        return None

    def _script_source(self, cid: str) -> Optional[str]:
        n = self._script_node(cid)
        if n is None:
            return None
        try:
            return self.gd.open_script(n)
        except Exception:
            return None

    def _set_script(self, name: str, source: str):
        n = self._script_node(name)
        if n is None:
            n = self.gd.new_compiled_script(name)
        self.gd.update_script(n, source)

    def _copy_terrain_script(self, tid: str, cid: str):
        src = self._script_source(f"{tid}_Terrain")
        if not src:
            src = "include std:fe13:prelude;\n"
        # messages the terrain script uses (village talks...) come along into the new chapter's text
        keys = set(re.findall(r'"(MID_[^"]+)"', src))
        if keys:
            self.edits.pending_messages[cid] = self.edits.pending_messages.get(cid, {})
            mpath = f"m/{tid}.bin.lz"
            try:
                self.gd.open_text_data(mpath, True)
                for k in keys:
                    if self.gd.has_message(mpath, True, k):
                        self.edits.pending_messages[cid][k] = self.gd.message(mpath, True, k)
            except Exception:
                logging.warning("No text file for %s", tid)
        self._set_script(f"{cid}_Terrain", src)

    def change_template(self, plan: ChapterPlan):
        self._copy_map(plan.template, plan.cid)
        plan.treasures = self.read_treasures(plan.cid)

    def load_plan(self, cid: str) -> ChapterPlan:
        src = self._script_source(cid) or ""
        plan = plan_from_script(src)
        if plan is None and cid in SLOT_IDS:
            plan = self._plan_from_files(cid)
        if plan is None:
            plan = ChapterPlan(cid=cid, title=self.chapter_name(cid), template=cid)
            plan.unlock_after = ""
        plan.units = self.read_units(cid)
        self.attach_quotes(plan)
        plan.treasures = self.read_treasures(cid)
        plan.__dict__["loaded_unlock"] = plan.unlock_after  # not saved: the world map spot stays unless this changes
        plan.__dict__["loaded_spot"] = list(plan.world_spot or [])
        return plan

    def is_legacy(self, cid: str) -> bool:
        """A chapter in your slots made outside the Map Maker (its script has no Map Maker plan):
        saving it here replaces its script with the Map Maker's."""
        if cid not in SLOT_IDS:
            return False
        src = self._script_source(cid)
        return bool(src) and PLAN_MARK not in src

    def _plan_from_files(self, cid: str) -> ChapterPlan:
        """A plan for a chapter in your slots that has none (made before the Map Maker): its
        names, unlock and story are read from its files; its map stays its own."""
        plan = ChapterPlan(cid=cid, title=self.chapter_name(cid), template=cid, label="", description="")
        plan.label = self.message(f"MCID_{cid}_T") or ""
        plan.description = self.message(f"MCID_T_{cid}") or ""
        row = self.chapter_rid(cid)
        req = self.gd.int(row, "requirement") if row is not None else None
        rows = self.chapter_rows()
        plan.unlock_after = self._cid(rows[req]) if req is not None and 0 <= req < len(rows) else "X001"
        tpath = f"m/{cid}.bin.lz"
        try:
            self.gd.open_text_data(tpath, True)
            plan.opening = parse_conversation(self.gd.message(tpath, True, f"MID_{cid}_OP1"))
            plan.ending = parse_conversation(self.gd.message(tpath, True, f"MID_{cid}_ED1"))
        except Exception:
            pass
        return plan

    def clear_chapter(self, plan: ChapterPlan, render_title: Optional[Callable[[str, str], bytes]] = None) -> str:
        """Start a chapter of your slots over: the new plan's map, units, story and events
        replace everything the chapter had (its row and slot stay)."""
        c = plan.cid
        if c in GAME_CIDS or self.chapter_rid(c) is None:
            raise ValueError(f"{c} is not one of your chapters.")
        self.edits.pending_messages.pop(c, None)
        self._copy_map(plan.template, c)
        plan.treasures = self.read_treasures(c)
        self.save_chapter(plan, render_title=render_title, new=True)
        return c

    def chapters_after(self, cid: str) -> List[str]:
        """Map Maker chapters that appear after this one (their unlock chapter)."""
        out = []
        for ch in self.custom_chapters():
            if ch["cid"] == cid:
                continue
            try:
                p = plan_from_script(self._script_source(ch["cid"]) or "")
            except Exception:
                p = None
            if p is not None and p.unlock_after == cid:
                out.append(ch["cid"])
        return out

    def delete_chapter(self, cid: str):
        """Remove a chapter that is not one of the game's own: its row in the chapter list, its
        bottom-screen spot and its world map node. The chapter's own files stay in the output folder
        (nothing reads them any more). Chapters below it in the list move up one place."""
        gd = self.gd
        if cid in GAME_CIDS:
            raise ValueError(f"{cid} is one of the game's own chapters.")
        if self.chapter_rid(cid) is None:
            raise ValueError(f"There is no chapter {cid}.")
        r, f = gd.table("chapters")
        gd.list_remove(r, f, self.row_index(cid))
        gd.set_store_dirty("gamedata", True)
        node = next((n for n in gd.nodes() if "GMap" in n.name), None)
        if node is not None:
            rows = gd.items(node.rid, "table") or []
            for i in reversed(range(len(rows))):
                if gd.string(rows[i], "gm") == f"GM_{cid}":
                    gd.list_remove(node.rid, "table", i)
                    gd.set_store_dirty("gmap", True)
        self.edits.world_nodes.pop(cid, None)
        self.edits.gm_rows.pop(cid, None)
        self.edits.pending_messages.pop(cid, None)
        self.edits.retired.add(cid)

    def attach_quotes(self, plan: ChapterPlan):
        """Battle quotes of the plan back onto their units (by the unit's own PID)."""
        for u in plan.units:
            u.quotes = [{"vs": q.vs, "text": q.text} for q in plan.quotes if q.enemy and q.enemy == u.pid]
            if u.quotes:
                u.own = True

    # ------------------------------------------------------------------ chests, villages, terrain
    def read_treasures(self, cid: str) -> List[ce.Treasure]:
        src = self._script_source(f"{cid}_Terrain")
        msgs = {}
        for path in (f"m/{cid}.bin.lz",):
            try:
                self.gd.open_text_data(path, True)
                for k in self.gd.enumerate_messages(path, True) or []:
                    msgs[k] = self.gd.message(path, True, k)
            except Exception:
                pass
        for k, v in self.edits.pending_messages.get(cid, {}).items():
            msgs.setdefault(k, v)
        return ce.read_treasures(src, msgs, parse_conversation)

    def treasure_tiles(self, grid) -> List[Tuple[int, int, str]]:
        """(x, y, "chest" / "village") of the chest and village / house tiles of a map grid."""
        if not grid:
            return []
        w, h, raw = grid
        out = []
        for y in range(h):
            for x in range(w):
                t = raw[y * 32 + x]
                if t in ce.CHEST_TILES:
                    out.append((x, y, "chest"))
                elif t in ce.VILLAGE_TILES:
                    out.append((x, y, "village"))
        return out

    def set_tile(self, cid: str, x: int, y: int, tile: int) -> bool:
        """Change one gameplay tile of a chapter's map (the 3D map model stays as it is)."""
        try:
            g = self.gd.multi_open("grids", f"data/terrain/{cid}.bin.lz")
        except Exception:
            return False
        raw = list(self.gd.bytes(g, "grid"))
        i = y * 32 + x
        if not (0 <= i < len(raw)) or raw[i] == tile:
            return False
        raw[i] = tile
        self.gd.set_bytes(g, "grid", raw)
        self.gd.multi_set_dirty("grids", f"data/terrain/{cid}.bin.lz", True)
        return True

    def save_chapter(self, plan: ChapterPlan, render_title: Optional[Callable[[str, str], bytes]] = None,
                     new: bool = False):
        """Write everything of a Chapter Maker chapter (row texts, units, script, world map, title)."""
        gd = self.gd
        c = plan.cid
        row = self.chapter_rid(c)
        if row is None:
            raise KeyError(f"No chapter {c}")
        # unlock: requirement = row index of the chapter that must be cleared
        if plan.unlock_after and self.chapter_rid(plan.unlock_after) is not None:
            gd.set_int(row, "requirement", self.row_index(plan.unlock_after))
            gd.set_store_dirty("gamedata", True)
        # names
        gd.set_message(self._msg_path, True, f"MCID_{c}", plan.title or c)
        gd.set_message(self._msg_path, True, f"MCID_T_{c}", plan.description or plan.title or c)
        gd.set_message(self._msg_path, True, f"MCID_{c}_T", plan.label or "")
        # dispos / person: start from the template's files on a new chapter
        if new or not self._exists(self.dispos_key(c)):
            self._fresh_dispos(c)
        self.write_units(c, plan.units, "Normal", plan.tier, plan.theme)
        self._make_e_dispos(c, [u for u in plan.units if u.team == "player"])
        # chapter text
        tpath = f"m/{c}.bin.lz"
        if not self._text_exists(tpath):
            gd.new_text_data(tpath, True)
        else:
            gd.open_text_data(tpath, True)
        op = conversation(plan.opening)
        ed = conversation(plan.ending)
        gd.set_message(tpath, True, f"MID_{c}_OP1", op or None)
        gd.set_message(tpath, True, f"MID_{c}_ED1", ed or None)
        boss = next((u for u in plan.units if u.team == "enemy" and u.boss), None)
        boss_face = (boss.face if boss else "") or ""
        has_boss_line = bool(boss and boss_face and plan.boss_line.strip())
        gd.set_message(tpath, True, f"MID_{c}_BOSS_DIE1",
                       boss_talk(boss_face[4:] if boss_face.startswith("FID_") else boss_face, plan.boss_line)
                       if has_boss_line else None)
        for k, v in self.edits.pending_messages.pop(c, {}).items():
            gd.set_message(tpath, True, k, v)
        # events: battle quotes come from the units (their PIDs are known now)
        def face_of(u: Unit) -> str:
            if u.face or not u.character:
                return u.face
            r = gd.key_to_rid("characters", u.character)
            return (gd.string(r, "fid") or "") if r else ""

        plan.quotes = [ce.BattleQuote(u.pid, q.get("vs", ""), face_of(u), q.get("text", ""))
                       for u in plan.units if u.team in ("enemy", "ally") and u.pid for q in u.quotes
                       if (q.get("text") or "").strip()]
        ev_msgs = ce.event_messages(plan, conversation, boss_talk)
        for k, v in ev_msgs.items():
            gd.set_message(tpath, True, k, v)
        if any(ce.flashes(plan, e) for e in plan.tile_events):
            from paragon.unlimited.map_maker import event_sparkle

            event_sparkle.ensure(gd, self.edits.files, self._read)
        # chests and villages (terrain script)
        talk_keys = {(t.x, t.y): f"MID_{c}_PU_VIL{i}" for i, t in enumerate(plan.treasures, 1)
                     if ev_msgs.get(f"MID_{c}_PU_VIL{i}")}
        self._set_script(f"{c}_Terrain", ce.write_treasures(self._script_source(f"{c}_Terrain"), plan.treasures,
                                                            talk_keys))
        # script
        self._set_script(c, chapter_script(plan, True, boss.pid if boss else None, bool(op), bool(ed), has_boss_line,
                                           any(u.team == "join" for u in plan.units), ev_msgs))
        # world map node, landmark, bottom-screen spot, title card. A chapter that already has its
        # spot keeps it (and the world map files stay as they are) unless its unlock changed.
        spot = self._spot(plan)
        keep = (not new and plan.unlock_after == plan.__dict__.get("loaded_unlock")
                and list(spot or []) == list(plan.__dict__.get("loaded_spot") or [])
                and self._has_world_node(c))
        if not keep:
            self.edits.world_nodes[c] = (self.row_index(c), plan.unlock_after or "X001",
                                         (self.templates.get(plan.template) or {}).get("landmark") or "", spot)
            self._set_gm(c, plan.unlock_after or "X001")
        if (ce.seize_tile(plan) or ce.survive_turn(plan)) and self.banner_renderer is not None:
            from paragon.unlimited.map_maker import mission_banner

            try:
                mission_banner.write(self.edits.files, self._read, plan, self.banner_renderer)
            except Exception:
                logging.exception("Mission banner")
        if render_title is not None:
            try:
                self.edits.files[f"chapter/title/E/{c}.ctpk.lz"] = self.title_card(plan, render_title)
            except Exception:
                logging.exception("Title card")

    @staticmethod
    def _spot(plan: ChapterPlan) -> Optional[Tuple[int, int]]:
        s = plan.world_spot or []
        if len(s) != 2:
            return None
        try:
            return wm.clamp_gm(float(s[0]), float(s[1]))
        except (TypeError, ValueError):
            return None

    def world_map_layout(self) -> dict:
        """The world map as the spot picker shows it: {"nodes": {cid: (x, y)} on the bottom-screen
        map, "routes": [(from, to)], "names": {cid: display name}}. Spots chosen in this session but
        not written yet are included."""
        out = {"nodes": {}, "routes": [], "names": {}}
        try:
            spots = wm.Spots(bytes(self.gd.read_file("gmap/spot.bcres.lz")))
        except Exception:
            logging.exception("World map")
            return out
        nodes = spots.nodes()
        for cid, (_bone, pos) in nodes.items():
            out["nodes"][cid] = wm.gm_spot(pos)
        for name in spots.routes():
            parts = name.split("_")
            if len(parts) == 3 and parts[1] in nodes and parts[2] in nodes:
                out["routes"].append((parts[1], parts[2]))
        for cid, item in self.edits.world_nodes.items():
            anchor, spot = item[1], (item[3] if len(item) > 3 else None)
            if spot is not None:
                out["nodes"][cid] = tuple(spot)
            out["routes"] = [r for r in out["routes"] if r[1] != cid] + [(anchor, cid)]
        for cid in out["nodes"]:
            try:
                out["names"][cid] = self.chapter_name(cid)
            except Exception:
                out["names"][cid] = cid
        return out

    def _has_world_node(self, cid: str) -> bool:
        if cid in self.edits.world_nodes:
            return True
        try:
            spots = wm.Spots(bytes(self.gd.read_file("gmap/spot.bcres.lz")))
            return cid in spots.nodes()
        except Exception:
            return False

    def _text_exists(self, path: str) -> bool:
        try:
            if self.gd.has_text_data(path, True):
                return True
        except Exception:
            pass
        try:
            return self.gd.file_exists(path, True)
        except Exception:
            return False

    def _fresh_dispos(self, cid: str):
        """New chapter: dispos/person from Paralogue 1 with only an empty Player and Enemy army."""
        gd = self.gd
        for store, key in (("dispos", self.dispos_key(cid)), ("person", self.person_key(cid))):
            src = key.replace(cid, "X001")
            if self._exists(key):
                self._replace_multi(store, src, key)
            else:
                gd.multi_duplicate(store, src, key)
        d = gd.multi_open("dispos", self.dispos_key(cid))
        facs = gd.items(d, "factions") or []
        for i in reversed(range(len(facs))):
            name = gd.string(facs[i], "name")
            if name not in ("Player", "Enemy"):
                gd.list_remove(d, "factions", i)
                continue
            tb = gd.rid(facs[i], "table")
            for j in reversed(range(len(gd.items(tb, "spawns") or []))):
                gd.list_remove(tb, "spawns", j)
        p = gd.multi_open("person", self.person_key(cid))
        gd.set_string(p, "filename", cid)
        for i in reversed(range(len(gd.items(p, "people") or []))):
            gd.list_remove(p, "people", i)
        self.mark_dirty(cid)

    def _make_e_dispos(self, cid: str, players: List[Unit]):
        """<cid>E: the deploy positions with placeholder units (the game uses it for the map preview)."""
        gd = self.gd
        key = f"data/dispos/{cid}E.bin.lz"
        if self._exists(key):
            self._replace_multi("dispos", "data/dispos/X001E.bin.lz", key)
        else:
            gd.multi_duplicate("dispos", "data/dispos/X001E.bin.lz", key)
        d = gd.multi_open("dispos", key)
        fac = (gd.items(d, "factions") or [None])[0]
        if fac is None:
            return
        tb = gd.rid(fac, "table")
        spawns = gd.items(tb, "spawns") or []
        proto = spawns[0]
        for i in reversed(range(1, len(spawns))):
            gd.list_remove(tb, "spawns", i)
        for k, u in enumerate(players):
            sp = proto if k == 0 else gd.list_add(tb, "spawns")
            if k:
                gd.copy(proto, sp, [])
            gd.set_bytes(sp, "coord_1", [u.x, u.y])
            gd.set_bytes(sp, "coord_2", [u.x, u.y])
        gd.multi_set_dirty("dispos", key, True)

    def _set_gm(self, cid: str, anchor: str):
        """Bottom-screen spot GM_<cid> (placed next to the anchor; the exact spot follows the node on flush)."""
        gd = self.gd
        node = next((n for n in gd.nodes() if "GMap" in n.name), None)
        if node is None:
            return
        rows = gd.items(node.rid, "table") or []
        by = {gd.string(r, "gm"): r for r in rows}
        r = by.get(f"GM_{cid}")
        if r is None:
            r = gd.list_add(node.rid, "table")
            src = by.get(f"GM_{anchor}") or (rows[0] if rows else None)
            if src is not None:
                gd.copy(src, r, [])
            gd.set_string(r, "gm", f"GM_{cid}")
        self.edits.gm_rows[cid] = r
        gd.set_store_dirty("gmap", True)

    # ------------------------------------------------------------------ title card
    def title_card(self, plan: ChapterPlan, render: Callable[[str, str], bytes]) -> bytes:
        """render(label, title) -> 256x64 RGBA; returns the LZ13 ctpk."""
        rgba = render(plan.label or "", plan.title or "")
        tmpl = self._read("chapter/title/E/X001.ctpk.lz")
        if tmpl is None:
            raise FileNotFoundError("chapter/title/E/X001.ctpk.lz")
        from paragon.unlimited.portraits.portrait_files import CtpkTexture

        tex = CtpkTexture.parse(tmpl)
        enc = bytes(pgn.encode_etc1(rgba, tex.width, tex.height, tex.fmt == 13))
        return tex.with_pixels(enc)

    # ------------------------------------------------------------------ slots
    def fill_free_slots(self, render_title=None, limit: Optional[int] = None) -> List[str]:
        """Create ready-to-play chapters in every free slot."""
        made = []
        while self.free_rows() > 0 and (limit is None or len(made) < limit):
            slot = self.next_slot_id()
            if slot is None:
                break
            plan = self.default_plan(slot, SLOT_IDS.index(slot))
            self.create_chapter(plan, render_title)
            made.append(slot)
        return made


def _plain(name: str, blob: Optional[bytes]) -> Optional[bytes]:
    """Arc contents are stored compressed; the layered file system works with plain bytes."""
    if blob is None:
        return None
    if name.endswith(".lz"):
        try:
            return bytes(pgn.decompress_lz13(blob))
        except Exception:
            return blob
    return blob


class ChapterMakerEdits:
    """Binary files the Chapter Maker writes when the project is saved."""

    def __init__(self, gd):
        self.gd = gd
        self.files: Dict[str, bytes] = {}
        self.world_nodes: Dict[str, tuple] = {}  # cid -> (row, anchor, landmark, spot or None)
        self.gm_rows: Dict[str, int] = {}
        self.pending_messages: Dict[str, Dict[str, str]] = {}
        self.retired: set = set()  # deleted chapters whose world map node is taken off on save

    def has_pending(self) -> bool:
        return bool(self.files or self.world_nodes or self.retired)

    def apply_world_map(self) -> List[str]:
        """Add / move the nodes in gmap/spot.bcres and the landmark names in gmap/model.bcres."""
        if not self.world_nodes and not self.retired:
            return []
        gd = self.gd
        spots = wm.Spots(bytes(gd.read_file("gmap/spot.bcres.lz")))
        if self.retired:
            for cid in sorted(self.retired):
                spots.retire(cid)
            self.retired.clear()
            if not self.world_nodes:
                self.files["gmap/spot.bcres.lz"] = spots.to_bytes()
                return []
        marks = wm.Landmarks(bytes(gd.read_file("gmap/model.bcres.lz")))
        names = set(marks.names())
        placed = []
        written = []
        for cid, item in sorted(self.world_nodes.items()):
            row, anchor, landmark = item[:3]
            spot = item[3] if len(item) > 3 else None
            nodes = spots.nodes()
            if anchor not in nodes:
                anchor = "X001" if "X001" in nodes else next(iter(nodes))
            if spot is not None:  # the spot chosen in the Map Maker
                pos = wm.from_gm(*spot)
                spots.set_node(cid, row, anchor, pos, wm.road_points(nodes[anchor][1], pos))
                placed.append(pos)
                self._gm_from(cid, pos, spot)
                if f"m_{cid}" not in names:
                    target = f"m_{landmark}" if landmark and f"m_{landmark}" in names else f"m_{anchor}"
                    marks.set_alias(f"m_{cid}", target if target in names else "m_X001")
                written.append(cid)
                continue
            if cid in nodes:
                route = spots.route_to(cid)
                if route and route[0] == f"route_{anchor}_{cid}" and spots.node_name(cid) == f"pos_{cid}_{row}":
                    placed.append(nodes[cid][1])
                    self._gm_from(cid, nodes[cid][1])
                    continue
            pos, points = spots.auto_place(anchor, placed)
            spots.set_node(cid, row, anchor, pos, points)
            placed.append(pos)
            self._gm_from(cid, pos)
            target = f"m_{landmark}" if landmark and f"m_{landmark}" in names else f"m_{anchor}"
            if target not in names:
                target = "m_X001"
            marks.set_alias(f"m_{cid}", target)
            written.append(cid)
        self.files["gmap/spot.bcres.lz"] = spots.to_bytes()
        self.files["gmap/model.bcres.lz"] = marks.to_bytes()
        self.world_nodes.clear()
        return written

    def _gm_from(self, cid: str, pos, spot=None):
        r = self.gm_rows.get(cid)
        if r is None:
            return
        x, y = spot if spot is not None else wm.gm_spot(pos)
        self.gd.set_int(r, "position_x", x)
        self.gd.set_int(r, "position_y", y)
        self.gd.set_store_dirty("gmap", True)

    def flush(self, output_path: Optional[str] = None, backup_dir: Optional[str] = None) -> List[str]:
        """Write the pending binary files (decompressed contents; .lz files are compressed on
        write) to the output folder. Files they replace in the output folder are copied to
        backup_dir first."""
        out = []
        for path, blob in sorted(self.files.items()):
            if backup_dir and output_path:
                src = os.path.join(output_path, path)
                if os.path.isfile(src):
                    dst = os.path.join(backup_dir, path)
                    os.makedirs(os.path.dirname(dst), exist_ok=True)
                    with open(src, "rb") as f_in, open(dst, "wb") as f_out:
                        f_out.write(f_in.read())
            self.gd.write_file(path, blob)
            out.append(path)
        self.files.clear()
        return out
