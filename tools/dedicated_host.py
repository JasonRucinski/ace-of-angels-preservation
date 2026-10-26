"""Supervise fresh game sessions, persistent map rotation and a status watchdog.

Planned child exit 75 advances the map. Unexpected exit or stale status stops
the controller with an error so systemd applies its bounded crash restart.
Players must quit/relaunch between sessions; this adds no client reconnect hook.
"""
import argparse
import json
import math
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import host_ops
import online_terrain
from station_runtime import parse_args as server_config

SESSION_COMPLETE = 75
DEFAULTS = {
    "maps": ["CTF_arena", "CTF_arena_b", "ast_fld_a"],
    "kill_limit": 10,
    "time_limit_seconds": 900,
    "restart_warning_seconds": 30,
    "intermission_seconds": 5,
    "idle_recycle_seconds": 300,
    "recycle_arena_joins": 40,
    "recycle_station_admissions": 56,
    "health_timeout_seconds": 30,
    "terrain": True,
}


def load_config(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict) or set(data) - set(DEFAULTS):
        raise ValueError("rotation config must be an object containing only documented settings")
    settings = {**DEFAULTS, **data}
    maps = settings["maps"]
    if (not isinstance(maps, list) or not 1 <= len(maps) <= len(online_terrain.MAP_NAMES)
            or any(not isinstance(name, str) or name not in online_terrain.MAP_NAMES for name in maps)
            or len(set(maps)) != len(maps)):
        raise ValueError("maps must be a nonempty list of unique supported map names")
    bounds = {"kill_limit": (0, 1000, True), "time_limit_seconds": (0, 86400, False),
              "restart_warning_seconds": (0, 300, False), "intermission_seconds": (0, 300, False),
              "idle_recycle_seconds": (0, 86400, False), "recycle_arena_joins": (1, 48, True),
              "recycle_station_admissions": (1, 63, True), "health_timeout_seconds": (5, 300, False)}
    for name, (low, high, integer) in bounds.items():
        value = settings[name]
        if (type(value) not in (int, float) or (integer and type(value) is not int)
                or not math.isfinite(value) or not low <= value <= high):
            raise ValueError(f"{name} must be {'an integer' if integer else 'a number'} in {low}..{high}")
    if not (settings["kill_limit"] or settings["time_limit_seconds"]):
        raise ValueError("enable at least one of kill_limit or time_limit_seconds")
    if type(settings["terrain"]) is not bool or (len(maps) > 1 and not settings["terrain"]):
        raise ValueError("terrain must be true for a multi-map rotation (clients need online-terrain-v2 or later)")
    return settings


def load_state(path, maps):
    try:
        state = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"schema": 1, "map": maps[0], "sessions_completed": 0}
    if (not isinstance(state, dict) or state.get("schema") != 1
            or not isinstance(state.get("map"), str)
            or type(state.get("sessions_completed")) is not int or state["sessions_completed"] < 0):
        raise ValueError("invalid rotation state; restore its backup or move it aside to start from the first map")
    if state["map"] not in maps:
        state["map"] = maps[0]
    return state


def child_args(args, settings, name):
    next_map = settings["maps"][(settings["maps"].index(name) + 1) % len(settings["maps"])]
    result = [str(args.key), str(args.log), "--profile", args.profile,
              "--bind-address", args.bind_address, "--max-players", str(args.max_players),
              "--port", str(args.port), "--arena-port", str(args.arena_port), "--tcp", str(args.tcp),
              "--map", name, "--status-file", str(args.status_file), "--sustained-delivery",
              "--managed-session", "--next-map", next_map,
              "--kill-limit", str(settings["kill_limit"]),
              "--time-limit", str(settings["time_limit_seconds"]),
              "--restart-warning", str(settings["restart_warning_seconds"]),
              "--idle-recycle", str(settings["idle_recycle_seconds"]),
              "--recycle-arena-joins", str(settings["recycle_arena_joins"]),
              "--recycle-station-admissions", str(settings["recycle_station_admissions"])]
    if settings["terrain"]:
        result.append("--experimental-terrain")
    return result


def stop_child(proc):
    if proc is None or proc.poll() is not None:
        return
    try:
        if os.name == "posix":
            proc.send_signal(signal.SIGINT)
        else:
            proc.terminate()
        proc.wait(timeout=10)
    except ProcessLookupError:
        pass
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=3)


def monitor(proc, status_path, timeout):
    """Only a fresh status from this child feeds the watchdog; clocks may change."""
    last_update, last_mtime = time.monotonic(), None
    latest = None
    while proc.poll() is None:
        try:
            mtime = status_path.stat().st_mtime_ns
            status = json.loads(status_path.read_text(encoding="utf-8"))
            if isinstance(status, dict) and status.get("pid") == proc.pid and mtime != last_mtime:
                last_update, last_mtime, latest = time.monotonic(), mtime, status
        except (OSError, ValueError):
            pass
        if time.monotonic() - last_update >= timeout:
            raise RuntimeError(f"game process {proc.pid} has not updated its status for {timeout:g}s")
        time.sleep(0.25)
    # The final state is written immediately before a planned exit.
    try:
        status = json.loads(status_path.read_text(encoding="utf-8"))
        if isinstance(status, dict) and status.get("pid") == proc.pid:
            latest = status
    except (OSError, ValueError):
        pass
    return proc.returncode, latest


def run(args, settings):
    state = load_state(args.state_file, settings["maps"])
    host_ops.write_status(args.state_file, state)
    while True:
        name = state["map"]
        args.status_file.unlink(missing_ok=True)
        command = [sys.executable, "-I", "-u", str(Path(__file__).with_name("station_stub.py")),
                   *child_args(args, settings, name)]
        print(f"Starting map {name}; completed sessions={state['sessions_completed']}", flush=True)
        proc = None
        try:
            proc = subprocess.Popen(command, stdin=subprocess.DEVNULL,
                                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            code, status = monitor(proc, args.status_file, settings["health_timeout_seconds"])
        finally:
            stop_child(proc)
        if code != SESSION_COMPLETE or not status or not status.get("lifecycle", {}).get("restart_reason"):
            raise RuntimeError(f"game process exited unexpectedly ({code}); retaining map {name}")
        state = {"schema": 1,
                 "map": settings["maps"][(settings["maps"].index(name) + 1) % len(settings["maps"])],
                 "sessions_completed": state["sessions_completed"] + 1,
                 "last_map": name, "last_reason": status["lifecycle"]["restart_reason"]}
        host_ops.write_status(args.state_file, state)
        print(f"Session complete ({state['last_reason']}); next map {state['map']}", flush=True)
        time.sleep(settings["intermission_seconds"])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("key", type=Path)
    parser.add_argument("log", type=Path)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--state-file", type=Path, required=True)
    parser.add_argument("--status-file", type=Path, required=True)
    parser.add_argument("--profile", default="vpn-dogfight", choices=("vpn-dogfight", "lan-dogfight", "local-guests"))
    parser.add_argument("--bind-address", default="127.0.0.1")
    parser.add_argument("--max-players", type=int, default=2)
    parser.add_argument("--port", type=int, default=5033)
    parser.add_argument("--arena-port", type=int, default=5031)
    parser.add_argument("--tcp", type=int, default=5034)
    parser.add_argument("--check", action="store_true", help="validate without opening sockets or writing state")
    args = parser.parse_args(argv)
    try:
        paths = [args.key, args.log, args.config, args.state_file, args.status_file]
        if len({path.resolve() for path in paths}) != len(paths):
            raise ValueError("key, log, config, state and status must be separate files")
        settings = load_config(args.config)
        if len(args.key.read_bytes()) != 256:
            raise ValueError("SCRTY.BIN must contain exactly 256 bytes")
        for name in settings["maps"]:
            server_config(child_args(args, settings, name))
        load_state(args.state_file, settings["maps"])
        if args.check:
            print(json.dumps(settings, indent=2))
            return 0
        run(args, settings)
    except KeyboardInterrupt:
        print("Dedicated host stopped", flush=True)
        return 0
    except (OSError, ValueError, RuntimeError) as error:
        print(f"Dedicated host failed: {error}", file=sys.stderr, flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
