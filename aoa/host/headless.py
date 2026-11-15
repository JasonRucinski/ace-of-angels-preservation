"""Run, check or inspect a host from one settings file: the headless host.

  python -I tools/aoa_host.py check  [CONFIG.json] [overrides]
  python -I tools/aoa_host.py run    [CONFIG.json] [overrides] [-- server diagnostics]
  python -I tools/aoa_host.py status [CONFIG.json] [overrides]

CONFIG is a HostConfig JSON file (aoa/host/config.py): the Linux
deploy/linux/host.json.example, or work/host/host.json, which the host window
writes for each run. The older Linux pair is still read: a rotation.json
without "schema" (deploy/linux/rotation.json.example) takes AOA_BIND_ADDRESS
and AOA_MAX_PLAYERS from the environment or a host.env beside it, and the
paths of the original aoa-host.service. Without CONFIG the defaults apply:
this PC only (local-guests on 127.0.0.1).

Overrides: --profile, --bind-address, --map (one map instead of the
rotation), --max-players, --backdrop, --terrain and --console (the server
reads host commands from this terminal). Words after `--` go to the server
unchanged, for diagnostics such as test impairment.

check validates every map in process and prints the server's settings.
run validates, then supervises: a crashed host restarts with the settings it
had, at most 3 times in 10 minutes and 5 s apart; a rotation advances on each
planned exit; managed sessions have the status watchdog. Ctrl+C or SIGINT
stops it. status prints the status file the server rewrites every 2 s.
"""
import argparse
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

from aoa.host import dedicated, ops
from aoa.host.config import ConfigError, HostConfig
from aoa.host.defaults import ALIASES, BACKDROPS, LIMITS, PORTS, PROFILES
from aoa.host.supervisor import HostProcess, RestartBudget, Supervisor, SupervisorError
from aoa.maps import registry

# Where the original systemd unit kept its files (deploy/linux/aoa-host.service before host.json).
LEGACY_PATHS = {"key": "/etc/ace-of-angels/SCRTY.BIN", "log": "/var/lib/ace-of-angels/host.jsonl",
                "status": "/var/lib/ace-of-angels/status.json",
                "state": "/var/lib/ace-of-angels/rotation-state.json"}


def read_env(path):
    """KEY=VALUE lines of a systemd EnvironmentFile; comments and blank lines skipped."""
    values = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip().strip('"')
    return values


def legacy_config(path, environ=None):
    """HostConfig of a rotation.json and its host.env values (the original Linux deployment)."""
    try:
        settings = dedicated.load_config(path)
    except ValueError as error:
        raise ConfigError(f"{path}: {error}") from None
    env = {}
    beside = Path(path).with_name("host.env")
    if beside.is_file():
        env.update(read_env(beside))
    env.update(os.environ if environ is None else environ)
    if "AOA_BIND_ADDRESS" not in env:
        raise ConfigError(f"{path} is a rotation file: set AOA_BIND_ADDRESS (host.env) or use a host.json")
    try:
        max_players = int(env.get("AOA_MAX_PLAYERS", LIMITS["max_players"]))
    except ValueError:
        raise ConfigError("AOA_MAX_PLAYERS must be a whole number") from None
    args = SimpleNamespace(profile="vpn-dogfight", bind_address=env["AOA_BIND_ADDRESS"], max_players=max_players,
                           port=PORTS["station"], arena_port=PORTS["arena"], tcp=PORTS["tcp"],
                           **{name: Path(value) for name, value in LEGACY_PATHS.items()
                              if name in ("key", "log")},
                           status_file=Path(LEGACY_PATHS["status"]), state_file=Path(LEGACY_PATHS["state"]))
    return dedicated.host_config(args, settings)


def load(path=None, environ=None):
    """The HostConfig in `path` (host.json or a legacy rotation.json), or the defaults."""
    if path is None:
        return HostConfig()
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except OSError as error:
        raise ConfigError(f"host config: {error}") from None
    except ValueError as error:
        raise ConfigError(f"{path} is not JSON: {error}") from None
    if isinstance(data, dict) and "schema" not in data and "maps" in data:
        return legacy_config(path, environ)
    return HostConfig.from_json(data)


def apply_overrides(config, args):
    if args.profile is not None:
        config.profile = args.profile
    if args.bind_address is not None:
        config.bind_address = args.bind_address
    if args.map is not None:
        config.maps = [args.map]
    if args.max_players is not None:
        config.max_players = args.max_players
    if args.backdrop is not None:
        config.backdrop = args.backdrop
    if args.terrain:
        config.terrain = True
    if args.console:
        config.console = True
    config.extra_args = [*config.extra_args, *args.server_args]
    return config


def describe(config):
    """What the operator needs to tell players, from the settings the server will use."""
    m = config.managed_settings()
    limits = (f"{config.kill_limit or 'no'} kills / "
              f"{f'{config.time_limit_seconds:g} s' if config.time_limit_seconds else 'no time limit'}")
    lines = [f"{config.profile} on {config.bind_address}: up to {config.max_players} players; {limits}",
             f"Maps: {', '.join(config.maps)}{' (rotation)' if config.managed is not None else ''}"
             f"{'; terrain on' if config.terrain else ''}; backdrop {config.backdrop}",
             f"UDP {config.ports['station']} + {config.ports['arena']}; TCP {config.ports['tcp']}. "
             f"Status: {config.status_path()}"]
    if config.profile in ALIASES:
        lines.append(f"Each client hosts-file entry: {config.bind_address} {ALIASES[config.profile]}; "
                     f"prepare each client for Station {ALIASES[config.profile]}")
    if config.managed is not None:
        lines.append(f"Managed sessions: restart warning {m['restart_warning_seconds']:g} s, "
                     f"intermission {m['intermission_seconds']:g} s; players quit and rejoin between maps")
    if any(str(a).startswith("--impair-") for a in config.extra_args):
        lines.append("TEST IMPAIRMENT ON: do not use this host for normal play.")
    if config.console:
        lines.append("Type 'help' for host commands. Ctrl+C stops the host.")
    return "\n".join(lines)


def run(config):
    managed = config.managed is not None
    host = HostProcess(console=False, capture=False, inherit_stdin=config.console)
    supervisor = Supervisor(config, host, budget=RestartBudget(),
                            state_path=config.path("state") if managed else None,
                            watchdog=config.managed_settings()["health_timeout_seconds"] if managed else None,
                            report=lambda text: print(text, flush=True))
    supervisor.run()


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    server_args = []
    if "--" in argv:
        at = argv.index("--")
        argv, server_args = argv[:at], argv[at + 1:]
    parser = argparse.ArgumentParser(prog="aoa_host.py", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("action", choices=("run", "check", "status"))
    parser.add_argument("config", nargs="?", type=Path, help="host.json (or a legacy rotation.json)")
    parser.add_argument("--profile", choices=PROFILES)
    parser.add_argument("--bind-address")
    parser.add_argument("--map", choices=registry.MAP_NAMES)
    parser.add_argument("--max-players", type=int)
    parser.add_argument("--backdrop", choices=BACKDROPS)
    parser.add_argument("--terrain", action="store_true")
    parser.add_argument("--console", action="store_true")
    args = parser.parse_args(argv)
    args.server_args = server_args
    try:
        config = apply_overrides(load(args.config), args)
        if args.action == "status":
            status, age = ops.read_status(config.status_path())
            if status is None:
                print(f"no status at {config.status_path()}", file=sys.stderr)
                return 1
            print(json.dumps({"age_s": None if age is None else round(age, 1), **status}, indent=2))
            return 0
        parsed = config.validate()
        if args.action == "check":
            print(json.dumps({name: vars(a) for name, a in parsed.items()}, default=str, indent=2))
            return 0
        print(describe(config), flush=True)
        run(config)
    except ConfigError as error:
        print(f"{parser.prog}: error: {error}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("Host stopped", flush=True)
    except (OSError, SupervisorError) as error:
        print(f"Host failed: {error}", file=sys.stderr, flush=True)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
