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

import online_terrain

DOGFIGHT_PROFILES = ("lan-dogfight", "vpn-dogfight")
PRIVATE_NETWORKS = ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")
# Tailscale and other overlay networks assign addresses from the shared
# CGNAT range. Binding one requires it to be this host's own interface.
VPN_NETWORKS = ("100.64.0.0/10",)


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


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="AoA local diagnostics and private LAN/VPN dogfight relay")
    parser.add_argument("key", type=Path, help="256-byte SCRTY.BIN")
    parser.add_argument("log", type=Path, help="rotating JSONL output")
    parser.add_argument("--profile", choices=("diagnostic", "local-relay", "local-guests") + DOGFIGHT_PROFILES,
                        default="diagnostic")
    parser.add_argument("--bind-address", default="127.0.0.1",
                        help="specific local IPv4; LAN profile requires RFC1918, VPN profile also 100.64.0.0/10")
    parser.add_argument("--advertised-address", help="arena IPv4; defaults to bind address and must match it")
    parser.add_argument("--map", choices=online_terrain.MAP_NAMES, default="CTF_arena",
                        help="advertised terrain; with --experimental-terrain, the map a patched client loads")
    parser.add_argument("--backdrop", choices=("spacebkgd", "spacebkgd2", "spacebkgd3", "spacebkgd5", "spacebkgd6"),
                        default="spacebkgd3")
    parser.add_argument("--port", type=int, default=5033)
    parser.add_argument("--arena-port", type=int, default=5031)
    parser.add_argument("--tcp", type=int, default=None)
    for flag in ("ack", "arena", "experimental-flight", "experimental-relay", "experimental-object", "experimental-teams"):
        parser.add_argument("--" + flag, action=argparse.BooleanOptionalAction, default=None)
    parser.add_argument("--pilot", default="testpilot")
    parser.add_argument("--seconds", type=float, default=0)
    parser.add_argument("--peer-timeout", type=float, default=30)
    parser.add_argument("--max-players", type=int, default=8, help="simultaneous arena admissions, 1..49")
    parser.add_argument("--spawn-axis", choices=("x", "z"), default="x",
                        help="diagnostic relay spawn line; ships initially face +z")
    parser.add_argument("--spawn-spacing", type=float, default=1000.0, help="distance between relay spawns")
    parser.add_argument("--kill-limit", type=int, default=20, help="relay match ends at this many kills; 0 disables")
    parser.add_argument("--time-limit", type=float, default=600.0, help="relay match length in seconds; 0 disables")
    parser.add_argument("--managed-session", action="store_true",
                        help="dedicated controller: warn, drain and exit 75 after a match or admission limit")
    parser.add_argument("--next-map", choices=online_terrain.MAP_NAMES,
                        help="next map announced by the dedicated controller")
    parser.add_argument("--restart-warning", type=float, default=30, help="managed restart countdown in seconds")
    parser.add_argument("--recycle-arena-joins", type=int, default=40)
    parser.add_argument("--recycle-station-admissions", type=int, default=56)
    parser.add_argument("--idle-recycle", type=float, default=300,
                        help="managed session: recycle used admissions after this long with no arena players")
    parser.add_argument("--raw-capture", action="store_true")
    parser.add_argument("--experimental-terrain", action="store_true",
                        help="native terrain for --map; requires the online-terrain-v2 (or later) client patch "
                             "(v1 clients load Arena1a only)")
    parser.add_argument("--spawn-at", type=float, nargs=3, metavar=("X", "Y", "Z"),
                        help="first relay spawn; defaults to the map's viewing spawn with terrain, else the origin")
    parser.add_argument("--powerup-zones", type=Path, metavar="TRN",
                        help="place power-ups in the kind-6 zones of this 2.9.2 terrain file "
                             "(e.g. game/2.9.2/jrmap292.trn); needs the relay")
    parser.add_argument("--target-ships", type=int, default=0, metavar="N",
                        help="N passive hostile ships ahead of the spawn that the target keys can select "
                             "(0..98); needs the relay")
    parser.add_argument("--arena1a-buoys", type=Path, metavar="GOB",
                        help="restore ten native navigation buoys from original Arena1a.Gob; requires Arena1a terrain and sustained delivery")
    parser.add_argument('--navigation-buoys', type=Path, metavar='EXPORT_DIR',
                        help='restore the selected map navigation objects from exported AOAOBJECTS, with original archive order')
    parser.add_argument('--buoy-trn', type=Path, help='original JRMAP.TRN for navigation; defaults beside SCRTY.BIN')
    parser.add_argument('--turret-trial', type=Path, metavar='EXPORT_DIR',
                        help='inactive five-turret Arena1a placement trial; model assignment is provisional and orientation is zero')
    parser.add_argument('--warp-trial', type=Path, metavar='EXPORT_DIR',
                        help='nine native Arena1a warp gates on loopback; local client transit, editor orientation not restored')
    parser.add_argument("--experimental-reliable-combat", action="store_true",
                        help="ordered combat delivery; retires peers at 30 total essential events")
    parser.add_argument("--experimental-protection-probe", action="store_true",
                        help="single-client explicit 0x81 probe; requires the opt-in prepared client")
    parser.add_argument("--sustained-delivery", action=argparse.BooleanOptionalAction, default=None,
                        help="windowed ordered delivery of despawns/combat events for a whole session "
                             "(default on for vpn-dogfight); see tools/reliable_window.py")
    parser.add_argument("--reorder-margin", type=float, default=3.0,
                        help="seconds a stale datagram may trail later ones (sustained delivery)")
    parser.add_argument("--status-file", type=Path, help="JSON host status, rewritten every two seconds")
    parser.add_argument("--console", action="store_true", help="read host commands (status, kick, ban) from stdin")
    parser.add_argument("--impair-rtt-ms", type=float, default=0.0, help="TEST ONLY: added round trip")
    parser.add_argument("--impair-jitter-ms", type=float, default=0.0, help="TEST ONLY: random extra delay per direction")
    parser.add_argument("--impair-loss", type=float, default=0.0, help="TEST ONLY: percent dropped per direction")
    parser.add_argument("--impair-duplicate", type=float, default=0.0, help="TEST ONLY: percent duplicated per direction")
    parser.add_argument("--impair-seed", type=int, help="TEST ONLY: repeatable impairment")
    parser.add_argument("--log-max-bytes", type=int, default=1024 * 1024)
    parser.add_argument("--log-backups", type=int, default=3)
    parser.add_argument("--print-config", action="store_true", help="validate and print settings without reading key or binding")
    args = parser.parse_args(argv)
    for flag in ("ack", "arena", "experimental_flight", "experimental_relay", "experimental_object", "experimental_teams"):
        if getattr(args, flag) is None:
            setattr(args, flag, args.profile in ("local-relay", "local-guests") + DOGFIGHT_PROFILES
                    and flag in ("ack", "arena", "experimental_relay"))
    args.guest_sessions = args.profile in ("local-guests",) + DOGFIGHT_PROFILES
    if args.sustained_delivery is None:
        args.sustained_delivery = args.profile == "vpn-dogfight"
    if args.experimental_terrain and not (
            args.profile in DOGFIGHT_PROFILES or
            args.profile in ("local-relay", "local-guests")):
        parser.error("experimental terrain requires a dogfight or loopback relay/guest profile")
    if args.powerup_zones is not None and not args.experimental_relay:
        parser.error("--powerup-zones requires the relay")
    if not 0 <= args.target_ships <= 98:
        parser.error("--target-ships must be 0..98")
    if args.target_ships and not args.experimental_relay:
        parser.error("--target-ships requires the relay")
    if args.warp_trial is not None:
        if not (args.profile in ('local-relay', 'local-guests') and args.experimental_relay
                and args.experimental_terrain and args.sustained_delivery and args.map == 'Arena1a'):
            parser.error('--warp-trial requires a loopback relay, Arena1a terrain and sustained delivery')
        if args.target_ships > 69:
            parser.error('--warp-trial reserves slots 71..79; at most 69 target ships')
        if not args.warp_trial.is_dir():
            parser.error('--warp-trial requires an original exported AOAOBJECTS directory')
    if args.turret_trial is not None:
        if not (args.experimental_relay and args.experimental_terrain and args.sustained_delivery and args.map == 'Arena1a'):
            parser.error('--turret-trial requires relay, Arena1a terrain and sustained delivery')
        if args.target_ships > 78:
            parser.error('--turret-trial reserves slots 80..84; at most 78 target ships')
        if not args.turret_trial.is_dir():
            parser.error('--turret-trial requires an original exported AOAOBJECTS directory')
    if args.arena1a_buoys is not None:
        if not (args.experimental_relay and args.experimental_terrain and args.map == 'Arena1a' and args.sustained_delivery):
            parser.error('--arena1a-buoys requires relay, Arena1a terrain and --sustained-delivery')
        if args.target_ships > 88:
            parser.error('--arena1a-buoys reserves object slots 90..99; at most 88 target ships')
        if not args.arena1a_buoys.is_file():
            parser.error('--arena1a-buoys requires an existing original layout file')
    if args.navigation_buoys is not None:
        if args.arena1a_buoys:
            parser.error('choose --navigation-buoys or the legacy --arena1a-buoys option')
        if not (args.experimental_relay and args.experimental_terrain and args.sustained_delivery):
            parser.error('--navigation-buoys requires relay, terrain and sustained delivery')
        if args.target_ships > 88:
            parser.error('--navigation-buoys reserves slots 90..99; at most 88 target ships')
        if not args.navigation_buoys.is_dir():
            parser.error('--navigation-buoys requires an exported AOAOBJECTS directory')
    if args.powerup_zones is not None and not args.powerup_zones.is_file():
        parser.error(f"--powerup-zones: no file {args.powerup_zones}")
    if args.spawn_at is not None:
        if not all(math.isfinite(v) and abs(v) <= 1e7 for v in args.spawn_at):
            parser.error("--spawn-at coordinates must be finite and within 1e7")
        args.spawn_origin = tuple(args.spawn_at)
    else:
        args.spawn_origin = online_terrain.spawn(args.map) if args.experimental_terrain else None
    if args.tcp is None and args.profile in ("local-relay", "local-guests") + DOGFIGHT_PROFILES:
        args.tcp = 5034
    args.advertised_address = args.advertised_address or args.bind_address
    try:
        bind = ipaddress.IPv4Address(args.bind_address)
        advertised = ipaddress.IPv4Address(args.advertised_address)
    except ipaddress.AddressValueError:
        parser.error("bind and advertised addresses must be literal IPv4 addresses")
    if bind != advertised:
        parser.error("advertised address must match the bound address")
    if args.profile in DOGFIGHT_PROFILES:
        networks = PRIVATE_NETWORKS + (VPN_NETWORKS if args.profile == "vpn-dogfight" else ())
        if not any(bind in ipaddress.IPv4Network(network) for network in networks):
            parser.error(f"{args.profile} requires a specific IPv4 address on this host in " + ", ".join(networks))
        if not (args.ack and args.arena and args.experimental_relay) or args.experimental_flight:
            parser.error(f"{args.profile} requires replies, arena and relay; standalone flight is unsupported")
        if args.experimental_reliable_combat or args.experimental_protection_probe or args.experimental_object or args.experimental_teams:
            parser.error(f"{args.profile} does not enable experimental combat delivery, protection, objects or teams")
        if args.max_players > 8:
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
    if not 1 <= args.max_players <= 49:
        parser.error("--max-players must be 1..49")
    if not math.isfinite(args.restart_warning) or not 0 <= args.restart_warning <= 300:
        parser.error("--restart-warning must be 0..300 seconds")
    if not math.isfinite(args.idle_recycle) or not 0 <= args.idle_recycle <= 86400:
        parser.error("--idle-recycle must be 0..86400 seconds")
    if not 1 <= args.recycle_arena_joins <= 48 or not 1 <= args.recycle_station_admissions <= 63:
        parser.error("recycling thresholds must be below the 49 arena / 64 Station lifetime limits")
    if args.managed_session and not (args.experimental_relay and args.sustained_delivery and args.next_map):
        parser.error("--managed-session requires the relay, sustained delivery and --next-map")
    if args.experimental_flight or args.experimental_relay:
        if not args.arena or not args.ack:
            parser.error("experimental flight/relay requires --arena and --ack")
    if args.experimental_teams and not args.experimental_relay:
        parser.error("experimental teams requires the relay")
    if args.experimental_reliable_combat and not args.experimental_relay:
        parser.error("reliable combat requires the relay")
    if args.sustained_delivery and (not args.experimental_relay or args.experimental_reliable_combat
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
            not args.experimental_flight or args.experimental_relay or args.max_players != 1):
        parser.error("protection probe requires --experimental-flight --max-players 1 and no relay")
    if args.experimental_object and not (args.experimental_flight or args.experimental_relay):
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
