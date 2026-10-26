"""Dedicated host lifecycle: real child processes and synthetic loopback clients."""
import contextlib
import json
import os
import select
import signal
import socket
import struct
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dedicated_host as dedicated
import online_terrain
import station_stub as stub
from test_internet_play import SyntheticClient
from test_station_runtime import job_request, read_reply
from test_station_stub import request


class DedicatedTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.key = bytes(range(256))
        (self.folder / "key").write_bytes(self.key)
        self.settings = {**dedicated.DEFAULTS, "maps": ["CTF_arena", "CTF_arena_b"],
                         "kill_limit": 1, "time_limit_seconds": 0, "restart_warning_seconds": 1.5,
                         "intermission_seconds": 0.1, "idle_recycle_seconds": 0}
        self.config = self.folder / "rotation.json"
        self.config.write_text(json.dumps(self.settings))
        self.status_path = self.folder / "status.json"
        self.state_path = self.folder / "state.json"
        self.clients, self.connections, self.processes = [], [], []
        self.addCleanup(self.close)
        self.ports = []
        with contextlib.ExitStack() as stack:
            for kind in (socket.SOCK_DGRAM, socket.SOCK_DGRAM, socket.SOCK_STREAM):
                probe = stack.enter_context(socket.socket(socket.AF_INET, kind))
                probe.bind(("127.0.0.1", 0))
                self.ports.append(probe.getsockname()[1])
        self.station, self.arena, self.tcp = [("127.0.0.1", p) for p in self.ports]

    def close(self):
        for proc, stream in reversed(self.processes):
            dedicated.stop_child(proc)
            stream.close()
        for connection in self.connections:
            connection.close()
        for client in self.clients:
            client.sock.close()

    def launch(self, controller=False, extra=()):
        tool = "dedicated_host.py" if controller else "station_stub.py"
        arguments = [str(self.folder / "key"), str(self.folder / "events.jsonl"),
                     "--profile", "local-guests", "--port", str(self.ports[0]),
                     "--arena-port", str(self.ports[1]), "--tcp", str(self.ports[2]),
                     "--status-file", str(self.status_path)]
        if controller:
            arguments += ["--config", str(self.config), "--state-file", str(self.state_path)]
        else:
            arguments += ["--managed-session", "--next-map", "CTF_arena_b", "--sustained-delivery",
                          "--experimental-terrain", "--kill-limit", "1", "--time-limit", "0",
                          "--idle-recycle", "0", "--restart-warning", "1.5", "--seconds", "20"]
        stream = (self.folder / f"process-{len(self.processes)}.log").open("w+")
        proc = subprocess.Popen([sys.executable, "-I", "-S", "-u", str(Path(__file__).with_name(tool)),
                                 *arguments, *extra], stdin=subprocess.DEVNULL,
                                stdout=stream, stderr=subprocess.STDOUT,
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        self.processes.append((proc, stream))
        self.until(lambda: self.status().get("pid") is not None, proc=proc)
        return proc

    def status(self):
        try:
            return json.loads(self.status_path.read_text())
        except (OSError, ValueError):
            return {}

    def pump(self, seconds=0.03):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            if not self.clients:
                time.sleep(0.01)
                continue
            ready, _, _ = select.select([c.sock for c in self.clients], [], [], 0.01)
            for client in self.clients:
                if client.sock in ready:
                    client.handle(*client.sock.recvfrom(512))
                client.resend()

    def until(self, predicate, timeout=10, proc=None):
        deadline = time.monotonic() + timeout
        while not predicate():
            if proc is not None and proc.poll() is not None:
                self.fail(f"host exited {proc.returncode}: " +
                          (self.folder / f"process-{len(self.processes)-1}.log").read_text())
            self.assertLess(time.monotonic(), deadline, "host response missing")
            self.pump()

    def login(self, arena=True):
        client = SyntheticClient(self.key)
        self.clients.append(client)
        client.send(self.station, 10, request())
        self.until(lambda: self.ports[0] in client.acks)
        ack = client.acks[self.ports[0]]
        self.assertEqual(struct.unpack_from("<I", ack, 6)[0], 0)
        if arena:
            connection = socket.create_connection(self.tcp, timeout=3)
            self.connections.append(connection)
            connection.sendall(job_request(identity=struct.unpack_from("<I", ack, 136)[0]))
            listing = read_reply(connection)
            self.assertIn(self.status()["map"].encode(), listing)
            client.send(self.arena, 10, request()[:31] + ack[13:])
            self.until(lambda: self.ports[1] in client.acks)
            arena_ack = client.acks[self.ports[1]]
            self.assertEqual(struct.unpack_from("<I", arena_ack, 6)[0], 0)
            client.slot = struct.unpack_from("<I", arena_ack, 2)[0] & 0xFF
        return client

    def completed(self, proc, reason):
        self.until(lambda: proc.poll() is not None)
        self.assertEqual(proc.returncode, dedicated.SESSION_COMPLETE)
        self.assertEqual(self.status()["lifecycle"]["restart_reason"], reason)

    def test_configuration_and_state(self):
        self.assertEqual(dedicated.load_config(self.config)["maps"], self.settings["maps"])
        for patch in ({"maps": []}, {"maps": ["../bad"]}, {"maps": ["Arena1a", "Arena1a"]},
                      {"kill_limit": True}, {"time_limit_seconds": float("nan")},
                      {"kill_limit": 0, "time_limit_seconds": 0}, {"recycle_arena_joins": 49},
                      {"recycle_station_admissions": 64}, {"terrain": False}, {"unknown": 1}):
            with self.subTest(patch=patch):
                self.config.write_text(json.dumps({**self.settings, **patch}))
                with self.assertRaises(ValueError):
                    dedicated.load_config(self.config)
        state = {"schema": 1, "map": "CTF_arena_b", "sessions_completed": 4}
        self.state_path.write_text(json.dumps(state))
        self.assertEqual(dedicated.load_state(self.state_path, self.settings["maps"]), state)
        self.assertEqual(dedicated.load_state(self.state_path, ["Arena1a"])["map"], "Arena1a")
        self.state_path.write_text('{"schema":1,"map":"CTF_arena","sessions_completed":-1}')
        with self.assertRaises(ValueError):
            dedicated.load_state(self.state_path, self.settings["maps"])

    def test_kill_limit_announces_drains_and_keeps_final_score(self):
        proc = self.launch()
        a, b = self.login(), self.login()
        self.until(lambda: all(c.bodies(0x2C) for c in (a, b)))
        self.assertEqual(a.bodies(0x2C)[0], online_terrain.marker("CTF_arena"))
        b.send_reliable(self.arena, 0x37, struct.pack("<I", stub.player_tag(a.slot)))
        self.until(lambda: any(b"Next map CTF_arena_b" in body for body in a.bodies(0x21)))
        stranger = SyntheticClient(self.key)
        self.clients.append(stranger)
        stranger.send(self.station, 10, request())
        self.until(lambda: self.ports[0] in stranger.acks)
        self.assertEqual(struct.unpack_from("<I", stranger.acks[self.ports[0]], 6)[0], 4)
        self.completed(proc, "kill limit")
        players = {p["slot"]: p for p in self.status()["players"]}
        self.assertEqual(players[a.slot]["kills"], 1)
        self.assertEqual(players[b.slot]["deaths"], 1)
        self.assertEqual(self.status()["station_admissions_used"], 2)

    def test_time_limit_starts_with_flight_not_empty_server(self):
        proc = self.launch(extra=("--kill-limit", "0", "--time-limit", "0.5", "--restart-warning", "0.2"))
        self.pump(1)
        self.assertIsNone(proc.poll())
        client = self.login()
        self.until(lambda: client.bodies(0x2C))
        self.completed(proc, "time limit")

    def test_admission_thresholds_recycle_before_exhaustion(self):
        for arena in (False, True):
            with self.subTest(arena=arena):
                self.status_path.unlink(missing_ok=True)
                flag = "--recycle-arena-joins" if arena else "--recycle-station-admissions"
                proc = self.launch(extra=(flag, "2", "--restart-warning", "0.2"))
                self.login(arena=arena)
                self.login(arena=arena)
                self.completed(proc, "arena admission threshold" if arena else "Station admission threshold")
                field = "arena_joins_used" if arena else "station_admissions_used"
                self.assertEqual(self.status()[field], 2)
                for client in self.clients:
                    client.pending.clear()

    def test_idle_used_session_is_recycled(self):
        proc = self.launch(extra=("--idle-recycle", "0.3", "--restart-warning", "0.2"))
        self.login(arena=False)
        self.completed(proc, "idle session cleanup")

    def test_watchdog_detects_stalled_process(self):
        proc = subprocess.Popen([sys.executable, "-I", "-S", "-c", "import time; time.sleep(60)"],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            self.status_path.write_text(json.dumps({"pid": proc.pid}))
            with self.assertRaisesRegex(RuntimeError, "has not updated"):
                dedicated.monitor(proc, self.status_path, 0.3)
        finally:
            dedicated.stop_child(proc)

    @unittest.skipUnless(os.name == "posix", "controller shutdown requires POSIX SIGINT")
    def test_controller_rotates_resumes_and_retains_map_on_crash(self):
        self.settings.update(kill_limit=0, time_limit_seconds=0.5, restart_warning_seconds=0.2)
        self.config.write_text(json.dumps(self.settings))
        proc = self.launch(controller=True)
        first_pid = self.status()["pid"]
        self.login()
        self.until(lambda: self.status().get("map") == "CTF_arena_b", timeout=12, proc=proc)
        self.assertNotEqual(self.status()["pid"], first_pid)
        self.assertEqual(self.status()["arena_joins_used"], 0)
        self.assertEqual(json.loads(self.state_path.read_text())["sessions_completed"], 1)
        dedicated.stop_child(proc)
        self.assertEqual(proc.returncode, 0)
        self.status_path.unlink(missing_ok=True)
        # A fresh controller resumes the saved map; an unexpected child death
        # fails to systemd rather than advancing the playlist or spinning.
        resumed = self.launch(controller=True)
        self.assertEqual(self.status()["map"], "CTF_arena_b")
        os.kill(self.status()["pid"], signal.SIGKILL)
        self.until(lambda: resumed.poll() is not None)
        self.assertEqual(resumed.returncode, 1)
        self.assertEqual(json.loads(self.state_path.read_text())["map"], "CTF_arena_b")
        self.assertEqual(json.loads(self.state_path.read_text())["sessions_completed"], 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
