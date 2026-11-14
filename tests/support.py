"""Helpers several server suites share: synthetic client packets and replies.

Standard library and aoa only, so every game-free suite can import it.
"""
import socket
import struct
import time
from collections import deque

from aoa.formats import aoapack
from aoa.protocol import codec


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
