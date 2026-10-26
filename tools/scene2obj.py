"""Rebuild AoA scene-layout .Gob files (arenas, bases, asteroid fields) as one OBJ.

Usage:
    python -I tools/scene2obj.py <AOAOBJECTS export dir> <scene name | all> <out_dir> [texture_dir]

Scene .Gob files hold node records instead of meshes. Per node (offsets from
the end of the node's name string):
    +0x00  f32[6]   bounding box
    +0x4C  f32[3]   position
    +0x58  f32[3]   scale
    +0x64  f32[4]   rotation quaternion
    +0xF8  f32[16]  world matrix, Direct3D row-vector convention
                    (world = [x y z 1] * M); rows 0-2 orthonormal * scale,
                    row 3 = position (checked against +0x4C for every node)
Nodes refer to objects by name: the instance name minus its trailing number
("Astr-C07" -> "Astr-C") is matched case-insensitively against the .Sco
object names (longest prefix wins); the .Sco's fifth string is the .Gob
model, whose most detailed mesh is used. Nodes that resolve to nothing
(waypoints, nav/warp markers, safe zones, dummies) are listed in
<scene>_nodes.json with their positions, as are all resolved instances.
Output is right-handed (Z negated) like tools/gob2obj.py.
"""
import json
import math
import argparse
import re
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gob2obj  # noqa: E402

NODE_MATRIX, NODE_POS = 0xF8, 0x4C


def sco_models(src):
    out = {}
    for p in src.glob("*.[Ss]co"):
        s = [t for _, _, t in gob2obj.strings(p.read_bytes())]
        if len(s) >= 5 and s[4]:
            out[s[0].lower()] = {"object": s[0], "class": s[1], "faction": s[2], "gob": s[4]}
    return out


def best_mesh(src, gob, cache):
    key = gob.lower()
    if key not in cache:
        path = next((p for p in src.glob("*.[Gg]ob") if p.stem.lower() == key), None)
        meshes = gob2obj.parse(path.read_bytes()) if path else []
        cache[key] = max(meshes, key=lambda m: len(m["verts"])) if meshes else None
    return cache[key]


def is_scene(d):
    return not gob2obj.parse(d) and any(t == "Category" for _, _, t in gob2obj.strings(d))


def read_nodes(d):
    """Read layout nodes, including dummy records with nonempty exporter text.

    Category is the u32 immediately after the tagged Category string in the
    same record. Retain offsets/matrices for auditing, not inferred game rules.
    """
    strings = gob2obj.strings(d)
    candidates = []
    for i, (start, after, name) in enumerate(strings[1:], 1):
        if not name or name == "Category" or "\n" in name or after + NODE_MATRIX + 64 > len(d):
            continue
        if i + 1 >= len(strings) or not (strings[i + 1][2] == "" or strings[i + 1][2].startswith("*Type:")):
            continue
        matrix = struct.unpack_from("<16f", d, after + NODE_MATRIX)
        position = struct.unpack_from("<3f", d, after + NODE_POS)
        if not all(map(math.isfinite, matrix + position)) or matrix[15] != 1.0:
            continue
        if any(abs(matrix[12 + k] - position[k]) > 1e-2 * max(1, abs(position[k])) for k in range(3)):
            continue
        candidates.append((i, start, after, name, matrix, position))
    result = []
    for index, (i, start, after, name, matrix, position) in enumerate(candidates):
        end = candidates[index + 1][1] if index + 1 < len(candidates) else len(d)
        categories = [(at, value_at) for at, value_at, text in strings[i + 1:]
                      if after <= at < end and text == "Category" and value_at + 4 <= end]
        if len(categories) != 1:
            raise ValueError(f"{name}: expected exactly one Category within node record")
        category_at, value_at = categories[0]
        result.append({"name": name, "position": list(position), "matrix": list(matrix),
                       "source_offset": start, "category_offset": category_at,
                       "category": struct.unpack_from("<I", d, value_at)[0],
                       "exporter_text": strings[i + 1][2]})
    return result


def compose(child, parent):
    """Direct3D row-vector transform: local point * child * parent."""
    result = [sum(child[r * 4 + k] * parent[k * 4 + c] for k in range(4))
              for r in range(4) for c in range(4)]
    if not all(map(math.isfinite, result)):
        raise ValueError("non-finite nested scene transform")
    return result


def layout_catalog(src):
    """Preserve archive order for the client's first prefix match.

    export_assets records that order in _export.json. Without provenance,
    ambiguous prefixes must remain unresolved rather than depend on glob order.
    """
    paths = {p.name.casefold(): p for p in src.glob('*.[Gg]ob')}
    manifest = src.parent / '_export.json'
    ordered = []
    if manifest.exists():
        for entry in json.loads(manifest.read_text(encoding='utf-8')):
            if entry['archive'].casefold() == src.name.casefold():
                p = paths.get(Path(entry['out']).name.casefold())
                if p is not None and p not in ordered:
                    ordered.append(p)
    proven = len(ordered) == len(paths)
    ordered.extend(p for p in paths.values() if p not in ordered)
    return [p for p in ordered if is_scene(p.read_bytes())], proven


def resolve_layout(token, catalog):
    # 0x4CDD30 calls CString comparison 0x5270C0: case-insensitive,
    # query-length prefix comparison, first database match (not longest).
    paths, ordered = catalog
    matches = [p for p in paths if token and p.stem.casefold().startswith(token.casefold())]
    return matches[0] if matches and (ordered or len(matches) == 1) else None


def expanded_nodes(src, name, expand, ancestors=(), parent=None, path="", _catalog=None, _objects=None):
    if name.casefold() in ancestors or len(ancestors) >= 8:
        raise ValueError("cyclic or excessive nested layout")
    source = next(p for p in src.glob("*.[Gg]ob") if p.stem.casefold() == name.casefold())
    catalog = _catalog if _catalog is not None else layout_catalog(src) if expand else ([], False)
    objects = _objects if _objects is not None else sco_models(src)
    for node in read_nodes(source.read_bytes()):
        node["source_scene"] = source.stem
        node["node_path"] = path + node["name"]
        if parent is not None:
            node["matrix"] = compose(node["matrix"], parent)
            node["position"] = node["matrix"][12:15]
        # Native category 9 tries a named graphics layout after object lookup.
        target = re.sub(r"[0-9]+$", "", node["name"].split()[0])
        object_match = any(o.startswith(target.casefold()) for o in objects) if target else False
        nested = resolve_layout(target, catalog) if expand and node["category"] == 9 and not object_match else None
        if nested:
            node["nested_layout"] = nested.stem
            node["layout_lookup"] = target
        yield node
        if nested:
            yield from expanded_nodes(src, nested.stem, True, ancestors + (name.casefold(),),
                                      node["matrix"], node["node_path"] + "/", catalog, objects)


def export(src, name, out_dir, tex_dir, objects, cache, expand_layouts=False):
    d = next(p for p in src.glob("*.[Gg]ob") if p.stem.lower() == name.lower()).read_bytes()
    nodes, lines, mtl, vbase = [], [f"# AoA scene {name}", f"mtllib {name}.mtl"], {}, 1
    for source_node in expanded_nodes(src, name, expand_layouts):
        t, M, pos = source_node["name"], source_node["matrix"], source_node["position"]
        base = re.sub(r"[\s\-_]*\d+$", "", t).strip().lower()
        obj = max((o for o in objects if base.startswith(o) or o.startswith(base)),
                  key=len, default=None) if base else None
        node = {**source_node, "position": [round(x, 3) for x in pos]}
        mesh = best_mesh(src, objects[obj]["gob"], cache) if obj else None
        if mesh:
            node.update(object=objects[obj]["object"], model=objects[obj]["gob"])
            tex = Path(mesh["texture"]).with_suffix(".png").name if mesh["texture"] else None
            mat = re.sub(r"\W", "_", tex or "untextured")
            mtl[mat] = tex
            lines += [f"o {re.sub(r'\\s', '_', source_node['node_path'])}", f"usemtl {mat}"]
            for x, y, z, u, v, *_ in mesh["verts"]:
                wx = x * M[0] + y * M[4] + z * M[8] + M[12]
                wy = x * M[1] + y * M[5] + z * M[9] + M[13]
                wz = x * M[2] + y * M[6] + z * M[10] + M[14]
                lines.append(f"v {wx:.3f} {wy:.3f} {-wz:.3f}")
            lines += [f"vt {u:.6f} {1 - v:.6f}" for _, _, _, u, v, *_ in mesh["verts"]]
            for a, b, c, _ in mesh["faces"]:
                lines.append("f " + " ".join(f"{vbase + k}/{vbase + k}" for k in (a, c, b)))
            vbase += len(mesh["verts"])
        nodes.append(node)
    (out_dir / f"{name}.obj").write_text("\n".join(lines) + "\n", encoding="utf-8")
    m = []
    for mat, tex in mtl.items():
        m += [f"newmtl {mat}", "Kd 1 1 1"]
        if tex:
            m.append(f"map_Kd {(Path(tex_dir) / tex).as_posix() if tex_dir else tex}")
    (out_dir / f"{name}.mtl").write_text("\n".join(m) + "\n", encoding="utf-8")
    (out_dir / f"{name}_nodes.json").write_text(json.dumps(nodes, indent=1), encoding="utf-8")
    placed = sum(1 for n in nodes if "model" in n)
    return len(nodes), placed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("src", type=Path)
    parser.add_argument("which")
    parser.add_argument("out_dir", type=Path)
    parser.add_argument("tex_dir", nargs="?")
    parser.add_argument("--expand-layouts", action="store_true", help="expand native category-9 nested layouts; preview evidence only")
    args = parser.parse_args()
    src, which, out_dir, tex_dir = args.src, args.which, args.out_dir, args.tex_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    objects, cache = sco_models(src), {}
    names = [p.stem for p in sorted(src.glob("*.[Gg]ob")) if is_scene(p.read_bytes())] if which == "all" else [which]
    for n in names:
        total, placed = export(src, n, out_dir, tex_dir, objects, cache, args.expand_layouts)
        print(f"{n}: {total} nodes, {placed} placed as geometry, {total - placed} markers/unresolved")


if __name__ == "__main__":
    main()
