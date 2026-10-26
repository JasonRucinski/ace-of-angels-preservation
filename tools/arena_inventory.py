"""Inventory extracted local scene/scenario assets; does not claim hosting support.

Usage: python -I tools/arena_inventory.py <export-dir> <scenes-dir> <output.json>
Scene node JSON comes from scene2obj.py; its object matching is heuristic.
"""
import hashlib
import json
import sys
from pathlib import Path

def inventory(export, scenes):
    objects = export / "AOAOBJECTS"
    gob_files = {p.stem.casefold(): p for p in objects.glob("*.Gob")}
    layouts = []
    for path in sorted(scenes.glob("*_nodes.json")):
        name = path.stem.removesuffix("_nodes")
        source = gob_files[name.casefold()]
        nodes = json.loads(path.read_text())
        models = sorted({n["model"] for n in nodes if "model" in n})
        layouts.append({
            "name": name, "nodes": len(nodes),
            "geometry_nodes": sum("model" in n for n in nodes),
            "marker_nodes": sum("model" not in n for n in nodes),
            "missing_referenced_models": [m for m in models if m.casefold() not in gob_files],
            "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        })
    scenarios = [{"name": p.name, "bytes": p.stat().st_size,
                  "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
                 for p in sorted((export / "SCENARIOS").iterdir()) if p.is_file()]
    return {"scope": "Extracted local assets only; no multiplayer rules or hosting verification",
            "layouts": layouts, "scenarios": scenarios,
            "backdrops": sorted(p.stem for p in gob_files.values()
                                if p.stem.casefold().startswith("spacebkgd"))}


if __name__ == "__main__":
    result = inventory(Path(sys.argv[1]), Path(sys.argv[2]))
    Path(sys.argv[3]).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
