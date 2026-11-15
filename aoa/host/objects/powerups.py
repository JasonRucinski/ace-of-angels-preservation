"""Server-placed power-ups."""
import math
import secrets
import struct

from aoa.host import object_slots as slots


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
    FIRST_INDEX, LAST_INDEX = slots.first("powerups"), slots.last("powerups")  # Between targets and missiles
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
        return slots.DYNAMIC_TAG | index

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
