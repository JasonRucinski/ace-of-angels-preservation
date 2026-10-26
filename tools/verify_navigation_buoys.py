"""Read-only live verification: PID Arena1a.Gob output.json."""
import json
import argparse
import math
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import navigation_buoys
from inspect_arena import snapshot


def verify(live, nodes, map_name='Arena1a'):
    found = []
    for index, node in enumerate(nodes, navigation_buoys.FIRST_INDEX):
        tag = hex(0x40010000 | index)
        matches = [o for o in live['active_objects'] if o['tag'] == tag]
        if len(matches) != 1:
            raise ValueError(f"{node['name']}: expected one live tag {tag}, found {len(matches)}")
        obj = matches[0]
        expected_position = struct.unpack('<3f', struct.pack('<3f', *node['position']))
        error = math.dist(obj['position'], expected_position)
        if (obj['name'] != node['name'] or obj['kind'] != 3 or error > .01 or
                obj['graphics'] == '0x0' or not obj['visible'] or not obj['collidable']):
            raise ValueError(f"{node['name']}: wrong name/type/position or missing graphics/visibility/collision")
        if sum(o['name'] == node['name'] for o in live['active_objects']) != sum(n['name'] == node['name'] for n in nodes):
            raise ValueError(f"{node['name']}: duplicate name")
        found.append({'name': node['name'], 'tag': tag, 'kind': obj['kind'],
                      'position_error': error, 'graphics_present': True,
                      'visible_flag': True, 'collidable_flag': True})
    tour = json.loads((navigation_buoys.ROOT / 'evidence/2.9.2/map_viewer_tour_20261023.json').read_text())
    baseline = 23 if map_name == 'JRMAP' else tour['maps'][map_name]['terrain_objects']
    if len(live['terrain_objects']) != baseline or not live['terrain_list_complete']:
        raise ValueError(f'{map_name} terrain baseline changed')
    return {'scope': 'Live memory verification, not visual acceptance or multiplayer collision acceptance',
            'map': map_name, 'buoys': found, 'terrain_objects': baseline, 'safe_zones': live['safe_zone_count'],
            'editor_rotations_restored': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('pid', type=int)
    parser.add_argument('source', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--map', default='Arena1a', choices=navigation_buoys.online_terrain.MAP_NAMES)
    parser.add_argument('--trn', type=Path)
    args = parser.parse_args()
    nodes = (navigation_buoys.placements(args.source) if args.source.is_file() and args.map == 'Arena1a' else
             navigation_buoys.map_placements(args.source, args.map, args.trn))
    result = verify(snapshot(args.pid, include_objects=True), nodes, args.map)
    args.output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, indent=2))
