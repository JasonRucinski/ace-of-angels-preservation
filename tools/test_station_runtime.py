"""Configuration, bounded I/O and live listing checks; localhost only."""
import contextlib
import io
import json
import queue
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import aoanet
import aoapack
import station_stub as stub
from station_runtime import EventLog, StationTCPServer, parse_args
from test_station_stub import request


def read_reply(client):
    with client.makefile("rb") as stream:
        header = stream.read(4)
        if len(header) != 4:
            raise AssertionError("missing TCP frame header")
        size = int.from_bytes(header, "little")
        body = stream.read(size)
        if len(body) != size:
            raise AssertionError("truncated TCP reply")
        return aoapack.decompress(body)[0] if size else b""


def job_request(job=5, identity=0, flag=0):
    header = bytearray(142)
    header[:12] = b"private-name"
    struct.pack_into("<I", header, 60, identity)
    header[128:130] = bytes([job, flag])
    return bytes(header)


def test_responder(request, address):
    return stub.tcp_reply(request[128]), "server_list" if request[128] == 5 else None, None


class RuntimeTests(unittest.TestCase):
    def test_configuration(self):
        base = ["key", "log"]
        diagnostic = parse_args(base)
        self.assertFalse(diagnostic.ack or diagnostic.arena or diagnostic.raw_capture)
        local = parse_args(base + ["--profile", "local-relay", "--arena-port", "6001"])
        self.assertTrue(local.ack and local.arena and local.experimental_relay)
        self.assertEqual((local.tcp, local.arena_port), (5034, 6001))
        for options in (["--unknown"], ["--port", "65536"], ["--seconds", "nan"],
                        ["--max-players", "0"], ["--max-players", "50"],
                        ["--peer-timeout", "inf"], ["--peer-timeout", "0"],
                        ["--experimental-relay"], ["--experimental-object"],
                        ["--profile", "local-relay", "--no-ack"],
                        ["--arena", "--arena-port", "5033"], ["--log-backups", "0"],
                        ["--log-max-bytes", "100"], ["--pilot", "\u2603"],
                        ["--spawn-axis", "y"], ["--spawn-spacing", "0"], ["--spawn-spacing", "nan"],
                        ["--kill-limit", "-1"], ["--time-limit", "nan"], ["--experimental-teams"],
                        ["--experimental-reliable-combat"]):
            with self.subTest(options=options), contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                parse_args(base + options)
        probe_options = ["--ack", "--arena", "--experimental-flight", "--max-players", "1",
                         "--experimental-protection-probe"]
        self.assertTrue(parse_args(base + probe_options).experimental_protection_probe)
        for options in (["--experimental-protection-probe"],
                        probe_options + ["--experimental-relay"],
                        probe_options + ["--max-players", "2"]):
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                parse_args(base + options)
        result = subprocess.run([sys.executable, "-I", str(Path(stub.__file__)),
                                 "nonexistent.key", "nonexistent.log", "--profile", "local-relay", "--print-config"],
                                capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(json.loads(result.stdout)["experimental_relay"])

    def test_log_redaction_rotation_and_capture(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "metadata.jsonl"
            with EventLog(path, max_bytes=16384, backups=2) as log:
                for i in range(800):
                    log({"event": "udp_packet", "type": 10, "len": 381, "wire_len": i,
                         "payload": "private-payload", "from": "private-address", "fields": {"handle": "private-name"}})
            files = list(Path(tmp).glob("metadata.jsonl*"))
            self.assertEqual(len(files), 3)
            for file in files:
                self.assertLessEqual(file.stat().st_size, 16384)
                text = file.read_text()
                self.assertNotIn("private", text)
                for line in text.splitlines():
                    self.assertEqual(json.loads(line)["event"], "udp_packet")
            self.assertFalse(log.failed)
            raw = Path(tmp) / "raw.jsonl"
            with EventLog(raw, raw=True) as capture:
                capture({"event": "udp_packet", "payload": "private-payload"})
                capture({"event": "udp_packet", "payload": "x" * 20000})
            rows = [json.loads(line) for line in raw.read_text().splitlines()]
            self.assertEqual(rows[0]["payload"], "private-payload")
            self.assertIn("raw_omitted", rows[1])

    def test_log_queue_does_not_block_producer(self):
        with tempfile.TemporaryDirectory() as tmp:
            entered, release = threading.Event(), threading.Event()
            log = EventLog(Path(tmp) / "log", queue_size=4)

            def paused_write(line):
                entered.set()
                release.wait(3)

            with patch.object(log, "_write", paused_write), log:
                log({"event": "start"})
                self.assertTrue(entered.wait(1))
                for _ in range(20):
                    log({"event": "packet"})
                self.assertEqual(log.queue.qsize(), 4)
                self.assertEqual(log.dropped, 16)
                release.set()
            self.assertFalse(log.failed)

    def test_tcp_slow_fragmented_truncated_and_shutdown(self):
        logs, notifications = [], queue.Queue(maxsize=1)
        with StationTCPServer(0, logs.append, True, test_responder, notifications) as server:
            endpoint = ("127.0.0.1", server.port)
            with socket.create_connection(endpoint, timeout=2) as slow:
                slow.sendall(b"x")
                with socket.create_connection(endpoint, timeout=2) as fast:
                    packet = job_request(flag=0xA7)
                    fast.sendall(packet[:71])
                    fast.sendall(packet[71:])
                    self.assertEqual(read_reply(fast), stub.TCP_JOB_BODIES[5])
                # A slow earlier connection cannot serialize other TCP jobs.
                self.assertEqual(notifications.get(timeout=1), "server_list")
                with socket.create_connection(endpoint, timeout=2) as truncated:
                    truncated.sendall(packet[:130])
                    truncated.shutdown(socket.SHUT_WR)
                    self.assertEqual(truncated.recv(4), b"")
                with socket.create_connection(endpoint, timeout=2) as unknown:
                    unknown.sendall(job_request(255))
                    self.assertEqual(read_reply(unknown), b"")
                with socket.create_connection(endpoint, timeout=2) as reset:
                    reset.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("HH", 1, 0))
                    reset.sendall(job_request())
                # Exhausted notifications must not block the worker. The reset
                # client's complete request may or may not have been answered
                # (and notified) before the reset arrived; drain either way.
                time.sleep(0.2)
                while not notifications.empty():
                    notifications.get_nowait()
                notifications.put_nowait("occupied")
                for _ in range(2):
                    with socket.create_connection(endpoint, timeout=2) as fast:
                        fast.sendall(job_request())
                        self.assertEqual(read_reply(fast), stub.TCP_JOB_BODIES[5])
                server.stop.set()
                server.thread.join(2)
                self.assertFalse(server.thread.is_alive())
                self.assertEqual(slow.recv(4), b"")
        self.assertTrue(any(record["status"] == "truncated" for record in logs))
        self.assertTrue(any(record["status"] == "shutdown" for record in logs))

    def test_tcp_deadline_and_capacity(self):
        logs = []
        with StationTCPServer(0, logs.append, True, test_responder, queue.Queue(1)) as server:
            server.MAX_CLIENTS, server.TIMEOUT = 1, 0.3
            endpoint = ("127.0.0.1", server.port)
            with socket.create_connection(endpoint, timeout=2) as slow:
                slow.sendall(b"x")
                time.sleep(0.05)
                with socket.create_connection(endpoint, timeout=2) as excess:
                    self.assertEqual(excess.recv(4), b"")
                self.assertEqual(slow.recv(4), b"")
            with socket.create_connection(endpoint, timeout=2) as recovered:
                recovered.sendall(job_request())
                self.assertEqual(read_reply(recovered), stub.TCP_JOB_BODIES[5])
        self.assertTrue(any(record["status"] == "timeout" for record in logs))

    def test_tcp_connection_kept_for_live_session(self):
        # The real client reuses its data socket; a server close trips its
        # stuck queue mutex (0x4366F0 -> 0x5E6700) and later deadlocks it.
        logs, live = [], {7}

        def responder(request, address):
            identity = struct.unpack_from("<I", request, 60)[0]
            known = identity in live
            return (stub.tcp_reply(request[128]) if known else bytes(4)), None, identity if known else None

        with StationTCPServer(0, logs.append, True, responder, queue.Queue(4),
                              lambda identity: identity in live) as server:
            server.TIMEOUT = 0.3
            endpoint = ("127.0.0.1", server.port)
            with socket.create_connection(endpoint, timeout=2) as client:
                client.sendall(job_request(14, identity=7))
                self.assertEqual(read_reply(client), stub.TCP_JOB_BODIES[14])
                time.sleep(0.5)  # Idle longer than TIMEOUT: still open.
                client.sendall(job_request(5, identity=7))
                self.assertEqual(read_reply(client), stub.TCP_JOB_BODIES[5])
                # A partial request on the kept connection is still bounded.
                client.sendall(b"x")
                self.assertEqual(client.recv(4), b"")
            with socket.create_connection(endpoint, timeout=2) as client:
                client.sendall(job_request(5, identity=7))
                self.assertEqual(read_reply(client), stub.TCP_JOB_BODIES[5])
                live.clear()  # Station session ends: the connection closes.
                self.assertEqual(client.recv(4), b"")
            with socket.create_connection(endpoint, timeout=2) as client:
                client.sendall(job_request(5, identity=9))
                self.assertEqual(read_reply(client), b"")
                self.assertEqual(client.recv(4), b"", "unresolved connections close after one reply")
        statuses = [(r["event"], r["status"]) for r in logs]
        self.assertEqual(statuses.count(("tcp_job", "complete")), 4)
        for status in ("timeout", "session_ended"):
            self.assertTrue(any(s == status for _, s in statuses), status)

    def test_live_profile_population_and_exhaustion(self):
        key = bytes(range(256))
        with tempfile.TemporaryDirectory() as tmp, contextlib.ExitStack() as resources:
            folder = Path(tmp)
            (folder / "key").write_bytes(key)
            # Distinct ephemeral UDP ports held until both are selected.
            probes = [socket.socket(socket.AF_INET, socket.SOCK_DGRAM) for _ in range(2)]
            for probe in probes:
                probe.bind(("127.0.0.1", 0))
            station_port, arena_port = [probe.getsockname()[1] for probe in probes]
            for probe in probes:
                probe.close()
            proc = subprocess.Popen([sys.executable, "-I", str(Path(stub.__file__)), str(folder / "key"),
                                     str(folder / "log"), "--profile", "local-relay", "--port", str(station_port),
                                     "--arena-port", str(arena_port), "--tcp", "0", "--seconds", "4"],
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            try:
                # TCP binding is synchronous; first flushed line reports its port.
                line = proc.stdout.readline()
                self.assertTrue(line.startswith("Station TCP on 127.0.0.1:"), line)
                tcp_port = int(line.strip().rsplit(":", 1)[1])
                station = resources.enter_context(socket.socket(socket.AF_INET, socket.SOCK_DGRAM))
                station.settimeout(2)
                station.sendto(aoanet.encode(10, request(), key), ("127.0.0.1", station_port))
                ack = aoanet.decode(station.recv(512), key)
                identity = struct.unpack_from("<I", ack["payload"], 13 + 0x7B)[0]

                def listing():
                    with socket.create_connection(("127.0.0.1", tcp_port), timeout=2) as client:
                        client.sendall(job_request(identity=identity))
                        return read_reply(client)

                def population():
                    body = listing()
                    self.assertEqual(len(body), 256)
                    self.assertEqual(body[128:160].split(b"\0")[0], b"Local Relay")
                    self.assertEqual(struct.unpack_from("<H", body, 128 + 0x72)[0], arena_port)
                    return struct.unpack_from("<I", body, 128 + 0x74)[0]

                self.assertEqual(population(), 0)
                slow = resources.enter_context(socket.create_connection(("127.0.0.1", tcp_port), timeout=2))
                slow.sendall(b"x")
                endpoint = ("127.0.0.1", arena_port)
                for index in range(49):
                    peer = resources.enter_context(socket.socket(socket.AF_INET, socket.SOCK_DGRAM))
                    peer.settimeout(2)
                    peer.sendto(aoanet.encode(10, request(), key), endpoint)
                    ack = aoanet.decode(peer.recv(512), key)
                    self.assertEqual(ack["type"], 11)
                    if index == 0:
                        self.assertEqual(population(), 1)
                        peer.sendto(aoanet.encode(10, request(), key), endpoint)
                        self.assertEqual(aoanet.decode(peer.recv(512), key)["type"], 11)
                        self.assertEqual(population(), 1)
                    peer.sendto(aoanet.encode(0x4E, b"\0", key), endpoint)
                    # A subsequent handshake is a same-socket processing barrier;
                    # retired endpoint receives no ACK, so use the next admission
                    # or polling of the immutable list snapshot for synchronization.
                    if index == 0:
                        deadline = time.monotonic() + 1
                        while population() != 0:
                            self.assertLess(time.monotonic(), deadline)
                deadline = time.monotonic() + 1
                while len(listing()) != 128:
                    self.assertLess(time.monotonic(), deadline)
                stdout, stderr = proc.communicate(timeout=7)
                self.assertEqual(proc.returncode, 0, stderr)
                self.assertIn("writer_failed=False", stdout)
                text = (folder / "log").read_text()
                self.assertNotIn("testpilot", text)
                self.assertNotIn(request().hex(), text)
                self.assertNotIn("private-name", text)
                self.assertTrue(any(json.loads(line).get("event") == "arena_departure" for line in text.splitlines()))
            finally:
                if proc.poll() is None:
                    proc.terminate()
                proc.communicate(timeout=5)


if __name__ == "__main__":
    unittest.main(verbosity=2)
