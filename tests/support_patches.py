"""The client patch regions and a synthetic pristine image, for the suites that need them.

collect() lists every region each registered patch writes (the content of
tests/snapshots/patch_regions.json); synthetic_pristine() is a zero image of
the 2.9.2 client's size, with its real section table (evidence/2.9.2/
pe_facts.json) and every patch's original bytes at its sites, and
synthetic_client() makes the preparation code accept it. Used by the client
suites. Standard library and aoa only; no game file is read.
"""
import contextlib
import hashlib
import json
import struct
import types
import unittest
from unittest import mock

from aoa.client import patches as registry
from aoa.client import prepare
from aoa.client.experiments import render_culling_experiment
from aoa.client.patches import base as patching
from aoa.client.patches import logger
from aoa.client.patches import own_ship_menu
from aoa.client.patches import station_host
from aoa.client.patches import third_person
from aoa.paths import ROOT
from archive.offline_baseline import render_clock_experiment

PE_FACTS = ROOT / "evidence/2.9.2/pe_facts.json"
# The user's original client, which the needs-game halves of the client suites run on.
ORIGINAL = ROOT / "game/2.9.2/AOACLIENT.EXE.orig"
needs_game = unittest.skipUnless(ORIGINAL.is_file(), "needs the user's original 2.9.2 client "
                                                     "(game/2.9.2/AOACLIENT.EXE.orig)")
# Its exported objects (tools/export_assets.py), which some LOD checks also read.
EXPORT = ROOT / "work/2.9.2/export"
needs_export = unittest.skipUnless((EXPORT / "AOAOBJECTS").is_dir(), "needs the exported client objects "
                                                                     "(work/2.9.2/export/AOAOBJECTS)")
BASE = patching.IMAGE_BASE
# Where each patch lived when the snapshot was taken, if it has moved since.
SNAPSHOT_MODULE = {"logger-size-v1": "patch_client", "logger-lock-v1": "patch_client",
                   "background-network-v1": "prepare_client"}
# Snapshot labels of older variants.
SNAPSHOT_VARIANT = {"third-person-camera-v2": "v2", "third-person-camera-v1": "v1",
                    own_ship_menu.LEGACY_NAME: "legacy"}


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
    # Optional header: PE32 magic, image base and image size, so aoa.formats.pe can map it.
    struct.pack_into("<H", image, e_lfanew + 24, 0x10B)
    struct.pack_into("<I", image, e_lfanew + 24 + 28, int(facts["image_base"], 16))
    struct.pack_into("<I", image, e_lfanew + 24 + 56, int(facts["size_of_image"], 16))
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


@contextlib.contextmanager
def synthetic_client(pristine=None):
    """Make the preparation code accept the synthetic client: its pristine and
    stability-patched hashes stand in for the real 2.9.2 ones."""
    pristine = synthetic_pristine() if pristine is None else pristine
    pristine_sha = hashlib.sha256(pristine).hexdigest()
    with mock.patch.object(logger, "PRISTINE_292", pristine_sha):
        stable_sha = hashlib.sha256(logger.stabilize(pristine)).hexdigest()
    with mock.patch.object(logger, "PRISTINE_292", pristine_sha), \
            mock.patch.object(logger, "STABLE_SHA256", stable_sha):
        yield


def region(offset, old, new):
    assert len(old) == len(new), offset
    return {"va": h(offset + BASE), "offset": h(offset), "size": len(old), "old": old.hex(), "new": new.hex()}


def triples(patch, regions=None):
    """(file offset, old, new) of a Patch descriptor's regions (default: its current variant)."""
    return [(r.va - BASE, r.old, r.new) for r in (patch.regions if regions is None else regions)]


def variants(patch, labels=None):
    """{snapshot label: [(file offset, old, new)]} of every variant; the current one is "current"."""
    labels = {patch.id: "current", **(labels or {})}
    return {labels.get(name, name): triples(patch, regions) for name, regions in patch.variants}


def regions_view(module):
    """The module as aoa.emulation.render_pipeline.run(patch=...) reads one:
    regions() as (file offset, old, new), and CENTER_VISIBLE if it has it."""
    return types.SimpleNamespace(regions=lambda: triples(module.PATCH),
                                 **({"CENTER_VISIBLE": module.CENTER_VISIBLE}
                                    if hasattr(module, "CENTER_VISIBLE") else {}))


def listed(triples):
    return sorted((region(off, old, new) for off, old, new in triples), key=lambda r: r["va"])


def runtime(va, size, what):
    return {"va": h(va), "size": size, "what": what}


def module_of(patch_id):
    """Name of the module under aoa/client/patches that exports this patch."""
    for name, module in vars(registry).items():
        found = getattr(module, "PATCHES", None) or (getattr(module, "PATCH", None),)
        if any(p is not None and p.id == patch_id for p in found if hasattr(p, "id")):
            return name
    raise KeyError(patch_id)


def collect():
    """{patch id: {module, variants: {label: [region]}, runtime_data?, pe_header?}}."""
    patches = {}

    def add(name, module, variants, **extra):
        patches[name] = {"module": module, "variants": {k: listed(v) for k, v in variants.items()}, **extra}

    extras = {
        "logger-size-v1": {"pe_header": [{"field": f"{name} VirtualSize", "old": hex(old), "new": hex(new)}
                                         for name, old, new in logger.HEADER]},
        "logger-lock-v1": {"runtime_data": [runtime(logger.LOCK_OWNER, 4, "lock owner"),
                                            runtime(logger.LOCK_DEPTH, 4, "lock depth")]},
        third_person.NAME: {"runtime_data": [runtime(third_person.FAKE, third_person.ARMED + 1 - third_person.FAKE,
                                                     "FAKE..ARMED block (own_ship_menu RESTRICT inside, C5)")]},
        own_ship_menu.NAME: {"runtime_data": [runtime(own_ship_menu.RESTRICT, 1, "RESTRICT")]},
    }
    for patch in registry.REGISTRY:
        add(patch.id, SNAPSHOT_MODULE.get(patch.id) or module_of(patch.id), variants(patch, SNAPSHOT_VARIANT),
            **extras.get(patch.id, {}))
    add("station-hostname", "local_station + prepare_client.host_field",
        {"current": [(station_host.OFFSET, station_host.ORIGINAL, prepare.host_field("localhost"))]})
    add("experiment-render-clock", "render_clock_experiment", {"current": render_clock_experiment.regions()})
    add("experiment-render-culling", "render_culling_experiment", {"current": render_culling_experiment.regions()})
    return dict(sorted(patches.items()))
