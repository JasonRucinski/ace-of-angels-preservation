"""Power-up zones, spawn/move layouts and the relay's pickup path (findings 9.44).

Synthetic loopback only; no game process.
"""
import random
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
import decode_trn
import station_stub as stub
from test_station_stub import request


def record(kind, position=(0.0, 0.0, 0.0), half=0.0, value=0):
    """One 540-byte 2.9.2 terrain record with the fields ReadInTerrain passes on."""
    r = bytearray(decode_trn.REC_292)
    struct.pack_into("<3f", r, 0xC4, *position)
    struct.pack_into("<f", r, 0x104, half)
    struct.pack_into("<I", r, 0x194, value)
    struct.pack_into("<I", r, 0x200, kind)
    struct.pack_into("<I", r, decode_trn.REC_292 - 4, decode_trn.SENTINEL)
    return bytes(r)


def terrain(*records):
    return struct.pack("<I", len(records)) + b"".join(records)


ZONES = terrain(record(0, (9.0, 9.0, 9.0)),                      # A static model
                record(6, (1000.0, -2000.0, 30000.0), 500.0, 3),  # Shield +20
                record(2, (0.0, 0.0, 0.0), 2000.0, 0),            # A safe zone
                record(6, (-5000.0, 0.0, 0.0), 1000.0, 0))        # Missile


class ZoneTests(unittest.TestCase):
    def test_reads_only_kind_6_records(self):
        zones = decode_trn.powerup_zones_292(ZONES)
        self.assertEqual([(z["type"], z["half"]) for z in zones], [(3, 500.0), (0, 1000.0)])
        self.assertEqual(zones[0]["position"], (1000.0, -2000.0, 30000.0))

    def test_rejects_truncated_or_unsentineled_files(self):
        with self.assertRaises(ValueError):
            decode_trn.powerup_zones_292(ZONES[:-1])
        with self.assertRaises(ValueError):
            decode_trn.powerup_zones_292(terrain(record(6)[:-4] + bytes(4)))


class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.zones = decode_trn.powerup_zones_292(ZONES)
        self.powerups = stub.PowerUps(self.zones, random.Random(7))

    def test_spawn_layout_matches_the_2_7_1_sender(self):
        spawns = self.powerups.spawns()
        self.assertEqual([kind for kind, _ in spawns], [0x43, 0x43])
        for (_, body), zone, index in zip(spawns, self.zones, (100, 101)):
            self.assertEqual(len(body), 17)
            x, y, z, kind, tag = struct.unpack("<3iBI", body)
            self.assertEqual((kind, tag), (zone["type"], 0x40000000 | index))
            for c, centre in zip((x, y, z), zone["position"]):
                self.assertLessEqual(abs(c - centre), zone["half"] + 1)

    def test_pickup_moves_inside_the_zone_and_hides_for_five_seconds(self):
        tag = struct.pack("<I", 0x40000000 | 101)
        name, (kind, body) = self.powerups.pickup(tag, now=10.0)
        self.assertEqual((name, kind, len(body)), ("Missile Power Up", 0x53, 14))
        index, *position = struct.unpack("<H3f", body)
        self.assertEqual(index, 101)
        for c, centre in zip(position, self.zones[1]["position"]):
            self.assertLessEqual(abs(c - centre), self.zones[1]["half"] + 1e-3)
        self.assertIsNone(self.powerups.pickup(tag, now=14.9), "taken while hidden")
        self.assertIsNotNone(self.powerups.pickup(tag, now=15.0))
        self.assertEqual(self.powerups.taken, 2)
        # Late joiners get the moved position.
        spawned = struct.unpack("<3iBI", self.powerups.spawns()[1][1])[:3]
        self.assertEqual(spawned, tuple(int(c) for c in self.powerups.items[101][1]))

    def test_rejects_unknown_tags_and_bad_sizes(self):
        for payload in (struct.pack("<I", 0x40000000 | 102), struct.pack("<I", 0x40010000 | 100),
                        struct.pack("<I", 100), b"\x64\x00\x00", bytes(5)):
            self.assertIsNone(self.powerups.pickup(payload, now=0.0), payload.hex())
        self.assertEqual(self.powerups.taken, 0)

    def test_rejects_zones_the_client_or_fields_cannot_hold(self):
        for zone in ({"position": (0.0, 0.0, 0.0), "half": 1.0, "type": 5},
                     {"position": (9.9e6, 0.0, 0.0), "half": 2e5, "type": 0},
                     {"position": (float("nan"), 0.0, 0.0), "half": 1.0, "type": 0}):
            with self.assertRaises(ValueError):
                stub.PowerUps([zone])
        with self.assertRaises(ValueError):
            stub.PowerUps([{"position": (0.0, 0.0, 0.0), "half": 1.0, "type": 0}] * 401)


class RelayTests(unittest.TestCase):
    def test_spawn_on_entry_pickup_broadcast_and_late_join(self):
        key = bytes(range(256))
        with tempfile.TemporaryDirectory(prefix="aoa-powerups-") as tmp:
            folder = Path(tmp)
            (folder / "key").write_bytes(key)
            (folder / "zones.trn").write_bytes(ZONES)
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
                probe.bind(("127.0.0.1", 0))
                endpoint = probe.getsockname()
            process = subprocess.Popen(
                [sys.executable, "-I", str(Path(stub.__file__)), str(folder / "key"), str(folder / "log"),
                 "--port", "0", "--arena", "--arena-port", str(endpoint[1]), "--ack", "--experimental-relay",
                 "--powerup-zones", str(folder / "zones.trn"), "--peer-timeout", "8", "--seconds", "20"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            peers = [socket.socket(socket.AF_INET, socket.SOCK_DGRAM) for _ in range(3)]
            messages = {p: [] for p in peers}

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
                        if message["type"] == 8:
                            bounce = bytearray(message["payload"])
                            bounce[6] = peers.index(peer) + 1
                            send(peer, 9, bytes(bounce))
                        messages[peer].append((message["type"], message["payload"]))

            def bodies(peer, kind):
                return [body for k, body in messages[peer] if k == kind]

            try:
                for peer in peers:
                    peer.bind(("127.0.0.1", 0))
                a, b, late = peers
                deadline = time.monotonic() + 5
                while not bodies(a, 0x0B):
                    send(a, 10, request())
                    pump(0.1)
                    self.assertLess(time.monotonic(), deadline, "server failed to start")
                    self.assertIsNone(process.poll())
                send(b, 10, request())
                pump(3.5)
                for peer in (a, b):
                    self.assertEqual([struct.unpack("<3iBI", s)[3:] for s in bodies(peer, 0x43)],
                                     [(3, 0x40000064), (0, 0x40000065)])
                send(a, 0x44, struct.pack("<I", 0x40000065))
                send(b, 0x44, struct.pack("<I", 0x40000065))  # A second pickup while hidden
                send(a, 0x44, struct.pack("<I", 0x40000066))  # No such power-up
                pump(0.5)
                for peer in (a, b):
                    moves = bodies(peer, 0x53)
                    self.assertEqual(len(moves), 1)
                    self.assertEqual(struct.unpack_from("<H", moves[0])[0], 101)
                moved = struct.unpack("<3f", bodies(a, 0x53)[0][2:])
                send(late, 10, request())
                pump(3.5)
                spawned = [struct.unpack("<3iBI", s) for s in bodies(late, 0x43)]
                self.assertEqual(spawned[1][:3], tuple(int(c) for c in moved))
                self.assertIsNone(process.poll())
            finally:
                for peer in peers:
                    peer.close()
                process.terminate()
                stdout, stderr = process.communicate(timeout=5)
                self.assertNotIn("Traceback", stderr.decode(errors="replace"))
            self.assertIn(b"power-ups: 2 from zones.trn", stdout)


if __name__ == "__main__":
    unittest.main()
