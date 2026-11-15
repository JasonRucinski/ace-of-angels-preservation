"""Bounded local Station configuration, logging and TCP list transport."""
import argparse
import ipaddress
import json
import math
import os
import queue
import selectors
import socket
import threading
import time
from pathlib import Path
from collections import Counter, OrderedDict

from aoa.host import object_slots as slots
from aoa.host.defaults import (OBJECT_PROFILES, OBJECT_RULE, requirement, ARENA_JOINS, BACKDROPS, DEFAULT_BACKDROP, DEFAULT_MAP, DOGFIGHT_MAX_PLAYERS,
                               DOGFIGHT_PROFILES, GUEST_PROFILES, HOST_DEFAULTS, LOOPBACK, LOOPBACK_PROFILES,
                               MANAGED, PEER_TIMEOUT, PORTS, PRIVATE_NETWORKS, PROFILES, STATION_ADMISSIONS,
                               SUSTAINED_PROFILES, VPN_NETWORKS)
from aoa.host.vessels import DEFAULT_VESSEL, SELECTABLE_VESSELS
from aoa.maps import registry

__all__ = ["ConfigError", "DatagramBudget", "EventLog", "StationTCPServer", "build_parser", "parse_args",
           # also read from here by older callers
           "DOGFIGHT_PROFILES", "PRIVATE_NETWORKS", "VPN_NETWORKS", "HOST_DEFAULTS", "DEFAULT_VESSEL",
           "SELECTABLE_VESSELS"]


class ConfigError(ValueError):
    """An invalid server setting, as argparse's one-line message without the usage text."""


class _Parser(argparse.ArgumentParser):
    raise_errors = False

    def error(self, message):
        if self.raise_errors:
            raise ConfigError(message)
        super().error(message)


class DatagramBudget:
    """Fixed diagnostic ingress limits; bounded endpoint tracking and work."""
    GLOBAL_RATE, GLOBAL_BURST = 400, 200
    PEER_RATE, PEER_BURST = 60, 120
    MAX_PEERS = 256

    def __init__(self):
        self.tokens = self.GLOBAL_BURST
        self.updated = None
        self.peers = OrderedDict()
        self.dropped = 0

    def allow(self, peer, now):
        if self.updated is None:
            self.updated = now
        self.tokens = min(self.GLOBAL_BURST, self.tokens + max(0, now - self.updated) * self.GLOBAL_RATE)
        self.updated = now
        if self.tokens < 1:
            self.dropped += 1
            return False
        self.tokens -= 1
        tokens, updated = self.peers.pop(peer, (self.PEER_BURST, now))
        tokens = min(self.PEER_BURST, tokens + max(0, now - updated) * self.PEER_RATE)
        allowed = tokens >= 1
        self.peers[peer] = (tokens - 1 if allowed else tokens, now)
        if len(self.peers) > self.MAX_PEERS:
            self.peers.popitem(last=False)
        if not allowed:
            self.dropped += 1
        return allowed


def build_parser(raise_errors=False):
    """The server's argparse parser (aoa/host/flagdoc.py builds the docs table from it)."""
    parser = _Parser(description="AoA local diagnostics and private LAN/VPN dogfight relay")
    parser.raise_errors = raise_errors
    parser.add_argument("key", type=Path, help="256-byte SCRTY.BIN")
    parser.add_argument("log", type=Path, help="rotating JSONL output")
    parser.add_argument("--profile", choices=PROFILES, default="diagnostic",
                        help="diagnostic listens only; local-relay and local-guests serve this PC; "
                             "lan-dogfight and vpn-dogfight a private LAN or VPN address")
    parser.add_argument("--bind-address", default=LOOPBACK,
                        help="specific local IPv4; LAN profile requires RFC1918, VPN profile also 100.64.0.0/10")
    parser.add_argument("--map", choices=registry.MAP_NAMES, default=DEFAULT_MAP,
                        help="advertised terrain; with --terrain, the map a patched client loads")
    parser.add_argument("--backdrop", choices=BACKDROPS, default=DEFAULT_BACKDROP,
                        help="space backdrop named in the server list; the client accepts only these")
    parser.add_argument("--port", type=int, default=PORTS["station"], help="Station UDP port; 0 picks a free one (tests)")
    parser.add_argument("--arena-port", type=int, default=PORTS["arena"], help="arena UDP port; 0 picks a free one")
    parser.add_argument("--tcp", type=int, default=None,
                        help=f"Station list TCP port; {PORTS['tcp']} in every relay profile, off in diagnostic")
    parser.add_argument("--ack", action=argparse.BooleanOptionalAction, default=None,
                        help="answer Station and arena handshakes (on in every relay profile)")
    parser.add_argument("--arena", action=argparse.BooleanOptionalAction, default=None,
                        help="open the arena UDP port (on in every relay profile)")
    parser.add_argument("--relay", action=argparse.BooleanOptionalAction, default=None,
                        help="assign player tags and relay movement and combat (on in every relay profile)")
    # Old names, kept for one release; hidden from --help.
    parser.add_argument("--experimental-relay", dest="relay", action=argparse.BooleanOptionalAction,
                        default=argparse.SUPPRESS, help=argparse.SUPPRESS)
    parser.add_argument("--pilot", default="testpilot",
                        help="synthetic Station pilot name, 1..19 ASCII characters (a prefix with guest profiles)")
    parser.add_argument("--seconds", type=float, default=0, help="stop after this many seconds; 0 runs until stopped")
    parser.add_argument("--peer-timeout", type=float, default=PEER_TIMEOUT,
                        help="seconds of silence before a Station or arena peer expires")
    parser.add_argument("--max-players", type=int, default=HOST_DEFAULTS["max_players"],
                        help="simultaneous arena admissions, 1..49")
    parser.add_argument("--kill-limit", type=int, default=HOST_DEFAULTS["kill_limit"],
                        help="relay match ends at this many kills; 0 disables")
    parser.add_argument("--time-limit", type=float, default=float(HOST_DEFAULTS["time_limit_seconds"]),
                        help="relay match length in seconds; 0 disables")
    parser.add_argument("--raw-capture", action="store_true",
                        help="log payloads and addresses too (private diagnostic captures only)")
    parser.add_argument("--terrain", action="store_true",
                        help=f"native terrain for --map; {requirement('terrain')} "
                             "(clients without it join in empty space)")
    parser.add_argument("--experimental-terrain", dest="terrain", action="store_true",
                        default=argparse.SUPPRESS, help=argparse.SUPPRESS)
    parser.add_argument("--spawn-at", type=float, nargs=3, metavar=("X", "Y", "Z"),
                        help="first relay spawn; defaults to the map's viewing spawn with terrain, else the origin")
    parser.add_argument("--start-vessel", default=DEFAULT_VESSEL, choices=sorted(SELECTABLE_VESSELS), metavar="NAME",
                        help=f"fighter every pilot starts in until they pick another (default {DEFAULT_VESSEL}); "
                             "needs the relay")
    parser.add_argument("--sustained-delivery", action=argparse.BooleanOptionalAction, default=None,
                        help="windowed ordered delivery of despawns/combat events for a whole session "
                             "(default on for vpn-dogfight); see aoa/host/delivery.py")
    parser.add_argument("--reorder-margin", type=float, default=3.0,
                        help="seconds a stale datagram may trail later ones (sustained delivery)")
    parser.add_argument("--status-file", type=Path, help="JSON host status, rewritten every two seconds")
    parser.add_argument("--console", action="store_true", help="read host commands (status, kick, ban) from stdin")
    parser.add_argument("--log-max-bytes", type=int, default=1024 * 1024, help="log file size before rotation")
    parser.add_argument("--log-backups", type=int, default=3, help="rotated log files kept, 1..10")
    parser.add_argument("--print-config", action="store_true", help="validate and print settings without reading key or binding")

    objects = parser.add_argument_group("map objects", "server-placed objects; each needs the relay")
    objects.add_argument("--powerup-zones", type=Path, metavar="TRN",
                         help="place power-ups in the kind-6 zones of this 2.9.2 terrain file "
                              "(e.g. game/2.9.2/jrmap292.trn)")
    objects.add_argument("--target-ships", type=int, default=0, metavar="N",
                         help="N passive hostile ships ahead of the spawn that the target keys can select "
                              f"(0..{slots.target_limit()})")
    objects.add_argument('--navigation-buoys', type=Path, metavar='EXPORT_DIR',
                         help='restore the selected map navigation objects from exported AOAOBJECTS, with original archive order')
    objects.add_argument('--buoy-trn', type=Path, help='original JRMAP.TRN for navigation on JRMAP; defaults beside SCRTY.BIN')
    objects.add_argument('--map-waypoints', type=Path, metavar='TRN',
                         help='navigation waypoints (kind 3) of a 2.9.2 terrain file from tools/make_map.py')
    objects.add_argument('--turret-trial', type=Path, metavar='EXPORT_DIR',
                         help='inactive five-turret Arena1a placement trial; model assignment is provisional and orientation is zero')
    objects.add_argument('--warp-trial', type=Path, metavar='EXPORT_DIR',
                         help='nine native Arena1a warp gates on loopback; local client transit, editor orientation not restored')

    managed = parser.add_argument_group("managed session", "the headless host's rotation; each needs --managed-session")
    managed.add_argument("--managed-session", action="store_true",
                         help="warn, drain and exit 75 after a match or admission limit")
    managed.add_argument("--next-map", choices=registry.MAP_NAMES, help="next map announced")
    managed.add_argument("--restart-warning", type=float, default=MANAGED["restart_warning_seconds"],
                         help="restart countdown in seconds")
    managed.add_argument("--recycle-arena-joins", type=int, default=MANAGED["recycle_arena_joins"],
                         help=f"end the session after this many arena joins (below the {ARENA_JOINS} per run)")
    managed.add_argument("--recycle-station-admissions", type=int, default=MANAGED["recycle_station_admissions"],
                         help=f"end the session after this many Station logins (below the {STATION_ADMISSIONS} per run)")
    managed.add_argument("--idle-recycle", type=float, default=MANAGED["idle_recycle_seconds"],
                         help="recycle used admissions after this long with no arena players")

    diagnostics = parser.add_argument_group("diagnostics", "protocol experiments and test conditions; not for play")
    diagnostics.add_argument("--experimental-flight", action=argparse.BooleanOptionalAction, default=None,
                             help="flight entry without the relay")
    diagnostics.add_argument("--experimental-object", action=argparse.BooleanOptionalAction, default=None,
                             help="one passive test object (slot 1)")
    diagnostics.add_argument("--experimental-teams", action=argparse.BooleanOptionalAction, default=None,
                             help="free-for-all teams (crashed a client: findings 9.30-9.31)")
    diagnostics.add_argument("--experimental-reliable-combat", action="store_true",
                             help="ordered combat delivery; retires peers at 30 total essential events")
    diagnostics.add_argument("--experimental-protection-probe", action="store_true",
                             help="single-client explicit 0x81 probe; requires the opt-in prepared client")
    diagnostics.add_argument("--spawn-axis", choices=("x", "z"), default="x",
                             help="relay spawn line; ships initially face +z")
    diagnostics.add_argument("--spawn-spacing", type=float, default=1000.0, help="distance between relay spawns")
    diagnostics.add_argument("--impair-rtt-ms", type=float, default=0.0, help="TEST ONLY: added round trip")
    diagnostics.add_argument("--impair-jitter-ms", type=float, default=0.0, help="TEST ONLY: random extra delay per direction")
    diagnostics.add_argument("--impair-loss", type=float, default=0.0, help="TEST ONLY: percent dropped per direction")
    diagnostics.add_argument("--impair-duplicate", type=float, default=0.0, help="TEST ONLY: percent duplicated per direction")
    diagnostics.add_argument("--impair-seed", type=int, help="TEST ONLY: repeatable impairment")
    return parser


def parse_args(argv=None, *, raise_errors=False):
    """Validated server settings. With raise_errors, an invalid setting raises
    ConfigError for in-process callers instead of printing usage and exiting."""
    parser = build_parser(raise_errors)
    args = parser.parse_args(argv)

    def given(name):
        return getattr(args, name) != parser.get_default(name)

    for flag in ("ack", "arena", "experimental_flight", "relay", "experimental_object", "experimental_teams"):
        if getattr(args, flag) is None:
            setattr(args, flag, args.profile in LOOPBACK_PROFILES + DOGFIGHT_PROFILES
                    and flag in ("ack", "arena", "relay"))
    args.guest_sessions = args.profile in GUEST_PROFILES
    if args.sustained_delivery is None:
        args.sustained_delivery = args.profile in SUSTAINED_PROFILES
    if args.terrain and args.profile not in DOGFIGHT_PROFILES + LOOPBACK_PROFILES:
        parser.error("--terrain requires a dogfight or loopback relay/guest profile")
    # Settings that would be ignored in this mode are refused (audit H10).
    for name in ("next_map", "restart_warning", "recycle_arena_joins", "recycle_station_admissions", "idle_recycle"):
        if given(name) and not args.managed_session:
            parser.error(f"--{name.replace('_', '-')} needs --managed-session")
    for name in ("kill_limit", "time_limit", "spawn_axis", "spawn_spacing", "start_vessel", "powerup_zones"):
        if given(name) and not args.relay:
            parser.error(f"--{name.replace('_', '-')} requires the relay")
    if given("reorder_margin") and not args.sustained_delivery:
        parser.error("--reorder-margin needs sustained delivery")
    if given("buoy_trn") and not (args.navigation_buoys and args.map == "JRMAP"):
        parser.error("--buoy-trn needs --navigation-buoys on JRMAP")
    if not 0 <= args.target_ships <= slots.target_limit():
        parser.error(f"--target-ships must be 0..{slots.target_limit()}")
    if args.target_ships and not args.relay:
        parser.error("--target-ships requires the relay")
    for name in OBJECT_PROFILES:
        if getattr(args, name) is not None and args.profile not in OBJECT_PROFILES[name]:
            parser.error(f"--{name.replace('_', '-')} is not offered on {args.profile} ({OBJECT_RULE})")
    if args.warp_trial is not None:
        if not (args.relay and args.terrain and args.sustained_delivery and args.map == 'Arena1a'):
            parser.error('--warp-trial requires a loopback relay, Arena1a terrain and sustained delivery')
        if args.target_ships > slots.target_limit(["warp_gates"]):
            parser.error(f'--warp-trial reserves {slots.reservation("warp_gates")}; '
                         f'at most {slots.target_limit(["warp_gates"])} target ships')
        if not args.warp_trial.is_dir():
            parser.error('--warp-trial requires an original exported AOAOBJECTS directory')
    if args.turret_trial is not None:
        if not (args.relay and args.terrain and args.sustained_delivery and args.map == 'Arena1a'):
            parser.error('--turret-trial requires relay, Arena1a terrain and sustained delivery')
        if args.target_ships > slots.target_limit(["turrets"]):
            parser.error(f'--turret-trial reserves {slots.reservation("turrets")}; '
                         f'at most {slots.target_limit(["turrets"])} target ships')
        if not args.turret_trial.is_dir():
            parser.error('--turret-trial requires an original exported AOAOBJECTS directory')
    if args.navigation_buoys is not None:
        if not (args.relay and args.terrain and args.sustained_delivery):
            parser.error('--navigation-buoys requires relay, terrain and sustained delivery')
        if args.target_ships > slots.target_limit(["buoys"]):
            parser.error(f'--navigation-buoys reserves {slots.reservation("buoys")}; '
                         f'at most {slots.target_limit(["buoys"])} target ships')
        if not args.navigation_buoys.is_dir():
            parser.error('--navigation-buoys requires an exported AOAOBJECTS directory')
        if args.map == 'JRMAP':
            trn = args.buoy_trn or args.key.parent / 'JRMAP.TRN'
            if not trn.is_file():
                parser.error(f'--navigation-buoys on JRMAP needs the original JRMAP.TRN: no file {trn} (see --buoy-trn)')
    if args.map_waypoints is not None:
        if args.navigation_buoys:
            parser.error('--map-waypoints replaces the other navigation options')
        if not (args.relay and args.terrain and args.sustained_delivery):
            parser.error('--map-waypoints requires relay, terrain and sustained delivery')
        if args.target_ships > slots.target_limit(["buoys"]):
            parser.error(f'--map-waypoints reserves {slots.reservation("buoys")}; '
                         f'at most {slots.target_limit(["buoys"])} target ships')
        if not args.map_waypoints.is_file():
            parser.error(f'--map-waypoints: no file {args.map_waypoints}')
    if args.powerup_zones is not None and not args.powerup_zones.is_file():
        parser.error(f"--powerup-zones: no file {args.powerup_zones}")
    if args.spawn_at is not None:
        if not all(math.isfinite(v) and abs(v) <= 1e7 for v in args.spawn_at):
            parser.error("--spawn-at coordinates must be finite and within 1e7")
        args.spawn_origin = tuple(args.spawn_at)
    else:
        args.spawn_origin = registry.spawn(args.map) if args.terrain else None
    if args.tcp is None and args.profile in LOOPBACK_PROFILES + DOGFIGHT_PROFILES:
        args.tcp = PORTS["tcp"]
    try:
        bind = ipaddress.IPv4Address(args.bind_address)
    except ipaddress.AddressValueError:
        parser.error("--bind-address must be a literal IPv4 address")
    if args.profile in DOGFIGHT_PROFILES:
        networks = PRIVATE_NETWORKS + (VPN_NETWORKS if args.profile == "vpn-dogfight" else ())
        if not any(bind in ipaddress.IPv4Network(network) for network in networks):
            parser.error(f"{args.profile} requires a specific IPv4 address on this host in " + ", ".join(networks))
        if not (args.ack and args.arena and args.relay) or args.experimental_flight:
            parser.error(f"{args.profile} requires replies, arena and relay; standalone flight is unsupported")
        if args.experimental_reliable_combat or args.experimental_protection_probe or args.experimental_object or args.experimental_teams:
            parser.error(f"{args.profile} does not enable experimental combat delivery, protection, objects or teams")
        if args.max_players > DOGFIGHT_MAX_PLAYERS:
            parser.error(f"{args.profile} supports at most eight configured players; tested capacity may be lower")
    elif not bind.is_loopback:
        parser.error("diagnostic/local profiles require IPv4 loopback; use lan-dogfight or vpn-dogfight")
    if any(port is not None and not 0 <= port <= 65535 for port in (args.port, args.arena_port, args.tcp)):
        parser.error("ports must be 0..65535 (0 selects an ephemeral test port)")
    if args.arena and args.port != 0 and args.port == args.arena_port:
        parser.error("Station and arena UDP ports must differ")
    if not math.isfinite(args.seconds) or args.seconds < 0:
        parser.error("--seconds must be finite and nonnegative")
    if not math.isfinite(args.peer_timeout) or args.peer_timeout <= 0:
        parser.error("--peer-timeout must be finite and positive")
    if not math.isfinite(args.spawn_spacing) or not 0 < args.spawn_spacing <= 100000:
        parser.error("--spawn-spacing must be finite, positive and at most 100000")
    if not 0 <= args.kill_limit <= 1000 or not math.isfinite(args.time_limit) or not 0 <= args.time_limit <= 86400:
        parser.error("--kill-limit must be 0..1000 and --time-limit 0..86400 seconds")
    if not 1 <= args.max_players <= ARENA_JOINS:
        parser.error(f"--max-players must be 1..{ARENA_JOINS}")
    if not math.isfinite(args.restart_warning) or not 0 <= args.restart_warning <= 300:
        parser.error("--restart-warning must be 0..300 seconds")
    if not math.isfinite(args.idle_recycle) or not 0 <= args.idle_recycle <= 86400:
        parser.error("--idle-recycle must be 0..86400 seconds")
    if not 1 <= args.recycle_arena_joins < ARENA_JOINS or not 1 <= args.recycle_station_admissions < STATION_ADMISSIONS:
        parser.error("recycling thresholds must be below the 49 arena / 64 Station lifetime limits")
    if args.managed_session and not (args.relay and args.sustained_delivery and args.next_map):
        parser.error("--managed-session requires the relay, sustained delivery and --next-map")
    if args.experimental_flight or args.relay:
        if not args.arena or not args.ack:
            parser.error("experimental flight and the relay require --arena and --ack")
    if args.experimental_teams and not args.relay:
        parser.error("experimental teams requires the relay")
    if args.experimental_reliable_combat and not args.relay:
        parser.error("reliable combat requires the relay")
    if args.sustained_delivery and (not args.relay or args.experimental_reliable_combat
                                    or args.experimental_protection_probe):
        parser.error("sustained delivery requires the relay and replaces the 30-event reliable experiments")
    if not math.isfinite(args.reorder_margin) or not 0.5 <= args.reorder_margin <= 30:
        parser.error("--reorder-margin must be 0.5..30 seconds")
    for name in ("impair_rtt_ms", "impair_jitter_ms"):
        if not math.isfinite(getattr(args, name)) or not 0 <= getattr(args, name) <= 5000:
            parser.error(f"--{name.replace('_', '-')} must be 0..5000")
    for name in ("impair_loss", "impair_duplicate"):
        if not math.isfinite(getattr(args, name)) or not 0 <= getattr(args, name) <= 50:
            parser.error(f"--{name.replace('_', '-')} must be 0..50 percent")
    if args.experimental_protection_probe and (
            not args.experimental_flight or args.relay or args.max_players != 1):
        parser.error("protection probe requires --experimental-flight --max-players 1 and no relay")
    if args.experimental_object and not (args.experimental_flight or args.relay):
        parser.error("experimental object requires flight or relay")
    if args.log_max_bytes < 16384 or not 1 <= args.log_backups <= 10:
        parser.error("logs require at least 16384 bytes per file and 1..10 backups")
    try:
        pilot = args.pilot.encode("ascii")
    except UnicodeEncodeError:
        parser.error("pilot must be ASCII")
    if not pilot or len(pilot) > 19 or b"\0" in pilot:
        parser.error("pilot must contain 1..19 non-NUL ASCII characters")
    return args


class EventLog:
    """Nonblocking producers, bounded queue/records, one rotating file writer.

    Default allowlist excludes addresses, login fields, names and payloads.
    Raw mode is an explicit diagnostic capture, never a production setting.
    """
    METADATA = ("t", "event", "udp_port", "tcp_port", "wire_len", "type", "crc_ok",
                "len", "job", "status", "bytes_sent", "slot", "reason", "map", "next_map", "restart_in_s")
    MAX_RECORD = 16000

    def __init__(self, path, raw=False, max_bytes=1024 * 1024, backups=3, queue_size=1024):
        if max_bytes < 16384 or not 1 <= backups <= 10:
            raise ValueError("invalid rotation bounds")
        self.path = Path(path)
        self.raw, self.max_bytes, self.backups = raw, max_bytes, backups
        self.queue = queue.Queue(maxsize=queue_size)
        self.stop = threading.Event()
        self.dropped = 0
        self.failed = False
        self.lock = threading.Lock()
        self.counts = Counter()
        self.thread = threading.Thread(target=self._run, name="station-log", daemon=True)

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Surface output-path failures before starting networking.
        with self.path.open("ab"):
            pass
        self.thread.start()
        return self

    def __call__(self, record):
        with self.lock:
            event = record.get("event")
            if event in ("udp_packet", "tcp_job", "arena_departure", "station_departure", "admission_rejected"):
                self.counts[event] += 1
            if event == "udp_packet" and record.get("crc_ok") is False:
                self.counts["invalid_udp"] += 1
        data = dict(record) if self.raw else {key: record[key] for key in self.METADATA if key in record}
        line = (json.dumps(data, ensure_ascii=True) + "\n").encode("utf-8")
        if len(line) > self.MAX_RECORD:
            data = {key: record[key] for key in self.METADATA if key in record}
            data["raw_omitted"] = "record exceeds capture limit"
            line = (json.dumps(data) + "\n").encode("utf-8")
        if len(line) > self.MAX_RECORD:
            line = b'{"event":"oversized_log_record"}\n'
        try:
            self.queue.put_nowait(line)
        except queue.Full:
            with self.lock:
                self.dropped += 1

    def _write(self, line):
        if self.path.stat().st_size + len(line) > self.max_bytes:
            oldest = Path(str(self.path) + f".{self.backups}")
            oldest.unlink(missing_ok=True)
            for index in range(self.backups - 1, 0, -1):
                source = Path(str(self.path) + f".{index}")
                if source.exists():
                    source.replace(Path(str(self.path) + f".{index + 1}"))
            self.path.replace(Path(str(self.path) + ".1"))
        with self.path.open("ab") as stream:
            stream.write(line)

    def _run(self):
        try:
            while not self.stop.is_set() or not self.queue.empty():
                try:
                    line = self.queue.get(timeout=0.1)
                except queue.Empty:
                    continue
                self._write(line)
        except OSError:
            self.failed = True

    def __exit__(self, *_):
        self.stop.set()
        self.thread.join(timeout=5)
        if self.thread.is_alive():
            self.failed = True
        print(f"log summary: dropped={self.dropped} writer_failed={self.failed} events={dict(self.counts)}", flush=True)


class StationTCPServer:
    """Bounded independent event loop for the legacy 142-byte list requests.

    The 2.9.2 client reuses its data connection for later jobs ("already
    connected"). If the server closes it, the client's ShutdownTCPBySocket
    (0x4366F0) leaves its TCP queue mutex (0x5E6700) set, and the next job
    queued during a transfer spins forever on the UI thread. So a connection
    stays open across jobs while the Station session that its last request
    resolved to is alive. Each request still has a TIMEOUT from its first
    byte, and a connection that has not resolved a session closes after one
    reply or TIMEOUT.
    """
    MAX_CLIENTS = 64  # Station admission capacity; sessions may each hold one.
    TIMEOUT = 3.0

    def __init__(self, port, log, reply, responder, notifications, session_alive=None, *, bind_address="127.0.0.1"):
        """responder(request, peer) -> (reply, notification, identity|None)."""
        self.log, self.reply, self.responder, self.notifications = log, reply, responder, notifications
        self.session_alive = session_alive or (lambda identity: False)
        self.stop = threading.Event()
        self.listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            # Fresh Linux sessions must rebind while old TCP connections are
            # in TIME_WAIT. Do not enable Winsock's different reuse semantics.
            if os.name == "posix":
                self.listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.listener.bind((bind_address, port))
            self.listener.listen(8)
            self.listener.setblocking(False)
        except BaseException:
            self.listener.close()
            raise
        self.port = self.listener.getsockname()[1]
        self.thread = threading.Thread(target=self._run, name="station-tcp", daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def _run(self):
        clients = {}
        with selectors.DefaultSelector() as selector:
            selector.register(self.listener, selectors.EVENT_READ)

            def record(state, status):
                data = bytes(state["data"])
                self.log({"t": round(time.time(), 3), "event": "tcp_job", "tcp_port": self.port,
                          "from": state["address"], "len": len(data), "status": status,
                          "job": state.get("job"), "bytes_sent": state["sent"], "payload": data.hex()})

            def close(client, status):
                state = clients.pop(client)
                selector.unregister(client)
                client.close()
                # An idle kept-alive connection has nothing new to report
                # except why it ended.
                if state["data"] or state["sent"] or not state["jobs"]:
                    record(state, status)
                else:
                    self.log({"t": round(time.time(), 3), "event": "tcp_close", "tcp_port": self.port,
                              "status": status, "job": state.get("job")})

            try:
                while not self.stop.is_set():
                    for event, mask in selector.select(0.1):
                        client = event.fileobj
                        if client is self.listener:
                            try:
                                client, address = self.listener.accept()
                            except OSError:
                                continue
                            if len(clients) >= self.MAX_CLIENTS:
                                client.close()
                                continue
                            client.setblocking(False)
                            clients[client] = {"data": bytearray(), "address": f"{address[0]}:{address[1]}",
                                               "peer": address, "identity": None, "jobs": 0,
                                               "deadline": time.monotonic() + self.TIMEOUT, "sent": 0}
                            selector.register(client, selectors.EVENT_READ)
                            continue
                        state = clients[client]
                        try:
                            if mask & selectors.EVENT_READ:
                                chunk = client.recv(142 - len(state["data"]))
                                if not chunk:
                                    close(client, "truncated" if state["data"] or not state["jobs"] else "client_closed")
                                    continue
                                if not state["data"]:
                                    # Each request on a kept connection gets its own bound.
                                    state["deadline"] = time.monotonic() + self.TIMEOUT
                                state["data"].extend(chunk)
                                if len(state["data"]) == 142:
                                    state["job"] = state["data"][128]
                                    if not self.reply:
                                        close(client, "observed")
                                        continue
                                    state["output"], state["notification"], state["identity"] = self.responder(
                                        bytes(state["data"]), state["peer"])
                                    selector.modify(client, selectors.EVENT_WRITE)
                            if mask & selectors.EVENT_WRITE:
                                sent = client.send(state["output"][state["sent"]:])
                                if sent == 0:
                                    close(client, "disconnected")
                                    continue
                                state["sent"] += sent
                                if state["sent"] == len(state["output"]):
                                    if state["notification"] is not None:
                                        try:
                                            self.notifications.put_nowait(state["notification"])
                                        except queue.Full:
                                            pass
                                    state["jobs"] += 1
                                    if state["identity"] is None:
                                        close(client, "complete")
                                        continue
                                    record(state, "complete")
                                    state["data"], state["sent"], state["deadline"] = bytearray(), 0, None
                                    selector.modify(client, selectors.EVENT_READ)
                        except BlockingIOError:
                            continue
                        except OSError:
                            close(client, "disconnected")
                    now = time.monotonic()
                    for client, state in list(clients.items()):
                        if state["deadline"] is not None and now >= state["deadline"]:
                            close(client, "timeout")
                        elif state["deadline"] is None and not self.session_alive(state["identity"]):
                            close(client, "session_ended")
            finally:
                for client in list(clients):
                    close(client, "shutdown")
                self.listener.close()

    def __exit__(self, *_):
        self.stop.set()
        self.thread.join(timeout=5)
        if self.thread.is_alive():
            raise RuntimeError("Station TCP worker did not stop")
