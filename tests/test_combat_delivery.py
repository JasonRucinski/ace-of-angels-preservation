"""Synthetic loopback combat delivery; no game process or real damage model."""
import select
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
import station_stub as stub
import test_station_stub
from test_station_stub import request


class CombatDeliveryTests(unittest.TestCase):
    def test_launch_impact_death_with_lost_ack(self):
        key = bytes(range(256))
        with tempfile.TemporaryDirectory(prefix="aoa-combat-delivery-") as tmp:
            folder = Path(tmp)
            (folder / "key").write_bytes(key)
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
                probe.bind(("127.0.0.1", 0))
                endpoint = probe.getsockname()
            process = subprocess.Popen(
                [sys.executable, "-I", str(Path(stub.__file__)), str(folder / "key"),
                 str(folder / "log"), "--port", "0", "--arena", "--arena-port", str(endpoint[1]),
                 "--ack", "--experimental-relay", "--experimental-reliable-combat",
                 "--peer-timeout", "8", "--seconds", "30"],
                stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            peers = [socket.socket(socket.AF_INET, socket.SOCK_DGRAM) for _ in range(2)]
            messages = {p: [] for p in peers}
            seen = {p: set() for p in peers}
            copies = {}
            hold_launch_ack = True

            def send(peer, kind, body):
                peer.sendto(aoanet.encode(kind, body, key), endpoint)

            def pump(duration):
                until = time.monotonic() + duration
                while time.monotonic() < until:
                    ready, _, _ = select.select(peers, [], [], min(0.05, max(0, until - time.monotonic())))
                    for peer in ready:
                        try:
                            message = aoanet.decode(peer.recv(512), key)
                        except ConnectionResetError:
                            continue
                        self.assertTrue(message["crc_ok"])
                        kind, body = message["type"], message["payload"]
                        if kind == 8:
                            bounce = bytearray(body)
                            bounce[6] = peers.index(peer) + 1
                            send(peer, 9, bytes(bounce))
                        if kind == 0x1B:
                            sequence, kind, body = body[-5:-1], body[-1], body[:-5]
                            identity = peer, sequence
                            copies[identity] = copies.get(identity, 0) + 1
                            if not (peer == peers[1] and kind == 0x2A and hold_launch_ack):
                                send(peer, 0x0F, sequence)
                            if sequence in seen[peer]:
                                continue
                            seen[peer].add(sequence)
                        messages[peer].append((kind, body))

            def bodies(peer, kind):
                return [body for k, body in messages[peer] if k == kind]

            try:
                for peer in peers:
                    peer.bind(("127.0.0.1", 0))
                a, b = peers
                deadline = time.monotonic() + 5
                while not bodies(a, 0x0B):
                    send(a, 10, request())
                    pump(0.1)
                    self.assertLess(time.monotonic(), deadline, "server failed to start")
                    self.assertIsNone(process.poll())
                send(b, 10, request())
                pump(3.5)
                for peer in peers:
                    self.assertEqual(len(bodies(peer, 0x2C)), 1)
                launch = test_station_stub.ProtocolTests.fire_missile()
                wrapped = launch + struct.pack("<I", 100) + b"\x2a"
                send(a, 0x1B, wrapped)
                send(a, 0x1B, wrapped)  # Lost inbound ACK / duplicate launch.
                pump(0.2)
                for peer in peers:
                    self.assertEqual(len(bodies(peer, 0x2A)), 1)
                tag = struct.unpack_from("<I", bodies(a, 0x2A)[0], 0x10)[0]
                impact = struct.pack("<II3fB", tag, stub.player_tag(2), 0, 0, 5000, 1)
                send(b, 0x30, impact)
                send(b, 0x30, impact)
                pump(0.7)
                self.assertEqual(bodies(a, 0x30), [impact])
                self.assertEqual(bodies(b, 0x30), [], "impact overtook unacknowledged launch")
                hold_launch_ack = False
                pump(1.2)
                self.assertEqual(bodies(b, 0x30), [impact])
                self.assertTrue(any(peer == b and n >= 2 for (peer, _), n in copies.items()))
                send(b, 0x37, struct.pack("<I", stub.player_tag(1)))
                send(b, 0x37, struct.pack("<I", stub.player_tag(1)))
                pump(0.3)
                self.assertEqual(bodies(a, 0x38), [struct.pack("<II", stub.player_tag(2), stub.player_tag(1))])
                self.assertEqual(bodies(b, 0x38), [], "death must never echo to victim")
                self.assertEqual(struct.unpack_from("<i", bodies(a, 0x42)[-1], 4 + 0x7F)[0], 1)
                self.assertEqual(struct.unpack_from("<i", bodies(b, 0x42)[-1], 4 + 0x83)[0], 1)
                self.assertEqual(struct.unpack("<3f", bodies(b, 0x24)[-1]), stub.spawn_position(2))
                self.assertIsNone(process.poll())
                # Exhaust the shared budget through real combat traffic.
                # Retiring a peer during broadcast must not crash iteration
                # or allow the 31st event to evict an old duplicate ID.
                for sequence in range(101, 116):
                    before = len(bodies(a, 0x2A))
                    send(a, 0x1B, launch + struct.pack("<I", sequence) + b"\x2a")
                    pump(0.1)
                    if len(bodies(a, 0x2A)) == before:
                        break
                    tag = struct.unpack_from("<I", bodies(a, 0x2A)[-1], 0x10)[0]
                    send(b, 0x30, struct.pack("<II3fB", tag, stub.player_tag(2), 0, 0, 5000, 1))
                    pump(0.1)
                self.assertEqual(len(seen[a]), 30)
                self.assertLessEqual(len(seen[b]), 30)
                pump(0.2)
                messages[a].clear()
                send(a, 10, request())
                pump(0.2)
                self.assertFalse(bodies(a, 0x0B), "retired endpoint was readmitted")
                self.assertIsNone(process.poll())
            finally:
                for peer in peers:
                    peer.close()
                process.terminate()
                _, stderr = process.communicate(timeout=5)
                self.assertNotIn("Traceback", stderr.decode(errors="replace"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
