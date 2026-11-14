"""Bounded decoder regression/fuzz cases; deterministic and entirely offline."""
import random
import sys
import unittest
import socket
import struct
import subprocess
import tempfile
from pathlib import Path

from aoa.formats import aoacrypt
from aoa.protocol import codec
from aoa.formats import aoapack
from aoa.host.runtime import DatagramBudget
from tests.test_station_stub import request
from aoa import paths

KEY = bytes(range(256))


class NetworkBoundsTests(unittest.TestCase):
    def test_ingress_limits_and_bounded_endpoint_table(self):
        budget = DatagramBudget()
        self.assertTrue(all(budget.allow("first", 0) for _ in range(120)))
        self.assertFalse(budget.allow("first", 0))
        self.assertTrue(budget.allow("other", 0))
        self.assertTrue(budget.allow("first", 1))
        for index in range(1000):
            budget.allow(index, index + 2)
        self.assertEqual(len(budget.peers), budget.MAX_PEERS)
        budget = DatagramBudget()
        self.assertTrue(all(budget.allow(index, 0) for index in range(200)))
        self.assertFalse(budget.allow("new", 0))
        self.assertTrue(budget.allow("new", 1))

    def test_oversized_packets_and_wrong_version_do_not_admit_or_crash(self):
        with tempfile.TemporaryDirectory() as tmp, socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as peer:
            folder = Path(tmp)
            (folder / "key").write_bytes(KEY)
            proc = subprocess.Popen([sys.executable, "-I", str(paths.entry("station_stub")), str(folder / "key"),
                                     str(folder / "log"), "--port", "0", "--ack", "--seconds", "5"],
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            try:
                port = int(proc.stdout.readline().split("127.0.0.1:")[1].split()[0])
                endpoint = ("127.0.0.1", port)
                peer.settimeout(2)
                for data in (b"", b"x", bytes(513), bytes(60000)):
                    peer.sendto(data, endpoint)
                invalid = bytearray(request())
                struct.pack_into("<I", invalid, 1, 8)
                peer.sendto(codec.encode(10, invalid, KEY), endpoint)
                rejected = codec.decode(peer.recv(512), KEY)
                self.assertEqual(struct.unpack_from("<I", rejected["payload"], 6)[0], 8)
                self.assertEqual(rejected["payload"][13:], bytes(350))
                peer.sendto(codec.encode(10, request(), KEY), endpoint)
                accepted = codec.decode(peer.recv(512), KEY)
                self.assertEqual(struct.unpack_from("<I", accepted["payload"], 6)[0], 0)
                self.assertEqual(struct.unpack_from("<I", accepted["payload"], 136)[0], 1)
                self.assertIsNone(proc.poll())
            finally:
                if proc.poll() is None:
                    proc.terminate()
                proc.communicate(timeout=5)

    def test_supported_packets_and_boundaries(self):
        rng = random.Random(20261021)
        for size in (0, 1, 12, 129, 191, 320, 363, 381, 438, 508):
            payload = rng.randbytes(size)
            for compressed in (False, True):
                message = codec.decode(codec.encode(31, payload, KEY, compressed), KEY)
                self.assertTrue(message["crc_ok"])
                self.assertEqual((message["type"], message["payload"]), (31, payload))
        self.assertEqual(len(codec.decode(codec.encode(31, bytes(509), KEY), KEY)["payload"]), 509)
        for kind, payload, key in ((256, b"", KEY), (-1, b"", KEY), (1, bytes(510), KEY), (1, b"", b"x")):
            with self.assertRaises(ValueError):
                codec.encode(kind, payload, key)
        with self.assertRaises(ValueError):
            codec.encode(1, bytes(509), KEY, compress=False)

    def test_malformed_trailers_and_expansion(self):
        for wire in (b"", b"x", b"xx", bytes(513), aoacrypt.encrypt(b"\0\0\x10", KEY)):
            with self.assertRaises(ValueError):
                codec.decode(wire, KEY)
        for data in (b"", b"\x08", b"\0\x08", b"\x01"):
            with self.assertRaises(ValueError):
                aoapack.decompress(data, max_output=512)
        for size in (513, 4096, 16384):
            bomb = aoapack.compress(bytes(size))
            self.assertLessEqual(len(bomb), 512)
            with self.assertRaises(ValueError):
                codec.decode(aoacrypt.encrypt(bomb, KEY), KEY)
        # Both CRC layers matter when the optional compression CRC is used.
        inner = b"hello\x05" + aoapack.crc16_xmodem(b"hello").to_bytes(2, "little")
        packed = bytearray(aoapack.compress(inner, with_crc=True))
        packed[-2] ^= 1
        with self.assertRaises(ValueError):
            codec.decode(aoacrypt.encrypt(packed, KEY), KEY)

    def test_seeded_fuzz_has_only_bounded_results_or_value_errors(self):
        rng = random.Random(9417)
        cases = [rng.randbytes(rng.randrange(514)) for _ in range(2000)]
        for _ in range(2000):
            wire = bytearray(codec.encode(rng.randrange(256), rng.randbytes(rng.randrange(450)), KEY))
            wire[rng.randrange(len(wire))] ^= rng.randrange(1, 256)
            cases.append(bytes(wire))
        for wire in cases:
            try:
                decoded = codec.decode(wire, KEY)
            except ValueError:
                continue
            self.assertLessEqual(len(decoded["payload"]), 509)
            self.assertIn(decoded["type"], range(256))

    def test_archive_decoder_remains_unbounded_by_default(self):
        payload = b"archive-data" * 1000
        self.assertEqual(aoapack.decompress(aoapack.compress(payload, with_crc=True))[0], payload)
        for crc in (False, True):
            self.assertEqual(aoapack.decompress(aoapack.compress(b"", with_crc=crc))[0], b"")


if __name__ == "__main__":
    unittest.main(verbosity=2)
