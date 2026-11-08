"""Every place the "60 support partners" part changes (North American code.bin, version 1.0),
checked against the disassembly. gen.py turns this list into the patch."""
CAVE = 0x459B90          # free zero bytes at end of .text (0x459B88..0x45A000)
CAVE_END = 0x45A000
COUNT8 = 0x523F00        # unused tail of the last .bss page (bss ends 0x52320C)
COUNT = 0x4D0BA8         # game's global: static position of PID_ダミー
F_LABEL = 0x2BE6B0       # label lookup (string -> record), 0 if missing
F_POS = 0x2DA13C         # person pointer -> static position (file bits in 0xF000)
F_ALLOC = 0x31276C       # alloc(size)
F_CLEAR = 0x312A68       # clear(buf, size)
N_OLD, N_NEW = 52, 60

# kind 1: 'add rD, rP, rI, lsl #3' -> rD = slot(P,I) - 0x88
# kind 2: 'ldr rD, [rP, rOff]'      -> rD = *slot(P,I)
# kind 3: 'add rD, rA, rB'          -> rD = points(unit,idx) - 0xC4 (read only)
# kind 4: same, allocating the extension buffer (write)
SITES = [
  # addr,     kind, D, A(person/unit), B(index), expected original word
  (0x18FF88, 1, 0, 7, 6, 0xE0870186),
  (0x20AB3C, 1, 0, 0, 4, 0xE0800184),
  (0x20AFAC, 1, 0, 0, 4, 0xE0800184),
  (0x27D8B8, 1, 5, 0, 4, 0xE0805184),
  (0x2AFC78, 1, 0, 0, 5, 0xE0800185),
  (0x2AFF48, 1, 0, 5, 4, 0xE0850184),
  (0x2AFF6C, 1, 0, 5, 4, 0xE0850184),
  (0x3B2730, 1, 0, 0, 4, 0xE0800184),
  (0x3B2854, 1, 0, 0, 4, 0xE0800184),
  (0x209A48, 2, 2, 1, 0, 0xE7912002),
  (0x209AD8, 2, 2, 1, 0, 0xE7912002),
  (0x20B9D8, 2, 2, 1, 0, 0xE7912002),
  (0x20AB10, 2, 0, 0, 4, 0xE7900001),
  (0x20AF80, 2, 0, 0, 4, 0xE7900001),
  (0x20A4E4, 3, 0, 0, 2, 0xE0800002),
  (0x20B558, 3, 0, 0, 1, 0xE0800001),
  (0x20BD6C, 3, 1, 1, 6, 0xE0811006),
  (0x20BE5C, 3, 1, 1, 4, 0xE0811004),
  (0x20C040, 3, 1, 1, 6, 0xE0811006),
  (0x20C144, 3, 1, 1, 2, 0xE0811002),
  (0x20C1D4, 3, 0, 0, 1, 0xE0800001),
  (0x278380, 3, 1, 1, 7, 0xE0811007),
  (0x27DCCC, 3, 3, 3, 4, 0xE0833004),
  (0x2DE2DC, 3, 1, 1, 4, 0xE0811004),
  (0x3B2834, 3, 0, 0, 5, 0xE0800005),
  (0x3B28A4, 3, 0, 5, 4, 0xE0850004),
  (0x414B40, 3, 1, 1, 4, 0xE0811004),
  (0x20A53C, 4, 1, 1, 2, 0xE0811002),
  (0x20A578, 4, 1, 1, 2, 0xE0811002),
  (0x27BC3C, 4, 0, 0, 4, 0xE0800004),
  (0x27BC6C, 4, 0, 0, 5, 0xE0800005),
  (0x27D96C, 4, 1, 6, 4, 0xE0861004),
]
# loop bounds 'cmp rX, #52' -> #60  (addr, expected word)
BOUNDS = [(0x1900F0,0xE3560034),(0x209A58,0xE3500034),(0x209AE8,0xE3500034),(0x20AB98,0xE3540034),
          (0x20B008,0xE3540034),(0x20B9E8,0xE3500034),(0x27D978,0xE3540034),(0x2AFCC0,0xE3550034),
          (0x2AFF80,0xE3540034),(0x3B27E8,0xE3540034),(0x3B2904,0xE3540034)]
# simple word replacements (addr, expected, new)
WORDS = [
  (0x18FF70, 0xE3A000D0, 0xE3A000F0),   # alloc 52*4 -> 60*4 list
  (0x20AAD8, 0xE2800035, 0xE280003D),   # (units+53)*4 -> (units+61)*4
  (0x20AF48, 0xE2800035, 0xE280003D),
  (0x3A2B30, COUNT, COUNT8),            # loader: buffer length uses count+8
  (0x3A4F20, COUNT, COUNT8),            # writer
  (0x2B7870, COUNT, COUNT8),            # unit copy
]
