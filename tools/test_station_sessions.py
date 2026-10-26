"""Session routing and lifecycle regressions; synthetic loopback clients only."""
import contextlib
import socket
import struct
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import aoanet
import station_stub as stub
from test_station_runtime import job_request, read_reply
from test_station_stub import request


class StationSessionTests(unittest.TestCase):
    def test_guest_ticket_ownership_and_lease(self):
        sessions = stub.StationSessions(3, pilot="abcdefghijklmnopqrs", guests=True)
        station_peer, arena_peer, intruder = ("127.0.0.1", 1), ("127.0.0.1", 2), ("127.0.0.1", 3)
        with patch.object(stub.secrets, "randbits", side_effect=[0, 12345]):
            identity = sessions.admit(station_peer, request(), 0)
        self.assertEqual(identity, 12345)
        name = sessions.peers[station_peer]["pilot"]
        self.assertEqual(name, "abcdefghijklmnop-01")
        ack = stub.ack_connect(request(), station_id=identity, pilot_name=name)[1]
        arena_request = request()[:31] + ack[13:]
        self.assertEqual(sessions.arena_owner(arena_request, arena_peer, 1), identity)
        self.assertIsNone(sessions.arena_owner(request(), arena_peer, 1))
        self.assertIsNone(sessions.arena_owner(arena_request, ("127.0.0.2", 2), 1))
        changed = bytearray(arena_request)
        changed[31] ^= 1
        self.assertIsNone(sessions.arena_owner(changed, arena_peer, 1))
        sessions.bind_arena(identity, arena_peer, 6)
        self.assertIsNone(sessions.arena_owner(arena_request, intruder, 2))
        self.assertEqual(sessions.pings(2), [])
        sessions.renew_arena(arena_peer, 10)
        self.assertEqual(sessions.resolve(job_request(identity=identity), station_peer, 9), identity)
        sessions.release_arena(arena_peer, 9)
        self.assertIsNone(sessions.peers[station_peer]["arena"])
        self.assertEqual(sessions.peers[station_peer]["expiry"], 12)
        sessions.depart(station_peer)
        with patch.object(stub.secrets, "randbits", side_effect=[12345, 67890]):
            second_id = sessions.admit(intruder, request(), 10)
        self.assertEqual(second_id, 67890)
        self.assertEqual(sessions.peers[intruder]["pilot"], "abcdefghijklmnop-02")

    def test_shared_socket_binds_station_to_arena(self):
        # The real client uses one UDP socket for Station and arena. Once the
        # arena admits it, Station must stop pinging that socket (9.28).
        key = bytes(range(256))
        with tempfile.TemporaryDirectory() as tmp, contextlib.ExitStack() as resources:
            folder = Path(tmp)
            (folder / "key").write_bytes(key)
            probes = [resources.enter_context(socket.socket(socket.AF_INET, socket.SOCK_DGRAM)) for _ in range(2)]
            for probe in probes:
                probe.bind(("127.0.0.1", 0))
            station_port, arena_port = [probe.getsockname()[1] for probe in probes]
            for probe in probes:
                probe.close()
            proc = subprocess.Popen([sys.executable, "-I", str(Path(stub.__file__)), str(folder / "key"),
                                     str(folder / "log"), "--profile", "local-relay", "--port", str(station_port),
                                     "--arena-port", str(arena_port), "--tcp", "0", "--seconds", "12"],
                                    stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            try:
                client = resources.enter_context(socket.socket(socket.AF_INET, socket.SOCK_DGRAM))
                client.bind(("127.0.0.1", 0))
                client.settimeout(0.2)

                def collect(seconds):
                    got, end = [], time.monotonic() + seconds
                    while time.monotonic() < end:
                        try:
                            data, source = client.recvfrom(512)
                        except (socket.timeout, ConnectionResetError):
                            continue
                        got.append((source[1], aoanet.decode(data, key)["type"]))
                    return got

                deadline = time.monotonic() + 5
                while not any(kind == 11 for _, kind in collect(0.2)):
                    client.sendto(aoanet.encode(10, request(), key), ("127.0.0.1", station_port))
                    self.assertLess(time.monotonic(), deadline, "Station did not start")
                self.assertIn((station_port, 8), collect(2.2), "Station pings before arena entry")
                client.sendto(aoanet.encode(10, request(), key), ("127.0.0.1", arena_port))
                after = collect(2.5)
                self.assertIn((arena_port, 11), after)
                self.assertNotIn((station_port, 8), after, "Station still pings the shared socket")
            finally:
                proc.terminate()
                proc.communicate(timeout=5)

    def test_retries_routing_departure_and_capacity(self):
        sessions = stub.StationSessions(30)
        first, second = ("127.0.0.1", 10001), ("127.0.0.1", 10002)
        identity = sessions.admit(first, request(), 0)
        other = sessions.admit(second, request(), 0)
        self.assertNotEqual(identity, other)
        self.assertEqual(sessions.admit(first, request(), 5), identity)
        self.assertEqual(sessions.peers[first]["expiry"], 30)
        self.assertIsNone(sessions.admit(first, bytes(381), 5))
        self.assertEqual(sessions.resolve(job_request(identity=identity), second, 5), identity)
        self.assertIsNone(sessions.resolve(job_request(identity=identity), ("127.0.0.2", 1), 5))
        self.assertIsNone(sessions.resolve(job_request(), first, 5))
        self.assertEqual(sessions.alias_target(identity, 5), first)
        sessions.admit(first, request(), 6)
        self.assertIsNone(sessions.alias_target(identity, 6))
        self.assertTrue(sessions.depart(first))
        self.assertFalse(sessions.depart(first))
        self.assertIsNone(sessions.resolve(job_request(identity=identity), first, 7))
        self.assertIsNone(sessions.alias_target(identity, 7))
        self.assertIsNone(sessions.admit(first, request(), 7))
        for index in range(2, sessions.CAPACITY):
            self.assertIsNotNone(sessions.admit(("127.0.0.1", 10001 + index), request(), 7))
        self.assertIsNone(sessions.admit(("127.0.0.1", 20000), request(), 7))
        self.assertEqual(len(sessions.peers) + len(sessions.retired), sessions.CAPACITY)

    def test_heartbeat_validation_and_expired_notifications(self):
        sessions = stub.StationSessions(3)
        peer = ("127.0.0.1", 10001)
        identity = sessions.admit(peer, request(), 0)
        self.assertEqual(sessions.pings(0), [])
        ((target, (kind, payload)),) = sessions.pings(1)
        self.assertEqual((target, kind), (peer, 8))
        bounce = bytearray(payload)
        # Any echoed tag: the real client reports its arena slot here.
        bounce[6] = 2
        self.assertFalse(sessions.heartbeat(peer, bounce[:-1], 2))
        self.assertFalse(sessions.heartbeat((peer[0], 2), bounce, 2))
        self.assertTrue(sessions.heartbeat(peer, bounce, 2))
        self.assertFalse(sessions.heartbeat(peer, bounce, 3))  # Consumed timestamp.
        self.assertEqual(sessions.peers[peer]["expiry"], 5)
        self.assertEqual(sessions.resolve(job_request(identity=identity), peer, 4), identity)
        self.assertIsNone(sessions.resolve(job_request(identity=identity), peer, 5))
        self.assertIsNone(sessions.alias_target(identity, 5))
        self.assertIsNone(sessions.admit(peer, request(), 5))
        late = bytearray(sessions.pings(4)[0][1][1])
        late[6] = 1
        self.assertFalse(sessions.heartbeat(peer, late, 5))
        self.assertEqual(sessions.pings(6), [])

    def test_two_clients_same_ip_and_stale_tcp(self):
        key = bytes(range(256))
        with tempfile.TemporaryDirectory() as tmp, contextlib.ExitStack() as resources:
            folder = Path(tmp)
            (folder / "key").write_bytes(key)
            proc = subprocess.Popen([sys.executable, "-I", str(Path(stub.__file__)),
                                     str(folder / "key"), str(folder / "log"), "--ack",
                                     "--port", "0", "--tcp", "0", "--peer-timeout", "3", "--seconds", "15"],
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            try:
                tcp_port = int(proc.stdout.readline().strip().rsplit(":", 1)[1])
                udp_line = proc.stdout.readline()
                udp_port = int(udp_line.split("127.0.0.1:")[1].split()[0])
                endpoint = ("127.0.0.1", udp_port)

                def peer():
                    client = resources.enter_context(socket.socket(socket.AF_INET, socket.SOCK_DGRAM))
                    client.settimeout(2)
                    return client

                def receive(client, expected):
                    deadline = time.monotonic() + 2
                    while time.monotonic() < deadline:
                        packet = aoanet.decode(client.recv(1024), key)
                        self.assertTrue(packet["crc_ok"])
                        if packet["type"] == 8:
                            bounce = bytearray(packet["payload"])
                            bounce[6] = 1
                            client.sendto(aoanet.encode(9, bounce, key), endpoint)
                        else:
                            self.assertEqual(packet["type"], expected)
                            return packet["payload"]
                    self.fail("expected response did not arrive")

                def join(client):
                    client.sendto(aoanet.encode(10, request(), key), endpoint)
                    return struct.unpack_from("<I", receive(client, 11), 13 + 0x7B)[0]

                def listing(identity, job=5):
                    with socket.create_connection(("127.0.0.1", tcp_port), timeout=2) as client:
                        client.sendall(job_request(job, identity, flag=0xA7))
                        return read_reply(client)

                first, second = peer(), peer()
                first_id, second_id = join(first), join(second)
                self.assertNotEqual(first_id, second_id)
                # Second joined most recently, but first's request must target first.
                self.assertEqual(struct.unpack_from("<I", listing(first_id), 0x74)[0], 2)
                self.assertEqual(receive(first, 0x9A), stub.pilot_list())
                listing(second_id)
                self.assertEqual(receive(second, 0x9A), stub.pilot_list())
                self.assertEqual(listing(first_id, 14), bytes(128))
                self.assertEqual(listing(0), b"")
                self.assertEqual(listing(999), b"")
                self.assertEqual(listing(first_id, 255), b"")

                first.sendto(aoanet.encode(0x1B, request() + struct.pack("<I", 123) + b"\x0a", key), endpoint)
                self.assertEqual(receive(first, 15), struct.pack("<I", 123))
                self.assertEqual(struct.unpack_from("<I", receive(first, 11), 13 + 0x7B)[0], first_id)
                self.assertEqual(struct.unpack_from("<I", listing(first_id), 0x74)[0], 2)
                # Retry cannot reset alias state. A duplicate alias would precede
                # the following ACK and fail receive's exact message-type check.
                self.assertEqual(join(first), first_id)

                partial = resources.enter_context(socket.create_connection(("127.0.0.1", tcp_port), timeout=2))
                pending = job_request(identity=first_id)
                partial.sendall(pending[:71])
                first.sendto(aoanet.encode(0x4E, b"\0", key), endpoint)
                deadline = time.monotonic() + 1
                while struct.unpack_from("<I", listing(second_id), 0x74)[0] != 1:
                    self.assertLess(time.monotonic(), deadline)
                partial.sendall(pending[71:])
                self.assertEqual(read_reply(partial), b"")
                self.assertEqual(listing(first_id), b"")

                third = peer()
                third_id = join(third)
                self.assertNotIn(third_id, (first_id, second_id))
                self.assertEqual(struct.unpack_from("<I", listing(second_id), 0x74)[0], 2)
                # Keep second alive with validated bounces while third expires.
                second.settimeout(0.1)
                deadline = time.monotonic() + 5
                while True:
                    try:
                        packet = aoanet.decode(second.recv(1024), key)
                        self.assertEqual(packet["type"], 8)  # No cross-session/duplicate alias.
                        bounce = bytearray(packet["payload"])
                        bounce[6] = 1
                        second.sendto(aoanet.encode(9, bounce, key), endpoint)
                    except socket.timeout:
                        pass
                    body = listing(second_id)
                    self.assertEqual(len(body), 128)
                    if struct.unpack_from("<I", body, 0x74)[0] == 1:
                        break
                    self.assertLess(time.monotonic(), deadline)
                self.assertEqual(listing(third_id), b"")
                self.assertIsNone(proc.poll())
            finally:
                if proc.poll() is None:
                    proc.terminate()
                proc.communicate(timeout=5)


if __name__ == "__main__":
    unittest.main(verbosity=2)
