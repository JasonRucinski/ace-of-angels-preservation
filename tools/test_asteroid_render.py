"""Original-x86 distance-gate regression; no game launch or GPU claim."""
import struct
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import asteroid_render as patch
import prepare_client
from emulate_codec import Emu, SCRATCH, STACK, STUBS
from pe_util import PE
from unicorn.x86_const import (UC_X86_REG_ESI, UC_X86_REG_ESP, UC_X86_REG_EAX,
                               UC_X86_REG_EFLAGS, UC_X86_REG_FPCW)

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'game/2.9.2/AOACLIENT.EXE.orig'


class AsteroidRenderTests(unittest.TestCase):
    def setUp(self):
        self.emu = Emu(PE(SOURCE))

    def gate(self, name, distance, patched=True, control=0x7F):
        e = self.emu
        for offset, old, new in patch.regions():
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
        e = self.emu
        for offset, _, new in patch.regions():
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
        e.uc.emu_start(patch.SITE, patch.SITE + 6, count=100)
        self.assertEqual(e.uc.reg_read(UC_X86_REG_EAX), 0x12345678)
        self.assertEqual(e.uc.reg_read(UC_X86_REG_EFLAGS), 0x247)
        self.assertEqual(e.uc.reg_read(UC_X86_REG_ESP), STACK + 0x8000)

    def test_exact_undo_idempotence_and_corruption_rejection(self):
        before = prepare_client.configure(SOURCE.read_bytes())
        after = prepare_client.configure(before, experimental_asteroids=True)
        self.assertEqual(patch.configure(after, False), before)
        self.assertEqual(prepare_client.configure(after), after)
        self.assertIn(patch.NAME, prepare_client.inspect(after)['patches'])
        for offset in (patch.SITE - 0x400000, patch.CAVE - 0x400000, 0x12345):
            broken = bytearray(after)
            broken[offset] ^= 1
            with self.assertRaises(ValueError):
                prepare_client.inspect(bytes(broken))
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
            prepare_client.prepare(exe)
            before = exe.read_bytes()
            prepare_client.prepare(exe, experimental_asteroids=True)
            self.assertIn(patch.NAME, prepare_client.check(exe, require_assets=False)['patches'])
            prepare_client.prepare(exe, experimental_asteroids=False)
            self.assertEqual(exe.read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
