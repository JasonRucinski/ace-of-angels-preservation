#!/usr/bin/env python3
"""Read the compiled-in version of an Ace of Angels client (AOACLIENT.EXE).

The client keeps major/minor/patch in three initialised .data globals and only
ever reads them, e.g. for "Entering Ace of Angels runtime client ver(%d.%d.%d)".
The bundled AOANOTES.TXT is not trustworthy -- the 2004 build's notes say
v2.3.0 while the binary is v2.9.2.

Method: find a version format string, find the `push imm32` of its address,
take the absolute-address loads (mov reg, [abs]) just before it, and read
those dwords from the file. No disassembler needed.

    python3 -I tools/aoa_version.py AOACLIENT.EXE
"""
import struct
import sys

from aoa import cli  # noqa: E402
from aoa.formats.pe import Image

FORMATS = [
    b"Entering Ace of Angels runtime client ver(%d.%d.%d)",
    b"Ace of Angels (v%d.%d.%d Beta)",
    b"Ace of Angels v%d.%d.%d",
]
# mov eax,[moffs32] is A1; mov r32,[disp32] is 8B with modrm 00 reg 101.
LOADS = {b"\xa1": 1, b"\x8b\x0d": 2, b"\x8b\x15": 2, b"\x8b\x1d": 2,
         b"\x8b\x35": 2, b"\x8b\x3d": 2}


def main(argv=None):
    ap = cli.parser(__doc__)
    ap.add_argument("client", help="the AOACLIENT.EXE to read")
    a = ap.parse_args(argv)
    d = open(a.client, "rb").read()
    image = Image(d)
    results = set()
    for fmt in FORMATS:
        soff = d.find(fmt)
        if soff < 0:
            continue
        sva = image.off_to_va(soff)
        push = b"\x68" + struct.pack("<I", sva)
        p = 0
        while (p := d.find(push, p)) >= 0:
            window = d[max(0, p - 64):p]
            addrs = []
            for k in range(len(window)):
                for op, n in LOADS.items():
                    if window[k:k + n] == op and k + n + 4 <= len(window):
                        addrs.append(struct.unpack_from("<I", window, k + n)[0])
            # The last three loads before the push are the arguments.
            cand = sorted(set(addrs[-3:]))
            if len(cand) == 3 and cand[1] - cand[0] == 4 and cand[2] - cand[1] == 4:
                o = image.va_to_off(cand[0])
                if o is not None:
                    v = struct.unpack_from("<III", d, o)
                    results.add(v)
                    print(f"{fmt.decode()!r} @ {sva:#x}: globals {cand[0]:#x}.. -> "
                          f"v{v[0]}.{v[1]}.{v[2]}")
            p += 1
    if not results:
        sys.exit("no version found (format strings or load pattern differ in this build)")
    if len(results) > 1:
        print("warning: references disagree:", sorted(results))


if __name__ == "__main__":
    sys.exit(cli.run(main))
