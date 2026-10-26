"""Convert AoA .Gob models (from AoAObjects.odb) to Wavefront OBJ + MTL.

Usage:
    python -I tools/gob2obj.py <model.Gob | dir_of_gobs> <out_dir> [texture_dir]

Format, as recovered from the files (validated per mesh, not assumed):
  strings      b"hWv\\x05" + u32 length + bytes + NUL
  header       b"Gob\\0", ids/flags, model name, bounding box, material
               table (letter string -> texture filename string)
  mesh block   material letter string, then
                 u32 vertex_count, u32 face_count,
                 vertex_count x 64-byte vertex:
                   f32 x,y,z | f32 u,v | 8 bytes (0) | u32 | 12 bytes junk
                   (uninitialised memory from the exporter) | f32 nx,ny,nz |
                   u32 colour (ARGB) | u32
                 face_count x 36-byte face:
                   u16 i0,i1,i2 | u16 flags | 16 bytes (0) | u32 group |
                   f32 x3 (per-face data, not needed for geometry)
               followed by a shader name string ("SimpleTextured") and the
               texture filename used by that mesh.
  Meshes are introduced by "*LOD: n" name strings (1 = most detailed).

A candidate block is accepted only if every index is < vertex_count, at
least 95% of vertex normals are unit length, and the block lies inside the
file. Coordinates are Direct3D left-handed; OBJ is written right-handed by
negating Z, and the face winding is chosen so geometric normals agree with
the stored vertex normals.
"""
import json
import re
import struct
import sys
from pathlib import Path

TAG = b"hWv\x05"


def strings(d):
    out = []
    for m in re.finditer(re.escape(TAG), d):
        n = struct.unpack_from("<I", d, m.end())[0]
        if n < 256 and m.end() + 4 + n < len(d):
            out.append((m.start(), m.end() + 4 + n + 1, d[m.end() + 4:m.end() + 4 + n].decode("latin1")))
    return out


def try_mesh(d, at):
    """Parse counts + records at offset `at`; return mesh dict or None."""
    if at + 8 > len(d):
        return None
    nv, nf = struct.unpack_from("<II", d, at)
    if not (3 <= nv <= 65535 and 1 <= nf <= 65535):
        return None
    vo, fo = at + 8, at + 8 + nv * 64
    end = fo + nf * 36
    if end > len(d):
        return None
    verts, unit = [], 0
    for i in range(nv):
        o = vo + i * 64
        x, y, z, u, v = struct.unpack_from("<5f", d, o)
        nx, ny, nz = struct.unpack_from("<3f", d, o + 44)
        if abs((nx * nx + ny * ny + nz * nz) ** 0.5 - 1) < 0.02:
            unit += 1
        verts.append((x, y, z, u, v, nx, ny, nz))
    if unit < 0.95 * nv:
        return None
    faces = []
    for i in range(nf):
        a, b, c, flags = struct.unpack_from("<4H", d, fo + i * 36)
        if max(a, b, c) >= nv:
            return None
        faces.append((a, b, c, struct.unpack_from("<I", d, fo + i * 36 + 24)[0]))
    return {"offset": at, "end": end, "verts": verts, "faces": faces}


def parse(d):
    strs = strings(d)
    meshes, lod = [], None
    for idx, (start, after, s) in enumerate(strs):
        if s.startswith("*LOD"):
            lod = s
            continue
        m = try_mesh(d, after)
        if not m:
            continue
        tex = next((t for _, a2, t in strs[idx + 1:] if a2 > m["end"] and t.lower().endswith(".tga")), None)
        m.update(name=lod or f"mesh{len(meshes)}", material=s, texture=tex)
        meshes.append(m)
        lod = None
    return meshes


def write_obj(mesh, stem, out_dir, tex_dir):
    v, f = mesh["verts"], mesh["faces"]
    # winding: compare geometric normal (after Z flip) with stored vertex normals
    agree = 0
    for a, b, c, _ in f:
        p = [(v[i][0], v[i][1], -v[i][2]) for i in (a, b, c)]
        e1 = [p[1][k] - p[0][k] for k in range(3)]
        e2 = [p[2][k] - p[0][k] for k in range(3)]
        n = (e1[1] * e2[2] - e1[2] * e2[1], e1[2] * e2[0] - e1[0] * e2[2], e1[0] * e2[1] - e1[1] * e2[0])
        vn = [sum(v[i][5 + k] * (-1 if k == 2 else 1) for i in (a, b, c)) for k in range(3)]
        agree += 1 if sum(n[k] * vn[k] for k in range(3)) > 0 else -1
    flip = agree < 0
    tex_png = Path(mesh["texture"]).with_suffix(".png").name if mesh["texture"] else None
    lines = [f"# {stem} {mesh['name']} - converted from AoA .Gob", f"mtllib {stem}.mtl", f"o {stem}"]
    lines += [f"v {x:.6f} {y:.6f} {-z:.6f}" for x, y, z, *_ in v]
    lines += [f"vt {uu:.6f} {1 - vv:.6f}" for _, _, _, uu, vv, *_ in v]
    lines += [f"vn {nx:.6f} {ny:.6f} {-nz:.6f}" for *_, nx, ny, nz in v]
    lines.append("usemtl skin")
    for a, b, c, _ in f:
        tri = (a, c, b) if flip else (a, b, c)
        lines.append("f " + " ".join(f"{i + 1}/{i + 1}/{i + 1}" for i in tri))
    (out_dir / f"{stem}.obj").write_text("\n".join(lines) + "\n", encoding="utf-8")
    mtl = ["newmtl skin", "Kd 1 1 1", "Ka 0 0 0", "Ks 0 0 0"]
    if tex_png:
        rel = (Path(tex_dir) / tex_png) if tex_dir else Path(tex_png)
        mtl.append(f"map_Kd {rel.as_posix()}")
    (out_dir / f"{stem}.mtl").write_text("\n".join(mtl) + "\n", encoding="utf-8")
    return flip


def main():
    src, out_dir = Path(sys.argv[1]), Path(sys.argv[2])
    tex_dir = sys.argv[3] if len(sys.argv) > 3 else None
    out_dir.mkdir(parents=True, exist_ok=True)
    gobs = sorted(src.glob("*.[Gg]ob")) if src.is_dir() else [src]
    report = []
    for g in gobs:
        d = g.read_bytes()
        meshes = parse(d)
        entry = {"file": g.name, "bytes": len(d), "meshes": []}
        for i, m in enumerate(meshes):
            stem = f"{g.stem}_{re.sub(r'[^A-Za-z0-9]+', '', m['name']) or i}"
            flip = write_obj(m, stem, out_dir, tex_dir)
            entry["meshes"].append({"name": m["name"], "obj": f"{stem}.obj", "vertices": len(m["verts"]),
                                    "faces": len(m["faces"]), "texture": m["texture"],
                                    "offset": hex(m["offset"]), "winding_flipped": flip})
        report.append(entry)
    (out_dir / "_gob_report.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    ok = sum(1 for r in report if r["meshes"])
    print(f"{ok}/{len(report)} .Gob files yielded meshes; "
          f"{sum(len(r['meshes']) for r in report)} meshes written to {out_dir}")
    for r in report:
        if not r["meshes"]:
            print("  no mesh found:", r["file"], r["bytes"])


if __name__ == "__main__":
    main()
