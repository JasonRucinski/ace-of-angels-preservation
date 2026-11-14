"""Give the player's own ship a drawable 3D model for the F2 chase camera.

Two things keep your own hull off screen even after third-person-camera-v1
enables and culls its node (findings 9.39):

  * No model. The world dispatches object creation (0x4A36F5) to the app's
    handler 0x44C0A0(object, is_self), with is_self = (object tag +0x178 ==
    the local player's tag, world+0xD3424). The handler attaches the ship's
    meshes (0x43DF70: renderer into the draw list, 0x51870007 links on the
    nodes) only when is_self is 0. Patch: NOP the `jne` at 0x44C0C5, so your
    ship gets the same meshes as any other ship.
  * Hidden level-of-detail children. The shared ship renderer draws an
    instance only while its LOD child is visible (+0x151, via 0x542990).
    Every frame, after rendering, 0x48F730 sets all of your ship's children
    visible, does its own work, then forces them back to 0 (0x48FAE5). So
    they are hidden at the next frame's render. Patch: that store writes the
    chase flag (0x5E6879) instead of 0: unchanged in cockpit view, visible
    with F2 on.

In cockpit view nothing new is drawn: the mesh draw (0x568DE0) first needs
the ship's top node enabled (+0x150), which the frame (0x44A097) and the
renderer (0x43B42C) clear every frame unless the chase camera is on.

Library use only (prepare_client.py composes it); no file is written here.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from patch_client import Asm, jmp_patch  # noqa: E402
from third_person import CHASE_FLAG  # noqa: E402

NAME = "own-ship-model-v1"
MODEL_SITE = 0x44C0C5                 # jne 0x44C0D8 (skip when is_self)
MODEL_ORIGINAL = bytes.fromhex("7511")
CHILD_SITE = 0x48FAE5                 # mov byte [ecx+0x151], 0 (own LOD children)
CHILD_ORIGINAL = bytes.fromhex("c6815101000000")
CHILD_RESUME = 0x48FAEC
CAVE = 0x58BE00                       # after the third-person caves
CAVE_END = 0x58BF00


def code():
    a = Asm(CAVE)
    a.emit(b"\x80\x3d", CHASE_FLAG.to_bytes(4, "little"), 0x00)   # cmp byte [flag], 0
    a.emit(b"\x0f\x95\x81\x51\x01\x00\x00")                       # setne [ecx+0x151]
    a.rel32(0xE9, CHILD_RESUME)
    return a.resolve()


def regions():
    """(file offset, original bytes, patched bytes); image base 0x400000."""
    body = code()
    assert CAVE + len(body) <= CAVE_END
    return [(MODEL_SITE - 0x400000, MODEL_ORIGINAL, b"\x90\x90"),
            (CAVE - 0x400000, bytes(len(body)), body),
            (CHILD_SITE - 0x400000, CHILD_ORIGINAL, jmp_patch(CHILD_SITE, CAVE, len(CHILD_ORIGINAL)))]


def state(data):
    """True if applied, False if absent; raises on anything else."""
    found = set()
    for offset, old, new in regions():
        actual = data[offset:offset + len(old)]
        if actual == old:
            found.add(False)
        elif actual == new:
            found.add(True)
        else:
            raise ValueError("unexpected own-ship model code or cave")
    if len(found) != 1:
        raise ValueError("partial own-ship model patch")
    return found.pop()


def configure(data, enabled=True):
    state(data)
    out = bytearray(data)
    for offset, old, new in regions():
        out[offset:offset + len(old)] = new if enabled else old
    return bytes(out)
