"""60 support slots: writes the assembly (PATCH_S) and the linker script (LINK_LD).

The places in the game code that read a character's 52 support slots are listed in sites.py.
Each one is redirected (one 'bl' instruction) into new code in free space at the end of the
game's code, which reads slots 53-60 from the PU_SupportEx2 table Paragon writes into
data/person/static.bin. Run build.py (one folder up) to make the patch.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sites import *  # noqa: E402,F401,F403
B=0x100000
codes=sorted(set((k<<12)|(b<<8)|(a<<4)|d for _,k,d,a,b,_ in SITES))
S=[]
S.append(f"""
    .syntax unified
    .arm
    .section .cave,"ax"
    .global cave_start
cave_start:
@ ---------------- per-site stubs (enter with bl; all regs + flags preserved except rD)
""")
for c in codes:
    S.append(f"""stub_{c:04x}:
    push {{r0-r12, lr}}
    mov r0, #{c & 0xff}
    orr r0, r0, #{c & 0xff00}
    b common
""")
S.append(f"""
common:
    mrs r11, cpsr
    mov r10, r0
    and r1, r10, #0xF0
    lsr r1, r1, #4
    ldr r4, [sp, r1, lsl #2]          @ A
    and r1, r10, #0xF00
    lsr r1, r1, #8
    ldr r5, [sp, r1, lsl #2]          @ B
    lsr r9, r10, #12                  @ kind
    mov r8, sp
    bic sp, sp, #7                    @ 8-byte align for calls
    cmp r9, #3
    bge 1f
    mov r0, r4
    mov r1, r5
    bl slot_ptr
    cmp r9, #1
    subeq r0, r0, #0x88
    ldrne r0, [r0]
    b 2f
1:  cmp r4, r5                        @ unit = larger, index = smaller
    movlo r0, r5
    movlo r1, r4
    movhs r0, r4
    movhs r1, r5
    sub r2, r9, #3                    @ 0 = read, 1 = write (allocate)
    bl pts_ptr
    sub r0, r0, #0xC4
2:  mov sp, r8
    and r1, r10, #0xF
    str r0, [sp, r1, lsl #2]
    msr cpsr_f, r11
    pop {{r0-r12, pc}}

@ slot_ptr(r0=person, r1=i) -> address of slot i (8 bytes: PID ptr, C/B/A/S thresholds)
slot_ptr:
    cmp r1, #{N_OLD}
    addlt r0, r0, r1, lsl #3
    addlt r0, r0, #0x88
    bxlt lr
    push {{r4-r6, lr}}
    mov r4, r0
    sub r5, r1, #{N_OLD}
    cmp r5, #{N_NEW-N_OLD}
    bhs 9f
    adr r0, label
    bl f_label
    movs r6, r0
    beq 9f
    mov r0, r4
    bl f_pos                          @ r0 = static position of this person
    ldr r1, [r6], #4                  @ r1 = entry count, r6 -> first entry
8:  subs r1, r1, #1
    blt 9f
    ldrh r2, [r6]                     @ entry owner (u16 position)
    cmp r2, r0
    addne r6, r6, #68
    bne 8b
    add r0, r6, #4
    add r0, r0, r5, lsl #3
    pop {{r4-r6, pc}}
9:  adr r0, zero8
    pop {{r4-r6, pc}}

@ pts_ptr(r0=unit, r1=idx, r2=alloc) -> address of the support-points byte
pts_ptr:
    cmp r1, #{N_OLD}
    addlt r0, r0, r1
    addlt r0, r0, #0xC4
    bxlt lr
    push {{r4-r6, lr}}
    mov r4, r0
    sub r5, r1, #{N_OLD}
    mov r6, r2
    ldr r0, [r4, #0xF8]
    cmp r0, #0
    bne 3f
    cmp r6, #0
    adreq r0, zero8
    popeq {{r4-r6, pc}}
    ldr r0, =COUNT_ADDR
    ldr r0, [r0]
    add r0, r0, #8
    bl f_alloc
    str r0, [r4, #0xF8]
    ldr r1, =COUNT_ADDR
    ldr r1, [r1]
    add r1, r1, #8
    bl f_clear
    ldr r0, [r4, #0xF8]
3:  ldr r1, =COUNT_ADDR
    ldr r1, [r1]
    add r0, r0, r1
    add r0, r0, r5
    pop {{r4-r6, pc}}

@ replacement for leaf FUN_002EF8F8: PID of first partner whose S threshold is reached
new_2ef8f8:
    push {{r4-r8, lr}}
    mov r4, r0
    mov r5, #0
4:  ldr r0, [r4, #0x64]
    mov r1, r5
    bl slot_ptr
    mov r6, r0
    ldr r3, [r6]
    cmp r3, #0
    beq 5f
    mov r0, r4
    mov r1, r5
    mov r2, #0
    bl pts_ptr
    ldrb r3, [r0]
    ldrb r2, [r6, #7]
    cmp r2, r3
    bgt 5f
    ldr r0, [r6]
    pop {{r4-r8, pc}}
5:  add r5, r5, #1
    cmp r5, #{N_NEW}
    blt 4b
    ldr r0, [r4, #0x94]
    ands r0, r0, #0x400000
    ldrne r0, =0x45F2C8
    pop {{r4-r8, pc}}

@ end of GameData load (replaces 'pop {{r3-r9,pc}}' at 0x3D5340): also store count+8
count_hook:
    add r2, r0, #8
    ldr r1, =COUNT8_ADDR
    str r2, [r1]
    pop {{r3-r9, pc}}

    .ltorg
    .align 2
zero8: .word 0, 0
label: .asciz "PU_SupportEx2"
    .align 2
    .global cave_end
cave_end:
""")
# site sections
for a,k,d,aa,bb,_ in SITES:
    c=(k<<12)|(bb<<8)|(aa<<4)|d
    S.append(f'    .section .s_{a:x},"ax"\n    bl stub_{c:04x}\n')
for a,_ in BOUNDS:
    pass
S.append(f'    .section .s_2ef8f8,"ax"\n    b new_2ef8f8\n')
S.append(f'    .section .s_3d5340,"ax"\n    b count_hook\n')
# 27d20c..27d228 rewrite (alloc count+8 for the bond buffer)
S.append(f'''    .section .s_27d20c,"ax"
    ldr r0, [r8]
    add r0, r0, #8
    bl f_alloc
    str r0, [r4, #0xf8]
    ldr r1, [r8]
    add r1, r1, #8
    bl f_clear
    b ret_27d1ec
''')
PATCH_S = '\n'.join(S).replace('COUNT_ADDR', f'{COUNT:#x}').replace('COUNT8_ADDR', f'{COUNT8:#x}')
# linker script: every section at its own address, in address order
secs = [(".cave", CAVE)] + [(f".s_{a:x}", a) for a, *_ in SITES]
secs += [(".s_2ef8f8", 0x2EF8F8), (".s_3d5340", 0x3D5340), (".s_27d20c", 0x27D20C)]
secs.sort(key=lambda x: x[1])
LINK_LD = (
    f"f_label = {F_LABEL:#x};\n"
    f"f_pos = {F_POS:#x};\n"
    f"f_alloc = {F_ALLOC:#x};\n"
    f"f_clear = {F_CLEAR:#x};\n"
    "ret_27d1ec = 0x27d1ec;\n"
    "SECTIONS {\n" + "".join(f"  {n} {a:#x} : {{ *({n}) }}\n" for n, a in secs) + "}\n"
)
