"""Server-owned navigation placements from the user's original maps.

LoadObject uses native Buoy / kind 3, neutral relations, stable object slots
90..99. The receiver initializes orientation to zero; this first restoration
preserves names and positions, not the editor's rotations. No asset data is
embedded here. Callers must use ordered reliable delivery after flight entry.
"""
import hashlib
import json
import struct
from pathlib import Path

import scene2obj
import decode_trn
import online_terrain
import aoapack

ARENA1A_SHA256 = '5d652eaca4972d958eb1dc54b8ef277fdb8ea475be4912f01a5fd8d02afa7886'
FIRST_INDEX, COUNT = 90, 10
ROOT = Path(__file__).resolve().parents[1]
JRMAP_SHA256 = 'e3da8fbbdfb84ac7c830314e62bd8ceb7dfbdf9d90cd5fef614601133f23c5c4'


def map_placements(source, name, trn=None):
    """Expand original nested layouts; preserve JRMAP's original kind-3 model.

    Validate the archive's Gobs and recorded order before prefix resolution.
    Maps with no navigation records intentionally produce no objects.
    """
    if name not in online_terrain.MAP_NAMES:
        raise ValueError('unsupported navigation map')
    if name == 'JRMAP':
        if trn is None or hashlib.sha256(trn.read_bytes()).hexdigest() != JRMAP_SHA256:
            raise ValueError('JRMAP navigation requires the original JRMAP.TRN')
        data = trn.read_bytes()
        nodes = [dict(r, model_object=r['object'], position=list(struct.unpack_from('<3f', data, 4 + r['index'] * decode_trn.REC + 0xC0)))
                 for r in decode_trn.decode(data)['records'] if r['kind'] == 3]
        if any(n['model_object'] not in ('Buoy', 'Cube') for n in nodes):
            raise ValueError('unexpected JRMAP navigation object')
    else:
        archives = json.loads((ROOT / 'evidence/2.9.2/archives.json').read_text())
        archive = next(a for a in archives if a['archive'].upper().endswith('AOAOBJECTS.ODB'))
        expected = [e for e in archive['entries'] if e['name'].lower().endswith(('.gob', '.sco'))]
        files = {p.name.casefold(): p for p in source.iterdir() if p.suffix.casefold() in ('.gob', '.sco')}
        export_name = lambda e: aoapack.safe_name(e['index'], e['name']).split('_', 1)[1].casefold()
        if set(files) != {export_name(e) for e in expected}:
            raise ValueError('exported model/configuration inventory differs from original archive')
        for entry in expected:
            path = files.get(export_name(entry))
            if path is None or hashlib.sha256(path.read_bytes()).hexdigest() != entry['sha256']:
                raise ValueError(f"missing or modified original graphics asset: {entry['name']}")
        exported = json.loads((source.parent / '_export.json').read_text())
        order = [Path(e['out']).name.casefold() for e in exported
                 if e['archive'].casefold() == source.name.casefold() and e['out'].lower().endswith('.gob')]
        if order != [export_name(e) for e in expected if e['name'].lower().endswith('.gob')]:
            raise ValueError('exported graphics order differs from original archive')
        path = files[name.casefold() + '.gob']
        nodes = ([dict(n, model_object='Buoy') for n in scene2obj.expanded_nodes(source, name, True)
                  if n['category'] == 4] if scene2obj.is_scene(path.read_bytes()) else [])
    if len(nodes) > COUNT:
        raise ValueError('navigation records exceed reserved slots 90..99')
    # Repeated nested labels are valid: stable tags distinguish them.
    return nodes


def trn_placements(data):
    """Kind-3 waypoints of a 2.9.2 terrain file written by tools/make_map.py.

    The 2.9.2 client gates kind 3 off in AddTerrainObject, so the server
    sends them like the original maps' buoys.
    """
    count = struct.unpack_from('<I', data, 0)[0]
    if len(data) < 4 + count * decode_trn.REC_292:
        raise ValueError('truncated 2.9.2 terrain file')
    nodes = []
    for i in range(count):
        r = data[4 + i * decode_trn.REC_292:4 + (i + 1) * decode_trn.REC_292]
        if struct.unpack_from('<I', r, decode_trn.REC_292 - 4)[0] != decode_trn.SENTINEL:
            raise ValueError(f'record {i}: missing sentinel')
        if struct.unpack_from('<I', r, 0x200)[0] == 3:
            nodes.append({'name': decode_trn.cstr(r[0x80:0x98]), 'model_object': decode_trn.cstr(r[0x40:0x80]),
                          'position': list(struct.unpack_from('<3f', r, 0xC4))})
    if len(nodes) > COUNT:
        raise ValueError('navigation records exceed reserved slots 90..99')
    return nodes


def placements(source):
    data = source.read_bytes()
    if hashlib.sha256(data).hexdigest() != ARENA1A_SHA256:
        raise ValueError('navigation buoys require the original 2.9.2 Arena1a.Gob')
    nodes = [n for n in scene2obj.read_nodes(data) if n['category'] == 4]
    if len(nodes) != COUNT or len({n['name'] for n in nodes}) != COUNT:
        raise ValueError('expected ten unique Arena1a navigation records')
    return nodes


def loads(nodes):
    result = []
    for index, node in enumerate(nodes, FIRST_INDEX):
        packet = bytearray(0xBF)
        for offset, value in ((0, node.get('model_object', 'Buoy')), (0x20, 'AoAObjects.odb'), (0x40, node['name'])):
            encoded = value.encode('ascii')
            if len(encoded) >= 32:
                raise ValueError('navigation name exceeds LoadObject field')
            packet[offset:offset + len(encoded)] = encoded
        struct.pack_into('<II', packet, 0x60, 0x40010000 | index, 3)
        packet[0x90] = packet[0x91] = 2  # Neutral, matching native kind-3 creation.
        struct.pack_into('<3f', packet, 0x92, *node['position'])
        result.append((0x25, bytes(packet)))
    return result
