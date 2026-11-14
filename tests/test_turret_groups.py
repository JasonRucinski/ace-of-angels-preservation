"""Turret-group packet boundaries and original-client receiver behavior."""
import hashlib
import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import turret_groups
from patch_client import PRISTINE_292

CLIENT = Path(__file__).resolve().parents[1] / 'game/2.9.2/AOACLIENT.EXE.orig'


class GroupTests(unittest.TestCase):
    def test_bounds(self):
        for tags in ([0], [-1], [2**32], [True], [1, 1], list(range(1, 52))):
            with self.subTest(tags=tags), self.assertRaises(ValueError):
                turret_groups.status(tags)
        for team in ('x' * 32, 'bad\0name'):
            with self.assertRaises(ValueError):
                turret_groups.status([1], team=team)
        with self.assertRaises(ValueError):
            turret_groups.status([1], enabled=True)
        kind, body = turret_groups.status([1], enabled=True, team='Test team')
        self.assertEqual((kind, len(body)), (0x70, 236))
        self.assertEqual(body[204:].rstrip(b'\0'), b'Test team')

    @unittest.skipUnless(CLIENT.exists(), 'requires original 2.9.2 client')
    def test_native_disable_counts_and_terminator(self):
        from emulate_codec import Emu, HEAP, SCRATCH
        from pe_util import PE
        self.assertEqual(hashlib.sha256(CLIENT.read_bytes()).hexdigest(), PRISTINE_292)
        emu = Emu(PE(CLIENT))
        world, controller, objects = HEAP, HEAP + 0x100000, HEAP + 0x110000
        emu.write(world + 0xdf03c, struct.pack('<I', controller))
        emu.write(controller, struct.pack('<I', objects))
        tags = [0x20010000 + i for i in range(1, 51)]
        for i, tag in enumerate(tags):
            address = objects + i * 0x400
            emu.write(address + 0x178, struct.pack('<I', tag))
            emu.write(address + 0x180, struct.pack('<I', address + 0x400 if i < 49 else 0))
        for count in (0, 1, 5, 50):
            with self.subTest(count=count):
                for i in range(50):
                    emu.write(objects + i * 0x400 + 0x1dc, b'\xff' * 4)
                emu.write(SCRATCH, turret_groups.status(tags[:count])[1])
                emu.thiscall(0x4afd20, world, SCRATCH)
                for i in range(50):
                    expected = bytes(4) if i < count else b'\xff' * 4
                    self.assertEqual(emu.read(objects + i * 0x400 + 0x1dc, 4), expected)

    @unittest.skipUnless(CLIENT.exists(), 'requires original 2.9.2 client')
    def test_native_firing_gate(self):
        from emulate_codec import Emu, HEAP, STACK, STOP
        from pe_util import PE
        from unicorn import UC_HOOK_CODE
        from unicorn.x86_const import UC_X86_REG_EIP, UC_X86_REG_ESP, UC_X86_REG_EDI, UC_X86_REG_EBX
        self.assertEqual(hashlib.sha256(CLIENT.read_bytes()).hexdigest(), PRISTINE_292)
        emu = Emu(PE(CLIENT))
        def stop(uc, address, size, _):
            if address in (0x4e9720, 0x4e9297):
                uc.emu_stop()
        emu.uc.hook_add(UC_HOOK_CODE, stop)
        world, obj, gun = HEAP, HEAP + 0x100000, HEAP + 0x101000
        emu.write(0x5e7728, struct.pack('<I', world))
        sp = STACK + 0xe0000
        emu.write(sp + 0x28, struct.pack('<I', obj))
        for activation, world_flag, expected in ((0, 0, 0x4e9720), (-1, 0, 0x4e9297), (-1, 1, 0x4e9720)):
            with self.subTest(activation=activation, world_flag=world_flag):
                emu.write(obj + 0x1dc, struct.pack('<i', activation))
                emu.write(world + 0xdef4a, bytes([world_flag]))
                emu.uc.reg_write(UC_X86_REG_ESP, sp)
                emu.uc.reg_write(UC_X86_REG_EDI, gun)
                emu.uc.reg_write(UC_X86_REG_EBX, obj + 0x2000)  # Non-null target.
                emu.uc.emu_start(0x4e9254, STOP, count=60)
                self.assertEqual(emu.uc.reg_read(UC_X86_REG_EIP), expected)


if __name__ == '__main__':
    unittest.main(verbosity=2)
