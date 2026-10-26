"""End-to-end opt-in local guest ownership; no real client or public service."""
import contextlib
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
import station_stub
from station_runtime import parse_args
from test_station_runtime import job_request, read_reply
from test_station_stub import request


class GuestAdmissionTests(unittest.TestCase):
    def test_profile_and_socket_ownership(self):
        self.assertTrue(parse_args(["key", "log", "--profile", "local-guests"]).guest_sessions)
        self.assertFalse(parse_args(["key", "log", "--profile", "local-relay"]).guest_sessions)
        key = bytes(range(256))
        with tempfile.TemporaryDirectory() as tmp, contextlib.ExitStack() as resources:
            folder = Path(tmp)
            (folder / "key").write_bytes(key)
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
                probe.bind(("127.0.0.1", 0))
                arena = probe.getsockname()
            proc = subprocess.Popen([sys.executable, "-I", str(Path(station_stub.__file__)), str(folder / "key"),
                                     str(folder / "log"), "--profile", "local-guests", "--port", "0", "--tcp", "0",
                                     "--arena-port", str(arena[1]), "--peer-timeout", "3", "--seconds", "20"],
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            peers = [resources.enter_context(socket.socket(socket.AF_INET, socket.SOCK_DGRAM)) for _ in range(5)]
            for peer in peers:
                peer.settimeout(0.2)
            try:
                tcp_port = int(proc.stdout.readline().strip().rsplit(":", 1)[1])
                station_port = int(proc.stdout.readline().split("127.0.0.1:")[1].split()[0])
                station = ("127.0.0.1", station_port)
                s1, s2, a1, a2, attacker = peers
                slots = {s1: 1, s2: 1, a1: 1, a2: 2}

                def send(peer, endpoint, kind, data):
                    peer.sendto(aoanet.encode(kind, data, key), endpoint)

                def receive(peer, expected, timeout=5):
                    deadline = time.monotonic() + timeout
                    while time.monotonic() < deadline:
                        try:
                            message = aoanet.decode(peer.recv(512), key)
                        except socket.timeout:
                            continue
                        if message["type"] == 8 and peer in slots:
                            bounce = bytearray(message["payload"])
                            bounce[6] = slots[peer]
                            send(peer, station if peer in (s1, s2) else arena, 9, bounce)
                        if message["type"] == expected:
                            return message["payload"]
                    self.fail(f"missing message {expected}")

                def connect(peer, endpoint, body):
                    send(peer, endpoint, 10, body)
                    return receive(peer, 11)

                def listing(identity):
                    with socket.create_connection(("127.0.0.1", tcp_port), timeout=2) as client:
                        client.sendall(job_request(identity=identity))
                        return read_reply(client)

                self.assertEqual(struct.unpack_from("<I", connect(attacker, arena, request()), 6)[0], 5)
                ack1, ack2 = connect(s1, station, request()), connect(s2, station, request())
                id1, id2 = (struct.unpack_from("<I", ack, 136)[0] for ack in (ack1, ack2))
                self.assertNotEqual(id1, id2)
                names = [ack[13:33].split(b"\0")[0] for ack in (ack1, ack2)]
                self.assertEqual(names, [b"testpilot-01", b"testpilot-02"])
                for peer, identity, name in ((s1, id1, names[0]), (s2, id2, names[1])):
                    listing(identity)
                    self.assertEqual(receive(peer, 0x9A)[:32].split(b"\0")[0], name)
                req1, req2 = request()[:31] + ack1[13:], request()[:31] + ack2[13:]
                bad_name = bytearray(req2)
                bad_name[31:51] = req1[31:51]
                self.assertEqual(struct.unpack_from("<I", connect(attacker, arena, bad_name), 6)[0], 5)
                accepted1 = connect(a1, arena, req1)
                self.assertEqual(struct.unpack_from("<II", accepted1, 2), (0x80010001, 0))
                self.assertEqual(connect(a1, arena, req1), accepted1)
                # A different socket cannot replace the endpoint owning a ticket.
                self.assertEqual(struct.unpack_from("<I", connect(attacker, arena, req1), 6)[0], 5)
                accepted2 = connect(a2, arena, req2)
                self.assertEqual(struct.unpack_from("<II", accepted2, 2), (0x80010002, 0))
                send(s1, station, 0x4E, b"\0")
                deadline = time.monotonic() + 2
                while listing(id1):
                    self.assertLess(time.monotonic(), deadline)
                self.assertEqual(struct.unpack_from("<I", connect(attacker, arena, req1), 6)[0], 5)
                loaded = receive(a2, 0x26)
                self.assertEqual(struct.unpack_from("<I", loaded, 40)[0], 0x80010002)
                self.assertEqual(loaded[70:90].split(b"\0")[0], names[1])
                receive(a2, 0x24)
                # Station lease follows valid arena heartbeats, not idle Station
                # socket traffic. Keep flying past the original Station expiry.
                for _ in range(4):
                    receive(a2, 8)
                self.assertEqual(struct.unpack_from("<I", listing(id2), 0x74)[0], 1)
                send(s2, station, 0x4E, b"\0")
                deadline = time.monotonic() + 2
                while listing(id2):
                    self.assertLess(time.monotonic(), deadline)
                self.assertIsNone(proc.poll())
            finally:
                if proc.poll() is None:
                    proc.terminate()
                proc.communicate(timeout=5)


if __name__ == "__main__":
    unittest.main(verbosity=2)
