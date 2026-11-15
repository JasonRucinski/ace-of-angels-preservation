"""Golden snapshot of every byte the client patches write; game-free.

For each of the 22 patch IDs and both offline experiments, and for every
variant a module still recognizes, this lists each region's file offset,
original bytes and patched bytes, plus the runtime .data-tail reservations,
and compares them with tests/snapshots/patch_regions.json. A refactor that
moves or changes a single patch byte fails here.

  python -I tools/test.py test_patch_layout               compare with the snapshot
  python -I tools/test.py test_patch_layout -- --update   rewrite the snapshot

It also checks the layout rules of docs/restructure/audits/client.md
(finding C5): caves only in the .text padding, runtime data only in the
.data tail, and no two patches sharing bytes except the declared pairs. A
synthetic image, built from the section table in evidence/2.9.2/pe_facts.json
and every patch's own original bytes, shows that each module's configure()
and prepare_client's composition write exactly these regions and no others.
Standard library only; no game file is read.
"""
import hashlib
import json
import sys
import unittest
from pathlib import Path
from unittest import mock

from aoa.client.patches import archive_terminator  # noqa: E402
from aoa.client.patches import asteroid_render  # noqa: E402
from aoa.client.patches import cursor_warp  # noqa: E402
from aoa.client.patches import explicit_protection  # noqa: E402
from aoa.client.patches import frame_clock  # noqa: E402
from aoa.client.patches import menu_aspect  # noqa: E402
from aoa.client.patches import object_persistence  # noqa: E402
from aoa.client.patches import online_terrain  # noqa: E402
from aoa.client.patches import own_ship_menu  # noqa: E402
from aoa.client.patches import own_ship_model  # noqa: E402
from aoa.client import base  # noqa: E402
from aoa.client.patches import base as patching  # noqa: E402
from aoa.client.patches import physics_timestep  # noqa: E402
from aoa.client.patches import powerup_pickup  # noqa: E402
from aoa.client import prepare  # noqa: E402
from aoa.client.patches import solid_world_render  # noqa: E402
from aoa.client.patches import station_detail  # noqa: E402
from aoa.client.patches import texture32  # noqa: E402
from aoa.client.patches import third_person  # noqa: E402
from aoa.client.patches import visibility_fix  # noqa: E402
from aoa.client.patches import world_detail  # noqa: E402

from aoa.paths import ROOT
from tests.support_patches import BASE, collect, h, pe_facts, synthetic_pristine
SNAPSHOT = Path(__file__).resolve().parent / "snapshots/patch_regions.json"
TEXT_PADDING = (0x58B200, 0x58C000)   # .text zero padding mapped by logger-size-v1 (C5)
DATA_TAIL = (0x60D200, 0x60E000)      # zero-filled .data tail mapped by logger-size-v1 (C5)
# Patch IDs with no owning module NAME (client.md finding C7).
INLINE_IDS = ("logger-size-v1", "logger-lock-v1", "zero-time-physics-v1", "background-network-v1",
              "archive-terminator-v1")
EXPERIMENTS = ("experiment-render-clock", "experiment-render-culling")
# Pairs of patches allowed to write the same bytes. Anything else is a bug.
DECLARED_OVERLAPS = {
    # Declared alternatives at one site; prepare_client rejects both together.
    frozenset({asteroid_render.NAME, solid_world_render.NAME}),
    frozenset({station_detail.NAME, world_detail.NAME}),
    # Offline experiments, superseded by the shipping patches.
    frozenset({"experiment-render-clock", frame_clock.NAME}),
    frozenset({"experiment-render-culling", visibility_fix.NAME}),
    frozenset({"experiment-render-culling", online_terrain.NAME}),
    # Known exception (client.md finding C5): own_ship_menu's RESTRICT byte sits
    # inside third_person's FAKE..ARMED .data block, kept free only by a comment.
    frozenset({third_person.NAME, own_ship_menu.NAME}),
}


def snapshot():
    return {"about": "Every client patch region; regenerate with python -I tools/test.py test_patch_layout -- --update "
                     "only when a patch is meant to change.",
            "bounds": {"text_padding": [h(v) for v in TEXT_PADDING], "data_tail": [h(v) for v in DATA_TAIL]},
            "patches": collect()}


def render(data):
    return json.dumps(data, indent=1, sort_keys=True) + "\n"


def apply(image, regions):
    out = bytearray(image)
    for r in regions:
        offset = int(r["offset"], 16)
        assert out[offset:offset + r["size"]] == bytes.fromhex(r["old"]), r["va"]
        out[offset:offset + r["size"]] = bytes.fromhex(r["new"])
    return bytes(out)


def spans(patches):
    """(patch id, variant, space, start, end) for every file region and runtime reservation."""
    for name, patch in patches.items():
        for label, regions in patch["variants"].items():
            for r in regions:
                start = int(r["va"], 16)
                yield name, label, "file", start, start + r["size"]
        for r in patch.get("runtime_data", ()):
            start = int(r["va"], 16)
            yield name, "runtime", "runtime", start, start + r["size"]


class PatchLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.patches = collect()
        cls.pristine = synthetic_pristine()

    def test_snapshot_unchanged(self):
        self.assertTrue(SNAPSHOT.is_file(), "missing snapshot; run with --update")
        expected = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
        current = json.loads(render(snapshot()))
        for name in sorted(set(expected["patches"]) | set(current["patches"])):
            with self.subTest(patch=name):
                self.assertEqual(current["patches"].get(name), expected["patches"].get(name))
        self.assertEqual(current, expected)

    def test_every_patch_id_and_experiment_is_covered(self):
        names = {m.NAME for m in (explicit_protection, menu_aspect, cursor_warp, frame_clock, visibility_fix,
                                  third_person, own_ship_model, own_ship_menu, powerup_pickup, asteroid_render,
                                  solid_world_render, station_detail, world_detail, texture32,
                                  object_persistence, online_terrain)}
        self.assertEqual(set(self.patches), set(INLINE_IDS) | names | {"station-hostname"} | set(EXPERIMENTS))
        self.assertEqual(len(self.patches) - len(EXPERIMENTS), 22)

    def test_caves_in_text_padding_and_data_in_tail(self):
        sections = [(int(s["va"], 16), int(s["raw_off"], 16), int(s["raw_size"], 16), s["name"])
                    for s in pe_facts()["sections"]]
        text_va, text_vsize = int(pe_facts()["sections"][0]["va"], 16), int(pe_facts()["sections"][0]["vsize"], 16)
        for name, label, space, start, end in spans(self.patches):
            with self.subTest(patch=name, variant=label, va=h(start)):
                if space == "runtime":
                    self.assertTrue(DATA_TAIL[0] <= start < end <= DATA_TAIL[1])
                    continue
                if start >= text_va + text_vsize and start < TEXT_PADDING[1]:
                    self.assertTrue(TEXT_PADDING[0] <= start < end <= TEXT_PADDING[1])
                # Every region lies in one section's file data at offset = VA - image base.
                inside = [n for va, raw, size, n in sections if va <= start and end <= va + size and va - raw == BASE]
                self.assertEqual(len(inside), 1)

    def test_regions_disjoint_except_declared_pairs(self):
        found = set()
        items = list(spans(self.patches))
        for i, (n1, _, s1, a1, b1) in enumerate(items):
            for n2, _, s2, a2, b2 in items[i + 1:]:
                if n1 != n2 and s1 == s2 and a1 < b2 and a2 < b1:
                    found.add(frozenset({n1, n2}))
        self.assertEqual(found, DECLARED_OVERLAPS)

    def test_module_configure_writes_exactly_these_regions(self):
        # Experiments are left out: their configure() checks the whole image through prepare_client.
        modules = {m.NAME: m for m in (explicit_protection, menu_aspect, cursor_warp, frame_clock, visibility_fix,
                                       third_person, own_ship_model, own_ship_menu, powerup_pickup, asteroid_render,
                                       solid_world_render, station_detail, world_detail, texture32,
                                       object_persistence, online_terrain)}
        modules["archive-terminator-v1"] = archive_terminator
        for name, module in modules.items():
            with self.subTest(patch=name):
                patched = apply(self.pristine, self.patches[name]["variants"]["current"])
                if hasattr(module, "PATCH"):
                    self.assertEqual(patching.apply(module.PATCH, self.pristine, True), patched)
                    self.assertEqual(patching.apply(module.PATCH, patched, False), self.pristine)
                    continue
                self.assertEqual(module.configure(self.pristine, True), patched)
                self.assertEqual(module.configure(patched, False), self.pristine)
        patched = apply(self.pristine, self.patches["zero-time-physics-v1"]["variants"]["current"])
        with mock.patch.object(physics_timestep, "STABLE_SHA256", hashlib.sha256(self.pristine).hexdigest()):
            self.assertEqual(physics_timestep.configure(self.pristine), patched)
            self.assertEqual(physics_timestep.configure(patched, undo=True), self.pristine)

    def test_older_variants_upgrade_to_current(self):
        for name, module in ((third_person.NAME, third_person), (own_ship_menu.NAME, own_ship_menu),
                             (online_terrain.NAME, online_terrain)):
            current = apply(self.pristine, self.patches[name]["variants"]["current"])
            for label, regions in self.patches[name]["variants"].items():
                with self.subTest(patch=name, variant=label):
                    self.assertEqual(patching.apply(module.PATCH, apply(self.pristine, regions), True), current)
                    self.assertEqual(patching.apply(module.PATCH, apply(self.pristine, regions), False), self.pristine)

    def test_prepare_client_composition_writes_only_these_regions(self):
        pristine_sha = hashlib.sha256(self.pristine).hexdigest()
        with mock.patch.object(base, "PRISTINE_292", pristine_sha):
            logger = base.configure(self.pristine)[0]
        stable_sha = hashlib.sha256(logger).hexdigest()
        always = ["station-hostname", "zero-time-physics-v1", "background-network-v1", "archive-terminator-v1",
                  online_terrain.NAME, cursor_warp.NAME]
        chase = [third_person.NAME, own_ship_model.NAME, own_ship_menu.NAME]
        cases = (
            ({}, [menu_aspect.NAME, frame_clock.NAME, visibility_fix.NAME, *chase, powerup_pickup.NAME]),
            ({"smooth_frame_clock": False, "bounded_visibility": False, "chase_camera": False,
              "powerup_pickups": False, "menu_framing": False}, []),
            ({"experimental_protection": True, "experimental_asteroids": True, "experimental_station_detail": True,
              "experimental_texture32": True, "distant_objects": True, "chase_camera": False},
             [menu_aspect.NAME, frame_clock.NAME, visibility_fix.NAME, powerup_pickup.NAME, explicit_protection.NAME,
              asteroid_render.NAME, station_detail.NAME, texture32.NAME, object_persistence.NAME]),
            ({"experimental_solids": True, "experimental_world_detail": True},
             [menu_aspect.NAME, frame_clock.NAME, visibility_fix.NAME, *chase, powerup_pickup.NAME,
              solid_world_render.NAME, world_detail.NAME]),
        )
        with mock.patch.object(base, "PRISTINE_292", pristine_sha), \
                mock.patch.object(prepare, "STABLE_SHA256", stable_sha), \
                mock.patch.object(physics_timestep, "STABLE_SHA256", stable_sha):
            for options, chosen in cases:
                with self.subTest(options=options):
                    expected = logger
                    for name in always + chosen:
                        expected = apply(expected, self.patches[name]["variants"]["current"])
                    self.assertEqual(prepare.configure(self.pristine, **options), expected)


def main():
    if "--update" in sys.argv[1:]:
        SNAPSHOT.parent.mkdir(exist_ok=True)
        SNAPSHOT.write_text(render(snapshot()), encoding="utf-8", newline="\n")
        print(f"wrote {SNAPSHOT.relative_to(ROOT).as_posix()}")
        return
    unittest.main()


if __name__ == "__main__":
    main()
