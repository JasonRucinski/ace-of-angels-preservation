"""Combat ledgers of the relay: victim-reported deaths and server-tagged missiles."""
import math
import struct

from aoa.host import object_slots as slots
from aoa.protocol.arena import player_tag
from aoa.protocol.messages import NUL


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
    FIRST_INDEX, LAST_INDEX = slots.first("missiles"), slots.last("missiles")
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
            tag = slots.DYNAMIC_TAG | self.counter << 16 | index
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
