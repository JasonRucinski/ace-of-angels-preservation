"""Helpers several server suites share: synthetic client packets and replies.

Standard library and aoa only, so every game-free suite can import it.
"""
import select
import socket
import struct
import subprocess
import sys
import tempfile
import time
from collections import deque
from pathlib import Path

from aoa import paths
from aoa.formats import aoapack
from aoa.maps import navigation as buoys
from aoa.paths import ROOT
from aoa.protocol import codec

ARENA1A_GOB = ROOT / 'work/2.9.2/export/AOAOBJECTS/Arena1a.Gob'


def request():
    payload = bytearray(381)
    payload[1:5] = (9).to_bytes(4, "little")
    payload[5:9] = (2).to_bytes(4, "little")
    payload[9:13] = (2).to_bytes(4, "little")
    payload[31:40] = b"testpilot"
    return bytes(payload)


def fire_missile(target=0x80010002, shooter=0x80010001, count=1, lock=100.0):
    """A launch shaped like the real client's (stack bytes after names)."""
    p = bytearray(0x92)
    struct.pack_into("<fIII", p, 0, lock, target, shooter, count)
    stack = bytes.fromhex("18000000688c5303acf71900b4f71900ffffffff")
    p[0x50:0x70] = (b"Type II 1.1\0" + stack)[:0x20]
    p[0x70:0x90] = (b"Rack IIB a\0\0" + stack)[:0x20]
    return bytes(p)


def read_reply(client):
    with client.makefile("rb") as stream:
        header = stream.read(4)
        if len(header) != 4:
            raise AssertionError("missing TCP frame header")
        size = int.from_bytes(header, "little")
        body = stream.read(size)
        if len(body) != size:
            raise AssertionError("truncated TCP reply")
        return aoapack.decompress(body)[0] if size else b""


def job_request(job=5, identity=0, flag=0):
    header = bytearray(142)
    header[:12] = b"private-name"
    struct.pack_into("<I", header, 60, identity)
    header[128:130] = bytes([job, flag])
    return bytes(header)


class ClientHistory:
    """The original filter (0x4C2730): 30 IDs, circular, zero pre-filled."""

    def __init__(self):
        self.ids = deque([0] * 30, maxlen=30)

    def first(self, sequence):
        if sequence in self.ids:
            return False
        self.ids.append(sequence)
        return True


class SyntheticClient:
    """Models the 2.9.2 receive path: ACK every 0x1B, filter, then dispatch."""

    def __init__(self, key):
        self.key = key
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("127.0.0.1", 0))
        self.history = ClientHistory()
        self.applied, self.pending = [], {}
        self.sequence, self.slot, self.silent = 1, 0, False
        self.acks = {}

    def send(self, endpoint, kind, body):
        self.sock.sendto(codec.encode(kind, body, self.key), endpoint)

    def send_reliable(self, endpoint, kind, body):
        packet = body + struct.pack("<I", self.sequence) + bytes([kind])
        self.pending[self.sequence] = [endpoint, packet, time.monotonic() + 0.2]
        self.sequence += 1
        self.send(endpoint, 0x1B, packet)

    def handle(self, wire, source):
        message = codec.decode(wire, self.key)
        assert message["crc_ok"]
        kind, body = message["type"], message["payload"]
        if kind == 0x1B:
            self.send(source, 0x0F, body[-5:-1])
            if not self.history.first(struct.unpack("<I", body[-5:-1])[0]):
                return
            kind, body = body[-1], body[:-5]
        if kind == 0x0F:
            self.pending.pop(struct.unpack("<I", body)[0], None)
        elif kind == 8:
            reply = bytearray(body)
            reply[6] = self.slot
            self.send(source, 9, bytes(reply))
        elif kind == 0x0B:
            self.acks[source[1]] = body
        self.applied.append((kind, body))

    def resend(self):
        now = time.monotonic()
        for entry in self.pending.values():
            if now >= entry[2]:
                self.send(entry[0], 0x1B, entry[1])
                entry[2] = now + 0.2

    def bodies(self, kind):
        return [body for applied, body in self.applied if applied == kind]


def check_buoy_delivery(self, map_name, extra=(), expected=None, drop_ack_tag=None):
    """Run the server on map_name with navigation buoys; check what a first and a late joiner receive.

    `self` is the calling TestCase; needs the exported Arena1a (ARENA1A_GOB).
    """
    key = bytes(range(256))
    trn = ROOT / 'game/2.9.2/JRMAP.TRN'
    if expected is None:
        expected = buoys.loads(buoys.map_placements(ARENA1A_GOB.parent, map_name, trn))
    watched = {kind for kind, _ in expected} | {0x25}
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp)
        (folder / 'key').write_bytes(key)
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.bind(('127.0.0.1', 0))
            endpoint = probe.getsockname()
        process = subprocess.Popen([sys.executable, '-I', str(paths.entry("station_stub")),
            str(folder / 'key'), str(folder / 'log'), '--profile', 'local-relay',
            '--port', '0', '--tcp', '0', '--arena-port', str(endpoint[1]),
            '--map', map_name, '--experimental-terrain', '--sustained-delivery', '--navigation-buoys', str(ARENA1A_GOB.parent), '--buoy-trn', str(trn),
            '--peer-timeout', '15', '--seconds', '30', *extra], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        peers = [socket.socket(socket.AF_INET, socket.SOCK_DGRAM) for _ in range(2)]
        records = {p: [] for p in peers}
        seen = {p: set() for p in peers}
        missed_ack = False
        missed_event = None
        retransmitted = False

        def send(peer, kind, payload):
            peer.sendto(codec.encode(kind, payload, key), endpoint)

        def pump(seconds):
            nonlocal missed_ack, missed_event, retransmitted
            deadline = time.monotonic() + seconds
            while time.monotonic() < deadline:
                ready, _, _ = select.select(peers, [], [], min(.05, max(0, deadline - time.monotonic())))
                for peer in ready:
                    try:
                        message = codec.decode(peer.recv(512), key)
                    except ConnectionResetError:
                        continue
                    kind, body = message['type'], message['payload']
                    if kind == 8:
                        reply = bytearray(body); reply[6] = peers.index(peer) + 1
                        send(peer, 9, bytes(reply))
                    if kind == 0x1B:
                        seq, inner = struct.unpack_from('<IB', body, len(body) - 5)
                        # Lose one ACK to exercise retransmit/dedup.
                        if (inner == 0x25 and not missed_ack and
                                (drop_ack_tag is None or struct.unpack_from('<I', body, 96)[0] == drop_ack_tag)):
                            missed_ack = True
                            missed_event = (peer, seq)
                        else:
                            send(peer, 0x0F, struct.pack('<I', seq))
                        if seq in seen[peer]:
                            if (peer, seq) == missed_event:
                                retransmitted = True
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
                       len([k for k, _ in records[peer] if k in watched]) < len(expected)):
                    pump(.1)
                    self.assertLess(time.monotonic(), deadline)
                actual = [(kind, body) for kind, body in records[peer] if kind in watched]
                self.assertEqual(actual, expected)
                kinds = [k for k, _ in records[peer]]
                if expected:
                    self.assertLess(kinds.index(0x2C), kinds.index(0x25))
                if drop_ack_tag is not None and peer is peers[0]:
                    deadline = time.monotonic() + 10
                    while not retransmitted:
                        pump(.1)
                        self.assertLess(time.monotonic(), deadline, 'gate was not retransmitted after ACK loss')
            self.assertEqual(missed_ack, bool(expected))
        finally:
            for peer in peers: peer.close()
            process.terminate()
            stdout, stderr = process.communicate(timeout=5)
            self.assertNotIn(b'Traceback', stderr)
