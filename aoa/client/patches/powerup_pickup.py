"""Let server-placed power-ups be picked up, and come back after a pickup.

Two 2.9.2 changes stop the power-up loop the relay hosts (findings 9.44):

  * Not collidable. ReceiveSpawnPowerup (0x431D30) sets object type 6 with
    SetTerrainType (0x49A560), which in 2.9.2 clears the collidable byte
    +0x2FB for type 6 (2.7.1's 0x4EE130 set it). The collision pass
    0x4B2E90 skips such objects (0x4B3013), so CollideWithPowerup is never
    reached. Patch: the receiver's next store, `mov dword [edi+0x200], 4`
    at 0x431E19, jumps to a cave that repeats it and sets +0x2FB = 1. Only
    objects made by SpawnPowerUp 0x43 change; terrain power-up zones keep
    their type-6 settings.
  * Never shown again. MovePowerupTo (0x430B2B) hides the object with
    0x49CD70(0) (+0x2F7 and the model's enabled byte [+0x19C]+0x150) and
    starts the 5,000 ms countdown +0x338. When it ends, the object update
    0x49ABD0 sets only +0x2F7 (0x49ACC2), so the model stays disabled and
    the collision pass's draw test (0x542990) fails. Patch: in place, the
    expiry calls 0x49CD70(1) and clears the countdown. The countdown's only
    nonzero writer is that receiver (0x430B77), whose own 0x49CD70(0) call
    needs the model pointer, so the call cannot meet a null model.

Library use only (prepare_client.py composes it); no file is written here.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from patch_client import Asm, jmp_patch  # noqa: E402

NAME = "powerup-pickup-v1"
SPAWN_SITE = 0x431E19                 # mov dword [edi+0x200], 4
SPAWN_ORIGINAL = bytes.fromhex("c78700020000" "04000000")
SPAWN_RESUME = 0x431E23
EXPIRY_SITE = 0x49ACC2                # mov byte [esi+0x2F7], 1; mov dword [esi+0x338], 0
EXPIRY_ORIGINAL = bytes.fromhex("c686f702000001" "c7863803000000000000")
SHOW = 0x49CD70                       # CObject show/hide: +0x2F7 and model +0x150
CAVE = 0x58B2C0                       # free padding after patch_client's logger cave (ends 0x58B286)
CAVE_END = 0x58B300                   # cursor_warp.py's cave


def cave_code():
    a = Asm(CAVE)
    a.emit(SPAWN_ORIGINAL)                                   # mov dword [edi+0x200], 4
    a.emit(b"\xc6\x87\xfb\x02\x00\x00\x01")                  # mov byte [edi+0x2FB], 1
    a.rel32(0xE9, SPAWN_RESUME)
    return a.resolve()


def expiry_code():
    a = Asm(EXPIRY_SITE)
    a.emit(b"\x6a\x01\x8b\xce")                              # push 1; mov ecx, esi
    a.rel32(0xE8, SHOW)                                      # call 0x49CD70 (ret 4)
    a.emit(b"\x83\xa6\x38\x03\x00\x00\x00\x90")              # and dword [esi+0x338], 0; nop
    return a.resolve()


def regions():
    """(file offset, original bytes, patched bytes); image base 0x400000."""
    body, expiry = cave_code(), expiry_code()
    assert CAVE + len(body) <= CAVE_END and len(expiry) == len(EXPIRY_ORIGINAL)
    return [(SPAWN_SITE - 0x400000, SPAWN_ORIGINAL, jmp_patch(SPAWN_SITE, CAVE, len(SPAWN_ORIGINAL))),
            (CAVE - 0x400000, bytes(len(body)), body),
            (EXPIRY_SITE - 0x400000, EXPIRY_ORIGINAL, expiry)]


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
            raise ValueError("unexpected power-up pickup code or cave")
    if len(found) != 1:
        raise ValueError("partial power-up pickup patch")
    return found.pop()


def configure(data, enabled=True):
    state(data)
    out = bytearray(data)
    for offset, old, new in regions():
        out[offset:offset + len(old)] = new if enabled else old
    return bytes(out)
