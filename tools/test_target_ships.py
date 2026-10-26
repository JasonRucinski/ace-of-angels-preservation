"""Server-spawned target ships: layout, damage, destruction and relay delivery (findings 9.45, 9.46).

Synthetic loopback only; no game process.
"""
import math
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
import relay_motion
import station_stub as stub
import vessel_combat
import test_station_stub
from test_station_stub import request

fire_missile = test_station_stub.ProtocolTests.fire_missile  # Module import keeps its tests out of this run

# A real 2.9.2 client's 0x1F upload (Ym Khtat, slot 1) while its guns hit
# Target 1: mask 0x80000804, submask 2 = three perceived-damage entries.
HIT_REPORT = bytes.fromhex("008001000408008000000040000200000003020001400301020001400401020001400201")
HIT_ENTRIES = [(0x40010002, 3, 1), (0x40010002, 4, 1), (0x40010002, 2, 1)]


class LayoutTests(unittest.TestCase):
    def test_load_object_fields(self):
        ships = stub.TargetShips(3, (100.0, -50.0, 2000.0))
        loads = ships.loads()
        self.assertEqual([kind for kind, _ in loads], [0x25] * 3)
        for n, (_, p) in enumerate(loads):
            self.assertEqual(len(p), 0xBF)  # SendLoadObject 0x48A460
            self.assertEqual(p[0x20:0x40].rstrip(b"\0"), b"AoAObjects.odb")
            self.assertEqual(p[0x40:0x60].rstrip(b"\0"), f"Target {n + 1}".encode())
            self.assertIn(p[:0x20].rstrip(b"\0").decode(), stub.SELECTABLE_VESSELS)
            # World-object tag (index = low word), non-terrain kind 0x11.
            self.assertEqual(struct.unpack_from("<II", p, 0x60), (0x40010002 + n, 0x11))
            self.assertEqual(struct.unpack_from("<I", p, 0x8C)[0], 0)   # client makes its own team
            self.assertEqual((p[0x90], p[0x91]), (3, 3))                 # Hostile, as in the player load
            self.assertEqual(p[0xBA:], bytes(5))                         # no auto-target, world's zone
        positions = [struct.unpack_from("<3f", p, 0x92) for _, p in loads]
        self.assertEqual(positions[1], (100.0, -50.0, 2000.0 + stub.TargetShips.DISTANCE))
        for x, y, z in positions:
            self.assertAlmostEqual(math.dist((x, z), (100.0, 2000.0)), stub.TargetShips.DISTANCE, places=2)
            self.assertGreater(z, 2000.0)  # ahead: ships face +z at spawn
            self.assertEqual(y, -50.0)
        self.assertLess(positions[0][0], positions[1][0])
        self.assertLess(positions[1][0], positions[2][0])

    def test_one_ship_is_straight_ahead_and_counts_are_bounded(self):
        _, p = stub.TargetShips(1).loads()[0]
        self.assertEqual(struct.unpack_from("<3f", p, 0x92), (0.0, 0.0, stub.TargetShips.DISTANCE))
        self.assertEqual(len(stub.TargetShips(98).loads()), 98)
        self.assertEqual(stub.TargetShips.tag(stub.TargetShips.LAST_INDEX), 0x40010063)  # below power-ups (100)
        for count in (0, 99):
            with self.assertRaises(ValueError):
                stub.TargetShips(count)


class PerceivedDamageTests(unittest.TestCase):
    def test_real_upload(self):
        prefix = stub.movement_update(HIT_REPORT, 1)
        mask = struct.unpack_from("<I", HIT_REPORT, 4)[0]
        self.assertEqual(relay_motion.perceived_damage(HIT_REPORT, len(prefix), mask), HIT_ENTRIES)
        with self.assertRaises(ValueError):
            relay_motion.perceived_damage(HIT_REPORT[:-1], len(prefix), mask)
        # No 0x80000000 block, or one without submask 2: no entries.
        self.assertEqual(relay_motion.perceived_damage(HIT_REPORT, len(prefix), mask & 0x7FFFFFFF), [])
        no_list = HIT_REPORT[:len(prefix)] + struct.pack("<I", 0x100) + bytes(12)
        self.assertEqual(relay_motion.perceived_damage(no_list, len(prefix), mask), [])


class DamageTests(unittest.TestCase):
    def setUp(self):
        self.ships = stub.TargetShips(2)  # Target 1 Ym Khtat (index 2), Target 2 Vermok (index 3)

    def test_gun_damage_matches_the_client(self):
        # Gun-360 (system 6 of a Ym Khtat) deals 28 x 0.8 x 0.5 = 11.2: a live
        # client's own copy dropped from 107 to 95.8 on one such hit.
        self.assertEqual(vessel_combat.VESSELS["Ym Khtat"], (107.0, {2: 21, 3: 21, 4: 21, 5: 21, 6: 28, 7: 28}))
        self.assertEqual(self.ships.gun_hits("Ym Khtat", [(0x40010002, 6, 1)], 0), [])
        self.assertAlmostEqual(self.ships.hp[2], 95.8, places=4)
        self.assertEqual(self.ships.gun_hits("Ym Khtat", HIT_ENTRIES, 0), [])
        self.assertAlmostEqual(self.ships.hp[2], 95.8 - 3 * 8.4, places=4)

    def test_ignored_reports(self):
        for vessel, entries in (("Ym Khtat", [(0x80010002, 6, 1)]),   # a player: victim-side damage
                                ("Ym Khtat", [(0x40010004, 6, 1)]),   # no such ship
                                ("Ym Khtat", [(0x40020002, 6, 1)]),   # wrong high word
                                ("Ym Khtat", [(0x40010002, 9, 1)]),   # not one of its guns
                                ("Ym Khtat", [(0x40010002, 6, 0)]),
                                ("Ym Khtat", [(0x40010002, 6, 17)]),  # implausible count
                                ("No Such Ship", [(0x40010002, 6, 1)])):
            self.assertEqual(self.ships.gun_hits(vessel, entries, 0), [])
        self.assertEqual(self.ships.hp, {2: 107.0, 3: 66.0})

    def test_destroy_once_then_respawn(self):
        died = self.ships.gun_hits("Ym Khtat", [(0x40010002, 6, 10)], 5.0)  # 112 >= 107
        self.assertEqual(died, [(2, (0x45, struct.pack("<HB", 2, 1)))])     # RemoveObject, blow up
        self.assertEqual(self.ships.gun_hits("Ym Khtat", [(0x40010002, 6, 10)], 5.1), [])
        self.assertIsNone(self.ships.missile_hit(0x40010002, "Type II 1.1", 5.2))
        self.assertEqual([struct.unpack_from("<I", p, 0x60)[0] for _, p in self.ships.loads()], [0x40010003])
        self.assertEqual(self.ships.respawns(5.0 + stub.TargetShips.RESPAWN - 0.1), [])
        self.assertEqual(self.ships.respawns(5.0 + stub.TargetShips.RESPAWN), [self.ships.load(2)])
        self.assertEqual((self.ships.hp[2], self.ships.destroyed, len(self.ships.loads())), (107.0, 1, 2))

    def test_missile_damage(self):
        self.assertIsNone(self.ships.missile_hit(0x40010003, "Type II 1.1", 0))
        self.assertIsNone(self.ships.missile_hit(0x40010003, "Type III 1.1", 0))
        self.assertIsNone(self.ships.missile_hit(0x40010003, None, 0))  # unknown name: Type II
        self.assertEqual(self.ships.hp[3], 66.0 - 10.0 - 12.0 - 10.0)
        self.assertIsNone(self.ships.missile_hit(0x80010002, "Type II 1.1", 0))


class MissileTests(unittest.TestCase):
    def setUp(self):
        self.ships = stub.TargetShips(2)
        self.ledger = stub.MissileLedger(map(stub.TargetShips.tag, self.ships.ships))
        self.slots = {1: "a", 2: "b"}

    def test_launch_and_impact_at_a_target_ship(self):
        kind, body = self.ledger.launch(1, fire_missile(target=0x40010003), self.slots, 0)
        self.assertEqual(kind, 0x2A)
        tag = struct.unpack_from("<I", body, 0x10)[0]
        impact = struct.pack("<II3fB", tag, 0x40010003, 0.0, 0.0, 12000.0, 1)
        self.assertIsNone(self.ledger.impact(2, impact, self.slots, 1))  # only the shooter reports it
        self.assertEqual(self.ledger.impact(1, impact, self.slots, 1), (0x30, impact))
        self.assertIsNone(self.ledger.impact(1, impact, self.slots, 1))

    def test_other_objects_stay_rejected(self):
        for target in (0x40010001, 0x40010004, 0x40000064):  # test object, no such ship, a power-up
            self.assertIsNone(self.ledger.launch(1, fire_missile(target=target), self.slots, 0))
        self.assertIsNone(stub.MissileLedger().launch(1, fire_missile(target=0x40010002), self.slots, 0))
        tag = struct.unpack_from("<I", self.ledger.launch(1, fire_missile(), self.slots, 0)[1], 0x10)[0]
        stray = struct.pack("<II3fB", tag, 0x40010001, 0.0, 0.0, 0.0, 1)
        self.assertIsNone(self.ledger.impact(1, stray, self.slots, 1))
        self.ledger.discard(1)  # an object target leaves only the shooter to expire on
        self.assertEqual(self.ledger.live, {})


class RelayTests(unittest.TestCase):
    def test_ships_on_entry_missile_echo_destruction_and_late_join(self):
        key = bytes(range(256))
        with tempfile.TemporaryDirectory(prefix="aoa-targets-") as tmp:
            folder = Path(tmp)
            (folder / "key").write_bytes(key)
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
                probe.bind(("127.0.0.1", 0))
                endpoint = probe.getsockname()
            process = subprocess.Popen(
                [sys.executable, "-I", str(Path(stub.__file__)), str(folder / "key"), str(folder / "log"),
                 "--port", "0", "--arena", "--arena-port", str(endpoint[1]), "--ack", "--experimental-relay",
                 "--target-ships", "3", "--spawn-at", "0", "0", "-30000", "--peer-timeout", "8", "--seconds", "20"],
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
                expected = stub.TargetShips(3, (0.0, 0.0, -30000.0)).loads()
                for peer in (a, b):
                    self.assertEqual(bodies(peer, 0x25), [p for _, p in expected])
                send(a, 0x2A, fire_missile(target=0x40010003))
                pump(0.5)
                for peer in (a, b):
                    echo = bodies(peer, 0x2A)
                    self.assertEqual(len(echo), 1)
                    self.assertEqual(struct.unpack_from("<I", echo[0], 4)[0], 0x40010003)
                # Five real hit reports (3 x Gun310 each, 25.2) destroy Target 1 (107 HP).
                for n in range(5):
                    self.assertEqual(bodies(a, 0x45), [], n)
                    send(a, 0x1F, HIT_REPORT)
                    pump(0.2)
                for peer in (a, b):
                    self.assertEqual(bodies(peer, 0x45), [struct.pack("<HB", 2, 1)])
                send(late, 10, request())
                pump(3.5)
                self.assertEqual(bodies(late, 0x25), [p for _, p in expected[1:]])  # not the destroyed ship
                self.assertIsNone(process.poll())
            finally:
                for peer in peers:
                    peer.close()
                process.terminate()
                stdout, stderr = process.communicate(timeout=5)
                self.assertNotIn("Traceback", stderr.decode(errors="replace"))
            self.assertIn(b"target ships: 3", stdout)


if __name__ == "__main__":
    unittest.main()
