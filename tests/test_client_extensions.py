"""Loopback transport for the manual protection probe; no real game process."""
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from aoa.protocol import codec
from tests.support import request
from aoa import paths


class ExtensionTransportTests(unittest.TestCase):
    def test_explicit_protection_probe_order_and_retry(self):
        key = bytes(range(256))
        with tempfile.TemporaryDirectory(prefix="aoa-protection-") as tmp:
            folder = Path(tmp)
            (folder / "key").write_bytes(key)
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
                probe.bind(("127.0.0.1", 0))
                endpoint = probe.getsockname()
            process = subprocess.Popen(
                [sys.executable, "-I", str(paths.entry("station_stub")), str(folder / "key"), str(folder / "log"),
                 "--port", "0", "--arena", "--arena-port", str(endpoint[1]), "--ack",
                 "--experimental-flight", "--max-players", "1", "--experimental-protection-probe",
                 "--seconds", "25"], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as peer:
                    peer.bind(("127.0.0.1", 0))
                    peer.settimeout(0.1)
                    connected, entered, values, copies = False, False, [], {}
                    deadline = time.monotonic() + 22
                    while len(values) < 4 and time.monotonic() < deadline:
                        if not connected:
                            peer.sendto(codec.encode(10, request(), key), endpoint)
                        try:
                            message = codec.decode(peer.recv(512), key)
                        except (socket.timeout, ConnectionResetError):
                            continue
                        self.assertTrue(message["crc_ok"])
                        kind, body = message["type"], message["payload"]
                        if kind == 0x0B:
                            connected = True
                        elif kind == 0x2C:
                            entered = True
                        elif kind == 8:
                            bounce = bytearray(body)
                            bounce[6] = 1
                            peer.sendto(codec.encode(9, bytes(bounce), key), endpoint)
                        elif kind == 0x1B:
                            self.assertTrue(entered)
                            self.assertEqual((len(body), body[-1]), (6, 0x81))
                            sequence = body[-5:-1]
                            copies[sequence] = copies.get(sequence, 0) + 1
                            if copies[sequence] == 1:
                                values.append(body[0])
                            # Lose the first ACK for the first enable.
                            if len(copies) > 1 or copies[sequence] > 1:
                                peer.sendto(codec.encode(0x0F, sequence, key), endpoint)
                    self.assertEqual(values, [1, 1, 0, 0])
                    self.assertGreaterEqual(next(iter(copies.values())), 2)
                    self.assertIsNone(process.poll())
            finally:
                process.terminate()
                _, stderr = process.communicate(timeout=5)
                self.assertNotIn("Traceback", stderr.decode(errors="replace"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
