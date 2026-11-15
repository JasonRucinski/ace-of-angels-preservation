"""Byte-identical preparation: prepare's output image for fixed inputs and options; game-free.

The expected SHA-256 of every input and output, and the Station and patch IDs
inspect() reports for each, are in tests/snapshots/prepare_outputs.json. They were generated once, by
the composition in aoa/client/prepare.py as it stood before the patch registry
(phase 2a), and must never be regenerated: a refactor of the patch engine that
changes one byte of any output fails here.

Inputs are built from the synthetic client of tests/support_patches.py and
from the region snapshot (tests/snapshots/patch_regions.json), never from the
code under test: the pristine image, the stability-patched image, older
setups (no background fix, legacy patch variants) and prepared images. Each
case runs prepare's configure() with keyword options and an optional Station.
Standard library only; no game file is read.

    python -I tools/test.py test_prepare_outputs
"""
import hashlib
import json
import struct
import unittest
from pathlib import Path

from aoa.client import prepare
from tests.support_patches import synthetic_client, synthetic_pristine

SNAPSHOTS = Path(__file__).resolve().parent / "snapshots"
EXPECTED = SNAPSHOTS / "prepare_outputs.json"
REGIONS = SNAPSHOTS / "patch_regions.json"
ALL_OFF = {"smooth_frame_clock": False, "bounded_visibility": False, "chase_camera": False,
           "powerup_pickups": False, "menu_framing": False, "distant_objects": False,
           "experimental_protection": False, "experimental_asteroids": False, "experimental_solids": False,
           "experimental_station_detail": False, "experimental_world_detail": False,
           "experimental_texture32": False}
EVERYTHING = {"smooth_frame_clock": True, "bounded_visibility": True, "chase_camera": True,
              "powerup_pickups": True, "menu_framing": True, "distant_objects": True,
              "experimental_protection": True, "experimental_texture32": True}


def regions(patch, variant="current"):
    return json.loads(REGIONS.read_text(encoding="utf-8"))["patches"][patch]["variants"][variant]


def write(image, patch, variant="current", new=True):
    out = bytearray(image)
    for r in regions(patch, variant):
        offset = int(r["offset"], 16)
        out[offset:offset + r["size"]] = bytes.fromhex(r["new" if new else "old"])
    return bytes(out)


def stable(pristine):
    """The stability-patched image: both logger patches and their section sizes."""
    out = bytearray(write(write(pristine, "logger-size-v1"), "logger-lock-v1"))
    header = json.loads(REGIONS.read_text(encoding="utf-8"))["patches"]["logger-size-v1"]["pe_header"]
    e_lfanew = struct.unpack_from("<I", out, 0x3C)[0]
    table = e_lfanew + 24 + struct.unpack_from("<H", out, e_lfanew + 20)[0]
    for field in header:
        name = field["field"].split()[0].encode()
        for at in range(table, table + 40 * struct.unpack_from("<H", out, e_lfanew + 6)[0], 40):
            if out[at:at + 8].rstrip(b"\0") == name:
                assert struct.unpack_from("<I", out, at + 8)[0] == int(field["old"], 16)
                struct.pack_into("<I", out, at + 8, int(field["new"], 16))
    return bytes(out)


def inputs(pristine):
    """name -> input image."""
    base = stable(pristine)
    physics = write(base, "zero-time-physics-v1")
    with synthetic_client(pristine):
        prepared = prepare.configure(pristine)
        chase_off = prepare.configure(pristine, chase_camera=False)
        asteroids = prepare.configure(pristine, experimental_asteroids=True)
        world = prepare.configure(pristine, experimental_world_detail=True)
    return {
        "pristine": pristine,
        "stable": base,
        "stable-physics": physics,
        "stable-localhost-physics": write(physics, "station-hostname"),
        # A patch version 1 setup: no background-network fix, no archive terminator.
        "version-1": write(write(prepared, "background-network-v1", new=False), "archive-terminator-v1", new=False),
        "prepared": prepared,
        "prepared-chase-off": chase_off,
        "prepared-asteroids": asteroids,
        "prepared-world-detail": world,
        "legacy-third-person-v1": write(write(chase_off, "third-person-camera-v3", "v1"), "own-ship-model-v1"),
        "legacy-third-person-v2": write(chase_off, "third-person-camera-v3", "v2"),
        "legacy-own-ship-menu": write(write(prepared, "own-ship-menu-model-v1", new=False),
                                      "own-ship-menu-model-v1", "legacy"),
        "legacy-online-terrain-v2": write(write(prepared, "online-terrain-v3", new=False),
                                          "online-terrain-v3", "online-terrain-v2"),
        "legacy-online-arena1a-v1": write(write(prepared, "online-terrain-v3", new=False),
                                          "online-terrain-v3", "online-arena1a-v1"),
    }


# (case name, input name, Station or None, keyword options)
CASES = (
    ("fresh-defaults", "pristine", None, {}),
    ("fresh-everything-off", "pristine", None, ALL_OFF),
    ("fresh-everything-a", "pristine", None, {**EVERYTHING, "experimental_asteroids": True,
                                              "experimental_station_detail": True}),
    ("fresh-everything-b", "pristine", "127.0.0.1", {**EVERYTHING, "experimental_solids": True,
                                                     "experimental_world_detail": True}),
    ("fresh-asteroids", "pristine", None, {"experimental_asteroids": True}),
    ("fresh-solids", "pristine", None, {"experimental_solids": True}),
    ("fresh-station-detail", "pristine", None, {"experimental_station_detail": True}),
    ("fresh-world-detail", "pristine", None, {"experimental_world_detail": True}),
    ("fresh-distant-solids", "pristine", "aoalan", {"distant_objects": True, "experimental_solids": True}),
    ("stable-defaults", "stable", None, {}),
    ("stable-physics-defaults", "stable-physics", "10.0.0.1", {}),
    ("stable-localhost-physics", "stable-localhost-physics", None, {"menu_framing": False}),
    ("version-1-upgrade", "version-1", "127.0.0.1", {}),
    ("station-only-change", "prepared-chase-off", "aoalan", {}),
    ("unchanged-reprepare", "prepared-chase-off", None, {}),
    ("asteroids-replaced-by-solids", "prepared-asteroids", None, {"experimental_solids": True}),
    ("world-replaced-by-station", "prepared-world-detail", None, {"experimental_station_detail": True}),
    ("asteroids-kept-texture32-on", "prepared-asteroids", None, {"experimental_texture32": True}),
    ("prepared-everything-off", "prepared", None, ALL_OFF),
    ("upgrade-third-person-v1", "legacy-third-person-v1", None, {}),
    ("upgrade-third-person-v2", "legacy-third-person-v2", None, {}),
    ("upgrade-third-person-v2-off", "legacy-third-person-v2", None, {"chase_camera": False}),
    ("upgrade-own-ship-menu", "legacy-own-ship-menu", None, {}),
    ("upgrade-online-terrain-v2", "legacy-online-terrain-v2", None, {}),
    ("upgrade-online-arena1a-v1", "legacy-online-arena1a-v1", "aoalan", {}),
)


def described(image):
    state = prepare.inspect(image)
    return {"sha256": hashlib.sha256(image).hexdigest(), "host": state["host"], "patches": sorted(state["patches"])}


def outputs():
    """({input name: description}, {case name: description}) with the code under test."""
    pristine = synthetic_pristine()
    images = inputs(pristine)
    with synthetic_client(pristine):
        return ({name: described(image) for name, image in images.items()},
                {name: described(prepare.configure(images[source], station, **options))
                 for name, source, station, options in CASES})


class PrepareOutputTests(unittest.TestCase):
    def test_inputs_and_outputs_unchanged(self):
        expected = json.loads(EXPECTED.read_text(encoding="utf-8"))
        current = dict(zip(("inputs", "cases"), outputs()))
        for key in ("inputs", "cases"):
            self.assertEqual(sorted(current[key]), sorted(expected[key]))
            for name in expected[key]:
                with self.subTest(**{key: name}):
                    self.assertEqual(current[key][name], expected[key][name])

    def test_cases_cover_distinct_outputs(self):
        hashes = {case["sha256"] for case in json.loads(EXPECTED.read_text(encoding="utf-8"))["cases"].values()}
        self.assertGreaterEqual(len(hashes), 8)


if __name__ == "__main__":
    unittest.main()
