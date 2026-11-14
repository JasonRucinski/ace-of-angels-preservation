"""Golden snapshot of every byte the client patches write; game-free.

For each of the 22 patch IDs and both offline experiments, and for every
variant a module still recognizes, this lists each region's file offset,
original bytes and patched bytes, plus the runtime .data-tail reservations,
and compares them with tools/snapshots/patch_regions.json. A refactor that
moves or changes a single patch byte fails here.

  python -I tools/test_patch_layout.py            compare with the snapshot
  python -I tools/test_patch_layout.py --update   rewrite the snapshot

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
import struct
import sys
import unittest
from pathlib import Path
from unittest import mock

from aoa.client.patches import archive_terminator  # noqa: E402
from aoa.client.patches import asteroid_render  # noqa: E402
from aoa.client.patches import cursor_warp  # noqa: E402
from aoa.client.patches import explicit_protection  # noqa: E402
from aoa.client.patches import frame_clock  # noqa: E402
from aoa.client.patches import station_host  # noqa: E402
from aoa.client.patches import menu_aspect  # noqa: E402
from aoa.client.patches import object_persistence  # noqa: E402
from aoa.client.patches import online_terrain  # noqa: E402
from aoa.client.patches import own_ship_menu  # noqa: E402
from aoa.client.patches import own_ship_model  # noqa: E402
from aoa.client import base  # noqa: E402
from aoa.client.patches import physics_timestep  # noqa: E402
from aoa.client.patches import powerup_pickup  # noqa: E402
from aoa.client import prepare  # noqa: E402
from aoa.client.experiments import render_clock_experiment  # noqa: E402
from aoa.client.experiments import render_culling_experiment  # noqa: E402
from aoa.client.patches import solid_world_render  # noqa: E402
from aoa.client.patches import station_detail  # noqa: E402
from aoa.client.patches import texture32  # noqa: E402
from aoa.client.patches import third_person  # noqa: E402
from aoa.client.patches import visibility_fix  # noqa: E402
from aoa.client.patches import world_detail  # noqa: E402

from aoa.paths import ROOT
SNAPSHOT = Path(__file__).resolve().parent / "snapshots/patch_regions.json"
PE_FACTS = ROOT / "evidence/2.9.2/pe_facts.json"
BASE = base.IMAGE_BASE
TEXT_PADDING = (0x58B200, 0x58C000)   # .text zero padding mapped by logger-size-v1 (C5)
DATA_TAIL = (0x60D200, 0x60E000)      # zero-filled .data tail mapped by logger-size-v1 (C5)
# Original bytes at patch_client's sites, as its configure() expects them.
PATCH_CLIENT_SITES = {0x551775: "6a20", 0x526D00: "64a1000000006aff", 0x526F8C: "64890d0000000083c424c3",
                      0x527210: "8b4c24088d44240c", 0x527233: "e868fdffff8b065ec3"}
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


def h(value):
    return f"0x{value:06x}"


def pe_facts():
    return json.loads(PE_FACTS.read_text(encoding="utf-8"))


def pe_image():
    """Zero image of the client's size with its real PE section table (pe_facts.json)."""
    facts = pe_facts()
    image = bytearray(facts["bytes"])
    image[:2], e_lfanew = b"MZ", 0x80
    struct.pack_into("<I", image, 0x3C, e_lfanew)
    image[e_lfanew:e_lfanew + 4] = b"PE\0\0"
    struct.pack_into("<HH", image, e_lfanew + 4, int(facts["machine"], 16), len(facts["sections"]))
    struct.pack_into("<H", image, e_lfanew + 20, 0xE0)
    for i, section in enumerate(facts["sections"]):
        at = e_lfanew + 24 + 0xE0 + 40 * i
        image[at:at + 8] = section["name"].encode().ljust(8, b"\0")
        struct.pack_into("<IIII", image, at + 8, int(section["vsize"], 16), int(section["va"], 16) - BASE,
                         int(section["raw_size"], 16), int(section["raw_off"], 16))
        struct.pack_into("<I", image, at + 36, int(section["chars"], 16))
    return image


def synthetic_pristine():
    """pe_image() with every patch's original bytes at its sites.

    Original bytes that two patches both claim must agree, so this also checks
    that the modules describe one and the same client.
    """
    image, owner = pe_image(), {}
    for name, patch in collect().items():
        for regions in patch["variants"].values():
            for r in regions:
                offset = int(r["offset"], 16)
                for i, byte in enumerate(bytes.fromhex(r["old"])):
                    if owner.get(offset + i, (byte,))[0] != byte:
                        raise AssertionError(f"{name} and {owner[offset + i][1]} disagree on the original "
                                             f"byte at file offset {offset + i:#x}")
                    owner[offset + i] = (byte, name)
                    image[offset + i] = byte
    return bytes(image)


def region(offset, old, new):
    assert len(old) == len(new), offset
    return {"va": h(offset + BASE), "offset": h(offset), "size": len(old), "old": old.hex(), "new": new.hex()}


def listed(triples):
    return sorted((region(off, old, new) for off, old, new in triples), key=lambda r: r["va"])


def runtime(va, size, what):
    return {"va": h(va), "size": size, "what": what}


def patch_client_record():
    """patch_client.configure() run on a synthetic pristine image: its own record of every write."""
    image = pe_image()
    for va, old in PATCH_CLIENT_SITES.items():
        image[va - BASE:va - BASE + len(old) // 2] = bytes.fromhex(old)
    with mock.patch.object(base, "PRISTINE_292", hashlib.sha256(image).hexdigest()):
        return base.configure(bytes(image))[1]["patches"]


def collect():
    """{patch id: {module, variants: {label: [region]}, runtime_data?, pe_header?}}."""
    patches = {}

    def add(name, module, variants, **extra):
        patches[name] = {"module": module, "variants": {k: listed(v) for k, v in variants.items()}, **extra}

    size, lock, header = [], [], []
    for entry in patch_client_record():
        if "va" not in entry:
            header.append({"field": entry["patch"], "old": entry["old"], "new": entry["new"]})
            continue
        assert int(entry["file_offset"], 16) == int(entry["va"], 16) - BASE, entry
        triple = (int(entry["file_offset"], 16), bytes.fromhex(entry["old"]), bytes.fromhex(entry["new"]))
        (size if entry["patch"] == "dxgfx-logger-size" else lock).append(triple)
    add("logger-size-v1", "patch_client", {"current": size}, pe_header=header)
    add("logger-lock-v1", "patch_client", {"current": lock},
        runtime_data=[runtime(base.LOCK_OWNER, 4, "lock owner"),
                      runtime(base.LOCK_DEPTH, 4, "lock depth")])
    add("station-hostname", "local_station + prepare_client.host_field",
        {"current": [(station_host.OFFSET, station_host.ORIGINAL, prepare.host_field("localhost"))]})
    m = physics_timestep
    add("zero-time-physics-v1", "physics_timestep", {"current": [
        (m.SITE_OFFSET, m.DISPLACED, base.jmp_patch(m.SITE, m.CAVE, len(m.DISPLACED))),
        (m.CAVE_OFFSET, bytes(len(m.guard_code())), m.guard_code())]})
    add("background-network-v1", "prepare_client", {"current": [
        (prepare.BACKGROUND_OFFSET, prepare.BACKGROUND_JNE, prepare.BACKGROUND_NOP)]})
    for name, m in (("archive-terminator-v1", archive_terminator), (explicit_protection.NAME, explicit_protection)):
        code = m.cave_code()
        add(name, m.__name__.rpartition(".")[2], {"current": [
            (m.SITE_OFFSET, m.DISPLACED, base.jmp_patch(m.SITE, m.CAVE, len(m.DISPLACED))),
            (m.CAVE_OFFSET, bytes(len(code)), code)]})
    m = online_terrain
    jump = (m.SITE_OFFSET, m.DISPLACED, base.jmp_patch(m.SITE, m.CAVE, len(m.DISPLACED)))
    add(m.NAME, "online_terrain", {
        label: [jump, (m.CAVE_OFFSET, bytes(m.REGION), cave)]
        for label, cave in (("current", m.cave_code()), (m.V2_NAME, m.v2_code()), (m.LEGACY_NAME, m.legacy_code()))})
    for m in (menu_aspect, cursor_warp, frame_clock, visibility_fix, own_ship_model, powerup_pickup,
              asteroid_render, solid_world_render, station_detail, world_detail, texture32, object_persistence):
        add(m.NAME, m.__name__.rpartition(".")[2], {"current": m.regions()})
    add(third_person.NAME, "third_person", {"current" if v == "v3" else v: third_person.regions(v)
                                            for v in third_person.VARIANTS},
        runtime_data=[runtime(third_person.FAKE, third_person.ARMED + 1 - third_person.FAKE,
                              "FAKE..ARMED block (own_ship_menu RESTRICT inside, C5)")])
    add(own_ship_menu.NAME, "own_ship_menu", {"current": own_ship_menu.regions(), "legacy": own_ship_menu.regions(True)},
        runtime_data=[runtime(own_ship_menu.RESTRICT, 1, "RESTRICT")])
    add("experiment-render-clock", "render_clock_experiment", {"current": render_clock_experiment.regions()})
    add("experiment-render-culling", "render_culling_experiment", {"current": render_culling_experiment.regions()})
    return dict(sorted(patches.items()))


def snapshot():
    return {"about": "Every client patch region; regenerate with python -I tools/test_patch_layout.py --update "
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
                    self.assertEqual(module.configure(apply(self.pristine, regions), True), current)

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
