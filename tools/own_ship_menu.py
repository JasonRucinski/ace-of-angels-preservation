"""Keep your own hull drawn after the fighter menu previewed its model.

The fighter-select window (FighterSelectWin, 0x465EAB) gets the ship model's
renderer by name through 0x569380, the same shared renderer real ships of that
model use, and calls 0x5686A0(0): renderer +0x31 = 0 and every part's +0x244 = 0,
so its preview stays out of the main view. Nothing sets them back (every caller
of 0x5686A0 passes 0). It also clears each part's +0x245 (0x466033,
0x4660C9), the flag that makes the part draw (0x56D9F0, 0x56DD72) set its
instance's world transform. After an in-flight switch to a model the menu
showed, your new hull attaches to those parts: the main mesh pass (0x56ECC0)
skips them at the +0x244 check, and past that they would be drawn with the
previous object's transform (findings 9.41). The parts' instance lists still
hold the preview's node, so re-enabling them could draw a stray preview. The
menu's own draw (0x568DE0, 0x568F7D) re-sets +0x245 each time it draws.

own-ship-menu-model-v1, two hooks in 0x56ECC0:
  * part check (0x56ECDC, `mov al,[edi+0x244]`): stores the flag in RESTRICT.
    A part with the flag off is still walked when the chase flag (0x5E6879)
    is on; otherwise the original skip happens.
  * instance check (0x56ED01, `call 0x542990`): after the original drawable
    test, a restricted part only draws instances whose parent (+0x144) is the
    player's top node ([world+0xD3448]), i.e. your own ship's LOD children,
    and sets that part's +0x245 back to 1 so it uses your ship's transform.
With F2 off, and for every part the menu never touched, behaviour is unchanged.

Library use only (prepare_client.py composes it); no file is written here.
"""
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from patch_client import Asm, jmp_patch  # noqa: E402
from third_person import CHASE_FLAG, TICK  # noqa: E402

NAME = "own-ship-menu-model-v1"
PART_SITE = 0x56ECDC                      # mov al, byte [edi+0x244]
PART_ORIGINAL = bytes.fromhex("8a8744020000")
PART_RESUME = 0x56ECE2                    # test al, al ; je skip part
INSTANCE_SITE = 0x56ED01                  # call 0x542990 (instance drawable?)
INSTANCE_ORIGINAL = bytes.fromhex("e88a3cfdff")
DRAWABLE = 0x542990
WORLD = 0x5E7728
PLAYER_NODE = 0xD3448                     # world + this = the player's top render node
CAVE = 0x58BF00                           # after own_ship_model's cave
CAVE_END = 0x58C000
RESTRICT = TICK + 8                       # .data tail byte after third_person's state


def d32(value):
    return struct.pack("<I", value)


def code(legacy=False):
    """legacy=True builds the first cave (no +0x245 restore), kept for upgrades."""
    a = Asm(CAVE)
    a.label("part")
    a.emit(b"\x8a\x87\x44\x02\x00\x00")                    # mov al,[edi+0x244]
    a.emit(0xA2, d32(RESTRICT))                            # RESTRICT = al
    a.emit(b"\x84\xc0")
    a.rel8(0x75, "part_back")                              # flag on: original path
    a.emit(b"\x80\x3d", d32(CHASE_FLAG), 0x00)             # chase off: original skip
    a.rel8(0x74, "part_back")
    a.emit(b"\xb0\x01")                                    # walk the part anyway
    a.label("part_back")
    a.rel32(0xE9, PART_RESUME)
    a.label("instance")
    a.rel32(0xE8, DRAWABLE)                                # original test, ecx = instance
    a.emit(b"\x84\xc0")
    a.rel8(0x74, "done")
    a.emit(b"\x80\x3d", d32(RESTRICT), 0x00)
    a.rel8(0x75, "done")                                   # unrestricted part: drawable
    a.emit(0xA1, d32(WORLD))                               # mov eax,[world]
    a.emit(b"\x85\xc0")
    a.rel8(0x74, "done")
    a.emit(b"\x8b\x80", d32(PLAYER_NODE))                  # mov eax,[eax+0xD3448]
    a.emit(b"\x85\xc0")
    a.rel8(0x74, "done")
    a.emit(b"\x39\x86\x44\x01\x00\x00")                    # cmp [esi+0x144], eax
    if legacy:
        a.emit(b"\x0f\x94\xc0")                            # al = own child?
    else:
        a.rel8(0x75, "not_own")
        a.emit(b"\xc6\x87\x45\x02\x00\x00\x01")            # part +0x245 = 1 (own transform)
        a.emit(b"\xb0\x01\xc3")                            # al = 1; ret
        a.label("not_own")
        a.emit(b"\x31\xc0")                                # al = 0
    a.label("done")
    a.emit(0xC3)
    return a.resolve(), a.labels


def regions(legacy=False):
    """(file offset, original bytes, patched bytes); image base 0x400000."""
    body, labels = code(legacy)
    assert CAVE + len(body) <= CAVE_END
    call = b"\xe8" + struct.pack("<i", labels["instance"] - (INSTANCE_SITE + 5))
    return [(CAVE - 0x400000, bytes(len(body)), body),
            (PART_SITE - 0x400000, PART_ORIGINAL, jmp_patch(PART_SITE, labels["part"], len(PART_ORIGINAL))),
            (INSTANCE_SITE - 0x400000, INSTANCE_ORIGINAL, call)]


def matches(data, legacy):
    """True/False if every region is patched/original for this variant, else None."""
    found = set()
    for offset, old, new in regions(legacy):
        actual = data[offset:offset + len(old)]
        if actual == old:
            found.add(False)
        elif actual == new:
            found.add(True)
        else:
            return None
    return found.pop() if len(found) == 1 else None


def state(data):
    """True if applied (current or the first cave), False if absent; raises otherwise."""
    for legacy in (False, True):
        found = matches(data, legacy)
        if found is not None:
            return found
    raise ValueError("unexpected or partial own-ship menu-model patch")


def configure(data, enabled=True):
    state(data)
    out = bytearray(data)
    if matches(data, True):                    # remove the first cave before applying
        for offset, old, new in regions(True):
            out[offset:offset + len(old)] = old
    for offset, old, new in regions():
        out[offset:offset + len(old)] = new if enabled else old
    return bytes(out)
