"""Arena messages of the 2.9.2 client: ship and player loads, teams, removals, collisions, text.

These build and check the wire layout only. Which vessels a host offers is
the host's rule (aoa/host/vessels.py), so a vessel here is any name that
fits its field.
"""
import math
import struct

from aoa.protocol.messages import NUL
from aoa.protocol.station import pilot_list


# Player relation index (the client stores index + 1 at player +0x1CC:
# 1 Friendly, 2 Unfriendly, 3 Neutral, 4 Hostile, 5 Allied; the "Set target
# to ..." commands at 0x442376 onwards use these values).
RELATION_HOSTILE = 3


def ship_request(payload):
    """The vessel name of a well-formed fighter request, or None.

    SendRequestCustomConfig (0x48A030, type 0xA0, 37 bytes) is the online
    fighter menu's confirm (0x466A2D): u32 config index, vessel[32], a zero
    byte. The client zeroes the block before copying the name.
    """
    if len(payload) != 0x25 or payload[0x24] or NUL not in payload[4:0x24]:
        return None
    name = payload[4:0x24].split(NUL, 1)[0].decode("latin1")
    return name


def load_ship(vessel, slot=0):
    """ReceiveLoadShip at 0x4306C1: vessel[64], database[64], player slot u8.

    Slot zero is the receiver's own ship; others are the receiver's world
    index for that player, which is the tag's low word (0x4A5DE0). It calls
    ChangeObjectVessel (0x4A7F90) directly, as the offline menu does.
    """
    if not vessel or len(vessel.encode()) >= 64 or not 0 <= slot < 50:
        raise ValueError("unknown vessel or slot")
    return 0x27, vessel.encode().ljust(64, NUL) + b"AoAObjects.odb".ljust(64, NUL) + bytes([slot])


def flight_bootstrap(vessel, position=None, terrain=None):
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


def remove_player(slot):
    """2.9.2 type 0x2D reads a u8 slot at 0x430710, calls RemovePlayer.

    The receiver has no tag/generation check. Never send slot zero (local).
    """
    if not 1 <= slot < 50:
        raise ValueError("player slot must be 1..49")
    return 0x2D, bytes([slot])


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


def load_player(slot, position, vessel, name=None, team=None, station_id=None):
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
    if not vessel or len(vessel.encode()) >= 20:
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
    struct.pack_into("<3f", p, 0x1A4, *position)
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
