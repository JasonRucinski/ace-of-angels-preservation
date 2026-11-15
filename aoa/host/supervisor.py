"""Run the server as a child process and keep it running.

HostProcess   one child: start from a HostConfig, console commands, a graceful
              stop (console `quit`, else SIGINT; then terminate, then kill) and
              a pid-checked status read.
RestartBudget the one crash policy: at most 3 restarts in 10 minutes, 5 s
              apart, and only for a run that lasted 5 s (a host that cannot
              start is not restarted in a loop).
Supervisor    restart policy, map rotation with a saved state file, recycling
              (the server's managed sessions end with exit 75), the status
              watchdog and the planned exit. A crashed run restarts with the
              settings and map it had, not with later edits.

The host window polls a Supervisor from its timer; the headless host
(tools/aoa_host.py) calls run(). Tests drive it with a fake process.
"""
import copy
import json
import os
import queue
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

from aoa import paths
from aoa.host import ops
from aoa.host.defaults import SESSION_COMPLETE

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
RESTARTS, RESTART_WINDOW, RESTART_DELAY, MIN_UPTIME = 3, 600.0, 5.0, 5.0


class SupervisorError(RuntimeError):
    """The supervisor gave up: an unplanned exit or a stalled host beyond the restart budget."""


def stop_process(proc, timeout=10.0, console=False):
    """Stop a server child; players get the server's quit notice when it can still answer.

    `console`: the child reads commands on stdin, so `quit` asks it to stop.
    Otherwise SIGINT (POSIX; like Ctrl+C, the server drains its logs) or
    terminate (Windows). Returns the exit code.
    """
    if proc is None:
        return None
    if proc.poll() is not None:
        return proc.returncode
    try:
        if console and proc.stdin is not None:
            proc.stdin.write("quit\n")
            proc.stdin.flush()
        elif os.name == "posix":
            proc.send_signal(signal.SIGINT)
        else:
            proc.terminate()
    except (OSError, ValueError):
        pass  # Already gone, or its stdin is closed.
    try:
        proc.wait(timeout)
    except subprocess.TimeoutExpired:
        proc.terminate()
        try:
            proc.wait(5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(3)
    return proc.returncode


class Watchdog:
    """Only a status file this child rewrote counts as alive; clocks may change."""

    def __init__(self, path, pid, timeout, clock=time.monotonic):
        self.path, self.pid, self.timeout, self.clock = Path(path), pid, timeout, clock
        self.last_update, self.last_mtime, self.latest = clock(), None, None

    def check(self):
        try:
            mtime = self.path.stat().st_mtime_ns
        except OSError:
            mtime = None
        status, _ = ops.read_status(self.path, self.pid)
        if status is not None and mtime != self.last_mtime:
            self.last_update, self.last_mtime, self.latest = self.clock(), mtime, status
        if self.timeout is not None and self.clock() - self.last_update >= self.timeout:
            raise SupervisorError(f"game process {self.pid} has not updated its status for {self.timeout:g}s")

    def final(self):
        """The status written just before a planned exit, else the last fresh one."""
        status, _ = ops.read_status(self.path, self.pid)
        return status or self.latest


class RestartBudget:
    def __init__(self, restarts=RESTARTS, window=RESTART_WINDOW, delay=RESTART_DELAY, min_uptime=MIN_UPTIME):
        self.restarts, self.window, self.delay, self.min_uptime = restarts, window, delay, min_uptime
        self.times = []

    def allow(self, uptime, now):
        """Record and allow one restart of a run that lasted `uptime` seconds, if the budget has room."""
        self.times = [t for t in self.times if now - t < self.window]
        if uptime < self.min_uptime or len(self.times) >= self.restarts:
            return False
        self.times.append(now)
        return True


class HostProcess:
    """The server child process: start from a HostConfig, commands, clean stop, status."""

    def __init__(self, script=None, python=None, cwd=None, console=True, capture=True, popen=subprocess.Popen,
                 inherit_stdin=False):
        """console: send commands on a stdin pipe; inherit_stdin: the server reads this terminal itself."""
        self.script = Path(script) if script is not None else paths.entry("station_stub")
        self.python = python or sys.executable
        self.cwd, self.console, self.capture, self.popen = cwd or paths.ROOT, console and not inherit_stdin, capture, popen
        self.inherit_stdin = inherit_stdin
        self.proc, self.config, self.map, self.started = None, None, None, None
        self.output = queue.Queue()
        self.stopping = False

    def argv(self, config, map_name=None):
        return [self.python, "-u", "-I", str(self.script), *config.to_argv(map_name)]

    @property
    def running(self):
        return self.proc is not None and self.proc.poll() is None

    @property
    def pid(self):
        return None if self.proc is None else self.proc.pid

    def start(self, config, map_name=None):
        if self.running:
            raise RuntimeError("host already running")
        status = config.status_path()
        status.parent.mkdir(parents=True, exist_ok=True)
        status.unlink(missing_ok=True)
        self.proc = self.popen(self.argv(config, map_name), cwd=self.cwd,
                               stdin=None if self.inherit_stdin else subprocess.PIPE if self.console else subprocess.DEVNULL,
                               stdout=subprocess.PIPE if self.capture else None,
                               stderr=subprocess.STDOUT if self.capture else None,
                               text=True, bufsize=1, creationflags=NO_WINDOW)
        self.config, self.map = copy.deepcopy(config), map_name or config.maps[0]
        self.started, self.stopping = time.time(), False
        if self.capture:
            threading.Thread(target=self._read, args=(self.proc,), daemon=True).start()
        return self.proc

    def _read(self, proc):
        for line in proc.stdout:
            self.output.put(line.rstrip("\n"))
        self.output.put(f"[host exited with code {proc.wait()}]")

    def command(self, line):
        if not self.running or not self.console:
            return False
        try:
            self.proc.stdin.write(line.strip() + "\n")
            self.proc.stdin.flush()
            return True
        except OSError:
            return False

    def stop(self, timeout=10.0):
        """Ask the server to quit (players get a notice); force it after `timeout`."""
        if self.proc is None:
            return None
        self.stopping = True
        return stop_process(self.proc, timeout, console=self.console)

    def status(self):
        """(status dict or None, age in seconds or None) from this run's status file."""
        if self.proc is None:
            return None, None
        return ops.read_status(self.config.status_path(), self.proc.pid)


class Supervisor:
    """Keeps one host running: rotation, planned exits, the watchdog and the restart budget.

    `poll()` does one step and never blocks; `run()` loops until stopped or
    until it gives up (SupervisorError). Events go to `report(text)`.
    """

    def __init__(self, config, process=None, budget=None, state_path=None, watchdog=None,
                 report=print, clock=time.monotonic):
        self.config = copy.deepcopy(config)
        self.process = process or HostProcess()
        self.budget = budget or RestartBudget()
        self.state_path = Path(state_path) if state_path is not None else None
        self.watchdog_timeout = watchdog
        self.report, self.clock = report, clock
        self.state = {"schema": 1, "map": self.config.maps[0], "sessions_completed": 0}
        self.watchdog, self.started_at, self.next_start = None, None, None
        self.pending = None  # the config the next scheduled start uses
        self.stopped = False

    # --- rotation state --------------------------------------------------
    def load_state(self):
        """Resume the saved rotation; a map no longer in it restarts the rotation."""
        if self.state_path is None:
            return self.state
        try:
            state = json.loads(self.state_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            state = dict(self.state)
        except ValueError:
            state = None
        if (not isinstance(state, dict) or state.get("schema") != 1 or not isinstance(state.get("map"), str)
                or type(state.get("sessions_completed")) is not int or state["sessions_completed"] < 0):
            raise SupervisorError("invalid rotation state; restore its backup or move it aside "
                                  "to start from the first map")
        if state["map"] not in self.config.maps:
            state["map"] = self.config.maps[0]
        self.state = state
        return state

    def save_state(self):
        if self.state_path is not None:
            ops.write_status(self.state_path, self.state)

    # --- running ---------------------------------------------------------
    def start(self, config=None):
        """Start the current map now, with `config` (default: the current settings)."""
        config = config or self.config
        self.next_start, self.pending, self.stopped = None, None, False
        name = self.state["map"]
        self.report(f"Starting map {name}; completed sessions={self.state['sessions_completed']}")
        proc = self.process.start(config, name)
        self.started_at = self.clock()
        self.watchdog = Watchdog(config.status_path(), proc.pid, self.watchdog_timeout, self.clock)
        return proc

    def stop(self, timeout=10.0):
        self.stopped = True
        self.next_start = None
        return self.process.stop(timeout)

    def change(self, config):
        """New settings for the next start (Load map); the running host is not touched."""
        self.config = copy.deepcopy(config)
        if self.state["map"] not in self.config.maps:
            self.state["map"] = self.config.maps[0]

    def poll(self):
        """One step: 'running', 'waiting' (a restart or the next map is due later), 'stopped' or an event."""
        now = self.clock()
        if self.stopped:
            return "stopped"
        if self.next_start is not None:
            if now < self.next_start:
                return "waiting"
            self.start(self.pending)
            return "started"
        proc = self.process.proc
        if proc is None:
            return "stopped"
        code = proc.poll()
        if code is None:
            try:
                self.watchdog.check()
            except SupervisorError as error:
                stop_process(proc, console=self.process.console)
                return self._unplanned(str(error), now)
            return "running"
        if self.process.stopping or code == 0:
            # Stopped from here, or by the server's own console `quit` or --seconds.
            self.stopped = True
            if code == 0 and not self.process.stopping:
                self.report("Host stopped (exit code 0)")
            return "stopped"
        status = self.watchdog.final()
        lifecycle = (status or {}).get("lifecycle") or {}
        if code == SESSION_COMPLETE and lifecycle.get("restart_reason"):
            return self._planned(lifecycle["restart_reason"], now)
        return self._unplanned(f"game process exited unexpectedly ({code})", now)

    def _planned(self, reason, now):
        name = self.state["map"]
        self.state = {"schema": 1, "map": self.config.next_map(name),
                      "sessions_completed": self.state["sessions_completed"] + 1,
                      "last_map": name, "last_reason": reason}
        self.save_state()
        self.report(f"Session complete ({reason}); next map {self.state['map']}")
        self.next_start = now + self.config.managed_settings()["intermission_seconds"]
        self.pending = self.config
        return "planned"

    def _unplanned(self, why, now):
        uptime = now - (self.started_at if self.started_at is not None else now)
        if not self.budget.allow(uptime, now):
            self.stopped = True
            raise SupervisorError(f"{why}; retaining map {self.state['map']}")
        self.report(f"[{why}; restarting in {self.budget.delay:g} s, players must rejoin]")
        # The crashed run's own settings and map, not later edits.
        self.pending, self.state["map"] = self.process.config, self.process.map
        self.next_start = now + self.budget.delay
        return "restarting"

    def run(self, interval=0.25, sleep=time.sleep):
        """Start and supervise until stop() or a SupervisorError; the child is stopped on the way out."""
        self.load_state()
        self.save_state()
        try:
            self.start()
            while self.poll() != "stopped":
                sleep(interval)
        finally:
            stop_process(self.process.proc, console=self.process.console)
