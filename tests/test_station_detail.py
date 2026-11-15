"""Execute the original child LOD traversal with extracted station thresholds."""
import tempfile
import unittest
from pathlib import Path

from aoa.client.patches import station_detail as patch
from aoa.client import prepare
from tests.support_emulation import SOURCE, StationLod
from aoa.client.patches import base as patching
from tests.support_patches import triples


class StationDetailTests(StationLod, unittest.TestCase):
    def test_finest_mesh_set_across_all_station_boundaries(self):
        self.check_finest_mesh_set_across_all_station_boundaries()

    def test_other_models_short_names_and_null_unchanged(self):
        for name in (None, '', 'H', 'Hy_', 'Hy_base', 'Hy_base10', 'hy_base1', 'Astr-B_mip', 'Vermok', 'effect'):
            for size in (5, 200, 749, 750, 1024, 4000):
                self.assertEqual(self.select(name, size), self.select(name, size, False))

    def test_hook_preserves_registers_and_flags(self):
        self.check_hook_preserves_registers_and_flags()

    def test_install_preserve_and_exact_undo(self):
        with tempfile.TemporaryDirectory() as folder:
            exe = Path(folder) / 'AOACLIENT.EXE'
            exe.write_bytes(SOURCE.read_bytes())
            prepare.prepare(exe, {"experimental_solids": True})
            before = exe.read_bytes()
            prepare.prepare(exe, {"experimental_station_detail": True})
            after = exe.read_bytes()
            self.assertEqual(prepare.configure(after), after)
            self.assertIn(patch.NAME, prepare.check(exe, require_assets=False)['patches'])
            prepare.prepare(exe, {"experimental_station_detail": True})
            self.assertEqual(exe.read_bytes(), after)
            prepare.prepare(exe, {"experimental_station_detail": False})
            self.assertEqual(exe.read_bytes(), before)
            allowed = {i for off, old, _ in triples(patch.PATCH) for i in range(off, off + len(old))}
            self.assertTrue(all(a == b or i in allowed for i, (a, b) in enumerate(zip(before, after))))
            # prepare's backup and record are the only undo; no per-tool side files.
            self.assertEqual(sorted(p.name for p in Path(folder).iterdir()),
                             ['AOACLIENT.EXE', 'AOACLIENT.EXE.setup-original', '_client_setup.json'])

    def test_partial_corruption_rejection(self):
        before = prepare.configure(SOURCE.read_bytes(), experimental_solids=True)
        after = prepare.configure(before, experimental_station_detail=True)
        for offset in (patch.SITE - 0x400000, patch.CAVE - 0x400000, 0x12345):
            broken = bytearray(after)
            broken[offset] ^= 1
            with self.assertRaises(ValueError):
                prepare.inspect(bytes(broken))
        partial = bytearray(before)
        off, _, new = triples(patch.PATCH)[0]
        partial[off:off + len(new)] = new
        with self.assertRaises(ValueError):
            patching.apply(patch.PATCH, bytes(partial), True)


if __name__ == '__main__':
    unittest.main()
