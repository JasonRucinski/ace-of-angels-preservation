"""Local stand-in for the AoA Station server (UDP), for observing the real client.

Usage:
    python -I tools/station_stub.py <SCRTY.BIN> <log.jsonl> [--port 5033] [--tcp 5034] [--ack] [--arena] [--pilot testpilot] [--seconds N]

Defaults to 127.0.0.1; lan-dogfight opts into one private LAN IPv4 address,
vpn-dogfight into one private or VPN (100.64.0.0/10) address.
Decodes every datagram
with tools/aoanet.py (cipher keyed by SCRTY.BIN, CCompress, CRC16). Bounded,
rotating metadata logs are the default; --raw-capture explicitly includes
packet data. --profile local-relay enables the documented loopback setup.
Use --print-config to inspect settings without opening sockets.
See docs/lan-dogfight.md for LAN setup. Point a local client at 127.0.0.1 in the login dialog's
"Station IP" box. Nothing is ever sent unless --ack is given; replies are
built per message type and are experiments, not a complete server. --arena
adds the initial game-server acknowledgement on UDP 5031. --pilot sets the
one synthetic pilot supplied per session after its first TCP server-list request.
--experimental-flight loads a local vessel and enters flight. The separate
--experimental-relay also assigns player tags and forwards filtered movement
fields. Synthetic-peer motion is verified; full gameplay is not implemented.
--arena-port overrides 5031 for isolated protocol tests.
--experimental-object adds one passive mission ship to the flight bootstrap.
--target-ships N adds N passive hostile ships ahead of the spawn for the target keys.
--peer-timeout sets Station/arena inactivity expiry in seconds (default 30). Retired
relay slots and endpoints are not reused during this run (49 admissions max);
despawn delivery uses bounded reliable retries. Use a fresh client endpoint
to rejoin. Observers retire if removal delivery fails or its 30-ID duplicate
history would be exceeded; safe slot reuse still requires protocol work.
LAN sessions require restarting host and clients for reconnects.
--sustained-delivery (default for vpn-dogfight) replaces that 30-ID lifetime
budget with a time window (tools/reliable_window.py): despawns and combat
events stay ordered and reliable for a whole session, and a rejoining
client from a silent player's IP replaces the stale ship. Slots are still
not reused (49 arena joins per host run).
Station allows 64 lifetime admissions; expired/quit endpoints stay retired.
TCP lists require the ID echoed in the Station player record and a matching
source IP. This is diagnostic correlation, not authentication or ownership.
"""
import json
import hashlib
import errno
import math
import os
import queue
import secrets
import select
import socket
import struct
import sys
import time
from collections import OrderedDict, deque
from contextlib import ExitStack
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import aoanet  # noqa: E402
import host_ops
import relay_motion
from net_impair import Impairment, MeteredSocket, TrafficMeter
from reliable_window import WindowedReliable
import online_terrain
import decode_trn
import vessel_combat
import navigation_buoys
import turret_trial
import warp_trial
from station_runtime import DatagramBudget, EventLog, StationTCPServer, parse_args

NUL = bytes(1)
SESSION_COMPLETE = 75  # Dedicated controller advances the rotation only on this clean exit.
# Player relation index (the client stores index + 1 at player +0x1CC:
# 1 Friendly, 2 Unfriendly, 3 Neutral, 4 Hostile, 5 Allied; the "Set target
# to ..." commands at 0x442376 onwards use these values).
RELATION_HOSTILE = 3
TYPE_NAMES = {0x0A: "SConnectReq", 0x0B: "SAckConnect", 0x94: "type94 (ping/keepalive?)", 0x1B: "wrapper 0x1B"}


def connect_req_fields(p):
    """Decode SConnectReq (0x0A) as described in docs/findings.md section 3."""
    if len(p) < 0x1F + 20:
        return {}
    u32 = lambda o: int.from_bytes(p[o:o + 4], "little")  # noqa: E731
    handle = p[0x1F:0x1F + 20].split(b"\0")[0].decode("latin1")
    return {"version": f"{u32(5)}.{u32(1)}.{u32(9)}", "flag_0x0E": p[0x0E], "handle": handle,
            "login_block_len": len(p) - 0x1F}


def ack_connect(req_payload, kind=1, player_id=1, station_id=None, result=0, pilot_name=None):
    """SAckConnect (0x0B), layout from 2.9.2 CClientComm::ReceiveAckConnect (0x431630):
    +0 u8 (logged as "me[%d]"), +1 u8 ack kind (switch at 0x4317d6:
    1 = station path, which reads status flags/squad; 0 = game server path),
    +2 u32 player id, +6 u32 result
    (0 or 0x0F = success), +0x0A..0x0C u8 flags, +0x0D the 350-byte player
    block (same size as the request's login block; status flags at +0x3F,
    squad present at +0x45, squad name at +0x11F). The player block is the
    client's own login block echoed back, with status and squad cleared."""
    block = bytearray(req_payload[0x1F:0x1F + 350].ljust(350, b"\0")) if result == 0 else bytearray(350)
    if pilot_name is not None and result == 0:
        pilot_list(pilot_name)
        block[:20] = pilot_name.encode("ascii").ljust(20, b"\0")
    payload = bytearray(0x0D) + block
    payload[1] = kind
    payload[2:6] = player_id.to_bytes(4, "little")
    payload[6:10] = result.to_bytes(4, "little")
    payload[0x3F:0x43] = bytes(4)
    payload[0x45:0x49] = bytes(4)
    if station_id is not None:
        # SendRequestTCPData copies player-record+0x7B to request+0x3C.
        struct.pack_into("<I", payload, 0x0D + 0x7B, station_id)
    return 0x0B, bytes(payload)


def ack_reliable(payload):
    """Reliable messages arrive as 0x1B: inner payload || u32 sequence || u8 inner
    type. The client drops the pending copy when it receives type 0x0F whose
    payload starts with that u32 sequence (CAOAComm receive switch, 0x4864E2,
    walks the retry list at +0xF18 comparing entry+0 with payload+0)."""
    return 0x0F, payload[-5:-1]


TCP_REQUEST_LEN = 142   # u32 correlation at +0x3C, u8 job +0x80, u8 flag +0x81


class StationSessions:
    """Local session/guest ownership, not authenticated internet identity.

    UDP owns mutable state. TCP reads a replaced, immutable route snapshot.
    No endpoint/ID reuse during a process: delayed quits cannot hit a rejoin.
    """
    CAPACITY = 64

    def __init__(self, timeout, pilot="testpilot", guests=False):
        self.timeout = timeout
        self.pilot, self.guests = pilot, guests
        self.peers = {}
        self.retired = set()
        self.next_id = 1
        self.routes = {}
        self.used_ids = set()

    def _publish(self):
        self.routes = {state["id"]: (peer, state["expiry"])
                       for peer, state in self.peers.items()}

    def admit(self, peer, payload, now):
        fingerprint = hashlib.sha256(payload).digest()
        if peer in self.peers:
            state = self.peers[peer]
            return state["id"] if state["request"] == fingerprint and now < state["expiry"] else None
        if peer in self.retired or self.next_id > self.CAPACITY:
            return None
        identity = self.next_id
        if self.guests:
            # This legacy field is only 32 bits. Randomness prevents trivial
            # sequential selection, but is not a modern authentication scheme.
            for _ in range(128):
                identity = secrets.randbits(32)
                if identity and identity not in self.used_ids:
                    break
            else:
                return None
        pilot = f"{self.pilot[:16]}-{self.next_id:02d}" if self.guests else self.pilot
        self.next_id += 1
        self.used_ids.add(identity)
        self.peers[peer] = {"id": identity, "request": fingerprint, "aliases": False,
                            "pilot": pilot, "arena": None,
                            "expiry": now + self.timeout, "ping_due": now + 1, "ticks": []}
        self._publish()
        return identity

    def resolve(self, request, address, now):
        """Called by TCP; a source IP alone never selects a session."""
        identity = int.from_bytes(request[60:64], "little")
        route = self.routes.get(identity)
        if route is not None and route[0][0] == address[0] and now < route[1]:
            return identity
        return None

    def alias_target(self, identity, now):
        route = self.routes.get(identity)
        if route is None or now >= route[1]:
            return None
        peer = route[0]
        state = self.peers[peer]
        if state["aliases"]:
            return None
        state["aliases"] = True
        return peer

    def depart(self, peer):
        if self.peers.pop(peer, None) is None:
            return False
        self.retired.add(peer)
        self._publish()
        return True

    def heartbeat(self, peer, payload, now):
        # No tag check: the 2.9.2 client uses one UDP socket for Station and
        # arena, and after arena entry it echoes its arena slot here (live
        # capture, findings 9.23). The single-use issued tick is the check.
        state = self.peers.get(peer)
        if (state is None or now >= state["expiry"] or len(payload) != 12
                or payload[:4] not in state["ticks"]):
            return False
        state["ticks"].remove(payload[:4])
        state["expiry"] = now + self.timeout
        self._publish()
        return True

    def pings(self, now):
        packets = []
        for peer, state in self.peers.items():
            if state["arena"] is None and now < state["expiry"] and now >= state["ping_due"]:
                packet = arena_ping(int(now * 1000))
                state["ticks"].append(packet[1][:4])
                del state["ticks"][:-4]
                state["ping_due"] = now + 1
                packets.append((peer, packet))
        return packets

    def arena_owner(self, payload, peer, now):
        if len(payload) != 381:
            return None
        identity = int.from_bytes(payload[31 + 0x7B:35 + 0x7B], "little")
        route = self.routes.get(identity)
        if route is None or route[0][0] != peer[0] or now >= route[1]:
            return None
        state = self.peers[route[0]]
        if payload[31:51] != state["pilot"].encode("ascii").ljust(20, b"\0"):
            return None
        if state["arena"] is not None and state["arena"] != peer:
            return None
        return identity

    def bind_arena(self, identity, peer, expiry):
        state = self.peers[self.routes[identity][0]]
        state["arena"], state["expiry"] = peer, expiry
        self._publish()

    def renew_arena(self, peer, expiry):
        for state in self.peers.values():
            if state["arena"] == peer:
                state["expiry"] = expiry
                self._publish()
                return

    def release_arena(self, peer, now):
        for state in self.peers.values():
            if state["arena"] == peer:
                state["arena"] = None
                state["expiry"] = now + self.timeout
                self._publish()
                return


def pilot_list(name="testpilot"):
    """Type 0x9A: ten NUL-terminated 32-byte slots, no header.

    2.9.2 dispatch 0x430F5D passes the payload to notify slot +8;
    0x45DBE0 reads ten slots and selects the last nonempty name.
    Keep the test name within the login block's narrower 20-byte field.
    """
    encoded = name.encode("ascii")
    if not encoded or len(encoded) > 19 or b"\0" in encoded:
        raise ValueError("pilot must contain 1..19 non-NUL ASCII characters")
    return encoded.ljust(320, b"\0")


def udp_replies(message_type, payload, arena=False):
    """Replies to validated packets; wrappers acknowledge and dispatch once.

    Only the first arena handshake is implemented, not arena simulation.
    Repeated requests deliberately produce the same stateless replies.
    """
    replies = []
    if message_type == 0x1B:
        if len(payload) < 5:
            return replies
        replies.append(ack_reliable(payload))
        message_type, payload = payload[-1], payload[:-5]
    if message_type == 0x0A and len(payload) == 381:
        replies.append(ack_connect(payload, kind=0 if arena else 1))
    return replies


DEFAULT_VESSEL = "Ym Khtat"
# Every .Sco object in the 2.9.2 AoAObjects.odb with an engine, pods
# excluded (work/2.9.2/sco.json): the fighters the in-flight menu offers.
SELECTABLE_VESSELS = frozenset((
    "AlphaFighter", "Dafusha", "Dasibaz", "Eagle", "Etat'Illraku", "Foushar", "Grathven", "Hartra",
    "IBCH", "Janha Vari", "Kafic", "MBB", "Meskvak Su", "Mkulat", "N'Goc", "Naroch", "Natak'Illraku",
    "Rchat", "Rhino", "Saksatar", "Shrike", "Tekan", "Test Missile Boat", "Tholfus", "Ummra Viazyem",
    "Vagym", "Vasa Chovo", "Vermok", "Vrak Stat", "Yagari", "Ym Khtat", "Zkole"))


def ship_config_list():
    """TCP job 4 body: the custom-config list (findings 9.40).

    The handler (0x435CEB -> 0x4AF030) takes 0x68-byte entries; one whose
    +0x20 name is "_all" sets world +0xDF141, so the fighter menu offers a
    "default" config (index 0) for every ship. Without it the menu shows
    "Ship Not Available" and refuses with "Fighter Not Available".
    """
    entry = bytearray(0x68)
    entry[0x20:0x24] = b"_all"
    return bytes(entry)


def ship_request(payload):
    """The vessel of a valid fighter request, or None.

    SendRequestCustomConfig (0x48A030, type 0xA0, 37 bytes) is the online
    fighter menu's confirm (0x466A2D): u32 config index, vessel[32], a zero
    byte. The client zeroes the block before copying the name.
    """
    if len(payload) != 0x25 or payload[0x24] or NUL not in payload[4:0x24]:
        return None
    name = payload[4:0x24].split(NUL, 1)[0].decode("latin1")
    return name if name in SELECTABLE_VESSELS else None


def load_ship(vessel=DEFAULT_VESSEL, slot=0):
    """ReceiveLoadShip at 0x4306C1: vessel[64], database[64], player slot u8.

    Slot zero is the receiver's own ship; others are the receiver's world
    index for that player, which is the tag's low word (0x4A5DE0). It calls
    ChangeObjectVessel (0x4A7F90) directly, as the offline menu does.
    """
    if vessel not in SELECTABLE_VESSELS or not 0 <= slot < 50:
        raise ValueError("unknown vessel or slot")
    return 0x27, vessel.encode().ljust(64, NUL) + b"AoAObjects.odb".ljust(64, NUL) + bytes([slot])


def flight_bootstrap(position=None, terrain=None, vessel=DEFAULT_VESSEL):
    """Experimental local ship load, then explicit flight entry.

    0x27 loads the vessel into local slot zero. 0x2C ignores its four-byte body.
    `terrain` is an online_terrain marker asking a patched client to create
    that map's terrain; None sends the original empty body.
    """
    if terrain is not None and len(terrain) != 4:
        raise ValueError("terrain marker must be four bytes")
    replies = [load_ship(vessel), (0x2C, terrain if terrain is not None else bytes(4))]
    if position is not None:
        # SetupFlightMode (0x44B68E) resets coordinates during 0x2C.
        # Apply this afterwards; 0x430881 -> 0x4BE970 sets actual and target.
        replies.append((0x24, struct.pack("<3f", *position)))
    return replies


def arena_ping(tick_ms):
    """Type 8 invokes BouncePing (0x486C20); type 9 is its 12-byte reply.

    Timestamp u32, trip time u16, player u8, reserved u8, two u16 counters.
    Player zero denotes the server peer on the client. The client replaces
    this with its own tag's low byte when bouncing the packet.
    """
    return 0x08, struct.pack("<IHBBHH", tick_ms & 0xFFFFFFFF, 0, 0, 0, 0, 0)


def remove_player(slot):
    """2.9.2 type 0x2D reads a u8 slot at 0x430710, calls RemovePlayer.

    The receiver has no tag/generation check. Never send slot zero (local).
    """
    if not 1 <= slot < 50:
        raise ValueError("player slot must be 1..49")
    return 0x2D, bytes([slot])


class ReliableRemovals:
    """Bounded 0x1B delivery; preserve the client's 30-entry duplicate cache.

    All outbound reliable messages must use this shared history budget.
    Sequence zero is pre-filled in the client cache.
    Retries back off from INTERVAL to MAX_INTERVAL and give up after
    `deadline` seconds. A real 2.9.2 client in a background window stops
    servicing UDP for tens of seconds and then drains its queue (findings
    9.23), so the server passes its peer timeout here: an observer is not
    retired for a stall it would otherwise survive.
    """
    INTERVAL = 0.5
    MAX_INTERVAL = 4.0
    HISTORY = 30

    def __init__(self, deadline=2.5, ordered=False):
        self.deadline = deadline
        self.ordered = ordered
        self.pending = {}
        self.sent = {}
        self.sequence = 1

    def queue(self, peer, slot, now):
        kind, body = remove_player(slot)
        return self.queue_message(peer, kind, body, now)

    def queue_message(self, peer, kind, body, now):
        """Share one lifetime history budget across every essential event.

        Ordered mode holds subsequent packets until the preceding ACK. This
        prevents an impact overtaking its launch. None means budget exhausted;
        an empty tuple means accepted but waiting behind another event.
        """
        if not 0 <= kind <= 255 or kind == 0x1B or len(body) > 503:
            raise ValueError("invalid reliable inner message")
        if self.sent.get(peer, 0) >= self.HISTORY or self.sequence > 0xFFFFFFFF:
            return None
        seq = self.sequence
        self.sequence += 1
        packet = (0x1B, body + struct.pack("<I", seq) + bytes([kind]))
        waiting = self.ordered and any(p == peer for p, _ in self.pending)
        self.pending[peer, seq] = (packet, math.inf if waiting else now + self.INTERVAL,
                                  self.INTERVAL, now + self.deadline)
        self.sent[peer] = self.sent.get(peer, 0) + 1
        return () if waiting else packet

    def acknowledge(self, peer, payload, now=None):
        if len(payload) != 4:
            return False
        identity = peer, struct.unpack("<I", payload)[0]
        entry = self.pending.get(identity)
        if entry is None or entry[1] == math.inf:
            return False
        del self.pending[identity]
        if self.ordered:
            for next_id, (packet, due, interval, deadline) in self.pending.items():
                if next_id[0] == peer:
                    self.pending[next_id] = (packet, time.monotonic() if now is None else now,
                                             interval, deadline)
                    break
        return True

    def due(self, now):
        failed = {peer for (peer, _), (_, _, _, give_up) in self.pending.items() if now >= give_up}
        packets = []
        for (peer, seq), (packet, due, interval, give_up) in list(self.pending.items()):
            if peer not in failed and now >= due:
                packets.append((peer, packet))
                interval = min(interval * 2, self.MAX_INTERVAL)
                self.pending[peer, seq] = (packet, now + interval, interval, give_up)
        return packets, failed

    def discard(self, peer):
        for identity in list(self.pending):
            if identity[0] == peer:
                del self.pending[identity]
        self.sent.pop(peer, None)


class InboundReliable:
    """Per-channel/endpoint duplicate suppression for inbound 0x1B envelopes.

    Mirrors the client's own receive history (a fixed count of recent IDs),
    with a larger window. Callers ACK every copy, since an earlier ACK may
    have been lost; only the first copy may cause side effects. Sequence zero
    is not pre-filled: the client's send counter origin is unverified.
    History outlives departure (endpoints are never reused); the table is
    bounded instead. A replay older than WINDOW newer distinct IDs, or from
    an endpoint evicted from the table, is treated as new, so handlers must
    remain idempotent.
    """
    WINDOW = 64
    MAX_ENDPOINTS = 512
    # Repeated handshakes must be re-answered: the reply may have been lost.
    REPLAYABLE = frozenset({0x0A})

    def __init__(self):
        self.history = OrderedDict()
        self.duplicates = 0

    def first(self, endpoint, sequence):
        recent = self.history.pop(endpoint, None) or deque(maxlen=self.WINDOW)
        self.history[endpoint] = recent
        if len(self.history) > self.MAX_ENDPOINTS:
            self.history.popitem(last=False)
        if sequence in recent:
            self.duplicates += 1
            return False
        recent.append(sequence)
        return True


def ffa_team(slot):
    """Free-for-all: every player its own team (id, name). New design."""
    return slot, f"Team{slot}"


def object_to_team(tag, team):
    """Type 0x50 ObjectToTeam, 46 bytes (receiver 0x432100 -> 0x4AD590):
    u32 object tag, u32 team id, u32 team-leader tag, team name at +0x0C,
    flags at +0x2C/+0x2D (left 0). For the local player the receiver looks
    the leader up and prints "Wingleader: <name>"; a leader of 0 makes that
    a null player and crashes in msvcrt (findings 9.31). In a free-for-all
    every player leads its own team."""
    team_id, team_name = team
    pilot_list(team_name)
    body = bytearray(0x2E)
    struct.pack_into("<III", body, 0, tag, team_id, tag)
    body[0x0C:0x0C + 20] = team_name.encode().ljust(20, NUL)
    return 0x50, bytes(body)


def load_player(slot, position=None, name=None, team=None, vessel=DEFAULT_VESSEL, station_id=None):
    """Experimental SLoadPlayer, 438 bytes, recovered from 0x4A6320.

    Synthetic player data only: never distribute the login/password block.
    The high tag bit identifies players; low 16 bits select their world slot.
    A nonzero team id at +0x40 (team name at +0x2C) assigns a team via
    ObjectToTeam 0x4AD590. Only with --experimental-teams: ad-hoc teams
    crashed a client (findings 9.30-9.31).
    +0x44/+0x45 are the receiver's relation to this player when on the same
    or another team (0x49CA40); both are Hostile, since free-for-all has no
    teammates. 0 (Friendly) made LaunchActiveMissiles refuse (9.32).
    """
    if not 1 <= slot < 50:
        raise ValueError("player slot must be 1..49")
    if vessel not in SELECTABLE_VESSELS:
        raise ValueError("unknown vessel")
    p = bytearray(0x1B6)
    p[:20] = vessel.encode().ljust(20, b"\0")
    p[20:40] = b"AoAObjects.odb".ljust(20, b"\0")
    struct.pack_into("<I", p, 0x28, 0x80010000 | slot)
    p[0x44] = p[0x45] = RELATION_HOSTILE
    pilot = name if name is not None else f"LocalPilot{slot}"
    pilot_list(pilot)  # Enforce the same narrow ASCII field bound.
    p[0x46:0x46 + 20] = pilot.encode().ljust(20, b"\0")
    if station_id is not None:
        # Only in a player's own record: the copy flag below replaces its
        # record, and TCP requests carry +0x7B (9.16, 9.40).
        struct.pack_into("<I", p, 0x46 + 0x7B, station_id)
    struct.pack_into("<3f", p, 0x1A4, *(position if position is not None else spawn_position(slot)))
    p[0x1B0] = 1
    if team is not None:
        team_id, team_name = team
        pilot_list(team_name)
        p[0x2C:0x2C + 20] = team_name.encode().ljust(20, NUL)
        struct.pack_into("<I", p, 0x40, team_id)
    return 0x26, bytes(p)


def player_tag(slot):
    return 0x80010000 | slot


def collision_target(payload, sender_slot, slots):
    """Validate a 0x48 collision impulse; return the target slot or None.

    20 bytes: u32 source tag, u32 target tag, float3 (send 0x487130). The
    receiver _exit(2)s unless the target tag is its own (0x431EA0), so it
    must reach only that target, and only from the claimed source.
    """
    if len(payload) != 20:
        return None
    source, target = struct.unpack_from("<II", payload)
    if source != player_tag(sender_slot) or target & 0xFFFF0000 != 0x80010000:
        return None
    if not all(math.isfinite(v) for v in struct.unpack_from("<3f", payload, 8)):
        return None
    slot = target & 0xFFFF
    return slot if slot != sender_slot and slot in slots else None


class DeathLedger:
    """Victim-reported deaths (0x37) and kill counts for the local relay.

    In 2.9.2 the victim's own client computes damage from relayed fire
    state and reports its killer's tag (findings 9.26). This trusts that
    report, as the original protocol did; it is not authoritative combat.
    """
    REPEAT = 2.0  # One death per victim per window: 0x37 is unreliable.

    def __init__(self):
        self.kills, self.deaths, self.last = {}, {}, {}

    def report(self, victim_slot, payload, slots, now):
        """Return the 0x38 (killed tag, killer tag) for observers, or None.

        Unknown or self killers become 0 ("killer null" in 0x4A51C0).
        Never send this to the victim: 0x4A5440 would report again.
        """
        if len(payload) != 4 or now < self.last.get(victim_slot, -math.inf) + self.REPEAT:
            return None
        self.last[victim_slot] = now
        killer = struct.unpack("<I", payload)[0]
        killer_slot = killer & 0xFFFF
        if killer & 0xFFFF0000 != 0x80010000 or killer_slot == victim_slot or killer_slot not in slots:
            killer, killer_slot = 0, None
        self.deaths[victim_slot] = self.deaths.get(victim_slot, 0) + 1
        if killer_slot is not None:
            self.kills[killer_slot] = self.kills.get(killer_slot, 0) + 1
        return 0x38, struct.pack("<II", player_tag(victim_slot), killer)


class MissileLedger:
    """Server-assigned missile tags and one impact per missile (9.32).

    Online, LaunchActiveMissiles (0x4B0E00) only sends 0x2A (146 bytes)
    with its 16 missile tags zeroed; OnReceiveMissileLaunch (0x4B16B0)
    then creates each missile from the server's echo, shooter included.
    The target's or the shooter's client reports the hit as 0x30 (21 bytes,
    0x485960) without applying it; each receiver applies an impact on
    itself (0x433FC0). Tags are 0x40CCIIII like AllocNewObject (0x4A5960)
    makes: index IIII below its 1000-object limit, above the test object.
    `objects` are tags of server-owned world objects (TargetShips) that may
    also be targeted and hit; only the shooter's client reports those hits.
    """
    LAUNCH_SIZE, IMPACT_SIZE = 0x92, 0x15
    MAX_COUNT = 16          # SFireMissile tag slots (0x4B1082 limit)
    MAX_LIVE = 16           # Per shooter; bounds the index ring's reuse
    FIRST_INDEX, LAST_INDEX = 500, 999
    LIFETIME = 60.0

    def __init__(self, objects=()):
        self.objects = frozenset(objects)
        self.live = {}      # tag -> (shooter slot, target slot or None for an object, expiry)
        self.names = {}     # tag -> missile name (object damage is the server's)
        self.index = self.FIRST_INDEX
        self.counter = 0

    def _expire(self, now):
        for tag in [t for t, (_, _, expiry) in self.live.items() if now >= expiry]:
            del self.live[tag]
            self.names.pop(tag, None)

    def _next_tag(self):
        while True:
            index = self.index
            self.index = self.FIRST_INDEX if index >= self.LAST_INDEX else index + 1
            self.counter = (self.counter + 1) & 0xFF
            tag = 0x40000000 | self.counter << 16 | index
            if all(t & 0xFFFF != index for t in self.live):
                return tag

    @staticmethod
    def _name(field):
        """NUL-terminated ASCII name within its 32-byte field, or None."""
        name = field.split(NUL, 1)[0]
        if NUL not in field or not name or not all(32 <= c < 127 for c in name):
            return None
        return name

    def launch(self, sender_slot, payload, slots, now):
        """Return the 0x2A echo for every loaded player, or None.

        +0 f32 lock (0..100), +4 target tag, +8 shooter tag, +0xC count,
        +0x10 16 tags, +0x50 missile name, +0x70 rack name (32 bytes each;
        the client leaves stack bytes after the NULs: scrubbed here),
        +0x90 u16 targeted system (0x4B14C9 caps it at 0x1000).
        """
        if len(payload) != self.LAUNCH_SIZE:
            return None
        self._expire(now)
        lock, target, shooter, count = struct.unpack_from("<fIII", payload)
        target_slot = None if target in self.objects else target & 0xFFFF
        if (not math.isfinite(lock) or not 0 <= lock <= 100 or shooter != player_tag(sender_slot)
                or target_slot is not None and (target & 0xFFFF0000 != 0x80010000 or target_slot == sender_slot
                                                or target_slot not in slots)
                or not 1 <= count <= self.MAX_COUNT
                or any(payload[0x10:0x50])
                or struct.unpack_from("<H", payload, 0x90)[0] > 0x1000):
            return None
        names = [self._name(payload[o:o + 0x20]) for o in (0x50, 0x70)]
        if None in names:
            return None
        if (sum(1 for s, _, _ in self.live.values() if s == sender_slot) + count > self.MAX_LIVE
                or len(self.live) + count > self.LAST_INDEX - self.FIRST_INDEX + 1):
            return None
        body = bytearray(payload[:0x10] + bytes(0x80) + payload[0x90:])
        for offset, name in zip((0x50, 0x70), names):
            body[offset:offset + len(name)] = name
        for i in range(count):
            tag = self._next_tag()
            self.live[tag] = (sender_slot, target_slot, now + self.LIFETIME)
            self.names[tag] = names[0].decode("ascii")
            struct.pack_into("<I", body, 0x10 + 4 * i, tag)
        return 0x2A, bytes(body)

    def impact(self, sender_slot, payload, slots, now):
        """Return the 0x30 impact for every loaded player, or None.

        +0 missile tag, +4 hit tag (0: no object), +8 float3 position,
        +0x14 direct-hit flag. Only the missile's shooter or target may
        report it, and only the first report counts. On acceptance
        names[tag] is left for the caller to pop.
        """
        if len(payload) != self.IMPACT_SIZE:
            return None
        self._expire(now)
        tag, hit = struct.unpack_from("<II", payload)
        entry = self.live.get(tag)
        if entry is None or sender_slot not in entry[:2]:
            return None
        if hit and hit not in self.objects and (hit & 0xFFFF0000 != 0x80010000 or hit & 0xFFFF not in slots):
            return None
        if not all(math.isfinite(v) for v in struct.unpack_from("<3f", payload, 8)) or payload[0x14] > 1:
            return None
        del self.live[tag]
        return 0x30, bytes(payload)

    def discard(self, slot):
        """Forget missiles whose shooter or target left."""
        for tag in [t for t, entry in self.live.items() if slot in entry[:2]]:
            del self.live[tag]
            self.names.pop(tag, None)


class PowerUps:
    """Server-placed power-ups in a map's power-up zones (findings 9.44).

    SpawnPowerUp 0x43, 17 bytes (2.7.1 sender 0x4D67E0, 2.9.2 receiver
    0x431D30): i32 x/y/z, u8 type 0..4, u32 nonzero tag. The client makes a
    `PowerUp1` world object (type 6) under that tag. Touching it applies the
    effect locally (CollideWithPowerup 0x4B4D60), hides it and reports the
    tag as HitPowerup 0x44, 4 bytes (0x485DB0). MovePowerupTo 0x53, 14 bytes
    (sender 0x4D6CB0, receiver 0x430B2B): u16 world-object index, f32 x/y/z;
    each client hides the object, moves it and shows it again 5000 ms later
    (+0x338 countdown, 0x49ABD0). The effect is the client's; the server
    only places, moves and de-duplicates.

    One power-up per zone, at a random point in its box: AddPowerupZone
    (0x492C10) sizes a zone's maximum as int(...) + 1, so at least one. Its
    density keys (POWERUPUNITDENSITY, MAXPOWERUPSPERUNITDENSITY) were server
    settings that no build ships.
    """
    NAMES = ("Missile Power Up", "Shield Power +5", "Shield Power +10", "Shield Power +20", "Repair Power Up")
    FIRST_INDEX, LAST_INDEX = 100, 499  # Between the test object (1) and missiles (500+)
    HIDDEN = 5.0                        # The client's 5000 ms reappearance timer
    LIMIT = 1e7                         # Coordinates the i32 spawn fields carry safely

    def __init__(self, zones, rng=None):
        if len(zones) > self.LAST_INDEX - self.FIRST_INDEX + 1:
            raise ValueError(f"{len(zones)} power-up zones; at most {self.LAST_INDEX - self.FIRST_INDEX + 1}")
        self.rng = rng or secrets.SystemRandom()
        self.items = {}  # index -> [zone, position, hidden until]
        for n, zone in enumerate(zones):
            if not 0 <= zone["type"] < len(self.NAMES):
                raise ValueError(f"power-up zone {n}: type {zone['type']} is not 0..4")
            if not (math.isfinite(zone["half"]) and 0 <= zone["half"] <= self.LIMIT and
                    all(math.isfinite(c) and abs(c) + zone["half"] <= self.LIMIT for c in zone["position"])):
                raise ValueError(f"power-up zone {n}: box outside +-{self.LIMIT:g}")
            self.items[self.FIRST_INDEX + n] = [zone, self._point(zone), 0.0]
        self.taken = 0

    def _point(self, zone):
        half = zone["half"]
        return tuple(c + self.rng.uniform(-half, half) for c in zone["position"])

    @staticmethod
    def tag(index):
        return 0x40000000 | index

    def spawns(self):
        """0x43 for every power-up, sent to a player after flight entry."""
        return [(0x43, struct.pack("<3iBI", *(int(c) for c in position), zone["type"], self.tag(index)))
                for index, (zone, position, _) in sorted(self.items.items())]

    def pickup(self, payload, now):
        """(name, 0x53 for every loaded player) for a valid 0x44, else None."""
        if len(payload) != 4:
            return None
        tag = struct.unpack("<I", payload)[0]
        item = self.items.get(tag & 0xFFFF)
        if item is None or tag != self.tag(tag & 0xFFFF) or now < item[2]:
            return None
        item[1], item[2] = self._point(item[0]), now + self.HIDDEN
        self.taken += 1
        return self.NAMES[item[0]["type"]], (0x53, struct.pack("<H3f", tag & 0xFFFF, *item[1]))


class TargetShips:
    """Passive server-owned ships that the target keys can select (9.45).

    The target scans (0x4A1530, 0x4A1970, 0x4A0550) walk only players and
    world objects (9.38), and map terrain is neither. LoadObject 0x25
    (191 bytes, receiver 0x4A66A0) makes a world object under the given
    tag. Kind 0x11 leaves it non-terrain (+0x20C = 0 in SetTerrainType
    0x49A560), which the candidate filter 0x4A10F0 requires. The relation
    bytes +0x90/+0x91 use the player load's encoding (9.32); 3 is Hostile,
    so J and missile launch accept them. Team id 0 makes the client create
    a team of its own for each ship (0x4AD4B0). No AI: they hold position.

    Damage is the server's, as in the original (9.46). LoadObject sets the
    object's category +0x200 to 4, for which DoSimpleDamage (0x49BFA0) resets
    the HP and never kills, so no client destroys a ship itself. The shooter
    reports its own gun hits in its 0x1F upload (relay_motion.perceived_damage);
    each hit takes gun-table damage x 0.8 (DoDamage 0x49BCE0) x 0.5 (0x49BFA0)
    from the vessel's simple HP, its Shield value. Missile hits take the
    shield drops measured on players (9.32). At 0 HP every player gets
    RemoveObject 0x45, as the original server sent for a destroyed object
    (SendRemoveObject 0x488ED0 from DoSimpleDamage's server branch): u16
    world-object index, u8 1 = blow up (receiver 0x430728 -> 0x4A71A0). The
    ship is loaded again RESPAWN seconds later. ObjectHasDied 0x38 is no
    substitute: for an object with +0x1DC = -1 the kill routine (0x4A5440)
    only resets its shields.
    """
    FIRST_INDEX, LAST_INDEX = 2, 99    # After the test object (1), before power-ups (100+)
    VESSELS = ("Ym Khtat", "Vermok", "Shrike", "Rhino", "Tholfus", "Eagle")
    # Ahead of the spawn. Arena1a spawns in a 5137-unit safe zone, where the
    # client allows no missile lock or launch (+0x2F8 gates 0x44AFD0 and
    # 0x4B0E47); at the zone edge this leaves more than Type II's 5000.
    DISTANCE = 12000.0
    ARC = 60.0                         # Degrees the ships spread across; all on screen at spawn
    HOSTILE = 3
    GUN_SCALE = 0.8 * 0.5              # DoDamage, then DoSimpleDamage
    MAX_HITS = 16                      # Per report entry, per upload
    MISSILE_DAMAGE = (("Type III", 12.0), ("Type II", 10.0))  # Measured shield drops (9.32)
    RESPAWN = 15.0

    def __init__(self, count, origin=None):
        if not 0 < count <= self.LAST_INDEX - self.FIRST_INDEX + 1:
            raise ValueError(f"target ships: {count} is not 1..{self.LAST_INDEX - self.FIRST_INDEX + 1}")
        x, y, z = origin or (0.0, 0.0, 0.0)
        self.ships = {}  # index -> (vessel, name, position)
        for n in range(count):
            # Ships face +z at spawn (spawn_position), so the arc is in view.
            angle = math.radians(0.0 if count == 1 else -self.ARC / 2 + self.ARC * n / (count - 1))
            position = (x + self.DISTANCE * math.sin(angle), y, z + self.DISTANCE * math.cos(angle))
            self.ships[self.FIRST_INDEX + n] = (self.VESSELS[n % len(self.VESSELS)], f"Target {n + 1}", position)
        self.hp = {index: self.max_hp(index) for index in self.ships}
        self.dead_until = {}  # index -> respawn time
        self.destroyed = 0

    @staticmethod
    def tag(index):
        return 0x40010000 | index

    def index(self, tag):
        """The live ship with this tag, or None."""
        index = tag & 0xFFFF
        return index if tag == self.tag(index) and index in self.ships and index not in self.dead_until else None

    def max_hp(self, index):
        return vessel_combat.VESSELS[self.ships[index][0]][0]

    def load(self, index):
        vessel, name, position = self.ships[index]
        p = bytearray(0xBF)
        for offset, value in ((0, vessel), (0x20, "AoAObjects.odb"), (0x40, name)):
            p[offset:offset + len(value)] = value.encode("ascii")
        struct.pack_into("<II", p, 0x60, self.tag(index), 0x11)
        p[0x90] = p[0x91] = self.HOSTILE
        struct.pack_into("<3f", p, 0x92, *position)
        return 0x25, bytes(p)

    def loads(self):
        """0x25 for every live ship, sent to a player after flight entry."""
        return [self.load(index) for index in sorted(self.ships) if index not in self.dead_until]

    def _damage(self, index, amount, now):
        """(index, 0x45 for every player) if this destroyed the ship, else None."""
        self.hp[index] -= amount
        if self.hp[index] > 0:
            return None
        self.dead_until[index] = now + self.RESPAWN
        self.destroyed += 1
        return index, (0x45, struct.pack("<HB", index, 1))

    def gun_hits(self, vessel, entries, now):
        """Apply a shooter's perceived-damage entries; [(index, 0x45)] for ships destroyed.

        Entries for players, unknown or dead ships, guns the shooter's vessel
        lacks and implausible counts are ignored.
        """
        guns = vessel_combat.VESSELS.get(vessel, (0.0, {}))[1]
        out = []
        for tag, gun, hits in entries:
            index = self.index(tag)
            if index is None or gun not in guns or not 0 < hits <= self.MAX_HITS:
                continue
            died = self._damage(index, guns[gun] * self.GUN_SCALE * hits, now)
            if died is not None:
                out.append(died)
        return out

    def missile_hit(self, tag, missile, now):
        """Apply one accepted missile impact; (index, 0x45) if it destroyed the ship."""
        index = self.index(tag)
        if index is None:
            return None
        amount = next((v for prefix, v in self.MISSILE_DAMAGE if (missile or "").startswith(prefix)),
                      self.MISSILE_DAMAGE[-1][1])
        return self._damage(index, amount, now)

    def respawns(self, now):
        """0x25 for every ship whose respawn time has come, at full HP."""
        out = []
        for index in sorted(i for i, due in self.dead_until.items() if now >= due):
            del self.dead_until[index]
            self.hp[index] = self.max_hp(index)
            out.append(self.load(index))
        return out


def arena_message(text):
    """Type 0x21 arena text (294 bytes; receiver 0x4348E0).

    u16 kind at +3 = 3 shows the NUL-terminated text at +0x25 in the
    arena message window (0x446E50).
    """
    body = bytearray(0x126)
    struct.pack_into("<H", body, 3, 3)
    encoded = text.encode("ascii", "replace")[:0x126 - 0x25 - 1]
    body[0x25:0x25 + len(encoded)] = encoded
    return 0x21, bytes(body)


class Match:
    """Kill/time limits for the proposed first dogfight (new design, not a
    recovered rule). A match starts when the first player is loaded; when it
    ends the server announces the result and the next match starts at once.
    Returning clients to Station has no recovered server message (9.22)."""

    def __init__(self, kill_limit, time_limit):
        self.kill_limit, self.time_limit = kill_limit, time_limit
        self.started, self.number = None, 1

    def start(self, now):
        if self.started is None:
            self.started = now

    def stop(self):
        self.started = None

    def ended(self, kills, now):
        if self.kill_limit and max(kills.values(), default=0) >= self.kill_limit:
            return "kill limit"
        if self.started is not None and self.time_limit and now - self.started >= self.time_limit:
            return "time limit"
        return None

    def result(self, kills, names):
        """Announcement text; ties are reported as ties."""
        best = max(kills.values(), default=0)
        leaders = sorted(names.get(slot, f"Pilot{slot}") for slot, k in kills.items() if k == best and best)
        if not leaders:
            return f"Match {self.number} over: no kills"
        if len(leaders) > 1:
            return f"Match {self.number} over: tie at {best} kills ({', '.join(leaders)})"
        return f"Match {self.number} over: {leaders[0]} wins with {best} kills"

    def next(self, now):
        self.number += 1
        self.started = now


def spawn_position(slot, axis="x", spacing=1000.0, origin=None):
    """Diagnostic line of spawns. Ships appear to face +z initially, so
    axis z with a short spacing puts each later player ahead of the first.
    `origin` moves the line, e.g. to a map's viewing spawn."""
    offset = (slot - 1) * spacing
    x, y, z = origin or (0.0, 0.0, 0.0)
    return (x + offset, y, z) if axis == "x" else (x, y, z + offset)


def scenario_test_object():
    """One passive mission ship, not an AI/scenario implementation.

    SendLoadObject 0x48A460 sends type 0x25, 0xBF bytes. The mission-group
    loader uses object kind 0x11. Tag low word is an index below 1000.
    """
    p = bytearray(0xBF)
    for offset, value in ((0, b"Ym Khtat"), (0x20, b"AoAObjects.odb"),
                          (0x40, b"Local mission ship")):
        p[offset:offset + len(value)] = value
    struct.pack_into("<II", p, 0x60, 0x40010001, 0x11)
    struct.pack_into("<3f", p, 0x92, 0.0, 0.0, 1500.0)
    return 0x25, bytes(p)


def reported_motion(payload, previous):
    """Read position/velocity from a validated movement_update result.

    Decoder 0x495330 puts 0x40 first, followed by velocity flags 1/2/4.
    Keep last reported coordinates, without inventing server-side motion.
    Delta velocities require the previous value; float32 round like client.
    """
    mask = struct.unpack_from("<I", payload, 4)[0]
    offset = 8
    position, velocity = previous
    if mask & 0x40:
        position = struct.unpack_from("<3f", payload, offset)
        offset += 12
    if mask & 1:
        velocity = struct.unpack_from("<3f", payload, offset)
    elif mask & 6:
        delta = struct.unpack_from("<3h" if mask & 2 else "<3b", payload, offset)
        velocity = struct.unpack("<3f", struct.pack("<3f", *(a + b for a, b in zip(velocity, delta))))
    if not all(math.isfinite(v) for v in (*position, *velocity)):
        raise ValueError("non-finite movement")
    return position, velocity


def motion_snapshot(slot, motion):
    """Absolute position and velocity seed for a newly connected observer."""
    position, velocity = motion
    return 0x1F, struct.pack("<HHI6f", 0x8000, slot, 0x41, *position, *velocity)


def movement_update(payload, slot):
    """Keep the first player's kinematic prefix and validated gun state.

    Decoder 0x495330 consumes these fields before the optional blocks. The
    0x20000000/0x40000000/0x80000000 blocks cannot safely be forwarded: the
    client receive caller leaves some destination pointers uninitialized.
    Discard them and any additional records. Delta fields retain their
    original encoding; this is not state recovery or authoritative simulation.
    """
    if len(payload) < 8:
        return None
    trip, player, raw_mask = struct.unpack_from("<HHI", payload)
    if not trip & 0x8000 or player != slot:
        return None
    mask = raw_mask & 0x07FFFFFF
    if not mask:
        return None
    size = 12 if mask & 0x40 else 0
    # Absolute float triplets or signed short/byte delta triplets, in the
    # decoder's order (not ascending flag order).
    for absolute in (0x1, 0x8, 0x40000):
        size += next((n for flag, n in ((absolute, 12), (absolute << 1, 6),
                                      (absolute << 2, 3)) if mask & flag), 0)
    size += 4 * sum(bool(mask & flag) for flag in (0x80, 0x100, 0x200))
    size += 4 if mask & 0x400 else (2 if mask & 0x800 else 0)
    size += 4 * sum(bool(mask & flag) for flag in (0x1000, 0x2000, 0x4000,
                                                0x8000, 0x10000, 0x20000))
    for absolute in (0x200000, 0x1000000):
        size += next((n for flag, n in ((absolute, 12), (absolute << 1, 6),
                                      (absolute << 2, 3)) if mask & flag), 0)
    if len(payload) < 8 + size:
        return None
    end = 8 + size
    if raw_mask & relay_motion.GUN_STATE:
        # The per-gun fire state directly follows the prefix. Keep it only
        # when well formed with bounded indexes; otherwise drop the block.
        try:
            end = relay_motion.gun_state(payload, end)[1]
            mask |= relay_motion.GUN_STATE
        except ValueError:
            pass
    return struct.pack("<HHI", trip, slot, mask) + payload[8:end]

# Uncompressed TCP reply bodies per job type. Job 14 (resource file-state
# list, handler 0x432ED0): a 128-byte name header, then 168-byte records,
# count = (len - 0x80) / 0xA8; zero records = "every file is current".
def server_record(index, name, s20, s40, ip, port, players, status=0):
    """One 128-byte game-server entry for job 5 (ReceiveGameserverList, 0x432760):
    +0x00 str[32], +0x20 str[32], +0x40 str[32], +0x60 str (IP), +0x72 u16,
    +0x74 u32 players, +0x78 u8 slot index, +0x7C u32 (passed on only if < 99).
    Slot 0 is not a server: CAOAStationDlg's notify (0x4582B0) writes its
    player count into the "Logins" box. Slots >= 1 become rows of the Server
    list (control 0x42B: name, players, IP); RequestGameserverConnect
    (0x42FF20) connects to the row's +0x60 IP and +0x72 port."""
    r = bytearray(0x80)
    for off, text, size in ((0x00, name, 32), (0x20, s20, 32), (0x40, s40, 32), (0x60, ip, 18)):
        b = text.encode("latin1")[:size - 1]
        r[off:off + len(b)] = b
    r[0x72:0x74] = port.to_bytes(2, "little")
    r[0x74:0x78] = players.to_bytes(4, "little")
    r[0x78] = index
    r[0x7C:0x80] = status.to_bytes(4, "little")
    return bytes(r)


TCP_JOB_BODIES = {
    4: ship_config_list(),
    14: bytes(0x80),
    5: server_record(0, "station", "", "", "", 0, 1)
       # Bundled terrain and the client's default backdrop (0x4A3045).
       # Unknown backdrop names make On3dGfxInitialized call _exit(2).
       + server_record(1, "Local Arena", "CTF_arena", "spacebkgd3", "127.0.0.1", 5031, 0),
}


def tcp_reply(job, bodies=None):
    """u32 length + CCompress body (CClientComm::TCPRead 0x435930 decompresses
    with the routine matching 2.7.1 CCompress::Decompress). Length 0 skips the
    job handler and only releases the client's transfer lock."""
    import aoapack
    body = (TCP_JOB_BODIES if bodies is None else bodies).get(job)
    if body is None:
        return (0).to_bytes(4, "little")
    packed = aoapack.compress(body)
    return len(packed).to_bytes(4, "little") + packed


def server_list_body(population, arena_port=None, mode="Local Arena", available=True, station_population=0,
                     advertised_address="127.0.0.1", terrain="CTF_arena", backdrop="spacebkgd3"):
    """Publish admitted arena population; no arena row when unavailable.

    Existing recovered fields 0x20/0x40 are terrain/backdrop, not mode enums.
    """
    body = server_record(0, "station", "", "", "", 0, station_population)
    if arena_port is not None and available:
        body += server_record(1, mode, terrain, backdrop, advertised_address, arena_port, population)
    return body


def main():
    args = parse_args()
    if args.print_config:
        print(json.dumps(vars(args), default=str, indent=2))
        return
    key = args.key.read_bytes()
    if len(key) != 256:
        raise ValueError("SCRTY.BIN must contain exactly 256 bytes")
    try:
        with EventLog(args.log, args.raw_capture, args.log_max_bytes, args.log_backups) as log, ExitStack() as resources:
            return run(args, key, log, resources)
    except KeyboardInterrupt:
        # systemd uses SIGINT, like a foreground Ctrl+C, so the context
        # managers close sockets and drain logs before a successful exit.
        print("Host stopped", flush=True)
    except OSError as error:
        raise SystemExit(f"Host I/O failed: {error}. Check that {args.bind_address} belongs to this PC and the ports are free.") from error


def run(args, key, log, resources):
    warp = warp_trial.loads(warp_trial.placement(args.warp_trial)) if args.warp_trial else []
    trial = turret_trial.loads(turret_trial.placements(args.turret_trial)) if args.turret_trial else []
    buoys = navigation_buoys.loads(navigation_buoys.placements(args.arena1a_buoys)) if args.arena1a_buoys else []
    if args.navigation_buoys:
        buoys = navigation_buoys.loads(navigation_buoys.map_placements(
            args.navigation_buoys, args.map, args.buoy_trn or args.key.parent / 'JRMAP.TRN'))
    port, seconds, peer_timeout = args.port, args.seconds, args.peer_timeout
    reply, pilot = args.ack, args.pilot
    notifications = queue.Queue(maxsize=1024)
    station = StationSessions(peer_timeout, pilot, args.guest_sessions)
    ingress = DatagramBudget()
    inbound = InboundReliable()
    resources.callback(lambda: print(f"UDP ingress: rate_limited={ingress.dropped} "
                                     f"reliable_duplicates={inbound.duplicates}", flush=True))
    meter = TrafficMeter()
    seed = args.impair_seed
    impair_in = Impairment(args.impair_rtt_ms, args.impair_jitter_ms, args.impair_loss, args.impair_duplicate, seed)
    impair_out = Impairment(args.impair_rtt_ms, args.impair_jitter_ms, args.impair_loss, args.impair_duplicate,
                            None if seed is None else seed + 1)
    if impair_in.active:
        print("TEST IMPAIRMENT ACTIVE (each direction): " + json.dumps(impair_out.describe()), flush=True)
        log({"t": round(time.time(), 3), "event": "impairment", "status": impair_out.describe()})
    s = resources.enter_context(socket.socket(socket.AF_INET, socket.SOCK_DGRAM))
    s.bind((args.bind_address, port))
    s = MeteredSocket(s, meter, impair_in, impair_out)
    sockets = [s]
    if args.arena:
        arena_port = args.arena_port
        arena = resources.enter_context(socket.socket(socket.AF_INET, socket.SOCK_DGRAM))
        arena.bind((args.bind_address, arena_port))
        arena = MeteredSocket(arena, meter, impair_in, impair_out)
        sockets.append(arena)
    mode = "Local Relay" if args.experimental_relay else ("Local Flight" if args.experimental_flight else "Handshake Test")
    if args.profile == "lan-dogfight":
        mode = "LAN Dogfight"
    elif args.profile == "vpn-dogfight":
        mode = "VPN Dogfight"
    hosted_port = arena.getsockname()[1] if args.arena and reply else None
    job_bodies = {4: TCP_JOB_BODIES[4], 14: TCP_JOB_BODIES[14], 5: server_list_body(0, hosted_port, mode,
                                                         advertised_address=args.advertised_address,
                                                         terrain=args.map, backdrop=args.backdrop)}

    def station_tcp_response(request, address):
        identity = station.resolve(request, address, time.monotonic())
        if identity is None:
            return bytes(4), None, None
        job = request[128]
        return tcp_reply(job, job_bodies), identity if job == 5 else None, identity

    def session_alive(identity):
        route = station.routes.get(identity)  # Immutable snapshot; TCP thread.
        return route is not None and time.monotonic() < route[1]

    if args.tcp is not None:
        tcp = resources.enter_context(StationTCPServer(args.tcp, log, reply,
            station_tcp_response, notifications, session_alive, bind_address=args.bind_address))
        print(f"Station TCP on {args.bind_address}:{tcp.port}", flush=True)
    bootstrap_due = {}
    arena_players = {}
    arena_connections = {}
    arena_pilots = {}
    arena_vessels = {}  # addr -> vessel chosen in the fighter menu
    start_vessel = args.start_vessel
    if start_vessel not in SELECTABLE_VESSELS:
        raise ValueError(f"unknown --start-vessel {start_vessel!r}")
    arena_reported = {}  # addr -> (rating, score) from the client's own stats
    arena_motion = {}
    ping_due = {}
    expiry_due = {}
    ping_ticks = {}
    next_player_slot = 1
    retired_endpoints = set()
    protection_probe = {}  # peer -> (next due, index in explicit 1,1,0,0 probe)
    if args.sustained_delivery:
        removals = WindowedReliable(deadline=peer_timeout, margin=args.reorder_margin)
        resources.callback(lambda: print(f"sustained delivery: expired_events={removals.expired} "
                                         f"window_waits={removals.window_waits}", flush=True))
    else:
        removals = ReliableRemovals(deadline=peer_timeout,
                                   ordered=args.experimental_reliable_combat or args.experimental_protection_probe)
    resources.callback(lambda: print("traffic: " + json.dumps(dict(meter.totals(), dropped_in=meter.dropped_in,
                                                                   dropped_out=meter.dropped_out)), flush=True))
    deaths = DeathLedger()
    targets = TargetShips(args.target_ships, args.spawn_origin) if args.target_ships else None
    if buoys:
        print(f'{args.map} navigation buoys: {len(buoys)}', flush=True)
    if targets is not None:
        print(f"target ships: {len(targets.ships)}", flush=True)
    missiles = MissileLedger(map(TargetShips.tag, targets.ships) if targets is not None else ())
    powerups = None
    if args.powerup_zones is not None:
        powerups = PowerUps(decode_trn.powerup_zones_292(args.powerup_zones.read_bytes()))
        print(f"power-ups: {len(powerups.items)} from {args.powerup_zones.name}", flush=True)
    match = Match(args.kill_limit, args.time_limit)
    resources.callback(lambda: print("kills=" + json.dumps(deaths.kills) + " deaths=" + json.dumps(deaths.deaths),
                                     flush=True))
    motion_refresh_due = time.monotonic() + 1
    arena_heard = {}   # addr -> last valid arena datagram (monotonic)
    arena_rtt = {}     # addr -> smoothed ping round trip, ms
    banned_ips = set()
    started = time.monotonic()
    status_due = started
    traffic_mark = {}  # addr -> (time, rx_bytes, tx_bytes) at the previous status
    console = host_ops.Console(sys.stdin) if args.console else None
    REJOIN_SILENCE = 5.0
    overflowed = set()  # peers whose reliable queue overflowed, departed next pass
    restart_reason, restart_due = None, None
    restart_notices = set()
    idle_since = started

    def announce_restart(now):
        remaining = max(0, math.ceil(restart_due - now))
        text = f"Next map {args.next_map} in {remaining}s. Quit and relaunch to rejoin."
        for peer in list(ping_due):
            deliver(peer, arena_message(text))

    def schedule_restart(reason, now):
        nonlocal restart_reason, restart_due
        if restart_due is not None:
            return
        restart_reason, restart_due = reason, now + args.restart_warning
        log({"t": round(time.time(), 3), "event": "session_restart_scheduled", "reason": reason,
             "map": args.map, "next_map": args.next_map, "restart_in_s": args.restart_warning})
        print(f"Session ending ({reason}); next map {args.next_map} in {args.restart_warning:g}s", flush=True)
        refresh_server_list()
        announce_restart(now)

    def player_stats(addr):
        """(kills, deaths, rating, score): server counts, client-reported rest."""
        slot = arena_players.get(addr)
        rating, score = arena_reported.get(addr, (0, 0))
        return deaths.kills.get(slot, 0), deaths.deaths.get(slot, 0), rating, score

    def own_record(addr):
        """0x42 for a player's own HUD (0x4AFC00 -> 0x49DB20 copies 350 bytes).

        Its own handshake record with the server's kills (+0x7F) and deaths
        (+0x83) and its last reported score (+0x4E). Never sent to anyone else:
        the record is the client's login block.
        """
        kills, died, _, score = player_stats(addr)
        record = bytearray(arena_connections[addr][31:381])
        struct.pack_into("<i", record, 0x4E, score)
        struct.pack_into("<i", record, 0x7F, kills)
        struct.pack_into("<i", record, 0x83, died)
        return 0x42, struct.pack("<I", player_tag(arena_players[addr])) + bytes(record)

    def change_vessel(addr, payload):
        """Answer the fighter menu's 0xA0 request (findings 9.40).

        The pilot and every loaded observer get 0x27 for the new hull; late
        joiners get it in the player record. The original server path moves a
        ship that changes outside a safe zone to a random point (0x4A4310), so
        the relay sends it back to its spawn, as after a death: a swap is not
        a free escape or repair.
        """
        vessel = ship_request(payload)
        slot = arena_players[addr]
        log({"t": round(time.time(), 3), "event": "ship_change", "slot": slot, "status": vessel or "rejected"})
        if vessel is None:
            return
        arena_vessels[addr] = vessel
        deliver(addr, load_ship(vessel), True)
        for peer in ping_due:
            if peer != addr:
                deliver(peer, load_ship(vessel, slot), True)
        spawn = spawn_position(slot, args.spawn_axis, args.spawn_spacing, args.spawn_origin)
        deliver(addr, (0x24, struct.pack("<3f", *spawn)))

    def end_match(reason, now):
        """Announce the result, reset the scoreboard and start the next match."""
        if restart_due is not None:
            return
        loaded = {arena_players[peer]: peer for peer in ping_due if peer in arena_players}
        names = {slot: arena_pilots.get(peer) or f"LocalPilot{slot}" for slot, peer in loaded.items()}
        text = f"{match.result(deaths.kills, names)} ({reason})"
        log({"t": round(time.time(), 3), "event": "match_end", "reason": reason})
        if args.managed_session:
            for peer in loaded.values():
                deliver(peer, arena_message(text))
            schedule_restart(reason, now)
            return  # Keep the final scoreboard until the session closes.
        deaths.kills.clear()
        deaths.deaths.clear()
        match.next(now)
        for peer in loaded.values():
            deliver(peer, arena_message(text))
            deliver(peer, arena_message(f"Match {match.number} started"))
            deliver(peer, own_record(peer))

    def refresh_server_list():
        hosted_port = arena.getsockname()[1] if args.arena and reply else None
        available = (restart_due is None and len(arena_connections) < args.max_players and
                     len(arena_connections) + len(retired_endpoints) < 49)
        job_bodies[5] = server_list_body(len(arena_connections), hosted_port, mode, available, len(station.peers),
                                       args.advertised_address, args.map, args.backdrop)

    def combat_send(peer, packet):
        if peer not in arena_connections:
            return
        if args.sustained_delivery:
            packet = removals.queue_message(peer, *packet, time.monotonic(), essential=False)
            if packet is None:
                depart(peer, "reliable event queue overflow")
                return
        elif args.experimental_reliable_combat:
            packet = removals.queue_message(peer, *packet, time.monotonic())
            if packet is None:
                depart(peer, "essential event history exhausted")
                return
        if packet:
            arena.sendto(aoanet.encode(*packet, key), peer)

    def destroy_targets(destroyed, shooter):
        """Announce target ships the server destroyed to every loaded player."""
        for index, packet in destroyed:
            log({"t": round(time.time(), 3), "event": "target_destroyed", "ship": index, "slot": shooter})
            for peer in arena_players:
                if peer not in bootstrap_due:
                    combat_send(peer, packet)

    def deliver(peer, packet, essential=False):
        """Session state: reliable and ordered with sustained delivery.

        The 2.9.2 receive loop unwraps 0x1B in place and joins the plain
        path at 0x486464 with the inner type, so any message type can be
        wrapped. Without sustained delivery this stays best effort.
        """
        if not args.sustained_delivery:
            arena.sendto(aoanet.encode(*packet, key), peer)
            return
        if peer not in arena_connections:
            return
        queued = removals.queue_message(peer, *packet, time.monotonic(), essential=essential)
        if queued is None:
            overflowed.add(peer)  # Callers may be iterating arena state.
        elif queued:
            arena.sendto(aoanet.encode(*queued, key), peer)

    refresh_server_list()

    def station_depart(peer, reason):
        arena_peer = station.peers.get(peer, {}).get("arena")
        if station.depart(peer):
            if arena_peer is not None:
                depart(arena_peer, "Station session ended")
            refresh_server_list()
            log({"t": round(time.time(), 3), "event": "station_departure", "reason": reason})

    def depart(peer, reason):
        if peer not in arena_connections:
            return
        # Clear every arena-owned timer/baseline before notifying observers.
        loaded = peer in ping_due
        retired_endpoints.add(peer)
        slot = arena_players.pop(peer, None)
        removals.discard(peer)
        if slot is not None:
            missiles.discard(slot)
        for state in (arena_connections, arena_pilots, arena_vessels, arena_motion, arena_reported, bootstrap_due,
                      ping_due,
                      expiry_due, ping_ticks, protection_probe, arena_heard, arena_rtt, traffic_mark):
            state.pop(peer, None)
        station.release_arena(peer, time.monotonic())
        if loaded and slot is not None:
            failed = []
            for observer in list(ping_due):
                packet = removals.queue(observer, slot, time.monotonic())
                if packet is None:
                    failed.append(observer)
                elif packet:
                    arena.sendto(aoanet.encode(*packet, key), observer)
            for observer in failed:
                depart(observer, "reliable removal history exhausted")
        refresh_server_list()
        log({"t": round(time.time(), 3), "event": "arena_departure", "slot": slot, "reason": reason})

    def players_now(now):
        players = []
        for peer, slot in sorted(arena_players.items(), key=lambda item: item[1]):
            entry = meter.endpoints.get(peer, {"rx_bytes": 0, "tx_bytes": 0})
            then, rx, tx = traffic_mark.get(peer, (started, 0, 0))
            elapsed = max(now - then, 1e-3)
            kills, died, _, _ = player_stats(peer)
            players.append({"slot": slot, "pilot": arena_pilots.get(peer) or f"LocalPilot{slot}",
                            "loaded": peer in ping_due, "kills": kills, "deaths": died,
                            "ping_ms": round(arena_rtt[peer]) if peer in arena_rtt else None,
                            "in_kbps": round((entry["rx_bytes"] - rx) * 8 / elapsed / 1000, 1),
                            "out_kbps": round((entry["tx_bytes"] - tx) * 8 / elapsed / 1000, 1),
                            "idle_s": round(now - arena_heard.get(peer, now), 1)})
        return players

    def host_status(now):
        players = players_now(now)
        for peer in arena_players:
            entry = meter.endpoints.get(peer, {"rx_bytes": 0, "tx_bytes": 0})
            traffic_mark[peer] = (now, entry["rx_bytes"], entry["tx_bytes"])
        return {"schema": 1, "pid": os.getpid(), "profile": args.profile, "mode": mode, "map": args.map,
                "uptime_s": round(now - started),
                "match": match.number, "players": players, "max_players": args.max_players,
                "arena_joins_used": next_player_slot - 1, "arena_joins_limit": 49,
                "station_sessions": len(station.peers), "station_admissions_used": station.next_id - 1,
                "station_admissions_limit": station.CAPACITY, "banned_ips": len(banned_ips),
                "sustained_delivery": args.sustained_delivery,
                "navigation_buoys": len(buoys),
                "warp_trial": {"objects": len(warp), "gate": warp_trial.GATE,
                               "destination_node": "WarpTgt01", "model": "WarpGate / WarpA",
                               "orientation_restored": False, "host_authorized_transit": False} if warp else None,
                "turret_trial": {"objects": len(trial) // 2, "enabled": False,
                                 "model_assignment": "provisional TurretA", "orientation_restored": False} if trial else None,
                "powerups": None if powerups is None else {"placed": len(powerups.items), "taken": powerups.taken},
                "target_ships": None if targets is None else {"placed": len(targets.ships),
                                                              "destroyed": targets.destroyed},
                "reliable_pending": len(removals.pending), "events_expired": getattr(removals, "expired", 0),
                "traffic": dict(meter.totals(), dropped_in=meter.dropped_in, dropped_out=meter.dropped_out),
                "impairment": impair_out.describe() if impair_out.active else None,
                "lifecycle": {"managed": args.managed_session, "next_map": args.next_map,
                              "kill_limit": args.kill_limit, "time_limit_s": args.time_limit,
                              "match_elapsed_s": None if match.started is None else round(now - match.started),
                              "restart_reason": restart_reason,
                              "restart_in_s": None if restart_due is None else max(0, math.ceil(restart_due - now))}}

    def remove_by_host(slot, ban):
        peer = next((peer for peer, taken in arena_players.items() if taken == slot), None)
        if peer is None:
            return f"no arena player in slot {slot}"
        arena.sendto(aoanet.encode(*arena_message("You were removed by the host"), key), peer)
        if ban:
            banned_ips.add(peer[0])
        depart(peer, "banned by host" if ban else "kicked by host")
        station_depart(peer, "banned by host" if ban else "kicked by host")
        log({"t": round(time.time(), 3), "event": "host_" + ("ban" if ban else "kick"), "slot": slot})
        return f"{'banned' if ban else 'kicked'} slot {slot}"

    def run_command(line, now):
        command, value = host_ops.parse_command(line)
        if command is None:
            return value
        if command == "help":
            return host_ops.HELP
        if command == "status":
            return host_ops.player_table(players_now(now))
        if command == "end":
            if not arena_players or match.started is None:
                return "no match in progress"
            end_match("ended by host", now)
            return "match ended"
        if command in ("say", "quit"):
            text = value if command == "say" else "Host is shutting down"
            for peer in list(arena_players) if args.arena else []:
                arena.sendto(aoanet.encode(*arena_message(text), key), peer)
            log({"t": round(time.time(), 3), "event": "host_" + command})
            return host_ops.QUIT if command == "quit" else f"said to {len(arena_players)} player(s)"
        return remove_by_host(value, command == "ban")

    print(f"station stub on {args.bind_address}:{s.getsockname()[1]} (replies {'ON' if reply else 'off'})", flush=True)
    if console is not None:
        print("Host console ready. " + host_ops.HELP, flush=True)
    end = time.monotonic() + seconds if seconds else None
    while end is None or time.monotonic() < end:
        now = time.monotonic()
        if args.managed_session:
            if arena_connections:
                idle_since = now
            if next_player_slot - 1 >= args.recycle_arena_joins:
                schedule_restart("arena admission threshold", now)
            elif station.next_id - 1 >= args.recycle_station_admissions:
                schedule_restart("Station admission threshold", now)
            elif (args.idle_recycle and not arena_connections and station.next_id > 1
                  and now - idle_since >= args.idle_recycle):
                schedule_restart("idle session cleanup", now)
            if restart_due is not None:
                if now >= restart_due:
                    log({"t": round(time.time(), 3), "event": "session_restart", "reason": restart_reason,
                         "map": args.map, "next_map": args.next_map})
                    if args.status_file is not None:
                        host_ops.write_status(args.status_file, host_status(now))
                    return SESSION_COMPLETE
                for threshold in (10, 5):
                    if threshold < args.restart_warning and restart_due - now <= threshold and threshold not in restart_notices:
                        restart_notices.add(threshold)
                        announce_restart(now)
        for sock in sockets:
            sock.flush(now)
        for peer in list(overflowed):
            depart(peer, "reliable event queue overflow")
        overflowed.clear()
        if console is not None:
            for line in console.drain():
                response = run_command(line, now)
                if response:
                    print(response, flush=True)
                if response == host_ops.QUIT:
                    end = now  # leave the loop; ExitStack cleanup still runs
        if args.status_file is not None and now >= status_due:
            try:
                host_ops.write_status(args.status_file, host_status(now))
            except OSError as error:
                print(f"status file not written: {error}", flush=True)
            status_due = now + 2
        for peer, state in list(station.peers.items()):
            if now >= state["expiry"]:
                station_depart(peer, "inactivity timeout")
        for peer, packet in station.pings(now):
            s.sendto(aoanet.encode(*packet, key), peer)
        retries, failed = removals.due(time.monotonic())
        for peer in failed:
            depart(peer, "essential event unacknowledged")
        for peer, packet in retries:
            if peer in arena_connections:
                arena.sendto(aoanet.encode(*packet, key), peer)
        for peer, (due, step) in list(protection_probe.items()):
            if now < due or any(p == peer for p, _ in removals.pending):
                continue
            desired = (1, 1, 0, 0)[step]
            packet = removals.queue_message(peer, 0x81, bytes([desired]), now)
            if packet is None:
                depart(peer, "protection probe delivery exhausted")
                continue
            if packet:
                arena.sendto(aoanet.encode(*packet, key), peer)
            log({"t": round(time.time(), 3), "event": "protection_probe_step", "status": desired})
            print(f"Protection probe {step + 1}/4: state={desired}", flush=True)
            if step == 3:
                del protection_probe[peer]
            else:
                protection_probe[peer] = (now + 3, step + 1)
        for peer, due in list(expiry_due.items()):
            if time.monotonic() >= due:
                depart(peer, "inactivity timeout")
        if args.experimental_relay:
            if not arena_players:
                match.stop()
            elif match.started is not None:
                reason = match.ended(deaths.kills, now)
                if reason:
                    end_match(reason, now)
        if args.experimental_relay and now >= motion_refresh_due:
            for subject, state in arena_motion.items():
                if subject not in ping_due:
                    continue
                packet = aoanet.encode(0x1F, relay_motion.snapshot(arena_players[subject], state,
                                                                    stats=player_stats(subject)), key)
                for observer in ping_due:
                    if observer != subject:
                        arena.sendto(packet, observer)
            motion_refresh_due = now + 1
        for peer, due in list(bootstrap_due.items()):
            if time.monotonic() >= due:
                if args.experimental_relay:
                    for other, slot in arena_players.items():
                        if other != peer and other in bootstrap_due:
                            continue
                        # Its own record replaces the client's (0x4A641C): keep
                        # the Station ID that its TCP requests carry (9.40).
                        own_id = struct.unpack_from("<I", arena_connections[peer], 0x1F + 0x7B)[0]
                        deliver(peer, load_player(slot, arena_motion[other][0x40], arena_pilots.get(other),
                                                  ffa_team(slot) if args.experimental_teams else None,
                                                  arena_vessels.get(other, start_vessel),
                                                  own_id if other == peer else None), True)
                        if other != peer:
                            deliver(other, load_player(arena_players[peer], arena_motion[peer][0x40],
                                                       arena_pilots.get(peer),
                                                       ffa_team(arena_players[peer]) if args.experimental_teams
                                                       else None, arena_vessels.get(peer, start_vessel)), True)
                    for other, slot in arena_players.items():
                        if other != peer and other not in bootstrap_due:
                            arena.sendto(aoanet.encode(0x1F, relay_motion.snapshot(
                                slot, arena_motion[other], stats=player_stats(other)), key), peer)
                position = arena_motion[peer][0x40] if peer in arena_motion else None
                for packet in flight_bootstrap(position, online_terrain.marker(args.map)
                                               if args.experimental_terrain else None,
                                               arena_vessels.get(peer, start_vessel)):
                    deliver(peer, packet, True)
                if args.experimental_teams:
                    slot = arena_players[peer]
                    arena.sendto(aoanet.encode(*object_to_team(player_tag(slot), ffa_team(slot)), key), peer)
                if args.experimental_object:
                    rtype, rpay = scenario_test_object()
                    arena.sendto(aoanet.encode(rtype, rpay, key), peer)
                if powerups is not None:
                    for packet in powerups.spawns():
                        deliver(peer, packet, True)
                if targets is not None:
                    for packet in targets.loads():
                        deliver(peer, packet, True)
                for packet in buoys:
                    deliver(peer, packet, True)
                for packet in trial:
                    deliver(peer, packet, True)
                for packet in warp:
                    deliver(peer, packet, True)
                del bootstrap_due[peer]
                ping_due[peer] = time.monotonic()
                if args.experimental_protection_probe:
                    protection_probe[peer] = (time.monotonic() + 3, 0)
                if args.experimental_relay:
                    match.start(time.monotonic())
        if targets is not None:
            for packet in targets.respawns(time.monotonic()):
                for peer in arena_players:
                    if peer not in bootstrap_due:
                        deliver(peer, packet, True)
        for peer, due in list(ping_due.items()):
            now = time.monotonic()
            if now >= due:
                rtype, rpay = arena_ping(int(now * 1000))
                ticks = ping_ticks.setdefault(peer, [])
                ticks.append(rpay[:4])
                del ticks[:-4]
                arena.sendto(aoanet.encode(rtype, rpay, key), peer)
                ping_due[peer] = now + 1
        # BeginSerialLoad precedes Station dialog initialization. Wait until
        # its first server-list TCP job so the alias observer is registered.
        # This delivery timing is experimental, not a recovered server rule.
        # Bound each drain even if the TCP producer keeps replenishing it.
        for _ in range(notifications.qsize()):
            identity = notifications.get_nowait()
            peer = station.alias_target(identity, time.monotonic())
            if peer is not None:
                s.sendto(aoanet.encode(0x9A, pilot_list(station.peers[peer]["pilot"]), key), peer)
        ready = [sock for sock in sockets if sock.has_due()]
        if not ready:
            wait = 0.5
            for due in [sock.next_due() for sock in sockets] + [getattr(removals, "next_due", lambda: None)()]:
                if due is not None:
                    wait = min(wait, max(0.0, due - time.monotonic()))
            ready, _, _ = select.select(sockets, [], [], wait)
        if not ready:
            continue
        receiver = ready[0]
        sockets.remove(receiver)
        sockets.append(receiver)  # Fair service when both UDP channels stay ready.
        try:
            wire, addr = receiver.recvfrom(aoanet.MAX_WIRE + 1)
        except BlockingIOError:
            continue  # Held or dropped by test impairment.
        except ConnectionResetError:
            # Windows reports ICMP port-unreachable here after a client exits.
            # A dead test peer must not take down the other clients' listener.
            continue
        except OSError as error:
            # Windows raises WSAEMSGSIZE for a UDP datagram larger than the
            # buffer. POSIX truncates it to MAX_WIRE+1, rejected by decode.
            if error.errno == errno.EMSGSIZE or getattr(error, "winerror", None) == 10040:
                continue
            raise
        try:
            if not ingress.allow((receiver.getsockname()[1], addr), time.monotonic()):
                continue
            m = aoanet.decode(wire, key)
        except Exception as e:  # noqa: BLE001
            m = {"type": None, "payload": b"", "crc_ok": False, "error": repr(e)}
        rec = {"t": round(time.time(), 3), "from": f"{addr[0]}:{addr[1]}", "wire_len": len(wire),
               "udp_port": receiver.getsockname()[1],
               "type": m["type"], "name": TYPE_NAMES.get(m["type"], ""), "crc_ok": m["crc_ok"],
               "len": len(m["payload"]), "payload": m["payload"].hex()}
        log({"event": "udp_packet", **rec})
        if reply and m["crc_ok"]:
            message_type, payload = m["type"], m["payload"]
            if message_type == 0x1B:
                if len(payload) < 5:
                    continue
                rtype, rpay = ack_reliable(payload)
                receiver.sendto(aoanet.encode(rtype, rpay, key), addr)
                message_type, payload = payload[-1], payload[:-5]
                if message_type == 0x1B:
                    # Only one reliable envelope is supported. Do not let a
                    # nested envelope fall through to the stateless helper.
                    continue
                if (not inbound.first((receiver.getsockname()[1], addr), rpay)
                        and message_type not in InboundReliable.REPLAYABLE):
                    log({"t": round(time.time(), 3), "event": "reliable_duplicate", "type": message_type})
                    continue
            if message_type == 0x0A and len(payload) == 381:
                if struct.unpack_from("<III", payload, 1) != (9, 2, 2):
                    # Original 2.9.2 login error switch maps result 8 to
                    # 'Incorrect version.' Do not allocate on rejection.
                    receiver.sendto(aoanet.encode(*ack_connect(payload, kind=1 if receiver is s else 0, result=8), key), addr)
                    log({"t": round(time.time(), 3), "event": "admission_rejected", "reason": "unsupported client version"})
                    continue
            if addr[0] in banned_ips:
                continue
            if receiver is s:
                now = time.monotonic()
                if message_type == 0x0A and len(payload) == 381:
                    new_session = addr not in station.peers
                    if new_session and restart_due is not None:
                        receiver.sendto(aoanet.encode(*ack_connect(payload, result=4), key), addr)
                        continue
                    identity = station.admit(addr, payload, now)
                    if identity is not None:
                        if new_session and not arena_connections:
                            idle_since = now
                        if new_session and args.sustained_delivery:
                            # A player whose client crashed or lost its link logs in
                            # again from a new endpoint on the same IP. Remove the
                            # stale ship now instead of after the peer timeout. An
                            # active second client on the same PC is left alone.
                            for stale in [peer for peer in arena_connections if peer[0] == addr[0] and peer != addr
                                          and now - arena_heard.get(peer, now) >= REJOIN_SILENCE]:
                                depart(stale, "replaced by rejoin")
                                station_depart(stale, "replaced by rejoin")
                        refresh_server_list()
                        name = station.peers[addr]["pilot"] if args.guest_sessions else None
                        receiver.sendto(aoanet.encode(*ack_connect(payload, station_id=identity, pilot_name=name), key), addr)
                    elif addr not in station.peers and addr not in station.retired and station.next_id > station.CAPACITY:
                        receiver.sendto(aoanet.encode(*ack_connect(payload, result=4), key), addr)
                elif message_type == 0x4E and len(payload) == 1:
                    station_depart(addr, "client quit")
                elif message_type == 9:
                    station.heartbeat(addr, payload, now)
                continue
            if receiver is not s and message_type == 0x0A and len(payload) == 381:
                # Retries (including reliable wrappers) acknowledge the same
                # admission, without postponing or restarting flight. Endpoint
                # replacement needs an explicit departure/expiry policy first.
                first_join = addr not in arena_connections
                if first_join and restart_due is not None:
                    receiver.sendto(aoanet.encode(*ack_connect(payload, kind=0, result=4), key), addr)
                    continue
                if first_join and addr not in retired_endpoints and len(arena_connections) >= args.max_players:
                    receiver.sendto(aoanet.encode(*ack_connect(payload, kind=0, result=4), key), addr)
                    continue
                if first_join and (addr in retired_endpoints or
                                   len(arena_connections) + len(retired_endpoints) >= 49):
                    continue
                if not first_join and arena_connections[addr] != payload:
                    continue
                owner = None
                if args.guest_sessions:
                    owner = station.arena_owner(payload, addr, time.monotonic())
                    if owner is None:
                        receiver.sendto(aoanet.encode(*ack_connect(payload, kind=0, result=5), key), addr)
                        continue
                    arena_pilots[addr] = station.peers[station.routes[owner][0]]["pilot"]
                player_id = 1
                if args.experimental_relay:
                    if first_join:
                        if next_player_slot >= 50:
                            continue
                        arena_players[addr] = next_player_slot
                        next_player_slot += 1
                        arena_motion[addr] = relay_motion.initial(spawn_position(
                            arena_players[addr], args.spawn_axis, args.spawn_spacing, args.spawn_origin))
                    player_id = 0x80010000 | arena_players[addr]
                arena_connections[addr] = payload
                refresh_server_list()
                rtype, rpay = ack_connect(payload, 0, player_id)
                receiver.sendto(aoanet.encode(rtype, rpay, key), addr)
                if first_join and (args.experimental_flight or args.experimental_relay):
                    bootstrap_due[addr] = time.monotonic() + 3
                if first_join:
                    expiry_due[addr] = time.monotonic() + peer_timeout + (3 if addr in bootstrap_due else 0)
                    if owner is None and addr in station.peers and station.peers[addr]["arena"] is None:
                        # The 2.9.2 client uses one UDP socket for Station and
                        # arena. Bind them so Station stops pinging this socket
                        # once the arena owns it, and the lease follows arena
                        # activity (findings 9.28).
                        owner = station.peers[addr]["id"]
                    if owner is not None:
                        station.bind_arena(owner, addr, expiry_due[addr])
                continue
            if receiver is not s and addr in arena_connections:
                arena_heard[addr] = time.monotonic()
                if message_type == 0x0F:
                    removals.acknowledge(addr, payload)
                    continue
                if message_type == 0x4E and len(payload) == 1:
                    # SendImQuitting (0x4871C0) sends the reason byte, not a
                    # target slot. Only the sending endpoint can depart.
                    depart(addr, "client quit")
                    continue
                if message_type == 9 and len(payload) == 12:
                    ticks = ping_ticks.get(addr, [])
                    if payload[6] == arena_players.get(addr, 1) and payload[:4] in ticks:
                        ticks.remove(payload[:4])
                        sample = (int(time.monotonic() * 1000) - struct.unpack_from("<I", payload)[0]) & 0xFFFFFFFF
                        if sample < 60000:
                            previous = arena_rtt.get(addr)
                            arena_rtt[addr] = sample if previous is None else previous * 0.8 + sample * 0.2
                        expiry_due[addr] = time.monotonic() + peer_timeout
                        station.renew_arena(addr, expiry_due[addr])
                    continue
            if receiver is not s and args.experimental_relay:
                if (message_type == 0x1F and addr in arena_players and
                        addr not in bootstrap_due and len(payload) >= 8):
                    # Movement deltas are not made reliable by this stub;
                    # replaying a wrapped delta would apply it twice.
                    if m["type"] == 0x1B:
                        continue
                    p = movement_update(payload, arena_players[addr])
                    if p is not None:
                        try:
                            state, present, missing = relay_motion.update(p, arena_motion[addr])
                        except (ValueError, OverflowError):
                            continue
                        arena_motion[addr] = state
                        raw_mask = struct.unpack_from("<I", payload, 4)[0]
                        # Locate the client's own stats only when the relayed
                        # prefix/gun block match the original byte layout.
                        if not raw_mask & relay_motion.GUN_STATE or relay_motion.GUN_STATE in present:
                            try:
                                reported = relay_motion.client_stats(payload, len(p), raw_mask)
                            except ValueError:
                                reported = None
                            if reported is not None:
                                arena_reported[addr] = reported
                            if targets is not None:
                                try:
                                    hits = relay_motion.perceived_damage(payload, len(p), raw_mask)
                                except ValueError:
                                    hits = []
                                destroy_targets(targets.gun_hits(arena_vessels.get(addr, start_vessel), hits,
                                                                time.monotonic()), arena_players[addr])
                        p = relay_motion.snapshot(arena_players[addr], state, include_control=0x400 in present,
                                                  stats=player_stats(addr))
                        expiry_due[addr] = time.monotonic() + peer_timeout
                        station.renew_arena(addr, expiry_due[addr])
                        for peer in arena_players:
                            if peer != addr and peer not in bootstrap_due:
                                receiver.sendto(aoanet.encode(0x1F, p, key), peer)
                elif message_type == 0xA0 and addr in arena_players and addr not in bootstrap_due:
                    change_vessel(addr, payload)
                elif message_type == 0x44 and powerups is not None and addr in arena_players \
                        and addr not in bootstrap_due:
                    taken = powerups.pickup(payload, time.monotonic())
                    log({"t": round(time.time(), 3), "event": "powerup_pickup", "slot": arena_players[addr],
                         "status": taken[0] if taken else "rejected"})
                    if taken is not None:
                        for peer in list(ping_due):
                            deliver(peer, taken[1], True)
                elif message_type in (0x2A, 0x30, 0x37, 0x48) and addr in arena_players and addr not in bootstrap_due:
                    sender = arena_players[addr]
                    loaded = {slot: peer for peer, slot in arena_players.items() if peer not in bootstrap_due}
                    if message_type in (0x2A, 0x30):
                        # Optional ordered delivery shares the removal budget.
                        handle = missiles.launch if message_type == 0x2A else missiles.impact
                        result = handle(sender, payload, loaded, time.monotonic())
                        log({"t": round(time.time(), 3), "event": "missile_" + ("launch" if message_type == 0x2A
                                                                                else "impact"),
                             "slot": sender, "accepted": result is not None})
                        if result is not None:
                            for peer in loaded.values():
                                combat_send(peer, result)
                            if message_type == 0x30:
                                missile, hit = struct.unpack_from("<II", payload)
                                name = missiles.names.pop(missile, None)
                                if targets is not None:
                                    died = targets.missile_hit(hit, name, time.monotonic())
                                    destroy_targets([died] if died else [], sender)
                    elif message_type == 0x48:
                        target = collision_target(payload, sender, loaded)
                        if target is not None:
                            receiver.sendto(aoanet.encode(0x48, payload, key), loaded[target])
                    else:
                        death = deaths.report(sender, payload, loaded, time.monotonic())
                        if death is not None:
                            log({"t": round(time.time(), 3), "event": "player_died", "slot": sender,
                                 "reason": "killed" if death[1][4:] != bytes(4) else "no valid killer"})
                            for slot, peer in loaded.items():
                                if slot != sender:
                                    combat_send(peer, death)
                            # The victim resets itself to the origin (9.27);
                            # restore its assigned spawn like flight entry.
                            spawn = spawn_position(sender, args.spawn_axis, args.spawn_spacing, args.spawn_origin)
                            if addr in arena_connections:
                                deliver(addr, (0x24, struct.pack("<3f", *spawn)))
                            killer_slot = struct.unpack_from("<I", death[1], 4)[0] & 0xFFFF
                            for peer in {addr, loaded.get(killer_slot)} - {None}:
                                if peer in arena_connections:
                                    deliver(peer, own_record(peer))
            for rtype, rpay in udp_replies(message_type, payload, arena=receiver is not s):
                receiver.sendto(aoanet.encode(rtype, rpay, key), addr)


if __name__ == "__main__":
    raise SystemExit(main())
