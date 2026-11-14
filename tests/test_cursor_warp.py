"""Run the client's own cursor warp (0x4EACE0) in x86, before and after the fix."""
import struct
import sys
import unittest
from pathlib import Path

from unicorn import Uc, UC_ARCH_X86, UC_MODE_32, UC_HOOK_CODE
from unicorn.x86_const import (UC_X86_REG_EAX, UC_X86_REG_EBX, UC_X86_REG_ECX, UC_X86_REG_EDX,
                               UC_X86_REG_EDI, UC_X86_REG_EBP, UC_X86_REG_ESI, UC_X86_REG_ESP,
                               UC_X86_REG_EIP)

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cursor_warp
import prepare_client

ORIGINAL = Path(__file__).resolve().parents[1] / "game/2.9.2/AOACLIENT.EXE.orig"
WARP, MOUSE, HWND, RETURN, STACK = 0x4EACE0, 0x700000, 0x1234, 0x6F0F00, 0x710000
STUB_S2C, STUB_SET = 0x6F0000, 0x6F0010


def warp(image, x, y, cached, window, s2c_ok=True):
    """Return the SetCursorPos point for a warp to client (x, y)."""
    u = Uc(UC_ARCH_X86, UC_MODE_32)
    u.mem_map(0x400000, 0x200000)
    u.mem_map(0x6F0000, 0x30000)
    u.mem_write(0x401000, image[0x1000:0x18C000])
    u.mem_write(cursor_warp.IAT_SCREENTOCLIENT, struct.pack("<I", STUB_S2C))
    u.mem_write(cursor_warp.IAT_SETCURSORPOS, struct.pack("<I", STUB_SET))
    u.mem_write(cursor_warp.MAIN_HWND, struct.pack("<I", HWND))
    u.mem_write(MOUSE + 0x28, struct.pack("<II", *cached))
    calls = []

    def hook(uc, address, size, _):
        esp = uc.reg_read(UC_X86_REG_ESP)
        ret, a, b = struct.unpack("<III", uc.mem_read(esp, 12))
        if address == STUB_S2C:
            calls.append(("ScreenToClient", a))
            if s2c_ok:
                px, py = struct.unpack("<ii", uc.mem_read(b, 8))
                uc.mem_write(b, struct.pack("<ii", px - window[0], py - window[1]))
            uc.reg_write(UC_X86_REG_EAX, int(s2c_ok))
        else:
            calls.append(("SetCursorPos", struct.unpack("<i", struct.pack("<I", a))[0],
                          struct.unpack("<i", struct.pack("<I", b))[0]))
            uc.reg_write(UC_X86_REG_EAX, 1)
        uc.reg_write(UC_X86_REG_ECX, 0xBAD1)
        uc.reg_write(UC_X86_REG_EDX, 0xBAD2)
        uc.reg_write(UC_X86_REG_ESP, esp + 12)
        uc.reg_write(UC_X86_REG_EIP, ret)

    u.hook_add(UC_HOOK_CODE, hook, begin=STUB_S2C, end=STUB_SET)
    sp = STACK - 0x100
    u.mem_write(sp, struct.pack("<III", RETURN, x, y))
    saved = {UC_X86_REG_EBX: 0x1111, UC_X86_REG_ESI: 0x2222, UC_X86_REG_EDI: 0x3333, UC_X86_REG_EBP: 0x4444}
    for reg, value in {**saved, UC_X86_REG_ESP: sp, UC_X86_REG_ECX: MOUSE}.items():
        u.reg_write(reg, value)
    u.emu_start(WARP, RETURN, count=200)
    assert u.reg_read(UC_X86_REG_ESP) == sp + 12, "ret 8 stack balance"
    assert all(u.reg_read(reg) == value for reg, value in saved.items()), "callee-saved registers"
    assert struct.unpack("<ii", u.mem_read(MOUSE + 0x10, 8)) == (x, y), "internal position"
    return calls


class CursorWarpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original = ORIGINAL.read_bytes()
        cls.prepared = prepare_client.configure(cls.original)
        cls.unfixed = cursor_warp.configure(cls.prepared, False)

    def test_original_sends_stale_origin_to_the_corner(self):
        calls = warp(self.unfixed, 960, 540, cached=(65535, 65535), window=(0, 0))
        self.assertEqual(calls, [("SetCursorPos", 960 + 65535, 540 + 65535)])

    def test_fixed_uses_live_window_origin(self):
        for x, y, cached, window in [(960, 540, (65535, 65535), (0, 0)),
                                     (12, 700, (0, 0), (-1920, 100)),
                                     (320, 240, (65528, 65505), (-8, -31)),
                                     (0, 0, (100, 200), (100, 200))]:
            with self.subTest(window=window, cached=cached):
                calls = warp(self.prepared, x, y, cached, window)
                self.assertEqual(calls, [("ScreenToClient", HWND),
                                         ("SetCursorPos", x + window[0], y + window[1])])

    def test_falls_back_to_cached_origin(self):
        calls = warp(self.prepared, 50, 60, cached=(300, 400), window=(9, 9), s2c_ok=False)
        self.assertEqual(calls[-1], ("SetCursorPos", 350, 460))

    def test_reversible_and_rejects_corruption(self):
        self.assertIn(cursor_warp.NAME, prepare_client.inspect(self.prepared)["patches"])
        self.assertEqual(cursor_warp.configure(self.prepared), self.prepared)
        for off in [cursor_warp.CAVE - 0x400000, cursor_warp.SITE - 0x400000]:
            bad = bytearray(self.prepared)
            bad[off] ^= 0xFF
            with self.assertRaises(ValueError):
                cursor_warp.configure(bad)
            with self.assertRaises(ValueError):
                prepare_client.inspect(bytes(bad))


if __name__ == "__main__":
    unittest.main()
