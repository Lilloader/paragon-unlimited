"""Paragon Unlimited (developer tool): build Data/FE13/PU_MapTemplates.json from the game's maps.

For every Awakening map with a terrain grid (main story, paralogues and, when given, the DLC maps)
it records the map size, the player start positions and the enemy layout of the Normal mode
(position, class, behavior, boss), plus a difficulty tier and terrain tags. Chapter Maker turns a
template into generic enemies at any difficulty, so only positions and class lines are kept.

Usage: python scripts/pu_build_map_templates.py <romfs> <out.json> [<dlc unpacked layer> <dlc arc folder>]
"""
import json
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from paragon import paragon as pgn  # noqa: E402
from paragon.core.services import fe13_chapter_maker as cm  # noqa: E402

NORMAL = 0x80
SKIP = {"P001", "E000"}
FIX_CLASS = {
    "ゾンビ": "戦士", "マミー": "蛮族", "マスターロード": "剣士", "ロード": "剣士", "ロード2": "剣士",
    "マスターロード2": "ソードマスター", "戦術師": "魔道士", "神軍師": "賢者", "神軍師2": "賢者",
    "踊り子": "剣士", "踊り子2": "剣士", "踊り子3": "ソードマスター", "村人": "ソルジャー", "商人": "ソルジャー",
    "オーバーロード": "勇者", "オーバーロード2": "勇者", "スターロード": "ソードマスター", "マムクート": "戦士",
    "マムクート2": "ウォーリアー", "ラグズ": "戦士", "ラグズ2": "ウォーリアー", "ボス": "ソーサラー",
    "ボス男2": "ソーサラー", "ボス女2": "ソーサラー", "シルエット": "ソードマスター", "ダミー": "ソルジャー",
    "予約０１": "勇者", "予約０２": "勇者", "ダークナイト2": "ソーサラー",
}
ARMY_THEME = {
    "BID_ならずもの": "ruffian", "BID_ペレジア軍": "plegia", "BID_ヴァルム帝国軍": "valm", "BID_屍兵": "risen",
    "BID_ギムレー教軍": "grimleal", "BID_その他": "mercenary",
}


def tier_of(levels, promoted):
    if not levels:
        return 2
    avg = sum(levels) / len(levels)
    ratio = sum(promoted) / len(promoted)
    if ratio > 0.5:
        return 4 if avg <= 8 else 5 if avg <= 14 else 6
    return 1 if avg <= 3 else 2 if avg <= 7 else 3


def tags_of(w, h, raw):
    c = Counter(raw[y * 32 + x] for y in range(h) for x in range(w))
    n = max(1, w * h)
    share = lambda ids: sum(c[i] for i in ids) / n  # noqa: E731
    tags = []
    if share({4}) > 0.2:
        tags.append("Desert")
    if share({59, 60, 61, 62, 63, 64, 65, 66, 67}) > 0.2:
        tags.append("Snow")
    if share({69, 70, 12, 13}) > 0.15:
        tags.append("Ship")
    elif share({16, 17, 18}) > 0.15:
        tags.append("Water")
    if share({33, 35, 40, 41, 42, 34, 36, 37}) > 0.3:
        tags.append("Castle")
    if share({3, 61}) > 0.12:
        tags.append("Forest")
    if share({6, 7, 62}) > 0.12:
        tags.append("Mountains")
    if c[22] + c[23] + c[25] + c[64] >= 2:
        tags.append("Villages")
    if share({45, 46, 47}) > 0.1:
        tags.append("Lava")
    if not tags:
        tags.append("Fields")
    return tags


def main(romfs, out_path, dlc_layer=None, dlc_arcs=None):
    layers = [dlc_layer] if dlc_layer else []
    empty = os.path.join(os.path.dirname(os.path.abspath(out_path)), "_tmpl_empty_out")
    os.makedirs(empty, exist_ok=True)
    gd = pgn.GameData.load(empty, romfs, "FE13", "EnglishNA", os.path.join("Data", "FE13"), layers)
    gd.read()
    msg = "m/GameData.bin.lz"
    gd.open_text_data(msg, True)

    def message(k):
        return gd.message(msg, True, k) if k and gd.has_message(msg, True, k) else None

    chapters = {}
    r, f = gd.table("chapters")
    for c in gd.items(r, f):
        cid = (gd.key(c) or "")[4:]
        nm = gd.string(c, "name")
        chapters[cid] = (message((nm or "") + "_T"), message(nm))

    ids = sorted(p[:-7] for p in os.listdir(os.path.join(romfs, "data", "terrain")) if p.endswith(".bin.lz"))
    sources = [(i, "base") for i in ids if i not in SKIP and os.path.isfile(os.path.join(romfs, "map", "terrain", i + ".bcres.lz"))]
    dlc_names = {}
    if dlc_layer and dlc_arcs:
        from paragon.core.services import fe13_dlc

        ws = os.path.dirname(dlc_layer.rstrip("/\\"))
        for e in fe13_dlc.episodes(ws[:-4] if ws.endswith("_DLC") else ws):
            dlc_names[e["id"]] = e.get("name")
        for p in sorted(os.listdir(os.path.join(dlc_layer, "data", "terrain"))):
            if p.endswith(".bin.lz"):
                sources.append((p[:-7], "dlc"))

    maps = []
    for cid, src in sources:
        try:
            g = gd.multi_open("grids", f"data/terrain/{cid}.bin.lz")
            w, h = gd.int(g, "map_width"), gd.int(g, "map_height")
            raw = bytes(gd.bytes(g, "grid"))
            d = gd.multi_open("dispos", f"data/dispos/{cid}.bin.lz")
        except Exception as e:  # noqa: BLE001
            print("skip", cid, e, file=sys.stderr)
            continue
        try:
            p = gd.multi_open("person", f"data/person/{cid}.bin.lz")
            people = {gd.string(x, "pid"): x for x in gd.items(p, "people")}
        except Exception:  # noqa: BLE001
            people = {}
        players, enemies, seen = [], [], set()
        levels, promoted, armies = [], [], Counter()
        grid = (w, h, raw)
        for fac in gd.items(d, "factions"):
            name = gd.string(fac, "name")
            if name not in ("Player", "Enemy"):
                continue
            for sp in gd.items(gd.rid(fac, "table"), "spawns"):
                x, y = gd.bytes(sp, "coord_1")
                if name == "Player":
                    if (x, y) not in seen and cm.ChapterMaker.can_stand(grid, x, y):
                        players.append([x, y])
                        seen.add((x, y))
                    continue
                if not (gd.int(sp, "spawn_flags_1") & NORMAL):
                    continue
                if (x, y) in seen:
                    continue
                pid = gd.string(sp, "pid")
                person = people.get(pid) or gd.key_to_rid("characters", pid)
                job = gd.rid(person, "job") if person else None
                jid = gd.key(job) if job else "JID_ソルジャー男"
                stem, sex = cm.class_stem(jid)
                stem = FIX_CLASS.get(stem, stem)
                jid = cm.class_jid(stem, sex)
                if not gd.key_to_rid("jobs", jid):
                    jid = "JID_ソルジャー男"
                if not cm.ChapterMaker.can_stand(grid, x, y, jid):
                    continue
                seen.add((x, y))
                boss = bool(gd.int(sp, "spawn_flags_2") & cm.BOSS_FLAG)
                mv = gd.string(sp, "move") or ""
                act = gd.string(sp, "action") or ""
                beh = "stay" if mv == "AI_MV_Null" else "charge" if act == "AI_AC_Everytime" else "wait"
                enemies.append({"x": x, "y": y, "cls": jid, "behavior": beh, "boss": boss})
                if person:
                    levels.append(gd.int(person, "level") or 1)
                    promoted.append(stem in cm.DEMOTE)
                    a = gd.rid(person, "army")
                    if a:
                        armies[gd.key(a)] += 1
        if len(players) < 2 or not enemies:
            print("skip", cid, "players", len(players), "enemies", len(enemies), file=sys.stderr)
            continue
        theme = "ruffian"
        for army, _n in armies.most_common():
            if army in ARMY_THEME:
                theme = ARMY_THEME[army]
                break
        if src == "base":
            label, title = chapters.get(cid, (None, None))
        else:
            label, title = "DLC", dlc_names.get(cid)
        maps.append({
            "id": cid,
            "source": src,
            "label": label or cid,
            "title": title or cid,
            "size": [w, h],
            "players": players,
            "enemies": enemies,
            "theme": theme,
            "tier": tier_of(levels, promoted),
            "tags": tags_of(w, h, raw),
            "landmark": cid if src == "base" else "",
        })
        print(cid, w, h, len(players), len(enemies), theme, maps[-1]["tier"], maps[-1]["tags"], file=sys.stderr)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"version": 1, "maps": maps}, f, ensure_ascii=False, separators=(",", ":"))


if __name__ == "__main__":
    main(*sys.argv[1:5])
