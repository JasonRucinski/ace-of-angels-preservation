"""Opt-in Arena1a gates using recovered native models and destinations.

The original client handles local transit for kind 7. This trial does not add
host-authorized transit or restore editor orientation.
"""
import struct

import navigation_buoys
from audit_turret_groups import hierarchy
from audit_warp_gates import routes

FIRST_INDEX, COUNT = 71, 9
INDEX = FIRST_INDEX  # First-gate diagnostic compatibility.
TAG = 0x40010000 | INDEX
GATE = 'Rail_Hy1 HyBase1_Rail'
ROUTES = (
    (GATE, 'WarpTgt01'),
    ('Rail_Hy2 HyBase2_Rail', 'WarpTgt02'),
    ('Rail_Home1 Home_Rail', 'WarpTgt03'),
    ('Rail_Home2 Home_Rail', 'WarpTgt04'),
    ('Rail_Hy_k1 Rail_Hy1a', 'Dummy04'),
    ('Rail_Hy_J1 Rail_SSa', 'Dummy01'),
    ('Rail_Hy_J2 Rail_SSb', 'Dummy02'),
    ('Rail_Hy_J3 RailSSc', 'Dummy03'),
    ('Rail_Hy_k2 Rail_Hy1b', 'WarpTgt05'),
)


def placement(source):
    """First gate for focused diagnostics; the host uses placements()."""
    return placements(source)[0]


def placements(source):
    navigation_buoys.map_placements(source, 'Arena1a')
    nodes = hierarchy((source / 'Arena1a.Gob').read_bytes())
    gates = routes(nodes)
    if tuple((g['name'], g['destination_node']) for g in gates) != ROUTES:
        raise ValueError('expected the nine verified Arena1a routes in original order')
    return gates


def tag(gate):
    return 0x40010000 | (FIRST_INDEX + ROUTES.index((gate['name'], gate['destination_node'])))


def load(gate):
    packet = bytearray(191)
    # Native layout labels gates using the token after the first space.
    for offset, text in ((0, 'WarpGate'), (32, 'AoAObjects.odb'), (64, gate['name'].split(' ', 1)[1])):
        raw = text.encode('ascii')
        if len(raw) >= 32 or b'\0' in raw:
            raise ValueError('invalid gate label')
        packet[offset:offset + len(raw)] = raw
    struct.pack_into('<II', packet, 96, tag(gate), 7)
    packet[144:146] = b'\2\2'
    struct.pack_into('<3f', packet, 146, *gate['position'])
    struct.pack_into('<3f', packet, 158, *gate['destination'])
    return 0x25, bytes(packet)


def loads(gates):
    if isinstance(gates, dict):  # Single-gate native probes.
        gates = [gates]
    packets = [load(gate) for gate in gates]
    tags = [struct.unpack_from('<I', packet, 96)[0] for _, packet in packets]
    if len(set(tags)) != len(tags):
        raise ValueError('duplicate warp gate')
    return packets
