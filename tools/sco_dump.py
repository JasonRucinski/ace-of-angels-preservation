"""Decode AoA .Sco object configs (ships, stations, pods) into JSON + a summary table.

Usage:
    python -I tools/sco_dump.py <AOAOBJECTS export dir> <out.json> [summary.md]

Layout recovered from the data (strings use the hWv\\x05 tag, see gob2obj.py):
  header strings  name, class code (e.g. S621), faction, (empty), .Gob model
  then a list of systems; each system is a name string followed by a
  284-byte block whose first fields are
      u32 system type (12 gun, 8 ECM, 7 scanner, 4 shield, 6 hull, 1 engine,
                       21 internal hull, 20 missile rack, 0 power plant, ...)
      f32 hit points  (matches the in-game Damage panel)
      f32 x4          further per-type parameters (kept raw)
  guns are followed by mount point (DummyNN, a hardpoint in the .Gob), weapon
  id (G-280) and firing sound; racks by mount, slot and missile type.
Type ids and the meaning of the further parameters are inferred from the
data, not from client code; the raw floats are kept so nothing is lost.
"""
import json
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gob2obj  # noqa: E402

SYSTEM_BLOCK = 284


def decode(d):
    st = gob2obj.strings(d)
    head = [t for _, _, t in st[:5]]
    out = {"name": head[0], "class": head[1], "faction": head[2], "model": head[4] if len(head) > 4 else "",
           "systems": []}
    for i, (start, after, t) in enumerate(st):
        nxt = st[i + 1][0] if i + 1 < len(st) else len(d)
        if not t or nxt - after != SYSTEM_BLOCK:
            continue
        stype = struct.unpack_from("<I", d, after)[0]
        hp, *params = struct.unpack_from("<5f", d, after + 4)
        sysrec = {"name": t, "type": stype, "hp": round(hp, 3), "params": [round(p, 3) for p in params]}
        follow = [s for _, _, s in st[i + 1:i + 6]]
        if follow and follow[0] and stype in (12, 20):  # mount names vary: Dummy05, Dmy-G04, RACK_I_02
            sysrec["mount"] = follow[0]
            if stype == 12:   # gun: weapon id, firing sound
                sysrec["weapon"], sysrec["sound"] = (follow[1:3] + ["", ""])[:2]
            elif stype == 20:  # missile rack: first non-numeric name is the missile type
                sysrec["missile"] = next((s for s in follow[1:5] if s and not s.isdigit()), "")
        out["systems"].append(sysrec)
    tail = [t for _, _, t in st[-2:] if t]
    if tail:
        out["trailer"] = tail[-1]
    return out


def main():
    src, out_json = Path(sys.argv[1]), Path(sys.argv[2])
    objs = [decode(p.read_bytes()) for p in sorted(src.glob("*.[Ss]co"))]
    out_json.write_text(json.dumps(objs, indent=1), encoding="utf-8")
    if len(sys.argv) > 3:
        rows = ["| Object | Class | Faction | Model | Hull | Int. hull | Shield | Engine | Weapons |",
                "|---|---|---|---|---|---|---|---|---|"]
        for o in objs:
            hp = {s["name"]: s["hp"] for s in o["systems"]}
            guns = [s["name"] for s in o["systems"] if s["type"] == 12]
            racks = [s.get("missile") or "?" for s in o["systems"] if s["type"] == 20]
            weapons = ", ".join(f"{g} x{guns.count(g)}" for g in dict.fromkeys(guns))
            if racks:
                weapons += ("; " if weapons else "") + "missiles: " + ", ".join(racks)
            rows.append(f"| {o['name']} | {o['class']} | {o['faction']} | {o['model']} | {hp.get('Hull', '')} | "
                        f"{hp.get('Internal Hull', '')} | {hp.get('Shield', '')} | {hp.get('Engine', '')} | {weapons} |")
        Path(sys.argv[3]).write_text("\n".join(rows) + "\n", encoding="utf-8")
    print(f"decoded {len(objs)} .Sco files -> {out_json}")


if __name__ == "__main__":
    main()
