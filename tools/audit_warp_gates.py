"""Recover Arena1a warp destinations and exercise original client code offline.

No live process writes, packets, asset changes or gate activation. Optional
full coordinates stay in a local report; committed evidence contains names
and checks. The emulated layout stops before object allocation, and the
collision probe stops before sound/network calls.
"""
import argparse
import hashlib
import json
import math
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from audit_turret_groups import hierarchy
from navigation_buoys import ARENA1A_SHA256
from patch_client import PRISTINE_292

ROOT = Path(__file__).resolve().parents[1]


def routes(nodes):
    result = []
    for gate in nodes:
        if gate['category'] != 6:
            continue
        children = [n for n in nodes if n['parent_id'] == gate['node_id']]
        if len(children) != 1:
            raise ValueError(f"{gate['name']}: expected exactly one destination child")
        child = children[0]
        result.append({'name': gate['name'], 'node_id': gate['node_id'],
                       'destination_node': child['name'], 'destination_id': child['node_id'],
                       'position': gate['world_position'],
                       'destination': child['world_position']})
    if len(result) != 9:
        raise ValueError('expected nine Arena1a warp gates')
    return result


def native_checks(client, nodes, links):
    if hashlib.sha256(client.read_bytes()).hexdigest() != PRISTINE_292:
        raise ValueError('requires the original 2.9.2 executable')
    from pe_util import PE
    from emulate_codec import Emu, HEAP, STACK, SCRATCH, STOP
    from unicorn import UC_HOOK_CODE
    from unicorn.x86_const import (UC_X86_REG_EBP, UC_X86_REG_EBX,
                                   UC_X86_REG_EDI, UC_X86_REG_EIP, UC_X86_REG_ESP)
    emu = Emu(PE(client))
    addresses = {n['node_id']: HEAP + 0x10000 + i * 0x400 for i, n in enumerate(nodes)}
    for node in nodes:
        address = addresses[node['node_id']]
        emu.write(address + 0x7c, struct.pack('<16f', *node['matrix']))
        emu.write(address + 0x144, struct.pack('<I', addresses.get(node['parent_id'], 0)))
    stops = {0x4971f0, 0x4964f8, 0x4b5110}

    def stop(uc, address, size, _):
        if address in stops:
            uc.emu_stop()

    emu.uc.hook_add(UC_HOOK_CODE, stop)
    control, table = HEAP + 0x1000, HEAP + 0x2000
    sp = STACK + 0xe0000
    errors = []
    for link in links:
        root, child = addresses[link['node_id']], addresses[link['destination_id']]
        emu.write(root + 4, struct.pack('<I', 1))
        emu.write(root + 0x10, struct.pack('<I', table))
        emu.write(table, struct.pack('<II', child, 0x51870001))
        emu.write(control + 0x18, b'\1')
        emu.write(sp, bytes(0x200))
        emu.write(sp + 0x10, struct.pack('<I', root))
        emu.write(sp + 0x1c, struct.pack('<I', control))
        emu.uc.reg_write(UC_X86_REG_ESP, sp)
        emu.uc.reg_write(UC_X86_REG_EBP, 0)
        emu.uc.emu_start(0x4962f7, STOP, count=10000)
        assert emu.uc.reg_read(UC_X86_REG_EIP) == 0x4971f0
        args = emu.uc.reg_read(UC_X86_REG_ESP)
        database, model, params, override = struct.unpack('<4I', emu.read(args + 4, 16))
        assert emu.pe.cstr(database).lower() == 'aoaobjects.odb'
        assert emu.pe.cstr(model) == 'WarpGate' and override == 0
        assert struct.unpack('<I', emu.read(params + 0x2c, 4))[0] == 7
        target = struct.unpack('<3f', emu.read(params + 0x34, 12))
        error = math.dist(target, link['destination'])
        assert error < .1, (link['name'], error)
        errors.append(error)

    rejected = []
    for name, enabled, count, pointer, kind in (
            ('controller disabled', 0, 1, child, 0x51870001),
            ('no child', 1, 0, child, 0x51870001),
            ('wrong child type', 1, 1, child, 0x51870005),
            ('null child', 1, 1, 0, 0x51870001)):
        emu.write(control + 0x18, bytes([enabled]))
        emu.write(root + 4, struct.pack('<I', count))
        emu.write(table, struct.pack('<II', pointer, kind))
        emu.write(sp, bytes(0x200))
        emu.write(sp + 0x10, struct.pack('<I', root))
        emu.write(sp + 0x1c, struct.pack('<I', control))
        emu.uc.reg_write(UC_X86_REG_ESP, sp)
        emu.uc.reg_write(UC_X86_REG_EBP, 0)
        emu.uc.emu_start(0x4962f7, STOP, count=1000)
        assert emu.uc.reg_read(UC_X86_REG_EIP) == 0x4964f8
        rejected.append(name)

    # Original sender and kind-7 receiver: destination is packet +0x9E,
    # then object +0x70. Execute the dispatch, not a Python copy of it.
    obj, extra, packet, received = HEAP + 0x4000, HEAP + 0x5000, SCRATCH, HEAP + 0x6000
    emu.write(obj + 0x1f8, struct.pack('<I', 7))
    emu.write(obj + 0x308, struct.pack('<I', extra))
    for link in links:
        target = struct.pack('<3f', *link['destination'])
        emu.write(extra + 0x34, target)
        emu.uc.reg_write(UC_X86_REG_EBX, obj)
        emu.uc.reg_write(UC_X86_REG_EBP, packet)
        emu.uc.emu_start(0x48a6c5, 0x48a718, count=100)
        assert emu.read(packet + 0x9e, 12) == target
        assert struct.unpack('<I', emu.read(packet + 0x64, 4))[0] == 7
        emu.uc.reg_write(UC_X86_REG_EDI, received)
        emu.uc.emu_start(0x4a699f, 0x4a6a9f, count=100)
        assert emu.read(received + 0x70, 12) == target

    # Native node-warp collision moves the ship to destination plus a
    # velocity-directed exit offset. Stop before sound and outgoing messages.
    speed_floor = struct.unpack('<f', emu.pe.read_va(0x5900bc, 4))[0]
    exit_offset = struct.unpack('<f', emu.pe.read_va(0x5900b8, 4))[0]
    destination = (1000., -2000., 3000.)
    emu.write(received + 0x70, struct.pack('<3f', *destination))
    collision_errors = []
    for velocity in ((0., 0., 0.), (100., 0., 0.), (0., -100., 0.),
                     (0., 0., 100.), (3., 4., 12.), (.01, 0., 0.)):
        emu.write(obj + 0x54, struct.pack('<3f', *velocity))
        emu.thiscall(0x4b5060, control, obj, received)
        assert emu.uc.reg_read(UC_X86_REG_EIP) == 0x4b5110
        denominator = max(math.sqrt(sum(v*v for v in velocity)), speed_floor)
        expected = [p + v / denominator * exit_offset for p, v in zip(destination, velocity)]
        actual = struct.unpack('<3f', emu.read(obj + 0x30, 12))
        error = math.dist(actual, expected)
        assert error < .001
        assert emu.read(obj + 0x30, 12) == emu.read(obj + 0x70, 12)
        assert emu.read(obj + 0x54, 12) == struct.pack('<3f', *velocity)
        collision_errors.append(error)
    emu.thiscall(0x49a560, received, 7)
    assert struct.unpack('<I', emu.read(received + 0x1f4, 4))[0] == 7
    assert emu.read(received + 0x2fb, 1) == b'\1'
    assert emu.pe.u32(0x4b3564 + 4) == 0x4b30bf
    stops.update((0x4b5060, 0x4b34d2))
    for local_player, busy, expected in ((1, 0, 0x4b5060), (0, 0, 0x4b34d2),
                                         (1, 1, 0x4b34d2)):
        emu.write(sp + 0x13, bytes([local_player]))
        emu.write(control + 0x20, bytes([busy]))
        emu.uc.reg_write(UC_X86_REG_ESP, sp)
        emu.uc.reg_write(UC_X86_REG_EBX, control)
        emu.uc.reg_write(UC_X86_REG_EBP, obj)
        emu.uc.reg_write(UC_X86_REG_EDI, received)
        emu.uc.emu_start(0x4b30bf, STOP, count=100)
        assert emu.uc.reg_read(UC_X86_REG_EIP) == expected
    return {'layout_destinations': len(errors), 'maximum_destination_error': max(errors),
            'layout_rejections': rejected, 'native_destination_field_round_trips': len(links),
            'collision_vectors': len(collision_errors), 'maximum_collision_error': max(collision_errors),
            'exit_offset': exit_offset, 'speed_floor': speed_floor,
            'kind_7_collidable_and_node_collision_dispatch': True,
            'local_player_and_busy_guard_cases': 3}


def relay_checks(links):
    from station_stub import movement_update
    import relay_motion
    for link in links:
        position = struct.unpack('<3f', struct.pack('<3f', *link['destination']))
        packet = struct.pack('<HHI6f', 0x8000, 1, 0x41, *position, 0., 0., 100.)
        filtered = movement_update(packet, 1)
        state, present, missing = relay_motion.update(filtered, relay_motion.initial(link['position']))
        assert state[0x40] == position and not missing
        observer, _, missing = relay_motion.update(relay_motion.snapshot(1, state),
                                                   relay_motion.initial(link['position']))
        assert observer[0x40] == position and observer[1] == (0., 0., 100.) and not missing
    return {'destination_jumps_through_movement_codecs': len(links),
            'scope': 'Synthetic codec checks, not socket or live two-client tests',
            'host_authorizes_gate_transit': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--local-report', type=Path)
    args = parser.parse_args()
    nodes = hierarchy((ROOT / 'work/2.9.2/export/AOAOBJECTS/Arena1a.Gob').read_bytes())
    links = routes(nodes)
    checks = native_checks(ROOT / 'game/2.9.2/AOACLIENT.EXE.orig', nodes, links)
    import gob2obj
    source = ROOT / 'work/2.9.2/export/AOAOBJECTS'
    config = source / 'WarpGate.Sco'
    model = gob2obj.strings(config.read_bytes())[4][2]
    archive = next(a for a in json.loads((ROOT / 'evidence/2.9.2/archives.json').read_text())
                   if a['archive'].upper().endswith('AOAOBJECTS.ODB'))
    hashes = {entry['name'].casefold(): entry['sha256'] for entry in archive['entries']}
    for path in (config, source / (model + '.Gob')):
        assert hashlib.sha256(path.read_bytes()).hexdigest() == hashes[path.name.casefold()]
    report = {'scope': 'Offline original-code research; no live gates spawned or transit tested',
              'client_sha256': PRISTINE_292, 'map_sha256': ARENA1A_SHA256,
              'gates': [{k: v for k, v in link.items() if k not in ('position', 'destination')} for link in links],
              'native_checks': checks,
              'model_object': 'WarpGate', 'model_gob': model,
              'model_config_and_geometry_hashes_match_archive': True,
              'relay_checks': relay_checks(links),
              'remaining': ['Rendered gate orientation and trigger geometry',
                            'Live single-gate transit and re-entry behavior',
                            'Host movement validation and two-client synchronization',
                            'Late join, map changes and cleanup']}
    if args.local_report:
        args.local_report.parent.mkdir(parents=True, exist_ok=True)
        args.local_report.write_text(json.dumps({'summary': report, 'routes': links}, indent=2) + '\n')
    path = ROOT / 'evidence/2.9.2/warp_gates_20261026.json'
    path.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
