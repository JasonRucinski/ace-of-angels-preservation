"""The launchers' one settings file: work/settings.json.

    {"schema": 1,
     "game_folder": "game/2.9.2",
     "client": {"server": "aoalan", "friends": [{"name": "Sam", "address": "192.168.0.61"}],
                "skip_wrapper": false},
     "host": {"schema": 1, "profile": "lan-dogfight", "bind_address": "192.168.0.61", ...}}

`host` is a HostConfig JSON object (aoa/host/config.py), so the same object
works as the Linux host's host.json, and `tools/aoa_host.py run
work/settings.json` reads it. The file stores only what differs from the
defaults; the defaults stay in the engines' tables (HostConfig, prepare).

load() never raises: a missing file gives the defaults, a damaged one the
defaults plus a notice per value it could not use, named. On first use the
host window's old work/host/host_control.json is migrated (and left in place).
"""
import copy
import dataclasses
import json
import math
from pathlib import Path

from aoa.client import prepare
from aoa.host import defaults
from aoa.host.config import ConfigError, HostConfig
from aoa.maps import registry
from aoa.paths import ROOT, WORK

SCHEMA = 1
PATH = WORK / "settings.json"
OLD_HOST_FILE = WORK / "host" / "host_control.json"
DEFAULT_GAME = "game/2.9.2"
DEFAULT_SERVER = prepare.LOOPBACK[0]
CLIENT_KEYS = ("server", "friends", "skip_wrapper")
FRIEND_KEYS = ("name", "address", "alias")
MAX_FRIENDS = 20


def default_host():
    """The host window's starting point before anything is saved: the engine's defaults with map
    terrain on. Saved files store the difference from HostConfig() itself (host_difference)."""
    return HostConfig(terrain=True, objects={"powerups": True})


@dataclasses.dataclass
class Settings:
    game_folder: str = DEFAULT_GAME
    server: str = DEFAULT_SERVER
    friends: list = dataclasses.field(default_factory=list)
    skip_wrapper: bool = False
    host: HostConfig = dataclasses.field(default_factory=default_host)

    def game_path(self, root=ROOT):
        path = Path(self.game_folder)
        return path if path.is_absolute() else Path(root) / path

    def friend(self, name):
        return next((f for f in self.friends if f["name"] == name), None)

    def add_friend(self, name, address, alias=None):
        """Remember a friend's server (replacing one of the same name); the newest first."""
        entry = {"name": name, "address": address, **({"alias": alias} if alias else {})}
        check_friend(entry)
        self.friends = [entry, *(f for f in self.friends if f["name"] != name)][:MAX_FRIENDS]
        return entry

    def to_json(self):
        """Only what differs from the defaults."""
        data = {"schema": SCHEMA}
        if self.game_folder != DEFAULT_GAME:
            data["game_folder"] = self.game_folder
        client = {}
        if self.server != DEFAULT_SERVER:
            client["server"] = self.server
        if self.friends:
            client["friends"] = [dict(f) for f in self.friends]
        if self.skip_wrapper:
            client["skip_wrapper"] = True
        if client:
            data["client"] = client
        data["host"] = host_difference(self.host)
        return data


def host_config(settings):
    """A copy of the host settings for a run: the shared game folder unless the host names its own."""
    config = copy.deepcopy(settings.host)
    if config.paths.get("game") is None:
        config.paths["game"] = settings.game_folder
    return config


def host_difference(config):
    """config.to_json() with only the keys that differ from the engine's HostConfig() (plus schema),
    so the object means the same to the headless host, which knows nothing of default_host()."""
    current, base = config.to_json(), HostConfig().to_json()
    return {k: v for k, v in current.items() if k == "schema" or v != base.get(k)}


def check_friend(entry):
    if not isinstance(entry, dict):
        raise ValueError("a friend must be a JSON object")
    unknown = sorted(set(entry) - set(FRIEND_KEYS))
    if unknown:
        raise ValueError(f"unknown friend setting {', '.join(unknown)}")
    for key in ("name", "address"):
        if not isinstance(entry.get(key), str) or not entry[key].strip() or len(entry[key]) > 64:
            raise ValueError(f"friend {key} must be text of 1 to 64 characters")
    if "alias" in entry:
        prepare.host_field(entry["alias"])


def _client(data, settings, notices):
    if not isinstance(data, dict):
        notices.append("Ignored the player settings: they are not a JSON object.")
        return
    for key in sorted(set(data) - set(CLIENT_KEYS)):
        notices.append(f"Ignored an unknown player setting: {key!r}.")
    if "server" in data:
        try:
            prepare.host_field(data["server"])
            settings.server = data["server"]
        except (ValueError, TypeError):
            notices.append(f"Ignored the saved server address {data['server']!r}: the game cannot use it.")
    if "friends" in data:
        friends = data["friends"] if isinstance(data["friends"], list) else []
        if not isinstance(data["friends"], list):
            notices.append("Ignored the saved friends: they are not a list.")
        for entry in friends[:MAX_FRIENDS]:
            try:
                check_friend(entry)
            except (ValueError, TypeError) as error:
                notices.append(f"Ignored a saved friend ({error}).")
                continue
            if settings.friend(entry["name"]) is None:
                settings.friends.append(dict(entry))
    if "skip_wrapper" in data:
        if type(data["skip_wrapper"]) is bool:
            settings.skip_wrapper = data["skip_wrapper"]
        else:
            notices.append("Ignored skip_wrapper: it must be true or false.")


def _host(data, notices, root=ROOT):
    """A HostConfig from a saved host object; values it cannot use are dropped one by one, each named."""
    if not isinstance(data, dict):
        notices.append("Ignored the host settings: they are not a JSON object.")
        return default_host()
    base = HostConfig().to_json()
    try:
        return HostConfig.from_json({**base, **data}, root=root)
    except ConfigError:
        pass
    kept = dict(base)
    for key, value in data.items():
        if key == "schema":
            continue
        try:
            HostConfig.from_json({**kept, key: value}, root=root)
        except ConfigError as error:
            notices.append(f"Ignored the host setting {key!r}: {error}.")
            continue
        kept[key] = value
    try:
        return HostConfig.from_json(kept, root=root)
    except ConfigError as error:  # values valid alone but not together
        notices.append(f"Ignored the saved host settings: {error}.")
        return default_host()


def from_json(data, notices, root=ROOT):
    settings = Settings()
    if not isinstance(data, dict):
        notices.append("The settings file does not hold settings; using the defaults.")
        return settings
    if data.get("schema") != SCHEMA:
        notices.append(f"The settings file has schema {data.get('schema')!r}, not {SCHEMA}; using the defaults.")
        return settings
    for key in sorted(set(data) - {"schema", "game_folder", "client", "host"}):
        notices.append(f"Ignored an unknown setting: {key!r}.")
    if "game_folder" in data:
        if isinstance(data["game_folder"], str) and data["game_folder"].strip():
            settings.game_folder = data["game_folder"]
        else:
            notices.append("Ignored the saved game folder: it is not a folder name.")
    if "client" in data:
        _client(data["client"], settings, notices)
    if "host" in data:
        settings.host = _host(data["host"], notices, root)
    return settings


def load(path=None, notices=None, old_host_file=None, root=ROOT):
    """(Settings, notices). Never raises; see the module docstring."""
    path = Path(PATH if path is None else path)
    notices = [] if notices is None else notices
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        settings = Settings()
        old = Path(OLD_HOST_FILE if old_host_file is None else old_host_file)
        if old.is_file():
            settings.host, game = migrate_host_control(old, notices, root)
            if game:
                settings.game_folder = game
            notices.append(f"Read your earlier host settings from {old.name}.")
        return settings, notices
    except (OSError, UnicodeDecodeError, ValueError) as error:
        notices.append(f"Could not read the settings file ({error}); using the defaults.")
        return Settings(), notices
    return from_json(data, notices, root), notices


def save(settings, path=None):
    path = Path(PATH if path is None else path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(settings.to_json(), indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)
    return path


# --- migration of the host window's file before work/settings.json ---------------
OLD_MODES = {"This PC only": "local-guests", "LAN": "lan-dogfight", "VPN (internet)": "vpn-dogfight"}
OLD_OBJECTS = ("navigation_buoys", "turret_trial", "warp_trial")


def migrate_host_control(path, notices, root=ROOT):
    """(HostConfig, game folder or None) from an old work/host/host_control.json; bad values are skipped."""
    try:
        old = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError) as error:
        notices.append(f"Could not read {Path(path).name} ({error}); using the default host settings.")
        return default_host(), None
    if not isinstance(old, dict):
        return default_host(), None
    data = {}
    mode = OLD_MODES.get(old.get("mode"), old.get("mode"))
    if mode in OLD_MODES.values():
        data["profile"] = mode
        if mode != "local-guests" and isinstance(old.get("address"), str) and old["address"].strip():
            data["bind_address"] = old["address"].split()[0]
    if old.get("map") in registry.MAP_NAMES:
        data["maps"] = [old["map"]]
    if type(old.get("terrain")) is bool:
        data["terrain"] = old["terrain"]
        data["objects"] = {"powerups": old["terrain"]}
    if old.get("backdrop") in defaults.BACKDROPS:
        data["backdrop"] = old["backdrop"]
    for key in ("max_players", "kill_limit", "target_ships"):
        if type(old.get(key)) is int:
            data[key] = old[key]
    minutes = old.get("time_limit_min")
    if type(minutes) in (int, float) and math.isfinite(minutes) and minutes >= 0:
        data["time_limit_seconds"] = int(minutes * 60)
    for key in OLD_OBJECTS:
        if type(old.get(key)) is bool:
            data.setdefault("objects", {})[key] = old[key]
    game = old.get("game") if isinstance(old.get("game"), str) and old["game"].strip() else None
    return _host(data, notices, root), game
