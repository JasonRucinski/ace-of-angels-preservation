"""Export verified 2.0.0/2.7.1 Gob geometry; shader bindings remain unresolved.

python -I tools/export_legacy_models.py <export/AOAOBJECTS> <output-dir>
Early vertices are 32 bytes (xyz, uv, normal), faces are 36 bytes.
Requires unit normals, valid indices and an exact shader-record boundary.
"""
import json
import math
from pathlib import Path
import struct
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gob2obj


def parse(data):
    meshes = []
    for _, at, name in gob2obj.strings(data):
        if at + 8 > len(data):
            continue
        nv, nf = struct.unpack_from('<II', data, at)
        faces_at = at + 8 + nv * 32
        end = faces_at + nf * 36
        if not (3 <= nv <= 65535 and 1 <= nf <= 65535 and end + 8 <= len(data)):
            continue
        if data[end + 4:end + 8] != gob2obj.TAG:
            continue
        verts = [struct.unpack_from('<8f', data, at + 8 + i * 32) for i in range(nv)]
        if not all(math.isfinite(x) for v in verts for x in v):
            continue
        unit = sum(abs(sum(x*x for x in v[5:8]) ** .5 - 1) < .02 for v in verts)
        if unit < .95 * nv:
            continue
        faces = [(*struct.unpack_from('<3H', data, faces_at + i * 36),
                  struct.unpack_from('<I', data, faces_at + i * 36 + 24)[0]) for i in range(nf)]
        if any(max(f[:3]) >= nv for f in faces):
            continue
        meshes.append({'name': name, 'offset': at, 'end': end,
                       'verts': verts, 'faces': faces, 'texture': None})
    return meshes


def main():
    src, out = map(Path, sys.argv[1:3])
    out.mkdir(parents=True, exist_ok=True)
    report = []
    for path in sorted(src.glob('*.Gob')):
        row = {'file': path.name, 'meshes': []}
        for i, mesh in enumerate(parse(path.read_bytes())):
            stem = f'{path.stem}_{i}'
            gob2obj.write_obj(mesh, stem, out, None)
            row['meshes'].append({'obj': stem + '.obj', 'vertices': len(mesh['verts']),
                                  'faces': len(mesh['faces']), 'offset': mesh['offset'],
                                  'end': mesh['end'], 'material': mesh['name']})
        report.append(row)
    (out / '_legacy_report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(f'{sum(bool(r["meshes"]) for r in report)}/{len(report)} models; '
          f'{sum(len(r["meshes"]) for r in report)} meshes; geometry only')


if __name__ == '__main__':
    main()
