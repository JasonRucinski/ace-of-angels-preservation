"""Internet-play host checks: python -I tools/test_internet_play.py.

Covers the VPN profile, sustained windowed delivery against a model of the
2.9.2 client's 30-ID duplicate history, the test impairment layer, the host
status/console and a live loopback session under induced delay and loss.
The fixture VPN address is redirected to loopback. No real client, VPN or
internet path is exercised; those remain manual acceptance steps.
"""
import contextlib
import io
import json
import os
import random
import select
import socket
import struct
import sys
import tempfile
import threading
import time
import unittest
from collections import deque
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import aoanet
import host_ops
import station_stub as stub
from net_impair import Impairment, MeteredSocket, TrafficMeter
from reliable_window import WindowedReliable
from station_runtime import parse_args
from test_station_runtime import job_request, read_reply
import test_station_stub
from test_station_stub import request

VPN_ADDRESS = "100.101.102.103"


def quiet_parse(argv):
    with contextlib.redirect_stderr(io.StringIO()):
        return parse_args(argv)


class ClientHistory:
    """The original filter (0x4C2730): 30 IDs, circular, zero pre-filled."""

    def __init__(self):
        self.ids = deque([0] * 30, maxlen=30)

    def first(self, sequence):
        if sequence in self.ids:
            return False
        self.ids.append(sequence)
        return True


class ConfigTests(unittest.TestCase):
    def test_vpn_profile(self):
        base = ["key", "log", "--profile", "vpn-dogfight", "--bind-address"]
        for address in ("100.64.0.1", VPN_ADDRESS, "100.127.255.254", "10.147.17.5", "192.168.1.55"):
            args = parse_args(base + [address])
            self.assertTrue(args.sustained_delivery and args.guest_sessions and args.experimental_relay)
            self.assertEqual((args.advertised_address, args.tcp), (address, 5034))
        for address in ("100.63.255.255", "100.128.0.1", "8.8.8.8", "127.0.0.1", "0.0.0.0", "169.254.1.1"):
            with self.subTest(address=address), self.assertRaises(SystemExit):
                quiet_parse(base + [address])
        lan = parse_args(["key", "log", "--profile", "lan-dogfight", "--bind-address", "192.168.1.55"])
        self.assertFalse(lan.sustained_delivery)
        with self.assertRaises(SystemExit):
            quiet_parse(["key", "log", "--profile", "lan-dogfight", "--bind-address", VPN_ADDRESS])
        self.assertTrue(parse_args(["key", "log", "--profile", "lan-dogfight", "--bind-address", "192.168.1.55",
                                    "--sustained-delivery"]).sustained_delivery)
        terrain = parse_args(base + [VPN_ADDRESS, "--map", "Arena1a", "--experimental-terrain"])
        self.assertTrue(terrain.experimental_terrain)
        # online-terrain-v2 selects any recovered map, not only Arena1a.
        self.assertEqual(parse_args(base + [VPN_ADDRESS, "--experimental-terrain"]).map, "CTF_arena")
        for options in (["--map", "NoSuchMap"], ["--advertised-address", "100.64.0.2"],
                        ["--experimental-reliable-combat"], ["--max-players", "9"], ["--reorder-margin", "0.1"],
                        ["--impair-loss", "51"], ["--impair-rtt-ms", "nan"], ["--impair-jitter-ms", "-1"]):
            with self.subTest(options=options), self.assertRaises(SystemExit):
                quiet_parse(base + [VPN_ADDRESS] + options)
        with self.assertRaises(SystemExit):
            quiet_parse(["key", "log", "--sustained-delivery"])  # needs the relay


class WindowedDeliveryTests(unittest.TestCase):
    def test_order_expiry_and_failure(self):
        delivery = WindowedReliable(deadline=30, margin=3)
        launch = delivery.queue_message("a", 0x2A, b"launch", 0, essential=False)
        self.assertEqual(delivery.queue_message("a", 0x30, b"impact", 0, essential=False), ())
        self.assertFalse(delivery.acknowledge("a", struct.pack("<I", 2)))  # not yet sent
        self.assertEqual(delivery.due(0.3), ([("a", launch)], set()))
        # Droppable events are abandoned after five seconds; the next continues.
        packets, failed = delivery.due(5.0)
        self.assertFalse(failed)
        self.assertEqual(packets[0][1][1][:-5], b"impact")
        self.assertEqual(delivery.expired, 1)
        self.assertTrue(delivery.acknowledge("a", packets[0][1][1][-5:-1]))
        removal = delivery.queue("a", 2, 6)
        self.assertEqual(removal[1][:1], b"\x02")
        self.assertEqual(delivery.due(35.9)[1], set())
        self.assertEqual(delivery.due(36)[1], {"a"})  # essential: retire the peer
        delivery.discard("a")
        self.assertEqual(delivery.due(100), ([], set()))

    def test_window_holds_the_thirty_first_id(self):
        delivery = WindowedReliable(margin=3)
        for index in range(30):
            packet = delivery.queue_message("a", 0x38, bytes([index]), index * 0.01)
            self.assertTrue(packet)
            self.assertTrue(delivery.acknowledge("a", packet[1][-5:-1]))
        self.assertEqual(delivery.queue_message("a", 0x38, b"x", 0.5), ())
        self.assertEqual(delivery.due(2.99), ([], set()))
        packets, _ = delivery.due(3.0)
        self.assertEqual(packets[0][1][1][:-5], b"x")
        self.assertEqual(delivery.window_waits, 1)

    def test_client_model_detects_eviction(self):
        history = ClientHistory()
        for sequence in range(1, 32):
            self.assertTrue(history.first(sequence))
        self.assertTrue(history.first(1), "an evicted replay executes again")

    def test_sustained_events_under_impairment_never_reapply(self):
        # Virtual time: RTT/loss grid, duplicates, jitter and stale copies up
        # to 90% of the margin late. Every one of 400 events per run (13 times
        # the old lifetime budget) must apply exactly once, in order, through
        # the client's 30-ID history.
        margin, total = 3.0, 400
        for rtt in (0.030, 0.080, 0.150):
            for loss in (0, 0.01, 0.03):
                for seed in range(2):
                    rng = random.Random(seed)
                    delivery = WindowedReliable(deadline=30, margin=margin)
                    history, applied, flights = ClientHistory(), [], []

                    def transmit(packet, now):
                        if rng.random() < loss:
                            return
                        flights.append((now + rtt / 2 + rng.random() * rtt / 2, "data", packet))
                        if rng.random() < 0.05:
                            flights.append((now + rtt / 2 + rng.random() * margin * 0.9, "data", packet))

                    queued, now = 0, 0.0
                    while now < 1000:
                        while queued < total and queued < now * 6:  # offered: 6 events/s per observer
                            packet = delivery.queue_message("a", 0x38, struct.pack("<H", queued), now)
                            self.assertIsNotNone(packet)
                            if packet:
                                transmit(packet, now)
                            queued += 1
                        arrived = sorted((item for item in flights if item[0] <= now), key=lambda item: item[0])
                        flights = [item for item in flights if item[0] > now]
                        for _, kind, payload in arrived:
                            if kind == "ack":
                                delivery.acknowledge("a", payload, now)
                                continue
                            if history.first(struct.unpack("<I", payload[1][-5:-1])[0]):
                                applied.append(struct.unpack("<H", payload[1][:2])[0])
                            if rng.random() >= loss:
                                flights.append((now + rtt / 2, "ack", payload[1][-5:-1]))
                        packets, failed = delivery.due(now)
                        self.assertFalse(failed, (rtt, loss, seed))
                        for _, packet in packets:
                            transmit(packet, now)
                        if queued == total and not delivery.pending:
                            break
                        now = round(now + 0.005, 3)
                    self.assertEqual(applied, list(range(total)), (rtt, loss, seed))
                    self.assertFalse(delivery.pending)


class ImpairmentTests(unittest.TestCase):
    class FakeSocket:
        def __init__(self):
            self.sent, self.inbox = [], deque()

        def sendto(self, data, address):
            self.sent.append((data, address))
            return len(data)

        def recvfrom(self, size):
            if not self.inbox:
                raise BlockingIOError
            return self.inbox.popleft()

        def fileno(self):
            return -1

        def getsockname(self):
            return ("127.0.0.1", 1)

    def test_delay_loss_duplicate_and_meter(self):
        clock = [0.0]
        raw, meter = self.FakeSocket(), TrafficMeter()
        sock = MeteredSocket(raw, meter, Impairment(100, 0, 0, 0, 1), Impairment(100, 0, 0, 0, 2),
                             clock=lambda: clock[0])
        sock.sendto(b"abc", ("h", 1))
        sock.flush()
        self.assertEqual(raw.sent, [])
        self.assertAlmostEqual(sock.next_due(), 0.05)
        clock[0] = 0.05
        sock.flush()
        self.assertEqual(raw.sent, [(b"abc", ("h", 1))])
        raw.inbox.append((b"in", ("h", 1)))
        with self.assertRaises(BlockingIOError):
            sock.recvfrom(512)
        self.assertFalse(sock.has_due())
        clock[0] = 0.1
        self.assertTrue(sock.has_due())
        self.assertEqual(sock.recvfrom(512), (b"in", ("h", 1)))
        self.assertEqual(meter.endpoints[("h", 1)], {"rx_packets": 1, "rx_bytes": 2, "tx_packets": 1, "tx_bytes": 3})
        lossy = Impairment(0, 0, 10, 10, seed=5)
        copies = [len(lossy.schedule(0)) for _ in range(10000)]
        self.assertAlmostEqual(copies.count(0) / 10000, 0.10, delta=0.015)
        self.assertAlmostEqual(copies.count(2) / 10000, 0.09, delta=0.015)
        plain = MeteredSocket(raw, meter, Impairment(), Impairment())
        self.assertIsNone(plain.inbound)
        plain.sendto(b"x", ("h", 2))
        self.assertEqual(raw.sent[-1], (b"x", ("h", 2)))
        for bad in ((-1, 0, 0, 0), (0, 0, 51, 0), (float("inf"), 0, 0, 0)):
            with self.assertRaises(ValueError):
                Impairment(*bad)


class HostOpsTests(unittest.TestCase):
    def test_commands_status_and_table(self):
        self.assertEqual(host_ops.parse_command(" KICK 3 "), ("kick", 3))
        self.assertEqual(host_ops.parse_command("status"), ("status", None))
        for bad in ("kick", "kick 0", "kick 50", "ban x", "reboot", "status now"):
            self.assertEqual(host_ops.parse_command(bad), (None, host_ops.HELP))
        self.assertEqual(host_ops.parse_command("   "), (None, ""))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "nested" / "status.json"
            host_ops.write_status(path, {"players": []})
            self.assertEqual(json.loads(path.read_text())["players"], [])
            self.assertFalse(path.with_name("status.json.tmp").exists())
        table = host_ops.player_table([{"slot": 2, "pilot": "testpilot-02", "kills": 1, "deaths": 0,
                                        "ping_ms": None, "in_kbps": 1.5, "out_kbps": 2.0, "idle_s": 0.1}])
        self.assertIn("testpilot-02", table)


class SyntheticClient:
    """Models the 2.9.2 receive path: ACK every 0x1B, filter, then dispatch."""

    def __init__(self, key):
        self.key = key
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("127.0.0.1", 0))
        self.history = ClientHistory()
        self.applied, self.pending = [], {}
        self.sequence, self.slot, self.silent = 1, 0, False
        self.acks = {}

    def send(self, endpoint, kind, body):
        self.sock.sendto(aoanet.encode(kind, body, self.key), endpoint)

    def send_reliable(self, endpoint, kind, body):
        packet = body + struct.pack("<I", self.sequence) + bytes([kind])
        self.pending[self.sequence] = [endpoint, packet, time.monotonic() + 0.2]
        self.sequence += 1
        self.send(endpoint, 0x1B, packet)

    def handle(self, wire, source):
        message = aoanet.decode(wire, self.key)
        assert message["crc_ok"]
        kind, body = message["type"], message["payload"]
        if kind == 0x1B:
            self.send(source, 0x0F, body[-5:-1])
            if not self.history.first(struct.unpack("<I", body[-5:-1])[0]):
                return
            kind, body = body[-1], body[:-5]
        if kind == 0x0F:
            self.pending.pop(struct.unpack("<I", body)[0], None)
        elif kind == 8:
            reply = bytearray(body)
            reply[6] = self.slot
            self.send(source, 9, bytes(reply))
        elif kind == 0x0B:
            self.acks[source[1]] = body
        self.applied.append((kind, body))

    def resend(self):
        now = time.monotonic()
        for entry in self.pending.values():
            if now >= entry[2]:
                self.send(entry[0], 0x1B, entry[1])
                entry[2] = now + 0.2

    def bodies(self, kind):
        return [body for applied, body in self.applied if applied == kind]


class LiveVpnSessionTests(unittest.TestCase):
    def test_impaired_session_kick_and_rejoin(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        status_path = Path(directory.name) / "status.json"
        args = parse_args(["key", "log", "--profile", "vpn-dogfight", "--bind-address", VPN_ADDRESS,
                           "--port", "0", "--arena-port", "0", "--tcp", "0", "--seconds", "45",
                           "--kill-limit", "1", "--time-limit", "0", "--console", "--status-file", str(status_path),
                           "--impair-rtt-ms", "60", "--impair-jitter-ms", "20", "--impair-loss", "3",
                           "--impair-duplicate", "1", "--impair-seed", "7"])
        key = bytes(range(256))
        bindings, failures, logs = [], [], []
        original_bind = socket.socket.bind
        read_end, write_end = os.pipe()
        console_in = os.fdopen(read_end, "r")
        console_out = os.fdopen(write_end, "w")
        self.addCleanup(console_out.close)

        def fixture_bind(sock, endpoint):
            if endpoint[0] == VPN_ADDRESS:
                original_bind(sock, ("127.0.0.1", endpoint[1]))
                bindings.append((sock.type, sock.getsockname()[1]))
            else:
                original_bind(sock, endpoint)

        def server():
            try:
                with contextlib.redirect_stdout(io.StringIO()), contextlib.ExitStack() as resources:
                    stub.run(args, key, logs.append, resources)
            except BaseException as error:  # noqa: BLE001
                failures.append(error)

        clients = []
        with patch.object(socket.socket, "bind", fixture_bind), patch.object(sys, "stdin", console_in):
            worker = threading.Thread(target=server, daemon=True)
            worker.start()
            deadline = time.monotonic() + 3
            while len(bindings) < 3 and time.monotonic() < deadline:
                time.sleep(0.01)
        self.assertEqual(len(bindings), 3, failures)
        station, arena, tcp = [("127.0.0.1", port) for _, port in bindings]

        def pump(duration):
            end = time.monotonic() + duration
            while time.monotonic() < end:
                ready, _, _ = select.select([c.sock for c in clients], [], [], 0.01)
                for client in clients:
                    if client.sock in ready:
                        wire, source = client.sock.recvfrom(512)
                        if not client.silent:
                            client.handle(wire, source)
                    if not client.silent:
                        client.resend()

        def until(predicate, timeout=6, retry=None):
            end = time.monotonic() + timeout
            next_retry = 0
            while not predicate():
                self.assertFalse(failures, failures)
                self.assertLess(time.monotonic(), end, "expected host response missing")
                if retry is not None and time.monotonic() >= next_retry:
                    retry()
                    next_retry = time.monotonic() + 0.3
                pump(0.01)

        def join(client, arena_join=True):
            until(lambda: station[1] in client.acks,
                  retry=lambda: client.send(station, 10, request()))
            ack = client.acks[station[1]]
            identity = struct.unpack_from("<I", ack, 136)[0]
            with socket.create_connection(tcp, timeout=2) as connection:
                connection.sendall(job_request(identity=identity))
                listing = read_reply(connection)
            self.assertEqual(listing[0x80 + 0x60:0x80 + 0x72].split(b"\0")[0], VPN_ADDRESS.encode())
            self.assertIn(b"VPN Dogfight", listing)
            if arena_join:
                until(lambda: arena[1] in client.acks,
                      retry=lambda: client.send(arena, 10, request()[:31] + ack[13:]))
                client.slot = struct.unpack_from("<I", client.acks[arena[1]], 2)[0] & 0xFF

        try:
            a, b = SyntheticClient(key), SyntheticClient(key)
            clients += [a, b]
            for client in (a, b):
                join(client)
            self.assertEqual((a.slot, b.slot), (1, 2))
            until(lambda: all(c.bodies(0x2C) for c in (a, b)), timeout=8)
            pump(0.5)
            for client in (a, b):
                self.assertEqual(len(client.bodies(0x27)), 1)
                self.assertEqual(len(client.bodies(0x2C)), 1)
                self.assertEqual(struct.unpack("<3f", client.bodies(0x24)[-1]), stub.spawn_position(client.slot))
            # A bootstraps alone, then B: A loads itself once and B once.
            self.assertEqual(sorted(struct.unpack_from("<I", body, 0x28)[0] & 0xFF for body in a.bodies(0x26)), [1, 2])

            # Far beyond the old 30-event lifetime budget, through 3% loss.
            cycles = 25
            for index in range(cycles):
                a.send_reliable(arena, 0x2A, test_station_stub.ProtocolTests.fire_missile())
                until(lambda: all(len(c.bodies(0x2A)) == index + 1 for c in (a, b)))
                tag = struct.unpack_from("<I", a.bodies(0x2A)[-1], 0x10)[0]
                impact = struct.pack("<II3fB", tag, stub.player_tag(2), 0, 0, 5000, 1)
                b.send_reliable(arena, 0x30, impact)
                b.send_reliable(arena, 0x30, impact)
                until(lambda: all(len(c.bodies(0x30)) == index + 1 for c in (a, b)))
            b.send_reliable(arena, 0x37, struct.pack("<I", stub.player_tag(1)))
            until(lambda: any(b"Match 2 started" in body for body in b.bodies(0x21))
                  and any(b"Match 2 started" in body for body in a.bodies(0x21)))
            until(lambda: len(b.bodies(0x24)) == 2)
            pump(0.5)
            self.assertEqual(len(a.bodies(0x38)), 1)
            self.assertFalse(b.bodies(0x38))
            for client in (a, b):
                self.assertEqual(len(client.bodies(0x2A)), cycles)
                self.assertEqual(len(client.bodies(0x30)), cycles)
                self.assertEqual(sum(b"Match 2 started" in body for body in client.bodies(0x21)), 1)

            until(lambda: status_path.exists() and all(
                player["ping_ms"] is not None for player in json.loads(status_path.read_text())["players"]), timeout=4)
            status = json.loads(status_path.read_text())
            self.assertEqual([player["slot"] for player in status["players"]], [1, 2])
            self.assertTrue(all(player["ping_ms"] >= 50 for player in status["players"]), status["players"])
            self.assertTrue(status["sustained_delivery"])
            self.assertEqual(status["impairment"]["rtt_ms"], 60)
            self.assertGreater(status["traffic"]["tx_bytes"], 0)
            self.assertNotIn("127.0.0.1", status_path.read_text())

            # B's client dies; its player logs in again from a new endpoint.
            b.silent = True
            pump(5.5)
            d = SyntheticClient(key)
            clients.append(d)
            join(d, arena_join=False)
            until(lambda: a.bodies(0x2D) == [b"\x02"])
            self.assertTrue(any(row.get("event") == "arena_departure" and row.get("reason") == "replaced by rejoin"
                                for row in logs))
            until(lambda: arena[1] in d.acks, retry=lambda: d.send(arena, 10, request()[:31] + d.acks[station[1]][13:]))
            d.slot = 3
            until(lambda: any(struct.unpack_from("<I", body, 0x28)[0] & 0xFF == 3 for body in a.bodies(0x26)),
                  timeout=8)
            console_out.write("kick 3\n")
            console_out.flush()
            until(lambda: a.bodies(0x2D) == [b"\x02", b"\x03"])
            self.assertTrue(any(row.get("event") == "host_kick" for row in logs))
            self.assertFalse(any(row.get("event") == "arena_departure" and row.get("slot") == 1 for row in logs),
                             "the active client sharing the IP must stay")
        finally:
            worker.join(50)
            for client in clients:
                client.sock.close()
        self.assertFalse(worker.is_alive())
        self.assertFalse(failures, failures)


if __name__ == "__main__":
    unittest.main(verbosity=2)
