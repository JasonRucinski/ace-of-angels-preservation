"""Zero-time physics guard for the 2.9.2 client (findings 9.10).

The object update divides by its time step (acceleration at 0x48C200), and a
remote object's first update can have dt = 0, which gives NaNs. After the
original tick bookkeeping, the guard at 0x48AE71 checks the time step at
[esp+0x38]: zero takes the existing balanced epilogue at 0x48CE9F, positive
values run the displaced instruction and the original physics. Applied by
every prepare; aoa.emulation.check_movement runs it against original code.
"""
from aoa.client import layout
from aoa.client.asm import Asm, jmp_patch
from aoa.client.patches.base import Patch, Region

NAME = "zero-time-physics-v1"
SITE = 0x48AE71
CAVE = layout.cave(NAME).start
DISPLACED = bytes.fromhex("8b85f0000000")


def guard_code():
    a = Asm(CAVE)
    a.emit(bytes.fromhex("837c243800"))  # cmp dword [esp+38], 0
    a.rel32(b"\x0f\x84", 0x48CE9F)    # existing balanced physics epilogue
    a.emit(DISPLACED)                    # mov eax, [ebp+f0]
    a.rel32(0xE9, SITE + len(DISPLACED))
    return a.resolve()


PATCH = Patch(
    id=NAME, since=2, policy="always",
    regions=(Region(SITE, DISPLACED, jmp_patch(SITE, CAVE, len(DISPLACED))),
             Region(CAVE, bytes(len(guard_code())), guard_code(), "cave")))
