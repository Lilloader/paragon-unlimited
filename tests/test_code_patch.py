"""The bundled game code patch (Data/FE13/PU_CodePatch.ips)."""
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.chdir(os.path.join(os.path.dirname(__file__), ".."))

from paragon.unlimited.saving import save_checks as wp
from paragon.unlimited.tools import code_patch as cp

# The patch's places (code.bin file offsets = address - 0x100000), from the patch sources.
SUPPORT_CAVE = 0x459B90 - 0x100000  # 60 support slots: new code in free space
SKILL_HOOK = 0x2F1C30 - 0x100000  # skill effects: hook in the battle calculation
SKILL_CAVE = 0x459ED4 - 0x100000  # skill effects: new code in free space
SUPPORT_BITS = 0x108B30 - 0x100000  # 4096 support conversations
CLASS_CAVE = 0x2CFF98 - 0x100000  # class slots: avatar list (in the game's old code)
CLASS_CAP = 0x2BBE90 - 0x100000  # class slots: 64-class limit
MISSION_SITE = 0x3BC7A4 - 0x100000  # mission banner: Seize / Survive chapters


def check(cond, what):
    if not cond:
        raise AssertionError(what)


def write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)


def test_bundled():
    recs = cp.bundled_records()
    offs = {o for o, _ in recs}
    check(len(recs) == 68, len(recs))
    check({SUPPORT_CAVE, SKILL_HOOK, SKILL_CAVE, SUPPORT_BITS, CLASS_CAVE, CLASS_CAP, MISSION_SITE} <= offs,
          "all five features are in it")
    check(dict(recs)[MISSION_SITE] == bytes.fromhex("ed4efcea"), "b pu_mission")
    check(dict(recs)[SUPPORT_BITS] == bytes.fromhex("011aa013"), "movne r1, #0x1000")
    check(wp.ips_has_support_number_patch(cp.bundled_bytes()), "Paragon sees 4096 support numbers")
    check(cp.build_ips(cp.parse_ips(cp.bundled_bytes())) == cp.bundled_bytes(), "IPS round trip")
    for i, a in enumerate(recs):  # no two records touch the same bytes
        for b in recs[i + 1:]:
            check(not cp._overlaps(a, b), (hex(a[0]), hex(b[0])))
    check(cp.status(cp.bundled_bytes()) == cp.CURRENT and cp.status(None) == cp.NONE, "status")
    print("bundled patch: ok", len(cp.bundled_bytes()), "bytes")


def test_merge_and_install(tmp):
    other = [(0x1B2CF4, b"\x3c"), (0x036804, b"\x30\x00\x9f\xe5"), (0x1B5B88, b"\x00" * 20)]
    other_ips = cp.build_ips(other)
    check(cp.status(other_ips) == cp.OTHER, "another mod's patch")
    merged, kept = cp.merge(other_ips)
    check(kept == 3 and cp.parse_ips(merged)[:3] == other, "other changes kept, first")
    check(cp.status(merged) == cp.CURRENT, "merged = current")
    check(cp.unmerge(merged) == (other_ips, 3), "remove gives the other patch back")
    # an older Unlimited patch (without the 4096 change, an old support cave) is replaced
    old = [r for r in cp.bundled_records() if r[0] != SUPPORT_BITS]
    old[0] = (old[0][0], b"\xff" * len(old[0][1]))
    old_ips = cp.build_ips(other + old)
    check(cp.status(old_ips) == cp.OLD, "older Unlimited patch")
    check(cp.merge(old_ips)[0] == merged, "update = same as a fresh install")
    # RLE records are read too
    check(cp.parse_ips(b"PATCH\x00\x00\x10\x00\x00\x00\x04\xaaEOF") == [(0x10, b"\xaa" * 4)], "RLE")

    mods = os.path.join(tmp, "mods")
    title = os.path.join(mods, "00040000000A0500")
    os.makedirs(os.path.join(title, "romfs"))
    check(cp.target_path(mods) == os.path.join(title, "code.ips"), "default place")
    check(cp.describe(mods)[1:] == (True, False), "fresh: install only")
    r = cp.install(mods)
    check(r["backup"] is None and r["status_before"] == cp.NONE, r)
    check(cp.installed_status(os.path.join(title, "romfs"))[0] == cp.CURRENT, "any mod folder spelling")
    check(cp.describe(mods)[1:] == (False, True), "current: remove only")
    r = cp.uninstall(mods)
    check(r["kept"] == 0 and not os.path.exists(os.path.join(title, "code.ips")) and os.path.isfile(r["backup"]),
          "removed, backup kept")
    # with another mod's patch in exefs/: merged there, other changes kept
    exefs = os.path.join(title, "exefs", "code.ips")
    write(exefs, old_ips)
    check(cp.target_path(mods) == exefs, "uses the existing exefs/code.ips")
    r = cp.install(mods)
    with open(exefs, "rb") as f:
        check(f.read() == merged, "updated in place")
    with open(r["backup"], "rb") as f:
        check(f.read() == old_ips, "backup = the file before")
    check(r["kept"] == 3, r)
    data, src = cp.patch_for_sharing(mods)
    check(data == merged and "installed" in src, src)
    r = cp.uninstall(mods)
    with open(exefs, "rb") as f:
        check(f.read() == other_ips and r["kept"] == 3, "other mod's patch stays")
    data, src = cp.patch_for_sharing(mods)
    check(data == merged, "sharing merges the Unlimited patch in")
    check(cp.patch_for_sharing(None)[0] == cp.bundled_bytes(), "no mod folder: the bundled patch")
    print("merge / install / remove: ok")


def main():
    test_bundled()
    tmp = tempfile.mkdtemp()
    try:
        test_merge_and_install(tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("code patch test: all checks passed")


if __name__ == "__main__":
    main()
