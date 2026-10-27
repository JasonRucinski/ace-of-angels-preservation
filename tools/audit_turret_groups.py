"""Recover Arena1a turret hierarchy and verify transforms in original x86 code.

Read-only research: no host packets or client patches. Coordinates are written
only to an optional local report, not the committed count-only evidence.
"""
import argparse
import collections
import hashlib
import json
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gob2obj
import scene2obj
from navigation_buoys import ARENA1A_SHA256
from patch_client import PRISTINE_292

ROOT = Path(__file__).resolve().parents[1]


def hierarchy(data):
    if hashlib.sha256(data).hexdigest() != ARENA1A_SHA256:
        raise ValueError('requires the original Arena1a.Gob')
    nodes = scene2obj.read_nodes(data)
    ends = {start: end for start, end, _ in gob2obj.strings(data)}
    for node in nodes:
        at = ends[node['source_offset']]
        if struct.unpack_from('<II', data, at + 0x18) != (0x8237, 0x10003):
            raise ValueError('unsupported animation record')
        if struct.unpack_from('<I', data, at + 0x3c)[0] != 1:
            raise ValueError('expected one animation key')
        node['parent_id'] = struct.unpack_from('<I', data, at + 0x24)[0]
        node['node_id'] = struct.unpack_from('<I', data, at + 0xf4)[0]
    by_id = {n['node_id']: n for n in nodes}
    if len(by_id) != len(nodes):
        raise ValueError('duplicate node IDs')

    def resolve(node, visiting):
        if node['node_id'] in visiting:
            raise ValueError('cyclic parent links')
        if 'world_matrix' in node:
            return node['world_matrix']
        parent = node['parent_id']
        matrix = node['matrix']
        if parent != 0xffff:
            if parent not in by_id:
                raise ValueError('missing parent')
            matrix = scene2obj.compose(matrix, resolve(by_id[parent], visiting | {node['node_id']}))
        node['world_matrix'] = matrix
        node['world_position'] = matrix[12:15]
        return matrix

    for node in nodes:
        resolve(node, set())
    return nodes


def native_checks(client, nodes):
    if hashlib.sha256(client.read_bytes()).hexdigest() != PRISTINE_292:
        raise ValueError('requires the original 2.9.2 executable')
    from emulate_codec import Emu, HEAP, SCRATCH
    from pe_util import PE
    emu = Emu(PE(client))
    # Original animation writer: parent pointer +0x18 serializes its ID +8;
    # own ID +8 follows the animation-key array. No hooks or game calls needed.
    obj, parent, stream, output = HEAP, HEAP + 0x1000, HEAP + 0x2000, SCRATCH
    emu.write(obj + 8, struct.pack('<I', 120))
    emu.write(obj + 0x18, struct.pack('<I', parent))
    emu.write(parent + 8, struct.pack('<I', 119))
    emu.write(stream + 4, struct.pack('<I', output))
    emu.thiscall(0x5490c0, obj, stream)
    assert struct.unpack('<I', emu.read(output + 0xc, 4))[0] == 119
    assert struct.unpack('<I', emu.read(output + 0x28, 4))[0] == 120
    # Use the native recursive world-transform routine, including its original
    # multiplication implementation, on every decoded node. No stubs involved.
    addresses = {n['node_id']: HEAP + 0x10000 + i * 0x400 for i, n in enumerate(nodes)}
    for node in nodes:
        address = addresses[node['node_id']]
        emu.write(address + 0x7c, struct.pack('<16f', *node['matrix']))
        emu.write(address + 0x144, struct.pack('<I', addresses.get(node['parent_id'], 0)))
    errors = []
    for node in nodes:
        address = addresses[node['node_id']]
        result = emu.thiscall(0x542c80, address)
        assert result == address + 0x1a8
        matrix = struct.unpack('<16f', emu.read(result, 64))
        error = max(abs(a-b) for a, b in zip(matrix, node['world_matrix']))
        assert error < .1, (node['name'], error)
        errors.append(error)
    # Dispatch proof: packet kind 1 enters the turret-AI allocation branch.
    pe = emu.pe
    selector = pe.read_va(0x4a6d80, 1)[0]
    assert pe.u32(0x4a6d64 + 4 * selector) == 0x4a69dc
    return {'parent_id_writer': 'passed', 'native_world_transforms': len(nodes),
            'maximum_matrix_error': max(errors), 'load_object_turret_kind': 1}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--local-report', type=Path)
    args = parser.parse_args()
    nodes = hierarchy((ROOT / 'work/2.9.2/export/AOAOBJECTS/Arena1a.Gob').read_bytes())
    by_id = {n['node_id']: n for n in nodes}
    turrets = [n for n in nodes if n['category'] == 1]
    flags = [n for n in nodes if n['category'] == 5]
    assert len(turrets) == 80 and len(flags) == 18
    assert all(by_id[n['parent_id']]['category'] == 5 for n in turrets)
    groups = [{'flag': flag['name'], 'parent': by_id[flag['parent_id']]['name'],
               'turrets': [n['name'] for n in turrets if n['parent_id'] == flag['node_id']]}
              for flag in flags]
    report = {'scope': 'Hierarchy and native transform verification; no objects spawned',
              'client_sha256': PRISTINE_292, 'map_sha256': ARENA1A_SHA256,
              'turrets': len(turrets), 'groups': groups,
              'group_size_histogram': dict(collections.Counter(len(g['turrets']) for g in groups)),
              'native_checks': native_checks(ROOT / 'game/2.9.2/AOACLIENT.EXE.orig', nodes),
              'remaining': ['Per-marker model choice', 'Initial ownership and capture rules',
                            'Orientation delivery', 'Single-authority aiming/firing and damage',
                            'Live visual and multiplayer acceptance']}
    if args.local_report:
        args.local_report.parent.mkdir(parents=True, exist_ok=True)
        args.local_report.write_text(json.dumps({'summary': report, 'nodes': nodes}, indent=2) + '\n')
    path = ROOT / 'evidence/2.9.2/turret_groups_20261026.json'
    path.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
