"""Read and write the running 2.9.2 client's memory for scripted filming.

  python -I tools/reel/client_mem.py camera cockpit|chase|orbit
  python -I tools/reel/client_mem.py state
  python -I tools/reel/client_mem.py velocity VX VY VZ

Camera modes patch the running process only (never the file on disk): the
F2/F4 toggle-bit reads in the third-person camera's cave A (v2 and later), `and al,1`
(24 01), become `mov al,1` (B0 01). Offsets in aoa/live/addresses_292.py;
process access through aoa/live/procmem.py, which checks the build first.
"""
import argparse
import json
import struct
import sys
import time

from aoa.live import procmem
from aoa.live.addresses_292 import PLAYER_STRIDE as STRIDE, PLAYERS, WORLD
from aoa.reel import window  # noqa: E402

F4_READ, F2_READ = 0x58BC1B, 0x58BC3E   # `and al,1` after GetKeyState(VK_F4 / VK_F2)
AND_AL_1, MOV_AL_1 = b"\x24\x01", b"\xB0\x01"
ACCESS = procmem.VM_OPERATION | procmem.VM_READ | procmem.VM_WRITE | procmem.QUERY_INFORMATION


class Client(procmem.Process):
    def __init__(self, pid=None):
        super().__init__(pid or window.client_pids()[0], access=ACCESS)

    def camera(self, mode):
        """cockpit, chase (F2 forced on) or orbit (F4 forced on)."""
        want = {"cockpit": (AND_AL_1, AND_AL_1), "chase": (MOV_AL_1, AND_AL_1),
                "orbit": (AND_AL_1, MOV_AL_1)}[mode]
        for addr, data in zip((F2_READ, F4_READ), want):
            if self.read(addr, 2) not in (AND_AL_1, MOV_AL_1):
                raise ValueError(f"unexpected bytes at {addr:#x}; is this third-person-camera-v2 or later?")
            self.write(addr, data, code=True)

    def player(self, slot=0):
        world = struct.unpack("<I", self.read(WORLD, 4))[0]
        if not world:
            return None
        return world + PLAYERS + slot * STRIDE

    def state(self):
        p = self.player()
        raw = self.read(p, STRIDE)
        pointer = struct.unpack_from("<I", raw, 0x19C)[0]
        return {"active": raw[0x243], "position": struct.unpack_from("<3f", raw, 0x30),
                "velocity": struct.unpack_from("<3f", raw, 0x54),
                "max_velocity": struct.unpack_from("<H", raw, 0x10C)[0],
                "matrix": struct.unpack("<16f", self.read(pointer + 0x7C, 64)) if pointer else None}

    def set_velocity(self, v):
        self.write(self.player() + 0x54, struct.pack("<3f", *v))

    def set_position(self, pos):
        p = self.player()
        self.write(p + 0x30, struct.pack("<3f", *pos))
        self.write(p + 0x70, struct.pack("<3f", *pos))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="action", required=True)
    p = sub.add_parser("camera")
    p.add_argument("mode", choices=("cockpit", "chase", "orbit"))
    sub.add_parser("state")
    p = sub.add_parser("velocity")
    p.add_argument("v", type=float, nargs=3)
    p.add_argument("--hold", type=float, default=0, help="keep rewriting it for this many seconds")
    args = parser.parse_args(argv)
    if sys.platform != "win32":
        sys.exit("client_mem: needs Windows")
    c = Client()
    try:
        if args.action == "camera":
            c.camera(args.mode)
        elif args.action == "state":
            print(json.dumps(c.state()))
        else:
            end = time.monotonic() + args.hold
            while True:
                c.set_velocity(args.v)
                if time.monotonic() >= end:
                    break
                time.sleep(0.005)
    finally:
        c.close()


if __name__ == "__main__":
    main()
