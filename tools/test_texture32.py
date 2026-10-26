"""Texture-loader depth selection in original x86; no game launch or GPU claim."""
import struct
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import prepare_client
import texture32 as patch
from emulate_codec import Emu, SCRATCH, STACK
from pe_util import PE
from unicorn import UC_HOOK_CODE
from unicorn.x86_const import (UC_X86_REG_EAX, UC_X86_REG_ECX, UC_X86_REG_EDX, UC_X86_REG_EDI,
                               UC_X86_REG_ESI, UC_X86_REG_ESP, UC_X86_REG_EIP)

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'game/2.9.2/AOACLIENT.EXE.orig'
DONE, INVALID = 0x562AF9, 0x562AC4


class Texture32Tests(unittest.TestCase):
    def setUp(self):
        self.emu = Emu(PE(SOURCE))

    def run_to(self, start, stops, limit=200):
        e = self.emu

        def hook(uc, address, size, _):
            if address in stops:
                uc.emu_stop()
        handle = e.uc.hook_add(UC_HOOK_CODE, hook)
        try:
            e.uc.emu_start(start, 0, count=limit)
        finally:
            e.uc.hook_del(handle)
        return e.uc.reg_read(UC_X86_REG_EIP)

    def select(self, bpp, patched, preset=0):
        """Run 0x562AA0..0x562AF9: the view's depth/alpha choice for one TGA."""
        e = self.emu
        for off, old, new in patch.regions():
            e.write(off + 0x400000, new if patched else old)
            e.uc.ctl_remove_cache(off + 0x400000, off + 0x400000 + len(old))
        e.write(SCRATCH, struct.pack('<4I', 0, preset, 0x1234, 0xFFFFFFFF))
        e.uc.reg_write(UC_X86_REG_EDI, SCRATCH)
        e.uc.reg_write(UC_X86_REG_EAX, bpp)
        e.uc.reg_write(UC_X86_REG_ESI, 256)
        e.uc.reg_write(UC_X86_REG_EDX, 0xDEAD)
        e.uc.reg_write(UC_X86_REG_ESP, STACK + 0x8000)
        stop = self.run_to(0x562AA0, {DONE, INVALID})
        self.assertEqual(e.uc.reg_read(UC_X86_REG_ESP), STACK + 0x8000)
        if stop == INVALID:
            return None
        self.assertEqual(stop, DONE)
        self.assertEqual(e.uc.reg_read(UC_X86_REG_EDX), 0)  # later call argument
        depth, alpha = struct.unpack('<2I', e.read(SCRATCH + 4, 8))
        if not preset:
            self.assertEqual(e.read(SCRATCH + 12, 1), b'\0')
        return depth, alpha

    def test_depth_selection_for_every_source_depth(self):
        expected = {16: ((16, 0), (16, 0)), 24: ((16, 0), (32, 0)), 32: ((16, 4), (32, 8))}
        for bpp in (0, 8, 15, 16, 17, 24, 31, 32, 33, 64):
            with self.subTest(bpp=bpp):
                original, patched = expected.get(bpp, (None, None))
                self.assertEqual(self.select(bpp, False), original)
                self.assertEqual(self.select(bpp, True), patched)

    def test_existing_view_depth_is_untouched(self):
        for bpp in (16, 24, 32):
            for preset in (16, 32):
                self.assertEqual(self.select(bpp, True, preset), self.select(bpp, False, preset))

    def alloc(self, depth, alpha):
        """Run AllocTexture's format dispatch at 0x5636F0; return (callee, args)."""
        e = self.emu
        e.write(STACK + 0x8000, bytes(0x80))
        e.write(STACK + 0x8024, struct.pack('<2I', 512, 256))  # ebx, ebp
        e.write(STACK + 0x8038, struct.pack('<I', 7))
        e.write(SCRATCH, bytes(0x40))
        e.uc.reg_write(UC_X86_REG_ECX, depth)
        e.uc.reg_write(UC_X86_REG_EAX, alpha)
        e.uc.reg_write(UC_X86_REG_EDI, 0)
        e.uc.reg_write(UC_X86_REG_ESI, SCRATCH)
        e.uc.reg_write(UC_X86_REG_ESP, STACK + 0x8000)
        target = self.run_to(0x5636F0, {0x554840, 0x554970})
        esp = e.uc.reg_read(UC_X86_REG_ESP)
        return target, struct.unpack('<4I', e.read(esp + 4, 16))

    def surface_depth(self, alpha):
        """0x554A15..0x554A31: alpha bits below 8 request 16-bit, else 32-bit."""
        e = self.emu
        e.write(STACK + 0x8000, bytes(0x100))
        e.write(STACK + 0x80A4, struct.pack('<I', alpha))
        e.uc.reg_write(UC_X86_REG_ESP, STACK + 0x8000)
        e.uc.emu_start(0x554A15, 0x554A35, count=20)
        return struct.unpack('<I', e.read(STACK + 0x800C, 4))[0]

    def test_allocator_creates_argb8888_for_new_views(self):
        self.assertEqual(self.alloc(16, 0), (0x554840, (512, 256, 16, 7)))
        self.assertEqual(self.alloc(16, 4), (0x554970, (512, 256, 4, 7)))
        self.assertEqual(self.alloc(32, 0), (0x554970, (512, 256, 8, 7)))
        self.assertEqual(self.alloc(32, 8), (0x554970, (512, 256, 8, 7)))
        self.assertEqual(self.surface_depth(4), 16)
        self.assertEqual(self.surface_depth(8), 32)

    def test_converters_for_32_bit_surfaces(self):
        pe = PE(SOURCE)
        # 32-bit surface table: 24-bit -> 0x558B80, 32-bit -> 0x558A20, 16-bit -> stub.
        self.assertEqual(pe.read_va(0x5557A2, 10), bytes.fromhex('c78560010000808b5500'))
        self.assertEqual(pe.read_va(0x5557B8, 10), bytes.fromhex('c78564010000208a5500'))
        self.assertEqual(pe.read_va(0x555787, 10), bytes.fromhex('c7855c01000010154100'))
        self.assertEqual(pe.read_va(0x411510, 3), bytes.fromhex('c21000'))  # why 16-bit stays 16
        self.assertEqual(pe.read_va(0x558C71, 5), bytes.fromhex('0d000000ff'))  # 24-bit forced opaque

    def test_byte_scope_preparation_and_corruption(self):
        before = prepare_client.configure(SOURCE.read_bytes(), experimental_world_detail=True,
                                          experimental_solids=True)
        after = prepare_client.configure(before, experimental_texture32=True)
        allowed = {i for off, old, _ in patch.regions() for i in range(off, off + len(old))}
        changed = {i for i, (a, b) in enumerate(zip(before, after)) if a != b}
        self.assertTrue(changed and changed <= allowed)
        self.assertEqual(prepare_client.configure(after), after)  # preserved by normal preparation
        self.assertIn(patch.NAME, prepare_client.inspect(after)['patches'])
        self.assertEqual(prepare_client.configure(after, experimental_texture32=False), before)
        for off, _, _ in patch.regions():
            broken = bytearray(after)
            broken[off] ^= 1
            with self.assertRaises(ValueError):
                prepare_client.inspect(bytes(broken))
        partial = bytearray(before)
        off, _, new = patch.regions()[2]
        partial[off:off + len(new)] = new
        with self.assertRaises(ValueError):
            patch.configure(bytes(partial))

    def test_install_idempotence_and_exact_undo(self):
        with tempfile.TemporaryDirectory() as folder:
            exe = Path(folder) / 'AOACLIENT.EXE'
            exe.write_bytes(SOURCE.read_bytes())
            prepare_client.prepare(exe, experimental_solids=True, experimental_world_detail=True)
            before = exe.read_bytes()
            patch.install(exe)
            after = exe.read_bytes()
            self.assertIn(patch.NAME, prepare_client.check(exe, require_assets=False)['patches'])
            patch.install(exe)
            self.assertEqual(exe.read_bytes(), after)
            patch.install(exe, undo=True)
            self.assertEqual(exe.read_bytes(), before)
            exe.with_suffix('.EXE.before-texture32').write_bytes(b'wrong backup')
            with self.assertRaises(ValueError):
                patch.install(exe)
            self.assertEqual(exe.read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
