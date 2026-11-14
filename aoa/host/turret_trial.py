"""Opt-in, inactive five-turret Arena1a placement trial.

TurretA is the original client's debug-spawn model, a reconstruction choice
for these markers, not a recovered per-marker assignment. No capture or
combat is enabled. LoadObject currently initializes orientation to zero.
"""
import struct

import navigation_buoys
from audit_turret_groups import hierarchy
from turret_groups import status

FIRST_INDEX, COUNT = 80, 5
GROUP = 'Flag ND1-C'


def placements(source):
    # Reuse the full original-asset inventory/hash/order validation.
    navigation_buoys.map_placements(source, 'Arena1a')
    nodes = hierarchy((source / 'Arena1a.Gob').read_bytes())
    parent = next(n for n in nodes if n['name'] == GROUP and n['category'] == 5)
    children = [n for n in nodes if n['category'] == 1 and n['parent_id'] == parent['node_id']]
    if len(children) != COUNT:
        raise ValueError('expected five turrets in Flag ND1-C')
    return children


def loads(nodes):
    if len(nodes) != COUNT:
        raise ValueError('trial requires exactly five verified turret placements')
    result = []
    for index, node in enumerate(nodes, FIRST_INDEX):
        tag = 0x40010000 | index
        packet = bytearray(191)
        for offset, text in ((0, 'TurretA'), (32, 'AoAObjects.odb'), (64, node['name'])):
            raw = text.encode('ascii')
            if len(raw) >= 32 or b'\0' in raw:
                raise ValueError('invalid turret name')
            packet[offset:offset + len(raw)] = raw
        struct.pack_into('<II', packet, 96, tag, 1)
        packet[144:146] = b'\2\2'  # Neutral to all pilots during the trial.
        struct.pack_into('<3f', packet, 146, *node['world_position'])
        result.append((0x25, bytes(packet)))
        # Disable each object before the next is loaded. The neutral load is
        # also essential: LoadObject starts native turret AI enabled.
        result.append(status([tag]))
    return result
