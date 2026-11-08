"""Paragon Unlimited - readable English names for FE13 asset definition / preset entries."""
import re

WEAPON_WORDS = {
    "剣": "Sword", "槍": "Lance", "斧": "Axe", "弓": "Bow", "魔": "Tome", "魔法": "Tome", "杖": "Staff",
    "素手": "Unarmed", "竜石": "Dragonstone", "短剣": "Dagger", "石": "Stone",
}
EXTRA = {
    "馬": "Horse", "竜": "Wyvern", "飛竜": "Wyvern", "天馬": "Pegasus", "グリフォン": "Griffon",
    "汎用兵種": "generic class", "花嫁": "Bride", "傭兵": "Mercenary", "マムクートドラゴン": "Manakete dragon",
    "ラグズウサギ": "Taguel rabbit", "焼けマン": "Burned man", "BOSSギムレー": "Grima (boss)",
    "BOSSギムレー背中": "Grima (boss) back", "BOSSギムレー首": "Grima (boss) neck",
    "BOSSギムレー背中(BMAP用モーション)": "Grima (boss) back (map motion)",
    "勝利ボイス確認用": "Victory voice test", "イベントモーション": "Event motion ",
}
GROUPS = {
    "英雄": "Heroes", "マッチョ": "Muscular", "マイユニット": "Avatar", "徒歩": "Infantry",
    "徒歩重": "Armored infantry", "サムライ": "Samurai", "ローブ": "Robed", "軽業": "Acrobats",
    "騎馬": "Cavalry", "飛竜": "Wyverns", "天馬": "Pegasi", "グリフォン": "Griffons", "特殊": "Special",
}
ALIASES = {  # short forms used in preset names
    "ルキナ": "Lucina", "マイユニ男": "Robin (M)", "マイユニ女": "Robin (F)", "マイユニ": "Robin",
    "旅商人男": "Merchant (M)", "旅商人女": "Merchant (F)", "アーマー": "Knight", "グレナイト": "Great Knight",
    "ダークマージ": "Dark Mage", "賢者": "Sage", "本": "Tome", "ロリ": "petite", "マッチョ": "muscular",
    "ドラゴン": "Dragon", "ウサギ": "Rabbit",
}
WORDS = {
    "上級": "promoted", "男": "(M)", "女": "(F)", "全般": "all", "女性全般": "All females",
    "男性全般": "All males", "屍兵全般": "All Risen", "初期プリセット": "Default presets",
}


def _lookup_display(gd, table, key):
    try:
        rid = gd.key_to_rid(table, key)
        return gd.display(rid) if rid else None
    except Exception:
        return None


def english_name(gd, name: str) -> str:
    if not name:
        return "(no name)"
    for prefix, table in (("PID_", "characters"), ("JID_", "jobs"), ("IID_", "items")):
        if name.startswith(prefix):
            d = _lookup_display(gd, table, name)
            return f"{d} ({name})" if d else name
    if re.match(r"^\d{4}/\d\d/\d\d", name):
        return "File header (date / author)"
    base = name.lstrip("<>")
    if base in WORDS:
        return WORDS[base]
    if base.endswith("系") and base[:-1] in GROUPS:
        return f"Group: {GROUPS[base[:-1]]}"
    if base in EXTRA:
        return EXTRA[base]
    parts = re.split(r"[・]", base)
    out = []
    for i, p in enumerate(parts):
        star = p.startswith("★")
        p = p.lstrip("★")
        if i > 0 and p in WEAPON_WORDS:
            out.append(WEAPON_WORDS[p])
            continue
        if p in EXTRA or p in ALIASES:
            out.append(("★ " if star else "") + (EXTRA.get(p) or ALIASES[p]).strip())
            continue
        promoted = "上級" in p
        p2 = p.replace("上級", "")
        gender = ""
        if p2.endswith("男") or p2.endswith("女"):
            gender = " (M)" if p2.endswith("男") else " (F)"
        text = None
        for cand in (p2, p2[:-1] if gender else p2):
            d = _lookup_display(gd, "jobs", "JID_" + cand) or _lookup_display(gd, "jobs", "JID_" + cand + "男")
            if d:
                text = d + gender
                break
            d = _lookup_display(gd, "characters", "PID_" + cand)
            if d:
                text = d
                break
        if text is None and p2 in ALIASES:
            text = ALIASES[p2]
        if text is None:
            text = _split_compound(gd, p2)
        text = text or p
        if promoted:
            text += " (promoted)"
        out.append(("★ " if star else "") + text)
    return " - ".join(out)



def _job(gd, cand):
    for key in ("JID_" + cand, "JID_" + cand + "男", "JID_" + cand + "女"):
        d = _lookup_display(gd, "jobs", key)
        if d:
            return d
    return None


def _split_compound(gd, p):
    for k, v in sorted(ALIASES.items(), key=lambda kv: -len(kv[0])):
        if p.startswith(k) and len(p) > len(k):
            rest = p[len(k):]
            d = _lookup_display(gd, "characters", "PID_" + rest)
            if d:
                return f"{d} ({v})"
    """'ダークナイトマリアベル' -> 'Maribelle (Dark Knight)'; also prefixes like 傭兵/花嫁/イベントモーション."""
    for k, v in EXTRA.items():
        if p.startswith(k) and len(p) > len(k):
            rest = p[len(k):]
            d = _lookup_display(gd, "characters", "PID_" + rest) or _job(gd, rest)
            if d:
                return f"{d} ({v.strip()})"
    for cut in range(len(p) - 1, 0, -1):
        job = _job(gd, p[:cut]) or {"ペガサス": "Pegasus Knight", "ジェネラル": "General", "細い": "slim"}.get(p[:cut])
        if job:
            ch = _lookup_display(gd, "characters", "PID_" + p[cut:])
            if ch:
                return f"{ch} ({job})"
        ch = _lookup_display(gd, "characters", "PID_" + p[:cut])
        if ch:
            job = _job(gd, p[cut:]) or {"戦士": "Warrior", "蛮族": "Barbarian"}.get(p[cut:])
            if job:
                return f"{ch} ({job})"
    return None
