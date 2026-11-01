"""Add a new placeable object to a play copy's object database from a glTF model.

  python -I tools/make_object.py install config/objects/bennu.json MODEL.glb work/custom-map/client
  python -I tools/make_object.py preview config/objects/bennu.json MODEL.glb OUT_DIR
  python -I tools/make_object.py undo work/custom-map/client

The object spec names the model source and its SHA-256, the new object and
model names, the target radius in world units, the texture tile size and an
existing texture from TEXTURES.AOA, so no new texture entry is needed.

`install` writes a single-mesh .Gob and a .Sco cloned from the template object
(Astr-C: one textured mesh, asteroid systems) and appends both to the play
copy's AOAOBJECTS.ODB with aoapack.rebuild. The first install keeps the
copy's database as AOAOBJECTS.ODB.before-custom-objects. Later installs keep
the objects already added and replace this spec's own entries, so it can be
repeated; `undo` restores the backup, removing every added object. The main
game/2.9.2 folder is refused. Place the object with tools/make_map.py by its
object name.

.Gob layout as the asteroid template has it (tools/gob2obj.py for the mesh):
  +0x0C u32 162 + model-name length; tagged model name; f32[6] model box
  (min, max); material table with the texture name; a tagged node name, the
  node's f32[6] box in mesh space, and its local matrix with the translation
  at node +0x74; the mesh block (u32 vertex and face counts, 64-byte
  vertices, 36-byte faces); the shader block naming the texture again.
  Vertex: f32 x, y, z, u, v; zeros; f32 normal at +44; u32 colour
  0xFFFFFFFF at +56; u32 2 at +60. Face: u16 a, b, c; u16 edge flags 0x57;
  u32 2 at +20; f32 edge lengths |ab|, |bc|, |ca| at +24 (checked against
  every Astr-C face). The outward side is cross(b - a, c - a), Direct3D's
  left-handed coordinates: glTF z is negated.
Texture coordinates are a triplanar projection: each triangle takes the
plane of its dominant normal axis, at one texture repeat per `tile` units.
"""
import argparse
import hashlib
import json
import math
import shutil
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gob2obj  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
TAG = gob2obj.TAG
BACKUP = ".before-custom-objects"
TEMPLATE = "Astr-C"
TEMPLATE_GOB, TEMPLATE_SCO = "Astr-C.Gob", "Astr-C.Sco"
TEMPLATE_TEXTURE, TEMPLATE_NODE, TEMPLATE_SCO_GOB = "astr3.tga", "asteroid", "Astr-C_mip"
NODE_TRANSLATION = 0x74
FACE_FLAGS, FACE_GROUP, VERTEX_TAIL = 0x57, 2, 2


def read_glb(data):
    """Positions, normals (or None) and triangles of every mesh primitive."""
    magic, _, length = struct.unpack_from("<4sII", data)
    if magic != b"glTF" or length != len(data):
        raise ValueError("not a binary glTF file")
    n, kind = struct.unpack_from("<I4s", data, 12)
    if kind != b"JSON":
        raise ValueError("first glTF chunk is not JSON")
    gltf = json.loads(data[20:20 + n])
    at = 20 + n
    bn, bkind = struct.unpack_from("<I4s", data, at)
    if bkind != b"BIN\0":
        raise ValueError("no binary chunk")
    blob = data[at + 8:at + 8 + bn]
    sizes = {5126: ("f", 4), 5125: ("I", 4), 5123: ("H", 2), 5121: ("B", 1)}
    widths = {"SCALAR": 1, "VEC3": 3}

    def accessor(i):
        a = gltf["accessors"][i]
        view = gltf["bufferViews"][a["bufferView"]]
        code, size = sizes[a["componentType"]]
        width = widths[a["type"]]
        stride = view.get("byteStride", size * width)
        base = view.get("byteOffset", 0) + a.get("byteOffset", 0)
        return [struct.unpack_from("<" + code * width, blob, base + k * stride) for k in range(a["count"])]

    positions, normals, triangles = [], [], []
    for mesh in gltf["meshes"]:
        for prim in mesh["primitives"]:
            if prim.get("mode", 4) != 4:
                raise ValueError("only triangle lists are supported")
            base = len(positions)
            pos = accessor(prim["attributes"]["POSITION"])
            positions += pos
            normals += accessor(prim["attributes"]["NORMAL"]) if "NORMAL" in prim["attributes"] else [None] * len(pos)
            idx = [i[0] for i in accessor(prim["indices"])] if "indices" in prim else list(range(len(pos)))
            triangles += [(base + idx[k], base + idx[k + 1], base + idx[k + 2]) for k in range(0, len(idx) - 2, 3)]
    return positions, (None if any(v is None for v in normals) else normals), triangles


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _unit(a):
    n = math.sqrt(_dot(a, a))
    return (a[0] / n, a[1] / n, a[2] / n) if n else (0.0, 1.0, 0.0)


def prepare(positions, triangles, radius):
    """Game coordinates (glTF z negated), centred on the box, scaled to `radius`,
    degenerate triangles dropped and all wound outward.

    The winding comes from the closed mesh's signed volume, not from the
    file's normals (the NASA Bennu file's point inward); vertex normals are
    then the area-weighted face normals."""
    pos = [(x, y, -z) for x, y, z in positions]
    lo = [min(p[k] for p in pos) for k in range(3)]
    hi = [max(p[k] for p in pos) for k in range(3)]
    centre = [(lo[k] + hi[k]) / 2 for k in range(3)]
    scale = radius / max(math.dist(p, centre) for p in pos)
    pos = [tuple((p[k] - centre[k]) * scale for k in range(3)) for p in pos]
    tris = [t for t in triangles if _dot(*(2 * [_cross(_sub(pos[t[1]], pos[t[0]]), _sub(pos[t[2]], pos[t[0]]))])) > 0]
    volume = sum(_dot(pos[a], _cross(pos[b], pos[c])) for a, b, c in tris) / 6
    flipped = volume < 0
    if flipped:
        tris = [(a, c, b) for a, b, c in tris]
    acc = [[0.0, 0.0, 0.0] for _ in pos]
    for a, b, c in tris:
        n = _cross(_sub(pos[b], pos[a]), _sub(pos[c], pos[a]))
        for i in (a, b, c):
            for k in range(3):
                acc[i][k] += n[k]
    return pos, [_unit(n) for n in acc], tris, flipped


def triplanar(pos, nrm, tris, tile):
    """Split vertices per projection plane; (x, y, z, u, v, nx, ny, nz) + faces."""
    planes = ((2, 1), (0, 2), (0, 1))  # dominant x: (z, y); y: (x, z); z: (x, y)
    verts, index, faces = [], {}, []
    for a, b, c in tris:
        n = _cross(_sub(pos[b], pos[a]), _sub(pos[c], pos[a]))
        axis = max(range(3), key=lambda k: abs(n[k]))
        face = []
        for i in (a, b, c):
            key = (i, axis)
            if key not in index:
                s, t = planes[axis]
                index[key] = len(verts)
                verts.append((*pos[i], pos[i][s] / tile, pos[i][t] / tile, *nrm[i]))
            face.append(index[key])
        faces.append(tuple(face))
    if len(verts) > 0xFFFF:
        raise ValueError(f"{len(verts)} vertices exceed 16-bit face indices")
    return verts, faces


def mesh_block(verts, faces):
    out = bytearray(struct.pack("<II", len(verts), len(faces)))
    for x, y, z, u, v, nx, ny, nz in verts:
        r = bytearray(64)
        struct.pack_into("<5f", r, 0, x, y, z, u, v)
        struct.pack_into("<3fII", r, 44, nx, ny, nz, 0xFFFFFFFF, VERTEX_TAIL)
        out += r
    for a, b, c in faces:
        r = bytearray(36)
        struct.pack_into("<4H", r, 0, a, b, c, FACE_FLAGS)
        struct.pack_into("<I3f", r, 20, FACE_GROUP, math.dist(verts[a][:3], verts[b][:3]),
                         math.dist(verts[b][:3], verts[c][:3]), math.dist(verts[c][:3], verts[a][:3]))
        out += r
    return bytes(out)


def tagged(text):
    raw = text.encode("latin1")
    return TAG + struct.pack("<I", len(raw)) + raw + b"\0"


def _strings(data, text):
    return [(start, after) for start, after, s in gob2obj.strings(data) if s == text]


def write_gob(template, model, texture, verts, faces):
    """Template Gob with a new name, boxes, node translation, mesh and texture."""
    meshes = gob2obj.parse(template)
    if len(meshes) != 1:
        raise ValueError("template must hold exactly one mesh")
    mesh = meshes[0]
    (name_start, name_after), = [(s, a) for s, a, t in gob2obj.strings(template)[:1]]
    (node_start, node_after), = _strings(template, TEMPLATE_NODE)
    textures = _strings(template, TEMPLATE_TEXTURE)
    if len(textures) != 2 or not (textures[0][1] < node_start < mesh["offset"] < textures[1][0]):
        raise ValueError("unexpected template layout")
    lo = [min(v[k] for v in verts) for k in range(3)]
    hi = [max(v[k] for v in verts) for k in range(3)]
    box = struct.pack("<6f", *lo, *hi)
    node = bytearray(template[node_after:mesh["offset"]])
    node[0:24] = box
    node[NODE_TRANSLATION:NODE_TRANSLATION + 12] = bytes(12)
    head = bytearray(template[:name_start])
    struct.pack_into("<I", head, 0x0C, 162 + len(model.encode("latin1")))
    out = (bytes(head) + tagged(model) + box + template[name_after + 24:textures[0][0]] + tagged(texture)
           + template[textures[0][1]:node_after] + bytes(node) + mesh_block(verts, faces)
           + template[mesh["end"]:textures[1][0]] + tagged(texture) + template[textures[1][1]:])
    check = gob2obj.parse(out)
    if len(check) != 1 or len(check[0]["verts"]) != len(verts) or len(check[0]["faces"]) != len(faces) \
            or check[0]["texture"] != texture:
        raise ValueError("written Gob does not parse back")
    return out


def write_sco(template, obj, model):
    (o_start, o_after), = _strings(template, TEMPLATE)
    (g_start, g_after), = _strings(template, TEMPLATE_SCO_GOB)
    out = template[:o_start] + tagged(obj) + template[o_after:g_start] + tagged(model) + template[g_after:]
    s = [t for _, _, t in gob2obj.strings(out)]
    if s[0] != obj or s[4] != model:
        raise ValueError("written Sco does not parse back")
    return out


def load_spec(path):
    spec = json.loads(Path(path).read_text(encoding="utf-8"))
    for key in ("object", "model", "texture", "radius", "tile"):
        if key not in spec:
            raise ValueError(f"object spec needs {key!r}")
    for key in ("object", "model"):
        value = spec[key]
        if not (isinstance(value, str) and 0 < len(value) <= 23 and value.isascii()
                and value.replace("_", "").replace("-", "").isalnum()):
            raise ValueError(f"{key} must be 1..23 letters, digits, '-' or '_'")
    for key in ("radius", "tile"):
        if not (isinstance(spec[key], (int, float)) and math.isfinite(spec[key]) and spec[key] > 0):
            raise ValueError(f"{key} must be a positive number")
    return spec


def build(spec, glb, templates):
    data = Path(glb).read_bytes()
    want = spec.get("source", {}).get("sha256")
    if want and hashlib.sha256(data).hexdigest() != want:
        raise SystemExit(f"{glb}: SHA-256 differs from the spec's source")
    positions, _, triangles = read_glb(data)
    pos, nrm, tris, flipped = prepare(positions, triangles, float(spec["radius"]))
    verts, faces = triplanar(pos, nrm, tris, float(spec["tile"]))
    gob = write_gob(templates[TEMPLATE_GOB], spec["model"], spec["texture"], verts, faces)
    sco = write_sco(templates[TEMPLATE_SCO], spec["object"], spec["model"])
    return {f"{spec['object']}.Sco": sco, f"{spec['model']}.Gob": gob}, {
        "vertices": len(verts), "faces": len(faces), "flipped": flipped,
        "radius": round(max(math.sqrt(v[0] ** 2 + v[1] ** 2 + v[2] ** 2) for v in verts))}


def _archive(client):
    import aoapack
    return aoapack, aoapack.builtin_key(client / "AOACLIENT.EXE")


def templates_from(odb, aoapack, key0):
    d, key, _, entries = aoapack.read_archive(odb, key0)
    found = {e["name"]: aoapack.entry_bytes(d, key, key0, e)[0] for e in entries
             if e["name"] in (TEMPLATE_GOB, TEMPLATE_SCO)}
    if len(found) != 2:
        raise SystemExit(f"{odb}: template {TEMPLATE} not found")
    return found


def _play_copy(client):
    client = Path(client).resolve()
    if client == (ROOT / "game/2.9.2").resolve():
        raise SystemExit(f"{client} is the main client; use a play copy (tools/make_map.py install --copy-from)")
    if not (client / "AOAOBJECTS.ODB").is_file():
        raise SystemExit(f"{client}: no AOAOBJECTS.ODB")
    return client


def split_entries(entries, original, current):
    """(replacements, additions): an earlier install's entries for this spec
    are replaced, other new names are added. original and current are the
    lower-case entry names of the backup and the installed database."""
    taken = sorted(n for n in entries if n.lower() in original)
    if taken:
        raise SystemExit(f"{', '.join(taken)} already in the original database; choose new names")
    replace = {n: d for n, d in entries.items() if n.lower() in current}
    return replace, {n: d for n, d in entries.items() if n not in replace}


def install(spec, glb, client):
    client = _play_copy(client)
    odb, backup = client / "AOAOBJECTS.ODB", client / ("AOAOBJECTS.ODB" + BACKUP)
    if not backup.exists():
        shutil.copy2(odb, backup)
    aoapack, key0 = _archive(client)
    entries, stats = build(spec, glb, templates_from(backup, aoapack, key0))
    # Rebuild the installed database, not the backup, so objects added by
    # other specs stay.
    names = [{e["name"].lower() for e in aoapack.read_archive(p, key0)[3]} for p in (backup, odb)]
    out = aoapack.rebuild(odb, key0, *split_entries(entries, *names))
    odb.write_bytes(out)
    print(f"added {', '.join(entries)} to {odb} ({stats['vertices']} vertices, {stats['faces']} faces, "
          f"radius {stats['radius']}; sha256 {hashlib.sha256(out).hexdigest()})")
    return stats


def undo(client):
    client = _play_copy(client)
    backup = client / ("AOAOBJECTS.ODB" + BACKUP)
    if not backup.exists():
        raise SystemExit("no custom objects installed")
    shutil.move(backup, client / "AOAOBJECTS.ODB")
    print(f"restored {client / 'AOAOBJECTS.ODB'}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="action", required=True)
    p = sub.add_parser("install")
    p.add_argument("spec", type=Path)
    p.add_argument("glb", type=Path)
    p.add_argument("client", type=Path)
    p = sub.add_parser("preview")
    p.add_argument("spec", type=Path)
    p.add_argument("glb", type=Path)
    p.add_argument("out_dir", type=Path)
    p.add_argument("--client", type=Path, default=ROOT / "game/2.9.2", help="client whose database holds the template")
    p = sub.add_parser("undo")
    p.add_argument("client", type=Path)
    args = parser.parse_args()
    if args.action == "undo":
        undo(args.client)
    elif args.action == "install":
        install(load_spec(args.spec), args.glb, args.client)
    else:
        aoapack, key0 = _archive(args.client)
        entries, stats = build(load_spec(args.spec), args.glb, templates_from(args.client / "AOAOBJECTS.ODB", aoapack, key0))
        args.out_dir.mkdir(parents=True, exist_ok=True)
        for name, data in entries.items():
            (args.out_dir / name).write_bytes(data)
        print(f"wrote {', '.join(entries)} to {args.out_dir}: {stats}")


if __name__ == "__main__":
    main()
