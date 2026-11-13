"""Select closest authored mesh/texture variants for solid world model groups."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import station_detail

NAME = "world-full-detail-v1"
SITE = station_detail.SITE
OFFSET = SITE - 0x400000
ORIGINAL = station_detail.ORIGINAL
PATCHED = bytes.fromhex("b900007a4590")  # mov ecx, float-bits(4000); nop
RANGE_SITE = 0x546B46
RANGE_ORIGINAL = bytes.fromhex("7455")
RANGE_PATCHED = bytes.fromhex("eb55")  # use original 5..4096 group visibility range


def regions():
    return ((OFFSET, ORIGINAL, PATCHED),
            (RANGE_SITE - 0x400000, RANGE_ORIGINAL, RANGE_PATCHED))


def state(data):
    off = RANGE_SITE - 0x400000
    if data[OFFSET:OFFSET + 6] == PATCHED:
        if data[off:off + 2] != RANGE_PATCHED:
            raise ValueError("partial world-detail patch")
        station_detail.state(data[:OFFSET] + ORIGINAL + data[OFFSET + 6:])
        return True
    if data[off:off + 2] != RANGE_ORIGINAL:
        raise ValueError("unexpected world-detail group range or partial patch")
    station_detail.state(data)
    return False


def configure(data, enabled=True):
    """Pure toggle: refuses to replace the station-only patch at the same site."""
    if enabled == state(data):
        return data  # also leaves an installed station-only patch alone when off
    if enabled and station_detail.state(data):
        raise ValueError(f"{station_detail.NAME} and {NAME} cannot both be on; select one")
    for off, old, new in regions():
        data = data[:off] + (new if enabled else old) + data[off + len(old):]
    return data


def install(exe, undo=False):
    """Turn this option on, or off with undo, through prepare_client.prepare().

    Every other option keeps its installed state; prepare's own backup and
    record (_client_setup.json) cover undo.
    """
    import prepare_client
    return prepare_client.prepare(exe, experimental_world_detail=not undo)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("client", type=Path)
    parser.add_argument("--undo", action="store_true", help="turn this option off")
    args = parser.parse_args()
    try:
        print(json.dumps(install(args.client, args.undo), indent=2))
    except (ValueError, RuntimeError, OSError) as error:
        parser.exit(1, f"World detail setup failed: {error}\n")


if __name__ == "__main__":
    main()
