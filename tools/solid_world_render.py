"""Keep world model groups on their mesh path to the existing far horizon.

This changes the model visibility comparison, not the sprite/particle renderer.
It shares its site with the asteroid-only patch: configure() refuses to
replace that patch, and prepare_client decides between the two.
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
    if enabled == state(data):
        return data  # also leaves an installed asteroid-only patch alone when off
    if enabled and asteroid_render.state(data):
        raise ValueError(f"{asteroid_render.NAME} and {NAME} cannot both be on; select one")
    return data[:OFFSET] + (PATCHED if enabled else ORIGINAL) + data[OFFSET + 6:]


def install(exe, undo=False):
    """Turn this option on, or off with undo, through prepare_client.prepare().

    Every other option keeps its installed state; prepare's own backup and
    record (_client_setup.json) cover undo.
    """
    import prepare_client
    return prepare_client.prepare(exe, experimental_solids=not undo)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("client", type=Path)
    parser.add_argument("--undo", action="store_true", help="turn this option off")
    args = parser.parse_args()
    try:
        print(json.dumps(install(args.client, args.undo), indent=2))
    except (ValueError, RuntimeError, OSError) as error:
        parser.exit(1, f"Solid-world render setup failed: {error}\n")


if __name__ == "__main__":
    main()
