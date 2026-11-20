"""A real ArenaServer, in process on loopback, through join, fight, death, match end and rotation; game-free.

The server is built from a HostConfig rotation (CTF_arena then CTF_arena_b),
served in a thread with ephemeral ports, and driven by the synthetic clients
of tests/support.py: two guests log in through Station and the TCP list,
join the arena, fly, one shoots the other down; the kill limit ends the
match, the managed session announces the next map and serve() returns the
planned exit code. The next map then starts from the same config.

    python -I tools/test.py test_arena_server
"""
import contextlib
import io
import select
import socket
import struct
import tempfile
import threading
import time
import unittest
from pathlib import Path

from aoa.host import ops
from aoa.host.config import HostConfig
from aoa.host.defaults import SESSION_COMPLETE
from aoa.host.runtime import EventLog
from aoa.host.server import ArenaServer
from aoa.maps import registry
from aoa.protocol.arena import player_tag
from tests.support import SyntheticClient, job_request, read_reply, request

KEY = bytes(range(256))


class Run:
    """One ArenaServer.serve() in a thread; the server object and its exit code."""

    def __init__(self, config, name):
        self.args = config.validate()[name]
        self.stack = contextlib.ExitStack()
        self.output = io.StringIO()
        self.stack.enter_context(contextlib.redirect_stdout(self.output))
        log = self.stack.enter_context(EventLog(self.args.log))
        resources = self.stack.enter_context(contextlib.ExitStack())
        self.server = ArenaServer(self.args, KEY, log, resources)
        self.code = None
        self.thread = threading.Thread(target=self._serve, daemon=True)
        self.thread.start()

    def _serve(self):
        self.code = self.server.serve()

    def address(self, which):
        port = {"station": self.server.s.getsockname()[1], "arena": self.server.arena.getsockname()[1],
                "tcp": self.server.tcp_port}[which]
        return "127.0.0.1", port

    def close(self):
        self.server.quit_requested = True
        self.thread.join(10)
        self.stack.close()


class ArenaServerTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        (self.root / "key").write_bytes(KEY)
        self.config = HostConfig(
            root=self.root, profile="local-guests", maps=["CTF_arena", "CTF_arena_b"], terrain=True,
            sustained_delivery=True, kill_limit=1, time_limit_seconds=0, max_players=4,
            ports={"station": 0, "arena": 0, "tcp": 0},
            managed={"restart_warning_seconds": 0.5, "idle_recycle_seconds": 0},
            paths={"key": str(self.root / "key"), "log": str(self.root / "host.jsonl"),
                   "status": str(self.root / "status.json")})
        self.clients = []
        self.addCleanup(lambda: [c.sock.close() for c in self.clients])

    def pump(self, until, timeout=10):
        deadline = time.monotonic() + timeout
        while not until():
            self.assertLess(time.monotonic(), deadline, "server response missing")
            ready, _, _ = select.select([c.sock for c in self.clients], [], [], 0.02)
            for client in self.clients:
                if client.sock in ready:
                    client.handle(*client.sock.recvfrom(1024))
                client.resend()

    def login(self, run):
        station, arena = run.address("station"), run.address("arena")
        client = SyntheticClient(KEY)
        self.clients.append(client)
        client.send(station, 10, request())
        self.pump(lambda: station[1] in client.acks)
        ack = client.acks[station[1]]
        self.assertEqual(struct.unpack_from("<I", ack, 6)[0], 0)
        with socket.create_connection(run.address("tcp"), timeout=3) as connection:
            connection.sendall(job_request(identity=struct.unpack_from("<I", ack, 136)[0]))
            listing = read_reply(connection)
        client.send(arena, 10, request()[:31] + ack[13:])
        self.pump(lambda: arena[1] in client.acks)
        arena_ack = client.acks[arena[1]]
        self.assertEqual(struct.unpack_from("<I", arena_ack, 6)[0], 0)
        client.slot = struct.unpack_from("<I", arena_ack, 2)[0] & 0xFF
        return client, listing

    def test_join_fight_death_match_end_and_rotation(self):
        run = Run(self.config, "CTF_arena")
        self.addCleanup(run.close)
        (a, listing), (b, _) = self.login(run), self.login(run)
        self.assertIn(b"CTF_arena", listing)
        # Join: both reach flight with the map's terrain marker and see each other.
        self.pump(lambda: all(c.bodies(0x2C) for c in (a, b)))
        self.assertEqual(a.bodies(0x2C)[0], registry.marker("CTF_arena"))
        self.pump(lambda: len(a.bodies(0x26)) >= 2 and len(b.bodies(0x26)) >= 2)
        # Fight: B reports that A's fire killed it; A gets the kill notice, B its spawn back.
        b.send_reliable(run.address("arena"), 0x37, struct.pack("<I", player_tag(a.slot)))
        self.pump(lambda: a.bodies(0x38))
        self.assertEqual(struct.unpack("<II", a.bodies(0x38)[0]), (player_tag(b.slot), player_tag(a.slot)))
        self.pump(lambda: b.bodies(0x24))
        # Match end: one kill is the limit; the managed session names the next map and ends.
        self.pump(lambda: any(b"Next map CTF_arena_b" in body for body in a.bodies(0x21)))
        self.pump(lambda: any(b"wins with 1 kills" in body for body in b.bodies(0x21)))
        self.pump(lambda: run.code is not None)
        self.assertEqual(run.code, SESSION_COMPLETE)
        status, _ = ops.read_status(self.config.status_path())
        self.assertEqual(status["lifecycle"]["restart_reason"], "kill limit")
        self.assertEqual(status["lifecycle"]["next_map"], "CTF_arena_b")
        self.assertEqual({p["slot"]: (p["kills"], p["deaths"]) for p in status["players"]},
                         {a.slot: (1, 0), b.slot: (0, 1)})
        run.close()
        # Rotation: the next map starts from the same config, and a new client flies there.
        nxt = Run(self.config, self.config.next_map("CTF_arena"))
        self.addCleanup(nxt.close)
        self.assertEqual(nxt.args.next_map, "CTF_arena")
        c, listing = self.login(nxt)
        self.assertIn(b"CTF_arena_b", listing)
        self.pump(lambda: c.bodies(0x2C))
        self.assertEqual(c.bodies(0x2C)[0], registry.marker("CTF_arena_b"))


if __name__ == "__main__":
    unittest.main()
