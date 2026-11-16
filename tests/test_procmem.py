"""aoa/live/procmem.py against a fake process; game-free and needs no Windows.

The kernel32 calls are replaced by a bytearray standing in for the client's
memory, so sized reads, writes and the build check run anywhere. The real
OpenProcess/ReadProcessMemory path is Windows-only and is not exercised.

    python -I tools/test.py test_procmem
"""
import calendar
import ctypes
import json
import struct
import time
import unittest

from aoa.live import addresses_292, procmem
from aoa.paths import ROOT

BASE = addresses_292.IMAGE_BASE


class FakeProcess(procmem.Process):
    """Memory from BASE to BASE + 0x300000, with a PE header carrying `stamp`."""

    def __init__(self, stamp=addresses_292.PE_TIMESTAMP, **kwargs):
        self.memory = bytearray(0x300000)
        struct.pack_into("<I", self.memory, 0x3C, 0x100)
        struct.pack_into("<I", self.memory, 0x108, stamp)
        self.closed = False
        super().__init__(4242, **kwargs)

    def _open(self, pid, access):
        self.access = access
        return 1

    def _transfer(self, call, address, buffer, size):
        offset = address - BASE
        if not 0 <= offset <= len(self.memory) - size:
            return -1
        if call == "ReadProcessMemory":
            ctypes.memmove(buffer, bytes(self.memory[offset:offset + size]), size)
        else:
            self.memory[offset:offset + size] = buffer
        return size

    def _close(self):
        self.closed = True


class ProcessMemory(unittest.TestCase):
    def test_reads_are_sized_to_the_request(self):
        p = FakeProcess()
        p.memory[0x1000:0x1000 + 300] = bytes(range(256)) + bytes(44)
        self.assertEqual(p.read(BASE + 0x1000, 300)[:256], bytes(range(256)))  # > the old 64-byte buffer
        self.assertEqual(len(p.read(BASE + 0x1000, 1)), 1)
        self.assertEqual(p.u32(BASE + 0x1000), 0x03020100)
        with self.assertRaises(OSError):
            p.read(BASE - 4, 4)

    def test_write(self):
        p = FakeProcess(access=procmem.VM_READ | procmem.VM_WRITE)
        p.write(BASE + 0x2000, b"\xB0\x01")
        self.assertEqual(p.read(BASE + 0x2000, 2), b"\xB0\x01")

    def test_build_check(self):
        FakeProcess().close()
        with self.assertRaises(ValueError) as caught:
            FakeProcess(stamp=0x12345678)
        self.assertIn("not the 2.9.2 client", str(caught.exception))
        FakeProcess(stamp=0x12345678, build=None)
        with self.assertRaises(ValueError):
            FakeProcess(build="2.8.2")

    def test_close_once(self):
        with FakeProcess() as p:
            pass
        self.assertTrue(p.closed)
        self.assertIsNone(p.handle)
        p.close()

    def test_timestamp_matches_the_manifest(self):
        manifest = json.loads((ROOT / "manifest/downloads.json").read_text(encoding="utf-8"))
        entry = next(d for d in manifest["downloads"] if d["runtime_version"] == "2.9.2")
        stamp = calendar.timegm(time.strptime(entry["client_pe_timestamp_utc"], "%Y-%m-%dT%H:%M:%SZ"))
        self.assertEqual(stamp, addresses_292.PE_TIMESTAMP)

    def test_live_tools_share_the_module(self):
        from aoa.live import arena, frame_pacing
        from aoa.reel import client_mem
        self.assertIs(frame_pacing.Process, procmem.Process)
        self.assertTrue(issubclass(client_mem.Client, procmem.Process))
        self.assertIs(arena.Process, procmem.Process)
        self.assertEqual(client_mem.WORLD, addresses_292.WORLD)


if __name__ == "__main__":
    unittest.main()
