"""Original-x86 distance-gate regression; no game launch or GPU claim."""
import tempfile
import unittest
from pathlib import Path

from aoa.client.patches import asteroid_render as patch
from aoa.client import prepare
from tests.support_emulation import AsteroidGate, SOURCE


class AsteroidRenderTests(AsteroidGate, unittest.TestCase):
    def test_original_handoff_and_extended_asteroid_mesh_range(self):
        for control in (0x7F, 0x27F, 0x37F):
            for name in ('Astr-A__mip', 'Astr-B_mip', 'Astr-C_mip', 'Astr_06-A'):
                for distance in (100, 60999, 61000, 61001, 100000, 500000, 899999, 900000, 900001):
                    with self.subTest(name=name, distance=distance, control=control):
                        self.assertEqual(self.gate(name, distance, False, control), distance < 61000)
                        self.assertEqual(self.gate(name, distance, True, control), distance < 900000)

    def test_other_models_and_short_names_keep_original_cutoff(self):
        for name in (None, '', 'A', 'As', 'Ast', 'Astr', 'Astronaut', 'asteroid_a', 'Base', 'Vermok'):
            for distance in (60999, 61000, 100000, 900000):
                self.assertEqual(self.gate(name, distance), self.gate(name, distance, False))

    def test_hook_preserves_integer_state(self):
        self.check_hook_preserves_integer_state()

    def test_exact_undo_idempotence_and_corruption_rejection(self):
        before = prepare.configure(SOURCE.read_bytes())
        after = prepare.configure(before, experimental_asteroids=True)
        self.assertEqual(patch.configure(after, False), before)
        self.assertEqual(prepare.configure(after), after)
        self.assertIn(patch.NAME, prepare.inspect(after)['patches'])
        for offset in (patch.SITE - 0x400000, patch.CAVE - 0x400000, 0x12345):
            broken = bytearray(after)
            broken[offset] ^= 1
            with self.assertRaises(ValueError):
                prepare.inspect(bytes(broken))
        partial = bytearray(before)
        offset, _, new = patch.regions()[0]
        partial[offset:offset + len(new)] = new
        with self.assertRaises(ValueError):
            patch.configure(bytes(partial))
        allowed = {i for offset, old, _ in patch.regions() for i in range(offset, offset + len(old))}
        self.assertTrue(all(a == b or i in allowed for i, (a, b) in enumerate(zip(before, after))))

    def test_preparation_transaction_and_undo(self):
        with tempfile.TemporaryDirectory() as folder:
            exe = Path(folder) / 'AOACLIENT.EXE'
            exe.write_bytes(SOURCE.read_bytes())
            prepare.prepare(exe)
            before = exe.read_bytes()
            prepare.prepare(exe, experimental_asteroids=True)
            self.assertIn(patch.NAME, prepare.check(exe, require_assets=False)['patches'])
            prepare.prepare(exe, experimental_asteroids=False)
            self.assertEqual(exe.read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
