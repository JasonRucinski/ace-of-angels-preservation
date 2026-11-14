"""Original placements, guarded configuration and actual ordered delivery."""
import contextlib
import io
import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import navigation_buoys
import turret_trial
import test_navigation_buoys
from station_runtime import parse_args

SOURCE = Path(__file__).resolve().parents[1] / 'work/2.9.2/export/AOAOBJECTS'


@unittest.skipUnless((SOURCE / 'Arena1a.Gob').exists(), 'requires original exported maps')
class TrialTests(unittest.TestCase):
    def test_placements_and_guards(self):
        nodes = turret_trial.placements(SOURCE)
        packets = turret_trial.loads(nodes)
        self.assertEqual([n['name'] for n in nodes],
                         ['Turret ND-', 'Turret ND0', 'Turret ND1', 'Turret ND2', 'Turret ND3'])
        for index, node in enumerate(nodes):
            kind, body = packets[2 * index]
            tag = 0x40010050 + index
            self.assertEqual((kind, body[:32].rstrip(b'\0')), (0x25, b'TurretA'))
            self.assertEqual(struct.unpack_from('<II', body, 96), (tag, 1))
            self.assertEqual(body[146:158], struct.pack('<3f', *node['world_position']))
            self.assertNotEqual(body[146:158], struct.pack('<3f', *node['position']))
            self.assertEqual(body[144:146], b'\2\2')
            self.assertEqual(packets[2 * index + 1][0], 0x70)
            self.assertEqual(struct.unpack_from('<II', packets[2 * index + 1][1]), (0, tag))
        base = ['key', 'log', '--profile', 'local-relay', '--experimental-terrain',
                '--sustained-delivery', '--map', 'Arena1a', '--turret-trial', str(SOURCE)]
        self.assertEqual(parse_args(base + ['--target-ships', '78']).target_ships, 78)
        self.assertEqual(parse_args(base + ['--bind-address', '127.0.0.2',
                                           '--advertised-address', '127.0.0.2']).bind_address, '127.0.0.2')
        for extra in (['--map', 'JRMAP'], ['--no-sustained-delivery'],
                      ['--no-experimental-relay'], ['--target-ships', '79'],
                      ['--bind-address', '0.0.0.0', '--advertised-address', '0.0.0.0'],
                      ['--bind-address', '192.168.1.5', '--advertised-address', '192.168.1.5']):
            with self.subTest(extra=extra), contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                parse_args(base + extra)

    def test_first_late_join_with_buoys_and_lost_ack(self):
        expected = navigation_buoys.loads(navigation_buoys.map_placements(SOURCE, 'Arena1a'))
        expected += turret_trial.loads(turret_trial.placements(SOURCE))
        test_navigation_buoys.BuoyTests.check_delivery(
            self, 'Arena1a', ('--turret-trial', str(SOURCE)), expected)


if __name__ == '__main__':
    unittest.main(verbosity=2)
