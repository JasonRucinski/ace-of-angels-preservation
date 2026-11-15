"""Passive server-owned target ships."""
import math
import struct

from aoa.host import object_slots as slots, vessel_combat


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
    FIRST_INDEX, LAST_INDEX = slots.TARGETS_FIRST, slots.TARGETS_END - 1  # After the test object, before power-ups
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
        return slots.OBJECT_TAG | index

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
