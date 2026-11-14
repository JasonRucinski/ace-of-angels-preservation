"""LAN configuration plus synthetic sockets; no real-client/LAN gameplay claim.

The listener test redirects only its fixture LAN bind address to loopback.
It exercises the actual LAN profile without requiring a particular adapter.
"""
import contextlib
import io
import select
import socket
import struct
import sys
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import aoanet
import station_stub as stub
from station_runtime import parse_args
from test_station_runtime import job_request, read_reply
import test_station_stub
from test_station_stub import request


class LanDogfightTests(unittest.TestCase):
    def test_profile_address_boundaries(self):
        base = ["key", "log", "--profile", "lan-dogfight"]
        for address in ("10.1.2.3", "172.16.1.2", "172.31.255.254", "192.168.1.55"):
            args = parse_args(base + ["--bind-address", address])
            self.assertEqual(args.advertised_address, address)
            self.assertTrue(args.guest_sessions and args.experimental_relay and args.ack and args.arena)
            self.assertEqual((args.port, args.arena_port, args.tcp), (5033, 5031, 5034))
            self.assertFalse(args.experimental_reliable_combat)
        for address in ("127.0.0.1", "0.0.0.0", "8.8.8.8", "100.64.0.1", "169.254.1.2",
                        "172.15.0.1", "172.32.0.1", "224.0.0.1", "::1", "host", "192.168.1.999"):
            with self.subTest(address=address), contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                parse_args(base + ["--bind-address", address])
        for options in (["--advertised-address", "192.168.1.56"], ["--no-ack"], ["--no-arena"],
                        ["--no-experimental-relay"], ["--experimental-flight"], ["--max-players", "9"],
                        ["--experimental-reliable-combat"], ["--experimental-protection-probe"],
                        ["--experimental-object"], ["--experimental-teams"]):
            with self.subTest(options=options), contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                parse_args(base + ["--bind-address", "192.168.1.55"] + options)
        for profile in ("diagnostic", "local-relay", "local-guests"):
            args = parse_args(["key", "log", "--profile", profile])
            self.assertEqual((args.bind_address, args.advertised_address), ("127.0.0.1", "127.0.0.1"))
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                parse_args(["key", "log", "--profile", profile, "--bind-address", "192.168.1.55"])

    def test_map_and_backdrop_allowlist(self):
        default = parse_args(["key", "log"])
        self.assertEqual((default.map, default.backdrop), ("CTF_arena", "spacebkgd3"))
        for terrain in ("CTF_arena", "Arena1a"):
            for backdrop in ("spacebkgd", "spacebkgd2", "spacebkgd3", "spacebkgd5", "spacebkgd6"):
                args = parse_args(["key", "log", "--map", terrain, "--backdrop", backdrop])
                listing = stub.server_list_body(2, 5031, terrain=args.map, backdrop=args.backdrop)
                self.assertEqual(listing[0xa0:0xc0].split(b"\0")[0], terrain.encode())
                self.assertEqual(listing[0xc0:0xe0].split(b"\0")[0], backdrop.encode())
        for options in (["--map", "../Arena1a"], ["--map", "Curt3"], ["--backdrop", "field40"]):
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                parse_args(["key", "log"] + options)

    def test_guest_tickets_are_bound_to_source_ip(self):
        sessions = stub.StationSessions(30, guests=True)
        owners = [("192.168.1.11", 10001), ("192.168.1.12", 10001)]
        identities = [sessions.admit(peer, request(), 0) for peer in owners]
        self.assertNotEqual(*identities)
        for peer, identity in zip(owners, identities):
            name = sessions.peers[peer]["pilot"]
            ack = stub.ack_connect(request(), station_id=identity, pilot_name=name)[1]
            arena_request = request()[:31] + ack[13:]
            self.assertEqual(sessions.arena_owner(arena_request, peer, 1), identity)
            other = owners[1] if peer == owners[0] else owners[0]
            self.assertIsNone(sessions.arena_owner(arena_request, other, 1))
            self.assertIsNone(sessions.resolve(job_request(identity=identity), other, 1))
        self.assertNotEqual(*(sessions.peers[peer]["pilot"] for peer in owners))

    def test_lan_profile_listeners_and_sustained_combat(self):
        address = "192.168.1.55"
        args = parse_args(["key", "log", "--profile", "lan-dogfight", "--bind-address", address,
                           "--port", "0", "--arena-port", "0", "--tcp", "0", "--seconds", "15",
                           "--kill-limit", "1", "--time-limit", "0", "--map", "Arena1a", "--backdrop", "spacebkgd2"])
        key = bytes(range(256))
        bindings, failures, logs = [], [], []
        original_bind = socket.socket.bind

        def fixture_bind(sock, endpoint):
            if endpoint[0] == address:
                original_bind(sock, ("127.0.0.1", endpoint[1]))
                bindings.append((sock.type, endpoint[0], sock.getsockname()[1]))
            else:
                original_bind(sock, endpoint)

        def server():
            try:
                with contextlib.ExitStack() as resources:
                    stub.run(args, key, logs.append, resources)
            except BaseException as error:
                failures.append(error)

        with patch.object(socket.socket, "bind", fixture_bind), contextlib.ExitStack() as resources:
            worker = threading.Thread(target=server, daemon=True)
            worker.start()
            peers = [resources.enter_context(socket.socket(socket.AF_INET, socket.SOCK_DGRAM)) for _ in range(2)]
            for peer in peers:
                peer.bind(("127.0.0.1", 0))
            messages = {peer: [] for peer in peers}
            slots = {peer: index + 1 for index, peer in enumerate(peers)}

            def send(peer, endpoint, kind, body):
                peer.sendto(aoanet.encode(kind, body, key), endpoint)

            def pump(duration):
                deadline = time.monotonic() + duration
                while time.monotonic() < deadline:
                    ready, _, _ = select.select(peers, [], [], min(.01, max(0, deadline - time.monotonic())))
                    for peer in ready:
                        wire, source = peer.recvfrom(512)
                        msg = aoanet.decode(wire, key)
                        self.assertTrue(msg["crc_ok"])
                        kind, body = msg["type"], msg["payload"]
                        if kind == 8:
                            reply = bytearray(body)
                            reply[6] = slots[peer]
                            send(peer, source, 9, reply)
                        if kind == 0x1B:
                            send(peer, source, 0x0F, body[-5:-1])
                        messages[peer].append((kind, body))

            def bodies(peer, kind):
                return [body for k, body in messages[peer] if k == kind]

            def until(predicate, timeout=2):
                deadline = time.monotonic() + timeout
                while not predicate():
                    self.assertFalse(failures, failures)
                    self.assertLess(time.monotonic(), deadline, "expected relay response missing")
                    pump(.01)

            try:
                until(lambda: len(bindings) == 3)
                self.assertEqual([b[:2] for b in bindings], [(socket.SOCK_DGRAM, address),
                                                           (socket.SOCK_DGRAM, address),
                                                           (socket.SOCK_STREAM, address)])
                station, arena, tcp = [("127.0.0.1", binding[2]) for binding in bindings]
                for peer in peers:
                    send(peer, station, 10, request())
                    until(lambda: bool(bodies(peer, 11)))
                    ack = bodies(peer, 11)[-1]
                    identity = struct.unpack_from("<I", ack, 136)[0]
                    with socket.create_connection(tcp, timeout=2) as client:
                        client.sendall(job_request(identity=identity))
                        listing = read_reply(client)
                    self.assertEqual(listing[0x80 + 0x60:0x80 + 0x72].split(b"\0")[0], address.encode())
                    self.assertEqual(listing[0xa0:0xc0].split(b"\0")[0], b"Arena1a")
                    self.assertEqual(listing[0xc0:0xe0].split(b"\0")[0], b"spacebkgd2")
                    self.assertEqual(struct.unpack_from("<H", listing, 0x80 + 0x72)[0], arena[1])
                    messages[peer].clear()
                    send(peer, arena, 10, request()[:31] + ack[13:])
                    until(lambda: bool(bodies(peer, 11)))
                    self.assertEqual(struct.unpack_from("<I", bodies(peer, 11)[-1], 6)[0], 0)
                until(lambda: all(bodies(p, 0x2C) for p in peers), timeout=4)
                a, b = peers
                # 120 events per observer, not the bounded reliable experiment.
                for index in range(60):
                    send(a, arena, 0x2A, test_station_stub.ProtocolTests.fire_missile())
                    until(lambda: all(len(bodies(p, 0x2A)) == index + 1 for p in peers))
                    tag = struct.unpack_from("<I", bodies(a, 0x2A)[-1], 0x10)[0]
                    impact = struct.pack("<II3fB", tag, stub.player_tag(2), 0, 0, 5000, 1)
                    send(b, arena, 0x30, impact)
                    send(b, arena, 0x30, impact)
                    until(lambda: all(len(bodies(p, 0x30)) == index + 1 for p in peers))
                    pump(.04)  # remain within existing per-peer ingress budget
                for expected_round in (2, 3):
                    send(b, arena, 0x37, struct.pack("<I", stub.player_tag(1)))
                    send(b, arena, 0x37, struct.pack("<I", stub.player_tag(1)))
                    text = f"Match {expected_round} started".encode()
                    until(lambda: all(any(text in body for body in bodies(p, 0x21)) for p in peers))
                    # The reset record follows the announcement in a separate
                    # datagram; seeing the text does not mean it is received.
                    until(lambda: all(bodies(p, 0x42) and struct.unpack_from(
                        "<ii", bodies(p, 0x42)[-1], 4 + 0x7F) == (0, 0) for p in peers))
                    for peer in peers:
                        self.assertEqual(struct.unpack_from("<ii", bodies(peer, 0x42)[-1], 4 + 0x7F), (0, 0))
                    self.assertEqual(len(bodies(a, 0x38)), expected_round - 1)
                    self.assertFalse(bodies(b, 0x38), "victim must not receive another death notification")
                    self.assertEqual(struct.unpack("<3f", bodies(b, 0x24)[-1]), stub.spawn_position(2))
                    if expected_round == 2:
                        pump(2.1)  # original death-report suppression window
                self.assertEqual(sum(row.get("event") == "match_end" for row in logs), 2)
                self.assertFalse(any(row.get("event") == "arena_departure" for row in logs))
                self.assertFalse(any(bodies(p, 0x1B) for p in peers), "combat entered reliable history")
            finally:
                worker.join(17)
                self.assertFalse(worker.is_alive())
                self.assertFalse(failures, failures)


if __name__ == "__main__":
    unittest.main(verbosity=2)
