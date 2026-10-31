"""Keep distant world models visible with their existing authored LODs.

Opt-in, reversible 2.9.2 patch: 4,500,000-unit surface-distance horizon and
a 0.5 projected-size minimum. Child selection clamps to the group's original
authored minimum so distant groups still have meshes to draw.
"""
import argparse
import json
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from patch_client import Asm, jmp_patch

NAME = "distant-world-objects-v1"
HORIZON = 4_500_000.0
MIN_SIZE = 0.5
GROUP_SITE = 0x546BB3
GROUP_ORIGINAL = bytes.fromhex("8b54240455")  # mov edx,[esp+4]; push ebp
CHILD_SITE = 0x546BEA
CHILD_ORIGINAL = bytes.fromhex("85ff894c2434")  # test edi,edi; mov [esp+34],ecx
CAVE = 0x58BB80  # after station_detail, before third_person
CHILD_CAVE = CAVE + 0x20
CAVE_SIZE = 0x80


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


def regions():
    return (
        # These constants have one original code reference each: the world
        # mesh gate and cached-world-image horizon. No shared 5.0 is modified.
        (0x5B0C30 - 0x400000, struct.pack("<f", 61_000), struct.pack("<f", HORIZON)),
        (0x59D9C0 - 0x400000, struct.pack("<f", 900_000), struct.pack("<f", HORIZON)),
        (0x54326A - 0x400000, bytes.fromhex("d81d84fc5800"),
         bytes.fromhex("d81d40ed5800")),  # compare size to existing 0.5, not 5.0
        (GROUP_SITE - 0x400000, GROUP_ORIGINAL, jmp_patch(GROUP_SITE, CAVE, len(GROUP_ORIGINAL))),
        (CHILD_SITE - 0x400000, CHILD_ORIGINAL, jmp_patch(CHILD_SITE, CHILD_CAVE, len(CHILD_ORIGINAL))),
        (CAVE - 0x400000, bytes(CAVE_SIZE), code()),
    )


def state(data):
    states = []
    for offset, old, new in regions():
        actual = data[offset:offset + len(old)]
        if actual not in (old, new):
            raise ValueError("unexpected distant-object code, constant or occupied cave")
        states.append(actual == new)
    if len(set(states)) != 1:
        raise ValueError("partial distant-object patch")
    return states[0]


def configure(data, enabled=True):
    state(data)
    result = bytearray(data)
    for offset, old, new in regions():
        result[offset:offset + len(old)] = new if enabled else old
    return bytes(result)


def install(exe, undo=False):
    import frame_clock
    import powerup_pickup
    import prepare_client
    import third_person
    import visibility_fix

    exe = Path(exe).resolve()
    info = prepare_client.check(exe, require_assets=False)
    source = exe.read_bytes()
    before = configure(source, False)
    backup = exe.with_suffix(".EXE.before-object-persistence")
    if backup.exists() and backup.read_bytes() != before:
        raise ValueError("distant-object backup does not match this client")
    if not backup.exists():
        if undo or state(source):
            raise ValueError("missing distant-object exact-undo backup")
        prepare_client.atomic_write(backup, before)
    result = configure(source, not undo)
    prepare_client.prepare(
        exe, host=info["host"], distant_objects=not undo,
        smooth_frame_clock=frame_clock.NAME in info["patches"],
        bounded_visibility=visibility_fix.NAME in info["patches"],
        chase_camera=third_person.NAME in info["patches"],
        powerup_pickups=powerup_pickup.NAME in info["patches"],
    )
    if exe.read_bytes() != result:
        raise ValueError("distant-object verification failed")
    record = {"enabled": not undo, "sha256": prepare_client.sha(result),
              "undo_sha256": prepare_client.sha(before), "visual_acceptance": "pending",
              "horizon_world_units": HORIZON, "minimum_projected_size": MIN_SIZE,
              "scope": "world model visibility and cached-world-image horizon; authored LODs retained"}
    prepare_client.atomic_write(exe.parent / "_object_persistence.json",
                               (json.dumps(record, indent=2) + "\n").encode())
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("client", type=Path)
    parser.add_argument("--undo", action="store_true")
    args = parser.parse_args()
    try:
        print(json.dumps(install(args.client, args.undo), indent=2))
    except (ValueError, OSError) as error:
        parser.exit(1, f"Distant-object setup failed: {error}\n")


if __name__ == "__main__":
    main()
