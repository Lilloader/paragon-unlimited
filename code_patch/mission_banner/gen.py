"""Mission banner: writes the assembly (PATCH_S) and the linker script (LINK_LD).

At the start of turn 1 the game shows the mission banner (FUN_003BC758): Tlp_Mission01 ("Defeat
commander") when the chapter's win rule has 0x40000, otherwise Tlp_Mission02 ("Rout the enemy").
The 'otherwise' path (0x3BC7A4, 'adr r0, Tlp_Mission02') now jumps to pu_mission:

* win rule exactly 0x10000 (only Map Maker chapters set it: Seize / Survive, which have no win
  rule of the game's own until their goal is met): the banner is telop/Tlp_PUM_<chapter>.r.lz,
  the chapter's own picture (the game adds _E for English as for its own banners);
* anything else: Tlp_Mission02, as before.

The path is built on the stack; the game copies it (the banner keeps its own copy of the name).
The code lives in the old male avatar class code that class_slots/ replaced (0x2D0360-0x2D03E0,
not reached any more), the two strings in the unused end of the old Hit Rate +10 function
(0x218D48-0x218D64, see skill_effects/).
"""
F_CHNAME = 0x3B3690  # ev::ChapterGetName: the current chapter's id ("U004")
F_LOCAL = 0x30E420   # path -> the language's file (adds _E) when it exists
F_TELOP = 0x27689C   # play a telop: (parent, path, 1) -> telop process (0 = failed)
SITE = 0x3BC7A4      # adr r0, "telop/Tlp_Mission02.r.lz"
ORIG_PATH = 0x3BC800
BACK_ORIG = 0x3BC7A8  # bl FUN_0030e420 with r0 = path
BACK_DONE = 0x3BC7BC  # cmp r0, #0 after the telop call

CAVE, CAVE_END = 0x2D0360, 0x2D03E0
STR, STR_END = 0x218D48, 0x218D64

EXPECTED = {SITE: 0xE28F0054}  # adr r0, 0x3bc800

PATCH_S = r'''
    .syntax unified
    .arm
    .section .s_site,"ax"
    b pu_mission

    .section .cave,"ax"
@ r0 = the chapter's win rule, r4 = the parent process; {r4, lr} are on the stack
pu_mission:
    and r1, r0, #0x70000
    cmp r1, #0x10000
    ldrne r0, =orig_path
    bne back_orig
    sub sp, sp, #48
    bl f_chname
    mov r2, r0
    mov r0, sp
    ldr r1, =names
    bl copy
    mov r1, r2
    bl copy
    ldr r1, =names + 15
    bl copy
    mov r0, sp
    bl f_local
    mov r1, r0
    mov r2, #1
    mov r0, r4
    bl f_telop
    add sp, sp, #48
    b back_done
@ copy the string at r1 to r0 (with its 0); r0 = where that 0 is
copy:
    ldrb r3, [r1], #1
    strb r3, [r0], #1
    cmp r3, #0
    bne copy
    sub r0, r0, #1
    bx lr
    .ltorg

    .section .str,"a"
names:
    .asciz "telop/Tlp_PUM_"
    .asciz ".r.lz"
'''

LINK_LD = f'''f_chname = {F_CHNAME:#x};
f_local = {F_LOCAL:#x};
f_telop = {F_TELOP:#x};
orig_path = {ORIG_PATH:#x};
back_orig = {BACK_ORIG:#x};
back_done = {BACK_DONE:#x};
SECTIONS {{
  .s_str {STR:#x} : {{ *(.str) }}
  .cave {CAVE:#x} : {{ *(.cave) }}
  .s_site {SITE:#x} : {{ *(.s_site) }}
}}
ASSERT(SIZEOF(.cave) <= {CAVE_END - CAVE:#x}, "cave too big")
ASSERT(SIZEOF(.s_str) <= {STR_END - STR:#x}, "strings too big")
'''
