"""Original x86 LOD selection and extracted asset checks; no GUI or process input."""
import math
import hashlib
import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from audit_object_lod import audit
from emulate_codec import Emu, SCRATCH, STACK
from pe_util import PE
from patch_client import PRISTINE_292
from unicorn.x86_const import UC_X86_REG_ESI, UC_X86_REG_ESP, UC_X86_REG_FPCW

ROOT = Path(__file__).resolve().parents[1]


class ObjectLodTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.assets = audit(ROOT / 'work/2.9.2/export/AOAOBJECTS')
        if cls.assets['mesh_models'] != 154:
            raise AssertionError('Expected the complete extracted 2.9.2 mesh asset set')
        cls.models = {m['model']: m for m in cls.assets['models']}

    def setUp(self):
        path = ROOT / 'game/2.9.2/AOACLIENT.EXE.orig'
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), PRISTINE_292)
        self.emu = Emu(PE(path))
        self.emu.uc.reg_write(UC_X86_REG_FPCW, 0x7F)

    def selected(self, mesh, size, cached=False):
        self.emu.write(SCRATCH + 0x17C, struct.pack('<3f', size, *mesh['screen_size_range']))
        arg = struct.unpack('<I', struct.pack('<f', -1 if cached else size))[0]
        return self.emu.thiscall(0x542920, SCRATCH, arg)

    def test_asteroid_thresholds_have_one_selected_mesh(self):
        self.assertEqual(len(self.assets['asteroid_models']), 10)
        for name in self.assets['asteroid_models']:
            meshes = self.models[name]['meshes']
            boundaries = {x for m in meshes for x in m['screen_size_range']}
            sizes = sorted({5., 4000.} | {x+d for x in boundaries for d in (-0.01, 0, 0.01) if 5 <= x+d <= 4000})
            for size in sizes:
                for cached in (False, True):
                    with self.subTest(model=name, size=size, cached=cached):
                        self.assertEqual(sum(self.selected(m, size, cached) for m in meshes), 1)
            for size in (0, 4.99, 4096):
                self.assertEqual(sum(self.selected(m, size) for m in meshes), 0)

    def test_asteroid_switches_preserve_geometry_and_placement(self):
        for name in self.assets['asteroid_models']:
            model = self.models[name]
            with self.subTest(model=name):
                self.assertTrue(model['all_mesh_geometry_identical'])
                self.assertEqual(len({tuple(m['node_matrix']) for m in model['meshes']}), 1)
                self.assertEqual(len({tuple(m['center']) for m in model['meshes']}), 1)

    def test_ship_lod_offsets_cancel_after_node_transform(self):
        # Raw Vermok LOD meshes are separated by ~76 and ~151 units in X.
        # The serialized transforms place them back at the same origin.
        for name in ('Vermok', 'Vasa Chovo'):
            with self.subTest(model=name):
                levels = self.models[name]['lod_levels']
                self.assertEqual(len(levels), 3)
                for level in levels[1:]:
                    self.assertLess(math.dist(levels[0]['center'], level['center']), 0.001)

    def test_original_projected_size_clamps_before_lod(self):
        # Run the original arithmetic slice, including its compare/branch/store.
        # This deliberately excludes frustum tests and scene traversal.
        context = SCRATCH + 0x1000
        sp = STACK + 0x8000
        self.emu.write(context + 8, struct.pack('<f', 960))
        self.emu.write(sp + 0x1C, struct.pack('<I', context))
        for distance in (0.001, 1, 48, 100, 1000, 10000):
            self.emu.write(SCRATCH + 0x164, struct.pack('<2f', 100, distance))
            self.emu.uc.reg_write(UC_X86_REG_ESI, SCRATCH)
            self.emu.uc.reg_write(UC_X86_REG_ESP, sp)
            self.emu.uc.emu_start(0x54310D, 0x54315E, count=100)
            size = struct.unpack('<f', self.emu.read(SCRATCH + 0x17C, 4))[0]
            self.assertAlmostEqual(size, min(4000, 200*960/distance), places=3)
            for name in self.assets['asteroid_models']:
                self.assertEqual(sum(self.selected(m, size) for m in self.models[name]['meshes']), 1)


if __name__ == '__main__':
    unittest.main()
