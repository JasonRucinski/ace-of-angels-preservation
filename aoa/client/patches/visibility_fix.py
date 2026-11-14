"""Bounded trigonometry in the 2.9.2 visibility routine (render-pipeline-audit.md).

0x543000 computes a node's camera-relative direction, dots it with the camera
forward vector (+0x174) and, for larger projected sizes, at 0x5431A1 calls
acos(dot) and asin(radius/distance) to compare the node's angular extent with
the view cone. Two inputs leave the functions' domains:

  * at single precision the dot product can exceed 1 by an ulp (and fall below
    -1); acos returns NaN, every comparison is unordered, and the node counts as
    visible even when it is directly behind the camera;
  * with the camera inside the node's bounding sphere (distance <= radius),
    radius/distance > 1; asin returns NaN and the node is visible via the same
    unordered comparison, with NaN stored as its angular bound (+0x170).

This patch (Codex's offline culling correction, findings 9.36) clamps the dot
to [-1, 1] before the original acos call, and treats a camera inside the
sphere as visible with a finite bound of 1.0, as the original effectively did.

Deliberately left unchanged: the exact-centre case (distance 0). The original
marks such a node invisible before any trigonometry (0x543126), and that is
how the player's own ship stays hidden: in flight its render node is at
distance 0.0 from the camera every frame. The offline experiment made it
visible; promoted, that would draw the player's own hull at the camera.

Library use only (prepare_client.py composes it); no file is written here.
"""
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from patch_client import Asm, jmp_patch  # noqa: E402

NAME = "visibility-math-v1"
CENTER_VISIBLE = False      # distance-0 nodes keep the original (hidden) result
SITE = 0x5431A1
ORIGINAL = bytes.fromhex("d98674010000")  # fld dword [esi+174] ; the dot, for acos
ACOS_CALL = 0x5431A7                     # call _CIacos, consumes ST0
VISIBILITY_DONE = 0x543238               # mov [esi+154], al ; then LOD selection
CAVE = 0x58B700                          # below online terrain (0x58B800)


def code(cave=CAVE):
    a = Asm(cave)
    a.emit(bytes.fromhex("d98668010000d89e64010000dfe0f6c441"))  # distance <= radius?
    a.rel8(0x75, "inside")
    a.emit(bytes.fromhex("d98674010000d9e8d8d9dfe0f6c401"))      # dot; is 1 < dot?
    a.rel8(0x74, "lower")
    a.emit(bytes.fromhex("ddd8d9e8"))                            # replace with +1
    a.label("lower")
    a.emit(bytes.fromhex("d9e8d9e0d8d9dfe0f6c401"))              # is -1 < dot?
    a.rel8(0x75, "acos")
    a.emit(bytes.fromhex("ddd8d9e8d9e0"))                        # replace with -1
    a.label("acos")
    a.rel32(0xE9, ACOS_CALL)
    a.label("inside")
    a.emit(bytes.fromhex("c786700100000000803f"))                # bound = 1.0
    a.emit(bytes.fromhex("c6865301000001b801000000"))            # visible; eax = 1
    a.rel32(0xE9, VISIBILITY_DONE)
    return a.resolve()


def regions():
    """(file offset, original bytes, patched bytes); image base 0x400000."""
    body = code()
    assert CAVE + len(body) <= 0x58B800
    return [(CAVE - 0x400000, bytes(len(body)), body),
            (SITE - 0x400000, ORIGINAL, jmp_patch(SITE, CAVE, len(ORIGINAL)))]


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
            raise ValueError("unexpected visibility-math code or cave")
    if len(found) != 1:
        raise ValueError("partial visibility-math patch")
    return found.pop()


def configure(data, enabled=True):
    state(data)
    out = bytearray(data)
    for offset, old, new in regions():
        out[offset:offset + len(old)] = new if enabled else old
    return bytes(out)
