"""Probe original-client creation gates and inventory Arena1a rebuild work.

Runs original x86 branches up to (but never through) allocation. No process
memory is changed. Local per-node coordinates remain under ignored work/.
"""
import collections
import argparse
import hashlib
import json
import math
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from emulate_codec import Emu, HEAP, STACK, STOP
from patch_client import PRISTINE_292
from pe_util import PE
import scene2obj
from unicorn import UC_HOOK_CODE
from unicorn.x86_const import UC_X86_REG_EAX, UC_X86_REG_EBX, UC_X86_REG_EBP, UC_X86_REG_EDI, UC_X86_REG_EIP, UC_X86_REG_ESP

ROOT = Path(__file__).resolve().parents[1]


def probe_gates(client):
    assert hashlib.sha256(client.read_bytes()).hexdigest() == PRISTINE_292
    emu = Emu(PE(client))
    stops = {0x497861, 0x4A5960, 0x4964F8, 0x496306}

    def stop(uc, address, size, _):
        if address in stops:
            uc.emu_stop()

    emu.uc.hook_add(UC_HOOK_CODE, stop)
    results = []
    for kind, entry in [('turret', 0x497255), ('navigation', 0x49738F),
                        ('warp', 0x497560), ('flag', 0x4975DF)]:
        for enabled in [None, 'controller+4', 'controller+5', 'explicit argument']:
            sp = STACK + 0xE0000
            emu.write(HEAP, bytes(64))
            emu.write(sp, bytes(128))
            if enabled == 'controller+4':
                emu.write(HEAP + 4, b'\1')
            elif enabled == 'controller+5':
                emu.write(HEAP + 5, b'\1')
            elif enabled:
                emu.write(sp + 0x38, b'\1')
            emu.uc.reg_write(UC_X86_REG_EBX, HEAP)
            emu.uc.reg_write(UC_X86_REG_ESP, sp)
            emu.uc.emu_start(entry, STOP, count=80)
            destination = emu.uc.reg_read(UC_X86_REG_EIP)
            assert destination == (0x4A5960 if enabled else 0x497861)
            results.append({'kind': kind, 'enabled_by': enabled, 'allocation_reached': bool(enabled)})
    for flag in (0, 1):
        sp = STACK + 0xE0000
        emu.write(sp, bytes(128))
        emu.write(sp + 0x1C, struct.pack('<I', HEAP))
        emu.write(HEAP + 0x18, bytes([flag]))
        emu.uc.reg_write(UC_X86_REG_EBP, 0)
        emu.uc.reg_write(UC_X86_REG_ESP, sp)
        emu.uc.emu_start(0x4962F7, STOP, count=30)
        destination = emu.uc.reg_read(UC_X86_REG_EIP)
        assert destination == (0x496306 if flag else 0x4964F8)
        results.append({'kind': 'layout_warp', 'controller+0x18': flag,
                        'child_link_lookup_reached': bool(flag)})
    for category in (1, 5, 8):
        emu.uc.reg_write(UC_X86_REG_EAX, category)
        emu.uc.emu_start(0x496130, STOP, count=20)
        assert emu.uc.reg_read(UC_X86_REG_EIP) == 0x4964F8
        results.append({'layout_category': category, 'unconditionally_skipped': True})
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    live_source = parser.add_mutually_exclusive_group()
    live_source.add_argument('--pid', type=int, help='read-only snapshot of a client already flying Arena1a')
    live_source.add_argument('--snapshot', type=Path, help='previously captured inspect_arena --objects snapshot')
    args = parser.parse_args()
    source = ROOT / 'work/2.9.2/export/AOAOBJECTS'
    nodes = list(scene2obj.expanded_nodes(source, 'Arena1a', True))
    categories = dict(collections.Counter(n['category'] for n in nodes))
    assert categories == {1: 80, 4: 10, 5: 18, 6: 9, 7: 4, 8: 1, 9: 272}
    service = [n for n in nodes if n['name'].startswith(('ZA', 'ZShield', 'ZRepair', 'ZMissile'))]
    assert len(service) == 19
    report = {
        'scope': 'Original-code gate emulation and source-node inventory; allocation, AI and live restoration not tested',
        'client_sha256': PRISTINE_292,
        'map_sha256': hashlib.sha256((source / 'Arena1a.Gob').read_bytes()).hexdigest(),
        'root_records': 383, 'expanded_records': len(nodes), 'categories': categories,
        'gate_probes': probe_gates(ROOT / 'game/2.9.2/AOACLIENT.EXE.orig'),
        'missing_systems': {
            'turret_markers': 80, 'flag_markers': 18, 'navigation_markers': 10,
            'warp_markers': 9, 'service_markers': 19,
        },
        'service_types_by_name': dict(collections.Counter(
            'missile' if 'Missile' in n['name'] else 'repair' if 'Repair' in n['name'] else 'shield'
            for n in service)),
        'prior_live_baseline': {'terrain_objects': 239, 'safe_zones': 4,
                                'source': 'evidence/2.9.2/safe_zones_20261025.json'},
        'cautions': ['Markers are not necessarily renderable objects.',
                     'Four safe zones are not four additional terrain objects.',
                     'Controller flags alone do not make skipped turret/flag categories spawn.',
                     '136 gameplay markers is an inventory, not a promise of 136 additional models.',
                     'Object counts alone do not reconcile names, transforms or grouping.'],
    }
    if args.pid or args.snapshot:
        from inspect_arena import snapshot
        live = (snapshot(args.pid, include_objects=True) if args.pid else
                json.loads(args.snapshot.read_text(encoding='utf-8-sig')))
        if not live['active_players'] or not live['terrain_list_complete']:
            raise ValueError('client must be in flight with a complete terrain list')
        terrain = live['terrain_objects']
        static = [o for o in terrain if o['terrain_kind'] == 0]
        matched = [n for n in nodes if any(o['name'] == n['name'] and
                   math.dist(o['position'], n['position']) < 2 for o in static)]
        if len(static) != 235 or len(matched) != 235 or live['safe_zone_count'] != 4:
            raise ValueError('snapshot does not match the expected Arena1a baseline')
        output = ROOT / 'work/arena1a-game-trial/live-snapshot.json'
        if args.pid:
            output.write_text(json.dumps(live, indent=2) + '\n', encoding='utf-8')
        report['live_baseline'] = {
            'terrain_objects': len(terrain), 'matched_static_nodes': len(matched),
            'match_criterion': 'same name and position within 2 game units',
            'static_collidable_count': sum(o['collidable'] for o in static),
            'safe_zone_placeholders': sum(o['terrain_kind'] == 2 for o in terrain),
            'safe_zone_count': live['safe_zone_count'],
            'controller_flags': live['terrain_controller_flags'],
            'dynamic_object_names': [o['name'] for o in live['active_objects']],
            'additional_missing_node': 'Cube Home',
            'reconciliation': {'static': 235, 'safe_zones': 4, 'gameplay_markers': 136,
                               'cube_home': 1, 'group_or_link_helpers': 17, 'nested_layout_reference': 1},
            'limitations': 'Read-only live snapshot; collision flag is not a collision-play test; no nodes restored yet',
        }
    output = ROOT / 'evidence/2.9.2/arena1a_rebuild_20261026.json'
    output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
