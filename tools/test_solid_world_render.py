"""World model gate emulation and exact migration/rollback; no GPU claim."""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch as mock_patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import asteroid_render
import solid_world_render as patch
import prepare_client
import test_asteroid_render as fixture
from pe_util import Disasm, PE


class SolidWorldRenderTests(unittest.TestCase):
    def test_world_model_cutoff_and_integer_state(self):
        probe = fixture.AsteroidRenderTests()
        probe.setUp()
        with mock_patch.object(fixture, 'patch', patch):
            for control in (0x7F, 0x27F, 0x37F):
                for name in ('Astr-B_mip', 'Base', 'Vermok', None):
                    for distance in (100, 60999, 61000, 61001, 100000, 899999, 900000, 900001):
                        self.assertEqual(probe.gate(name, distance, False, control), distance < 61000)
                        self.assertEqual(probe.gate(name, distance, True, control), distance < 900000)
            probe.test_hook_preserves_integer_state()

    def test_scope_is_model_visibility_not_global_billboard_setting(self):
        pe = PE(fixture.SOURCE)
        with tempfile.TemporaryDirectory() as directory:
            dis = Disasm(pe, Path(directory) / 'code.pkl')
            self.assertEqual(dis.refs_to_func(0x543000), [0x546BCE])
            self.assertEqual(dis.refs_to_func(0x546B20), [0x49BCC2, 0x4A4E36])
        before = prepare_client.configure(pe.data)
        after = prepare_client.configure(before, experimental_solids=True)
        # Every byte outside this one comparison is identical, including all
        # sprite/effect submission, cached-image code, LOD and depth settings.
        self.assertEqual(before[:patch.OFFSET], after[:patch.OFFSET])
        self.assertEqual(before[patch.OFFSET + 6:], after[patch.OFFSET + 6:])

    def test_legacy_migration_preservation_and_exact_undo(self):
        clean = prepare_client.configure(fixture.SOURCE.read_bytes())
        legacy = prepare_client.configure(clean, experimental_asteroids=True)
        broad = prepare_client.configure(legacy, experimental_solids=True)
        self.assertEqual(broad, prepare_client.configure(clean, experimental_solids=True))
        self.assertEqual(prepare_client.configure(broad), broad)
        self.assertEqual(patch.configure(broad, False), clean)
        self.assertEqual(prepare_client.configure(broad, experimental_solids=False,
                                                experimental_asteroids=True), legacy)
        self.assertIn(patch.NAME, prepare_client.inspect(broad)['patches'])
        self.assertNotIn(asteroid_render.NAME, prepare_client.inspect(broad)['patches'])
        with self.assertRaises(ValueError):
            prepare_client.configure(broad, experimental_asteroids=True)

    def test_corruption_and_abandoned_cave_rejected(self):
        broad = prepare_client.configure(fixture.SOURCE.read_bytes(), experimental_solids=True)
        for offset in (patch.OFFSET, asteroid_render.CAVE - 0x400000, 0x12345):
            broken = bytearray(broad)
            broken[offset] ^= 1
            with self.assertRaises(ValueError):
                prepare_client.inspect(bytes(broken))

    def test_install_reapply_undo_and_backup_guard(self):
        with tempfile.TemporaryDirectory() as directory:
            exe = Path(directory) / 'AOACLIENT.EXE'
            exe.write_bytes(fixture.SOURCE.read_bytes())
            prepare_client.prepare(exe, experimental_asteroids=True)
            before = exe.read_bytes()
            patch.install(exe)
            after = exe.read_bytes()
            patch.install(exe)
            self.assertEqual(exe.read_bytes(), after)
            self.assertIn(patch.NAME, prepare_client.check(exe, require_assets=False)['patches'])
            patch.install(exe, undo=True)
            self.assertEqual(exe.read_bytes(), before)
            patch.install(exe, undo=True)
            self.assertEqual(exe.read_bytes(), before)
            backup = exe.with_suffix('.EXE.before-solid-world-render')
            backup.write_bytes(backup.read_bytes()[:-1])
            with self.assertRaises(ValueError):
                patch.install(exe)
            self.assertEqual(exe.read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
