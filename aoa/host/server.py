"""The stand-in Station and arena server for one host run: ArenaServer.

The command line is aoa/host/cli.py (tools/station_stub.py); the settings
are aoa/host/runtime.py. The message builders live in aoa/protocol/ and the
roles in aoa/host/ (sessions, delivery, combat, match, objects, spawn,
transport, console, vessels). The names below them are re-exported here for
the tests and the emulation checks that import them from this module.
"""
import json
import math
import queue
import secrets  # tests patch secrets.randbits through this module
import struct
import sys
import time

from aoa.formats import trn
from aoa.host import console, ops
from aoa.host.combat import DeathLedger, MissileLedger
from aoa.host.defaults import ARENA_JOINS, MODE_NAMES, SESSION_COMPLETE
from aoa.host.delivery import InboundReliable, ReliableRemovals, WindowedReliable
from aoa.host.match import Match
from aoa.host.net_impair import Impairment, TrafficMeter
from aoa.host.objects import load_objects
from aoa.host.objects.powerups import PowerUps
from aoa.host.objects.targets import TargetShips
from aoa.host.objects.test_object import scenario_test_object
from aoa.host.runtime import SELECTABLE_VESSELS, StationTCPServer
from aoa.host.sessions import StationSessions
from aoa.host.spawn import spawn_position
from aoa.host.transport import Transport
from aoa.host.vessels import flight_bootstrap, load_player, load_ship, ship_request
from aoa.maps import registry
from aoa.protocol import codec
from aoa.protocol import motion as protocol_motion
from aoa.protocol.arena import (arena_message, collision_target, ffa_team, object_to_team, player_tag,
                                remove_player)
from aoa.protocol.messages import NUL, TYPE_NAMES
from aoa.protocol.station import ack_connect, ack_reliable, arena_ping, pilot_list, udp_replies
from aoa.protocol.tcp_list import (TCP_JOB_BODIES, server_list_body, server_record,
                                   ship_config_list, tcp_reply)

__all__ = [  # re-exported for the tests and emulation checks; remove as they import the role modules
    "ArenaServer", "run", "SESSION_COMPLETE", "secrets", "NUL", "TYPE_NAMES",
    "ack_connect", "ack_reliable", "arena_ping", "pilot_list", "udp_replies",
    "arena_message", "collision_target", "ffa_team", "object_to_team", "player_tag", "remove_player",
    "flight_bootstrap", "load_player", "load_ship", "ship_request", "SELECTABLE_VESSELS",
    "TCP_JOB_BODIES", "server_list_body", "server_record", "ship_config_list", "tcp_reply",
    "StationSessions", "ReliableRemovals", "InboundReliable", "WindowedReliable", "DeathLedger",
    "MissileLedger", "PowerUps", "TargetShips", "Match", "spawn_position", "scenario_test_object",
    "load_objects"]


class ArenaServer:
    """One host run of the stand-in Station and arena server.

    `serve()` runs until --seconds elapse, the console quits, or a managed
    session completes (it then returns SESSION_COMPLETE).
    """

    def __init__(self, args, key, log, resources, objects=None):
        self.args, self.key, self.log, self.resources, self.objects = args, key, log, resources, objects
        self.arena = None
        self.warp_gates, self.warp, self.trial, self.buoys = load_objects(self.args) if self.objects is None else self.objects
        self.peer_timeout = self.args.peer_timeout
        self.reply, pilot = self.args.ack, self.args.pilot
        self.notifications = queue.Queue(maxsize=1024)
        self.station = StationSessions(self.peer_timeout, pilot, self.args.guest_sessions)
        self.meter = TrafficMeter()
        seed = self.args.impair_seed
        self.impair_in = Impairment(self.args.impair_rtt_ms, self.args.impair_jitter_ms, self.args.impair_loss, self.args.impair_duplicate, seed)
        self.impair_out = Impairment(self.args.impair_rtt_ms, self.args.impair_jitter_ms, self.args.impair_loss, self.args.impair_duplicate,
                                None if seed is None else seed + 1)
        if self.impair_in.active:
            print("TEST IMPAIRMENT ACTIVE (each direction): " + json.dumps(self.impair_out.describe()), flush=True)
            self.log({"t": round(time.time(), 3), "event": "impairment", "status": self.impair_out.describe()})
        self.transport = Transport(self.args, self.key, self.log, self.resources, self.meter,
                                   self.impair_in, self.impair_out)
        self.s, self.arena, self.sockets = self.transport.station, self.transport.arena, self.transport.sockets
        self.mode = "Local Relay" if self.args.relay else ("Local Flight" if self.args.experimental_flight else "Handshake Test")
        self.mode = MODE_NAMES.get(self.args.profile, self.mode)
        hosted_port = self.arena.getsockname()[1] if self.args.arena and self.reply else None
        self.job_bodies = {4: TCP_JOB_BODIES[4], 14: TCP_JOB_BODIES[14], 5: server_list_body(0, hosted_port, self.mode,
                                                             address=self.args.bind_address,
                                                             terrain=self.args.map, backdrop=self.args.backdrop)}

        if self.args.tcp is not None:
            tcp = self.resources.enter_context(StationTCPServer(self.args.tcp, self.log, self.reply,
                self.station_tcp_response, self.notifications, self.session_alive, bind_address=self.args.bind_address))
            print(f"Station TCP on {self.args.bind_address}:{tcp.port}", flush=True)
        self.bootstrap_due = {}
        self.arena_players = {}
        self.arena_connections = {}
        self.arena_pilots = {}
        self.arena_vessels = {}  # addr -> vessel chosen in the fighter menu
        self.start_vessel = self.args.start_vessel
        if self.start_vessel not in SELECTABLE_VESSELS:
            raise ValueError(f"unknown --start-vessel {self.start_vessel!r}")
        self.arena_reported = {}  # addr -> (rating, score) from the client's own stats
        self.arena_motion = {}
        self.ping_due = {}
        self.expiry_due = {}
        self.ping_ticks = {}
        self.next_player_slot = 1
        self.retired_endpoints = set()
        self.protection_probe = {}  # peer -> (next due, index in explicit 1,1,0,0 probe)
        if self.args.sustained_delivery:
            self.removals = WindowedReliable(deadline=self.peer_timeout, margin=self.args.reorder_margin)
            self.resources.callback(lambda: print(f"sustained delivery: expired_events={self.removals.expired} "
                                             f"window_waits={self.removals.window_waits}", flush=True))
        else:
            self.removals = ReliableRemovals(deadline=self.peer_timeout,
                                       ordered=self.args.experimental_reliable_combat or self.args.experimental_protection_probe)
        self.resources.callback(lambda: print("traffic: " + json.dumps(dict(self.meter.totals(), dropped_in=self.meter.dropped_in,
                                                                       dropped_out=self.meter.dropped_out)), flush=True))
        self.deaths = DeathLedger()
        self.targets = TargetShips(self.args.target_ships, self.args.spawn_origin) if self.args.target_ships else None
        if self.buoys:
            print(f'{self.args.map} navigation buoys: {len(self.buoys)}', flush=True)
        if self.targets is not None:
            print(f"target ships: {len(self.targets.ships)}", flush=True)
        self.missiles = MissileLedger(map(TargetShips.tag, self.targets.ships) if self.targets is not None else ())
        self.powerups = None
        if self.args.powerup_zones is not None:
            self.powerups = PowerUps(trn.powerup_zones_292(self.args.powerup_zones.read_bytes()))
            print(f"power-ups: {len(self.powerups.items)} from {self.args.powerup_zones.name}", flush=True)
        self.match = Match(self.args.kill_limit, self.args.time_limit)
        self.resources.callback(lambda: print("kills=" + json.dumps(self.deaths.kills) + " deaths=" + json.dumps(self.deaths.deaths),
                                         flush=True))
        self.motion_refresh_due = time.monotonic() + 1
        self.arena_heard = {}   # addr -> last valid arena datagram (monotonic)
        self.arena_rtt = {}     # addr -> smoothed ping round trip, ms
        self.banned_ips = set()
        self.started = time.monotonic()
        self.status_due = self.started
        self.traffic_mark = {}  # addr -> (time, rx_bytes, tx_bytes) at the previous status
        self.console = ops.Console(sys.stdin) if self.args.console else None
        self.REJOIN_SILENCE = 5.0
        self.overflowed = set()  # peers whose reliable queue overflowed, departed next pass
        self.restart_reason, self.restart_due = None, None
        self.restart_notices = set()
        self.idle_since = self.started
        self.quit_requested = False

        self.refresh_server_list()

    def station_tcp_response(self, request, address):
        identity = self.station.resolve(request, address, time.monotonic())
        if identity is None:
            return bytes(4), None, None
        job = request[128]
        return tcp_reply(job, self.job_bodies), identity if job == 5 else None, identity

    def session_alive(self, identity):
        route = self.station.routes.get(identity)  # Immutable snapshot; TCP thread.
        return route is not None and time.monotonic() < route[1]

    def announce_restart(self, now):
        remaining = max(0, math.ceil(self.restart_due - now))
        text = f"Next map {self.args.next_map} in {remaining}s. Quit and relaunch to rejoin."
        for peer in list(self.ping_due):
            self.deliver(peer, arena_message(text))

    def schedule_restart(self, reason, now):
        if self.restart_due is not None:
            return
        self.restart_reason, self.restart_due = reason, now + self.args.restart_warning
        self.log({"t": round(time.time(), 3), "event": "session_restart_scheduled", "reason": reason,
             "map": self.args.map, "next_map": self.args.next_map, "restart_in_s": self.args.restart_warning})
        print(f"Session ending ({reason}); next map {self.args.next_map} in {self.args.restart_warning:g}s", flush=True)
        self.refresh_server_list()
        self.announce_restart(now)

    def player_stats(self, addr):
        """(kills, deaths, rating, score): server counts, client-reported rest."""
        slot = self.arena_players.get(addr)
        rating, score = self.arena_reported.get(addr, (0, 0))
        return self.deaths.kills.get(slot, 0), self.deaths.deaths.get(slot, 0), rating, score

    def own_record(self, addr):
        """0x42 for a player's own HUD (0x4AFC00 -> 0x49DB20 copies 350 bytes).

        Its own handshake record with the server's kills (+0x7F) and deaths
        (+0x83) and its last reported score (+0x4E). Never sent to anyone else:
        the record is the client's login block.
        """
        kills, died, _, score = self.player_stats(addr)
        record = bytearray(self.arena_connections[addr][31:381])
        struct.pack_into("<i", record, 0x4E, score)
        struct.pack_into("<i", record, 0x7F, kills)
        struct.pack_into("<i", record, 0x83, died)
        return 0x42, struct.pack("<I", player_tag(self.arena_players[addr])) + bytes(record)

    def change_vessel(self, addr, payload):
        """Answer the fighter menu's 0xA0 request (findings 9.40).

        The pilot and every loaded observer get 0x27 for the new hull; late
        joiners get it in the player record. The original server path moves a
        ship that changes outside a safe zone to a random point (0x4A4310), so
        the relay sends it back to its spawn, as after a death: a swap is not
        a free escape or repair.
        """
        vessel = ship_request(payload)
        slot = self.arena_players[addr]
        self.log({"t": round(time.time(), 3), "event": "ship_change", "slot": slot, "status": vessel or "rejected"})
        if vessel is None:
            return
        self.arena_vessels[addr] = vessel
        self.deliver(addr, load_ship(vessel), True)
        for peer in self.ping_due:
            if peer != addr:
                self.deliver(peer, load_ship(vessel, slot), True)
        spawn = spawn_position(slot, self.args.spawn_axis, self.args.spawn_spacing, self.args.spawn_origin)
        self.deliver(addr, (0x24, struct.pack("<3f", *spawn)))

    def end_match(self, reason, now):
        """Announce the result, reset the scoreboard and start the next match."""
        if self.restart_due is not None:
            return
        loaded = {self.arena_players[peer]: peer for peer in self.ping_due if peer in self.arena_players}
        names = {slot: self.arena_pilots.get(peer) or f"LocalPilot{slot}" for slot, peer in loaded.items()}
        text = f"{self.match.result(self.deaths.kills, names)} ({reason})"
        self.log({"t": round(time.time(), 3), "event": "match_end", "reason": reason})
        if self.args.managed_session:
            for peer in loaded.values():
                self.deliver(peer, arena_message(text))
            self.schedule_restart(reason, now)
            return  # Keep the final scoreboard until the session closes.
        self.deaths.kills.clear()
        self.deaths.deaths.clear()
        self.match.next(now)
        for peer in loaded.values():
            self.deliver(peer, arena_message(text))
            self.deliver(peer, arena_message(f"Match {self.match.number} started"))
            self.deliver(peer, self.own_record(peer))

    def refresh_server_list(self):
        hosted_port = self.arena.getsockname()[1] if self.args.arena and self.reply else None
        available = (self.restart_due is None and len(self.arena_connections) < self.args.max_players and
                     len(self.arena_connections) + len(self.retired_endpoints) < ARENA_JOINS)
        self.job_bodies[5] = server_list_body(len(self.arena_connections), hosted_port, self.mode, available, len(self.station.peers),
                                       self.args.bind_address, self.args.map, self.args.backdrop)

    def combat_send(self, peer, packet):
        if peer not in self.arena_connections:
            return
        if self.args.sustained_delivery:
            packet = self.removals.queue_message(peer, *packet, time.monotonic(), essential=False)
            if packet is None:
                self.depart(peer, "reliable event queue overflow")
                return
        elif self.args.experimental_reliable_combat:
            packet = self.removals.queue_message(peer, *packet, time.monotonic())
            if packet is None:
                self.depart(peer, "essential event history exhausted")
                return
        if packet:
            self.arena.sendto(codec.encode(*packet, self.key), peer)

    def destroy_targets(self, destroyed, shooter):
        """Announce target ships the server destroyed to every loaded player."""
        for index, packet in destroyed:
            self.log({"t": round(time.time(), 3), "event": "target_destroyed", "ship": index, "slot": shooter})
            for peer in self.arena_players:
                if peer not in self.bootstrap_due:
                    self.combat_send(peer, packet)

    def deliver(self, peer, packet, essential=False):
        """Session state: reliable and ordered with sustained delivery.

        The 2.9.2 receive loop unwraps 0x1B in place and joins the plain
        path at 0x486464 with the inner type, so any message type can be
        wrapped. Without sustained delivery this stays best effort.
        """
        if not self.args.sustained_delivery:
            self.arena.sendto(codec.encode(*packet, self.key), peer)
            return
        if peer not in self.arena_connections:
            return
        queued = self.removals.queue_message(peer, *packet, time.monotonic(), essential=essential)
        if queued is None:
            self.overflowed.add(peer)  # Callers may be iterating arena state.
        elif queued:
            self.arena.sendto(codec.encode(*queued, self.key), peer)

    def station_depart(self, peer, reason):
        arena_peer = self.station.peers.get(peer, {}).get("arena")
        if self.station.depart(peer):
            if arena_peer is not None:
                self.depart(arena_peer, "Station session ended")
            self.refresh_server_list()
            self.log({"t": round(time.time(), 3), "event": "station_departure", "reason": reason})

    def depart(self, peer, reason):
        if peer not in self.arena_connections:
            return
        # Clear every arena-owned timer/baseline before notifying observers.
        loaded = peer in self.ping_due
        self.retired_endpoints.add(peer)
        slot = self.arena_players.pop(peer, None)
        self.removals.discard(peer)
        if slot is not None:
            self.missiles.discard(slot)
        for state in (self.arena_connections, self.arena_pilots, self.arena_vessels, self.arena_motion, self.arena_reported, self.bootstrap_due,
                      self.ping_due,
                      self.expiry_due, self.ping_ticks, self.protection_probe, self.arena_heard, self.arena_rtt, self.traffic_mark):
            state.pop(peer, None)
        self.station.release_arena(peer, time.monotonic())
        if loaded and slot is not None:
            failed = []
            for observer in list(self.ping_due):
                packet = self.removals.queue(observer, slot, time.monotonic())
                if packet is None:
                    failed.append(observer)
                elif packet:
                    self.arena.sendto(codec.encode(*packet, self.key), observer)
            for observer in failed:
                self.depart(observer, "reliable removal history exhausted")
        self.refresh_server_list()
        self.log({"t": round(time.time(), 3), "event": "arena_departure", "slot": slot, "reason": reason})

    def serve(self):
        print(f"station stub on {self.args.bind_address}:{self.s.getsockname()[1]} (replies {'ON' if self.reply else 'off'})", flush=True)
        if self.console is not None:
            print("Host console ready. " + ops.HELP, flush=True)
        end = time.monotonic() + self.args.seconds if self.args.seconds else None
        while end is None or time.monotonic() < end:
            now = time.monotonic()
            code = self.tick(now)
            if code is not None:
                return code
            if self.quit_requested:
                end = now  # leave the loop; ExitStack cleanup still runs
            self.receive()

    def tick(self, now):
        """Housekeeping before each receive; SESSION_COMPLETE ends a managed session."""
        if self.args.managed_session and self.managed_tick(now):
            return SESSION_COMPLETE
        self.transport.flush(now)
        for peer in list(self.overflowed):
            self.depart(peer, "reliable event queue overflow")
        self.overflowed.clear()
        if self.console is not None:
            for line in self.console.drain():
                response = console.command(self, line, now)
                if response:
                    print(response, flush=True)
                if response == ops.QUIT:
                    self.quit_requested = True
        if self.args.status_file is not None and now >= self.status_due:
            try:
                ops.write_status(self.args.status_file, console.status(self, now))
            except OSError as error:
                print(f"status file not written: {error}", flush=True)
            self.status_due = now + 2
        for peer, state in list(self.station.peers.items()):
            if now >= state["expiry"]:
                self.station_depart(peer, "inactivity timeout")
        for peer, packet in self.station.pings(now):
            self.s.sendto(codec.encode(*packet, self.key), peer)
        retries, failed = self.removals.due(time.monotonic())
        for peer in failed:
            self.depart(peer, "essential event unacknowledged")
        for peer, packet in retries:
            if peer in self.arena_connections:
                self.arena.sendto(codec.encode(*packet, self.key), peer)
        self.probe_tick(now)
        for peer, due in list(self.expiry_due.items()):
            if time.monotonic() >= due:
                self.depart(peer, "inactivity timeout")
        if self.args.relay:
            if not self.arena_players:
                self.match.stop()
            elif self.match.started is not None:
                reason = self.match.ended(self.deaths.kills, now)
                if reason:
                    self.end_match(reason, now)
        if self.args.relay and now >= self.motion_refresh_due:
            for subject, state in self.arena_motion.items():
                if subject not in self.ping_due:
                    continue
                packet = codec.encode(0x1F, protocol_motion.snapshot(self.arena_players[subject], state,
                                                                    stats=self.player_stats(subject)), self.key)
                for observer in self.ping_due:
                    if observer != subject:
                        self.arena.sendto(packet, observer)
            self.motion_refresh_due = now + 1
        for peer, due in list(self.bootstrap_due.items()):
            if time.monotonic() >= due:
                self.bootstrap(peer)
        if self.targets is not None:
            for packet in self.targets.respawns(time.monotonic()):
                for peer in self.arena_players:
                    if peer not in self.bootstrap_due:
                        self.deliver(peer, packet, True)
        for peer, due in list(self.ping_due.items()):
            now = time.monotonic()
            if now >= due:
                rtype, rpay = arena_ping(int(now * 1000))
                ticks = self.ping_ticks.setdefault(peer, [])
                ticks.append(rpay[:4])
                del ticks[:-4]
                self.arena.sendto(codec.encode(rtype, rpay, self.key), peer)
                self.ping_due[peer] = now + 1
        # BeginSerialLoad precedes Station dialog initialization. Wait until
        # its first server-list TCP job so the alias observer is registered.
        # This delivery timing is experimental, not a recovered server rule.
        # Bound each drain even if the TCP producer keeps replenishing it.
        for _ in range(self.notifications.qsize()):
            identity = self.notifications.get_nowait()
            peer = self.station.alias_target(identity, time.monotonic())
            if peer is not None:
                self.s.sendto(codec.encode(0x9A, pilot_list(self.station.peers[peer]["pilot"]), self.key), peer)
        return None

    def managed_tick(self, now):
        """Recycling and the restart countdown; True when the session is complete."""
        if self.arena_connections:
            self.idle_since = now
        if self.next_player_slot - 1 >= self.args.recycle_arena_joins:
            self.schedule_restart("arena admission threshold", now)
        elif self.station.next_id - 1 >= self.args.recycle_station_admissions:
            self.schedule_restart("Station admission threshold", now)
        elif (self.args.idle_recycle and not self.arena_connections and self.station.next_id > 1
              and now - self.idle_since >= self.args.idle_recycle):
            self.schedule_restart("idle session cleanup", now)
        if self.restart_due is not None:
            if now >= self.restart_due:
                self.log({"t": round(time.time(), 3), "event": "session_restart", "reason": self.restart_reason,
                     "map": self.args.map, "next_map": self.args.next_map})
                if self.args.status_file is not None:
                    ops.write_status(self.args.status_file, console.status(self, now))
                return True
            for threshold in (10, 5):
                if threshold < self.args.restart_warning and self.restart_due - now <= threshold and threshold not in self.restart_notices:
                    self.restart_notices.add(threshold)
                    self.announce_restart(now)
        return False

    def probe_tick(self, now):
        for peer, (due, step) in list(self.protection_probe.items()):
            if now < due or any(p == peer for p, _ in self.removals.pending):
                continue
            desired = (1, 1, 0, 0)[step]
            packet = self.removals.queue_message(peer, 0x81, bytes([desired]), now)
            if packet is None:
                self.depart(peer, "protection probe delivery exhausted")
                continue
            if packet:
                self.arena.sendto(codec.encode(*packet, self.key), peer)
            self.log({"t": round(time.time(), 3), "event": "protection_probe_step", "status": desired})
            print(f"Protection probe {step + 1}/4: state={desired}", flush=True)
            if step == 3:
                del self.protection_probe[peer]
            else:
                self.protection_probe[peer] = (now + 3, step + 1)

    def bootstrap(self, peer):
        """Flight entry three seconds after admission: players, ship, terrain and map objects."""
        if self.args.relay:
            for other, slot in self.arena_players.items():
                if other != peer and other in self.bootstrap_due:
                    continue
                # Its own record replaces the client's (0x4A641C): keep
                # the Station ID that its TCP requests carry (9.40).
                own_id = struct.unpack_from("<I", self.arena_connections[peer], 0x1F + 0x7B)[0]
                self.deliver(peer, load_player(slot, self.arena_motion[other][0x40], self.arena_pilots.get(other),
                                          ffa_team(slot) if self.args.experimental_teams else None,
                                          self.arena_vessels.get(other, self.start_vessel),
                                          own_id if other == peer else None), True)
                if other != peer:
                    self.deliver(other, load_player(self.arena_players[peer], self.arena_motion[peer][0x40],
                                               self.arena_pilots.get(peer),
                                               ffa_team(self.arena_players[peer]) if self.args.experimental_teams
                                               else None, self.arena_vessels.get(peer, self.start_vessel)), True)
            for other, slot in self.arena_players.items():
                if other != peer and other not in self.bootstrap_due:
                    self.arena.sendto(codec.encode(0x1F, protocol_motion.snapshot(
                        slot, self.arena_motion[other], stats=self.player_stats(other)), self.key), peer)
        position = self.arena_motion[peer][0x40] if peer in self.arena_motion else None
        for packet in flight_bootstrap(position, registry.marker(self.args.map)
                                       if self.args.terrain else None,
                                       self.arena_vessels.get(peer, self.start_vessel)):
            self.deliver(peer, packet, True)
        if self.args.experimental_teams:
            slot = self.arena_players[peer]
            self.arena.sendto(codec.encode(*object_to_team(player_tag(slot), ffa_team(slot)), self.key), peer)
        if self.args.experimental_object:
            rtype, rpay = scenario_test_object()
            self.arena.sendto(codec.encode(rtype, rpay, self.key), peer)
        if self.powerups is not None:
            for packet in self.powerups.spawns():
                self.deliver(peer, packet, True)
        if self.targets is not None:
            for packet in self.targets.loads():
                self.deliver(peer, packet, True)
        for packet in self.buoys:
            self.deliver(peer, packet, True)
        for packet in self.trial:
            self.deliver(peer, packet, True)
        for packet in self.warp:
            self.deliver(peer, packet, True)
        del self.bootstrap_due[peer]
        self.ping_due[peer] = time.monotonic()
        if self.args.experimental_protection_probe:
            self.protection_probe[peer] = (time.monotonic() + 3, 0)
        if self.args.relay:
            self.match.start(time.monotonic())

    def receive(self):
        """Handle at most one datagram; waits up to 0.5 s or until the next due retry."""
        datagram = self.transport.receive(self.banned_ips, getattr(self.removals, "next_due", lambda: None)())
        if datagram is not None:
            self.dispatch(*datagram)

    def dispatch(self, receiver, addr, message_type, payload, wrapped):
        """Route a datagram to the handler for its channel."""
        if receiver is self.s:
            self.on_station(receiver, addr, message_type, payload)
            return
        if message_type == 0x0A and len(payload) == 381:
            self.on_admission(receiver, addr, payload)
            return
        if addr in self.arena_connections and self.on_arena(addr, message_type, payload):
            return
        if self.args.relay:
            self.on_relay(receiver, addr, message_type, payload, wrapped)

    def on_station(self, receiver, addr, message_type, payload):
        now = time.monotonic()
        if message_type == 0x0A and len(payload) == 381:
            new_session = addr not in self.station.peers
            if new_session and self.restart_due is not None:
                receiver.sendto(codec.encode(*ack_connect(payload, result=4), self.key), addr)
                return
            identity = self.station.admit(addr, payload, now)
            if identity is not None:
                if new_session and not self.arena_connections:
                    self.idle_since = now
                if new_session and self.args.sustained_delivery:
                    # A player whose client crashed or lost its link logs in
                    # again from a new endpoint on the same IP. Remove the
                    # stale ship now instead of after the peer timeout. An
                    # active second client on the same PC is left alone.
                    for stale in [peer for peer in self.arena_connections if peer[0] == addr[0] and peer != addr
                                  and now - self.arena_heard.get(peer, now) >= self.REJOIN_SILENCE]:
                        self.depart(stale, "replaced by rejoin")
                        self.station_depart(stale, "replaced by rejoin")
                self.refresh_server_list()
                name = self.station.peers[addr]["pilot"] if self.args.guest_sessions else None
                receiver.sendto(codec.encode(*ack_connect(payload, station_id=identity, pilot_name=name), self.key), addr)
            elif addr not in self.station.peers and addr not in self.station.retired and self.station.next_id > self.station.CAPACITY:
                receiver.sendto(codec.encode(*ack_connect(payload, result=4), self.key), addr)
        elif message_type == 0x4E and len(payload) == 1:
            self.station_depart(addr, "client quit")
        elif message_type == 9:
            self.station.heartbeat(addr, payload, now)

    def on_admission(self, receiver, addr, payload):
        # Retries (including reliable wrappers) acknowledge the same
        # admission, without postponing or restarting flight. Endpoint
        # replacement needs an explicit departure/expiry policy first.
        first_join = addr not in self.arena_connections
        if first_join and self.restart_due is not None:
            receiver.sendto(codec.encode(*ack_connect(payload, kind=0, result=4), self.key), addr)
            return
        if first_join and addr not in self.retired_endpoints and len(self.arena_connections) >= self.args.max_players:
            receiver.sendto(codec.encode(*ack_connect(payload, kind=0, result=4), self.key), addr)
            return
        if first_join and (addr in self.retired_endpoints or
                           len(self.arena_connections) + len(self.retired_endpoints) >= ARENA_JOINS):
            return
        if not first_join and self.arena_connections[addr] != payload:
            return
        owner = None
        if self.args.guest_sessions:
            owner = self.station.arena_owner(payload, addr, time.monotonic())
            if owner is None:
                receiver.sendto(codec.encode(*ack_connect(payload, kind=0, result=5), self.key), addr)
                return
            self.arena_pilots[addr] = self.station.peers[self.station.routes[owner][0]]["pilot"]
        player_id = 1
        if self.args.relay:
            if first_join:
                if self.next_player_slot > ARENA_JOINS:
                    return
                self.arena_players[addr] = self.next_player_slot
                self.next_player_slot += 1
                self.arena_motion[addr] = protocol_motion.initial(spawn_position(
                    self.arena_players[addr], self.args.spawn_axis, self.args.spawn_spacing, self.args.spawn_origin))
            player_id = 0x80010000 | self.arena_players[addr]
        self.arena_connections[addr] = payload
        self.refresh_server_list()
        rtype, rpay = ack_connect(payload, 0, player_id)
        receiver.sendto(codec.encode(rtype, rpay, self.key), addr)
        if first_join and (self.args.experimental_flight or self.args.relay):
            self.bootstrap_due[addr] = time.monotonic() + 3
        if first_join:
            self.expiry_due[addr] = time.monotonic() + self.peer_timeout + (3 if addr in self.bootstrap_due else 0)
            if owner is None and addr in self.station.peers and self.station.peers[addr]["arena"] is None:
                # The 2.9.2 client uses one UDP socket for Station and
                # arena. Bind them so Station stops pinging this socket
                # once the arena owns it, and the lease follows arena
                # activity (findings 9.28).
                owner = self.station.peers[addr]["id"]
            if owner is not None:
                self.station.bind_arena(owner, addr, self.expiry_due[addr])

    def on_arena(self, addr, message_type, payload):
        """ACK, quit and ping replies of an admitted endpoint; True when handled."""
        self.arena_heard[addr] = time.monotonic()
        if message_type == 0x0F:
            self.removals.acknowledge(addr, payload)
            return True
        if message_type == 0x4E and len(payload) == 1:
            # SendImQuitting (0x4871C0) sends the reason byte, not a
            # target slot. Only the sending endpoint can depart.
            self.depart(addr, "client quit")
            return True
        if message_type == 9 and len(payload) == 12:
            ticks = self.ping_ticks.get(addr, [])
            if payload[6] == self.arena_players.get(addr, 1) and payload[:4] in ticks:
                ticks.remove(payload[:4])
                sample = (int(time.monotonic() * 1000) - struct.unpack_from("<I", payload)[0]) & 0xFFFFFFFF
                if sample < 60000:
                    previous = self.arena_rtt.get(addr)
                    self.arena_rtt[addr] = sample if previous is None else previous * 0.8 + sample * 0.2
                self.expiry_due[addr] = time.monotonic() + self.peer_timeout
                self.station.renew_arena(addr, self.expiry_due[addr])
            return True
        return False

    def on_relay(self, receiver, addr, message_type, payload, wrapped):
        """Relay gameplay: movement, vessel change, power-ups, missiles, collisions and deaths."""
        if addr not in self.arena_players or addr in self.bootstrap_due:
            return
        if message_type == 0x1F and len(payload) >= 8:
            # Movement deltas are not made reliable by this stub;
            # replaying a wrapped delta would apply it twice.
            if not wrapped:
                self.on_movement(receiver, addr, payload)
        elif message_type == 0xA0:
            self.change_vessel(addr, payload)
        elif message_type == 0x44 and self.powerups is not None:
            taken = self.powerups.pickup(payload, time.monotonic())
            self.log({"t": round(time.time(), 3), "event": "powerup_pickup", "slot": self.arena_players[addr],
                 "status": taken[0] if taken else "rejected"})
            if taken is not None:
                for peer in list(self.ping_due):
                    self.deliver(peer, taken[1], True)
        elif message_type in (0x2A, 0x30, 0x37, 0x48):
            self.on_combat(receiver, addr, message_type, payload)

    def on_movement(self, receiver, addr, payload):
        p = protocol_motion.movement_update(payload, self.arena_players[addr])
        if p is None:
            return
        try:
            state, present, missing = protocol_motion.update(p, self.arena_motion[addr])
        except (ValueError, OverflowError):
            return
        self.arena_motion[addr] = state
        raw_mask = struct.unpack_from("<I", payload, 4)[0]
        # Locate the client's own stats only when the relayed
        # prefix/gun block match the original byte layout.
        if not raw_mask & protocol_motion.GUN_STATE or protocol_motion.GUN_STATE in present:
            try:
                reported = protocol_motion.client_stats(payload, len(p), raw_mask)
            except ValueError:
                reported = None
            if reported is not None:
                self.arena_reported[addr] = reported
            if self.targets is not None:
                try:
                    hits = protocol_motion.perceived_damage(payload, len(p), raw_mask)
                except ValueError:
                    hits = []
                self.destroy_targets(self.targets.gun_hits(self.arena_vessels.get(addr, self.start_vessel), hits,
                                                      time.monotonic()), self.arena_players[addr])
        p = protocol_motion.snapshot(self.arena_players[addr], state, include_control=0x400 in present,
                                     stats=self.player_stats(addr))
        self.expiry_due[addr] = time.monotonic() + self.peer_timeout
        self.station.renew_arena(addr, self.expiry_due[addr])
        for peer in self.arena_players:
            if peer != addr and peer not in self.bootstrap_due:
                receiver.sendto(codec.encode(0x1F, p, self.key), peer)

    def on_combat(self, receiver, addr, message_type, payload):
        sender = self.arena_players[addr]
        loaded = {slot: peer for peer, slot in self.arena_players.items() if peer not in self.bootstrap_due}
        if message_type in (0x2A, 0x30):
            # Optional ordered delivery shares the removal budget.
            handle = self.missiles.launch if message_type == 0x2A else self.missiles.impact
            result = handle(sender, payload, loaded, time.monotonic())
            self.log({"t": round(time.time(), 3), "event": "missile_" + ("launch" if message_type == 0x2A
                                                                    else "impact"),
                 "slot": sender, "accepted": result is not None})
            if result is not None:
                for peer in loaded.values():
                    self.combat_send(peer, result)
                if message_type == 0x30:
                    missile, hit = struct.unpack_from("<II", payload)
                    name = self.missiles.names.pop(missile, None)
                    if self.targets is not None:
                        died = self.targets.missile_hit(hit, name, time.monotonic())
                        self.destroy_targets([died] if died else [], sender)
        elif message_type == 0x48:
            target = collision_target(payload, sender, loaded)
            if target is not None:
                receiver.sendto(codec.encode(0x48, payload, self.key), loaded[target])
        else:
            self.on_death(addr, sender, payload, loaded)

    def on_death(self, addr, sender, payload, loaded):
        death = self.deaths.report(sender, payload, loaded, time.monotonic())
        if death is None:
            return
        self.log({"t": round(time.time(), 3), "event": "player_died", "slot": sender,
             "reason": "killed" if death[1][4:] != bytes(4) else "no valid killer"})
        for slot, peer in loaded.items():
            if slot != sender:
                self.combat_send(peer, death)
        # The victim resets itself to the origin (9.27);
        # restore its assigned spawn like flight entry.
        spawn = spawn_position(sender, self.args.spawn_axis, self.args.spawn_spacing, self.args.spawn_origin)
        if addr in self.arena_connections:
            self.deliver(addr, (0x24, struct.pack("<3f", *spawn)))
        killer_slot = struct.unpack_from("<I", death[1], 4)[0] & 0xFFFF
        for peer in {addr, loaded.get(killer_slot)} - {None}:
            if peer in self.arena_connections:
                self.deliver(peer, self.own_record(peer))


def run(args, key, log, resources, objects=None):
    return ArenaServer(args, key, log, resources, objects).serve()

