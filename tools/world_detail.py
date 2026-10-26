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
    if state(data):
        for off, old, _ in regions():
            data = data[:off] + old + data[off + len(old):]
    if enabled:
        data = station_detail.configure(data, False)
        for off, old, new in regions():
            data = data[:off] + new + data[off + len(old):]
    return data


def install(exe, undo=False):
    import prepare_client
    exe = Path(exe).resolve()
    prepare_client.paths(exe)
    source = exe.read_bytes()
    info = prepare_client.inspect(source)
    backup = exe.with_suffix(".EXE.before-world-detail")
    if not backup.exists():
        if undo or state(source):
            raise ValueError("missing world-detail exact-undo backup")
        prepare_client.atomic_write(backup, source)
    before = backup.read_bytes()
    before_info = prepare_client.inspect(before)
    if state(before):
        raise ValueError("world-detail backup already contains this patch")
    expected = prepare_client.configure(before, host=before_info["host"], experimental_world_detail=True)
    if source not in (before, expected):
        raise ValueError("world-detail backup does not match this client")
    result = before if undo else expected
    prepare_client.prepare(exe, host=info["host"], experimental_world_detail=not undo,
                           experimental_station_detail=station_detail.NAME in before_info["patches"] if undo else False)
    if exe.read_bytes() != result:
        raise ValueError("world-detail verification failed")
    record = {"enabled": not undo, "sha256": prepare_client.sha(result),
              "undo_sha256": prepare_client.sha(before), "visual_acceptance": "pending",
              "scope": "solid world child mesh/texture LOD selection fixed at 4000; group visibility uses original 5..4096 default; effect renderer unchanged"}
    prepare_client.atomic_write(exe.parent / "_world_detail.json",
                               (json.dumps(record, indent=2) + "\n").encode())
    return record


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("client", type=Path)
    parser.add_argument("--undo", action="store_true")
    args = parser.parse_args()
    print(json.dumps(install(args.client, args.undo), indent=2))
