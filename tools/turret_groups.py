"""Native turret-group status codec; not enabled in the host yet.

2.9.2 receiver 0x4AFD20 reads an enabled DWORD, up to 50 zero-terminated
object tags, then a 32-byte team name. This changes existing objects; it
does not spawn turrets or establish a flag's capture rules.
"""
import struct


def status(tags, *, enabled=False, team=''):
    tags = list(tags)
    if len(tags) > 50 or len(set(tags)) != len(tags):
        raise ValueError('expected at most 50 distinct turret tags')
    if any(type(tag) is not int or not 0 < tag <= 0xffffffff for tag in tags):
        raise ValueError('turret tags must be nonzero uint32 values')
    if type(enabled) is not bool:
        raise ValueError('enabled must be boolean')
    name = team.encode('ascii')
    if b'\0' in name or len(name) >= 32:
        raise ValueError('team must fit a null-terminated 32-byte field')
    if enabled and not name:
        raise ValueError('enabling turrets requires an explicit team name')
    packet = bytearray(236)
    struct.pack_into('<I', packet, 0, int(enabled))
    for index, tag in enumerate(tags):
        struct.pack_into('<I', packet, 4 + index * 4, tag)
    packet[204:204 + len(name)] = name
    return 0x70, bytes(packet)
