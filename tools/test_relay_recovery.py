"""Real loopback relay checks for capacity and periodic absolute recovery."""
import contextlib
import math
import socket
import struct
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import aoanet
import relay_motion
import station_stub
from test_station_stub import request


class RelayRecoveryTests(unittest.TestCase):
    def test_capacity_periodic_recovery_and_invalid_state(self):
        key = bytes(range(256))
        with tempfile.TemporaryDirectory() as tmp, contextlib.ExitStack() as resources:
            folder = Path(tmp)
            (folder / "key").write_bytes(key)
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
                probe.bind(("127.0.0.1", 0))
                endpoint = probe.getsockname()
            proc = subprocess.Popen([sys.executable, "-I", str(Path(station_stub.__file__)), str(folder / "key"),
                                     str(folder / "log"), "--port", "0", "--arena", "--arena-port", str(endpoint[1]),
                                     "--ack", "--experimental-relay", "--max-players", "2", "--seconds", "15"],
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            peers = [resources.enter_context(socket.socket(socket.AF_INET, socket.SOCK_DGRAM)) for _ in range(3)]
            for peer in peers:
                peer.settimeout(0.25)
            slots = {}
            try:
                self.assertIn("station stub on", proc.stdout.readline())

                def send(peer, kind, payload):
                    peer.sendto(aoanet.encode(kind, payload, key), endpoint)

                def receive(peer, predicate):
                    deadline = time.monotonic() + 5
                    while time.monotonic() < deadline:
                        try:
                            message = aoanet.decode(peer.recv(512), key)
                        except socket.timeout:
                            continue
                        self.assertTrue(message["crc_ok"])
                        if message["type"] == 8 and peer in slots:
                            bounce = bytearray(message["payload"])
                            bounce[6] = slots[peer]
                            send(peer, 9, bounce)
                        elif message["type"] == 0x1B:
                            body = message["payload"]
                            send(peer, 15, body[-5:-1])
                        if predicate(message):
                            return message
                    self.fail("expected relay packet did not arrive")

                def join(peer):
                    send(peer, 10, request())
                    ack = receive(peer, lambda m: m["type"] == 11)["payload"]
                    result = struct.unpack_from("<I", ack, 6)[0]
                    if result == 0:
                        slots[peer] = struct.unpack_from("<I", ack, 2)[0] & 0xFFFF
                    return result

                a, b, c = peers
                self.assertEqual(join(a), 0)
                self.assertEqual(join(b), 0)
                self.assertEqual(join(c), 4)
                self.assertEqual(slots, {a: 1, b: 2})
                for peer in (a, b):
                    receive(peer, lambda m: m["type"] == 0x24)
                initial = relay_motion.initial((100, 200, 300))
                initial.update({8: (10, 20, 30), 0x40000: (1, 2, 3),
                                0x200000: (0.1, 0.2, 0.3), 0x1000000: (0.4, 0.5, 0.6)})
                baseline = relay_motion.snapshot(1, initial)
                expected, _, _ = relay_motion.update(baseline, {})
                send(a, 31, baseline)

                def is_state(message, state):
                    # Relayed snapshots carry server-owned stats (none yet; 9.30).
                    return message["type"] == 31 and message["payload"] == relay_motion.snapshot(
                        1, state, stats=(0, 0, 0, 0))

                receive(b, lambda m: is_state(m, expected))
                delta = struct.pack("<HHI3b3h3b", 0x8000, 1, 4 | 0x400000 | 0x4000000,
                                    1, -2, 3, 200, -300, 400, 4, -5, 6)
                expected, _, _ = relay_motion.update(delta, expected)
                send(a, 31, delta)
                receive(b, lambda m: is_state(m, expected))  # Discard immediate delivery.
                # No more movement input: this match must come from periodic refresh.
                receive(b, lambda m: is_state(m, expected))
                send(a, 31, struct.pack("<HHI3f", 0x8000, 1, 8, math.nan, 1, 2))
                receive(b, lambda m: is_state(m, expected))
                send(a, 0x4E, b"\0")
                receive(b, lambda m: m["type"] == 0x1B and m["payload"][-1] == 0x2D)
                self.assertEqual(join(c), 0)
                self.assertEqual(slots[c], 3)  # Rejected admission consumed no slot.
                self.assertIsNone(proc.poll())
            finally:
                if proc.poll() is None:
                    proc.terminate()
                proc.communicate(timeout=5)


if __name__ == "__main__":
    unittest.main(verbosity=2)
