"""Keep distant world models visible with their existing authored LODs.

Opt-in, reversible 2.9.2 patch: 4,500,000-unit surface-distance horizon and
a 0.5 projected-size minimum. Child selection clamps to the group's original
authored minimum so distant groups still have meshes to draw.
"""
import struct

from aoa.client import layout
from aoa.client.asm import Asm, jmp_patch
from aoa.client.patches import asteroid_render
from aoa.client.patches.base import Patch, Region

NAME = "distant-world-objects-v1"
HORIZON = 4_500_000.0
MIN_SIZE = 0.5
GROUP_SITE = 0x546BB3
GROUP_ORIGINAL = bytes.fromhex("8b54240455")  # mov edx,[esp+4]; push ebp
CHILD_SITE = 0x546BEA
CHILD_ORIGINAL = bytes.fromhex("85ff894c2434")  # test edi,edi; mov [esp+34],ecx
CAVE = layout.cave(NAME).start
CHILD_CAVE = CAVE + 0x20
CAVE_SIZE = layout.cave(NAME).size


def code():
    a = Asm(CAVE)
    a.emit(bytes.fromhex("8b5424048954240c"))  # save authored min in unused local
    a.emit(b"\xba", struct.pack("<f", MIN_SIZE))  # root visibility minimum
    a.emit(0x55)  # displaced push ebp; no flags or x87 state changed
    a.rel32(0xE9, GROUP_SITE + len(GROUP_ORIGINAL))
    group = a.resolve()
    assert CAVE + len(group) <= CHILD_CAVE

    a = Asm(CHILD_CAVE)
    # Two saved registers now precede the original frame: local +0xC is +0x14.
    # Sizes are nonnegative floats, so unsigned bit ordering matches float order.
    a.emit(bytes.fromhex("3b4c2414"))  # cmp ecx,[esp+14]
    a.rel8(0x73, "selected")  # actual size >= authored minimum
    a.emit(bytes.fromhex("8b4c2414"))  # select lowest authored LOD below its range
    a.label("selected")
    a.emit(bytes.fromhex("894c243485ff"))  # displaced store, then original flags
    a.rel32(0xE9, CHILD_SITE + len(CHILD_ORIGINAL))
    body = group.ljust(CHILD_CAVE - CAVE, b"\0") + a.resolve()
    assert len(body) <= CAVE_SIZE
    return body.ljust(CAVE_SIZE, b"\0")


# The two horizon constants are shared: asteroid-mesh-distance-v1 reads both
# and solid-world-mesh-distance-v1 reads the 900,000 one, so with this patch
# on their horizons are 4,500,000 too (tests/test_patch_layout.py states the
# combined effect). No shared 5.0 is modified.
PATCH = Patch(
    id=NAME, since=22, policy="option", option="distant_objects",
    label="Distant objects — extended visibility", group="visual",
    regions=(
        Region(asteroid_render.MESH_HORIZON, struct.pack("<f", 61_000), struct.pack("<f", HORIZON), "const"),
        Region(asteroid_render.BILLBOARD_HORIZON, struct.pack("<f", 900_000), struct.pack("<f", HORIZON), "const"),
        Region(0x54326A, bytes.fromhex("d81d84fc5800"),
               bytes.fromhex("d81d40ed5800")),  # compare size to existing 0.5, not 5.0
        Region(GROUP_SITE, GROUP_ORIGINAL, jmp_patch(GROUP_SITE, CAVE, len(GROUP_ORIGINAL))),
        Region(CHILD_SITE, CHILD_ORIGINAL, jmp_patch(CHILD_SITE, CHILD_CAVE, len(CHILD_ORIGINAL))),
        Region(CAVE, bytes(CAVE_SIZE), code(), "cave")))
