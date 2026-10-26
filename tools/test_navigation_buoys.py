"""Original-layout validation and ordered buoy delivery to first/late joiners."""
import contextlib
import io
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
import navigation_buoys as buoys
import station_stub as stub
from station_runtime import parse_args
from test_station_stub import request

SOURCE = Path(__file__).resolve().parents[1] / 'work/2.9.2/export/AOAOBJECTS/Arena1a.Gob'


@unittest.skipUnless(SOURCE.exists(), 'requires original exported Arena1a')
class BuoyTests(unittest.TestCase):
    def test_all_maps_and_nested_transforms(self):
        import online_terrain
        import scene2obj
        trn = Path(__file__).resolve().parents[1] / 'game/2.9.2/JRMAP.TRN'
        expected = {'Arena1a': 10, 'newterrain': 10, 'CTF_arena': 1,
                    'outerchange': 6, 'irrosa01': 5, 'hu_base_a': 1, 'hu_base_b': 1, 'JRMAP': 7}
        for name in online_terrain.MAP_NAMES:
            nodes = buoys.map_placements(SOURCE.parent, name, trn)
            self.assertEqual(len(nodes), expected.get(name, 0), name)
            self.assertEqual(len(buoys.loads(nodes)), len(nodes))
        outer = buoys.map_placements(SOURCE.parent, 'outerchange')
        self.assertEqual(len({tuple(n['position']) for n in outer}), 6)
        for n in outer:
            parent_name = n['node_path'].split('/')[0]
            parent = next(p for p in scene2obj.read_nodes((SOURCE.parent / 'outerchange.Gob').read_bytes()) if p['name'] == parent_name)
            child = next(p for p in scene2obj.read_nodes((SOURCE.parent / (n['source_scene'] + '.Gob')).read_bytes()) if p['name'] == n['name'])
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
                '--sustained-delivery', '--arena1a-buoys', str(SOURCE)]
        self.assertEqual(parse_args(base).map, 'Arena1a')
        general = ['key', 'log', '--profile', 'local-relay', '--experimental-terrain',
                   '--sustained-delivery', '--navigation-buoys', str(SOURCE.parent)]
        self.assertEqual(parse_args(general + ['--map', 'outerchange']).map, 'outerchange')
        for extra in (['--target-ships', '89'], ['--no-sustained-delivery'],
                      ['--arena1a-buoys', str(SOURCE)]):
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                parse_args(general + extra)
        for extra in (['--map', 'CTF_arena'], ['--target-ships', '89'],
                      ['--no-sustained-delivery'], ['--no-experimental-relay']):
            with self.subTest(extra=extra), contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                parse_args(base + extra)

    def test_reliable_first_and_late_join(self):
        for map_name in ('Arena1a', 'outerchange', 'JRMAP', 'CTF_arena_b'):
            with self.subTest(map=map_name):
                self.check_delivery(map_name)

    def check_delivery(self, map_name):
        key = bytes(range(256))
        trn = Path(__file__).resolve().parents[1] / 'game/2.9.2/JRMAP.TRN'
        expected = buoys.loads(buoys.map_placements(SOURCE.parent, map_name, trn))
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / 'key').write_bytes(key)
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
                probe.bind(('127.0.0.1', 0))
                endpoint = probe.getsockname()
            process = subprocess.Popen([sys.executable, '-I', str(Path(stub.__file__)),
                str(folder / 'key'), str(folder / 'log'), '--profile', 'local-relay',
                '--port', '0', '--tcp', '0', '--arena-port', str(endpoint[1]),
                '--map', map_name, '--experimental-terrain', '--sustained-delivery', '--navigation-buoys', str(SOURCE.parent), '--buoy-trn', str(trn),
                '--peer-timeout', '15', '--seconds', '30'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            peers = [socket.socket(socket.AF_INET, socket.SOCK_DGRAM) for _ in range(2)]
            records = {p: [] for p in peers}
            seen = {p: set() for p in peers}
            missed_ack = False

            def send(peer, kind, payload):
                peer.sendto(aoanet.encode(kind, payload, key), endpoint)

            def pump(seconds):
                nonlocal missed_ack
                deadline = time.monotonic() + seconds
                while time.monotonic() < deadline:
                    ready, _, _ = select.select(peers, [], [], min(.05, max(0, deadline - time.monotonic())))
                    for peer in ready:
                        try:
                            message = aoanet.decode(peer.recv(512), key)
                        except ConnectionResetError:
                            continue
                        kind, body = message['type'], message['payload']
                        if kind == 8:
                            reply = bytearray(body); reply[6] = peers.index(peer) + 1
                            send(peer, 9, bytes(reply))
                        if kind == 0x1B:
                            seq, inner = struct.unpack_from('<IB', body, len(body) - 5)
                            # Lose one ACK to exercise retransmit/dedup.
                            if inner == 0x25 and not missed_ack:
                                missed_ack = True
                            else:
                                send(peer, 0x0F, struct.pack('<I', seq))
                            if seq in seen[peer]:
                                continue
                            seen[peer].add(seq)
                            kind, body = inner, body[:-5]
                        records[peer].append((kind, body))

            try:
                for peer in peers:
                    peer.bind(('127.0.0.1', 0))
                for peer in peers:  # second arrives after first has all ten
                    deadline = time.monotonic() + 6
                    while not any(k == 0x0B for k, _ in records[peer]):
                        send(peer, 10, request()); pump(.1)
                        self.assertLess(time.monotonic(), deadline)
                        self.assertIsNone(process.poll())
                    deadline = time.monotonic() + 10
                    while (not any(k == 0x2C for k, _ in records[peer]) or
                           len([k for k, _ in records[peer] if k == 0x25]) < len(expected)):
                        pump(.1)
                        self.assertLess(time.monotonic(), deadline)
                    actual = [body for kind, body in records[peer] if kind == 0x25]
                    self.assertEqual(actual, [p for _, p in expected])
                    kinds = [k for k, _ in records[peer]]
                    if expected:
                        self.assertLess(kinds.index(0x2C), kinds.index(0x25))
                self.assertEqual(missed_ack, bool(expected))
            finally:
                for peer in peers: peer.close()
                process.terminate()
                stdout, stderr = process.communicate(timeout=5)
                self.assertNotIn(b'Traceback', stderr)


if __name__ == '__main__':
    unittest.main(verbosity=2)
