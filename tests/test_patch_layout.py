"""Golden snapshot of every byte the client patches write, and the layout rules; game-free.

For each of the 22 patch IDs and both offline experiments, and for every
variant a patch still recognizes, this lists each region's file offset,
original bytes and patched bytes, plus the runtime .data-tail reservations,
and compares them with tests/snapshots/patch_regions.json. A refactor that
moves or changes a single patch byte fails here.

  python -I tools/test.py test_patch_layout               compare with the snapshot
  python -I tools/test.py test_patch_layout -- --update   rewrite the snapshot

It also checks the registry (aoa/client/patches/__init__.py) and the layout
table (aoa/client/layout.py) against the rules of docs/restructure/audits/
client.md, findings C4 and C5: reservations disjoint and inside the .text
padding and .data tail, every cave inside its owner's reservation, no two
patches sharing bytes unless they are a declared conflict, and a constant
that one patch reads rewritten by another only where that is declared and
its effect stated here. A synthetic image, built from the section table in
evidence/2.9.2/pe_facts.json and every patch's own original bytes, shows
that the engine and prepare's composition write exactly these regions.
Standard library only; no game file is read.
"""
import json
import re
import struct
import sys
import unittest
from pathlib import Path

from aoa.client import layout
from aoa.client import patches as registry
from aoa.client import prepare
from aoa.client.patches import asteroid_render
from aoa.client.patches import base as patching
from aoa.client.patches import frame_clock
from aoa.client.patches import logger
from aoa.client.patches import object_persistence
from aoa.client.patches import online_terrain
from aoa.client.patches import own_ship_menu
from aoa.client.patches import solid_world_render
from aoa.client.patches import station_detail
from aoa.client.patches import third_person
from aoa.client.patches import visibility_fix
from aoa.client.patches import world_detail
from aoa.paths import ROOT
from tests.support_patches import BASE, collect, h, pe_facts, synthetic_client, synthetic_pristine

SNAPSHOT = Path(__file__).resolve().parent / "snapshots/patch_regions.json"
TEXT_PADDING = layout.TEXT_PADDING
DATA_TAIL = layout.DATA_TAIL
EXPERIMENTS = ("experiment-render-clock", "experiment-render-culling")
# Offline experiments may share bytes with the patches that superseded them.
EXPERIMENT_OVERLAPS = {
    frozenset({"experiment-render-clock", frame_clock.NAME}),
    frozenset({"experiment-render-culling", visibility_fix.NAME}),
    frozenset({"experiment-render-culling", online_terrain.NAME}),
}
# Constants one patch reads and another rewrites (finding C4), and which.
DECLARED_READS = {
    (asteroid_render.NAME, object_persistence.NAME): {asteroid_render.MESH_HORIZON,
                                                      asteroid_render.BILLBOARD_HORIZON},
    (solid_world_render.NAME, object_persistence.NAME): {asteroid_render.BILLBOARD_HORIZON},
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


def file_spans(patches):
    """(patch id, variant, start, end) for every file region of the snapshot."""
    for name, patch in patches.items():
        for label, regions in patch["variants"].items():
            for r in regions:
                start = int(r["va"], 16)
                yield name, label, start, start + r["size"]


def overlap(a, b):
    return a.start < b.end and b.start < a.end


def floats(image, *vas):
    return [struct.unpack_from("<f", image, va - BASE)[0] for va in vas]


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
        ids = {p.id for p in registry.REGISTRY}
        self.assertEqual(set(self.patches), ids | {"station-hostname"} | set(EXPERIMENTS))
        self.assertEqual(len(ids) + 1, 22)   # the Station hostname is the 22nd

    def test_registry_rules(self):
        self.assertEqual({frozenset({a.id, b.id}) for a, b in registry.CONFLICTS},
                         {frozenset({asteroid_render.NAME, solid_world_render.NAME}),
                          frozenset({station_detail.NAME, world_detail.NAME})})
        self.assertEqual(registry.PATCH_LEVEL, 22)
        self.assertEqual(sum(len(ids) for ids in registry.levels().values()), len(registry.REGISTRY))
        for p in registry.REGISTRY:
            with self.subTest(patch=p.id):
                if p.policy == "option" and p.option:
                    self.assertIn(p.group, patching.GROUPS)
                for _, regions in p.variants:
                    vas = [r.va for r in regions]
                    self.assertEqual(len(vas), len(set(vas)))

    def test_patch_level_table_in_the_docs_matches_the_registry(self):
        text = (ROOT / "docs/reference/client-patches.md").read_text(encoding="utf-8")
        table = text[text.index("### Patch levels"):].split("\n\n")[2]
        documented = {}
        for row in table.splitlines()[2:]:
            version, ids = (cell.strip() for cell in row.strip("|").split("|"))
            documented[None if "not recorded" in version else int(version)] = re.findall(r"`([^`]+)`", ids)
        self.assertEqual(documented, registry.levels())

    def test_reservations_disjoint_and_in_bounds(self):
        for table, bounds in ((layout.CAVES, TEXT_PADDING), (layout.DATA, DATA_TAIL)):
            for i, r in enumerate(table):
                with self.subTest(reservation=(r.owner, r.what)):
                    self.assertIn(r.owner, registry.BY_ID)
                    self.assertTrue(bounds[0] <= r.start < r.end <= bounds[1])
                    for other in table[i + 1:]:
                        self.assertFalse(overlap(r, other), (other.owner, other.what))

    def test_caves_and_data_inside_their_owners_reservations(self):
        for p in registry.REGISTRY:
            owned = [r for r in layout.CAVES if r.owner == p.id]
            for variant, regions in p.variants:
                for region in regions:
                    with self.subTest(patch=variant, va=h(region.va)):
                        inside = any(r.start <= region.va and region.end <= r.end for r in owned)
                        self.assertEqual(inside, region.kind == "cave")
            for start, size in p.data:
                with self.subTest(patch=p.id, data=h(start)):
                    self.assertTrue(any(r.owner == p.id and r.start <= start and start + size <= r.end
                                        for r in layout.DATA))
        # The runtime variables the modules use lie in their owners' reservations.
        for owner, va, size in ((third_person.NAME, third_person.FAKE, third_person.TICK + 4 - third_person.FAKE),
                                (third_person.NAME, third_person.ORBIT, third_person.ARMED + 1 - third_person.ORBIT),
                                (own_ship_menu.NAME, own_ship_menu.RESTRICT, 1),
                                ("logger-lock-v1", logger.LOCK_OWNER, 8)):
            with self.subTest(owner=owner, va=h(va)):
                self.assertTrue(any(r.owner == owner and r.start <= va and va + size <= r.end
                                    for r in layout.DATA))

    def test_regions_in_file_backed_sections(self):
        sections = [(int(s["va"], 16), int(s["raw_off"], 16), int(s["raw_size"], 16)) for s in pe_facts()["sections"]]
        for name, label, start, end in file_spans(self.patches):
            with self.subTest(patch=name, variant=label, va=h(start)):
                inside = [va for va, raw, size in sections if va <= start and end <= va + size and va - raw == BASE]
                self.assertEqual(len(inside), 1)
        patching.check_mapping(self.pristine, registry.REGISTRY)

    def test_regions_disjoint_except_declared_conflicts(self):
        found = set()
        items = list(file_spans(self.patches))
        for i, (n1, _, a1, b1) in enumerate(items):
            for n2, _, a2, b2 in items[i + 1:]:
                if n1 != n2 and a1 < b2 and a2 < b1:
                    found.add(frozenset({n1, n2}))
        conflicts = {frozenset({a.id, b.id}) for a, b in registry.CONFLICTS}
        self.assertEqual(found, conflicts | EXPERIMENT_OVERLAPS)

    def test_constants_read_and_rewritten_are_declared(self):
        found = {}
        for reader in registry.REGISTRY:
            for writer in registry.REGISTRY:
                for r in writer.regions:
                    hit = {va for va in reader.reads if r.kind == "const" and r.va <= va < r.end}
                    if hit and writer is not reader:
                        found.setdefault((reader.id, writer.id), set()).update(hit)
        self.assertEqual(found, DECLARED_READS)

    def test_distant_objects_move_the_asteroid_and_solid_world_horizons(self):
        # The combined effect of finding C4: with distant objects on, the
        # asteroid-only and solid-world horizons are 4,500,000, not 61,000/900,000.
        with synthetic_client(self.pristine):
            for options, mesh, billboard in (
                    ({"experimental_asteroids": True}, 61_000, 900_000),
                    ({"experimental_asteroids": True, "distant_objects": True}, 4_500_000, 4_500_000),
                    ({"experimental_solids": True}, 61_000, 900_000),
                    ({"experimental_solids": True, "distant_objects": True}, 4_500_000, 4_500_000)):
                with self.subTest(options=options):
                    image = prepare.configure(self.pristine, options=options)
                    self.assertEqual(floats(image, asteroid_render.MESH_HORIZON, asteroid_render.BILLBOARD_HORIZON),
                                     [mesh, billboard])
        # What each reads: the asteroid cave both, the solid-world site the 900,000 one.
        cave = asteroid_render.code()
        for va in (asteroid_render.MESH_HORIZON, asteroid_render.BILLBOARD_HORIZON):
            self.assertIn(b"\xd8\x1d" + struct.pack("<I", va), cave)            # fcomp [va]
        self.assertEqual(solid_world_render.PATCHED, b"\xd8\x1d" + struct.pack("<I", asteroid_render.BILLBOARD_HORIZON))

    def test_engine_writes_exactly_these_regions(self):
        for p in registry.REGISTRY:
            if p.policy == "base":
                continue
            with self.subTest(patch=p.id):
                patched = apply(self.pristine, self.patches[p.id]["variants"]["current"])
                self.assertEqual(patching.state(p, patched), p.id)
                self.assertIsNone(patching.state(p, self.pristine))
                self.assertEqual(patching.apply(p, self.pristine, True), patched)
                self.assertEqual(patching.apply(p, patched, False), self.pristine)
                for r in p.regions:
                    partial = bytearray(patched)
                    partial[r.va - BASE:r.end - BASE] = r.old
                    if len(p.regions) > 1:
                        with self.assertRaises(ValueError):
                            patching.state(p, bytes(partial))
                    partial[r.va - BASE] ^= 0xFF
                    if partial[r.va - BASE:r.end - BASE] not in (r.old, r.new):
                        with self.assertRaises(ValueError):
                            patching.state(p, bytes(partial))
        # The base step: both logger patches and the two section sizes.
        stable = self.pristine
        for name in ("logger-size-v1", "logger-lock-v1"):
            stable = apply(stable, self.patches[name]["variants"]["current"])
        with synthetic_client(self.pristine):
            built = logger.stabilize(self.pristine)
        changed = [i for i, (a, b) in enumerate(zip(stable, built)) if a != b]
        headers = logger.section_headers(built)
        self.assertEqual(changed, sorted(i for name, _, _ in logger.HEADER
                                         for i in range(headers[name] + 8, headers[name] + 12)
                                         if stable[i] != built[i]))
        self.assertTrue(changed)

    def test_older_variants_upgrade_to_current(self):
        for name, module in ((third_person.NAME, third_person), (own_ship_menu.NAME, own_ship_menu),
                             (online_terrain.NAME, online_terrain)):
            current = apply(self.pristine, self.patches[name]["variants"]["current"])
            for label, regions in self.patches[name]["variants"].items():
                with self.subTest(patch=name, variant=label):
                    self.assertEqual(patching.apply(module.PATCH, apply(self.pristine, regions), True), current)
                    self.assertEqual(patching.apply(module.PATCH, apply(self.pristine, regions), False), self.pristine)

    def test_prepare_composition_writes_only_these_regions(self):
        with synthetic_client(self.pristine):
            stable = logger.stabilize(self.pristine)
            always = ["station-hostname", *(p.id for p in registry.REGISTRY if p.policy == "always")]
            chase = [third_person.NAME, "own-ship-model-v1", own_ship_menu.NAME]
            defaults = [p.id for p in registry.OPTIONS.values() if p.default]
            cases = (
                ({}, [*defaults, *chase[1:]]),
                ({"smooth_frame_clock": False, "bounded_visibility": False, "chase_camera": False,
                  "powerup_pickups": False, "menu_framing": False}, []),
                ({"experimental_protection": True, "experimental_asteroids": True, "experimental_station_detail": True,
                  "experimental_texture32": True, "distant_objects": True, "chase_camera": False},
                 [*(d for d in defaults if d != third_person.NAME), "explicit-protection-v1", asteroid_render.NAME,
                  station_detail.NAME, "texture-argb8888-v1", object_persistence.NAME]),
                ({"experimental_solids": True, "experimental_world_detail": True},
                 [*defaults, *chase[1:], solid_world_render.NAME, world_detail.NAME]),
            )
            for options, chosen in cases:
                with self.subTest(options=options):
                    expected = stable
                    for name in always + chosen:
                        expected = apply(expected, self.patches[name]["variants"]["current"])
                    self.assertEqual(prepare.configure(self.pristine, options=options), expected)


def main():
    if "--update" in sys.argv[1:]:
        SNAPSHOT.parent.mkdir(exist_ok=True)
        SNAPSHOT.write_text(render(snapshot()), encoding="utf-8", newline="\n")
        print(f"wrote {SNAPSHOT.relative_to(ROOT).as_posix()}")
        return
    unittest.main()


if __name__ == "__main__":
    main()
