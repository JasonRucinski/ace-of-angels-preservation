"""Supervisor, RestartBudget and HostProcess with a fake child process; game-free.

    python -I tools/test.py test_supervisor
"""
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from aoa.host import ops
from aoa.host.config import HostConfig
from aoa.host.defaults import SESSION_COMPLETE
from aoa.host.supervisor import HostProcess, RestartBudget, Supervisor, SupervisorError


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


class FakeProc:
    pids = iter(range(4000, 5000))

    def __init__(self):
        self.pid, self.returncode, self.signals = next(self.pids), None, []
        self.stdin = None

    def poll(self):
        return self.returncode

    def wait(self, timeout=None):
        if self.returncode is None:
            self.returncode = -2
        return self.returncode

    def send_signal(self, sig):
        self.signals.append(sig)
        self.returncode = 0

    def terminate(self):
        self.returncode = -15

    def kill(self):
        self.returncode = -9


class FakeHost(HostProcess):
    """HostProcess whose child is a FakeProc; records (map, config) per start."""

    def __init__(self):
        super().__init__(console=False, capture=False, popen=lambda *a, **k: FakeProc())
        self.starts = []

    def start(self, config, map_name=None):
        proc = super().start(config, map_name)
        self.starts.append((self.map, config))
        return proc

    def write_status(self, **fields):
        ops.write_status(self.config.status_path(), {"pid": self.proc.pid, **fields})


class SupervisorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.clock = Clock()
        self.events = []
        self.host = FakeHost()

    def supervisor(self, config=None, **options):
        config = config or HostConfig(root=self.root)
        return Supervisor(config, self.host, report=self.events.append, clock=self.clock, **options)

    def crash(self, after=10):
        self.clock.now += after
        self.host.proc.returncode = 1

    def test_budget_three_per_ten_minutes_after_five_seconds(self):
        budget = RestartBudget()
        self.assertFalse(budget.allow(uptime=4.9, now=0))
        self.assertEqual([budget.allow(10, t) for t in (0, 60, 120, 180)], [True, True, True, False])
        self.assertTrue(budget.allow(10, 600.5))

    def test_crash_restarts_with_the_crashed_runs_settings(self):
        sup = self.supervisor(HostConfig(root=self.root, maps=["JRMAP"], kill_limit=5))
        sup.start()
        sup.change(HostConfig(root=self.root, maps=["Arena1a"], kill_limit=9))  # an edit after the start
        self.crash()
        self.assertEqual(sup.poll(), "restarting")
        self.assertEqual(sup.poll(), "waiting")
        self.clock.now += 5
        self.assertEqual(sup.poll(), "started")
        self.assertEqual([(m, c.kill_limit) for m, c in self.host.starts], [("JRMAP", 5), ("JRMAP", 5)])
        self.assertIn("restarting in 5 s", self.events[-2])

    def test_gives_up_after_the_budget(self):
        sup = self.supervisor()
        sup.start()
        for _ in range(3):
            self.crash()
            self.assertEqual(sup.poll(), "restarting")
            self.clock.now += 5
            self.assertEqual(sup.poll(), "started")
        self.crash()
        with self.assertRaisesRegex(SupervisorError, r"exited unexpectedly \(1\); retaining map CTF_arena"):
            sup.poll()
        self.assertEqual(len(self.host.starts), 4)

    def test_a_host_that_cannot_start_is_not_restarted(self):
        sup = self.supervisor()
        sup.start()
        self.crash(after=1)
        with self.assertRaises(SupervisorError):
            sup.poll()

    def test_rotation_advances_on_planned_exit_and_saves_state(self):
        config = HostConfig(root=self.root, maps=["CTF_arena", "CTF_arena_b"], terrain=True,
                            sustained_delivery=True, managed={"intermission_seconds": 2})
        state = self.root / "state.json"
        sup = self.supervisor(config, state_path=state)
        sup.load_state()
        sup.start()
        self.host.write_status(lifecycle={"restart_reason": "kill limit"})
        self.host.proc.returncode = SESSION_COMPLETE
        self.assertEqual(sup.poll(), "planned")
        saved = json.loads(state.read_text())
        self.assertEqual((saved["map"], saved["sessions_completed"], saved["last_reason"]),
                         ("CTF_arena_b", 1, "kill limit"))
        self.assertEqual(sup.poll(), "waiting")
        self.clock.now += 2
        self.assertEqual(sup.poll(), "started")
        self.assertEqual([m for m, _ in self.host.starts], ["CTF_arena", "CTF_arena_b"])
        # A new supervisor resumes the saved map.
        self.assertEqual(self.supervisor(config, state_path=state).load_state()["map"], "CTF_arena_b")

    def test_exit_75_without_a_reason_is_a_crash(self):
        sup = self.supervisor(budget=RestartBudget(restarts=0))
        sup.start()
        self.host.proc.returncode = SESSION_COMPLETE
        with self.assertRaises(SupervisorError):
            sup.poll()

    def test_watchdog_restarts_a_stalled_host(self):
        sup = self.supervisor(watchdog=30)
        sup.start()
        self.host.write_status()
        self.assertEqual(sup.poll(), "running")
        self.clock.now += 29
        self.assertEqual(sup.poll(), "running")
        self.clock.now += 1
        self.assertEqual(sup.poll(), "restarting")
        self.assertIsNotNone(self.host.proc.returncode)  # the stalled child was stopped
        self.assertIn("has not updated its status for 30s", self.events[-1])

    def test_stop_is_not_a_crash(self):
        sup = self.supervisor()
        sup.start()
        sup.stop()
        self.assertEqual(sup.poll(), "stopped")
        self.assertEqual(len(self.host.starts), 1)

    def test_clean_exit_ends_supervision(self):
        sup = self.supervisor()
        sup.start()
        self.clock.now += 60
        self.host.proc.returncode = 0  # console quit
        self.assertEqual(sup.poll(), "stopped")
        self.assertEqual(sup.poll(), "stopped")
        self.assertEqual(len(self.host.starts), 1)

    def test_invalid_state_file(self):
        state = self.root / "state.json"
        state.write_text("{}")
        with self.assertRaisesRegex(SupervisorError, "invalid rotation state"):
            self.supervisor(state_path=state).load_state()


class HostProcessTests(unittest.TestCase):
    def test_command_line_comes_from_the_config(self):
        calls = []

        def popen(argv, **options):
            calls.append((argv, options))
            proc = FakeProc()
            proc.stdin = None
            return proc

        with tempfile.TemporaryDirectory() as temp:
            config = HostConfig(root=Path(temp), maps=["JRMAP"])
            host = HostProcess(script="tools/station_stub.py", python="python", capture=False, popen=popen)
            host.start(config)
            argv, options = calls[0]
            self.assertEqual(argv[:4], ["python", "-u", "-I", "tools/station_stub.py"])
            self.assertEqual(argv[4:], config.to_argv())
            self.assertEqual(options["stdin"], subprocess.PIPE)
            self.assertEqual(host.map, "JRMAP")
            self.assertEqual(host.status(), (None, None))
            with self.assertRaises(RuntimeError):
                host.start(config)


if __name__ == "__main__":
    unittest.main()
