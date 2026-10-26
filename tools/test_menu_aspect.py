"""Execute both ship-menu hooks in x86, checking framing and ABI preservation."""
import math
import struct
import sys
import unittest
from pathlib import Path

from unicorn import Uc, UC_ARCH_X86, UC_MODE_32
from unicorn.x86_const import UC_X86_REG_EAX, UC_X86_REG_ECX, UC_X86_REG_EDX, UC_X86_REG_EBP, UC_X86_REG_ESP

sys.path.insert(0, str(Path(__file__).resolve().parent))
import menu_aspect
import prepare_client


class MenuAspectTests(unittest.TestCase):
    def test_projection_and_registers(self):
        code, labels = menu_aspect.code()
        for width, height in [(640, 480), (1024, 768), (1920, 1080), (3440, 1440), (1080, 1920)]:
            for entry, end in [("layout", 0x463D0B), ("render", 0x4652A6)]:
                with self.subTest(width=width, height=height, entry=entry):
                    u = Uc(UC_ARCH_X86, UC_MODE_32)
                    u.mem_map(0x400000, 0x200000)
                    u.mem_map(0x700000, 0x20000)
                    u.mem_write(menu_aspect.CAVE, code)
                    u.mem_write(0x700058, struct.pack("<II", width, height))
                    u.mem_write(0x70211C, struct.pack("<I", 0x703000))
                    u.mem_write(0x703004, struct.pack("<I", 0x700000))
                    for reg, value in [(UC_X86_REG_EAX, 0x700000), (UC_X86_REG_ECX, 0x1234),
                                       (UC_X86_REG_EDX, 0x5678), (UC_X86_REG_EBP, 0x702000),
                                       (UC_X86_REG_ESP, 0x710000)]:
                        u.reg_write(reg, value)
                    u.emu_start(labels[entry], end, count=1000)
                    focal = min(width, height * 4 // 3) // 2
                    self.assertEqual(u.reg_read(UC_X86_REG_ECX), 0x1234)
                    self.assertEqual(u.reg_read(UC_X86_REG_EDX), 0x5678)
                    if entry == "layout":
                        self.assertEqual(u.reg_read(UC_X86_REG_EAX), focal)
                        self.assertEqual(u.reg_read(UC_X86_REG_ESP), 0x710000)
                    else:
                        self.assertEqual(u.reg_read(UC_X86_REG_EAX), 0x700000)
                        self.assertEqual(u.reg_read(UC_X86_REG_ESP), 0x70FFFC)
                        fov = struct.unpack("<f", u.mem_read(0x70FFFC, 4))[0]
                        self.assertAlmostEqual(fov, 2 * math.atan((width // 2) / focal), places=6)

    def test_reversible_and_rejects_corruption(self):
        path = Path(__file__).resolve().parents[1] / "game/2.9.2/AOACLIENT.EXE.orig"
        source = prepare_client.configure(path.read_bytes())
        source = menu_aspect.configure(source, False)
        prepare_client.inspect(source)
        patched = menu_aspect.configure(source)
        self.assertEqual(menu_aspect.configure(patched), patched)
        self.assertEqual(menu_aspect.configure(patched, False), source)
        for off in [menu_aspect.CAVE - 0x400000, 0x63D06, 0x652A1]:
            bad = bytearray(patched)
            bad[off] ^= 0xFF
            with self.assertRaises(ValueError):
                menu_aspect.configure(bad)


if __name__ == "__main__":
    unittest.main()
