"""Original world-model LOD execution across the complete parsed asset set."""
import struct
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch as mock_patch

from aoa.client import prepare
from aoa.client.patches import world_detail as patch
from aoa.client.patches import station_detail
from tests import support_emulation as support
from aoa.emulation.emu import SCRATCH, STACK
from aoa.paths import ROOT
from aoa.maps.lod import audit
from aoa.client.patches import base as patching
from tests.support_patches import needs_export, needs_game, triples
from unicorn.x86_const import UC_X86_REG_ECX, UC_X86_REG_ESP


@needs_game
@needs_export
class WorldDetailTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.assets = audit(ROOT / 'work/2.9.2/export/AOAOBJECTS')['models']
        assert len(cls.assets) == 154

    def test_all_models_select_exact_closest_mesh_set(self):
        probe = support.probe(support.StationLod, patch)
        for model in self.assets:
            probe.meshes = [(None, mesh) for mesh in model['meshes']]
            finest = probe.select(model['model'], 4000, False)
            self.assertTrue(finest, model['model'])
            boundaries = {v for mesh in model['meshes'] for v in mesh['screen_size_range']}
            sizes = sorted({5., 4000.} | {v + d for v in boundaries for d in (-.01, 0, .01) if 5 <= v+d <= 4000})
            for size in sizes:
                with self.subTest(model=model['model'], size=size):
                    self.assertEqual(probe.select(model['model'], size), finest)

    def test_group_visibility_does_not_fall_back_below_authored_minimum(self):
        probe = support.probe(support.StationLod, patch)
        dock = next(m for m in self.assets if m['model'] == 'newdock')
        probe.meshes = [(None, mesh) for mesh in dock['meshes']]
        for enabled, expected in ((False, (200., 4096.)), (True, (5., 4096.))):
            probe.select('newdock', 191, enabled)
            e = probe.emu
            e.uc.reg_write(UC_X86_REG_ECX, SCRATCH)
            e.uc.reg_write(UC_X86_REG_ESP, STACK + 0x8000)
            e.uc.emu_start(0x546B20, 0x546BC2, count=1000)
            self.assertEqual(struct.unpack('<2f', e.read(SCRATCH + 0x180, 8)), expected)
            for size in (191, 197, 214, 223):
                result = e.thiscall(0x542920, SCRATCH, struct.unpack('<I', struct.pack('<f', size))[0])
                self.assertEqual(bool(result), enabled or size >= 200)
            for size in (4.99, 4096):
                self.assertFalse(e.thiscall(0x542920, SCRATCH, struct.unpack('<I', struct.pack('<f', size))[0]))

    def test_station_precision_and_integer_state(self):
        # Reuse the extracted station's real multi-part LOD thresholds.
        probe = support.probe(support.StationLod, patch)
        probe.check_finest_mesh_set_across_all_station_boundaries()
        # Fresh emulator avoids translated stop-address artifacts.
        probe.setUp()
        # Fixture's model-name setup is irrelevant to this unfiltered hook.
        with mock_patch.object(patch, 'MODEL', b'anything\0', create=True):
            probe.check_hook_preserves_registers_and_flags()

    def test_migration_preservation_and_undo_turns_it_off(self):
        with tempfile.TemporaryDirectory() as folder:
            exe = Path(folder) / 'AOACLIENT.EXE'
            exe.write_bytes(support.SOURCE.read_bytes())
            prepare.prepare(exe, {"experimental_solids": True, "experimental_station_detail": True})
            before = exe.read_bytes()
            prepare.prepare(exe, {"experimental_world_detail": True})
            after = exe.read_bytes()
            self.assertEqual(prepare.configure(after), after)
            self.assertIn(patch.NAME, prepare.check(exe, require_assets=False)['patches'])
            self.assertNotIn(station_detail.NAME, prepare.inspect(after)['patches'])
            prepare.prepare(exe, {"experimental_world_detail": True})
            self.assertEqual(exe.read_bytes(), after)
            # Undo turns world detail off; the station-only patch it replaced stays off.
            prepare.prepare(exe, {"experimental_world_detail": False})
            self.assertEqual(exe.read_bytes(), prepare.configure(before, experimental_station_detail=False))
            self.assertEqual(sorted(p.name for p in Path(folder).iterdir()),
                             ['AOACLIENT.EXE', 'AOACLIENT.EXE.setup-original', '_client_setup.json'])

    def test_byte_scope_and_corruption_rejection(self):
        before = prepare.configure(support.SOURCE.read_bytes(), experimental_solids=True)
        after = prepare.configure(before, experimental_world_detail=True)
        allowed = {i for off, old, _ in triples(patch.PATCH) for i in range(off, off + len(old))}
        self.assertTrue(all(a == b or i in allowed for i, (a, b) in enumerate(zip(before, after))))
        for offset in ((patch.SITE - 0x400000), patch.RANGE_SITE - 0x400000, station_detail.CAVE - 0x400000, 0x12345):
            broken = bytearray(after)
            broken[offset] ^= 1
            with self.assertRaises(ValueError):
                prepare.inspect(bytes(broken))
        partial = bytearray(before)
        partial[(patch.SITE - 0x400000):(patch.SITE - 0x400000) + 6] = patch.PATCHED
        with self.assertRaises(ValueError):
            patching.apply(patch.PATCH, bytes(partial), True)
        self.assertNotIn(patch.NAME, prepare.inspect(
            prepare.configure(after, experimental_station_detail=True))['patches'])
        with self.assertRaisesRegex(ValueError, f"{station_detail.NAME} and {patch.NAME}"):
            prepare.configure(before, experimental_station_detail=True, experimental_world_detail=True)


if __name__ == '__main__':
    unittest.main()
