"""Paragon Unlimited (developer tool): build Data/FE13/PU_SpriteParts.json from the game's own map
sprites. Not needed at run time.

For every class (sprite name stem, e.g. ドラゴンナイト) and sex, the game has a generic sprite
(ドラゴンナイト男) and many character versions (ドラゴンナイトクロム...): the same body with another head.
Comparing them gives, per pixel:
  - union: pixels where any character version differs from the generic one (heads, hair, hats)
  - core:  pixels where at least CORE of them differ (the generic head itself)
  - fill:  the pixel most versions agree on (the body under the head), or transparent
and per frame cell an anchor (centre x, top y of the core) used to line heads up between classes.

Usage: python scripts/pu_build_sprite_parts.py <romfs> <out.json> <names.json> <anims.json> <people.json>
(names / anims / people are dumps made with Paragon's data layer; see the v1.14 notes)."""
import base64
import json
import os
import sys
import zlib

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from paragon.core.services import fe13_sprite_workshop as ws  # noqa: E402

CORE = 0.3
MIN_VARIANTS = 2
NEAR = 4  # pixels a head may reach past the core (long hair, hats)


def decompress(data: bytes) -> bytes:
    sys.path.insert(0, os.environ.get("PU_LZ_PATH", ""))
    from lz import decompress as dz  # pure-python LZ11/LZ13 (dev machine)

    return dz(data)


def main(romfs, out_path, names_path, anims_path, people_path):
    names = json.load(open(names_path, encoding="utf-8"))["names"]
    jobs = json.load(open(names_path, encoding="utf-8"))["jobs"]
    anims = json.load(open(anims_path, encoding="utf-8"))
    people = json.load(open(people_path, encoding="utf-8"))
    unit = os.path.join(romfs, "map", "unit")
    cache = {}

    def load(n):
        if n not in cache:
            p = os.path.join(unit, n + "青.ctpk.lz")
            if not os.path.isfile(p):
                cache[n] = None
            else:
                s = ws.sheet_from_ctpk(decompress(open(p, "rb").read()))
                cache[n] = np.frombuffer(bytes(s.rgba), np.uint8).reshape(s.height, s.width, 4).copy()
        return cache[n]

    stems = sorted({j[:-1] if j[-1] in "男女" else j for j in jobs}, key=len, reverse=True)
    groups = {}
    for n in names:
        st = next((s for s in stems if n.startswith(s)), None)
        if st is None:
            continue
        rest = n[len(st):]
        groups.setdefault(st, {"generic": {}, "variants": []})
        if rest in ("男", "女"):
            groups[st]["generic"][rest] = n
        elif rest:
            groups[st]["variants"].append(rest)

    out = {"version": 1, "core": CORE, "classes": {}, "heads": {},
           "job_names": {k: v for k, v in jobs.items() if v},
           "people": {k: v["name"] for k, v in people.items() if v.get("name")}}
    for st, g in sorted(groups.items()):
        gens = g["generic"]
        by_sex = {"男": [], "女": []}
        for v in g["variants"]:
            X = load(st + v)
            if X is None:
                continue
            key = v[:-1] if v[-1:] in "男女" and v[:-1] in people else v
            sex = None
            if v[-1:] in "男女" and not v[:-1].isdigit() and key not in people:
                sex = v[-1]
            elif key in people and people[key]["female"] is not None:
                sex = "女" if people[key]["female"] else "男"
            if v[:-1].isdigit():  # avatar hair styles: 10女, 3男
                sex = v[-1]
            cands = [s for s in ("男", "女") if s in gens and load(gens[s]) is not None and load(gens[s]).shape == X.shape]
            if sex is None or sex not in cands:
                if not cands:
                    continue
                sex = min(cands, key=lambda s: int((X != load(gens[s])).any(2).sum()))
            by_sex[sex].append(v)
        for sex, vs in by_sex.items():
            if sex not in gens or len(vs) < MIN_VARIANTS:
                continue
            G = load(gens[sex])
            vis = int((G[..., 3] > 0).sum()) or 1
            stack = [G] + [load(st + v) for v in vs]
            S = np.stack(stack)  # k,h,w,4
            # the body all versions share: per-pixel majority (mode) over the generic + versions
            keys = (S[..., 0].astype(np.uint32) << 24) | (S[..., 1].astype(np.uint32) << 16) | (S[..., 2].astype(np.uint32) << 8) | S[..., 3]
            k, hh, ww = keys.shape
            flatk = keys.reshape(k, -1)
            srt = np.sort(flatk, axis=0)
            # mode per column: longest run in the sorted column
            best_val = srt[0].copy(); best_cnt = np.ones(hh * ww, int); run = np.ones(hh * ww, int)
            for r in range(1, k):
                same = srt[r] == srt[r - 1]
                run = np.where(same, run + 1, 1)
                better = run > best_cnt
                best_cnt = np.where(better, run, best_cnt); best_val = np.where(better, srt[r], best_val)
            mode = best_val.reshape(hh, ww); support = best_cnt.reshape(hh, ww)
            diffs = [keys[i] != mode for i in range(1, k)]
            counts = {v: int(d.sum()) for v, d in zip(vs, diffs)}
            med = float(np.median(list(counts.values())))
            if med > vis * 0.45:
                print(st, sex, "skipped: versions differ in", round(med / vis * 100), "% of the body", file=sys.stderr)
                continue
            keep = [i for i, v in enumerate(vs) if counts[v] <= med * 2.0]
            vs = [vs[i] for i in keep]
            diffs = [diffs[i] for i in keep]
            if len(vs) < MIN_VARIANTS:
                continue
            diff = np.stack(diffs).sum(0)
            n = len(vs)
            union = diff >= 1
            core = diff >= max(1, int(np.ceil(n * CORE)))
            # the generic's own head: where it differs from the shared body
            gen_head = keys[0] != mode
            union |= gen_head
            core |= gen_head & (diff >= 1)
            # heads stay near the head: drop differences far from the core (armor / weapon recolors)
            near = core.copy()
            for _ in range(NEAR):
                g = near.copy()
                g[1:] |= near[:-1]; g[:-1] |= near[1:]; g[:, 1:] |= near[:, :-1]; g[:, :-1] |= near[:, 1:]
                near = g
            union &= near
            d = union.copy()
            d[1:] |= union[:-1]; d[:-1] |= union[1:]; d[:, 1:] |= union[:, :-1]; d[:, :-1] |= union[:, 1:]
            union = d
            idx = np.flatnonzero(union.ravel())
            mv = mode.ravel()[idx]; ms = support.ravel()[idx]
            fill = np.zeros((len(idx), 4), np.uint8)
            ok = ms >= k * 0.5
            fill[ok, 0] = (mv[ok] >> 24) & 255; fill[ok, 1] = (mv[ok] >> 16) & 255
            fill[ok, 2] = (mv[ok] >> 8) & 255; fill[ok, 3] = mv[ok] & 255
            core_bits = core.ravel()[idx]
            a = anims.get(gens[sex])
            cw, ch = (a[0], a[1]) if a else (32, 32)
            H, W = G.shape[:2]
            anchors = {}
            for r in range(H // ch):
                for c in range(W // cw):
                    m = core[r * ch:(r + 1) * ch, c * cw:(c + 1) * cw]
                    ys, xs = np.nonzero(m)
                    if len(ys):
                        anchors[f"{c},{r}"] = [round(float((xs.min() + xs.max()) / 2 + c * cw), 1), int(ys.min() + r * ch)]
            out["classes"][f"{st}|{sex}"] = {
                "stem": st,
                "sex": sex,
                "generic": gens[sex],
                "variants": vs,
                "cell": [cw, ch],
                "size": [W, H],
                "union": base64.b64encode(zlib.compress(np.asarray(idx, "<u4").tobytes(), 9)).decode(),
                "fill": base64.b64encode(zlib.compress(fill.tobytes(), 9)).decode(),
                "core": base64.b64encode(zlib.compress(np.packbits(core_bits).tobytes(), 9)).decode(),
                "anchors": anchors,
            }
            for v in vs:
                out["heads"].setdefault(v, []).append({"class": f"{st}|{sex}", "sprite": st + v})
        print(st, {s: len(v) for s, v in by_sex.items()}, file=sys.stderr)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))


if __name__ == "__main__":
    main(*sys.argv[1:6])
