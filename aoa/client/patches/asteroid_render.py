"""Opt-in 2.9.2 asteroid mesh rendering instead of distant cached billboards.

Only the surface-distance gate for model names Astr-* / Astr_* changes.
Texture LOD, geometry, transforms, and all other models retain original code.
Visual acceptance and performance require a real flight test.
"""
import argparse
import json
from pathlib import Path

from aoa.client.base import Asm, jmp_patch

NAME = "asteroid-mesh-distance-v1"
SITE, CAVE = 0x543222, 0x58BA00
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


def regions():
    body = code()
    return ((SITE - 0x400000, ORIGINAL, jmp_patch(SITE, CAVE, len(ORIGINAL))),
            (CAVE - 0x400000, bytes(len(body)), body))


def state(data):
    states = []
    for offset, old, new in regions():
        actual = data[offset:offset + len(old)]
        if actual not in (old, new):
            raise ValueError("unexpected asteroid render code or occupied cave")
        states.append(actual == new)
    if len(set(states)) != 1:
        raise ValueError("partial asteroid render patch")
    return states[0]


def configure(data, enabled=True):
    state(data)
    result = bytearray(data)
    for offset, old, new in regions():
        result[offset:offset + len(old)] = new if enabled else old
    return bytes(result)


def install(exe, undo=False):
    """Turn this option on, or off with undo, through prepare_client.prepare().

    Every other option keeps its installed state; prepare's own backup and
    record (_client_setup.json) cover undo.
    """
    from aoa.client import prepare
    return prepare.prepare(exe, experimental_asteroids=not undo)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("client", type=Path)
    parser.add_argument("--undo", action="store_true", help="turn this option off")
    args = parser.parse_args()
    try:
        print(json.dumps(install(args.client, args.undo), indent=2))
    except (ValueError, RuntimeError, OSError) as error:
        parser.exit(1, f"Asteroid render setup failed: {error}\n")


if __name__ == "__main__":
    main()
