"""Scripted pilots for filming: synthetic clients that fly fixed paths.

  python -I tools/reel/bot.py game/2.9.2/SCRTY.BIN pilots.json [--seconds 60]

pilots.json is a list of {"hull": NAME, "path": {...}}. Paths, in world
units and seconds:
  {"kind": "line", "start": [x, y, z], "velocity": [vx, vy, vz]}
  {"kind": "circle", "center": [x, y, z], "radius": r, "speed": s, "phase": deg}
  {"kind": "hold", "at": [x, y, z]}
A circle lies in the x/z plane. Each pilot logs in to the local relay like
the real client (UDP login, TCP server list, arena join), asks for its hull
with the fighter menu's 0xA0 request, then sends absolute position and
velocity (mask 0x41) 30 times a second. Orientation is not sent: what the
remote ship's nose does is up to the receiving client.

Local relay only (127.0.0.1). These are test pilots, not players.
"""
import argparse
import json
import math
import select
import socket
import struct
import sys
import time
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))
import aoanet  # noqa: E402
import aoapack  # noqa: E402

HOST = "127.0.0.1"
STATION, ARENA, TCP = 5033, 5031, 5034
RATE = 30


def login_request(name):
    """The client's 381-byte login (type 10), as in test_station_stub.request()."""
    payload = bytearray(381)
    payload[1:5] = (9).to_bytes(4, "little")
    payload[5:9] = (2).to_bytes(4, "little")
    payload[9:13] = (2).to_bytes(4, "little")
    payload[31:31 + len(name)] = name.encode("ascii")
    return bytes(payload)


def job_request(identity, job=5):
    header = bytearray(142)
    header[:12] = b"private-name"
    struct.pack_into("<I", header, 60, identity)
    header[128:130] = bytes([job, 0])
    return bytes(header)


def tcp_job(identity, job=5):
    with socket.create_connection((HOST, TCP), timeout=5) as client:
        client.sendall(job_request(identity, job))
        with client.makefile("rb") as stream:
            size = int.from_bytes(stream.read(4), "little")
            body = stream.read(size)
    return aoapack.decompress(body)[0] if size else b""


def hull_request(hull):
    """SendRequestCustomConfig, type 0xA0: u32 config 0, vessel[32], 0."""
    return struct.pack("<I", 0) + hull.encode("latin1").ljust(32, b"\0") + b"\0"


def path_state(path, t):
    """(position, velocity) at t seconds."""
    kind = path["kind"]
    if kind == "hold":
        return tuple(path["at"]), (0.0, 0.0, 0.0)
    if kind == "line":
        v = path["velocity"]
        return tuple(s + t * d for s, d in zip(path["start"], v)), tuple(v)
    if kind == "circle":
        cx, cy, cz = path["center"]
        r, speed = path["radius"], path["speed"]
        a = math.radians(path.get("phase", 0)) + speed * t / r
        # Counter-clockwise seen from +y; velocity is the tangent.
        return (cx + r * math.cos(a), cy, cz + r * math.sin(a)), (-speed * math.sin(a), 0.0, speed * math.cos(a))
    raise ValueError(f"unknown path kind {kind!r}")


def movement(slot, position, velocity):
    """Absolute position + velocity upload (0x1F, mask 0x41)."""
    return struct.pack("<HHI6f", 0x8000, slot, 0x41, *position, *velocity)


class Pilot:
    def __init__(self, key, name, hull, path):
        self.key, self.name, self.hull, self.path = key, name, hull, path
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind((HOST, 0))
        self.identity = self.slot = None
        self.loaded = self.hull_sent = False

    def send(self, port, kind, body):
        self.sock.sendto(aoanet.encode(kind, body, self.key), (HOST, port))

    def receive(self):
        wire, source = self.sock.recvfrom(1024)
        msg = aoanet.decode(wire, self.key)
        kind, body = msg["type"], msg["payload"]
        if kind == 0x1B and len(body) >= 5:
            self.sock.sendto(aoanet.encode(0x0F, body[-5:-1], self.key), source)
            kind, body = body[-1], body[:-5]
        if kind == 8:
            reply = bytearray(body)
            reply[6] = self.slot or 0
            self.sock.sendto(aoanet.encode(9, bytes(reply), self.key), source)
        elif kind == 0x26 and len(body) >= 0x46 + 0x7F and self.identity:
            # Only the pilot's own record carries its Station ID (load_player).
            if struct.unpack_from("<I", body, 0x46 + 0x7B)[0] == self.identity:
                self.slot = struct.unpack_from("<I", body, 0x28)[0] & 0xFFFF
        elif kind == 0x2C:
            self.loaded = True
        return kind, body

    def wait(self, predicate, timeout=10):
        deadline = time.monotonic() + timeout
        while not predicate():
            left = deadline - time.monotonic()
            if left <= 0:
                raise TimeoutError(f"{self.name}: no reply from the relay")
            if select.select([self.sock], [], [], min(left, 0.05))[0]:
                last = self.receive()
                if last[0] == 11 and self.identity is None:
                    self.ack = last[1]

    def login(self):
        self.ack = None
        self.send(STATION, 10, login_request(self.name))
        self.wait(lambda: self.ack is not None)
        self.identity = struct.unpack_from("<I", self.ack, 136)[0]
        tcp_job(self.identity)
        station_ack, self.ack = self.ack, None
        self.send(ARENA, 10, login_request(self.name)[:31] + station_ack[13:])
        self.wait(lambda: self.loaded and self.slot is not None, timeout=15)

    def pump(self):
        while select.select([self.sock], [], [], 0)[0]:
            self.receive()


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("key", type=Path, help="SCRTY.BIN")
    parser.add_argument("pilots", type=Path)
    parser.add_argument("--seconds", type=float, default=60)
    parser.add_argument("--delay", type=float, default=0, help="hold paths at t=0 for this long after login")
    args = parser.parse_args()
    key = args.key.read_bytes()
    spec = json.loads(args.pilots.read_text())
    pilots = [Pilot(key, f"Wing{i + 1}", p["hull"], p["path"]) for i, p in enumerate(spec)]
    for pilot in pilots:
        pilot.login()
        pilot.send(ARENA, 0xA0, hull_request(pilot.hull))
        print(f"{pilot.name}: slot {pilot.slot}, {pilot.hull}", flush=True)
    time.sleep(0.5)  # the relay answers 0xA0 by moving the pilot to its spawn
    start = time.monotonic() + args.delay
    end = start + args.seconds
    tick = 1 / RATE
    next_send = time.monotonic()
    while time.monotonic() < end:
        for pilot in pilots:
            pilot.pump()
        now = time.monotonic()
        if now >= next_send:
            t = max(0.0, now - start)
            for pilot in pilots:
                position, velocity = path_state(pilot.path, t)
                pilot.send(ARENA, 0x1F, movement(pilot.slot, position, velocity))
            next_send += tick
        time.sleep(0.002)
    for pilot in pilots:
        pilot.send(ARENA, 0x4E, b"\0")  # SendImQuitting


if __name__ == "__main__":
    main()
