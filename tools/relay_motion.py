"""Recovered 2.9.2 safe movement prefix; not authoritative game physics.

Names remain destination offsets where physical semantics are unverified.
Order and scaling come from decoder 0x495330..0x49585F. Unknown initial
delta bases stay unknown until an absolute value arrives.
"""
import math
import struct

SMALL_DELTA_SCALE = struct.unpack("<f", bytes.fromhex("bd370635"))[0]
# (absolute flag, destination offset, format, delta scale). Scale None means
# scalar/no delta. The 0x400/0x800 pair is a signed integer replacement.
FIELDS = (
    (0x40, 0x6C, "3f", None),
    (1, 0x50, "3f", 1.0),
    (8, 0xE4, "3f", 1.0),
    (0x40000, 0x5C, "3f", 1.0),
    (0x80, 0xE0, "f", None), (0x100, 0xDC, "f", None), (0x200, 0xD8, "f", None),
    (0x400, 0xF0, "i", None),
    (0x1000, 0x40, "f", None), (0x2000, 0x3C, "f", None), (0x4000, 0x38, "f", None),
    (0x8000, 0x4C, "f", None), (0x10000, 0x48, "f", None), (0x20000, 0x44, "f", None),
    (0x200000, 0x84, "3f", SMALL_DELTA_SCALE),
    (0x1000000, 0x78, "3f", SMALL_DELTA_SCALE),
)


# Per-gun fire state that follows the prefix (decoder 0x49585F): u8 header
# (low 7 bits count, high bit to player +0x1A4), then count x (u16 system
# index, u8 value); the receiver stores value*0.1 in that gun (0x4DACF0).
# The decoder increments its own 5000-entry array at the index without a
# bounds check, so only small indexes are relayed (findings 9.26).
GUN_STATE = 0x10000000
MAX_SYSTEM_INDEX = 128
RELAYED_MASK = 0x07FFFFFF | GUN_STATE


def gun_state(payload, offset):
    """Parse one gun-state block; returns ((header, records), end offset)."""
    if offset >= len(payload):
        raise ValueError("truncated gun state")
    header = payload[offset]
    count = header & 0x7F
    end = offset + 1 + 3 * count
    if end > len(payload):
        raise ValueError("truncated gun state")
    records = tuple(struct.unpack_from("<HB", payload, offset + 1 + 3 * i) for i in range(count))
    if any(index >= MAX_SYSTEM_INDEX for index, _ in records):
        raise ValueError("gun system index out of range")
    return (header, records), end


# Player stats ride in the 0x80000000 block (u32 submask; decoder 0x495954):
# submask 0x100 = u16 kills, u16 deaths, u16 rating (to player +0x328),
# u16 unused, i32 score; ReceivePositionUpdate applies them with SetStats
# (0x493670: info +0x7F kills, +0x83 deaths, +0x4E score). Other submask
# parts write through pointers the receiver leaves unset, so the relay never
# forwards client blocks: it emits submask 0x100 alone (findings 9.30).
STATS = 0x80000000
STATS_SUBMASK = 0x100
STATS_FORMAT = "<IhhhHi"  # submask, kills, deaths, rating, unused, score
# Sizes of the submask parts the decoder reads before 0x100, in its order.
_BEFORE_STATS = ((0x20, 1), (0x4, 1), (0x8, 1), (0x10, 2), (0x40, 2))


def client_stats(payload, offset, mask):
    """(rating, score) from a client's own stats, or None.

    offset is where the 0x20000000 block would start (after the prefix and
    gun state). Raises ValueError on a truncated block.
    """
    if not mask & STATS:
        return None
    offset += (12 if mask & 0x20000000 else 0) + (2 if mask & 0x40000000 else 0)
    if offset + 4 > len(payload):
        raise ValueError("truncated stats submask")
    submask = struct.unpack_from("<I", payload, offset)[0]
    offset += 4
    if submask & 1:
        offset += 15
    if submask & 2:
        if offset >= len(payload):
            raise ValueError("truncated stats list")
        offset += 1 + 6 * payload[offset]
    for bit, size in _BEFORE_STATS:
        if submask & bit:
            offset += size
    found = None
    if submask & STATS_SUBMASK:
        if offset + 12 > len(payload):
            raise ValueError("truncated stats")
        _, _, rating, _, score = struct.unpack_from("<hhhHi", payload, offset)
        found, offset = (rating, score), offset + 12
    if submask & 0x200:
        # The variant real 2.9.2 clients send (decoder 0x495B21): 30 bytes,
        # rating u16 at +4, score i32 at +26.
        if offset + 30 > len(payload):
            raise ValueError("truncated full stats")
        found = (struct.unpack_from("<h", payload, offset + 4)[0],
                 struct.unpack_from("<i", payload, offset + 26)[0])
    return found


def perceived_damage(payload, offset, mask):
    """The shooter's reported hits: [(victim tag, gun system index, hits)].

    Submask 2 of the 0x80000000 block (encoder 0x49494A, from the list at
    world+0xDF034 that the gunshot pass 0x48F730 fills through 0x493480 for
    the local player's own shots): u8 count, then count x (u32 tag, u8 gun
    +0xA4, u8 hits). The client clears the list after each send (0x493460).
    offset is as for client_stats. Raises ValueError on a truncated block.
    """
    if not mask & STATS:
        return []
    offset += (12 if mask & 0x20000000 else 0) + (2 if mask & 0x40000000 else 0)
    if offset + 4 > len(payload):
        raise ValueError("truncated stats submask")
    submask = struct.unpack_from("<I", payload, offset)[0]
    offset += 4 + (15 if submask & 1 else 0)
    if not submask & 2:
        return []
    if offset >= len(payload) or offset + 1 + 6 * payload[offset] > len(payload):
        raise ValueError("truncated perceived damage")
    return [struct.unpack_from("<IBB", payload, offset + 1 + 6 * i) for i in range(payload[offset])]


def stats_block(kills, deaths, rating, score):
    return struct.pack(STATS_FORMAT, STATS_SUBMASK, kills, deaths, rating, 0, score)


def initial(position):
    return {0x40: tuple(position), 1: (0.0, 0.0, 0.0)}


def update(payload, previous):
    """Apply one filtered record atomically; reject non-finite values anywhere.

    Returns (new state, absolute flags present, unresolved delta flags).
    This cannot detect upstream UDP loss/reordering: the legacy prefix carries
    no proven sequence number. It prevents downstream loss of a delta from
    poisoning the observer's next absolute refresh.
    """
    if len(payload) < 8:
        raise ValueError("truncated movement header")
    trip, slot, mask = struct.unpack_from("<HHI", payload)
    if not trip & 0x8000 or not 1 <= slot < 50 or mask & ~RELAYED_MASK:
        raise ValueError("invalid filtered movement header")
    result, present, missing = dict(previous), set(), set()
    offset = 8
    for flag, destination, fmt, scale in FIELDS:
        delta = False
        if mask & flag:
            wire_format = fmt
        elif scale is not None and mask & (flag << 1 | flag << 2):
            wire_format = "3h" if mask & flag << 1 else "3b"
            delta = True
        elif flag == 0x400 and mask & 0x800:
            wire_format = "h"
        else:
            continue
        size = struct.calcsize("<" + wire_format)
        if offset + size > len(payload):
            raise ValueError("truncated movement field")
        values = struct.unpack_from("<" + wire_format, payload, offset)
        offset += size
        present.add(flag)
        if delta:
            if flag not in result:
                missing.add(flag)
                continue
            values = tuple(base + change * scale for base, change in zip(result[flag], values))
            try:
                values = struct.unpack("<3f", struct.pack("<3f", *values))
            except OverflowError as error:
                raise ValueError("movement float overflow") from error
        if any(not math.isfinite(value) for value in values):
            raise ValueError("non-finite movement field")
        result[flag] = values
    if mask & GUN_STATE:
        result[GUN_STATE], offset = gun_state(payload, offset)
        present.add(GUN_STATE)
    if offset != len(payload):
        raise ValueError("unexpected filtered movement suffix")
    return result, present, missing


def snapshot(slot, state, include_control=False, stats=None):
    """Absolute snapshot of observed state, with unknown fields omitted.

    0x400 (player +0xF4 status flags, e.g. 0x40 while guns fire) also
    refreshes a client timer via 0x4BE950. Never repeat it in periodic or
    late-join snapshots. The latest gun state is absolute and idempotent on
    the receiver (the decoder clears its counters per update), so it is
    always repeated.
    """
    mask, body = 0, bytearray()
    for flag, destination, fmt, scale in FIELDS:
        if flag not in state or flag == 0x400 and not include_control:
            continue
        mask |= flag
        body.extend(struct.pack("<" + fmt, *state[flag]))
    if GUN_STATE in state:
        header, records = state[GUN_STATE]
        mask |= GUN_STATE
        body.append(header)
        for index, value in records:
            body.extend(struct.pack("<HB", index, value))
    if stats is not None:
        # Server-owned (kills, deaths, rating, score); absolute and idempotent.
        mask |= STATS
        body.extend(stats_block(*stats))
    return struct.pack("<HHI", 0x8000, slot, mask) + body
