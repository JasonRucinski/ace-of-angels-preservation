"""Original-layout validation and ordered buoy delivery to first/late joiners."""
import contextlib
import io
import math
import struct
import tempfile
import unittest
from pathlib import Path

from aoa.maps import navigation as buoys
from aoa.host.runtime import parse_args
from tests.support import check_buoy_delivery
from aoa.paths import ROOT

SOURCE = ROOT / 'work/2.9.2/export/AOAOBJECTS/Arena1a.Gob'


@unittest.skipUnless(SOURCE.exists(), 'requires original exported Arena1a')
class BuoyTests(unittest.TestCase):
    def test_all_maps_and_nested_transforms(self):
        from aoa.maps import registry
        from aoa.formats import scene
        trn = ROOT / 'game/2.9.2/JRMAP.TRN'
        expected = {'Arena1a': 10, 'newterrain': 10, 'CTF_arena': 1,
                    'outerchange': 6, 'irrosa01': 5, 'hu_base_a': 1, 'hu_base_b': 1, 'JRMAP': 7}
        for name in registry.MAP_NAMES:
            nodes = buoys.map_placements(SOURCE.parent, name, trn)
            self.assertEqual(len(nodes), expected.get(name, 0), name)
            self.assertEqual(len(buoys.loads(nodes)), len(nodes))
        outer = buoys.map_placements(SOURCE.parent, 'outerchange')
        self.assertEqual(len({tuple(n['position']) for n in outer}), 6)
        for n in outer:
            parent_name = n['node_path'].split('/')[0]
            parent = next(p for p in scene.read_nodes((SOURCE.parent / 'outerchange.Gob').read_bytes()) if p['name'] == parent_name)
            child = next(p for p in scene.read_nodes((SOURCE.parent / (n['source_scene'] + '.Gob')).read_bytes()) if p['name'] == n['name'])
            expected_pos = [sum(child['position'][k] * parent['matrix'][k * 4 + c] for k in range(3)) + parent['matrix'][12 + c] for c in range(3)]
            self.assertLess(math.dist(n['position'], expected_pos), .001)
        jr = buoys.loads(buoys.map_placements(SOURCE.parent, 'JRMAP', trn))
        self.assertEqual([p[:32].rstrip(b'\0') for _, p in jr].count(b'Cube'), 4)
        self.assertEqual([p[:32].rstrip(b'\0') for _, p in jr].count(b'Buoy'), 3)

    def test_original_positions_names_and_native_kind(self):
        nodes = buoys.placements(SOURCE)
        packets = buoys.loads(nodes)
        self.assertEqual(len(packets), 10)
        for index, (node, (kind, packet)) in enumerate(zip(nodes, packets), 90):
            self.assertEqual((kind, len(packet)), (0x25, 191))
            self.assertEqual(packet[:32].rstrip(b'\0'), b'Buoy')
            self.assertEqual(packet[64:96].rstrip(b'\0').decode(), node['name'])
            self.assertEqual(struct.unpack_from('<II', packet, 96), (0x40010000 | index, 3))
            self.assertEqual(struct.unpack_from('<3f', packet, 0x92), tuple(node['position']))
            self.assertEqual(packet[0x90:0x92], b'\2\2')
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / 'bad.Gob'
            bad.write_bytes(SOURCE.read_bytes() + b'bad')
            with self.assertRaises(ValueError):
                buoys.placements(bad)

    def test_configuration_guards(self):
        base = ['key', 'log', '--profile', 'local-relay', '--map', 'Arena1a', '--experimental-terrain',
                '--sustained-delivery', '--navigation-buoys', str(SOURCE.parent)]
        self.assertEqual(parse_args(base).map, 'Arena1a')
        general = ['key', 'log', '--profile', 'local-relay', '--experimental-terrain',
                   '--sustained-delivery', '--navigation-buoys', str(SOURCE.parent)]
        self.assertEqual(parse_args(general + ['--map', 'outerchange']).map, 'outerchange')
        for extra in (['--target-ships', '89'], ['--no-sustained-delivery'],
                      ['--arena1a-buoys', str(SOURCE)]):
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                parse_args(general + extra)
        for extra in (['--target-ships', '89'], ['--no-sustained-delivery'], ['--no-experimental-relay']):
            with self.subTest(extra=extra), contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                parse_args(base + extra)

    def test_reliable_first_and_late_join(self):
        for map_name in ('Arena1a', 'outerchange', 'JRMAP', 'CTF_arena_b'):
            with self.subTest(map=map_name):
                check_buoy_delivery(self, map_name)


if __name__ == '__main__':
    unittest.main(verbosity=2)
