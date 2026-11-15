"""Fixtures shared by the suites that run original client code; needs unicorn and the game."""
import math
import struct
import unittest

from aoa.client.patches import asteroid_render
from aoa.client.patches import object_persistence as patch
from aoa.client.patches import station_detail
from aoa.client.patches import visibility_fix
from aoa.emulation.emu import Emu, SCRATCH, STACK, STUBS
from aoa.analysis.pe_util import PE
from aoa.formats import gob
from aoa.maps.lod import mesh_nodes
from aoa.paths import ROOT
from tests.support_patches import triples
from unicorn import UC_HOOK_CODE
from unicorn.x86_const import (UC_X86_REG_EAX, UC_X86_REG_ECX, UC_X86_REG_EFLAGS, UC_X86_REG_ESI,
                               UC_X86_REG_ESP, UC_X86_REG_FPCW)

SOURCE = ROOT / "game/2.9.2/AOACLIENT.EXE.orig"


class GroupProbe:
    def __init__(self, distant=False, extras=()):
        self.emu = e = Emu(PE(SOURCE))
        for module in (visibility_fix, *extras, *((patch,) if distant else ())):
            for offset, _, new in (triples(module.PATCH) if hasattr(module, "PATCH") else module.regions()):
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


class AsteroidGate:
    """TestCase mixin: the original distance gate (0x54320B) with `patch`'s regions written in or not.

    Shared by test_asteroid_render and test_solid_world_render, which set `patch`.
    """
    patch = asteroid_render

    def setUp(self):
        self.emu = Emu(PE(SOURCE))

    def gate(self, name, distance, patched=True, control=0x7F):
        e = self.emu
        for offset, old, new in self.patch.regions():
            e.write(offset + 0x400000, new if patched else old)
            # Unicorn retains translated blocks after mem_write; this fixture
            # alternates original and patched code in the same emulator.
            e.uc.ctl_remove_cache(offset + 0x400000, offset + 0x400000 + len(new))
        e.write(SCRATCH, bytes(0x200))
        e.write(SCRATCH + 0x20, struct.pack('<I', SCRATCH + 0x1000 if name is not None else 0))
        if name is not None:
            e.write(SCRATCH + 0x1000, name.encode() + b'\0')
        e.write(SCRATCH + 0x168, struct.pack('<f', distance + 5000))
        e.write(STACK + 0x8018, struct.pack('<f', distance))
        e.uc.reg_write(UC_X86_REG_ESI, SCRATCH)
        e.uc.reg_write(UC_X86_REG_ESP, STACK + 0x8000)
        e.uc.reg_write(UC_X86_REG_FPCW, control)
        e.uc.emu_start(0x54320B, 0x54323E, count=200)
        self.assertEqual(e.uc.reg_read(UC_X86_REG_ESP), STACK + 0x8000)
        self.assertEqual(e.uc.reg_read(UC_X86_REG_FPCW), control)
        return bool(e.read(SCRATCH + 0x154, 1)[0])

    def check_hook_preserves_integer_state(self):
        e = self.emu
        for offset, _, new in self.patch.regions():
            e.write(offset + 0x400000, new)
        e.write(SCRATCH + 0x20, struct.pack('<I', SCRATCH + 0x1000))
        e.write(SCRATCH + 0x1000, b'Astr-B_mip\0')
        e.write(SCRATCH + 0x2000, struct.pack('<f', 100000))
        e.write(STUBS + 0x500, b'\xd9\x05' + struct.pack('<I', SCRATCH + 0x2000))
        e.uc.reg_write(UC_X86_REG_ESI, SCRATCH)
        e.uc.reg_write(UC_X86_REG_ESP, STACK + 0x8000)
        e.uc.emu_start(STUBS + 0x500, STUBS + 0x506, count=1)
        e.uc.reg_write(UC_X86_REG_EAX, 0x12345678)
        e.uc.reg_write(UC_X86_REG_EFLAGS, 0x247)
        e.uc.emu_start(self.patch.SITE, self.patch.SITE + 6, count=100)
        self.assertEqual(e.uc.reg_read(UC_X86_REG_EAX), 0x12345678)
        self.assertEqual(e.uc.reg_read(UC_X86_REG_EFLAGS), 0x247)
        self.assertEqual(e.uc.reg_read(UC_X86_REG_ESP), STACK + 0x8000)


class StationLod:
    """TestCase mixin: the original child LOD traversal (0x546BDE) with the extracted
    Hy_base1 thresholds and `patch`'s regions written in or not.

    Shared by test_station_detail and test_world_detail, which set `patch`.
    """
    patch = station_detail

    def setUp(self):
        self.emu = Emu(PE(SOURCE))
        data = (ROOT / 'work/2.9.2/export/AOAOBJECTS/Hy_base1.Gob').read_bytes()
        nodes = mesh_nodes(data)
        self.meshes = [(m, max((n for n in nodes if n['start'] < m['offset']), key=lambda n:n['start']))
                       for m in gob.parse(data)]
        self.assertEqual(len(self.meshes), 6)

    def select(self, name, size, enabled=True, control=0x7F):
        e = self.emu
        for off, old, new in self.patch.regions():
            e.write(off + 0x400000, new if enabled else old)
            e.uc.ctl_remove_cache(off + 0x400000, off + 0x400000 + len(new))
        e.write(SCRATCH, bytes(0x400))
        e.write(SCRATCH + 0x20, struct.pack('<I', SCRATCH + 0x1000 if name is not None else 0))
        if name is not None:
            e.write(SCRATCH + 0x1000, name.encode() + b'\0')
        e.write(SCRATCH + 0x17C, struct.pack('<f', size))
        e.write(SCRATCH + 0x234, struct.pack('<I', SCRATCH + 0x8000))
        e.write(SCRATCH + 0x33A, b'\1')
        for i, (_, node) in enumerate(self.meshes):
            child = SCRATCH + 0x2000 + i * 0x400
            link = SCRATCH + 0x8000 + i * 0x20
            e.write(child, bytes(0x400))
            e.write(child + 0x180, struct.pack('<2f', *node['screen_size_range']))
            e.write(link, bytes(0x20))
            e.write(link + 8, struct.pack('<I', link + 0x20 if i + 1 < len(self.meshes) else 0))
            e.write(link + 0x10, struct.pack('<I', child))
        e.uc.reg_write(UC_X86_REG_ESI, SCRATCH)
        e.uc.reg_write(UC_X86_REG_ESP, STACK + 0x8000)
        e.uc.reg_write(UC_X86_REG_FPCW, control)
        before = e.read(SCRATCH, 0x400)
        e.uc.emu_start(0x546BDE, 0x546C10, count=1000)
        self.assertEqual(e.read(SCRATCH, 0x400), before)  # real size and visibility remain intact
        self.assertEqual(e.uc.reg_read(UC_X86_REG_ESP), STACK + 0x8000)
        self.assertEqual(e.uc.reg_read(UC_X86_REG_FPCW), control)
        return [i for i in range(len(self.meshes)) if e.read(SCRATCH + 0x2000 + i * 0x400 + 0x152, 1) == b'\1']

    def check_finest_mesh_set_across_all_station_boundaries(self):
        sizes = (5, 199.99, 200, 200.01, 749.99, 750, 750.01, 1023.99, 1024, 1024.01, 4000)
        finest = self.select('Hy_base1', 4000, False)
        self.assertEqual(finest, [0, 1, 2])
        self.assertEqual(len(self.meshes[1][0]['faces']), 2933)
        self.assertNotEqual(self.select('Hy_base1', 749, False), finest)
        for control in (0x7F, 0x27F, 0x37F):
            for size in sizes:
                self.assertEqual(self.select('Hy_base1', size, control=control), finest)

    def check_hook_preserves_registers_and_flags(self):
        e = self.emu
        # Keep this entry-point probe cold: reusing the traversal's translated
        # blocks can skip Unicorn's new stop address inside an existing block.
        for off, _, new in self.patch.regions():
            e.write(off + 0x400000, new)
        e.write(SCRATCH + 0x20, struct.pack('<I', SCRATCH + 0x1000))
        e.write(SCRATCH + 0x1000, self.patch.MODEL)
        e.write(SCRATCH + 0x17C, struct.pack('<f', 200))
        e.uc.reg_write(UC_X86_REG_ESI, SCRATCH)
        e.uc.reg_write(UC_X86_REG_ESP, STACK + 0x8000)
        e.uc.reg_write(UC_X86_REG_EAX, 0x12345678)
        e.uc.reg_write(UC_X86_REG_EFLAGS, 0x247)
        e.uc.emu_start(self.patch.SITE, self.patch.SITE + 6, count=100)
        self.assertEqual(e.uc.reg_read(UC_X86_REG_ECX), 0x457A0000)
        self.assertEqual(e.uc.reg_read(UC_X86_REG_EAX), 0x12345678)
        self.assertEqual(e.uc.reg_read(UC_X86_REG_EFLAGS), 0x247)
        self.assertEqual(e.uc.reg_read(UC_X86_REG_ESP), STACK + 0x8000)


def probe(mixin, patch):
    """A set-up instance of a probe mixin for `patch`, for use inside another suite's test."""
    class Probe(mixin, unittest.TestCase):
        pass
    instance = Probe()
    instance.patch = patch
    instance.setUp()
    return instance
