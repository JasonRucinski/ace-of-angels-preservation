"""Opt-in single Arena1a gate using the recovered native model/destination.

The original client handles local transit for kind 7. This trial does not add
host-authorized transit or restore editor orientation.
"""
import struct

import navigation_buoys
from audit_turret_groups import hierarchy
from audit_warp_gates import routes

INDEX = 85
TAG = 0x40010000 | INDEX
GATE = 'Rail_Hy1 HyBase1_Rail'


def placement(source):
    navigation_buoys.map_placements(source, 'Arena1a')
    nodes = hierarchy((source / 'Arena1a.Gob').read_bytes())
    return next(link for link in routes(nodes) if link['name'] == GATE)


def loads(gate):
    if gate['name'] != GATE or gate['destination_node'] != 'WarpTgt01':
        raise ValueError('warp trial requires the verified first Arena1a gate')
    packet = bytearray(191)
    # Native layout labels gates using the token after the first space.
    for offset, text in ((0, 'WarpGate'), (32, 'AoAObjects.odb'), (64, 'HyBase1_Rail')):
        raw = text.encode('ascii')
        packet[offset:offset + len(raw)] = raw
    struct.pack_into('<II', packet, 96, TAG, 7)
    packet[144:146] = b'\2\2'
    struct.pack_into('<3f', packet, 146, *gate['position'])
    struct.pack_into('<3f', packet, 158, *gate['destination'])
    return [(0x25, bytes(packet))]
