"""Pin Hy_base1 child mesh selection to its original closest detail level."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from patch_client import Asm, jmp_patch

NAME = "station-full-detail-v1"
SITE, CAVE = 0x546BE4, 0x58BB00
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


def regions():
    body = code()
    return ((SITE - 0x400000, ORIGINAL, jmp_patch(SITE, CAVE, len(ORIGINAL))),
            (CAVE - 0x400000, bytes(len(body)), body))


def state(data):
    states = []
    for offset, old, new in regions():
        actual = data[offset:offset + len(old)]
        if actual not in (old, new):
            raise ValueError("unexpected station detail code or occupied cave")
        states.append(actual == new)
    if len(set(states)) != 1:
        raise ValueError("partial station detail patch")
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
    import prepare_client
    return prepare_client.prepare(exe, experimental_station_detail=not undo)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("client", type=Path)
    parser.add_argument("--undo", action="store_true", help="turn this option off")
    args = parser.parse_args()
    try:
        print(json.dumps(install(args.client, args.undo), indent=2))
    except (ValueError, RuntimeError, OSError) as error:
        parser.exit(1, f"Station detail setup failed: {error}\n")


if __name__ == "__main__":
    main()
