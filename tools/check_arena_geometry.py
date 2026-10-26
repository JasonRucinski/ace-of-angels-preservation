"""Static CTF_arena export check; does not establish in-game collision.

Run after scene2obj.py: python -I tools/check_arena_geometry.py
The OBJ uses negated Z relative to the game's coordinates.
"""
import hashlib
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def inspect_geometry(path):
    vertices, faces, objects = [], [], []
    for line in path.read_text(encoding="utf-8").splitlines():
        fields = line.split()
        if not fields:
            continue
        if fields[0] == "v":
            vertex = tuple(map(float, fields[1:]))
            if len(vertex) != 3 or not all(map(math.isfinite, vertex)):
                raise ValueError("invalid or non-finite vertex")
            vertices.append(vertex)
        elif fields[0] == "f":
            face = tuple(int(field.split("/")[0]) - 1 for field in fields[1:])
            if len(face) != 3:
                raise ValueError("expected exported triangles")
            faces.append(face)
        elif fields[0] == "o":
            objects.append(" ".join(fields[1:]))
    if not vertices or not faces:
        raise ValueError("empty geometry")
    degenerate = 0
    for face in faces:
        if any(index < 0 or index >= len(vertices) for index in face):
            raise ValueError("triangle references a missing vertex")
        a, b, c = (vertices[index] for index in face)
        u, v = [b[i] - a[i] for i in range(3)], [c[i] - a[i] for i in range(3)]
        cross = [u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0]]
        if sum(value * value for value in cross) <= 1e-12:
            degenerate += 1
    return {"sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "vertices": len(vertices), "triangles": len(faces), "objects": len(objects),
            "degenerate_triangles": degenerate,
            "bounds_obj": {"min": [min(v[i] for v in vertices) for i in range(3)],
                           "max": [max(v[i] for v in vertices) for i in range(3)]}}


def main():
    scene = ROOT / "work/2.9.2/scenes"
    nodes_path = scene / "CTF_arena_nodes.json"
    nodes = json.loads(nodes_path.read_text(encoding="utf-8"))
    unresolved = [node for node in nodes if "model" not in node]
    models = ROOT / "work/2.9.2/export/AOAOBJECTS"
    available = {p.stem.casefold() for p in models.glob("*.Gob")}
    missing = sorted({node["model"] for node in nodes if "model" in node
                      and node["model"].casefold() not in available})
    geometry = inspect_geometry(scene / "CTF_arena.obj")
    result = {"map": "CTF_arena", "scope": "static heuristic export only; not original scene loading or collision",
              "geometry": geometry, "nodes_sha256": hashlib.sha256(nodes_path.read_bytes()).hexdigest(),
              "unresolved_nodes": unresolved, "missing_models": missing,
              "release_map_validated": False,
              "remaining": ["resolve node semantics and heuristic model matching",
                            "verify original-client world loading and transforms",
                            "establish collision geometry and continuous high-speed collision",
                            "validate eight spawn points, boundaries and recovery in game"]}
    output = ROOT / "work/ctf-arena-validation.json"
    output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
