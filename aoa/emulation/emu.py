"""Unicorn x86-32 emulator for running original client code offline.

Emu maps a client image (aoa.analysis.pe_util.PE) into memory: sections
copied from the file, virtual tails zero-filled, plus stack, heap, scratch
and stub regions. MFC42 operator new (ord823) / delete (ord825) are replaced
by a bump allocator / no-op; nothing else of the OS, loader or Winsock runs.
`thiscall` runs one function until it returns to STOP.

`Emu.for_build(path, "2.9.2")` loads a client only if it is that original
build (aoa.builds), and `emu.stop_at({...})` stops emulation at any of a set
of addresses (the set it returns can be changed between runs).

The emulation checks in this package and many suites build on it. Each
check has `run(client_path) -> report`, which tools/verify_local.py calls in
process; `check_main` is their shared command line (CLIENT.EXE.orig OUT.json).
The 2.7.1-only CCompress and CComm cross-check that used to live here is
archive/analysis/emulate_codec_271.py.
"""
import json
from pathlib import Path

from unicorn import UC_ARCH_X86, UC_HOOK_CODE, UC_MODE_32, Uc
from unicorn.x86_const import (UC_X86_REG_EAX, UC_X86_REG_ECX, UC_X86_REG_EIP,
                               UC_X86_REG_ESP)

from aoa import builds, cli


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

    @classmethod
    def for_build(cls, path, version):
        """An emulator for the client at path; ValueError unless it is the original `version`."""
        from aoa.analysis.pe_util import PE
        pe = PE(path)
        builds.require_build(pe.data, version)
        return cls(pe)

    def stop_at(self, addresses):
        """Stop emulation whenever execution reaches one of addresses; returns the live set."""
        stops = set(addresses)

        def hook(uc, address, size, _):
            if address in stops:
                uc.emu_stop()

        self.uc.hook_add(UC_HOOK_CODE, hook)
        return stops

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


def check_main(doc, run, argv=None):
    """Command line of an emulation check: run(CLIENT) and write the report to OUT as JSON."""
    ap = cli.parser(doc)
    ap.add_argument("source", type=Path, help="pristine 2.9.2 client (AOACLIENT.EXE.orig)")
    ap.add_argument("output", type=Path, help="JSON report to write")
    a = ap.parse_args(argv)
    result = run(a.source)
    write_report(result, a.output)
    print(json.dumps(result, indent=2))


def write_report(result, output):
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
