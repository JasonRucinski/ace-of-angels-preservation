"""Account for Arena1a nodes using exported data and pinned client dispatch evidence.

Writes an asset-review manifest under ignored work/ and a compact evidence report.
No game assets or executables are modified. This is not in-game acceptance.
"""
import collections
import hashlib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import scene2obj
from check_arena_geometry import inspect_geometry
from patch_client import PRISTINE_292
from pe_util import PE

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_DISPATCH = [0x4964F8, 0x496423, 0x4964F8, 0x496280, 0x4964F8,
                     0x4962F7, 0x4963E4, 0x4964F8, 0x496141, 0x4964F8]


def classify(node, objects, source):
    category, name = node["category"], node["name"]
    if category == 1:
        return {"group": "turret_marker", "status": "blocked", "reason": "Category 1 skipped by terrain creation dispatch; attachment transforms, spawning and AI are not implemented."}
    if category == 5:
        return {"group": "flag_marker", "status": "blocked", "reason": "Category 5 skipped by terrain creation dispatch; preview geometry does not implement flag rules."}
    if category in (4, 7):
        object_name = "Buoy" if category == 4 else "Cube"
        model = objects[object_name.casefold()]["gob"]
        return {"group": "navigation" if category == 4 else "safe_zone", "status": "native_path_identified",
                "object": object_name, "model": model,
                "reason": "Native category dispatch selects this object; online creation and behavior still require verification."}
    if category == 6:
        return {"group": "warp_rail", "status": "blocked", "object": "WarpGate", "model": objects["warpgate"]["gob"],
                "reason": "Requires handler flag +0x18 and linked child type 0x51870001; destination/link reconstruction and online behavior unverified."}
    if category == 9:
        # This is a lookup candidate, not a proved replacement for the original
        # tokenizer. The trailing-digit loop is visible at 0x496187..0x4961B3.
        token = re.sub(r"[0-9]+$", "", name.split()[0])
        if token.casefold() in objects:
            obj = objects[token.casefold()]
            return {"group": "named_object", "status": "asset_resolved", "object": obj["object"], "model": obj["gob"]}
        nested = next((p for p in source.glob("*.Gob") if p.stem.casefold() == token.casefold()), None)
        if nested and scene2obj.is_scene(nested.read_bytes()):
            return {"group": "nested_layout", "status": "preview_expanded", "layout": nested.stem,
                    "reason": "Preview uses child * parent transform; client recursion exists at 0x496279. Online acceptance pending."}
        group = ("service_marker" if name.startswith(("ZA", "ZMissile", "ZRepair", "ZShield")) else
                 "group_marker" if name.startswith("Group") else
                 "link_target" if name.startswith(("WarpTgt", "Dummy")) else "unresolved")
        return {"group": group, "status": "blocked", "lookup_candidate": token,
                "reason": "No matching local object configuration or graphics layout for this lookup candidate; helper/link semantics may apply. Do not substitute a guessed asset or rule."}
    return {"group": "other_category", "status": "blocked", "reason": "Native category semantics not established for this node."}


def main():
    source = ROOT / "work/2.9.2/export/AOAOBJECTS"
    output = ROOT / "work/arena1a-review"
    output.mkdir(parents=True, exist_ok=True)
    client = ROOT / "game/2.9.2/AOACLIENT.EXE.orig"
    if hashlib.sha256(client.read_bytes()).hexdigest() != PRISTINE_292:
        raise ValueError("expected original 2.9.2 client")
    pe = PE(client)
    if [pe.u32(0x496790 + i * 4) for i in range(10)] != EXPECTED_DISPATCH:
        raise ValueError("terrain dispatch differs from recovered evidence")
    objects = scene2obj.sco_models(source)
    nodes = scene2obj.read_nodes((source / "Arena1a.Gob").read_bytes())
    classified = [{**node, **classify(node, objects, source)} for node in nodes]
    expanded = [{**node, **classify(node, objects, source)}
                for node in scene2obj.expanded_nodes(source, "Arena1a", True)]
    scene2obj.export(source, "Arena1a", output, "../2.9.2/TEXTURES", objects, {}, True)
    manifest = {"scope": "Static node/asset inventory and original-code branch evidence; not online loading or gameplay",
                "source_sha256": hashlib.sha256((source / "Arena1a.Gob").read_bytes()).hexdigest(),
                "root_nodes": classified, "expanded_nodes": expanded,
                "root_categories": dict(collections.Counter(n["category"] for n in nodes)),
                "root_groups": dict(collections.Counter(n["group"] for n in classified)),
                "all_nodes_working": False}
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    summary = {k: manifest[k] for k in ("scope", "source_sha256", "root_categories", "root_groups", "all_nodes_working")}
    summary.update(root_node_count=len(nodes), expanded_node_count=len(expanded),
                   previously_omitted_turret_records=80, geometry=inspect_geometry(output / "Arena1a.obj"),
                   native_dispatch={str(i + 1): hex(address) for i, address in enumerate(EXPECTED_DISPATCH)},
                   original_client_sha256=PRISTINE_292,
                   remaining=["original-client Arena1a loading and collision", "online creation of terrain, navigation and safe zones",
                              "turret attachment transforms, ownership and AI", "warp links and destinations",
                              "repair/shield/missile marker definitions and behavior", "group/dummy semantics",
                              "map-specific spawn acceptance"],
                   preview_coordinates="OBJ negates game Z; nested matrices compose child * parent; root marker hierarchy is not fully decoded")
    (ROOT / "evidence/2.9.2/arena1a_audit_20261021.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
