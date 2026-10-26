"""Opt-in 2.9.2 protection setter prototype; no files written here.

Changes the CAOAComm 0x81 receive case from a toggle to a one-byte state.
This is not session authentication, ordered delivery, or spawn protection
policy. Use only in the localhost extension gate with a prepared client.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from patch_client import Asm, jmp_patch

NAME = "explicit-protection-v1"
SITE, SITE_OFFSET = 0x4867C3, 0x867C3
CAVE, CAVE_OFFSET = 0x58B480, 0x18B480
DISPLACED = bytes.fromhex("8b0d28775e00e8127d0200")
RESUME, TOGGLE = 0x4867CE, 0x4AE4E0
WORLD_POINTER, FLAG = 0x5E7728, 0xD34EC


def cave_code():
    a = Asm(CAVE)
    a.emit(bytes.fromhex("83bee407000001"))  # cmp dword [esi+7e4], 1
    a.rel8(0x75, "done")
    a.emit(bytes.fromhex("8a86640300003c01"))  # mov al,[esi+364]; cmp al,1
    a.rel8(0x77, "done")                    # ja: reject all values above 1
    a.emit(bytes.fromhex("8b0d28775e0085c9"))  # mov ecx,[world]; test ecx,ecx
    a.rel8(0x74, "done")
    a.emit(bytes.fromhex("3881ec340d00"))     # cmp [ecx+d34ec],al
    a.rel8(0x74, "done")
    a.rel32(0xE8, TOGGLE)                   # retain original flag update/toast
    a.label("done")
    a.rel32(0xE9, RESUME)
    return a.resolve()


def state(data):
    code = cave_code()
    current = (data[SITE_OFFSET:SITE_OFFSET + len(DISPLACED)],
               data[CAVE_OFFSET:CAVE_OFFSET + len(code)])
    if current == (DISPLACED, bytes(len(code))):
        return False
    if current == (jmp_patch(SITE, CAVE, len(DISPLACED)), code):
        return True
    raise ValueError("unexpected explicit-protection code or cave")


def configure(data, enabled=True):
    state(data)
    code = cave_code()
    out = bytearray(data)
    out[SITE_OFFSET:SITE_OFFSET + len(DISPLACED)] = (
        jmp_patch(SITE, CAVE, len(DISPLACED)) if enabled else DISPLACED)
    out[CAVE_OFFSET:CAVE_OFFSET + len(code)] = code if enabled else bytes(len(code))
    return bytes(out)
