"""HostConfig: one host's settings, the only builder of the server command line.

`to_argv(map)` gives the station_stub.py arguments for one run on that map;
`validate()` runs, in process, every check the server makes before it opens
a socket (argparse rules, map objects and their asset files, power-up zones,
the key file), so a config that validates will start. Errors are
ConfigError with one line.

The JSON form (`to_json` / `from_json`) is what the host window saves and
what the headless host reads (deploy/linux/host.json.example):

    {"schema": 1, "profile": "vpn-dogfight", "bind_address": "100.101.102.103",
     "maps": ["CTF_arena", "CTF_arena_b"], "terrain": true, ...}

One map runs as is; a managed config (a rotation) runs each map as a managed
session that ends with exit 75 and names the next map. Relative paths are
taken from the repository root. Defaults come from aoa/host/defaults.py.
"""
import dataclasses
import json
import math
from dataclasses import dataclass, field
from pathlib import Path

from aoa.formats import trn
from aoa.host import defaults
from aoa.host.objects import load_objects
from aoa.host.objects.powerups import PowerUps
from aoa.host.runtime import ConfigError, parse_args
from aoa.maps import registry
from aoa.paths import ROOT

SCHEMA = 1
OBJECTS = ("navigation_buoys", "turret_trial", "warp_trial", "powerups")
PATHS = ("game", "key", "log", "status", "export", "state")
MANAGED_BOUNDS = {"restart_warning_seconds": (0, 300, False), "intermission_seconds": (0, 300, False),
                  "idle_recycle_seconds": (0, 86400, False), "recycle_arena_joins": (1, defaults.ARENA_JOINS - 1, True),
                  "recycle_station_admissions": (1, defaults.STATION_ADMISSIONS - 1, True),
                  "health_timeout_seconds": (5, 300, False)}

__all__ = ["ConfigError", "HostConfig", "SCHEMA"]


def _number(value):
    """Command-line text of a number: 600 for 600.0, 0.5 for 0.5."""
    return f"{value:g}" if isinstance(value, float) else str(value)


@dataclass
class HostConfig:
    profile: str = "local-guests"
    bind_address: str = defaults.LOOPBACK
    maps: list = field(default_factory=lambda: [defaults.DEFAULT_MAP])
    backdrop: str = defaults.DEFAULT_BACKDROP
    terrain: bool = False
    max_players: int = defaults.LIMITS["max_players"]
    kill_limit: int = defaults.LIMITS["kill_limit"]
    time_limit_seconds: float = defaults.LIMITS["time_limit_seconds"]
    target_ships: int = 0
    # Map objects; each needs terrain, and the first three the exported AOAOBJECTS (paths.export).
    objects: dict = field(default_factory=lambda: dict.fromkeys(OBJECTS, False))
    # None: the profile's default (on for vpn-dogfight).
    sustained_delivery: bool = None
    ports: dict = field(default_factory=lambda: dict(defaults.PORTS))
    # None picks the default: game/2.9.2, its SCRTY.BIN, work/host/<profile>.jsonl and
    # -status.json, work/2.9.2/export/AOAOBJECTS, work/host/rotation-state.json.
    paths: dict = field(default_factory=lambda: dict.fromkeys(PATHS))
    console: bool = False
    # A dict (defaults.MANAGED keys) runs managed sessions: recycling, a restart
    # warning and exit 75 after each match. Needed for a rotation.
    managed: dict = None
    # Diagnostic server flags passed through as given (spawn point, test impairment, run length).
    extra_args: list = field(default_factory=list)
    root: Path = field(default=ROOT, compare=False, repr=False)

    def __post_init__(self):
        # Partial groups keep the defaults of the keys they leave out.
        self.objects = {**dict.fromkeys(OBJECTS, False), **self.objects}
        self.ports = {**defaults.PORTS, **self.ports}
        self.paths = {**dict.fromkeys(PATHS), **self.paths}
        self.maps = list(self.maps) if isinstance(self.maps, (list, tuple)) else self.maps

    # --- paths ---------------------------------------------------------
    def path(self, name):
        value = self.paths.get(name)
        if value is None:
            work = self.root / "work/host"
            value = {"game": "game/2.9.2", "log": work / f"{self.profile}.jsonl",
                     "status": work / f"{self.profile}-status.json",
                     "export": "work/2.9.2/export/AOAOBJECTS", "state": work / "rotation-state.json"}.get(name)
            if name == "key":
                return self.path("game") / "SCRTY.BIN"
        value = Path(value)
        return value if value.is_absolute() else self.root / value

    def status_path(self):
        return self.path("status")

    def next_map(self, name):
        return self.maps[(self.maps.index(name) + 1) % len(self.maps)]

    # --- command line ---------------------------------------------------
    def to_argv(self, map_name=None):
        """station_stub.py arguments (key and log first) for one run on `map_name` (default: the first map)."""
        name = self.maps[0] if map_name is None else map_name
        argv = [str(self.path("key")), str(self.path("log")), "--profile", self.profile,
                "--bind-address", self.bind_address, "--max-players", _number(self.max_players)]
        for key, flag in (("station", "--port"), ("arena", "--arena-port"), ("tcp", "--tcp")):
            if self.ports[key] != defaults.PORTS[key]:
                argv += [flag, _number(self.ports[key])]
        argv += ["--map", name, "--backdrop", self.backdrop,
                 "--kill-limit", _number(self.kill_limit), "--time-limit", _number(self.time_limit_seconds)]
        argv += ["--target-ships", _number(self.target_ships)]
        if self.console:
            argv.append("--console")
        argv += ["--status-file", str(self.status_path())]
        if self.terrain:
            argv.append("--terrain")
        for key in ("navigation_buoys", "turret_trial", "warp_trial"):
            if self.objects.get(key):
                argv += ["--" + key.replace("_", "-"), str(self.path("export"))]
        if self.objects.get("powerups"):
            zones = self.powerup_zones(name)
            if zones is not None:
                argv += ["--powerup-zones", str(zones)]
        if self.sustained_delivery is not None:
            argv.append("--sustained-delivery" if self.sustained_delivery else "--no-sustained-delivery")
        if self.managed is not None:
            m = {**defaults.MANAGED, **self.managed}
            argv += ["--managed-session", "--next-map", self.next_map(name),
                     "--restart-warning", _number(m["restart_warning_seconds"]),
                     "--idle-recycle", _number(m["idle_recycle_seconds"]),
                     "--recycle-arena-joins", _number(m["recycle_arena_joins"]),
                     "--recycle-station-admissions", _number(m["recycle_station_admissions"])]
        return argv + [str(a) for a in self.extra_args]

    def powerup_zones(self, name):
        """The 2.9.2 terrain file whose kind-6 zones place power-ups on this map, or None (layouts have none)."""
        _, kind, target, _ = registry.MAPS[registry.MAP_NAMES.index(name)]
        return self.path("game") / target if kind == registry.TRN and self.terrain else None

    def managed_settings(self):
        return {**defaults.MANAGED, **(self.managed or {})}

    # --- validation -----------------------------------------------------
    def validate(self, *, key=True):
        """Every check the server makes before binding, for every map; raises ConfigError (one line).

        Returns the parsed server settings of each map. `key=False` skips the
        key file (the window checks it separately to name the folder).
        """
        self._check_shape()
        parsed = {}
        for name in self.maps:
            try:
                args = parse_args(self.to_argv(name), raise_errors=True)
            except ConfigError as error:
                raise ConfigError(f"{name}: {error}" if len(self.maps) > 1 else str(error)) from None
            try:
                load_objects(args)
                if args.powerup_zones is not None:
                    PowerUps(trn.powerup_zones_292(args.powerup_zones.read_bytes()))
            except (OSError, ValueError, KeyError) as error:
                raise ConfigError(f"map objects{' for ' + name if len(self.maps) > 1 else ''}: {error}") from None
            parsed[name] = args
        if key:
            path = self.path("key")
            try:
                size = len(path.read_bytes())
            except OSError:
                raise ConfigError(f"no SCRTY.BIN at {path}") from None
            if size != 256:
                raise ConfigError(f"{path} must contain exactly 256 bytes")
        return parsed

    def _check_shape(self):
        if self.profile not in defaults.PROFILES:
            raise ConfigError(f"profile must be one of {', '.join(defaults.PROFILES)}")
        maps = self.maps
        if (not isinstance(maps, list) or not 1 <= len(maps) <= len(registry.MAP_NAMES)
                or any(not isinstance(n, str) or n not in registry.MAP_NAMES for n in maps)
                or len(set(maps)) != len(maps)):
            raise ConfigError("maps must be a nonempty list of unique supported map names")
        if len(maps) > 1 and self.managed is None:
            raise ConfigError("a rotation of several maps needs managed sessions (\"managed\": {})")
        if len(maps) > 1 and not self.terrain:
            raise ConfigError("terrain must be on for a multi-map rotation (clients load each map's terrain)")
        if self.managed is not None:
            unknown = sorted(set(self.managed) - set(MANAGED_BOUNDS))
            if unknown:
                raise ConfigError(f"managed has unknown settings: {', '.join(unknown)} "
                                  f"(known: {', '.join(MANAGED_BOUNDS)})")
            for name, value in self.managed_settings().items():
                low, high, integer = MANAGED_BOUNDS[name]
                if (type(value) not in (int, float) or (integer and type(value) is not int)
                        or not math.isfinite(value) or not low <= value <= high):
                    raise ConfigError(f"managed {name} must be {'an integer' if integer else 'a number'} "
                                      f"in {low}..{high}")
            if not (self.kill_limit or self.time_limit_seconds):
                raise ConfigError("a managed session needs kill_limit or time_limit_seconds")
        for name, value in (("max_players", self.max_players), ("kill_limit", self.kill_limit),
                            ("target_ships", self.target_ships)):
            if type(value) is not int:
                raise ConfigError(f"{name} must be an integer")
        if type(self.time_limit_seconds) not in (int, float):
            raise ConfigError("time_limit_seconds must be a number")
        for name in ("terrain", "console"):
            if type(getattr(self, name)) is not bool:
                raise ConfigError(f"{name} must be true or false")
        if self.sustained_delivery not in (None, True, False):
            raise ConfigError("sustained_delivery must be true, false or null")
        for group, known in (("objects", OBJECTS), ("ports", tuple(defaults.PORTS)), ("paths", PATHS)):
            unknown = sorted(set(getattr(self, group)) - set(known))
            if unknown:
                raise ConfigError(f"{group} has unknown settings: {', '.join(unknown)} (known: {', '.join(known)})")
        if any(type(v) is not bool for v in self.objects.values()):
            raise ConfigError("objects values must be true or false")
        if any(type(v) is not int for v in self.ports.values()):
            raise ConfigError("ports must be integers")
        if any(v is not None and not isinstance(v, (str, Path)) for v in self.paths.values()):
            raise ConfigError("paths must be text or null")
        if not isinstance(self.extra_args, list) or any(not isinstance(a, (str, int, float)) for a in self.extra_args):
            raise ConfigError("extra_args must be a list of command-line words")

    # --- JSON -----------------------------------------------------------
    def to_json(self):
        data = {"schema": SCHEMA}
        for f in dataclasses.fields(self):
            if f.name == "root":
                continue
            value = getattr(self, f.name)
            if f.name == "paths":
                value = {k: (None if v is None else Path(v).as_posix()) for k, v in value.items()}
            data[f.name] = value
        return data

    @classmethod
    def from_json(cls, data, root=ROOT):
        """A HostConfig from its JSON object (or a path to one); unknown keys are named in the error."""
        if isinstance(data, (str, Path)):
            try:
                data = json.loads(Path(data).read_text(encoding="utf-8"))
            except OSError as error:
                raise ConfigError(f"host config: {error}") from None
            except ValueError as error:
                raise ConfigError(f"host config is not JSON: {error}") from None
        if not isinstance(data, dict):
            raise ConfigError("host config must be a JSON object")
        data = dict(data)
        schema = data.pop("schema", None)
        if schema != SCHEMA:
            raise ConfigError(f"host config schema must be {SCHEMA} (found {schema!r})")
        if not isinstance(data.pop("comment", ""), str):
            raise ConfigError("comment must be text")
        known = [f.name for f in dataclasses.fields(cls) if f.name != "root"]
        unknown = sorted(set(data) - set(known))
        if unknown:
            raise ConfigError(f"host config has unknown settings: {', '.join(unknown)} "
                              f"(known: schema, comment, {', '.join(known)})")
        config = cls(root=root)
        for name in ("objects", "ports", "paths"):
            if name in data:
                if not isinstance(data[name], dict):
                    raise ConfigError(f"{name} must be a JSON object")
                data[name] = {**getattr(config, name), **data[name]}
        if "managed" in data and data["managed"] is not None and not isinstance(data["managed"], dict):
            raise ConfigError("managed must be a JSON object or null")
        config = dataclasses.replace(config, **data)
        config._check_shape()
        return config

    def save(self, path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(path.name + ".tmp")
        temporary.write_text(json.dumps(self.to_json(), indent=2) + "\n", encoding="utf-8")
        temporary.replace(path)
