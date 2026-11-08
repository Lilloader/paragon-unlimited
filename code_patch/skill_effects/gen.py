"""Paragon Unlimited skill-effect engine for Awakening (North American version 1.0) code.bin.
Rules come from a GameData.bin block labelled PU_SkillFx: [u32 count][count x 8-byte rules]
rule: u16 skill id, u8 effect, u8 cond1, u8 cond2, s8 value, u16 reserved
Applied to both combatants after the game has worked out the battle numbers (hook at 0x2F1C30,
the call to FUN_003EEA6C, which turns them into hit %, crit %, damage and follow-ups).
Writes the assembly (PATCH_S) and the linker script (LINK_LD); run build.py one folder up."""
S = r'''
    .syntax unified
    .arm
@ ---------------------------------------------------------------- region 1 (old FUN_00218B30)
    .section .s_218b30,"ax"
    bx lr                               @ Hit+10 / Sure Strike / Avoid+10 / Gamble now come from the rules

    .section .cave2,"ax"
    .global pu_battle
@ pu_battle(r0 = battle): replaces 'bl FUN_003EEA6C' at 0x2F1C30
pu_battle:
    push {r3-r11, lr}
    mov r4, r0
    ldr r0, [r4, #0x180]
    tst r0, #0x80                       @ same checks as FUN_003EE888: numbers were (re)computed
    bne 9f
    ldr r0, [r4, #0x1c]
    tst r0, #4
    bne 9f
    adr r0, lbl_fx
    bl f_label
    movs r10, r0
    beq 9f
    mov r5, r4
    add r6, r4, #0xbc
    bl apply
    add r5, r4, #0xbc
    mov r6, r4
    bl apply
9:  mov r0, r4
    pop {r3-r11, lr}
    b f_eea6c

@ apply: r5 = side, r6 = other side, r10 = rule block
apply:
    push {r3, lr}
    ldr r7, [r5]                        @ unit
    cmp r7, #0
    popeq {r3, pc}
    mvn r11, #0                         @ other unit's class categories: not read yet
    ldr r9, [r10]
    add r8, r10, #4
1:  subs r9, r9, #1
    poplt {r3, pc}
    mov r0, r7
    ldrh r1, [r8]
    cmp r1, #0
    beq 8f
    bl f_hasskill
    cmp r0, #0
    beq 8f
    ldrb r0, [r8, #3]
    bl cond
    cmp r0, #0
    beq 8f
    ldrb r0, [r8, #4]
    bl cond
    cmp r0, #0
    beq 8f
    ldrb r0, [r8, #2]                   @ effect 1..7
    sub r0, r0, #1
    cmp r0, #7
    bhs 8f
    ldrsb r3, [r8, #5]
    cmp r0, #1                          @ effect 2 = damage received: lower it by raising Def/Res
    rsbeq r3, r3, #0
    add r1, r5, #0x30
    ldr r2, [r1, r0, lsl #2]
    adds r2, r2, r3
    movmi r2, #0
    str r2, [r1, r0, lsl #2]
    ldrh r0, [r8]                       @ mark the skill as used in this battle (ids < 112 only)
    cmp r0, #112
    bhs 8f
    add r1, r5, #0x8a
    add r1, r1, r0, lsr #3
    ldrb r2, [r1]
    and r3, r0, #7
    mov r12, #1
    orr r2, r2, r12, lsl r3
    strb r2, [r1]
8:  add r8, r8, #8
    b 1b

lbl_fx: .asciz "PU_SkillFx"
    .align 2

@ cond(r0 = condition) -> r0 = 1 / 0. Uses r5, r6, r7, r11 (r11 cache).
cond:
    cmp r0, #15
    movhs r0, #0
    bxhs lr
    add pc, pc, r0, lsl #2
    nop
    b c_true                            @ 0  always
    b c_init                            @ 1  this unit started the fight
    b c_def                             @ 2  the other unit started it
    b c_hpfull                          @ 3  HP full
    b c_hpnotfull                       @ 4  HP not full
    b c_hphalf                          @ 5  HP 50% or less
    b c_even                            @ 6  even turn
    b c_odd                             @ 7  odd turn
    b c_fly                             @ 8  foe flies
    b c_notmounted                      @ 9  foe neither flies nor rides
    b c_foefull                         @ 10 foe HP full
    b c_foenotfull                      @ 11 foe HP not full
    b c_foemag                          @ 12 foe attacks with magic
    b c_foephys                         @ 13 foe attacks with a physical weapon
    b c_hpquarter                       @ 14 HP 25% or less
c_true: mov r0, #1
    bx lr
c_init: ldr r0, [r5, #0x1c]
    and r0, r0, #1
    bx lr
c_def: ldr r0, [r5, #0x1c]
    and r0, r0, #1
    eor r0, r0, #1
    bx lr
c_even: ldr r0, [r5, #0x74]
    and r0, r0, #1
    eor r0, r0, #1
    bx lr
c_odd: ldr r0, [r5, #0x74]
    and r0, r0, #1
    bx lr
c_foemag: ldr r0, [r6, #0x1c]
    lsr r0, r0, #1
    and r0, r0, #1
    bx lr
@ HP tests: r1 = mode (0 full, 1 not full, 2 half, 3 quarter), r2 = unit
c_hpfull: mov r1, #0
    b hp_self
c_hpnotfull: mov r1, #1
    b hp_self
c_hphalf: mov r1, #2
    b hp_self
c_hpquarter: mov r1, #3
hp_self: mov r2, r7
    b hp_test
c_foefull: mov r1, #0
    b hp_foe
c_foenotfull: mov r1, #1
hp_foe: ldr r2, [r6]
    cmp r2, #0
    moveq r0, #0
    bxeq lr
    b hp_test
c_fly: mov r1, #0
    b cat_test
c_notmounted: mov r1, #1
    b cat_test
    .ltorg

    .section .cave3,"ax"
c_foephys: ldr r0, [r6, #0xc]
    cmp r0, #0
    bxeq lr
    ldr r0, [r6, #0x1c]
    lsr r0, r0, #1
    and r0, r0, #1
    eor r0, r0, #1
    bx lr
hp_test:
    push {r4, r5, r6, lr}
    mov r4, r1
    mov r5, r2
    ldrsb r6, [r5, #0x8f]               @ current HP
    mov r0, r5
    mov r1, #3
    bl f_maxhp                          @ FUN_002F3AC0(unit, 3) = max HP
    cmp r4, #0
    bne 1f
    cmp r6, r0
    movge r0, #1
    movlt r0, #0
    pop {r4, r5, r6, pc}
1:  cmp r4, #1
    bne 2f
    cmp r6, r0
    movlt r0, #1
    movge r0, #0
    pop {r4, r5, r6, pc}
2:  cmp r4, #2
    lsleq r6, r6, #1
    lslne r6, r6, #2
    cmp r6, r0
    movle r0, #1
    movgt r0, #0
    pop {r4, r5, r6, pc}

@ cat_test: r1 = 0 -> foe flies; 1 -> foe neither flies nor is a rider/beast
cat_test:
    push {r4, r5, r6, lr}
    mov r4, r1
    ldr r0, [r6]
    cmp r0, #0
    moveq r0, #0
    popeq {r4, r5, r6, pc}
    cmn r11, #1
    bne 1f
    bl f_cats                           @ FUN_002CA8A0(unit) -> class category bits
    mov r11, r0
1:  adr r0, jc_fly
    bl jcid_bit
    mov r5, r0
    cmp r4, #0
    andeq r0, r11, r5
    beq 3f
    adr r0, jc_beast
    bl jcid_bit
    orr r5, r5, r0
    ands r0, r11, r5
    moveq r0, #1
    movne r0, #0
    pop {r4, r5, r6, pc}
3:  cmp r0, #0
    movne r0, #1
    pop {r4, r5, r6, pc}
jcid_bit:
    push {r4, lr}
    bl f_label
    cmp r0, #0
    popeq {r4, pc}
    ldr r1, [r0, #4]
    mov r0, #1
    lsl r0, r0, r1
    pop {r4, pc}
jc_fly: .byte 0x4A,0x43,0x49,0x44,0x5F,0x94,0xF2,0x8D,0x73,0x00   @ "JCID_飛行"
jc_beast: .byte 0x4A,0x43,0x49,0x44,0x5F,0x8F,0x62,0x00           @ "JCID_獣"
    .align 2

    .section .s_2f1c30,"ax"
    bl pu_battle
'''
PATCH_S = S
ld = '''f_label = 0x2be6b0;
f_hasskill = 0x2eba08;
f_maxhp = 0x2f3ac0;
f_cats = 0x2ca8a0;
f_eea6c = 0x3eea6c;
SECTIONS {
  .s_218b30 0x218b30 : { *(.s_218b30) }
  .cave2 0x218b34 : { *(.cave2) }
  .s_2f1c30 0x2f1c30 : { *(.s_2f1c30) }
  .cave3 0x459ed4 : { *(.cave3) }
}
ASSERT(SIZEOF(.cave2) <= 0x218d64 - 0x218b34, "cave2 too big")
ASSERT(SIZEOF(.cave3) <= 0x45a000 - 0x459ed4, "cave3 too big")
'''
LINK_LD = ld
