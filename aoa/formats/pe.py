"""Section mapper for 32-bit Windows executables (PE); standard library only.

Address spaces:
  file offset  <->  RVA  <->  VA (= ImageBase + RVA)
Mapping goes through the section table. Bytes past a section's SizeOfRawData
but inside its VirtualSize are zero-initialised at load time and have no file
backing; `read_va` returns zeros for them and `va_to_off` returns None.

aoa.analysis.pe_util.PE adds imports and disassembly on top of this (with
pefile and capstone); readers that only need bytes at an address, such as
the archive key lookup in aoa.formats.aoapack, use Image directly.
"""
import struct
from pathlib import Path


class Image:
    """The headers and section table of a PE file, from its path or its bytes."""

    def __init__(self, source):
        if isinstance(source, (bytes, bytearray, memoryview)):
            self.path, self.data = None, bytes(source)
        else:
            self.path = Path(source)
            self.data = self.path.read_bytes()
        d = self.data
        if len(d) < 0x40 or d[:2] != b"MZ":
            raise ValueError("not a PE image: no MZ header")
        e = struct.unpack_from("<I", d, 0x3C)[0]
        if d[e:e + 4] != b"PE\0\0" or len(d) < e + 24:
            raise ValueError("not a PE image: no PE signature")
        count, optional_size = struct.unpack_from("<H", d, e + 6)[0], struct.unpack_from("<H", d, e + 20)[0]
        optional = e + 24
        magic = struct.unpack_from("<H", d, optional)[0]
        if magic == 0x10B:
            self.base = struct.unpack_from("<I", d, optional + 28)[0]
        elif magic == 0x20B:
            self.base = struct.unpack_from("<Q", d, optional + 24)[0]
        else:
            raise ValueError(f"not a PE image: optional header magic {magic:#x}")
        self.size_of_image = struct.unpack_from("<I", d, optional + 56)[0]
        self.sections = []
        for k in range(count):
            o = optional + optional_size + 40 * k
            name = d[o:o + 8]
            vsize, rva, raw_size, raw_off = struct.unpack_from("<IIII", d, o + 8)
            chars = struct.unpack_from("<I", d, o + 36)[0]
            self.sections.append({
                "name": name.rstrip(b"\0").decode("latin1"),
                "va": self.base + rva,
                "vsize": vsize,
                "raw_off": raw_off,
                "raw_size": raw_size,
                "chars": chars,
            })

    # ---- address mapping -------------------------------------------------
    def section_of_va(self, va):
        for s in self.sections:
            if s["va"] <= va < s["va"] + max(s["vsize"], s["raw_size"]):
                return s
        return None

    def va_to_off(self, va):
        s = self.section_of_va(va)
        if s is None:
            return None
        delta = va - s["va"]
        if delta >= s["raw_size"]:
            return None  # virtual zero-fill
        return s["raw_off"] + delta

    def off_to_va(self, off):
        for s in self.sections:
            if s["raw_off"] <= off < s["raw_off"] + s["raw_size"]:
                return s["va"] + (off - s["raw_off"])
        return None

    def read_va(self, va, n):
        out = bytearray()
        for i in range(n):
            o = self.va_to_off(va + i)
            out.append(self.data[o] if o is not None else 0)
        return bytes(out)

    def u32(self, va):
        return int.from_bytes(self.read_va(va, 4), "little")

    def cstr(self, va, limit=512):
        o = self.va_to_off(va)
        if o is None:
            return None
        end = self.data.find(b"\0", o, o + limit)
        if end < 0:
            return None
        raw = self.data[o:end]
        try:
            return raw.decode("ascii")
        except UnicodeDecodeError:
            return None

    def find_all(self, needle: bytes):
        out, i = [], self.data.find(needle)
        while i >= 0:
            out.append(i)
            i = self.data.find(needle, i + 1)
        return out

    def text(self):
        return next(s for s in self.sections if s["chars"] & 0x20000000)  # MEM_EXECUTE
