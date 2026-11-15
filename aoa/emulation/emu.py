"""Unicorn x86-32 emulator for running original client code offline.

Emu maps a client image (aoa.analysis.pe_util.PE) into memory: sections
copied from the file, virtual tails zero-filled, plus stack, heap, scratch
and stub regions. MFC42 operator new (ord823) / delete (ord825) are replaced
by a bump allocator / no-op; nothing else of the OS, loader or Winsock runs.
`thiscall` runs one function until it returns to STOP.

The emulation checks in this package and many suites build on it. The
2.7.1-only CCompress and CComm cross-check that used to live here is
archive/analysis/emulate_codec_271.py.
"""
from unicorn import UC_ARCH_X86, UC_HOOK_CODE, UC_MODE_32, Uc
from unicorn.x86_const import (UC_X86_REG_EAX, UC_X86_REG_ECX, UC_X86_REG_EIP,
                               UC_X86_REG_ESP)


STACK, HEAP, SCRATCH, STUBS = 0x10000000, 0x20000000, 0x30000000, 0x40000000
STOP = STUBS + 0x100
NEW, DELETE = STUBS + 0x10, STUBS + 0x20


class Emu:
    def __init__(self, pe):
        self.pe = pe
        self.uc = uc = Uc(UC_ARCH_X86, UC_MODE_32)
        size = (pe.pe.OPTIONAL_HEADER.SizeOfImage + 0xFFF) & ~0xFFF
        uc.mem_map(pe.base, size)
        for s in pe.sections:
            raw = pe.data[s["raw_off"]:s["raw_off"] + min(s["raw_size"], max(s["vsize"], s["raw_size"]))]
            uc.mem_write(s["va"], raw)
        for base, sz in ((STACK, 0x100000), (HEAP, 0x4000000), (SCRATCH, 0x100000), (STUBS, 0x1000)):
            uc.mem_map(base, sz)
        for iat, name in pe.imports.items():
            if name == "MFC42.DLL!ord823":
                uc.mem_write(iat, NEW.to_bytes(4, "little"))
            elif name == "MFC42.DLL!ord825":
                uc.mem_write(iat, DELETE.to_bytes(4, "little"))
        self.brk = HEAP
        uc.hook_add(UC_HOOK_CODE, self._stub, begin=NEW, end=DELETE)

    def _stub(self, uc, addr, size, _):
        esp = uc.reg_read(UC_X86_REG_ESP)
        ret = int.from_bytes(uc.mem_read(esp, 4), "little")
        if addr == NEW:
            n = int.from_bytes(uc.mem_read(esp + 4, 4), "little")
            p = self.brk
            self.brk = (self.brk + n + 0x1F) & ~0xF
            uc.reg_write(UC_X86_REG_EAX, p)
        uc.reg_write(UC_X86_REG_ESP, esp + 4)  # cdecl: caller pops args
        uc.reg_write(UC_X86_REG_EIP, ret)

    def thiscall(self, fn, this, *args):
        sp = STACK + 0xF0000
        frame = STOP.to_bytes(4, "little") + b"".join(a.to_bytes(4, "little") for a in args)
        self.uc.mem_write(sp, frame)
        self.uc.reg_write(UC_X86_REG_ESP, sp)
        self.uc.reg_write(UC_X86_REG_ECX, this)
        self.uc.emu_start(fn, STOP, count=50_000_000)
        return self.uc.reg_read(UC_X86_REG_EAX)

    def read(self, va, n):
        return bytes(self.uc.mem_read(va, n))

    def write(self, va, b):
        self.uc.mem_write(va, b)
