"""The client patch regions and a synthetic pristine image, for the suites that need them.

collect() lists every region each patch module writes (the content of
tests/snapshots/patch_regions.json); synthetic_pristine() is a zero image of
the 2.9.2 client's size, with its real section table (evidence/2.9.2/
pe_facts.json) and every patch's original bytes at its sites. Used by
test_patch_layout, test_prepare_client and test_client_launcher. Standard
library and aoa only; no game file is read.
"""
import hashlib
import json
import struct
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
PE_FACTS = ROOT / "evidence/2.9.2/pe_facts.json"
BASE = base.IMAGE_BASE
# Original bytes at patch_client's sites, as its configure() expects them.
PATCH_CLIENT_SITES = {0x551775: "6a20", 0x526D00: "64a1000000006aff", 0x526F8C: "64890d0000000083c424c3",
                      0x527210: "8b4c24088d44240c", 0x527233: "e868fdffff8b065ec3"}


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
