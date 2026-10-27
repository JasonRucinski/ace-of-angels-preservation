"""Read-only acceptance of the inactive Arena1a placement trial in memory."""
import argparse
import json
import math
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from inspect_arena import snapshot
import turret_trial


def verify(live, nodes):
    if not live['active_players']:
        raise ValueError('client must be in flight')
    results = []
    for index, node in enumerate(nodes, turret_trial.FIRST_INDEX):
        tag = hex(0x40010000 | index)
        matches = [obj for obj in live['active_objects'] if obj['tag'] == tag]
        if len(matches) != 1:
            raise ValueError(f'{tag}: expected exactly one turret')
        obj = matches[0]
        position = struct.unpack('<3f', struct.pack('<3f', *node['world_position']))
        error = math.dist(position, obj['position'])
        if (obj['name'] != node['name'] or obj['kind'] != 1 or error > .01 or
                obj['graphics'] == '0x0' or not obj['visible'] or
                obj['ai'] == '0x0' or obj['turret_activation'] != 0):
            raise ValueError(f"{tag}: trial mismatch: {obj}")
        results.append({'tag': tag, 'name': obj['name'], 'position_error': error,
                        'graphics_present': True, 'visible_flag': True, 'ai_present': True,
                        'activation': 0})
    if not live['terrain_list_complete'] or len(live['terrain_objects']) != 239:
        raise ValueError('Arena1a terrain baseline changed')
    return {'scope': 'Live memory verification; no visual or combat acceptance implied',
            'group': turret_trial.GROUP, 'turrets': results,
            'model_assignment': 'provisional TurretA', 'orientation_restored': False,
            'terrain_objects': 239, 'firing_enabled': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('pid', type=int)
    parser.add_argument('source', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    result = verify(snapshot(args.pid, include_objects=True), turret_trial.placements(args.source))
    args.output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, indent=2))
