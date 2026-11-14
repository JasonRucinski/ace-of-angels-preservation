"""Fixtures shared by the suites that run original client code; needs unicorn and the game."""
import math
import struct

from aoa.client.patches import object_persistence as patch
from aoa.client.patches import visibility_fix
from aoa.emulation.emu import Emu, SCRATCH, STACK, STUBS
from aoa.analysis.pe_util import PE
from aoa.paths import ROOT
from unicorn import UC_HOOK_CODE
from unicorn.x86_const import UC_X86_REG_ECX, UC_X86_REG_ESP, UC_X86_REG_FPCW

SOURCE = ROOT / "game/2.9.2/AOACLIENT.EXE.orig"


class GroupProbe:
    def __init__(self, distant=False, extras=()):
        self.emu = e = Emu(PE(SOURCE))
        for module in (visibility_fix, *extras, *((patch,) if distant else ())):
            for offset, _, new in module.regions():
                e.write(offset + 0x400000, new)
        # Only the C runtime's x87 asin/acos calls are replaced. All group,
        # distance, projected-size and mesh-selection instructions are original.
        self.input, self.output = SCRATCH + 0x9000, SCRATCH + 0x9010
        functions = {}
        for i, (iat, fn) in enumerate(((0x58C368, math.asin), (0x58C364, math.acos))):
            stub = STUBS + 0x400 + i * 0x20
            e.write(iat, struct.pack("<I", stub))
            e.write(stub, b"\xdd\x1d" + struct.pack("<I", self.input)
                    + b"\xdd\x05" + struct.pack("<I", self.output) + b"\xc3")
            functions[stub + 6] = fn

        def trig(uc, address, size, _):
            if address in functions:
                value = struct.unpack("<d", e.read(self.input, 8))[0]
                e.write(self.output, struct.pack("<d", functions[address](value)))
        e.uc.hook_add(UC_HOOK_CODE, trig, begin=STUBS + 0x400, end=STUBS + 0x440)

    def run(self, meshes, distance=100_000., radius=100., control=0x7F, enabled=True, behind=False):
        e = self.emu
        node, camera, context = SCRATCH, SCRATCH + 0xA000, SCRATCH + 0xB000
        e.write(node, bytes(0x400))
        e.write(node + 0xAC, struct.pack("<3f", 0, 0, -distance if behind else distance))
        e.write(node + 0x164, struct.pack("<f", radius))
        e.write(node + 0x150, bytes([enabled, 0, 1]))
        e.write(node + 0x234, struct.pack("<I", SCRATCH + 0x8000))
        e.write(node + 0x33A, b"\1")
        for i, mesh in enumerate(meshes):
            child, link = SCRATCH + 0x1000 + i * 0x400, SCRATCH + 0x8000 + i * 0x20
            e.write(child, bytes(0x400))
            e.write(child + 0x180, struct.pack("<2f", *mesh["screen_size_range"]))
            e.write(link, bytes(0x20))
            e.write(link + 8, struct.pack("<I", link + 0x20 if i + 1 < len(meshes) else 0))
            e.write(link + 0x10, struct.pack("<I", child))
        e.write(camera, bytes(0x100))
        e.write(camera + 0x70, struct.pack("<3f", 0, 0, 1))
        e.write(context, bytes(0x100))
        e.write(context + 8, struct.pack("<f", 960))
        sp = STACK + 0x8000
        e.write(sp, struct.pack("<3I", 0, camera, context))
        e.uc.reg_write(UC_X86_REG_ECX, node)
        e.uc.reg_write(UC_X86_REG_ESP, sp)
        e.uc.reg_write(UC_X86_REG_FPCW, control)
        e.uc.emu_start(0x546B20, 0x546C10, count=10_000)
        assert e.uc.reg_read(UC_X86_REG_ESP) == sp - 0x2C
        assert e.uc.reg_read(UC_X86_REG_FPCW) == control
        return {
            "visible": bool(e.read(node + 0x151, 1)[0]),
            "size": struct.unpack("<f", e.read(node + 0x17C, 4))[0],
            "range": struct.unpack("<2f", e.read(node + 0x180, 8)),
            "selected": [i for i in range(len(meshes))
                         if e.read(SCRATCH + 0x1000 + i * 0x400 + 0x152, 1) == b"\1"],
        }
