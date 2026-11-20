"""The host defaults tables of docs/host/README.md, generated from aoa/host/defaults.py.

  python -I tools/run.py aoa.host.defaultsdoc            print the tables
  python -I tools/run.py aoa.host.defaultsdoc --check    exit 1 if the docs tables are out of date
  python -I tools/run.py aoa.host.defaultsdoc --write    rewrite the tables in docs/host/README.md

Profiles and who can join, ports, match and capacity limits, the managed
(rotation) session settings, map objects by profile and the client patch
level each hosted feature needs. The server's argparse, HostConfig, both
windows and the headless host read the same module, so these are the
defaults every host starts from. The tables sit between two marker
comments; the text around them is written by hand.
"""
import sys

from aoa import cli
from aoa.host import defaults

PORTS = {"station": "Station login (UDP)", "arena": "arena (UDP)", "tcp": "server list (TCP)"}
LIMITS = {"kill_limit": ("Kills to end a match", ""), "time_limit_seconds": ("Match length", " s"),
          "max_players": ("Players at once", "")}
MANAGED = {"restart_warning_seconds": ("Warning before a planned restart", " s"),
           "intermission_seconds": ("Pause before reopening", " s"),
           "idle_recycle_seconds": ("Recycle a used session with no arena players after", " s"),
           "recycle_arena_joins": ("Recycle after arena joins", ""),
           "recycle_station_admissions": ("Recycle after Station logins", ""),
           "health_timeout_seconds": ("Stop a process whose status file is older than", " s")}
OBJECTS = {"navigation_buoys": "Navigation buoys", "map_waypoints": "Map waypoints",
           "turret_trial": "Turret trial", "warp_trial": "Warp gates trial"}


def code(values):
    return ", ".join(f"`{v}`" for v in values)


def who(profile):
    if profile in defaults.DOGFIGHT_PROFILES:
        networks = defaults.PRIVATE_NETWORKS + (defaults.VPN_NETWORKS if profile == "vpn-dogfight" else ())
        return "this PC's own address in " + code(networks)
    return f"this PC only (`{defaults.LOOPBACK}`)"


def profiles():
    rows = ["| Profile | Who can join | Relay | Guest pilots | Sustained delivery | Server-list name | Hosts name |",
            "|---|---|---|---|---|---|---|"]
    for profile in defaults.PROFILES:
        rows.append(" | ".join([
            f"| `{profile}`", who(profile),
            "no: listens only" if profile == defaults.DIAGNOSTIC else "yes",
            "yes" if profile in defaults.GUEST_PROFILES else "no",
            "on" if profile in defaults.SUSTAINED_PROFILES else "off",
            defaults.MODE_NAMES.get(profile, ""),
            f"`{defaults.ALIASES[profile]}`" if profile in defaults.ALIASES else ""]) + " |")
    return rows


def pairs(header, items):
    return [header, "|---|---|", *(f"| {label} | {value} |" for label, value in items)]


def tables():
    out = ["**Profiles.**", "", *profiles(), ""]
    out += ["**Ports.**", ""]
    out += pairs("| Port | Number |", ((PORTS.get(k, k), v) for k, v in defaults.PORTS.items()))
    limits = [(LIMITS.get(k, (k, ""))[0], f"{v}{LIMITS.get(k, (k, ''))[1]}") for k, v in defaults.LIMITS.items()]
    limits += [("Arena joins per server run", defaults.ARENA_JOINS),
               ("Station logins per server run", defaults.STATION_ADMISSIONS),
               ("Silence before a player expires", f"{defaults.PEER_TIMEOUT:g} s"),
               ("Map", f"`{defaults.DEFAULT_MAP}`"),
               ("Backdrop", f"`{defaults.DEFAULT_BACKDROP}` (the client ships {code(defaults.BACKDROPS)})")]
    out += ["", "**Matches and capacity** (0 turns a match limit off).", ""]
    out += pairs("| Setting | Default |", limits)
    managed = [(MANAGED.get(k, (k, ""))[0], f"{v}{MANAGED.get(k, (k, ''))[1]}") for k, v in defaults.MANAGED.items()]
    managed.append(("Exit code of a session that ended as planned", defaults.SESSION_COMPLETE))
    out += ["", "**Rotation and recycling** (managed sessions: the headless host, a window rotation).", ""]
    out += pairs("| Setting | Default |", managed)
    out += ["", f"**Map objects.** {defaults.OBJECT_RULE[0].upper()}{defaults.OBJECT_RULE[1:]}.", ""]
    out += pairs("| Object | Profiles |", ((OBJECTS.get(k, k), code(v)) for k, v in defaults.OBJECT_PROFILES.items()))
    out += ["", "**Client patch level each hosted feature needs.**", ""]
    out += pairs("| Feature | Patch level |", ((k, f"{v} or later") for k, v in defaults.CLIENT_PATCH_LEVELS.items()))
    return "\n".join(out) + "\n"


BLOCK = cli.DocBlock("docs/host/README.md", "host defaults", "aoa.host.defaultsdoc", tables)


def main(argv=None):
    return BLOCK.main(argv, __doc__)


if __name__ == "__main__":
    sys.exit(cli.run(main))
