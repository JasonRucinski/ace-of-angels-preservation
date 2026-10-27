"""Single gate guards, original-client destination receipt and reliable delivery."""
import contextlib
import copy
import hashlib
import io
import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import navigation_buoys
import turret_trial
import warp_trial
import verify_warp_trial
from station_runtime import parse_args
import test_navigation_buoys
from patch_client import PRISTINE_292

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'work/2.9.2/export/AOAOBJECTS'
CLIENT = ROOT / 'game/2.9.2/AOACLIENT.EXE.orig'


@unittest.skipUnless((SOURCE / 'Arena1a.Gob').exists(), 'requires original exported maps')
class WarpTests(unittest.TestCase):
    def test_config_and_packet(self):
        gate = warp_trial.placement(SOURCE)
        kind, packet = warp_trial.loads(gate)[0]
        self.assertEqual((kind, len(packet)), (0x25, 191))
        self.assertEqual(packet[:32].rstrip(b'\0'), b'WarpGate')
        self.assertEqual(packet[64:96].rstrip(b'\0'), b'HyBase1_Rail')
        self.assertEqual(struct.unpack_from('<II', packet, 96), (warp_trial.TAG, 7))
        self.assertEqual(packet[146:158], struct.pack('<3f', *gate['position']))
        self.assertEqual(packet[158:170], struct.pack('<3f', *gate['destination']))
        self.assertNotEqual(packet[146:158], packet[158:170])
        base = ['key', 'log', '--profile', 'local-relay', '--experimental-terrain',
                '--sustained-delivery', '--map', 'Arena1a', '--warp-trial', str(SOURCE)]
        self.assertEqual(parse_args(base + ['--target-ships', '83']).target_ships, 83)
        self.assertEqual(parse_args(base + ['--bind-address', '127.0.0.2']).advertised_address, '127.0.0.2')
        self.assertEqual(parse_args(base + ['--profile', 'local-guests']).profile, 'local-guests')
        for extra in (['--map', 'JRMAP'], ['--no-sustained-delivery'],
                      ['--no-experimental-relay'], ['--target-ships', '84'],
                      ['--bind-address', '0.0.0.0'], ['--bind-address', '192.168.1.5'],
                      ['--profile', 'lan-dogfight', '--bind-address', '192.168.1.5'],
                      ['--warp-trial', str(SOURCE / 'missing')]):
            with self.subTest(extra=extra), contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                parse_args(base + extra)
        without_terrain = [arg for arg in base if arg != '--experimental-terrain']
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            parse_args(without_terrain)

    @unittest.skipUnless(CLIENT.exists(), 'requires original client')
    def test_original_client_receives_trial_destination(self):
        from emulate_codec import Emu, HEAP, SCRATCH
        from pe_util import PE
        from unicorn.x86_const import UC_X86_REG_EBP, UC_X86_REG_EDI, UC_X86_REG_EIP
        self.assertEqual(hashlib.sha256(CLIENT.read_bytes()).hexdigest(), PRISTINE_292)
        emu = Emu(PE(CLIENT))
        gate = warp_trial.placement(SOURCE)
        packet = warp_trial.loads(gate)[0][1]
        emu.write(SCRATCH, packet)
        emu.uc.reg_write(UC_X86_REG_EBP, SCRATCH)
        emu.uc.reg_write(UC_X86_REG_EDI, HEAP)
        emu.uc.emu_start(0x4a699f, 0x4a6a9f, count=100)
        self.assertEqual(emu.uc.reg_read(UC_X86_REG_EIP), 0x4a6a9f)
        self.assertEqual(emu.read(HEAP + 0x70, 12), packet[158:170])
        emu.thiscall(0x49a560, HEAP, 7)
        self.assertEqual(emu.read(HEAP + 0x2fb, 1), b'\1')

    def test_first_late_join_and_gate_ack_loss_with_other_nodes(self):
        expected = navigation_buoys.loads(navigation_buoys.map_placements(SOURCE, 'Arena1a'))
        expected += turret_trial.loads(turret_trial.placements(SOURCE))
        expected += warp_trial.loads(warp_trial.placement(SOURCE))
        test_navigation_buoys.BuoyTests.check_delivery(self, 'Arena1a',
                                ('--turret-trial', str(SOURCE), '--warp-trial', str(SOURCE)),
                                expected, drop_ack_tag=warp_trial.TAG)

    def test_live_verifier_rejects_missing_or_broken_destinations(self):
        gate = warp_trial.placement(SOURCE)
        packet = warp_trial.loads(gate)[0][1]
        obj = {'tag': hex(warp_trial.TAG), 'name': 'HyBase1_Rail', 'kind': 7,
               'position': struct.unpack_from('<3f', packet, 146),
               'target_position': struct.unpack_from('<3f', packet, 158),
               'graphics': '0x1234', 'visible': True, 'collidable': True}
        live = {'active_players': [{}], 'active_objects': [obj],
                'terrain_list_complete': True, 'terrain_objects': [{}] * 239}
        self.assertEqual(verify_warp_trial.verify(live, gate)['destination_error'], 0)
        for key, value in (('target_position', (0, 0, 0)), ('target_position', (float('nan'), 0, 0)),
                           ('position', (float('nan'), 0, 0)), ('kind', 0),
                           ('graphics', '0x0'), ('collidable', False)):
            bad = copy.deepcopy(live)
            bad['active_objects'][0][key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                verify_warp_trial.verify(bad, gate)
        for key, value in (('active_objects', []), ('active_objects', [obj, obj]),
                           ('terrain_objects', []), ('active_players', [])):
            bad = dict(live, **{key: value})
            with self.subTest(key=key), self.assertRaises(ValueError):
                verify_warp_trial.verify(bad, gate)


if __name__ == '__main__':
    unittest.main(verbosity=2)
