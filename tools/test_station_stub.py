"""Local protocol regression checks: python -I tools/test_station_stub.py.

Uses a synthetic cipher key and ephemeral localhost Station ports. Does not
launch the game, use its credentials, or contact any historical service.
"""
import json
import math
import random
import socket
import select
import struct
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import aoacrypt
import aoanet
import aoapack
import station_stub as stub
import relay_motion


def request():
    payload = bytearray(381)
    payload[1:5] = (9).to_bytes(4, "little")
    payload[5:9] = (2).to_bytes(4, "little")
    payload[9:13] = (2).to_bytes(4, "little")
    payload[31:40] = b"testpilot"
    return bytes(payload)


class ProtocolTests(unittest.TestCase):
    def test_ordered_combat_delivery(self):
        delivery = stub.ReliableRemovals(ordered=True)
        launch = delivery.queue_message("a", 0x2A, b"launch", 0)
        self.assertEqual(delivery.queue_message("a", 0x30, b"impact", 0), ())
        self.assertEqual(delivery.queue("a", 2, 0), ())
        # A guessed ACK must not remove an event that has never been sent.
        self.assertFalse(delivery.acknowledge("a", struct.pack("<I", 2), now=0))
        self.assertEqual(delivery.due(0.5), ([("a", launch)], set()))
        self.assertTrue(delivery.acknowledge("a", launch[1][-5:-1], now=0.6))
        packets, failed = delivery.due(0.6)
        self.assertFalse(failed)
        self.assertEqual(len(packets), 1)
        impact = packets[0][1]
        self.assertEqual(impact[1][:-5], b"impact")
        self.assertTrue(delivery.acknowledge("a", impact[1][-5:-1], now=0.7))
        removal = delivery.due(0.7)[0][0][1]
        self.assertEqual(removal[1][:-5], b"\x02")
        self.assertEqual(delivery.sent["a"], 3)
        # Queued traffic has a deadline too; no unbounded backlog.
        self.assertEqual(delivery.due(2.5), ([], {"a"}))

    def test_essential_events_share_history_budget(self):
        delivery = stub.ReliableRemovals(ordered=True)
        for index in range(30):
            packet = delivery.queue_message("a", (0x2A, 0x30, 0x38)[index % 3], b"event", index)
            self.assertTrue(packet)
            self.assertTrue(delivery.acknowledge("a", packet[1][-5:-1], now=index))
        self.assertIsNone(delivery.queue("a", 2, 31))
        self.assertIsNone(delivery.queue_message("a", 0x81, b"", 31))
        self.assertEqual(delivery.pending, {})

    def test_ordered_delivery_impairment_matrix(self):
        # Virtual time exercises the requested RTT/loss grid, ACK loss,
        # duplication, jitter and reordering without sleeping or networking.
        for rtt in (0.030, 0.080, 0.150):
            for loss in (0, 0.01, 0.03):
                for seed in range(10):
                    rng = random.Random(seed)
                    delivery = stub.ReliableRemovals(deadline=30, ordered=True)
                    flights, seen, applied = [], set(), []

                    def transmit(packet, now):
                        if rng.random() >= loss:
                            flights.append((now + rtt / 2 + rng.random() * rtt, "data", packet))
                            if rng.random() < 0.15:
                                flights.append((now + rtt * 3, "data", packet))

                    for index in range(30):
                        packet = delivery.queue_message("a", 0x38, bytes([index]), 0)
                        if packet:
                            transmit(packet, 0)
                    for tick in range(3001):
                        now = tick / 100
                        ready = sorted((item for item in flights if item[0] <= now), key=lambda item: item[0])
                        flights = [item for item in flights if item[0] > now]
                        for _, kind, packet in ready:
                            if kind == "ack":
                                delivery.acknowledge("a", packet, now=now)
                            else:
                                sequence = packet[1][-5:-1]
                                if sequence not in seen:
                                    seen.add(sequence)
                                    applied.append(packet[1][0])
                                if rng.random() >= loss:
                                    flights.append((now + rtt / 2, "ack", sequence))
                        packets, failed = delivery.due(now)
                        self.assertFalse(failed, (rtt, loss, seed))
                        for _, packet in packets:
                            transmit(packet, now)
                        if not delivery.pending and not flights:
                            break
                    self.assertEqual(applied, list(range(30)), (rtt, loss, seed))
                    self.assertFalse(delivery.pending)

    def test_reliable_removal_delivery(self):
        delivery = stub.ReliableRemovals()
        a, b = ("127.0.0.1", 1), ("127.0.0.1", 2)
        packet = delivery.queue(a, 2, 0)
        seq = packet[1][-5:-1]
        self.assertEqual(packet, (0x1B, b"\x02" + seq + b"\x2d"))
        self.assertFalse(delivery.acknowledge(b, seq))
        self.assertFalse(delivery.acknowledge(a, seq[:3]))
        self.assertFalse(delivery.acknowledge(a, seq + b"\0"))
        self.assertFalse(delivery.acknowledge(a, bytes(4)))
        self.assertEqual(delivery.due(0.49), ([], set()))
        # Backoff 0.5, 1, 2 ... seconds until the default 2.5-second deadline.
        self.assertEqual(delivery.due(0.5), ([(a, packet)], set()))
        self.assertEqual(delivery.due(1.0), ([], set()))
        self.assertEqual(delivery.due(1.5), ([(a, packet)], set()))
        self.assertEqual(delivery.due(2.49), ([], set()))
        self.assertEqual(delivery.due(2.5), ([], {a}))
        patient = stub.ReliableRemovals(deadline=30)
        packet = patient.queue(a, 2, 0)
        times = [t / 10 for t in range(1, 400) if patient.due(t / 10)[0]]
        self.assertEqual(times, [0.5, 1.5, 3.5, 7.5, 11.5, 15.5, 19.5, 23.5, 27.5])
        self.assertEqual(patient.due(30), ([], {a}))
        delivery.discard(a)
        self.assertEqual(delivery.due(100), ([], set()))
        packet = delivery.queue(b, 3, 101)
        self.assertNotEqual(packet[1][-5:-1], seq)
        self.assertTrue(delivery.acknowledge(b, packet[1][-5:-1]))
        self.assertFalse(delivery.acknowledge(b, packet[1][-5:-1]))
        self.assertEqual(delivery.due(102), ([], set()))

    def test_reliable_removal_history_bound(self):
        delivery = stub.ReliableRemovals()
        for slot in range(1, 31):
            packet = delivery.queue("observer", slot, 0)
            self.assertIsNotNone(packet)
            self.assertTrue(delivery.acknowledge("observer", packet[1][-5:-1]))
        self.assertIsNone(delivery.queue("observer", 31, 1))
        self.assertEqual(delivery.pending, {})
        delivery.sequence = 0xFFFFFFFF
        packet = delivery.queue("other", 1, 1)
        self.assertEqual(packet[1][-5:-1], b"\xff" * 4)
        self.assertIsNone(delivery.queue("other", 2, 1))

    def test_collision_target_validation(self):
        slots = {1: "a", 2: "b"}
        good = struct.pack("<II3f", 0x80010001, 0x80010002, 0, 0, 0)
        self.assertEqual(stub.collision_target(good, 1, slots), 2)
        for payload, sender in (
                (good, 2),                                                        # forged source
                (good[:19], 1),                                                   # size
                (struct.pack("<II3f", 0x80010001, 0x80010001, 0, 0, 0), 1),       # self target
                (struct.pack("<II3f", 0x80010001, 0x80010003, 0, 0, 0), 1),       # not loaded
                (struct.pack("<II3f", 0x80010001, 0x40010001, 0, 0, 0), 1),       # not a player
                (struct.pack("<II3f", 0x80010001, 0x80010002, math.nan, 0, 0), 1)):
            self.assertIsNone(stub.collision_target(payload, sender, slots))

    def test_team_records(self):
        kind, body = stub.object_to_team(0x80010002, stub.ffa_team(2))
        self.assertEqual((kind, len(body)), (0x50, 0x2E))
        # Tag, team id, and the team leader (the player itself; 0 crashed the
        # client's "Wingleader:" message in 0x432100).
        self.assertEqual(struct.unpack_from("<III", body), (0x80010002, 2, 0x80010002))
        self.assertTrue(body[0x0C:].startswith(b"Team2\0"))
        plain = stub.load_player(3)[1]
        teamed = stub.load_player(3, team=stub.ffa_team(3))[1]
        self.assertEqual(struct.unpack_from("<I", plain, 0x40)[0], 0)
        self.assertEqual(struct.unpack_from("<I", teamed, 0x40)[0], 3)
        self.assertTrue(teamed[0x2C:0x40].startswith(b"Team3\0"))
        self.assertEqual(plain[:0x2C] + plain[0x44:], teamed[:0x2C] + teamed[0x44:])
        # Same-team and other-team relation: Hostile (index 3, client value 4).
        # Friendly (0) made LaunchActiveMissiles refuse every target.
        self.assertEqual((plain[0x44], plain[0x45]), (3, 3))

    @staticmethod
    def fire_missile(target=0x80010002, shooter=0x80010001, count=1, lock=100.0):
        """A launch shaped like the real client's (stack bytes after names)."""
        p = bytearray(0x92)
        struct.pack_into("<fIII", p, 0, lock, target, shooter, count)
        stack = bytes.fromhex("18000000688c5303acf71900b4f71900ffffffff")
        p[0x50:0x70] = (b"Type II 1.1\0" + stack)[:0x20]
        p[0x70:0x90] = (b"Rack IIB a\0\0" + stack)[:0x20]
        return bytes(p)

    def test_missile_launch_echo(self):
        ledger = stub.MissileLedger()
        slots = {1: "a", 2: "b"}
        kind, body = ledger.launch(1, self.fire_missile(count=2), slots, 0)
        self.assertEqual((kind, len(body)), (0x2A, 0x92))
        tags = struct.unpack_from("<16I", body, 0x10)
        self.assertEqual([t >> 24 for t in tags[:2]], [0x40, 0x40])  # 0x40CCIIII object tags
        self.assertTrue(all(500 <= t & 0xFFFF <= 999 for t in tags[:2]))
        self.assertNotEqual(tags[0], tags[1])
        self.assertEqual(tags[2:], (0,) * 14)
        self.assertEqual(body[:0x10], self.fire_missile(count=2)[:0x10])
        # Names are kept; the client's leftover stack bytes are not relayed.
        self.assertEqual(body[0x50:0x70], b"Type II 1.1".ljust(32, b"\0"))
        self.assertEqual(body[0x70:0x90], b"Rack IIB a".ljust(32, b"\0"))
        rejected = (
            (2, self.fire_missile()),                        # shooter tag is not the sender
            (1, self.fire_missile(target=0x80010001)),       # self target
            (1, self.fire_missile(target=0x80010003)),       # target not loaded
            (1, self.fire_missile(target=0x40010001)),       # not a player
            (1, self.fire_missile(count=0)),
            (1, self.fire_missile(count=17)),
            (1, self.fire_missile(lock=math.nan)),
            (1, self.fire_missile(lock=101.0)),
            (1, self.fire_missile()[:-1]),
            (1, self.fire_missile()[:0x10] + b"\1" + self.fire_missile()[0x11:]),  # tags preset
            (1, self.fire_missile()[:0x50] + bytes(0x20) + self.fire_missile()[0x70:]),  # no name
        )
        for sender, payload in rejected:
            self.assertIsNone(ledger.launch(sender, payload, slots, 0))
        # At most 16 live missiles per shooter.
        for _ in range(7):
            self.assertIsNotNone(ledger.launch(1, self.fire_missile(count=2), slots, 0))
        self.assertIsNone(ledger.launch(1, self.fire_missile(), slots, 0))
        self.assertIsNotNone(ledger.launch(1, self.fire_missile(), slots, stub.MissileLedger.LIFETIME))

    def test_missile_impact_once(self):
        ledger = stub.MissileLedger()
        slots = {1: "a", 2: "b", 3: "c"}
        tag = struct.unpack_from("<I", ledger.launch(1, self.fire_missile(), slots, 0)[1], 0x10)[0]

        def impact(missile=tag, hit=0x80010002, x=0.0, flag=1):
            return struct.pack("<II3fB", missile, hit, x, 0.0, 5000.0, flag)

        for sender, payload in ((3, impact()),                     # neither shooter nor target
                                (2, impact(missile=tag + 1)),      # unknown missile
                                (2, impact(hit=0x80010009)),       # hit player not loaded
                                (2, impact(hit=0x40010001)),       # not a player
                                (2, impact(x=math.inf)),
                                (2, impact(flag=2)),
                                (2, impact()[:-1])):
            self.assertIsNone(ledger.impact(sender, payload, slots, 1))
        self.assertEqual(ledger.impact(2, impact(), slots, 1), (0x30, impact()))
        self.assertIsNone(ledger.impact(1, impact(), slots, 1))  # Already applied.
        # A miss (hit tag 0) from the shooter also ends the missile.
        tag = struct.unpack_from("<I", ledger.launch(1, self.fire_missile(), slots, 2)[1], 0x10)[0]
        self.assertIsNotNone(ledger.impact(1, impact(missile=tag, hit=0), slots, 3))
        tag = struct.unpack_from("<I", ledger.launch(1, self.fire_missile(), slots, 4)[1], 0x10)[0]
        ledger.discard(2)
        self.assertIsNone(ledger.impact(1, impact(missile=tag), slots, 5))

    def test_match_limits_and_announcement(self):
        match = stub.Match(kill_limit=3, time_limit=60)
        self.assertIsNone(match.ended({}, 0))
        match.start(100)
        match.start(150)  # Already running: the start time is kept.
        self.assertIsNone(match.ended({1: 2}, 159))
        self.assertEqual(match.ended({1: 3}, 101), "kill limit")
        self.assertEqual(match.ended({}, 160), "time limit")
        names = {1: "Alpha", 2: "Bravo"}
        self.assertEqual(match.result({1: 3, 2: 1}, names), "Match 1 over: Alpha wins with 3 kills")
        self.assertEqual(match.result({1: 2, 2: 2}, names), "Match 1 over: tie at 2 kills (Alpha, Bravo)")
        self.assertEqual(match.result({}, names), "Match 1 over: no kills")
        match.next(200)
        self.assertEqual((match.number, match.started), (2, 200))
        match.stop()
        self.assertIsNone(match.ended({}, 10_000))
        unlimited = stub.Match(0, 0)
        unlimited.start(0)
        self.assertIsNone(unlimited.ended({1: 999}, 10 ** 6))
        kind, body = stub.arena_message("Match 1 over" + "x" * 400)
        self.assertEqual((kind, len(body)), (0x21, 0x126))
        self.assertEqual(struct.unpack_from("<H", body, 3)[0], 3)
        self.assertTrue(body[0x25:].startswith(b"Match 1 over"))
        self.assertEqual(body[-1], 0)  # Always NUL-terminated.

    def test_death_ledger(self):
        ledger, slots = stub.DeathLedger(), {1: "a", 2: "b"}
        killed = ledger.report(1, struct.pack("<I", 0x80010002), slots, 10)
        self.assertEqual(killed, (0x38, struct.pack("<II", 0x80010001, 0x80010002)))
        self.assertIsNone(ledger.report(1, struct.pack("<I", 0x80010002), slots, 11))  # repeat copy
        for now, killer in ((20, 0x80010001), (30, 0x80010009), (40, 0x40010001)):  # self, unknown, object
            self.assertEqual(ledger.report(1, struct.pack("<I", killer), slots, now)[1][4:], bytes(4))
        self.assertIsNone(ledger.report(2, b"\0\0\0", slots, 50))
        self.assertEqual((ledger.kills, ledger.deaths), ({2: 1}, {1: 4}))

    def test_inbound_reliable_history(self):
        history = stub.InboundReliable()
        a, b = (5033, ("127.0.0.1", 1)), (5031, ("127.0.0.1", 1))
        self.assertTrue(history.first(a, b"\0\0\0\0"))  # No pre-filled zero.
        self.assertFalse(history.first(a, b"\0\0\0\0"))
        self.assertTrue(history.first(b, b"\0\0\0\0"), "channels share a history")
        for seq in range(1, history.WINDOW + 1):
            self.assertTrue(history.first(a, struct.pack("<I", seq)))
        # The documented limit: an ID older than the window is new again.
        self.assertTrue(history.first(a, b"\0\0\0\0"))
        self.assertFalse(history.first(a, struct.pack("<I", history.WINDOW)))
        self.assertEqual(history.duplicates, 2)
        for port in range(history.MAX_ENDPOINTS + 10):
            history.first((port, ("127.0.0.1", 2)), b"x")
        self.assertEqual(len(history.history), history.MAX_ENDPOINTS)

    def test_reliable_duplicates_acknowledged_once_dispatched(self):
        key = bytes(range(256))
        with tempfile.TemporaryDirectory(prefix="aoa-dedup-") as tmp:
            folder = Path(tmp)
            (folder / "key").write_bytes(key)
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
                probe.bind(("127.0.0.1", 0))
                endpoint = ("127.0.0.1", probe.getsockname()[1])
            proc = subprocess.Popen(
                [sys.executable, "-I", str(Path(stub.__file__)), str(folder / "key"),
                 str(folder / "log"), "--port", str(endpoint[1]), "--ack", "--seconds", "4"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as a, \
                        socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as b:
                    received = {a: [], b: []}

                    def pump(seconds):
                        end = time.monotonic() + seconds
                        while time.monotonic() < end:
                            ready, _, _ = select.select([a, b], [], [], 0.05)
                            for peer in ready:
                                try:
                                    received[peer].append(aoanet.decode(peer.recv(512), key))
                                except ConnectionResetError:
                                    pass

                    a.bind(("127.0.0.1", 0))
                    b.bind(("127.0.0.1", 0))
                    deadline = time.monotonic() + 3
                    while not any(m["type"] == 0x0B for m in received[a]):
                        a.sendto(aoanet.encode(0x0A, request(), key), endpoint)
                        pump(0.1)
                        self.assertLess(time.monotonic(), deadline, "Station did not start")
                    b.sendto(aoanet.encode(0x0A, request(), key), endpoint)
                    pump(0.2)
                    # The same ID from another endpoint is independent.
                    quit_packet = b"\x00" + struct.pack("<I", 7) + b"\x4e"
                    for peer in (a, a, a, b):
                        peer.sendto(aoanet.encode(0x1B, quit_packet, key), endpoint)
                    pump(0.3)
                    for peer, copies in ((a, 3), (b, 1)):
                        acks = [m["payload"] for m in received[peer] if m["type"] == 0x0F]
                        self.assertEqual(acks, [struct.pack("<I", 7)] * copies)
                stdout, _ = proc.communicate(timeout=10)
                self.assertIn("reliable_duplicates=2", stdout)
                self.assertIn("'station_departure': 2", stdout)
            finally:
                if proc.poll() is None:
                    proc.kill()
                    proc.communicate(timeout=5)

    def test_arena_departure_and_expiry(self):
        key = bytes(range(256))
        with tempfile.TemporaryDirectory(prefix="aoa-departure-") as tmp:
            folder = Path(tmp)
            (folder / "key").write_bytes(key)
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
                probe.bind(("127.0.0.1", 0))
                endpoint = ("127.0.0.1", probe.getsockname()[1])
            proc = subprocess.Popen(
                [sys.executable, "-I", str(Path(stub.__file__)), str(folder / "key"),
                 str(folder / "log"), "--port", "0", "--arena", "--arena-port",
                 str(endpoint[1]), "--ack", "--experimental-relay", "--peer-timeout", "2",
                 "--seconds", "30"], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            peers = [socket.socket(socket.AF_INET, socket.SOCK_DGRAM) for _ in range(5)]
            a, b, c, d, e = peers
            messages = {peer: [] for peer in peers}
            alive = {a: 1, b: 2}
            last_bounce = {}
            reliable_seen = {peer: set() for peer in peers}
            reliable_copies = {}
            muted_acks = set()

            def send(peer, kind, payload):
                peer.sendto(aoanet.encode(kind, payload, key), endpoint)

            def pump(seconds):
                end = time.monotonic() + seconds
                while time.monotonic() < end:
                    ready, _, _ = select.select(peers, [], [], min(0.1, max(0, end - time.monotonic())))
                    for peer in ready:
                        try:
                            message = aoanet.decode(peer.recv(512), key)
                        except ConnectionResetError:
                            continue
                        self.assertTrue(message["crc_ok"])
                        if message["type"] == 0x1B:
                            body = message["payload"]
                            seq = body[-5:-1]
                            identity = (peer, seq)
                            reliable_copies[identity] = reliable_copies.get(identity, 0) + 1
                            # Lose the first removal ACK, requiring a retry.
                            if reliable_copies[identity] > 1 and peer not in muted_acks:
                                send(peer, 0x0F, seq)
                            if seq in reliable_seen[peer]:
                                continue
                            reliable_seen[peer].add(seq)
                            message = {**message, "type": body[-1], "payload": body[:-5]}
                        messages[peer].append(message)
                        if message["type"] == 8 and peer in alive:
                            bounce = bytearray(message["payload"])
                            bounce[6] = alive[peer]
                            last_bounce[peer] = bytes(bounce)
                            send(peer, 9, bytes(bounce))

            def payloads(peer, kind):
                return [m["payload"] for m in messages[peer] if m["type"] == kind]

            try:
                # Bind all sockets so select works on Windows before admission.
                for peer in peers:
                    peer.bind(("127.0.0.1", 0))
                deadline = time.monotonic() + 5
                while not payloads(a, 0x0B):
                    send(a, 10, request())
                    pump(0.1)
                    if time.monotonic() > deadline or proc.poll() is not None:
                        self.fail("relay did not start")
                send(b, 10, request())
                pump(0.1)
                send(c, 10, request())
                pump(0.1)
                self.assertTrue(payloads(c, 0x0B))
                send(c, 0x4E, b"\x00")  # Quit before bootstrap.
                pump(3.4)
                self.assertFalse(payloads(c, 0x2C))
                for peer in (a, b):
                    self.assertEqual(len(payloads(peer, 0x2C)), 1)
                    self.assertEqual({struct.unpack_from("<I", p, 0x28)[0] for p in payloads(peer, 0x26)},
                                     {0x80010001, 0x80010002})
                send(b, 0x4E, b"")  # Truncation must not remove anyone.
                send(b, 0x4E, b"\x00\x00")
                pump(0.3)
                self.assertFalse(payloads(a, 0x2D))
                quit_packet = b"\x01" + struct.pack("<I", 88) + b"\x4e"
                send(b, 0x1B, quit_packet)
                send(b, 0x1B, quit_packet)
                alive.pop(b)
                pump(1.1)
                self.assertEqual(payloads(a, 0x2D), [b"\x02"])
                self.assertTrue(any(peer == a and copies >= 2 for (peer, _), copies in reliable_copies.items()))
                self.assertEqual(payloads(b, 0x0F), [struct.pack("<I", 88)] * 2)
                # Retired endpoints cannot be revived by old handshakes; late
                # movement cannot affect observers. New endpoints get new slots.
                messages[b].clear()
                messages[a].clear()
                send(b, 10, request())
                send(b, *stub.motion_snapshot(2, ((1, 2, 3), (4, 5, 6))))
                alive[d] = 4
                send(d, 10, request())
                send(d, *stub.motion_snapshot(4, ((1, 2, 3), (4, 5, 6))))
                pump(3.4)
                self.assertFalse(payloads(b, 0x0B))
                self.assertFalse(payloads(b, 8))
                self.assertFalse(payloads(a, 0x1F))
                self.assertEqual(struct.unpack_from("<I", payloads(d, 0x0B)[0], 2)[0], 0x80010004)
                self.assertTrue(payloads(d, 0x2C))
                # Only a fresh, issued ping for this slot keeps it alive.
                alive.pop(d)
                for _ in range(13):
                    send(d, 9, last_bounce[d])  # Already consumed.
                    send(d, 9, bytes(12))  # Unissued tick and wrong slot.
                    send(d, 9, b"\x00")
                    send(d, 0x1F, struct.pack("<HHI3f", 0x8000, 4, 0x40, float("nan"), 0, 0))
                    pump(0.2)
                self.assertEqual(payloads(a, 0x2D), [b"\x04"])
                messages[d].clear()
                alive[e] = 5
                send(e, 10, request())
                pump(3.4)
                self.assertEqual({struct.unpack_from("<I", p, 0x28)[0] for p in payloads(e, 0x26)},
                                 {0x80010001, 0x80010005})
                self.assertEqual(len(payloads(a, 0x27)), 0, "survivor was restarted")
                self.assertFalse(payloads(d, 8), "expired peer still receives heartbeats")
                # An observer that keeps bouncing pings but never acknowledges
                # removal must retire after the bounded delivery attempts.
                muted_acks.add(a)
                send(e, 0x4E, b"\x00")
                alive.pop(e)
                pump(3.2)
                self.assertIn(b"\x05", payloads(a, 0x2D))
                # --peer-timeout 2: sends at 0, 0.5 and 1.5 s, then retirement.
                self.assertEqual(max(copies for (peer, _), copies in reliable_copies.items() if peer == a), 3)
                messages[a].clear()
                send(a, 10, request())
                pump(1.2)
                self.assertFalse(payloads(a, 8))
                self.assertFalse(payloads(a, 0x0B))
                self.assertIsNone(proc.poll())
            finally:
                for peer in peers:
                    peer.close()
                proc.terminate()
                proc.communicate(timeout=5)

    def test_remove_player_bounds(self):
        self.assertEqual(stub.remove_player(49), (0x2D, b"\x31"))
        for slot in (0, -1, 50, 256):
            with self.assertRaises(ValueError):
                stub.remove_player(slot)

    def test_arena_handshake_retries_do_not_restart_flight(self):
        key = bytes(range(256))
        for mode in ("--experimental-flight", "--experimental-relay"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory(prefix="aoa-retry-") as tmp:
                folder = Path(tmp)
                (folder / "key").write_bytes(key)
                with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
                    probe.bind(("127.0.0.1", 0))
                    endpoint = ("127.0.0.1", probe.getsockname()[1])
                proc = subprocess.Popen(
                    [sys.executable, "-I", str(Path(stub.__file__)), str(folder / "key"),
                     str(folder / "log"), "--port", "0", "--arena", "--arena-port",
                     str(endpoint[1]), "--ack", mode, "--seconds", "20"],
                    stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
                try:
                    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as peer:
                        peer.settimeout(0.15)
                        sequence = struct.pack("<I", 42)
                        wrapped = request() + sequence + b"\x0a"
                        expected_tag = 0x80010001 if mode == "--experimental-relay" else 1
                        deadline = time.monotonic() + 5
                        first_ack = None
                        entered = 0
                        wrapper_acks = 0
                        next_retry = 0
                        # Retry throughout loading: this used to continually
                        # postpone bootstrap. The initial request is wrapped.
                        while not entered and time.monotonic() < deadline:
                            if time.monotonic() >= next_retry:
                                peer.sendto(aoanet.encode(0x1B, wrapped, key), endpoint)
                                next_retry = time.monotonic() + 0.2
                            try:
                                message = aoanet.decode(peer.recv(512), key)
                            except (socket.timeout, ConnectionResetError):
                                continue
                            if message["type"] == 0x0B:
                                self.assertEqual(struct.unpack_from("<I", message["payload"], 2)[0], expected_tag)
                                first_ack = first_ack or time.monotonic()
                            elif message["type"] == 0x0F:
                                self.assertEqual(message["payload"], sequence)
                                wrapper_acks += 1
                            elif message["type"] == 0x2C:
                                entered += 1
                        self.assertIsNotNone(first_ack)
                        self.assertGreater(wrapper_acks, 0)
                        self.assertEqual(entered, 1, "retries postponed or bypassed flight initialization")
                        # Both direct and wrapped retries after flight must
                        # retain the tag and must never reload the ship.
                        peer.sendto(aoanet.encode(0x0A, request(), key), endpoint)
                        peer.sendto(aoanet.encode(0x1B, wrapped, key), endpoint)
                        changed = bytearray(request())
                        changed[31:40] = b"different"
                        peer.sendto(aoanet.encode(0x0A, bytes(changed), key), endpoint)
                        nested = bytes(changed) + sequence + b"\x0a" + sequence + b"\x1b"
                        peer.sendto(aoanet.encode(0x1B, nested, key), endpoint)
                        deadline = time.monotonic() + 3.8
                        saw_retry_ack = False
                        while time.monotonic() < deadline:
                            try:
                                message = aoanet.decode(peer.recv(512), key)
                            except socket.timeout:
                                continue
                            self.assertNotIn(message["type"], (0x27, 0x2C), "retry restarted flight")
                            if message["type"] == 0x0B:
                                saw_retry_ack = True
                                self.assertEqual(struct.unpack_from("<I", message["payload"], 2)[0], expected_tag)
                                self.assertEqual(message["payload"][13:33], request()[31:51])
                        self.assertTrue(saw_retry_ack)
                        self.assertIsNone(proc.poll())
                finally:
                    proc.terminate()
                    proc.communicate(timeout=5)

    def test_reported_motion(self):
        state = ((12.0, 24.0, 36.0), (1.5, -2.5, 3.5))
        for mask, fmt, delta in ((2, "3h", (300, -400, 500)), (4, "3b", (1, -2, 3))):
            packet = struct.pack("<HHI" + fmt, 0x8000, 1, mask, *delta)
            result = stub.reported_motion(packet, state)
            self.assertEqual(result[0], state[0])
            self.assertEqual(result[1], tuple(a + b for a, b in zip(state[1], delta)))
        bad = struct.pack("<HHI3f", 0x8000, 1, 0x40, float("nan"), 0, 0)
        with self.assertRaises(ValueError):
            stub.reported_motion(bad, state)

    def test_arena_ping(self):
        self.assertEqual(stub.arena_ping(0x100000001), (8, b"\x01" + bytes(11)))
    def test_movement_filter(self):
        # Full snapshot mask observed in the live crash. 60 bytes of
        # kinematics precede the unsafe optional blocks.
        prefix = bytes(range(60))
        packet = struct.pack("<HHI", 0x8000, 1, 0xD1207381) + prefix + bytes(73)
        # A zero-record gun-state block survives; later optional blocks do not.
        self.assertEqual(stub.movement_update(packet, 1),
                         struct.pack("<HHI", 0x8000, 1, 0x11207381) + prefix + b"\x00")
        guns = bytes([0x82]) + struct.pack("<HBHB", 2, 15, 7, 15)
        firing = struct.pack("<HHI", 0x8000, 1, 0x91207381) + prefix + guns + bytes(9)
        self.assertEqual(stub.movement_update(firing, 1),
                         struct.pack("<HHI", 0x8000, 1, 0x11207381) + prefix + guns)
        # Out-of-range system indexes or a truncated block drop only the block.
        for bad in (bytes([1]) + struct.pack("<HB", 128, 15), bytes([3]) + struct.pack("<HB", 2, 15)):
            packet_bad = struct.pack("<HHI", 0x8000, 1, 0x11207381) + prefix + bad
            self.assertEqual(stub.movement_update(packet_bad, 1),
                             struct.pack("<HHI", 0x8000, 1, 0x01207381) + prefix)
        for n in range(68):
            self.assertIsNone(stub.movement_update(packet[:n], 1))
        self.assertIsNone(stub.movement_update(packet, 2))
        self.assertIsNone(stub.movement_update(struct.pack("<HHI", 0, 1, 1) + bytes(12), 1))
        self.assertIsNone(stub.movement_update(struct.pack("<HHI", 0x8000, 1, 0x80000000), 1))

    def test_experimental_relay_transport(self):
        # Two synthetic sockets verify transport only, not game simulation.
        key = bytes(range(256))
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.bind(("127.0.0.1", 0))
            arena_port = probe.getsockname()[1]
        with tempfile.TemporaryDirectory(prefix="aoa-relay-") as tmp:
            folder = Path(tmp)
            (folder / "key").write_bytes(key)
            proc = subprocess.Popen(
                [sys.executable, "-I", str(Path(stub.__file__)), str(folder / "key"),
                 str(folder / "log"), "--port", "0", "--arena", "--arena-port", str(arena_port),
                 "--ack", "--experimental-relay", "--experimental-object", "--seconds", "15"],
                stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            endpoint = ("127.0.0.1", arena_port)
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as a, socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as b:
                    a.settimeout(0.2)
                    deadline = time.monotonic() + 5
                    while True:
                        a.sendto(aoanet.encode(10, request(), key), endpoint)
                        try:
                            ack_a = aoanet.decode(a.recv(512), key)
                            break
                        except (socket.timeout, ConnectionResetError):
                            if time.monotonic() > deadline or proc.poll() is not None:
                                self.fail("relay did not start")
                    a.settimeout(5)
                    b.settimeout(5)
                    b.sendto(aoanet.encode(10, request(), key), endpoint)
                    ack_b = aoanet.decode(b.recv(512), key)
                    self.assertEqual(int.from_bytes(ack_a["payload"][2:6], "little"), 0x80010001)
                    self.assertEqual(int.from_bytes(ack_b["payload"][2:6], "little"), 0x80010002)
                    for peer in (a, b):
                        seen_players = set()
                        entered_flight = False
                        while True:
                            message = aoanet.decode(peer.recv(512), key)
                            self.assertTrue(message["crc_ok"])
                            if message["type"] == 0x26:
                                seen_players.add(int.from_bytes(message["payload"][0x28:0x2C], "little"))
                            if message["type"] == 0x2C:
                                entered_flight = True
                            # A peer is announced when its own bootstrap is
                            # ready, which may follow this observer's entry.
                            if entered_flight and seen_players == {0x80010001, 0x80010002}:
                                break
                        self.assertEqual(seen_players, {0x80010001, 0x80010002})
                    position = bytes.fromhex("00800100040800000000000000")
                    unsafe = bytearray(position)
                    unsafe[7] = 0x80
                    unsafe += struct.pack("<I", 1) + bytes(32)
                    a.sendto(aoanet.encode(0x1F, bytes(unsafe), key), endpoint)
                    while True:
                        forwarded = aoanet.decode(b.recv(512), key)
                        if (forwarded["type"] == 0x1F and
                                struct.unpack_from("<I", forwarded["payload"], 4)[0] & 0x400):
                            break
                    state, _, _ = relay_motion.update(position, relay_motion.initial((0, 0, 0)))
                    # Server-owned stats ride along: no kills/deaths yet, nothing reported.
                    self.assertEqual(forwarded["payload"],
                                     relay_motion.snapshot(1, state, include_control=True, stats=(0, 0, 0, 0)))
                    while True:
                        ping = aoanet.decode(b.recv(512), key)
                        if ping["type"] == 8:
                            break
                    self.assertTrue(ping["crc_ok"])
                    self.assertEqual(len(ping["payload"]), 12)
                    self.assertEqual(ping["payload"][4:], bytes(8))
                    # Move A, then join C. C must see the last reported
                    # coordinates and a full velocity seed, not A's spawn.
                    motion = ((1250.0, -250.0, 80.0), (12.0, -4.0, 7.0))
                    rtype, rpay = stub.motion_snapshot(1, motion)
                    a.sendto(aoanet.encode(rtype, rpay, key), endpoint)
                    while aoanet.decode(b.recv(512), key)["type"] != 0x1F:
                        pass
                    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as c:
                        c.settimeout(5)
                        c.sendto(aoanet.encode(10, request(), key), endpoint)
                        seen_position = seed = local_position = None
                        entered_flight = False
                        while True:
                            message = aoanet.decode(c.recv(512), key)
                            p = message["payload"]
                            if message["type"] == 0x26 and struct.unpack_from("<I", p, 0x28)[0] == 0x80010001:
                                seen_position = struct.unpack_from("<3f", p, 0x1A4)
                            if message["type"] == 0x1F and struct.unpack_from("<H", p, 2)[0] == 1:
                                seed = struct.unpack_from("<6f", p, 8)
                            if message["type"] == 0x24:
                                self.assertTrue(entered_flight)
                                local_position = struct.unpack("<3f", p)
                            if message["type"] == 0x25:
                                self.assertIsNotNone(local_position)
                                self.assertEqual(len(p), 191)
                                self.assertEqual(p[:32].split(b"\0")[0], b"Ym Khtat")
                                self.assertEqual(struct.unpack_from("<II", p, 0x60), (0x40010001, 0x11))
                                self.assertEqual(struct.unpack_from("<3f", p, 0x92), (0.0, 0.0, 1500.0))
                                break
                            if message["type"] == 0x2C:
                                entered_flight = True
                        self.assertEqual(seen_position, motion[0])
                        self.assertEqual(seed, motion[0] + motion[1])
                        self.assertEqual(local_position, (2000.0, 0.0, 0.0))
                    self.assertIsNone(proc.poll())
            finally:
                proc.terminate()
                proc.communicate(timeout=5)

    def test_ship_selection_messages(self):
        config = stub.ship_config_list()
        self.assertEqual(len(config), 0x68)
        self.assertEqual(config[0x20:0x25], b"_all\0")
        request_for = lambda name, index=0: struct.pack("<I", index) + name.ljust(32, b"\0") + b"\0"  # noqa: E731
        self.assertEqual(stub.ship_request(request_for(b"Vermok")), "Vermok")
        self.assertEqual(stub.ship_request(request_for(b"N'Goc", 3)), "N'Goc")
        for bad in (request_for(b"Death Star"), request_for(b"Vermok")[:-1], request_for(b"Vermok") + b"\0",
                    request_for(b"Vermok")[:-1] + b"\1", struct.pack("<I", 0) + b"V" * 32 + b"\0", bytes(37)):
            with self.subTest(bad=bad):
                self.assertIsNone(stub.ship_request(bad))
        kind, body = stub.load_ship("Vermok", 4)
        self.assertEqual((kind, len(body)), (0x27, 129))
        self.assertEqual(body[:64], b"Vermok".ljust(64, b"\0"))
        self.assertEqual(body[64:128], b"AoAObjects.odb".ljust(64, b"\0"))
        self.assertEqual(body[128], 4)
        self.assertEqual(stub.flight_bootstrap()[0], stub.load_ship("Ym Khtat", 0))
        self.assertEqual(stub.load_player(2, vessel="Kafic")[1][:20], b"Kafic".ljust(20, b"\0"))
        self.assertEqual(stub.load_player(2)[1][:20], b"Ym Khtat".ljust(20, b"\0"))
        for args in (("Death Star",), ("Vermok", 50), ("Vermok", -1)):
            with self.subTest(args=args), self.assertRaises(ValueError):
                stub.load_ship(*args)
        with self.assertRaises(ValueError):
            stub.load_player(2, vessel="Death Star")

    def test_ship_change_relay(self):
        # Pilot A picks a new fighter: A and observer B load it, A returns to
        # its spawn, and late joiner C gets it in A's player record.
        key = bytes(range(256))
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.bind(("127.0.0.1", 0))
            arena_port = probe.getsockname()[1]
        with tempfile.TemporaryDirectory(prefix="aoa-ship-") as tmp:
            folder = Path(tmp)
            (folder / "key").write_bytes(key)
            proc = subprocess.Popen(
                [sys.executable, "-I", str(Path(stub.__file__)), str(folder / "key"),
                 str(folder / "log"), "--port", "0", "--arena", "--arena-port", str(arena_port),
                 "--ack", "--experimental-relay", "--seconds", "20"],
                stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            endpoint = ("127.0.0.1", arena_port)

            def until(peer, kind):
                while True:
                    message = aoanet.decode(peer.recv(512), key)
                    if message["type"] == kind:
                        return message["payload"]

            try:
                with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as a, \
                        socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as b:
                    a.settimeout(0.2)
                    deadline = time.monotonic() + 5
                    while True:
                        a.sendto(aoanet.encode(10, request(), key), endpoint)
                        try:
                            a.recv(512)
                            break
                        except (socket.timeout, ConnectionResetError):
                            if time.monotonic() > deadline or proc.poll() is not None:
                                self.fail("relay did not start")
                    a.settimeout(5)
                    b.settimeout(5)
                    b.sendto(aoanet.encode(10, request(), key), endpoint)
                    self.assertEqual(until(a, 0x27)[:64], b"Ym Khtat".ljust(64, b"\0"))
                    until(a, 0x2C)
                    until(b, 0x2C)
                    # A's own bootstrap may be ready before B's; wait until
                    # the relay counts B as loaded (it then pings B).
                    until(b, 8)
                    unknown = struct.pack("<I", 0) + b"Death Star".ljust(32, b"\0") + b"\0"
                    a.sendto(aoanet.encode(0xA0, unknown, key), endpoint)
                    choice = struct.pack("<I", 0) + b"Vermok".ljust(32, b"\0") + b"\0"
                    # The client may send it reliably; the wrapper is ACKed.
                    a.sendto(aoanet.encode(0x1B, choice + struct.pack("<I", 7) + b"\xa0", key), endpoint)
                    self.assertEqual(until(a, 0x0F), struct.pack("<I", 7))
                    own = until(a, 0x27)
                    self.assertEqual((own[:64], own[128]), (b"Vermok".ljust(64, b"\0"), 0))
                    self.assertEqual(struct.unpack("<3f", until(a, 0x24)), (0.0, 0.0, 0.0))
                    seen = until(b, 0x27)
                    self.assertEqual((seen[:64], seen[64:78], seen[128]), (b"Vermok".ljust(64, b"\0"),
                                                                          b"AoAObjects.odb", 1))
                    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as c:
                        c.settimeout(5)
                        joining = bytearray(request())
                        struct.pack_into("<I", joining, 31 + 0x7B, 0x1234)  # Station ID
                        c.sendto(aoanet.encode(10, bytes(joining), key), endpoint)
                        vessels, ids, own = {}, {}, None
                        while True:
                            message = aoanet.decode(c.recv(512), key)
                            p = message["payload"]
                            self.assertNotEqual(message["type"], 0x42)  # No record refresh mid-flight setup.
                            if message["type"] == 0x26:
                                tag = struct.unpack_from("<I", p, 0x28)[0]
                                vessels[tag] = p[:20].split(b"\0")[0]
                                ids[tag] = struct.unpack_from("<I", p, 0x46 + 0x7B)[0]
                            elif message["type"] == 0x27:
                                own = p[:64].split(b"\0")[0]
                            elif message["type"] == 0x2C:
                                break
                        self.assertEqual(vessels, {0x80010001: b"Vermok", 0x80010002: b"Ym Khtat",
                                                   0x80010003: b"Ym Khtat"})
                        self.assertEqual(own, b"Ym Khtat")
                        # Its own record keeps the Station ID its TCP requests
                        # (job 4) carry; nobody else's record carries one.
                        self.assertEqual(ids, {0x80010001: 0, 0x80010002: 0, 0x80010003: 0x1234})
                    self.assertIsNone(proc.poll())
            finally:
                proc.terminate()
                proc.communicate(timeout=5)
            changes = [json.loads(line) for line in (folder / "log").read_text().splitlines()
                       if '"ship_change"' in line]
            self.assertEqual([(e["slot"], e["status"]) for e in changes], [(1, "rejected"), (1, "Vermok")])

    def test_pilot_bounds(self):
        self.assertEqual(stub.pilot_list()[:32], b"testpilot".ljust(32, b"\0"))
        self.assertEqual(stub.pilot_list()[32:], bytes(288))
        for name in ("", "x" * 20, "a\0b", "\u2603"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                stub.pilot_list(name)

    def test_station_and_arena_handshakes(self):
        for arena in (False, True):
            replies = stub.udp_replies(0x0A, request(), arena=arena)
            self.assertEqual(len(replies), 1)
            kind, payload = replies[0]
            self.assertEqual(kind, 0x0B)
            self.assertEqual(len(payload), 363)
            self.assertEqual(payload[1], 0 if arena else 1)
            self.assertEqual(payload[2:10], b"\x01" + bytes(7))
            self.assertEqual(payload[13:33], request()[31:51])

    def test_wrappers_and_truncation(self):
        seq = (123).to_bytes(4, "little")
        self.assertEqual(stub.udp_replies(0x1B, bytes(4) + seq + b"\x80"), [(0x0F, seq)])
        wrapped = stub.udp_replies(0x1B, request() + seq + b"\x0a")
        self.assertEqual(wrapped, [(0x0F, seq)] + stub.udp_replies(0x0A, request()))
        for size in range(5):
            self.assertEqual(stub.udp_replies(0x1B, bytes(size)), [])
        self.assertEqual(stub.udp_replies(0x0A, bytes(380)), [])

    def test_tcp_framing(self):
        for job, expected in stub.TCP_JOB_BODIES.items():
            reply = stub.tcp_reply(job)
            self.assertEqual(int.from_bytes(reply[:4], "little"), len(reply) - 4)
            self.assertEqual(aoapack.decompress(reply[4:])[0], expected)
        self.assertEqual(stub.tcp_reply(999), bytes(4))

    def test_loopback_exchange(self):
        key = bytes(range(256))
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.bind(("127.0.0.1", 0))
            udp_port = probe.getsockname()[1]
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            tcp_port = probe.getsockname()[1]
        with tempfile.TemporaryDirectory(prefix="aoa-stub-") as tmp:
            folder = Path(tmp)
            (folder / "key").write_bytes(key)
            proc = subprocess.Popen(
                [sys.executable, "-I", str(Path(stub.__file__)), str(folder / "key"),
                 str(folder / "log"), "--port", str(udp_port), "--tcp", str(tcp_port),
                 "--ack", "--seconds", "15"], stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE)
            try:
                deadline = time.monotonic() + 5
                while True:
                    try:
                        tcp = socket.create_connection(("127.0.0.1", tcp_port), timeout=2)
                        break
                    except ConnectionRefusedError:
                        if proc.poll() is not None or time.monotonic() > deadline:
                            self.fail("stub did not start")
                        time.sleep(0.05)
                with tcp, socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp:
                    udp.settimeout(3)
                    endpoint = ("127.0.0.1", udp_port)
                    udp.sendto(aoanet.encode(0x0A, request(), key), endpoint)
                    ack = aoanet.decode(udp.recvfrom(512)[0], key)
                    self.assertTrue(ack["crc_ok"])
                    self.assertEqual((ack["type"], ack["payload"][1]), (0x0B, 1))
                    # TCP framing must tolerate a fragmented request.
                    job = bytearray(142)
                    job[60:64] = ack["payload"][13 + 0x7B:17 + 0x7B]
                    job[128] = 5
                    tcp.sendall(job[:71])
                    tcp.sendall(job[71:])
                    with tcp.makefile("rb") as stream:
                        length = int.from_bytes(stream.read(4), "little")
                        body = aoapack.decompress(stream.read(length))[0]
                    self.assertEqual(body, stub.server_list_body(0, station_population=1))
                    aliases = aoanet.decode(udp.recvfrom(512)[0], key)
                    while aliases["type"] == 8:
                        aliases = aoanet.decode(udp.recvfrom(512)[0], key)
                    self.assertEqual(aliases["type"], 0x9A)
                    self.assertTrue(aliases["crc_ok"])
                    self.assertEqual(aliases["payload"], stub.pilot_list())
                    # A validly encrypted packet with a deliberately wrong CRC
                    # must be ignored, as must a short reliable wrapper.
                    bad = request() + b"\x0a" + (aoapack.crc16_xmodem(request()) ^ 1).to_bytes(2, "little")
                    udp.sendto(aoacrypt.encrypt(aoapack.compress(bad), key), endpoint)
                    udp.sendto(aoanet.encode(0x1B, b"\x00", key), endpoint)
                    udp.settimeout(0.7)
                    deadline = time.monotonic() + 0.7
                    while time.monotonic() < deadline:
                        udp.settimeout(max(0.01, deadline - time.monotonic()))
                        try:
                            packet = aoanet.decode(udp.recvfrom(512)[0], key)
                        except socket.timeout:
                            break
                        self.assertEqual(packet["type"], 8)  # Scheduled heartbeat only.
                self.assertIsNone(proc.poll(), "malformed input terminated stub")
            finally:
                proc.terminate()
                proc.communicate(timeout=5)


if __name__ == "__main__":
    unittest.main(verbosity=2)
