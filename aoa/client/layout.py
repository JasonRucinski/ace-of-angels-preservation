"""Where the client patches put new code and runtime state: one table.

logger-size-v1 maps two zero-filled areas of the 2.9.2 client (it raises
the .text and .data VirtualSize): the end of .text, file-backed padding the
original never used, and the tail of .data, which exists only at run time.
Every code cave and every runtime variable a patch adds is reserved here,
with its owner's patch ID; a module takes its addresses from this table, and
tests/test_patch_layout.py checks that reservations are disjoint, inside
these bounds, and hold every cave region of their owner. A reservation is
usually larger than the code in it; the free space lets a cave grow without
moving its neighbours.

Addresses are evidence-backed (prepared clients carry them): never move one.
A new patch takes a free range; `free()` lists them.
"""
from dataclasses import dataclass

TEXT_PADDING = (0x58B200, 0x58C000)   # .text after the original VirtualSize 0x18A1E0
DATA_TAIL = (0x60D200, 0x60E000)      # .data after the original VirtualSize 0x4C10C, up to .rsrc


@dataclass(frozen=True)
class Reservation:
    start: int
    size: int
    owner: str      # patch ID
    what: str = ""  # what it holds; names it when the owner has several

    @property
    def end(self):
        return self.start + self.size


CAVES = (
    Reservation(0x58B200, 0xC0, "logger-lock-v1", "spinlock and logger hooks"),
    Reservation(0x58B2C0, 0x40, "powerup-pickup-v1"),
    Reservation(0x58B300, 0x100, "cursor-warp-origin-v1"),
    Reservation(0x58B400, 0x40, "zero-time-physics-v1"),
    Reservation(0x58B440, 0x40, "archive-terminator-v1"),
    Reservation(0x58B480, 0x80, "explicit-protection-v1"),
    Reservation(0x58B500, 0x100, "ship-menu-aspect-v1"),
    Reservation(0x58B600, 0x80, "frame-clock-v1", "clock"),
    Reservation(0x58B680, 0x80, "frame-clock-v1", "gate"),
    Reservation(0x58B700, 0x100, "visibility-math-v1"),
    Reservation(0x58B800, 0x200, "online-terrain-v3", "hook code and map table"),
    Reservation(0x58BA00, 0x100, "asteroid-mesh-distance-v1"),
    Reservation(0x58BB00, 0x80, "station-full-detail-v1"),
    Reservation(0x58BB80, 0x80, "distant-world-objects-v1", "group and child hooks"),
    Reservation(0x58BC00, 0x200, "third-person-camera-v3", "caves A, B and R"),
    Reservation(0x58BE00, 0x100, "own-ship-model-v1"),
    Reservation(0x58BF00, 0x100, "own-ship-menu-model-v1"),
)
DATA = (
    Reservation(0x60D200, 0x8, "logger-lock-v1", "lock owner and depth"),
    Reservation(0x60D300, 0xEC, "third-person-camera-v3", "camera copy FAKE, NODE, TICK"),
    Reservation(0x60D3EC, 0x4, "own-ship-menu-model-v1", "RESTRICT"),
    Reservation(0x60D3F0, 0xC, "third-person-camera-v3", "ORBIT, START, ARMED"),
)


def _find(table, owner, what):
    found = [r for r in table if r.owner == owner and what in (None, r.what)]
    if len(found) != 1:
        raise KeyError(f"no single reservation for {owner}" + (f" {what!r}" if what else ""))
    return found[0]


def cave(owner, what=None):
    """The .text reservation of a patch (by patch ID and, if it has several, by `what`)."""
    return _find(CAVES, owner, what)


def data(owner, what=None):
    """A runtime .data reservation of a patch (by patch ID and, if it has several, by `what`)."""
    return _find(DATA, owner, what)


def free(table=CAVES, bounds=TEXT_PADDING):
    """(start, end) of every unreserved range inside bounds."""
    out, at = [], bounds[0]
    for r in sorted(table, key=lambda r: r.start):
        if r.start > at:
            out.append((at, r.start))
        at = max(at, r.end)
    if at < bounds[1]:
        out.append((at, bounds[1]))
    return out
