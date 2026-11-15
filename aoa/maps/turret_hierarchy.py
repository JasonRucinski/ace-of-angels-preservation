"""Decode the Arena1a node hierarchy (parent links and world transforms).

Used by the opt-in turret and warp-gate trials of the host
(aoa/host/turret_trial.py, aoa/host/warp_trial.py). The audit that checks
these transforms in original client code is
archive/analysis/audit_turret_groups.py.
"""
import hashlib
import struct

from aoa.formats import gob
from aoa.formats import scene
from aoa.maps.navigation import ARENA1A_SHA256


def hierarchy(data):
    if hashlib.sha256(data).hexdigest() != ARENA1A_SHA256:
        raise ValueError('requires the original Arena1a.Gob')
    nodes = scene.read_nodes(data)
    ends = {start: end for start, end, _ in gob.strings(data)}
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
            matrix = scene.compose(matrix, resolve(by_id[parent], visiting | {node['node_id']}))
        node['world_matrix'] = matrix
        node['world_position'] = matrix[12:15]
        return matrix

    for node in nodes:
        resolve(node, set())
    return nodes
