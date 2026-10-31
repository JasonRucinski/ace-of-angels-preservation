"""Build a new map from a JSON spec as a native 2.9.2 terrain file (*.TRN).

  python -I tools/make_map.py build   config/maps/crucible.json out.trn
  python -I tools/make_map.py install config/maps/crucible.json work/custom-map/client [--copy-from game/2.9.2]
  python -I tools/make_map.py serve   config/maps/crucible.json work/custom-map/client
  python -I tools/make_map.py obj     config/maps/crucible.json EXPORT/AOAOBJECTS OUT_DIR [TEX_DIR]

The client has no free map slot: the online-terrain cave's 20-entry table
fills its region, and its only .TRN entry is JRMAP's `jrmap292.trn`. So
`install` writes the new map into that slot of a separate play copy of the
client (made with --copy-from when the folder does not exist yet), and
refuses the main game/2.9.2 folder, whose JRMAP stays the original. `serve`
runs the loopback relay as map JRMAP from that copy, at the spec's spawn,
with the spec's power-up zones.

Spec (JSON): {"name", "spawn": [x, y, z], "objects": [...]}. Each object:
  {"object": ODB object, "name": instance name (optional),
   "pos": [x, y, z], "rot": [yaw, pitch, roll] degrees (optional)}
  {"zone": "safe", "pos": [...], "half": h}
  {"zone": "powerup", "pos": [...], "half": h, "type": 0..4}
  {"nav": waypoint name, "pos": [...], "object": model (default Buoy)}
Power-up types (findings 9.44): 0 missile, 1/2/3 shield +5/+10/+20, 4 repair.
At most ten waypoints; `serve` has the relay send them as LoadObject kind 3
(navigation_buoys.py, slots 90..99) with sustained delivery.

Records follow the editor-saved JRMAP layout as decode_trn converts it:
names at +0x00/+0x40/+0x80, the rotated x axis at +0x98 and z axis at +0xA4
(the two rows ReadInTerrain reads; JRMAP's identity is (1,0,0),(0,0,1)),
position at +0xC4, 1.0 at +0x100, half-size or position x at +0x104,
power-up type at +0x194, kind at +0x200, 4 at +0x204 for kinds 0 and 2, and
the sentinel at +0x218. Rotations are Direct3D yaw-pitch-roll (row vectors,
roll then pitch then yaw); positive yaw turns +z toward +x. The reader takes
no scale. Kinds 0 (static model), 2 (safe zone), 3 (navigation waypoint)
and 6 (power-up zone) are written. The 2.9.2 client gates kind 3 off, as it
does turrets, warps and flags, which are not written.
"""
import argparse
import hashlib
import json
import math
import re
import shutil
import struct
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import decode_trn  # noqa: E402
import online_terrain  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SLOT_MAP = "JRMAP"
SLOT_FILE = online_terrain.MAPS[online_terrain.MAP_NAMES.index(SLOT_MAP)][2]
KIND_MODEL, KIND_SAFE, KIND_NAV, KIND_POWERUP = 0, 2, 3, decode_trn.KIND_POWERUP_ZONE
NAME_MAX = 23  # 24-byte field with its NUL
COPY_SKIP = ("Logs", "Capture Images")


def rotation(yaw=0.0, pitch=0.0, roll=0.0):
    """Rows of the Direct3D yaw-pitch-roll matrix (images of x, y, z)."""
    cy, sy = math.cos(math.radians(yaw)), math.sin(math.radians(yaw))
    cp, sp = math.cos(math.radians(pitch)), math.sin(math.radians(pitch))
    cr, sr = math.cos(math.radians(roll)), math.sin(math.radians(roll))
    ry = ((cy, 0, -sy), (0, 1, 0), (sy, 0, cy))
    rx = ((1, 0, 0), (0, cp, sp), (0, -sp, cp))
    rz = ((cr, sr, 0), (-sr, cr, 0), (0, 0, 1))

    def mul(a, b):
        return tuple(tuple(sum(a[r][k] * b[k][c] for k in range(3)) for c in range(3)) for r in range(3))
    return mul(mul(rz, rx), ry)


def _finite(values, n, what):
    if not (isinstance(values, list) and len(values) == n and
            all(isinstance(v, (int, float)) and math.isfinite(v) for v in values)):
        raise ValueError(f"{what}: expected {n} finite numbers")
    return [float(v) for v in values]


def _name(text, what):
    raw = text.encode("latin1")
    if len(raw) > NAME_MAX or b"\0" in raw:
        raise ValueError(f"{what}: {text!r} must be at most {NAME_MAX} characters")
    return raw


def record(entry, index=0):
    """One 540-byte 2.9.2 record for a spec entry (see module notes)."""
    what = f"object {index}"
    pos = _finite(entry.get("pos"), 3, what + " pos")
    yaw, pitch, roll = _finite(entry.get("rot", [0, 0, 0]), 3, what + " rot")
    name = _name(entry.get("name", "---"), what + " name")
    r = bytearray(decode_trn.REC_292)
    x_axis, y_axis, z_axis = rotation(yaw, pitch, roll)
    struct.pack_into("<9f", r, 0x98, *x_axis, *z_axis, *y_axis)
    struct.pack_into("<3f", r, 0xC4, *pos)
    struct.pack_into("<f", r, 0x100, 1.0)
    zone = entry.get("zone")
    if "nav" in entry:
        # Kind 3, as JRMAP's buoys; the server sends it (see module notes).
        name = _name(entry["nav"], what + " nav")
        database, obj, kind, x_field = (decode_trn.DATABASE, _name(entry.get("object", "Buoy"), what + " object"),
                                        KIND_NAV, pos[0])
    elif zone is None:
        obj = entry.get("object")
        if not isinstance(obj, str) or not obj:
            raise ValueError(f"{what}: needs an ODB object or a zone")
        database, obj, kind, x_field = decode_trn.DATABASE, _name(obj, what + " object"), KIND_MODEL, pos[0]
    elif zone in ("safe", "powerup"):
        half = entry.get("half")
        if not (isinstance(half, (int, float)) and math.isfinite(half) and half > 0):
            raise ValueError(f"{what}: zone half-size must be positive")
        x_field = float(half)
        if zone == "safe":
            # Named like the layout path's safe zone so AddTerrainObject keeps it.
            database, obj, kind = decode_trn.DATABASE, decode_trn.SAFE_ZONE_OBJECT, KIND_SAFE
        else:
            ptype = entry.get("type")
            if ptype not in range(5):
                raise ValueError(f"{what}: power-up type must be 0..4")
            # Unnamed, as all eleven of JRMAP's; the relay, not the client, uses them.
            database, obj, kind = b"", b"", KIND_POWERUP
            struct.pack_into("<I", r, 0x194, ptype)
    else:
        raise ValueError(f"{what}: unknown zone {zone!r}")
    r[0x00:0x00 + len(database)] = database
    r[0x40:0x40 + len(obj)] = obj
    r[0x80:0x80 + len(name)] = name
    struct.pack_into("<3f", r, 0x104, x_field, pos[1], pos[2])
    struct.pack_into("<I", r, 0x200, kind)
    if kind in (KIND_MODEL, KIND_SAFE):
        struct.pack_into("<I", r, 0x204, 4)
    struct.pack_into("<I", r, decode_trn.REC_292 - 4, decode_trn.SENTINEL)
    return bytes(r)


def load_spec(path):
    spec = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(spec.get("objects"), list) or not spec["objects"]:
        raise ValueError("spec needs a non-empty objects list")
    _finite(spec.get("spawn"), 3, "spawn")
    return spec


def build(spec):
    """Spec -> .TRN bytes: u32 count, 540-byte records, no turret links."""
    return struct.pack("<I", len(spec["objects"])) + b"".join(
        record(e, i) for i, e in enumerate(spec["objects"]))


def parse(data):
    """The fields the 2.9.2 reader passes on, for checks and previews."""
    count = struct.unpack_from("<I", data, 0)[0]
    if len(data) != 4 + count * decode_trn.REC_292:
        raise ValueError(f"{count} records need {4 + count * decode_trn.REC_292} bytes, file has {len(data)}")
    out = []
    for i in range(count):
        r = data[4 + i * decode_trn.REC_292:4 + (i + 1) * decode_trn.REC_292]
        if struct.unpack_from("<I", r, decode_trn.REC_292 - 4)[0] != decode_trn.SENTINEL:
            raise ValueError(f"record {i}: missing sentinel")
        out.append({"object": decode_trn.cstr(r[0x40:0x80]), "name": decode_trn.cstr(r[0x80:0x98]),
                    "x_axis": struct.unpack_from("<3f", r, 0x98), "z_axis": struct.unpack_from("<3f", r, 0xA4),
                    "position": struct.unpack_from("<3f", r, 0xC4), "half": struct.unpack_from("<f", r, 0x104)[0],
                    "type": struct.unpack_from("<I", r, 0x194)[0], "kind": struct.unpack_from("<I", r, 0x200)[0]})
    return out


def odb_objects(client_dir):
    """Lower-case object names with a .Sco config in the client's object database."""
    import aoapack
    exe = client_dir / "AOACLIENT.EXE"
    _, _, _, entries = aoapack.read_archive(client_dir / "AOAOBJECTS.ODB", aoapack.builtin_key(exe))
    return {e["name"][:-4].lower() for e in entries if e["name"].lower().endswith(".sco")}


def check_objects(spec, available):
    used = {e.get("object", "Buoy") for e in spec["objects"] if "zone" not in e}
    missing = sorted(o for o in used if o.lower() not in available)
    if missing:
        raise ValueError(f"not in the client's object database: {', '.join(missing)}")


def copy_client(source, target):
    def skip(folder, names):
        return [n for n in names if Path(folder) == source and n in COPY_SKIP]
    shutil.copytree(source, target, ignore=skip)


def install(spec, client, copy_from=None):
    client = client.resolve()
    if client == (ROOT / "game/2.9.2").resolve():
        raise SystemExit(f"{client} is the main client; install into a separate play copy instead")
    if not client.exists():
        if copy_from is None:
            raise SystemExit(f"{client} does not exist; pass --copy-from game/2.9.2 to make the play copy")
        print(f"copying {copy_from} to {client} ...", flush=True)
        copy_client(copy_from.resolve(), client)
    if not (client / "SCRTY.BIN").is_file():
        raise SystemExit(f"{client} is not a client folder (no SCRTY.BIN)")
    try:
        check_objects(spec, odb_objects(client))
    except ImportError as error:  # the archive key lookup needs requirements.txt
        print(f"object names not checked ({error.name} missing); a missing object is skipped by the client")
    data = build(spec)
    (client / SLOT_FILE).write_bytes(data)
    (client / "_custom_map.json").write_text(json.dumps({
        "map": spec["name"], "slot": SLOT_MAP, "file": SLOT_FILE, "records": len(spec["objects"]),
        "sha256": hashlib.sha256(data).hexdigest()}, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {spec['name']} to {client / SLOT_FILE} ({len(data)} bytes, "
          f"sha256 {hashlib.sha256(data).hexdigest()})")


def serve(spec, client, seconds=0):
    trn = client / SLOT_FILE
    if trn.read_bytes() != build(spec):
        raise SystemExit(f"{trn} is not this spec; run install first")
    log = ROOT / "work/custom-map" / f"{spec['name']}.jsonl"
    log.parent.mkdir(parents=True, exist_ok=True)
    command = [sys.executable, "-I", str(ROOT / "tools/station_stub.py"), str(client / "SCRTY.BIN"), str(log),
               "--profile", "local-relay", "--map", SLOT_MAP, "--backdrop", spec.get("backdrop", "spacebkgd3"),
               "--experimental-terrain", "--spawn-at", *map(str, spec["spawn"])]
    if any(e.get("zone") == "powerup" for e in spec["objects"]):
        command += ["--powerup-zones", str(trn)]
    if any("nav" in e for e in spec["objects"]):
        command += ["--map-waypoints", str(trn), "--sustained-delivery"]
    if seconds:
        command += ["--seconds", str(seconds)]
    print(f"Serving {spec['name']} on 127.0.0.1; launch the client in {client} and Play. Ctrl+C stops.")
    sys.exit(subprocess.call(command))


def export_obj(spec, src, out_dir, tex_dir=None):
    """Preview geometry like scene2obj: each model's most detailed mesh, placed
    with the same rows the client reads. Zones are listed, not drawn."""
    import scene2obj
    objects, cache = scene2obj.sco_models(src), {}
    lines, mtl, vbase, placed = [f"# custom map {spec['name']}", f"mtllib {spec['name']}.mtl"], {}, 1, []
    for i, rec in enumerate(parse(build(spec))):
        model = objects.get(rec["object"].lower()) if rec["kind"] == KIND_MODEL else None
        mesh = scene2obj.best_mesh(src, model["gob"], cache) if model else None
        placed.append({"index": i, "object": rec["object"], "name": rec["name"], "kind": rec["kind"],
                       "position": [round(v, 1) for v in rec["position"]], "drawn": bool(mesh),
                       "radius": round(max(math.sqrt(x * x + y * y + z * z) for x, y, z, *_ in mesh["verts"]))
                       if mesh else None})
        if not mesh:
            continue
        x_axis, z_axis = rec["x_axis"], rec["z_axis"]
        y_axis = tuple(z_axis[(k + 1) % 3] * x_axis[(k + 2) % 3] - z_axis[(k + 2) % 3] * x_axis[(k + 1) % 3]
                       for k in range(3))  # z x x, as for any proper rotation
        tex = Path(mesh["texture"]).with_suffix(".png").name if mesh["texture"] else None
        mat = re.sub(r"\W", "_", tex or "untextured")
        mtl[mat] = tex
        lines += [f"o {i:03d}_{re.sub(r'\W', '_', rec['object'])}", f"usemtl {mat}"]
        for x, y, z, *_ in mesh["verts"]:
            w = [x * x_axis[k] + y * y_axis[k] + z * z_axis[k] + rec["position"][k] for k in range(3)]
            lines.append(f"v {w[0]:.3f} {w[1]:.3f} {-w[2]:.3f}")
        lines += [f"vt {u:.6f} {1 - v:.6f}" for _, _, _, u, v, *_ in mesh["verts"]]
        for a, b, c, _ in mesh["faces"]:
            lines.append("f " + " ".join(f"{vbase + k}/{vbase + k}" for k in (a, c, b)))
        vbase += len(mesh["verts"])
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{spec['name']}.obj").write_text("\n".join(lines) + "\n", encoding="utf-8")
    m = []
    for mat, tex in mtl.items():
        m += [f"newmtl {mat}", "Kd 1 1 1"] + ([f"map_Kd {(Path(tex_dir) / tex).as_posix() if tex_dir else tex}"]
                                              if tex else [])
    (out_dir / f"{spec['name']}.mtl").write_text("\n".join(m) + "\n", encoding="utf-8")
    (out_dir / f"{spec['name']}_nodes.json").write_text(json.dumps(placed, indent=1), encoding="utf-8")
    return placed


def clearance(spec, placed):
    """Distance from the spawn to the nearest model's bounding sphere."""
    spawn = spec["spawn"]
    return min((math.dist(spawn, p["position"]) - p["radius"], p["name"], p["object"])
               for p in placed if p["drawn"])


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="action", required=True)
    p = sub.add_parser("build")
    p.add_argument("spec", type=Path)
    p.add_argument("out", type=Path)
    p = sub.add_parser("install")
    p.add_argument("spec", type=Path)
    p.add_argument("client", type=Path)
    p.add_argument("--copy-from", type=Path)
    p = sub.add_parser("serve")
    p.add_argument("spec", type=Path)
    p.add_argument("client", type=Path)
    p.add_argument("--seconds", type=float, default=0)
    p = sub.add_parser("obj")
    p.add_argument("spec", type=Path)
    p.add_argument("src", type=Path, help="exported AOAOBJECTS folder (*.Sco, *.Gob)")
    p.add_argument("out_dir", type=Path)
    p.add_argument("tex_dir", nargs="?")
    args = parser.parse_args()
    spec = load_spec(args.spec)
    if args.action == "build":
        data = build(spec)
        args.out.write_bytes(data)
        print(f"wrote {args.out} ({len(spec['objects'])} records, {len(data)} bytes, "
              f"sha256 {hashlib.sha256(data).hexdigest()})")
    elif args.action == "install":
        install(spec, args.client, args.copy_from)
    elif args.action == "serve":
        serve(spec, args.client, args.seconds)
    else:
        placed = export_obj(spec, args.src, args.out_dir, args.tex_dir)
        gap, name, obj = clearance(spec, placed)
        print(f"{sum(p['drawn'] for p in placed)}/{len(placed)} records drawn; "
              f"spawn clearance {gap:.0f} units (nearest: {obj} {name})")


if __name__ == "__main__":
    main()
