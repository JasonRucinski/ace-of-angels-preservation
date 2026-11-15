"""World model gate emulation and exact migration/rollback; no GPU claim."""
import tempfile
import unittest
from pathlib import Path

from aoa.client.patches import asteroid_render
from aoa.client.patches import solid_world_render as patch
from aoa.client import prepare
from tests import support_emulation as support
from aoa.analysis.pe_util import Disasm, PE
from aoa.client.patches import base as patching


class SolidWorldRenderTests(unittest.TestCase):
    def test_world_model_cutoff_and_integer_state(self):
        probe = support.probe(support.AsteroidGate, patch)
        for control in (0x7F, 0x27F, 0x37F):
            for name in ('Astr-B_mip', 'Base', 'Vermok', None):
                for distance in (100, 60999, 61000, 61001, 100000, 899999, 900000, 900001):
                    self.assertEqual(probe.gate(name, distance, False, control), distance < 61000)
                    self.assertEqual(probe.gate(name, distance, True, control), distance < 900000)
        probe.check_hook_preserves_integer_state()

    def test_scope_is_model_visibility_not_global_billboard_setting(self):
        pe = PE(support.SOURCE)
        with tempfile.TemporaryDirectory() as directory:
            dis = Disasm(pe, Path(directory) / 'code.pkl')
            self.assertEqual(dis.refs_to_func(0x543000), [0x546BCE])
            self.assertEqual(dis.refs_to_func(0x546B20), [0x49BCC2, 0x4A4E36])
        before = prepare.configure(pe.data)
        after = prepare.configure(before, experimental_solids=True)
        # Every byte outside this one comparison is identical, including all
        # sprite/effect submission, cached-image code, LOD and depth settings.
        self.assertEqual(before[:(patch.SITE - 0x400000)], after[:(patch.SITE - 0x400000)])
        self.assertEqual(before[(patch.SITE - 0x400000) + 6:], after[(patch.SITE - 0x400000) + 6:])

    def test_legacy_migration_preservation_and_exact_undo(self):
        clean = prepare.configure(support.SOURCE.read_bytes())
        legacy = prepare.configure(clean, experimental_asteroids=True)
        broad = prepare.configure(legacy, experimental_solids=True)
        self.assertEqual(broad, prepare.configure(clean, experimental_solids=True))
        self.assertEqual(prepare.configure(broad), broad)
        self.assertEqual(patching.apply(patch.PATCH, broad, False), clean)
        self.assertEqual(prepare.configure(broad, experimental_solids=False,
                                                experimental_asteroids=True), legacy)
        self.assertIn(patch.NAME, prepare.inspect(broad)['patches'])
        self.assertNotIn(asteroid_render.NAME, prepare.inspect(broad)['patches'])
        self.assertEqual(prepare.configure(broad, experimental_asteroids=True), legacy)
        with self.assertRaisesRegex(ValueError, f"{asteroid_render.NAME} and {patch.NAME}"):
            prepare.configure(clean, experimental_asteroids=True, experimental_solids=True)

    def test_corruption_and_abandoned_cave_rejected(self):
        broad = prepare.configure(support.SOURCE.read_bytes(), experimental_solids=True)
        for offset in ((patch.SITE - 0x400000), asteroid_render.CAVE - 0x400000, 0x12345):
            broken = bytearray(broad)
            broken[offset] ^= 1
            with self.assertRaises(ValueError):
                prepare.inspect(bytes(broken))

    def test_install_reapply_and_undo_turns_it_off(self):
        with tempfile.TemporaryDirectory() as directory:
            exe = Path(directory) / 'AOACLIENT.EXE'
            exe.write_bytes(support.SOURCE.read_bytes())
            prepare.prepare(exe, {"experimental_asteroids": True})
            before = exe.read_bytes()
            prepare.prepare(exe, {"experimental_solids": True})
            after = exe.read_bytes()
            prepare.prepare(exe, {"experimental_solids": True})
            self.assertEqual(exe.read_bytes(), after)
            self.assertIn(patch.NAME, prepare.check(exe, require_assets=False)['patches'])
            # Undo turns solid-world off; the asteroid-only patch it replaced stays off.
            off = prepare.configure(before, experimental_asteroids=False)
            prepare.prepare(exe, {"experimental_solids": False})
            self.assertEqual(exe.read_bytes(), off)
            prepare.prepare(exe, {"experimental_solids": False})
            self.assertEqual(exe.read_bytes(), off)
            self.assertEqual(sorted(p.name for p in Path(directory).iterdir()),
                             ['AOACLIENT.EXE', 'AOACLIENT.EXE.setup-original', '_client_setup.json'])


if __name__ == '__main__':
    unittest.main()
