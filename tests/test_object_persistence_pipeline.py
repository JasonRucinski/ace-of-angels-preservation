"""Independent follow-through checks for the distant-object patch review.

Extend the original fixture through the function return, recursive child
visibility, the renderer's drawable predicate and dynamic projection setup.
No real Direct3D device or GPU is exercised.
"""
import math
import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from emulate_codec import SCRATCH, STACK, STOP
from test_object_persistence import GroupProbe
from unicorn.x86_const import (UC_X86_REG_EBX, UC_X86_REG_ESI, UC_X86_REG_EDI,
                               UC_X86_REG_EBP, UC_X86_REG_ESP, UC_X86_REG_EIP,
                               UC_X86_REG_FPCW, UC_X86_REG_FPSW, UC_X86_REG_EDX)


class PersistencePipelineTests(unittest.TestCase):
    def fixture(self, patched):
        e = GroupProbe(patched).emu
        node, camera, context = SCRATCH, SCRATCH + 0xA000, SCRATCH + 0xB000
        e.write(node, bytes(0x400))
        e.write(node + 4, struct.pack('<I', 2))
        e.write(node + 0x10, struct.pack('<I', SCRATCH + 0x7000))
        e.write(node + 0x150, b'\1\0\1')
        e.write(node + 0x234, struct.pack('<I', SCRATCH + 0x8000))
        e.write(node + 0x33A, b'\1')
        for i, limits in enumerate(((5., 100.), (100., 4096.))):
            child, link = SCRATCH + 0x1000 + i * 0x400, SCRATCH + 0x8000 + i * 0x20
            e.write(child, bytes(0x400))
            e.write(child + 0x134, struct.pack('<I', 1))
            e.write(child + 0x144, struct.pack('<I', node))
            e.write(child + 0x150, b'\1\0\0')
            e.write(child + 0x180, struct.pack('<2f', *limits))
            e.write(SCRATCH + 0x7000 + i * 8, struct.pack('<2I', child, 0x51870002))
            e.write(link, bytes(0x20))
            e.write(link + 8, struct.pack('<I', link + 0x20 if i == 0 else 0))
            e.write(link + 0x10, struct.pack('<I', child))
        e.write(camera, bytes(0x100))
        e.write(camera + 0x70, struct.pack('<3f', 0, 0, 1))
        e.write(camera + 0xD0, struct.pack('<3f', 13, -7, 91))
        e.write(node + 0xFC, struct.pack('<3f', 23, 41, -72))
        e.write(context + 8, struct.pack('<f', 960))
        return e, node, camera, context

    def update(self, fixture, distance, radius, control):
        e, node, camera, context = fixture
        e.write(node + 0xAC, struct.pack('<3f', 0, 0, distance))
        e.write(node + 0x164, struct.pack('<f', radius))
        saved = {UC_X86_REG_EBX: 0x11223344, UC_X86_REG_ESI: 0x22334455,
                 UC_X86_REG_EDI: 0x33445566, UC_X86_REG_EBP: 0x44556677}
        for reg, value in saved.items():
            e.uc.reg_write(reg, value)
        e.uc.reg_write(UC_X86_REG_FPCW, control)
        e.thiscall(0x546B20, node, camera, context, 0)
        self.assertEqual(e.uc.reg_read(UC_X86_REG_EIP), STOP)
        self.assertEqual(e.uc.reg_read(UC_X86_REG_ESP), STACK + 0xF0000 + 16)
        for reg, value in saved.items():
            self.assertEqual(e.uc.reg_read(reg), value)
        self.assertEqual(e.uc.reg_read(UC_X86_REG_FPCW), control)
        self.assertEqual(e.uc.reg_read(UC_X86_REG_FPSW) & 0x3800, 0)  # empty x87 stack
        drawn = [bool(e.thiscall(0x542990, SCRATCH + 0x1000 + i * 0x400)) for i in range(2)]
        return drawn, e.read(node + 0x32C, 12)  # original relative-motion outputs

    def test_complete_return_reappearance_and_recursive_drawability(self):
        for control in (0x7F, 0x27F, 0x37F):
            original, patched = self.fixture(False), self.fixture(True)
            # Reuse each tree: stale child visibility/LOD can only appear when
            # an object changes state, not in freshly zeroed per-case fixtures.
            cases = [(1000, 100, [False, True]), (100_000, 100, [True, False]),
                     (400_000, 100, [False, False]), (100_000, 100, [True, False]),
                     (-100_000, 100, [False, False]), (1000, 100, [False, True]),
                     (4_500_000, 1500, [True, False]),
                     (4_501_500, 1500, [False, False])]
            for distance, radius, expected in cases * 4:
                with self.subTest(control=control, distance=distance, radius=radius):
                    _, old_motion = self.update(original, distance, radius, control)
                    drawn, new_motion = self.update(patched, distance, radius, control)
                    self.assertEqual(drawn, expected)
                    self.assertEqual(old_motion, new_motion)

    def test_renderer_extends_projection_to_distant_terrain(self):
        for control in (0x7F, 0x27F, 0x37F):
            fixture = self.fixture(True)
            e, node, _, _ = fixture
            self.update(fixture, 4_500_000, 1500, control)
            graphics, terrain = SCRATCH + 0x20000, SCRATCH + 0x30000
            e.write(graphics, bytes(0x3000))
            e.write(graphics + 0x2B24, struct.pack('<2f', 100_000_000, 0))
            e.write(terrain, bytes(0x360))
            e.write(terrain + 0x19C, struct.pack('<I', node))
            e.uc.reg_write(UC_X86_REG_ESI, terrain)
            e.uc.reg_write(UC_X86_REG_EDX, terrain)
            e.uc.reg_write(UC_X86_REG_EDI, graphics)
            # Original terrain-list contribution to the mesh pass clip range.
            e.uc.emu_start(0x438CD7, 0x438D47, count=1000)
            far = struct.unpack('<f', e.read(graphics + 0x2B28, 4))[0]
            self.assertEqual(far, 4_501_500)
            # The real mesh pass calls this setter immediately before drawing.
            projection = graphics + 0x178
            e.write(projection + 4, struct.pack('<I', 1))
            e.write(projection + 0x10, bytes(4))  # no COM device; retain matrix
            e.write(projection + 0x12C, struct.pack('<2I', 1920, 1080))
            e.write(projection + 0x134, struct.pack('<f', math.pi / 2))
            e.thiscall(0x554340, projection, 0x41200000,
                       struct.unpack('<I', struct.pack('<f', far))[0])
            matrix = struct.unpack('<16f', e.read(projection + 0x144, 64))
            self.assertTrue(all(math.isfinite(x) for x in matrix))
            self.assertEqual(struct.unpack('<f', e.read(projection + 0x140, 4))[0], far)
            z = 4_500_000.
            depth = (z * matrix[10] + matrix[14]) / (z * matrix[11] + matrix[15])
            self.assertLessEqual(depth, 1.0000001)
            self.assertGreater(depth, 0)


if __name__ == '__main__':
    unittest.main()
