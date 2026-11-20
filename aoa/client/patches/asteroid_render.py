"""Opt-in 2.9.2 asteroid mesh rendering instead of distant cached billboards.

Only the surface-distance gate for model names Astr-* / Astr_* changes.
Texture LOD, geometry, transforms, and all other models retain original code.
Visual acceptance and performance require a real flight test.
"""
from aoa.client import layout
from aoa.client.asm import Asm, jmp_patch
from aoa.client.patches.base import Patch, Region

NAME = "asteroid-mesh-distance-v1"
SITE = 0x543222
CAVE = layout.cave(NAME).start
MESH_HORIZON = 0x5B0C30       # 61000.0, the world mesh gate
BILLBOARD_HORIZON = 0x59D9C0  # 900000.0, the cached billboard horizon
ORIGINAL = bytes.fromhex("d81d300c5b00")  # fcomp [61000.0]


def code():
    a = Asm(CAVE)
    a.emit(0x9C, 0x50)  # preserve integer flags and eax; ST0 is surface distance
    a.emit(bytes.fromhex("8b462085c0"))  # model-name pointer at node+20
    a.rel8(0x74, "ordinary")
    # Byte comparisons stop at the first mismatch, including short strings.
    for offset, char in enumerate(b"Astr"):
        a.emit(bytes([0x80, 0x38, char]) if offset == 0
               else bytes([0x80, 0x78, offset, char]))
        a.rel8(0x75, "ordinary")
    a.emit(bytes.fromhex("8078042d"))
    a.rel8(0x74, "asteroid")
    a.emit(bytes.fromhex("8078045f"))
    a.rel8(0x75, "ordinary")
    a.label("asteroid")
    a.emit(bytes.fromhex("d81dc0d95900"))  # original billboard horizon, 900000.0
    a.rel8(0xEB, "done")
    a.label("ordinary")
    a.emit(ORIGINAL)
    a.label("done")
    a.emit(0x58, 0x9D)
    a.rel32(0xE9, SITE + len(ORIGINAL))
    return a.resolve()


# Reads both horizon constants, which distant-world-objects-v1 rewrites to
# 4,500,000 (declared in its `reads`; see tests/test_patch_layout.py).
PATCH = Patch(
    id=NAME, since=None, policy="option", option="experimental_asteroids",
    label="Asteroid models only — reduce shape popping", group="experimental",
    conflicts=("solid-world-mesh-distance-v1",), reads=(MESH_HORIZON, BILLBOARD_HORIZON),
    regions=(Region(SITE, ORIGINAL, jmp_patch(SITE, CAVE, len(ORIGINAL))),
             Region(CAVE, bytes(len(code())), code(), "cave")))
