"""Run the Second Seal list builder from the original and the patched game code in Unicorn.

    python code_patch/class_slots/test_emu.py path/to/code.bin

code.bin (the game's decompressed code, North American 1.0) is not included. Needs the
unicorn Python package. The patch is taken from Data/FE13/PU_CodePatch.ips.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", ".."))
from emu import Game  # noqa: E402
from paragon.unlimited.tools import code_patch as cp  # noqa: E402

orig = open(sys.argv[1], "rb").read()
_p = bytearray(orig)
with open(os.path.join(HERE, "..", "..", "Data", "FE13", "PU_CodePatch.ips"), "rb") as f:
    for off, b in cp.parse_ips(f.read()):
        _p[off:off + len(b)] = b
patched = bytes(_p)

def run(code, setup):
    g = Game(code); u = setup(g); return g.seal_list(u)

def avatar_m(g):
    p = g.person(0, male=('JID_戦術師男', 'JID_トルバドール男', 'JID_ペガサスナイト男'), female=('JID_戦術師女', 'JID_戦士女', 'JID_蛮族女'))
    return g.unit(p)
def avatar_f(g):
    p = g.person(1, male=('JID_戦術師男', 'JID_トルバドール男', 'JID_ペガサスナイト男'), female=('JID_戦術師女', 'JID_戦士女', 'JID_蛮族女'))
    return g.unit(p, female=True)
def chrom(g):
    p = g.person(3, male=('JID_ロード男', 'JID_ソシアルナイト男', 'JID_アーチャー男'), female=('JID_ロード女', 'JID_ソシアルナイト女', 'JID_アーチャー女'))
    return g.unit(p)

ok = True
def check(c, what):
    global ok
    print(('ok   ' if c else 'FAIL ') + what)
    ok &= bool(c)

for name, s in (('male avatar', avatar_m), ('female avatar', avatar_f), ('Chrom', chrom)):
    a = run(orig, s); b = run(patched, s)
    check(a == b, f'{name}: same list as the original game without tables ({b[1]} classes)')
    print('     ', ' '.join(b[0]))

# reclass slots 4-5
def chrom_ex(g):
    u = chrom(g); g.class_ex([(9, 'JID_x', None, None, None), (3, 'JID_剣士男', 'JID_魔道士男', 'JID_剣士女', 'JID_魔道士女')]); return u
l, n = run(patched, chrom_ex)
check(l == ['JID_ロード男', 'JID_ソシアルナイト男', 'JID_アーチャー男', 'JID_剣士男', 'JID_魔道士男'], 'Chrom male: 5 reclass classes ' + ' '.join(l))
def chrom_f(g):
    p = g.person(3, male=('JID_ロード男', None, None), female=('JID_ロード女', 'JID_ソシアルナイト女', None))
    g.class_ex([(3, 'JID_剣士男', None, None, 'JID_魔道士女')]); return g.unit(p, female=True)
l, n = run(patched, chrom_f)
check(l == ['JID_ロード女', 'JID_ソシアルナイト女', 'JID_魔道士女'], 'female, empty slot 3 and 4, slot 5 set: ' + ' '.join(l))
# Tactician only in slot 4 makes an avatar
def tac4(g):
    p = g.person(5, male=('JID_剣士男', None, None))
    g.class_ex([(5, 'JID_戦術師男', None, None, None)]); return g.unit(p)
l, n = run(patched, tac4)
check(n == 13 and 'JID_ダークマージ男' in l, f'Tactician in slot 4 counts as an avatar ({n})')
# avatar table
def av_table(g):
    u = avatar_m(g)
    g.avatar([('JID_戦術師男', 0), ('JID_ペガサスナイト男', 0), ('JID_戦術師女', 1), ('JID_マムクート男', 0)]); return u
l, n = run(patched, av_table)
check(l == ['JID_戦術師男', 'JID_ペガサスナイト男', 'JID_マムクート男', 'JID_トルバドール男'], 'male avatar uses the table: ' + ' '.join(l))
def av_table_f(g):
    u = avatar_f(g)
    g.avatar([('JID_戦術師男', 0), ('JID_戦術師女', 1), ('JID_村人女', 1)]); return u
l, n = run(patched, av_table_f)
check(l == ['JID_戦術師女', 'JID_村人女', 'JID_戦士女', 'JID_蛮族女'], 'female avatar uses the table: ' + ' '.join(l))
def av_empty(g):
    u = avatar_m(g); g.avatar([]); return u
check(run(patched, av_empty) == run(orig, avatar_m), 'empty table = the game\'s own list')
# 64 limit
def av_big(g):
    u = avatar_m(g); g.avatar([(f'JID_X{i}', 0) for i in range(80)]); return u
l, n = run(patched, av_big)
check(n == 64 and l[-1] == 'JID_X63', f'list stops at 64 classes (count {n})')
def child(g):
    parent = g.person(7, male=('JID_アーチャー男', None, None))
    g.class_ex([(7, 'JID_剣士男', 'JID_ロード男', None, None)])
    kid = g.person(8, male=('JID_盗賊男', None, None))
    u = g.unit(kid)
    fam = g.alloc(0x40); g.w32(fam, parent); g.w32(u + 0x78, fam)
    return u
l, n = run(patched, child)
check(l == ['JID_盗賊男', 'JID_アーチャー男', 'JID_剣士男'], "a child gets a parent's slot 4 (Lord stays excluded): " + ' '.join(l))
print('ALL OK' if ok else 'SOME FAILED')
sys.exit(0 if ok else 1)
