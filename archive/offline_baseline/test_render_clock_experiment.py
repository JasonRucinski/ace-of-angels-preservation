"""Execute the experimental clock with controlled Windows counter results."""
import struct
import sys
import unittest
from itertools import product
from pathlib import Path
from unicorn import Uc, UC_ARCH_X86, UC_MODE_32, UC_HOOK_CODE
from unicorn.x86_const import UC_X86_REG_EAX, UC_X86_REG_ECX, UC_X86_REG_EDX, UC_X86_REG_ESP, UC_X86_REG_FPCW

sys.path.insert(0, str(Path(__file__).resolve().parent))
import render_clock_experiment as clock
import prepare_client


class ClockTests(unittest.TestCase):
    def test_counter_conversion_and_abi(self):
        for frequency, cw in product((10_000_000, 3_579_545), (0x7F, 0x27F, 0x37F)):
            for ms in (0, 1, 17, 551433734, 2**32 - 1, 2**32 + 17):
                with self.subTest(frequency=frequency, ms=ms):
                    u = Uc(UC_ARCH_X86, UC_MODE_32)
                    u.reg_write(UC_X86_REG_FPCW, cw)
                    u.mem_map(0x400000, 0x200000)
                    u.mem_map(0x700000, 0x20000)
                    u.mem_write(clock.CAVE, clock.code())
                    u.mem_write(0x58C060, struct.pack('<I', 0x500000))
                    u.mem_write(0x58C05C, struct.pack('<I', 0x500010))
                    u.mem_write(0x500000, bytes.fromhex('c20400'))
                    u.mem_write(0x500010, bytes.fromhex('c20400'))
                    def api(uc, address, size, data):
                        if address in (0x500000, 0x500010):
                            sp = uc.reg_read(UC_X86_REG_ESP)
                            ptr = struct.unpack('<I', uc.mem_read(sp + 4, 4))[0]
                            value = frequency if address == 0x500000 else round(ms * frequency / 1000)
                            uc.mem_write(ptr, struct.pack('<q', value))
                            uc.reg_write(UC_X86_REG_EAX, 1)
                    u.hook_add(UC_HOOK_CODE, api)
                    u.mem_write(0x710000, struct.pack('<I', 0x500100))
                    for reg, value in [(UC_X86_REG_ESP, 0x710000), (UC_X86_REG_ECX, 1234), (UC_X86_REG_EDX, 5678)]:
                        u.reg_write(reg, value)
                    u.emu_start(clock.CAVE, 0x500100, count=1000)
                    self.assertEqual(u.reg_read(UC_X86_REG_EAX), ms & 0xFFFFFFFF)
                    self.assertEqual(u.reg_read(UC_X86_REG_ESP), 0x710004)
                    self.assertEqual(u.reg_read(UC_X86_REG_ECX), 1234)
                    self.assertEqual(u.reg_read(UC_X86_REG_EDX), 5678)
                    self.assertEqual(u.reg_read(UC_X86_REG_FPCW), cw)

    def test_reversible(self):
        p = Path(__file__).resolve().parents[1] / 'game/2.9.2/AOACLIENT.EXE.orig'
        # The experiment shares the clock sites with frame-clock-v1; test it alone.
        original = prepare_client.configure(p.read_bytes(), smooth_frame_clock=False)
        patched = clock.configure(original)
        self.assertEqual(clock.configure(patched), patched)
        self.assertEqual(clock.configure(patched, False), original)
        allowed = {i for off, old, new in clock.regions() for i in range(off, off + len(old))}
        self.assertEqual(len(original), len(patched))
        self.assertTrue(all(i in allowed for i,(a,b) in enumerate(zip(original, patched)) if a != b))
        for off, old, new in clock.regions():
            bad = bytearray(patched)
            bad[off] ^= 0xFF
            with self.assertRaises(ValueError):
                clock.configure(bytes(bad))


if __name__ == '__main__':
    unittest.main()
