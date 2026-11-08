"""Class slots: writes the assembly (PATCH_S) and the linker script (LINK_LD).

The game builds a unit's Second Seal list in FUN_002CFF38 (list: unit at +0, up to 64 classes at
+4, count at +0x104). This part of the patch changes three things there:

1. Reclass slots 4 and 5. A character record holds 3 male and 3 female reclass classes
   (JID string pointers at +0x6C, female at +0x78). The two loops that read them (the list
   builder at 0x2D0454 and the "is this an avatar" test FUN_00214098 at 0x21412C) now run to 5
   and read slots 4-5 from the PU_ClassEx table Paragon writes into data/person/static.bin:
       u32 count, count x 20-byte entries:
       u16 owner (static position of the character), u16 reserved,
       JID pointers: male slot 4, male slot 5, female slot 4, female slot 5 (0 = none).
2. The avatar class list. Units whose reclass classes (or a parent's) include Tactician get a
   fixed list of 13 classes for their gender. The list now comes from the PU_AvatarCls table
   in data/GameData.bin when it has entries:
       u32 count, count x 8 bytes: JID pointer, u8 gender (0 male, 1 female), 3 bytes 0.
   Without the table (or with 0 entries) the game's own 13 classes are used, as before.
   The game's code for the 13 fixed classes is replaced by the new code (same space).
3. The list holds 64 classes and the game never checked: adding a 65th class now does
   nothing (0x2BBE90) instead of writing past the end.
Run build.py (one folder up) to make the patch.
"""
F_LABEL = 0x2BE6B0  # label lookup (string -> record), 0 if missing
F_JOB = 0x2DE558    # JID string -> class record
F_ADD = 0x2BBDE4    # add a class to a Second Seal list (skips 0 and duplicates)
F_POS = 0x2DA13C    # person pointer -> static position

CAVE_A, CAVE_A_END = 0x2CFF98, 0x2D00A4  # the avatar check + 13 female classes (old code)
CAVE_B, CAVE_B_END = 0x2D02AC, 0x2D03E0  # 13 male classes (old code)
RET_FEMALE, RET_MALE = 0x2D00A4, 0x2D03E0  # where the old code went on (Manakete / Taguel)

# The game's own avatar classes (their JID strings stay where they are in the code).
FEMALE = [0x2D017C, 0x2D018C, 0x2D01A4, 0x2D01BC, 0x2D01C8, 0x2D01DC, 0x2D01E8, 0x2D01F4,
          0x2D020C, 0x2D0224, 0x2D0238, 0x2D0248, 0x2D0258]
MALE = [0x2D05E8, 0x2D05F8, 0x2D0610, 0x2D0628, 0x2D0634, 0x2D0640, 0x2D064C, 0x2D0660,
        0x2D066C, 0x2D0678, 0x2D0690, 0x2D069C, 0x2D06AC]

# address: original word (checked against code.bin by build.py --code-bin)
EXPECTED = {
    0x2CFF98: 0xE3540000,  # cmp r4, #0 (female?)
    0x2CFF9C: 0x0A0000C2,  # beq <male list>
    0x2D02AC: 0xE28F0FCD,  # first male class
    0x2D0454: 0xE0850104,  # add r0, r5, r4, lsl #2   (list builder: reclass slot address)
    0x2D0458: 0xE590006C,  # ldr r0, [r0, #0x6c]
    0x2D04D4: 0xE3540003,  # cmp r4, #3
    0x21412C: 0xE0850104,  # add r0, r5, r4, lsl #2   (avatar test)
    0x214130: 0xE590006C,  # ldr r0, [r0, #0x6c]
    0x214154: 0xE3540003,  # cmp r4, #3
    0x2BBE90: 0xE2810001,  # add r0, r1, #1           (append to the list)
}

S = r'''
    .syntax unified
    .arm
@ ---------------------------------------------------------------- avatar classes
@ Enters at 0x2CFF98 (the old 'cmp r4, #0'). r4 = 1 female / 0 male, r8 = the list.
    .section .cave_a,"ax"
pu_avatar:
    adr r0, lbl_av
    bl f_label
    movs r5, r0
    beq 5f
    ldr r6, [r5], #4                    @ entries
    cmp r6, #0
    beq 5f
1:  ldrb r0, [r5, #4]                   @ gender of this entry
    cmp r0, r4
    bne 2f
    ldr r0, [r5]                        @ JID
    cmp r0, #0
    beq 2f
    bl f_job
    mov r1, r0
    mov r0, r8
    bl f_add
2:  add r5, r5, #8
    subs r6, r6, #1
    bne 1b
4:  cmp r4, #0
    beq ret_male
    b ret_female
5:  adr r5, def_female                  @ no table: the game's own 13 classes
    cmp r4, #0
    addeq r5, r5, #52
    mov r6, #13
6:  ldr r0, [r5], #4
    bl f_job
    mov r1, r0
    mov r0, r8
    bl f_add
    subs r6, r6, #1
    bne 6b
    b 4b
lbl_av: .asciz "PU_AvatarCls"
    .align 2
def_female: .word DEF_FEMALE
def_male: .word DEF_MALE

@ ---------------------------------------------------------------- reclass slots 4-5
    .section .cave_b,"ax"
@ rc_a: replaces 'add r0, r5, r4, lsl #2' at 0x2D0454 (r5 = person + gender*12, r4 = slot,
@ r9 = gender*3); rc_b: the same at 0x21412C (gender*3 in r8). Returns the JID in r0.
rc_a:
    mov r0, r5
    mov r1, r4
    mov r2, r9
    b rc_get
rc_b:
    mov r0, r5
    mov r1, r4
    mov r2, r8
rc_get:
    cmp r1, #3
    addlt r0, r0, r1, lsl #2
    ldrlt r0, [r0, #0x6c]
    bxlt lr
    push {r4-r6, lr}
    sub r4, r0, r2, lsl #2              @ the person
    sub r5, r1, #3                      @ 0/1 = slot 4/5
    cmp r2, #0
    addne r5, r5, #2                    @ female slots follow the male ones
    adr r0, lbl_cx
    bl f_label
    movs r6, r0
    beq 9f
    mov r0, r4
    bl f_pos
    ldr r1, [r6], #4
8:  subs r1, r1, #1
    blt 9f
    ldrh r2, [r6]
    cmp r2, r0
    addne r6, r6, #20
    bne 8b
    add r6, r6, #4
    ldr r0, [r6, r5, lsl #2]
    pop {r4-r6, pc}
9:  mov r0, #0
    pop {r4-r6, pc}

@ cap: replaces 'add r0, r1, #1' at 0x2BBE90 (r1 = count, r5 = list, r4 = class)
cap:
    cmp r1, #64
    popge {r4, r5, r6, pc}
    add r0, r1, #1
    add r1, r5, r1, lsl #2
    str r0, [r5, #0x104]
    str r4, [r1, #4]
    pop {r4, r5, r6, pc}
lbl_cx: .asciz "PU_ClassEx"
    .align 2

@ ---------------------------------------------------------------- sites
    .section .s_2d0454,"ax"
    bl rc_a
    nop
    .section .s_2d04d4,"ax"
    cmp r4, #5
    .section .s_21412c,"ax"
    bl rc_b
    nop
    .section .s_214154,"ax"
    cmp r4, #5
    .section .s_2bbe90,"ax"
    b cap
'''
PATCH_S = (S.replace("DEF_FEMALE", ", ".join(f"{a:#x}" for a in FEMALE))
           .replace("DEF_MALE", ", ".join(f"{a:#x}" for a in MALE)))
LINK_LD = f'''f_label = {F_LABEL:#x};
f_job = {F_JOB:#x};
f_add = {F_ADD:#x};
f_pos = {F_POS:#x};
ret_female = {RET_FEMALE:#x};
ret_male = {RET_MALE:#x};
SECTIONS {{
  .s_21412c 0x21412c : {{ *(.s_21412c) }}
  .s_214154 0x214154 : {{ *(.s_214154) }}
  .s_2bbe90 0x2bbe90 : {{ *(.s_2bbe90) }}
  .cave_a {CAVE_A:#x} : {{ *(.cave_a) }}
  .cave_b {CAVE_B:#x} : {{ *(.cave_b) }}
  .s_2d0454 0x2d0454 : {{ *(.s_2d0454) }}
  .s_2d04d4 0x2d04d4 : {{ *(.s_2d04d4) }}
}}
ASSERT(SIZEOF(.cave_a) <= {CAVE_A_END - CAVE_A:#x}, "cave_a too big")
ASSERT(SIZEOF(.cave_b) <= {CAVE_B_END - CAVE_B:#x}, "cave_b too big")
'''
