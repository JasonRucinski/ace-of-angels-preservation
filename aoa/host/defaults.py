"""The one table of host facts and defaults: profiles, networks, ports, aliases,
backdrops, match limits and the managed-session settings. Times are seconds.

The server's argparse, HostConfig, the host window, the headless host and
the map tools read these. Imports nothing from the server.
"""
DIAGNOSTIC = "diagnostic"
LOOPBACK_PROFILES = ("local-relay", "local-guests")   # relay on 127.0.0.1
DOGFIGHT_PROFILES = ("lan-dogfight", "vpn-dogfight")  # relay on a LAN or VPN address
PROFILES = (DIAGNOSTIC,) + LOOPBACK_PROFILES + DOGFIGHT_PROFILES
GUEST_PROFILES = ("local-guests",) + DOGFIGHT_PROFILES  # Station tickets and guest pilots
SUSTAINED_PROFILES = ("vpn-dogfight",)                  # sustained delivery on by default
# Mode name the server reports in its status and server list.
MODE_NAMES = {"lan-dogfight": "LAN Dogfight", "vpn-dogfight": "VPN Dogfight"}

PRIVATE_NETWORKS = ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")
# Tailscale and other overlay networks assign addresses from the shared
# CGNAT range. Binding one requires it to be this host's own interface.
VPN_NETWORKS = ("100.64.0.0/10",)
LOOPBACK = "127.0.0.1"

PORTS = {"station": 5033, "arena": 5031, "tcp": 5034}
# Hosts-file names the docs suggest for players (host window display).
ALIASES = {"lan-dogfight": "aoalan", "vpn-dogfight": "aoavpn"}
# Backdrops the client ships; any other name makes On3dGfxInitialized _exit(2).
BACKDROPS = ("spacebkgd", "spacebkgd2", "spacebkgd3", "spacebkgd5", "spacebkgd6")
DEFAULT_BACKDROP = "spacebkgd3"
DEFAULT_MAP = "CTF_arena"

# Match and capacity defaults (decision 2 of PLAN.md section 5: the server's own).
LIMITS = {"kill_limit": 20, "time_limit_seconds": 600, "max_players": 8}
HOST_DEFAULTS = LIMITS  # older name
DOGFIGHT_MAX_PLAYERS = 8
ARENA_JOINS = 49            # lifetime arena slots per run (player slots 1..49)
STATION_ADMISSIONS = 64     # lifetime Station sessions per run
PEER_TIMEOUT = 30.0

# Managed sessions (headless rotation): when to recycle and how to warn.
MANAGED = {"restart_warning_seconds": 30, "intermission_seconds": 5, "idle_recycle_seconds": 300,
           "recycle_arena_joins": 40, "recycle_station_admissions": 56, "health_timeout_seconds": 30}
SESSION_COMPLETE = 75       # exit code of a managed session that ended as planned
