"""Keep world model groups on their mesh path to the existing far horizon.

This changes the model visibility comparison, not the sprite/particle renderer.
The separate asteroid-only patch is removed when this patch is selected.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import asteroid_render

NAME = "solid-world-mesh-distance-v1"
SITE = asteroid_render.SITE
OFFSET = SITE - 0x400000
ORIGINAL = asteroid_render.ORIGINAL
PATCHED = bytes.fromhex("d81dc0d95900")  # fcomp [existing 900000.0 horizon]


def regions():
    return ((OFFSET, ORIGINAL, PATCHED),)


def state(data):
    actual = data[OFFSET:OFFSET + 6]
    if actual == PATCHED:
        # A broad patch must not coexist with an abandoned asteroid code cave.
        restored = data[:OFFSET] + ORIGINAL + data[OFFSET + 6:]
        asteroid_render.state(restored)
        return True
    asteroid_render.state(data)  # accept the intact legacy patch or original only
    return False


def configure(data, enabled=True):
    active = state(data)
    if active:
        data = data[:OFFSET] + ORIGINAL + data[OFFSET + 6:]
    if enabled:
        data = asteroid_render.configure(data, False)
        data = data[:OFFSET] + PATCHED + data[OFFSET + 6:]
    return data


def install(exe, undo=False):
    import prepare_client
    exe = Path(exe).resolve()
    prepare_client.paths(exe)
    source = exe.read_bytes()
    info = prepare_client.inspect(source)
    backup = exe.with_suffix(".EXE.before-solid-world-render")
    if not backup.exists():
        if undo or state(source):
            raise ValueError("missing solid-world exact-undo backup")
        prepare_client.atomic_write(backup, source)
    before = backup.read_bytes()
    before_info = prepare_client.inspect(before)
    if state(before):
        raise ValueError("solid-world backup already contains this patch")
    expected = prepare_client.configure(before, host=before_info["host"], experimental_solids=True)
    if source not in (before, expected):
        raise ValueError("solid-world backup does not match this client")
    result = before if undo else expected
    prepare_client.prepare(exe, host=info["host"], experimental_solids=not undo,
                           experimental_asteroids=asteroid_render.NAME in before_info["patches"] if undo else False)
    if exe.read_bytes() != result:
        raise ValueError("solid-world render verification failed")
    record = {"enabled": not undo, "sha256": prepare_client.sha(result),
              "undo_sha256": prepare_client.sha(before), "visual_acceptance": "pending",
              "scope": "world model-group surface-distance cutoff 61000 to 900000; texture LOD and effect renderer unchanged"}
    prepare_client.atomic_write(exe.parent / "_solid_world_render.json",
                               (json.dumps(record, indent=2) + "\n").encode())
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("client", type=Path)
    parser.add_argument("--undo", action="store_true")
    args = parser.parse_args()
    print(json.dumps(install(args.client, args.undo), indent=2))


if __name__ == "__main__":
    main()
