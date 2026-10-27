"""Read-only live gate inventory: PID export-directory output.json.

Checks placement and destination fields. Does not claim rendered orientation,
collision entry, travel, or multiplayer acceptance.
"""
import argparse
import json
import math
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from inspect_arena import snapshot
import warp_trial


def verify(live, gates):
    if (not live['active_players'] or not live['terrain_list_complete'] or
            len(live['terrain_objects']) != 239):
        raise ValueError('client must be in Arena1a flight with the 239-object terrain baseline')
    if isinstance(gates, dict):
        gates = [gates]
    results = [verify_gate(live, gate) for gate in gates]
    return {'scope': 'Live memory inventory only; transit and rendered orientation not verified',
            'objects': len(results), 'gates': results, 'terrain_objects': 239,
            'editor_orientation_restored': False, 'host_authorized_transit': False}


def verify_gate(live, gate):
    tag = hex(warp_trial.tag(gate))
    matches = [obj for obj in live['active_objects'] if obj['tag'] == tag]
    if len(matches) != 1:
        raise ValueError(f'expected exactly one trial gate with tag {tag}')
    obj = matches[0]
    f32 = lambda value: struct.unpack('<3f', struct.pack('<3f', *value))
    position_error = math.dist(obj['position'], f32(gate['position']))
    destination_error = math.dist(obj['target_position'], f32(gate['destination']))
    if (obj['name'] != gate['name'].split(' ', 1)[1] or obj['kind'] != 7 or
            not math.isfinite(position_error) or not math.isfinite(destination_error) or
            position_error > .01 or destination_error > .01 or
            obj['graphics'] == '0x0' or not obj['visible'] or not obj['collidable']):
        raise ValueError(f'trial gate mismatch: {obj}')
    return {'scope': 'Live memory inventory only; transit and rendered orientation not verified',
            'gate': gate['name'], 'destination_node': gate['destination_node'],
            'tag': tag, 'kind': 7, 'position_error': position_error,
            'destination_error': destination_error, 'graphics_present': True,
            'visible_flag': True, 'collidable_flag': True, 'terrain_objects': 239,
            'editor_orientation_restored': False, 'host_authorized_transit': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('pid', type=int)
    parser.add_argument('source', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    result = verify(snapshot(args.pid, include_objects=True), warp_trial.placements(args.source))
    args.output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, indent=2))
