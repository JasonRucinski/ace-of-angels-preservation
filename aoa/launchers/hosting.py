"""The host window's decisions, without a window: settings to HostConfig, the checks
before Start, the line to share, the firewall commands, the status text and the
map change that validates before it restarts.

The window edits one HostConfig (work/settings.json "host"); for each run
run_config() makes the copy that starts: the shared game folder, the console
the window talks to, and map objects that cannot run switched off. A
Supervisor (aoa/host/supervisor.py) runs it, as the headless host does.
"""
import copy
import time

from aoa.host import defaults
from aoa.host.config import ConfigError
from aoa.host.supervisor import HostProcess, RestartBudget, Supervisor
from aoa.launchers import catalog, game_folder, join, settings as settings_module
from aoa.paths import ROOT


# --- editing the settings ----------------------------------------------------------
def audience(config):
    return catalog.AUDIENCE_OF_PROFILE.get(config.profile, catalog.AUDIENCES[0])


def set_audience(config, key, address=None):
    """Who can join: the profile, and the address (loopback for this PC only)."""
    chosen = catalog.AUDIENCE[key]
    config.profile = chosen.profile
    config.bind_address = defaults.LOOPBACK if chosen.kind is None else (address or "").strip()
    return config


def address_choices(config, found):
    """This PC's addresses that fit the audience; the saved one first when it still fits."""
    choices = [] if audience(config).kind is None else \
        [a for a, k in found if k == audience(config).kind]
    return choices


def set_maps(config, maps):
    """One map runs as is; several rotate, which needs managed sessions and map terrain."""
    maps = list(dict.fromkeys(maps))
    if not maps:
        raise ConfigError("Choose at least one map.")
    config.maps = maps
    if len(maps) > 1:
        config.managed = config.managed if config.managed is not None else {}
        config.terrain = True
    else:
        config.managed = None
    return config


def run_config(s, export_ready=None):
    """The HostConfig one run starts with (a copy; the saved settings are not changed)."""
    config = settings_module.host_config(s)
    config.console = True
    ready = game_folder.export_ready(config.path("export")) if export_ready is None else export_ready
    reasons = catalog.object_availability(config.profile, config.maps, config.terrain, ready)
    for key, reason in reasons.items():
        if reason:
            config.objects[key] = False
    config.objects["powerups"] = bool(config.terrain and config.objects.get("powerups", True))
    placed = any(config.objects[k] for k in ("navigation_buoys", "turret_trial"))
    if config.sustained_delivery is None and (placed or config.profile == "local-guests"):
        config.sustained_delivery = True
    return config


# --- before Start ------------------------------------------------------------------
def check(config):
    """Everything that would stop this config from starting; ConfigError with a sentence for the host."""
    if audience(config).kind is not None and not config.bind_address:
        raise ConfigError(audience(config).no_address)
    key = config.path("key")
    if not key.is_file():
        raise ConfigError(f"No game found in {config.path('game')}. Set the game up with Play.cmd first, "
                          "or choose your game folder under Advanced.")
    for name in config.maps:
        needed = catalog.BY_NAME[name].client_file
        if needed and config.terrain and not (config.path("game") / needed).is_file():
            raise ConfigError(f"{name} needs its terrain file. Open Play.cmd, Options, and choose "
                              "\"Install JRMAP terrain\". Every player needs it too.")
    try:
        config.validate()
    except ConfigError as error:
        raise ConfigError(explain(str(error))) from None
    return config


def explain(message):
    """The server's own error, with a next step when it is one players of this window meet."""
    lower = message.lower()
    if "bind-address" in lower or "address" in lower and ("range" in lower or "requires" in lower):
        return f"{message}. Choose an address from the list for this kind of game."
    return message


# --- for players -----------------------------------------------------------------------
def share_text(config):
    """What the host tells players; the Join tab of Play.cmd reads it back."""
    if audience(config).kind is None:
        return "Players on this PC: open Play.cmd and choose Play on: This PC."
    return join.share_line(config.bind_address, catalog.ALIASES[config.profile])


def needs_text(config):
    return " ".join(catalog.feature_sentence(f) for f in catalog.host_needs(config))


def firewall_commands(config):
    """The inbound rules this host needs, as PowerShell lines to run as administrator (never run here)."""
    if audience(config).kind is None:
        return []
    vpn = config.profile == "vpn-dogfight"
    tag, label = ("VPN", "VPN") if vpn else ("LAN", "LAN")
    remote, profile = ("100.64.0.0/10", "Any") if vpn else ("LocalSubnet", "Private")
    udp = f"{config.ports['arena']},{config.ports['station']}"
    lines = []
    for protocol, ports in (("UDP", udp), ("TCP", str(config.ports["tcp"]))):
        lines.append(f"New-NetFirewallRule -Name AoA-{tag}-{protocol} -DisplayName \"Ace of Angels {label} "
                     f"{protocol}\" -Direction Inbound -Action Allow -Protocol {protocol} -LocalPort {ports} "
                     f"-LocalAddress {config.bind_address} -RemoteAddress {remote} -Profile {profile}")
    return lines


def firewall_sentence(config):
    if audience(config).kind is None:
        return "Not needed: only this PC can join."
    return (f"Windows must let players reach UDP {config.ports['arena']} and {config.ports['station']} and "
            f"TCP {config.ports['tcp']} on {config.bind_address}. Run these two lines once, in PowerShell "
            "opened as administrator:")


# --- running ---------------------------------------------------------------------------
def supervisor_for(config, report, process=None, budget=None):
    """A Supervisor as the headless host builds one, with a console the window talks to."""
    managed = config.managed is not None
    process = process or HostProcess(cwd=ROOT, console=True, capture=True)
    return Supervisor(config, process, budget=budget or RestartBudget(),
                      state_path=config.path("state") if managed else None,
                      watchdog=config.managed_settings()["health_timeout_seconds"] if managed else None,
                      report=report)


def change_map(supervisor, new, notice_seconds=2.0, sleep=time.sleep):
    """Restart on new settings: check them first (if they cannot start, nothing is said or
    stopped and ConfigError is raised), then warn the players, stop, and start."""
    check(new)
    supervisor.process.command(f"say Host is switching to {new.maps[0]}. Quit the game and rejoin in a minute.")
    sleep(notice_seconds)
    supervisor.stop()
    supervisor.change(new)
    supervisor.state["map"] = new.maps[0]
    supervisor.start(new)


def clock(seconds):
    seconds = int(seconds or 0)
    return f"{seconds // 3600}:{seconds % 3600 // 60:02}:{seconds % 60:02}"


def status_lines(status, config, age=None):
    """(headline, detail) for the running panel from the server's status file."""
    if status is None:
        return "Starting…", ""
    stale = age is not None and age > 8
    players = status.get("players") or []
    headline = (f"Running on {status.get('map')} · match {status.get('match')} · up {clock(status.get('uptime_s'))}"
                + (" · not responding" if stale else ""))
    detail = (f"{len(players)} of {status.get('max_players', config.max_players)} players · "
              f"joins used {status.get('arena_joins_used')} of {status.get('arena_joins_limit')}"
              + (" (the host restarts itself before the limit)" if config.managed is not None else "")
              + f" · banned addresses {status.get('banned_ips', 0)}")
    if status.get("impairment"):
        detail += " · TEST IMPAIRMENT ON"
    return headline, detail


COLUMNS = (("slot", "Slot", 50), ("pilot", "Pilot", 200), ("kills", "Kills", 60), ("deaths", "Deaths", 60),
           ("ping", "Ping (ms)", 80), ("idle", "Idle (s)", 70), ("flying", "Flying", 70))


def player_rows(status):
    """Table rows, sorted by kills."""
    rows = []
    for p in sorted((status or {}).get("players") or [], key=lambda p: (-p["kills"], p["deaths"], p["slot"])):
        rows.append((p["slot"], p["pilot"], p["kills"], p["deaths"],
                     "-" if p.get("ping_ms") is None else p["ping_ms"], p.get("idle_s", "-"),
                     "yes" if p.get("loaded") else "no"))
    return rows


def describe(config):
    """One line for the Start button's neighbour: what will run."""
    maps = config.maps[0] if len(config.maps) == 1 else f"{len(config.maps)} maps in turn"
    limits = []
    if config.kill_limit:
        limits.append(f"{config.kill_limit} kills")
    if config.time_limit_seconds:
        limits.append(f"{config.time_limit_seconds / 60:g} minutes")
    return (f"{audience(config).label} · {maps} · {' or '.join(limits) or 'no limit'} · "
            f"up to {config.max_players} players")


def copy_config(config):
    return copy.deepcopy(config)
