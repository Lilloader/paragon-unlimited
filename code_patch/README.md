# Game code patch (source)

`Data/FE13/PU_CodePatch.ips` is built from the files in this folder. It is for **Fire Emblem
Awakening, North American version 1.0** (title 00040000000A0500) and is optional: Paragon
Unlimited works without it, and the features below are then ignored by the game.

| Part | Folder | What it does |
|---|---|---|
| 60 support partners | `support_slots/` | Characters can have 8 more support partners (#052-#059), read from the `PU_SupportEx2` table Paragon writes into `data/person/static.bin`. |
| Skill effects | `skill_effects/` | Skills get effects from the `PU_SkillFx` table Paragon writes into `data/GameData.bin` (damage, hit, avoid, crit, dodge, attack speed, with conditions). |
| Support Log size | `build.py` (`SUPPORT_LOG`) | Room for 4096 support conversations instead of 1920. |
| Mission banner | `mission_banner/` | Map Maker Seize / Survive chapters (win rule exactly 0x10000) show their own turn-1 banner, `telop/Tlp_PUM_<chapter>.r.lz`, instead of "Rout the enemy". |
| Class slots | `class_slots/` | 5 reclass classes per gender (slots 4-5 from the `PU_ClassEx` table in `data/person/static.bin`), the avatar class list from the `PU_AvatarCls` table in `data/GameData.bin`, and a 64-class limit for Second Seal lists. |

## Building

```
python code_patch/build.py --code-bin path/to/code.bin
```

Needs LLVM (`clang`, `ld.lld`, `llvm-objdump`, `llvm-objcopy`). It writes `code_patch/out/PU_CodePatch.ips`
and says whether it is identical to the shipped one. With `--code-bin` (the game's decompressed
code.bin, which is not included) it also checks that every instruction the patch redirects is the
one it expects and that the free space it uses is empty.

Addresses below are where the code runs (code.bin is loaded at 0x100000; the IPS file stores
address - 0x100000).

## 60 support partners (`support_slots/`)

A character record holds 52 support slots (8 bytes each at +0x88) and a unit holds 52 support
point bytes (at +0xC4). The game reads them in 32 places. Each of those instructions is replaced
by one `bl` to a small stub in free space at the end of the game's code (`0x459B90`-`0x45A000`).
The stub does what the original instruction did for slots 0-51 and, for slots 52-59, looks the
character up in `PU_SupportEx2` (through the game's own label lookup, `0x2BE6B0`). Support
points for the extra slots live in a separate buffer per unit (pointer at unit +0xF8), allocated
on first use.

`sites.py` lists every place with the original instruction it expects:

| Address | Kind |
|---|---|
| `0x18ff88` | slot address (add rD, rP, rI, lsl #3) |
| `0x209a48` | slot read (ldr rD, [rP, rOff]) |
| `0x209ad8` | slot read (ldr rD, [rP, rOff]) |
| `0x20a4e4` | support points, read |
| `0x20a53c` | support points, write |
| `0x20a578` | support points, write |
| `0x20ab10` | slot read (ldr rD, [rP, rOff]) |
| `0x20ab3c` | slot address (add rD, rP, rI, lsl #3) |
| `0x20af80` | slot read (ldr rD, [rP, rOff]) |
| `0x20afac` | slot address (add rD, rP, rI, lsl #3) |
| `0x20b558` | support points, read |
| `0x20b9d8` | slot read (ldr rD, [rP, rOff]) |
| `0x20bd6c` | support points, read |
| `0x20be5c` | support points, read |
| `0x20c040` | support points, read |
| `0x20c144` | support points, read |
| `0x20c1d4` | support points, read |
| `0x278380` | support points, read |
| `0x27bc3c` | support points, write |
| `0x27bc6c` | support points, write |
| `0x27d8b8` | slot address (add rD, rP, rI, lsl #3) |
| `0x27d96c` | support points, write |
| `0x27dccc` | support points, read |
| `0x2afc78` | slot address (add rD, rP, rI, lsl #3) |
| `0x2aff48` | slot address (add rD, rP, rI, lsl #3) |
| `0x2aff6c` | slot address (add rD, rP, rI, lsl #3) |
| `0x2de2dc` | support points, read |
| `0x3b2730` | slot address (add rD, rP, rI, lsl #3) |
| `0x3b2834` | support points, read |
| `0x3b2854` | slot address (add rD, rP, rI, lsl #3) |
| `0x3b28a4` | support points, read |
| `0x414b40` | support points, read |

Other changes:

- **Loop limits** `cmp rX, #52` -> `#60` at `0x1900f0`, `0x209a58`, `0x209ae8`, `0x20ab98`,
  `0x20b008`, `0x20b9e8`, `0x27d978`, `0x2afcc0`, `0x2aff80`, `0x3b27e8`, `0x3b2904`.
- **List sizes**: `0x18ff70` (52*4 -> 60*4), `0x20aad8` and `0x20af48` (units+53 -> units+61).
- **Save files**: the unit support buffer is saved, loaded and copied with 8 more bytes
  (`0x3a2b30` loader, `0x3a4f20` writer, `0x2b7870` copy). Old saves load (the extra bytes are 0);
  saves made with the patch load without it (the extra bytes are skipped).
- `0x27d20c`: allocation of the bond buffer with count + 8.
- `0x2ef8f8` (who is a unit's S-rank partner) and `0x3d5340` (end of GameData loading, stores
  count + 8) jump into the new code.

## Skill effects (`skill_effects/`)

- `0x2F1C30`: the call that turns the battle numbers into hit %, crit %, damage and follow-ups
  (`FUN_003EEA6C`) now goes through `pu_battle` first, which applies the `PU_SkillFx` rules to both
  units. Rule format: skill id (u16), effect (u8), two conditions (u8), value (s8), reserved (u16).
- `0x218B30`: the game's built-in function for Hit Rate +10, Sure Strike, Avoid +10 and Gamble
  returns at once; Paragon writes effect lines for those four skills instead, so they work the
  same. The rest of that function's space (`0x218B34`-`0x218D64`) holds part of the new code; the
  other part is at `0x459ED4`-`0x45A000`.

## Support Log size

`0x108B30`: `movne r1, #0x780` (1920 bits) -> `movne r1, #0x1000` (4096 bits). This is the
"seen" array of the Support Log; numbers 1920 and up wrote past it. The game saves the array with
its size and loads a different size by copying what fits, so saves stay compatible both ways.

## Class slots (`class_slots/`)

The game builds a unit's Second Seal list in `FUN_002CFF38` (list object: unit at +0, 64 class
pointers at +4, count at +0x104).

- **Reclass slots 4-5.** A character record has 3 male and 3 female reclass JIDs (+0x6C, female
  at +0x78). The list builder (`0x2D0454`) and the "is it an avatar" test `FUN_00214098`
  (`0x21412C`) read them in a 3-step loop; each read is now a `bl` to `rc_a` / `rc_b`, which
  return slots 1-3 from the record and slots 4-5 from `PU_ClassEx` (u32 count, then 20-byte
  entries: u16 owner = static position, u16 0, JIDs male 4, male 5, female 4, female 5). The
  loop limits `cmp r4, #3` at `0x2D04D4` and `0x214154` become `#5`. Children get their parents'
  slots 4-5 too (same loop).
- **Avatar classes.** A unit with Tactician among its (or a parent's) reclass classes gets 13
  fixed classes for its gender. The code that added them (`0x2CFF98`-`0x2D00A4` female,
  `0x2D02AC`-`0x2D03E0` male) is replaced: the classes now come from `PU_AvatarCls` (u32 count,
  then 8-byte entries: JID, u8 gender 0 male / 1 female, 3 bytes 0). With no table or 0 entries
  the game's own 13 classes are used (their JID strings stay in place). Manakete / Taguel for
  units with those skills are added as before. The new code lives in the space of the code it
  replaces.
- **64-class limit.** `FUN_002BBDE4` (add a class to the list) never checked the count. `0x2BBE90`
  now jumps to `cap`, which does nothing once the list holds 64 classes.

`class_slots/test_emu.py` runs `FUN_002CFF38` from the original and the patched code.bin in the
Unicorn emulator (the game functions it calls are replaced by small Python stand-ins) and checks
the lists: same as the game without the tables, 5 reclass classes, the avatar list from the
table, parents' slots 4-5 for children, and the 64 limit.

## Mission banner (`mission_banner/`)

At the start of turn 1 `FUN_003BC758` plays `Tlp_Mission01` (win rule has 0x40000, "Defeat
commander") or `Tlp_Mission02` ("Rout the enemy"). The second path (`0x3BC7A4`,
`adr r0, "telop/Tlp_Mission02.r.lz"`) now branches to `pu_mission`: when the rule is exactly
0x10000 it builds `telop/Tlp_PUM_<chapter id>.r.lz` on the stack (chapter id from
`ev::ChapterGetName`, `0x3B3690`), asks `FUN_0030E420` for the English file (`..._E.r.lz`) and
plays it with `FUN_0027689C` (which keeps its own copy of the name), then rejoins the game's code
at `0x3BC7BC`. Any other rule goes back to `0x3BC7A8` with the game's own path. The game never
checks 0x10000 to decide a win (`FUN_00397D80` looks at 0x20000 and 0x40000 only).

The code sits in the old male avatar class code (`0x2D0360`-`0x2D03E0`) and its two strings in
the old Hit Rate +10 function (`0x218D48`-`0x218D64`); the class slot and skill effect parts
replaced both and nothing branches into these ranges any more. `build.py` stops if two parts write
the same bytes.

## Installing

In Paragon Unlimited: **Unlimited -> Install Game Code Patch (FE13)**. It merges with a code.ips
from another mod (the other mod's changes are kept unless they touch the same bytes), keeps a
backup, and can remove the patch again (`paragon/unlimited/tools/code_patch.py`).
