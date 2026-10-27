"""Native receiver/transit -> actual UDP host -> native observer decoder.

Requires original local assets. Uses synthetic peers and render bounds; no
running game, renderer, live collision geometry or display is exercised.
"""
import argparse
import json
import math
import select
import socket
import struct
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import aoanet
import relay_motion
import station_stub
import warp_trial
from test_station_stub import request

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'work/2.9.2/export/AOAOBJECTS'
CLIENT = ROOT / 'game/2.9.2/AOACLIENT.EXE.orig'
RESULTS = {}


@unittest.skipUnless(CLIENT.exists() and (SOURCE / 'Arena1a.Gob').exists(), 'requires original local assets')
class HeadlessWarpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from emulate_warp_trial import NativeWarp
        cls.native_type = NativeWarp
        cls.gate = warp_trial.placement(SOURCE)
        cls.packet = warp_trial.loads(cls.gate)[0][1]

    def test_complete_load_receiver_and_replay(self):
        native = self.native_type(CLIENT)
        actual = native.load(self.packet)
        self.assertEqual(actual['tag'], warp_trial.TAG)
        self.assertEqual(actual['name'], 'HyBase1_Rail')
        self.assertEqual(actual['kind'], 7)
        self.assertTrue(actual['active'] and actual['collidable'])
        self.assertEqual(actual['position'], struct.unpack_from('<3f', self.packet, 146))
        self.assertEqual(actual['destination'], struct.unpack_from('<3f', self.packet, 158))
        for _ in range(3):
            self.assertEqual(native.load(self.packet), actual)
        self.assertEqual((native.allocations, native.registrations, native.model_requests), (1, 1, 1))
        RESULTS['load_receiver'] = {'native_function_returned': True, 'duplicate_loads': 3,
                                    'allocations': 1, 'model_requests': 1,
                                    'fixture_services': sorted(native.called)}

    def test_native_overlap_boundaries_and_transit(self):
        native = self.native_type(CLIENT)
        fields = native.load(self.packet)
        origin, destination = fields['position'], fields['destination']
        cases = [('outside', 111., {}, False), ('boundary', 110., {}, False),
                 ('inside', 109.5, {}, True), ('center', 0., {}, True),
                 ('other_player', 0., {'local': False}, False),
                 ('busy', 0., {'busy': True}, False),
                 ('hidden', 0., {'visible': False}, False),
                 ('collision_disabled', 0., {'collidable': False}, False)]
        for name, distance, options, expected in cases:
            position = (origin[0], origin[1] + distance, origin[2])
            result = native.overlap(position, (0., 0., 100.), **options)
            with self.subTest(case=name):
                self.assertEqual(result['warped'], expected)
                self.assertEqual(result['position'],
                                 (destination[0], destination[1], destination[2] + 1000.) if expected else position)
        for velocity in ((0., 0., 0.), (100., 0., 0.), (0., -100., 0.),
                         (0., 0., 100.), (3., 4., 12.), (.01, 0., 0.)):
            result = native.overlap(origin, velocity)
            expected = tuple(p + v / max(math.sqrt(sum(c*c for c in velocity)), 100.) * 1000.
                             for p, v in zip(destination, velocity))
            self.assertTrue(result['warped'])
            self.assertLess(math.dist(result['position'], expected), .1)
            self.assertEqual(result['velocity'], velocity)
        # Re-running the same gate's overlap at its remote exit must not loop.
        result = native.overlap(origin, (0., 0., 100.))
        self.assertFalse(native.overlap(result['position'], result['velocity'])['warped'])
        RESULTS['overlap_and_transit'] = {'branch_cases': len(cases), 'velocity_cases': 6,
                                         'exit_does_not_retrigger_same_gate': True,
                                         'render_bounds': 'fixture spheres of radius 10 and 100; not actual model bounds',
                                         'sound_and_send_calls': 'stopped before these calls'}

    def test_udp_transit_observer_loss_late_join_and_reconnect(self):
        from emulate_motion_state import decoder, receive, compare
        from pe_util import PE
        key = bytes(range(256))
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.bind(('127.0.0.1', 0))
            endpoint = probe.getsockname()
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / 'key').write_bytes(key)
            process = subprocess.Popen([sys.executable, '-I', str(ROOT / 'tools/station_stub.py'),
                str(folder / 'key'), str(folder / 'log'), '--profile', 'local-relay',
                '--port', '0', '--tcp', '0', '--arena-port', str(endpoint[1]),
                '--map', 'Arena1a', '--experimental-terrain', '--sustained-delivery',
                '--warp-trial', str(SOURCE), '--seconds', '40'],
                stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            peers = [socket.socket(socket.AF_INET, socket.SOCK_DGRAM) for _ in range(4)]
            for peer in peers:
                peer.bind(('127.0.0.1', 0))
            records = {peer: [] for peer in peers}
            seen = {peer: set() for peer in peers}
            slots = {peer: i + 1 for i, peer in enumerate(peers)}
            gate_clients = {peer: self.native_type(CLIENT) for peer in peers}
            observers = {peer: decoder(PE(CLIENT)) for peer in peers}
            states = {peer: relay_motion.initial((0., 0., 0.)) for peer in peers}
            dropped = False
            drop_position = None
            pilot, observer, late, rejoined = peers

            def send(peer, kind, body):
                peer.sendto(aoanet.encode(kind, body, key), endpoint)

            def pump():
                nonlocal dropped
                ready, _, _ = select.select(peers, [], [], .02)
                for peer in ready:
                    try:
                        message = aoanet.decode(peer.recv(512), key)
                    except ConnectionResetError:
                        continue
                    self.assertTrue(message['crc_ok'])
                    kind, body = message['type'], message['payload']
                    if kind == 8:
                        reply = bytearray(body)
                        reply[6] = slots[peer]
                        send(peer, 9, bytes(reply))
                    if kind == 0x1b:
                        sequence, kind = struct.unpack_from('<IB', body, len(body) - 5)
                        send(peer, 0x0f, struct.pack('<I', sequence))
                        if sequence in seen[peer]:
                            continue
                        seen[peer].add(sequence)
                        body = body[:-5]
                    records[peer].append((kind, body))
                    if kind == 0x25:
                        self.assertEqual(body, self.packet)
                        gate_clients[peer].load(body)
                    if kind == 0x1f and struct.unpack_from('<H', body, 2)[0] == 1:
                        filtered = station_stub.movement_update(body, 1)
                        state, _, missing = relay_motion.update(filtered, states[peer])
                        self.assertFalse(missing)
                        if peer is observer and not dropped and state[0x40] == drop_position:
                            dropped = True
                            continue
                        states[peer] = state
                        receive(observers[peer], filtered)
                        compare(observers[peer], state)

            def until(predicate, timeout=8):
                deadline = time.monotonic() + timeout
                while not predicate():
                    self.assertIsNone(process.poll(), 'test host exited early')
                    self.assertLess(time.monotonic(), deadline, 'expected host response missing')
                    pump()

            def join(peer):
                deadline = time.monotonic() + 5
                while not any(kind == 11 for kind, _ in records[peer]):
                    send(peer, 10, request())
                    pump()
                    self.assertLess(time.monotonic(), deadline)
                ack = next(body for kind, body in records[peer] if kind == 11)
                self.assertEqual(struct.unpack_from('<I', ack, 2)[0], station_stub.player_tag(slots[peer]))
                until(lambda: gate_clients[peer].gate is not None)
                self.assertTrue(any(kind == 0x2c for kind, _ in records[peer]))

            try:
                join(pilot)
                join(observer)
                origin = gate_clients[pilot].fields()['position']
                velocity = (0., 0., 100.)
                send(pilot, *station_stub.motion_snapshot(1, (origin, velocity)))
                until(lambda: states[observer][0x40] == origin)
                transit = gate_clients[pilot].overlap(origin, velocity)
                self.assertTrue(transit['warped'])
                drop_position = transit['position']
                send(pilot, *station_stub.motion_snapshot(1, (drop_position, velocity)))
                until(lambda: dropped)
                self.assertEqual(states[observer][0x40], origin)
                # No additional upload: the host's periodic absolute refresh
                # must recover the observer after the dropped warp update.
                until(lambda: states[observer][0x40] == drop_position, timeout=3)
                self.assertEqual(states[observer][1], velocity)
                join(late)
                until(lambda: states[late][0x40] == drop_position)
                loads = [body for kind, body in records[late] if kind == 0x26 and
                         struct.unpack_from('<I', body, 0x28)[0] == station_stub.player_tag(1)]
                self.assertTrue(loads)
                self.assertEqual(struct.unpack_from('<3f', loads[-1], 0x1a4), drop_position)
                self.assertEqual(states[late][1], velocity)
                # An observer reconnects with a fresh peer/session and receives
                # exactly one gate plus the already-warped pilot's latest state.
                send(observer, 0x4e, b'\0')
                join(rejoined)
                until(lambda: states[rejoined][0x40] == drop_position)
                for peer in peers:
                    self.assertEqual(gate_clients[peer].allocations, 1)
                RESULTS['udp_chain'] = {
                    'native_load_and_transit_to_real_host_to_native_movement_decoder': 'passed',
                    'observer_recovers_without_second_upload': True,
                    'late_join_uses_post_warp_position_and_velocity': True,
                    'observer_reconnect_has_one_gate_and_current_pilot_position': True,
                    'synthetic_peer_connections': 4,
                    'scope': 'Movement prefix decoded natively; stats/rendering/full client loop not tested'}
            finally:
                for peer in peers:
                    peer.close()
                process.terminate()
                _, error = process.communicate(timeout=5)
                self.assertNotIn(b'Traceback', error)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(HeadlessWarpTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():
        raise SystemExit(1)
    if args.report and not result.skipped:
        report = {'scope': 'Headless native-code and real-host socket checks; no live game acceptance',
                  'tests_passed': result.testsRun, 'checks': RESULTS,
                  'remaining': ['Real model bounds and rendered orientation',
                                'Full game-loop collision entry', 'Actual clients on two PCs',
                                'Map-change cleanup and host-authorized transit']}
        args.report.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
