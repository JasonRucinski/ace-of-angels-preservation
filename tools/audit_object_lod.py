"""Audit extracted 2.9.2 object mesh variants without launching the client.

Named *LOD meshes are distinguished from unnamed variants. Matching geometry
does not establish runtime selection thresholds, culling or texture behavior.
"""
import hashlib
import json
import math
import re
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gob2obj


def mesh_record(mesh, node):
    positions = [v[:3] for v in mesh['verts']]
    if not all(math.isfinite(x) for p in positions for x in p):
        raise ValueError('nonfinite mesh vertex')
    matrix = node['matrix']
    transformed = [tuple(sum(p[k]*matrix[k*4+i] for k in range(3))+matrix[12+i] for i in range(3)) for p in positions]
    low = [min(p[i] for p in transformed) for i in range(3)]
    high = [max(p[i] for p in transformed) for i in range(3)]
    geometry = b''.join(struct.pack('<3f', *p) for p in positions)
    geometry += b''.join(struct.pack('<3I', *f[:3]) for f in mesh['faces'])
    return {'label': node['metadata'], 'named_lod': node['metadata'].startswith('*LOD'),
            'node': node['name'], 'node_matrix': matrix, 'screen_size_range': node['screen_size_range'],
            'vertices': len(positions), 'triangles': len(mesh['faces']),
            'geometry_sha256': hashlib.sha256(geometry).hexdigest(),
            'bounds': [low, high], 'center': [(a+b)/2 for a,b in zip(low, high)]}


def mesh_nodes(data):
    """Mesh-node header, distinct from the longer scene-layout node format.

    After name: bounds +0, affine matrix +0x44, size thresholds +0x84,
    tagged metadata +0x8C. Validate framing and matrix before using offsets.
    """
    strings = gob2obj.strings(data)
    result = []
    for (start, after, name), (next_start, _, metadata) in zip(strings, strings[1:]):
        if next_start != after + 0x8C:
            continue
        matrix = list(struct.unpack_from('<16f', data, after + 0x44))
        if not all(map(math.isfinite, matrix)) or matrix[3::4] != [0, 0, 0, 1]:
            raise ValueError(f'{name}: unsupported mesh-node matrix')
        result.append({'start':start,'name':name,'matrix':matrix,'metadata':metadata,
                       'screen_size_range':list(struct.unpack_from('<2f', data, after + 0x84))})
    return result


def audit(source):
    models, layouts = [], []
    for path in sorted(source.glob('*.[Gg]ob')):
        data = path.read_bytes()
        parsed = gob2obj.parse(data)
        nodes = mesh_nodes(data) if parsed else []
        meshes = [mesh_record(m, max((n for n in nodes if n['start'] < m['offset']), key=lambda n:n['start'])) for m in parsed]
        if not meshes:
            layouts.append(path.name)
            continue
        levels = {}
        for m in meshes:
            if m['named_lod']:
                for level in re.findall(r'\d+', m['label'].split(':',1)[1]):
                    levels.setdefault(level, []).append(m)
        named = []
        for level, parts in sorted(levels.items()):
            low = [min(p['bounds'][0][i] for p in parts) for i in range(3)]
            high = [max(p['bounds'][1][i] for p in parts) for i in range(3)]
            named.append({'level':level,'parts':len(parts),'bounds':[low,high], 'center':[(a+b)/2 for a,b in zip(low,high)]})
        record = {'model': path.stem, 'source_sha256': hashlib.sha256(data).hexdigest(), 'meshes': meshes}
        record['lod_levels'] = named
        if len(named) > 1:
            origin = named[0]
            diagonal = math.dist(*origin['bounds'])
            record['named_lod_max_center_shift_units'] = max(math.dist(origin['center'],m['center']) for m in named[1:])
            record['named_lod_max_center_shift_fraction_of_diagonal'] = record['named_lod_max_center_shift_units']/diagonal if diagonal else None
        models.append(record)
    asteroids = [m for m in models if m['model'].lower().startswith('astr')]
    for m in asteroids:
        m['all_mesh_geometry_identical'] = len({v['geometry_sha256'] for v in m['meshes']}) == 1
    return {'scope': 'asset geometry with serialized mesh-node transforms; no scene-parent transforms, runtime LOD selection, culling or GPU rendering',
            'mesh_models': len(models), 'unparsed_or_layout_models': layouts,
            'asteroid_models': [m['model'] for m in asteroids], 'models': models}


if __name__ == '__main__':
    root = Path(__file__).resolve().parents[1]
    result = audit(root / 'work/2.9.2/export/AOAOBJECTS')
    output = Path(sys.argv[1])
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps({'mesh_models': result['mesh_models'],
                      'asteroids': [{k:m[k] for k in ('model','all_mesh_geometry_identical')} for m in result['models'] if m['model'] in result['asteroid_models']],
                      'named_lod_largest_center_shifts': sorted(
                          [{'model':m['model'],'fraction':m['named_lod_max_center_shift_fraction_of_diagonal']} for m in result['models'] if 'named_lod_max_center_shift_fraction_of_diagonal' in m],
                          key=lambda m:m['fraction'], reverse=True)[:8]}, indent=2))
