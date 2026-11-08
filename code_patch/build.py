"""Build the Paragon Unlimited game code patch from source.

    python code_patch/build.py [--code-bin path/to/code.bin] [--out patch.ips]

Needs clang, ld.lld, llvm-objdump and llvm-objcopy (LLVM). Writes the patch to
code_patch/out/PU_CodePatch.ips and says whether it is identical to the one Paragon Unlimited
ships (Data/FE13/PU_CodePatch.ips).

With --code-bin (the decompressed code.bin of Fire Emblem Awakening, North American version 1.0)
it also checks that every instruction the patch replaces is the one it expects, and that the
free space it uses is empty. code.bin is not included here: it is Nintendo's.

The patch has five parts (see README.md for every place it changes):
  support_slots/  60 support partners per character
  skill_effects/  skill effect rules
  class_slots/    5 reclass classes per gender, the avatar class list from data, 64-class limit
  SUPPORT_LOG     one instruction: room for 4096 support conversations instead of 1920
  mission_banner/ the turn-1 banner of Map Maker Seize / Survive chapters
"""
import argparse
import os
import re
import struct
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
BASE = 0x100000  # code.bin is loaded at this address; IPS offsets are file offsets

# Support Log "seen" array: created with 1920 bits (movne r1, #0x780); 4096 bits instead.
SUPPORT_LOG = (0x108B30, 0x13A01D1E, 0x13A01A01)  # address, original word, new word


def assemble(name, patch_s, link_ld, work):
    """Assemble + link one part; returns {address: bytes} for its sections."""
    folder = os.path.join(work, name)
    os.makedirs(folder, exist_ok=True)
    src, ld, obj, elf = (os.path.join(folder, n) for n in ("patch.S", "link.ld", "patch.o", "patch.elf"))
    with open(src, "w") as f:
        f.write(patch_s)
    with open(ld, "w") as f:
        f.write(link_ld)
    subprocess.check_call(["clang", "--target=armv6k-none-eabi", "-march=armv6k", "-c", src, "-o", obj])
    subprocess.check_call(["ld.lld", "-e", "0", "-T", ld, obj, "-o", elf])
    sections = {}
    table = subprocess.check_output(["llvm-objdump", "-h", elf]).decode()
    for line in table.splitlines():
        m = re.match(r"\s*\d+\s+(\.\S+)\s+([0-9a-f]+)\s+([0-9a-f]+)", line)
        if m and (m.group(1).startswith(".s_") or m.group(1).startswith(".cave")) and int(m.group(2), 16):
            out = os.path.join(folder, "section.bin")
            subprocess.check_call(["llvm-objcopy", "-O", "binary", "--only-section=" + m.group(1), elf, out])
            with open(out, "rb") as f:
                sections[int(m.group(3), 16)] = f.read()
    return sections


def support_slots(work):
    sys.path.insert(0, os.path.join(HERE, "support_slots"))
    import gen as support_gen  # noqa: E402
    import sites  # noqa: E402

    sys.path.pop(0)
    parts = assemble("support_slots", support_gen.PATCH_S, support_gen.LINK_LD, work)
    expected = {}
    for addr, _kind, _d, _a, _b, word in sites.SITES:
        expected[addr] = word
    for addr, word in sites.BOUNDS:  # 'cmp rX, #52' -> '#60'
        parts[addr] = struct.pack("<I", (word & ~0xFF) | sites.N_NEW)
        expected[addr] = word
    for addr, word, new in sites.WORDS:
        parts[addr] = struct.pack("<I", new)
        expected[addr] = word
    free = [(sites.CAVE, sites.CAVE_END)]
    del sys.modules["gen"]
    return parts, expected, free


def skill_effects(work):
    sys.path.insert(0, os.path.join(HERE, "skill_effects"))
    import gen as skill_gen  # noqa: E402

    sys.path.pop(0)
    parts = assemble("skill_effects", skill_gen.PATCH_S, skill_gen.LINK_LD, work)
    expected = {0x218B30: 0xE92D4070, 0x2F1C30: 0xEB03F38D}  # function start; call to FUN_003EEA6C
    free = [(0x459ED4, 0x45A000)]
    del sys.modules["gen"]
    return parts, expected, free


def class_slots(work):
    sys.path.insert(0, os.path.join(HERE, "class_slots"))
    import gen as class_gen  # noqa: E402

    sys.path.pop(0)
    parts = assemble("class_slots", class_gen.PATCH_S, class_gen.LINK_LD, work)
    expected = dict(class_gen.EXPECTED)
    del sys.modules["gen"]
    return parts, expected, []  # it reuses the space of the game code it replaces


def mission_banner(work):
    sys.path.insert(0, os.path.join(HERE, "mission_banner"))
    import gen as mission_gen  # noqa: E402

    sys.path.pop(0)
    parts = assemble("mission_banner", mission_gen.PATCH_S, mission_gen.LINK_LD, work)
    expected = dict(mission_gen.EXPECTED)
    del sys.modules["gen"]
    return parts, expected, []  # old code that the other parts no longer reach


def overlaps(groups):
    """Places two parts both write (they must not)."""
    spans = sorted((a, a + len(d), i) for i, g in enumerate(groups) for a, d in g.items())
    return [f"{a:#x}-{e:#x} overlaps {b:#x}" for (a, e, _i), (b, _f, _j) in zip(spans, spans[1:]) if b < e]


def to_ips(groups):
    out = bytearray(b"PATCH")
    for parts in groups:
        for addr, data in sorted(parts.items()):
            off = addr - BASE
            for k in range(0, len(data), 0xFFFF):
                chunk = data[k:k + 0xFFFF]
                out += (off + k).to_bytes(3, "big") + len(chunk).to_bytes(2, "big") + chunk
    return bytes(out + b"EOF")


def check_code_bin(path, groups, expected, free):
    code = open(path, "rb").read()
    problems = []
    for addr, word in expected.items():
        got = struct.unpack_from("<I", code, addr - BASE)[0]
        if got != word:
            problems.append(f"{addr:#x}: expected {word:#010x}, the game has {got:#010x}")
    for start, end in free:
        used = [a for parts in groups for a in parts if start <= a < end]
        for a in used:
            size = max(len(p[a]) for p in groups if a in p)
            if any(code[a - BASE:a - BASE + size]):
                problems.append(f"{a:#x}: the free space is not empty")
    return problems


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--code-bin", help="code.bin of the game, to check the original instructions")
    ap.add_argument("--out", default=os.path.join(HERE, "out", "PU_CodePatch.ips"))
    args = ap.parse_args()
    work = tempfile.mkdtemp(prefix="pu_code_patch_")
    s_parts, s_expected, s_free = support_slots(work)
    k_parts, k_expected, k_free = skill_effects(work)
    c_parts, c_expected, c_free = class_slots(work)
    m_parts, m_expected, m_free = mission_banner(work)
    addr, old, new = SUPPORT_LOG
    log = {addr: struct.pack("<I", new)}
    groups = [s_parts, k_parts, log, c_parts, m_parts]
    clash = overlaps(groups)
    if clash:
        print("Parts write the same bytes:\n" + "\n".join(clash))
        return 1
    ips = to_ips(groups)
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "wb") as f:
        f.write(ips)
    print(f"Wrote {args.out} ({len(ips)} bytes, {sum(len(g) for g in groups)} changes)")
    shipped = os.path.join(ROOT, "Data", "FE13", "PU_CodePatch.ips")
    if os.path.isfile(shipped):
        same = open(shipped, "rb").read() == ips
        print("Identical to Data/FE13/PU_CodePatch.ips" if same else "DIFFERENT from Data/FE13/PU_CodePatch.ips")
    if args.code_bin:
        expected = {**s_expected, **k_expected, **c_expected, **m_expected, addr: old}
        problems = check_code_bin(args.code_bin, groups, expected, s_free + k_free + c_free + m_free)
        print("\n".join(problems) if problems else f"code.bin check: all {len(expected)} replaced instructions "
              "are the expected ones and the free space is empty")
        return 1 if problems else 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
