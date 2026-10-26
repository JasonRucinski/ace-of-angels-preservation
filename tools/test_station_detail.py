"""Execute the original child LOD traversal with extracted station thresholds."""
import struct
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import station_detail as patch
import prepare_client
import gob2obj
from audit_object_lod import mesh_nodes
from emulate_codec import Emu, SCRATCH, STACK
from pe_util import PE
from unicorn.x86_const import (UC_X86_REG_ESI, UC_X86_REG_ESP, UC_X86_REG_EAX,
                               UC_X86_REG_ECX, UC_X86_REG_EFLAGS, UC_X86_REG_FPCW)

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'game/2.9.2/AOACLIENT.EXE.orig'


class StationDetailTests(unittest.TestCase):
    def setUp(self):
        self.emu = Emu(PE(SOURCE))
        data = (ROOT / 'work/2.9.2/export/AOAOBJECTS/Hy_base1.Gob').read_bytes()
        nodes = mesh_nodes(data)
        self.meshes = [(m, max((n for n in nodes if n['start'] < m['offset']), key=lambda n:n['start']))
                       for m in gob2obj.parse(data)]
        self.assertEqual(len(self.meshes), 6)

    def select(self, name, size, enabled=True, control=0x7F):
        e = self.emu
        for off, old, new in patch.regions():
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

    def test_finest_mesh_set_across_all_station_boundaries(self):
        sizes = (5, 199.99, 200, 200.01, 749.99, 750, 750.01, 1023.99, 1024, 1024.01, 4000)
        finest = self.select('Hy_base1', 4000, False)
        self.assertEqual(finest, [0, 1, 2])
        self.assertEqual(len(self.meshes[1][0]['faces']), 2933)
        self.assertNotEqual(self.select('Hy_base1', 749, False), finest)
        for control in (0x7F, 0x27F, 0x37F):
            for size in sizes:
                self.assertEqual(self.select('Hy_base1', size, control=control), finest)

    def test_other_models_short_names_and_null_unchanged(self):
        for name in (None, '', 'H', 'Hy_', 'Hy_base', 'Hy_base10', 'hy_base1', 'Astr-B_mip', 'Vermok', 'effect'):
            for size in (5, 200, 749, 750, 1024, 4000):
                self.assertEqual(self.select(name, size), self.select(name, size, False))

    def test_hook_preserves_registers_and_flags(self):
        e = self.emu
        # Keep this entry-point probe cold: reusing the traversal's translated
        # blocks can skip Unicorn's new stop address inside an existing block.
        for off, _, new in patch.regions():
            e.write(off + 0x400000, new)
        e.write(SCRATCH + 0x20, struct.pack('<I', SCRATCH + 0x1000))
        e.write(SCRATCH + 0x1000, patch.MODEL)
        e.write(SCRATCH + 0x17C, struct.pack('<f', 200))
        e.uc.reg_write(UC_X86_REG_ESI, SCRATCH)
        e.uc.reg_write(UC_X86_REG_ESP, STACK + 0x8000)
        e.uc.reg_write(UC_X86_REG_EAX, 0x12345678)
        e.uc.reg_write(UC_X86_REG_EFLAGS, 0x247)
        e.uc.emu_start(patch.SITE, patch.SITE + 6, count=100)
        self.assertEqual(e.uc.reg_read(UC_X86_REG_ECX), 0x457A0000)
        self.assertEqual(e.uc.reg_read(UC_X86_REG_EAX), 0x12345678)
        self.assertEqual(e.uc.reg_read(UC_X86_REG_EFLAGS), 0x247)
        self.assertEqual(e.uc.reg_read(UC_X86_REG_ESP), STACK + 0x8000)

    def test_install_preserve_and_exact_undo(self):
        with tempfile.TemporaryDirectory() as folder:
            exe = Path(folder) / 'AOACLIENT.EXE'
            exe.write_bytes(SOURCE.read_bytes())
            prepare_client.prepare(exe, experimental_solids=True)
            before = exe.read_bytes()
            patch.install(exe)
            after = exe.read_bytes()
            self.assertEqual(prepare_client.configure(after), after)
            self.assertIn(patch.NAME, prepare_client.check(exe, require_assets=False)['patches'])
            patch.install(exe)
            self.assertEqual(exe.read_bytes(), after)
            patch.install(exe, undo=True)
            self.assertEqual(exe.read_bytes(), before)
            allowed = {i for off, old, _ in patch.regions() for i in range(off, off + len(old))}
            self.assertTrue(all(a == b or i in allowed for i, (a, b) in enumerate(zip(before, after))))

    def test_partial_corruption_and_backup_rejection(self):
        before = prepare_client.configure(SOURCE.read_bytes(), experimental_solids=True)
        after = prepare_client.configure(before, experimental_station_detail=True)
        for offset in (patch.SITE - 0x400000, patch.CAVE - 0x400000, 0x12345):
            broken = bytearray(after)
            broken[offset] ^= 1
            with self.assertRaises(ValueError):
                prepare_client.inspect(bytes(broken))
        partial = bytearray(before)
        off, _, new = patch.regions()[0]
        partial[off:off + len(new)] = new
        with self.assertRaises(ValueError):
            patch.configure(bytes(partial))
        with tempfile.TemporaryDirectory() as folder:
            exe = Path(folder) / 'AOACLIENT.EXE'
            exe.write_bytes(before)
            exe.with_suffix('.EXE.before-station-detail').write_bytes(b'wrong backup')
            with self.assertRaises(ValueError):
                patch.install(exe)
            self.assertEqual(exe.read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
