"""Run the game's Second Seal list builder (FUN_002CFF38) in an emulator, with the game
functions it calls replaced by small Python stand-ins, on the original and the patched code."""
import os, struct, sys
sys.path.insert(0, os.environ.get('UNICORN_PATH', '')) if os.environ.get('UNICORN_PATH') else None
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_CODE
from unicorn.arm_const import *

CODE = 0x100000
DATA = 0x10000000
STACK = 0x20000000
END = 0x30000000  # return address that stops the run


class Game:
    def __init__(self, code_bin):
        self.uc = Uc(UC_ARCH_ARM, UC_MODE_ARM)
        size = (len(code_bin) + 0xFFFFF) & ~0xFFFFF
        self.uc.mem_map(CODE, size + 0x100000)
        self.uc.mem_write(CODE, code_bin)
        self.uc.mem_map(DATA, 0x100000)
        self.uc.mem_map(STACK - 0x10000, 0x20000)
        self.uc.mem_map(END, 0x1000)
        self.top = DATA
        self.strings = {}
        self.jobs = {}  # address -> JID
        self.labels = {}
        self.pos = {}
        self.attrs = {}  # unit -> bitmask of attributes
        self.sid = {'SID_女性': 1, 'SID_マムクート': 2, 'SID_ラグズ': 3}
        self.sidrec = {}
        for name, bit in self.sid.items():
            r = self.alloc(8)
            self.w32(r + 4, bit)
            self.sidrec[name] = r
        mocks = {0x2BE6B0: self.f_label, 0x302FC4: self.f_sid, 0x308E50: self.f_mask,
                 0x2EF8C0: self.f_has, 0x2DE558: self.f_job, 0x2BBDC8: lambda: 0,
                 0x2D0AD8: lambda: 30, 0x2BBCA4: lambda: 0, 0x303044: self.f_strcmp,
                 0x2DA13C: self.f_pos}
        self.mocks = mocks
        self.uc.hook_add(UC_HOOK_CODE, self._hook)

    def alloc(self, n):
        a = self.top
        self.top += (n + 7) & ~7
        self.uc.mem_write(a, b'\0' * n)
        return a

    def w32(self, a, v): self.uc.mem_write(a, struct.pack('<I', v))
    def r32(self, a): return struct.unpack('<I', self.uc.mem_read(a, 4))[0]

    def cstr(self, a):
        out = b''
        while True:
            c = bytes(self.uc.mem_read(a, 1))
            if c == b'\0': return out.decode('shift_jis')
            out += c; a += 1

    def string(self, s):
        if s not in self.strings:
            b = s.encode('shift_jis') + b'\0'
            a = self.alloc(len(b)); self.uc.mem_write(a, b); self.strings[s] = a
        return self.strings[s]

    # --- stand-ins
    def f_label(self):
        return self.labels.get(self.cstr(self.uc.reg_read(UC_ARM_REG_R0)), 0)
    def f_sid(self):
        return self.sidrec.get(self.cstr(self.uc.reg_read(UC_ARM_REG_R0)), 0)
    def f_mask(self):
        bit = self.uc.reg_read(UC_ARM_REG_R2)
        self.uc.reg_write(UC_ARM_REG_R1, 0)
        return 1 << bit
    def f_has(self):
        unit = self.uc.reg_read(UC_ARM_REG_R0)
        m = self.uc.reg_read(UC_ARM_REG_R2)
        self.uc.reg_write(UC_ARM_REG_R1, 0)
        return self.attrs.get(unit, 0) & m
    def f_job(self):
        jid = self.cstr(self.uc.reg_read(UC_ARM_REG_R0))
        for a, j in self.jobs.items():
            if j == jid: return a
        a = self.alloc(0x100); self.jobs[a] = jid
        return a
    def f_strcmp(self):
        a = self.cstr(self.uc.reg_read(UC_ARM_REG_R0)); b = self.cstr(self.uc.reg_read(UC_ARM_REG_R1))
        return 0 if a == b else 1
    def f_pos(self):
        return self.pos.get(self.uc.reg_read(UC_ARM_REG_R0), 0xFFFF)

    def _hook(self, uc, addr, size, _):
        f = self.mocks.get(addr)
        if f:
            uc.reg_write(UC_ARM_REG_R0, f() & 0xFFFFFFFF)
            uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))

    # --- data
    def person(self, pos, male=(None, None, None), female=(None, None, None)):
        p = self.alloc(0x238)
        for i, j in enumerate(male):
            if j: self.w32(p + 0x6C + 4 * i, self.string(j))
        for i, j in enumerate(female):
            if j: self.w32(p + 0x78 + 4 * i, self.string(j))
        self.pos[p] = pos
        return p

    def unit(self, person, female=False, level=1):
        u = self.alloc(0x200)
        self.w32(u + 0x64, person)
        self.uc.mem_write(u + 0x8D, bytes([level]))
        self.attrs[u] = (1 << 1) if female else 0
        return u

    def class_ex(self, rows):  # [(pos, m4, m5, f4, f5)]
        t = self.alloc(4 + 20 * len(rows)); self.w32(t, len(rows))
        for k, (pos, *js) in enumerate(rows):
            e = t + 4 + 20 * k
            self.uc.mem_write(e, struct.pack('<HH', pos, 0))
            for i, j in enumerate(js):
                self.w32(e + 4 + 4 * i, self.string(j) if j else 0)
        self.labels['PU_ClassEx'] = t

    def avatar(self, rows):  # [(jid, gender)]
        t = self.alloc(4 + 8 * len(rows)); self.w32(t, len(rows))
        for k, (j, g) in enumerate(rows):
            self.w32(t + 4 + 8 * k, self.string(j)); self.uc.mem_write(t + 8 + 8 * k, bytes([g]))
        self.labels['PU_AvatarCls'] = t

    def seal_list(self, unit):
        lst = self.alloc(0x110)
        self.w32(lst, unit)
        self.uc.reg_write(UC_ARM_REG_R0, lst)
        self.uc.reg_write(UC_ARM_REG_R1, 0)
        self.uc.reg_write(UC_ARM_REG_SP, STACK)
        self.uc.reg_write(UC_ARM_REG_LR, END)
        self.uc.emu_start(0x2CFF38, END, count=200000)
        n = self.r32(lst + 0x104)
        return [self.jobs.get(self.r32(lst + 4 + 4 * i), hex(self.r32(lst + 4 + 4 * i))) for i in range(min(n, 70))], n
