"""Reversible zero-time physics guard for the stability-patched 2.9.2 client.

Usage: python -I tools/physics_timestep.py CLIENT.EXE [--undo]
Accepts the known logger fixes, with either original or localhost lookup.
Never changes preserved originals. No client is executed by this tool.
"""
import argparse
import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from local_station import OFFSET, ORIGINAL, LOCAL, STABLE_SHA256
from patch_client import Asm, jmp_patch

SITE, SITE_OFFSET = 0x48AE71, 0x8AE71
CAVE, CAVE_OFFSET = 0x58B400, 0x18B400
DISPLACED = bytes.fromhex("8b85f0000000")


def guard_code():
    a = Asm(CAVE)
    a.emit(bytes.fromhex("837c243800"))  # cmp dword [esp+38], 0
    a.rel32(b"\x0f\x84", 0x48CE9F)    # existing balanced physics epilogue
    a.emit(DISPLACED)                    # mov eax, [ebp+f0]
    a.rel32(0xE9, SITE + len(DISPLACED))
    return a.resolve()


def configure(data, undo=False):
    code = guard_code()
    jump = jmp_patch(SITE, CAVE, len(DISPLACED))
    state = (data[SITE_OFFSET:SITE_OFFSET + len(jump)],
             data[CAVE_OFFSET:CAVE_OFFSET + len(code)])
    if state not in ((DISPLACED, bytes(len(code))), (jump, code)):
        raise ValueError("unexpected physics code or cave")
    normalized = bytearray(data)
    normalized[SITE_OFFSET:SITE_OFFSET + len(jump)] = DISPLACED
    normalized[CAVE_OFFSET:CAVE_OFFSET + len(code)] = bytes(len(code))
    if normalized[OFFSET:OFFSET + len(ORIGINAL)] not in (ORIGINAL, LOCAL):
        raise ValueError("unexpected Station hostname")
    normalized[OFFSET:OFFSET + len(ORIGINAL)] = ORIGINAL
    if hashlib.sha256(normalized).hexdigest() != STABLE_SHA256:
        raise ValueError("requires known stability-patched 2.9.2 client")
    out = bytearray(data)
    out[SITE_OFFSET:SITE_OFFSET + len(jump)] = DISPLACED if undo else jump
    out[CAVE_OFFSET:CAVE_OFFSET + len(code)] = bytes(len(code)) if undo else code
    return bytes(out)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("exe", type=Path)
    parser.add_argument("--undo", action="store_true")
    args = parser.parse_args()
    if "originals" in (p.lower() for p in args.exe.resolve().parts):
        parser.error("refusing to modify originals/")
    data = configure(args.exe.read_bytes(), args.undo)
    args.exe.write_bytes(data)
    if args.exe.read_bytes() != data:
        raise RuntimeError("write verification failed")
    print("Zero-time physics guard: " + ("removed" if args.undo else "enabled"))
    print("SHA-256: " + hashlib.sha256(data).hexdigest())


if __name__ == "__main__":
    main()
