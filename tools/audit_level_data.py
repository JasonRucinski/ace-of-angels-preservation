"""Audit every recovered client for level, scenario and mission data.

Reads the extracted installers under work/asset-review/<version>/ and
writes full decodes to work/asset-review/level-data/ (ignored: they hold
coordinates) plus a summary without coordinates to
evidence/asset-review/level-data.json.

Checks:
  - every .AOA/.ODB archive: bytes not covered by any directory entry
  - JRMAP.TRN in each installer: hash, strict decode (tools/decode_trn.py)
  - SCENARIOS.AOA entries: strict decode (tools/decode_scenario.py)
  - SCRIPTS.AOA entries: hashes, changes between versions
  - layout Gobs: hashes per version; 2.0.0 TestScene via decode_legacy_layout

Usage: python -I tools/audit_level_data.py
"""
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import decode_legacy_layout  # noqa: E402
import decode_scenario  # noqa: E402
import decode_trn  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
REVIEW = ROOT / "work" / "asset-review"
OUT = REVIEW / "level-data"
EVIDENCE = ROOT / "evidence" / "asset-review" / "level-data.json"
VERSIONS = ["2.0.0", "2.7.1", "2.8.0", "2.8.2", "2.9.2"]
LAYOUTS = ("arena1a ctf_arena ctf_arena_b newterrain outerchange ast_fld_a ast_fld_b ast_fld_c "
           "ast_fld_d ctf_base hu_base_a hu_base_b hy_base_test hy_winga hybase2lay irrosa01 "
           "ze_winga ze_wingb hittest testscene").split()


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def archive_gaps(index):
    ents = sorted(index["entries"], key=lambda e: e["offset"])
    size = (ROOT / index["archive"]).stat().st_size
    pos, gaps = 260 + len(ents) * 280, 0
    for e in ents:
        gaps += max(0, e["offset"] - pos)
        pos = max(pos, e["offset"] + e["size"])
    return {"entries": len(ents), "bytes": size, "uncovered_bytes": gaps + max(0, size - pos)}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    report = {"versions": {}, "layout_sha256": {}}
    for v in VERSIONS:
        base = REVIEW / v
        rec = {"archives": {}, "scripts": {}, "scenarios": {}}
        for idx in sorted((base / "assets").glob("*/_index.json")):
            index = json.loads(idx.read_text(encoding="utf-8"))
            rec["archives"][idx.parent.name] = archive_gaps(index)
            if idx.parent.name == "SCRIPTS":
                rec["scripts"] = {e["name"]: e["sha256"] for e in index["entries"]}
            if idx.parent.name == "SCENARIOS":
                for e in index["entries"]:
                    dec = decode_scenario.decode(Path(ROOT / e["extracted_to"]).read_bytes())
                    (OUT / f"{e['name']}-{v}.json").write_text(json.dumps(dec, indent=1), encoding="utf-8")
                    rec["scenarios"][e["name"]] = {
                        "sha256": dec["sha256"], "consumed_exactly": dec["consumed_exactly"],
                        "teams": [t["name"] for t in dec["teams"]],
                        "groups": [{"name": g["name"], "team": g["team"], "members": len(g["members"]),
                                    "ship_types": sorted({m["ship_type"] for m in g["members"]}),
                                    "orders": [f"{o['verb']} {o['target_group']}" for o in g["orders"]],
                                    "waypoints": [w["action"] for w in g["waypoints"]]}
                                   for g in dec["groups"]]}
            if idx.parent.name == "AOAOBJECTS":
                for e in index["entries"]:
                    stem = e["name"].lower().rsplit(".", 1)[0]
                    if e["name"].lower().endswith(".gob") and stem in LAYOUTS:
                        report["layout_sha256"].setdefault(stem, {})[v] = e["sha256"]
                        if v == "2.0.0" and stem == "testscene":
                            dec = decode_legacy_layout.decode(Path(ROOT / e["extracted_to"]).read_bytes())
                            (OUT / "TestScene-2.0.0.json").write_text(json.dumps(dec, indent=1), encoding="utf-8")
                            rec["testscene"] = {"sha256": dec["sha256"], "nodes": dec["node_count"],
                                                "skipped": [s["name"] for s in dec["skipped_names"]]}
        trn = sorted((base / "members").glob("*_JRMAP.TRN"))
        if trn:
            dec = decode_trn.decode(trn[0].read_bytes())
            (OUT / f"JRMAP-{v}.json").write_text(json.dumps(dec, indent=1), encoding="utf-8")
            kinds = {}
            for r in dec["records"]:
                key = f"{r['object'] or '-'}/kind{r['kind']}"
                kinds[key] = kinds.get(key, 0) + 1
            rec["jrmap_trn"] = {"sha256": dec["sha256"], "records": dec["record_count"],
                                "links": dec["link_count"], "consumed_exactly": dec["consumed_exactly"],
                                "objects": dict(sorted(kinds.items()))}
        report["versions"][v] = rec
    EVIDENCE.write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8")
    gaps = sum(a["uncovered_bytes"] for r in report["versions"].values() for a in r["archives"].values())
    print(json.dumps({"archives": sum(len(r["archives"]) for r in report["versions"].values()),
                      "uncovered_archive_bytes": gaps,
                      "jrmap_hashes": sorted({r["jrmap_trn"]["sha256"] for r in report["versions"].values()}),
                      "evidence": EVIDENCE.relative_to(ROOT).as_posix()}, indent=1))


if __name__ == "__main__":
    main()
