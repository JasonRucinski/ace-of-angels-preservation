"""Supervise fresh game sessions, persistent map rotation and a status watchdog.

Planned child exit 75 advances the map. Unexpected exit or stale status stops
the controller with an error so systemd applies its bounded crash restart.
Players must quit/relaunch between sessions; this adds no client reconnect hook.

This is the original command line of deployed Linux hosts (a rotation.json
plus host.env arguments); it is kept working as it is. It builds a HostConfig
and runs the shared Supervisor with no restarts of its own. New hosts use
tools/aoa_host.py with one host.json (docs/linux-host.md).
"""
import argparse
import json
import math
import sys
import time
from pathlib import Path

from aoa.host import ops
from aoa.host.config import HostConfig
from aoa.host.supervisor import HostProcess, RestartBudget, Supervisor, Watchdog, stop_process
from aoa.maps import registry
from aoa.host.defaults import LIMITS, MANAGED, PORTS, SESSION_COMPLETE, requirement
from aoa.host.runtime import ConfigError, parse_args as server_config

__all__ = ["DEFAULTS", "SESSION_COMPLETE", "child_args", "host_config", "load_config", "load_state", "main",
           "monitor", "run", "stop_child", "supervisor"]
DEFAULTS = {
    "maps": ["CTF_arena", "CTF_arena_b", "ast_fld_a"],
    "kill_limit": LIMITS["kill_limit"],
    "time_limit_seconds": LIMITS["time_limit_seconds"],
    **MANAGED,
    "terrain": True,
}


def load_config(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("rotation config must be a JSON object")
    unknown = sorted(set(data) - set(DEFAULTS) - {"comment"})
    if unknown:
        raise ValueError(f"rotation config has unknown settings: {', '.join(unknown)} "
                         f"(documented: comment, {', '.join(DEFAULTS)})")
    if not isinstance(data.pop("comment", ""), str):
        raise ValueError("comment must be text")
    settings = {**DEFAULTS, **data}
    maps = settings["maps"]
    if (not isinstance(maps, list) or not 1 <= len(maps) <= len(registry.MAP_NAMES)
            or any(not isinstance(name, str) or name not in registry.MAP_NAMES for name in maps)
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
        raise ValueError(f"terrain must be true for a multi-map rotation ({requirement('terrain')})")
    return settings


def host_config(args, settings):
    """The HostConfig of a rotation.json `settings` and the controller's arguments."""
    return HostConfig(profile=args.profile, bind_address=args.bind_address, maps=list(settings["maps"]),
                      terrain=settings["terrain"], max_players=args.max_players,
                      kill_limit=settings["kill_limit"], time_limit_seconds=settings["time_limit_seconds"],
                      ports={"station": args.port, "arena": args.arena_port, "tcp": args.tcp},
                      sustained_delivery=True, managed={key: settings[key] for key in MANAGED},
                      paths={"key": str(args.key), "log": str(args.log), "status": str(args.status_file),
                             "state": str(args.state_file)})


def supervisor(args, settings, report=print):
    """The shared Supervisor with no restarts of its own: systemd restarts the controller."""
    return Supervisor(host_config(args, settings), HostProcess(console=False, capture=False),
                      budget=RestartBudget(restarts=0), state_path=args.state_file,
                      watchdog=settings["health_timeout_seconds"],
                      report=lambda text: report(text, flush=True))


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
    return host_config(args, settings).to_argv(name)


def stop_child(proc):
    stop_process(proc)


def monitor(proc, status_path, timeout):
    """(exit code, final status) of a child; RuntimeError if its status goes stale."""
    watchdog = Watchdog(status_path, proc.pid, timeout)
    while proc.poll() is None:
        watchdog.check()
        time.sleep(0.25)
    return proc.returncode, watchdog.final()


def run(args, settings):
    supervisor(args, settings).run()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("key", type=Path)
    parser.add_argument("log", type=Path)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--state-file", type=Path, required=True)
    parser.add_argument("--status-file", type=Path,
                        help="default work/host/<profile>-status.json, as the host window writes")
    parser.add_argument("--profile", default="vpn-dogfight", choices=("vpn-dogfight", "lan-dogfight", "local-guests"))
    parser.add_argument("--bind-address", help="this host's LAN or VPN IPv4; required except for local-guests, "
                                               "which uses 127.0.0.1")
    parser.add_argument("--max-players", type=int, default=LIMITS["max_players"])
    parser.add_argument("--port", type=int, default=PORTS["station"])
    parser.add_argument("--arena-port", type=int, default=PORTS["arena"])
    parser.add_argument("--tcp", type=int, default=PORTS["tcp"])
    parser.add_argument("--check", action="store_true", help="validate without opening sockets or writing state")
    args = parser.parse_args(argv)
    if args.bind_address is None:
        if args.profile != "local-guests":
            parser.exit(2, f"{parser.prog}: error: --bind-address is required for {args.profile} "
                           "(this host's own LAN or VPN IPv4 address)\n")
        args.bind_address = "127.0.0.1"
    if args.status_file is None:
        args.status_file = ops.status_path(args.profile)
    try:
        paths = [args.key, args.log, args.config, args.state_file, args.status_file]
        if len({path.resolve() for path in paths}) != len(paths):
            raise ValueError("key, log, config, state and status must be separate files")
        settings = load_config(args.config)
        if len(args.key.read_bytes()) != 256:
            raise ValueError("SCRTY.BIN must contain exactly 256 bytes")
        for name in settings["maps"]:
            try:
                server_config(child_args(args, settings, name), raise_errors=True)
            except ConfigError as error:
                raise ValueError(f"station_stub.py settings for map {name}: {error}") from None
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
