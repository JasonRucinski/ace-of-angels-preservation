"""The standard-library PE section mapper, on a synthetic image; game-free.

Checks aoa.formats.pe against a hand-built two-section executable, the
archive key lookup of aoa.formats.aoapack on it, and (when pefile is
installed) that aoa.analysis.pe_util.PE maps it the same way.

    python -I tools/test.py test_pe
"""
import hashlib
import importlib.util
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from aoa.formats import aoapack
from aoa.formats import pe
from aoa.paths import ROOT

BASE = 0x400000
KEY = bytes(range(256))
KEY_VA = 0x5DE678


def synthetic_image():
    """MZ + PE headers, .text (raw 0x200, virtual 0x100) and .data (raw 0x1000, virtual 0x3000).

    .data starts at RVA 0x1000 in the file at 0x600 and holds the 256-byte key
    at KEY_VA; its tail past the raw bytes is zero fill.
    """
    e = 0x80
    header = bytearray(0x400)
    header[:2] = b"MZ"
    struct.pack_into("<I", header, 0x3C, e)
    header[e:e + 4] = b"PE\0\0"
    struct.pack_into("<HHIIIHH", header, e + 4, 0x14C, 2, 0, 0, 0, 0xE0, 0x10F)
    optional = e + 24
    struct.pack_into("<H", header, optional, 0x10B)
    struct.pack_into("<I", header, optional + 28, BASE)
    struct.pack_into("<I", header, optional + 56, 0x1E1000)
    sections = optional + 0xE0
    key_rva = KEY_VA - BASE
    data_rva = key_rva & ~0xFFF
    for k, (name, vsize, rva, raw_size, raw_off, chars) in enumerate((
            (b".text", 0x100, 0x1000, 0x200, 0x400, 0x60000020),
            (b".data", 0x3000, data_rva, 0x1000, 0x600, 0xC0000040))):
        o = sections + 40 * k
        header[o:o + 8] = name.ljust(8, b"\0")
        struct.pack_into("<IIII", header, o + 8, vsize, rva, raw_size, raw_off)
        struct.pack_into("<I", header, o + 36, chars)
    text = bytes([0x90] * 0x100 + [0xCC] * 0x100)
    data = bytearray(0x1000)
    data[key_rva - data_rva:key_rva - data_rva + 256] = KEY
    data[0x10:0x18] = b"hello\0\0\0"
    return bytes(header) + text + bytes(data)


class Mapper(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = synthetic_image()
        tmp = tempfile.TemporaryDirectory(prefix="aoa-pe-")
        cls.addClassCleanup(tmp.cleanup)
        cls.path = Path(tmp.name) / "synthetic.exe"
        cls.path.write_bytes(cls.data)

    def test_headers(self):
        image = pe.Image(self.path)
        self.assertEqual(image.base, BASE)
        self.assertEqual(image.size_of_image, 0x1E1000)
        self.assertEqual([s["name"] for s in image.sections], [".text", ".data"])
        self.assertEqual(image.text()["name"], ".text")
        self.assertEqual(pe.Image(self.data).sections, image.sections)

    def test_mapping(self):
        image = pe.Image(self.data)
        data_va = image.sections[1]["va"]
        self.assertEqual(image.va_to_off(BASE + 0x1000), 0x400)
        self.assertEqual(image.off_to_va(0x400), BASE + 0x1000)
        self.assertEqual(image.va_to_off(data_va + 0x10), 0x610)
        self.assertEqual(image.off_to_va(0x610), data_va + 0x10)
        self.assertEqual(image.cstr(data_va + 0x10), "hello")
        self.assertEqual(image.read_va(KEY_VA, 256), KEY)
        self.assertEqual(image.u32(KEY_VA), int.from_bytes(KEY[:4], "little"))
        # Inside .text's raw size but past its virtual size: still file-backed.
        self.assertEqual(image.va_to_off(BASE + 0x1180), 0x580)
        # Past .data's raw bytes: virtual zero fill, no file offset.
        self.assertIsNone(image.va_to_off(data_va + 0x2000))
        self.assertEqual(image.read_va(data_va + 0xFFE, 4), bytes(4))
        self.assertIsNone(image.va_to_off(BASE))  # headers are not a section
        self.assertIsNone(image.off_to_va(0x10))
        self.assertEqual(image.find_all(b"\xcc" * 0x80), [0x500 + i for i in range(0x81)])

    def test_refuses_other_files(self):
        for data in (b"", b"MZ" + bytes(0x80), b"\x7fELF" + bytes(0x100)):
            with self.assertRaises(ValueError):
                pe.Image(data)

    def test_archive_key_without_analysis_packages(self):
        # A prepared client: unknown hash, key found at a candidate VA by its own hash.
        with mock.patch.object(aoapack, "KEY_SHA256", hashlib.sha256(KEY).hexdigest()):
            self.assertEqual(aoapack.builtin_key(self.path), KEY)
        with self.assertRaises(KeyError):
            aoapack.builtin_key(self.path)
        code = ("import sys; sys.path[:0] = [sys.argv[1]]; from aoa.formats import aoapack; "
                "from aoa.maps import make_map, make_object; from aoa.client import texture_pack; "
                "print(sorted({'capstone', 'pefile', 'unicorn'} & set(sys.modules)))")
        out = subprocess.run([sys.executable, "-I", "-c", code, str(ROOT)], capture_output=True,
                             text=True, check=True, stdin=subprocess.DEVNULL).stdout
        self.assertEqual(out.strip(), "[]")

    @unittest.skipUnless(importlib.util.find_spec("pefile") and importlib.util.find_spec("capstone"),
                         "needs pefile and capstone")
    def test_pe_util_maps_the_same_way(self):
        from aoa.analysis.pe_util import PE
        full = PE(self.path)
        image = pe.Image(self.path)
        self.assertEqual(full.base, full.pe.OPTIONAL_HEADER.ImageBase)
        self.assertEqual(full.sections, image.sections)
        self.assertEqual(full.sections, [{
            "name": s.Name.rstrip(b"\0").decode("latin1"), "va": BASE + s.VirtualAddress,
            "vsize": s.Misc_VirtualSize, "raw_off": s.PointerToRawData, "raw_size": s.SizeOfRawData,
            "chars": s.Characteristics} for s in full.pe.sections])
        self.assertEqual(full.read_va(KEY_VA, 256), KEY)


if __name__ == "__main__":
    unittest.main()
