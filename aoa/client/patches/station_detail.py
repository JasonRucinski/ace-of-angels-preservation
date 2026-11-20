"""Pin Hy_base1 child mesh selection to its original closest detail level."""
from aoa.client import layout
from aoa.client.asm import Asm, jmp_patch
from aoa.client.patches.base import Patch, Region

NAME = "station-full-detail-v1"
SITE = 0x546BE4
CAVE = layout.cave(NAME).start
ORIGINAL = bytes.fromhex("8b8e7c010000")  # mov ecx,[esi+17c]
MODEL = b"Hy_base1\0"


def code():
    a = Asm(CAVE)
    a.emit(ORIGINAL)
    a.emit(0x9C, 0x50)  # preserve flags and eax
    a.emit(bytes.fromhex("8b462085c0"))
    a.rel8(0x74, "done")
    for offset, char in enumerate(MODEL):
        a.emit(bytes([0x80, 0x38, char]) if offset == 0
               else bytes([0x80, 0x78, offset, char]))
        a.rel8(0x75, "done")
    a.emit(bytes.fromhex("b900007a45"))  # ecx = float bits of 4000 (original clamp)
    a.label("done")
    a.emit(0x58, 0x9D)
    a.rel32(0xE9, SITE + len(ORIGINAL))
    return a.resolve()


PATCH = Patch(
    id=NAME, since=None, policy="option", option="experimental_station_detail",
    label="Full station detail only", group="experimental", conflicts=("world-full-detail-v1",),
    regions=(Region(SITE, ORIGINAL, jmp_patch(SITE, CAVE, len(ORIGINAL))),
             Region(CAVE, bytes(len(code())), code(), "cave")))
