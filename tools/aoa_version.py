#!/usr/bin/env python3
"""Read the compiled-in version of an Ace of Angels client (AOACLIENT.EXE).

The client keeps major/minor/patch in three initialised .data globals and only
ever reads them, e.g. for "Entering Ace of Angels runtime client ver(%d.%d.%d)".
The bundled AOANOTES.TXT is not trustworthy -- the 2004 build's notes say
v2.3.0 while the binary is v2.9.2.

Method: find a version format string, find the `push imm32` of its address,
take the absolute-address loads (mov reg, [abs]) just before it, and read
those dwords from the file. No disassembler needed.

    python3 -I aoa_version.py AOACLIENT.EXE
"""
import struct
import sys

FORMATS = [
    b"Entering Ace of Angels runtime client ver(%d.%d.%d)",
    b"Ace of Angels (v%d.%d.%d Beta)",
    b"Ace of Angels v%d.%d.%d",
]
# mov eax,[moffs32] is A1; mov r32,[disp32] is 8B with modrm 00 reg 101.
LOADS = {b"\xa1": 1, b"\x8b\x0d": 2, b"\x8b\x15": 2, b"\x8b\x1d": 2,
         b"\x8b\x35": 2, b"\x8b\x3d": 2}


def sections(d):
    pe = struct.unpack_from("<I", d, 0x3C)[0]
    nsec = struct.unpack_from("<H", d, pe + 6)[0]
    optsz = struct.unpack_from("<H", d, pe + 20)[0]
    base = struct.unpack_from("<I", d, pe + 24 + 28)[0]
    out = []
    for k in range(nsec):
        o = pe + 24 + optsz + 40 * k
        vs, va, rs, ra = struct.unpack_from("<IIII", d, o + 8)
        out.append((va, max(vs, rs), ra, rs))
    return base, out


def off_to_va(base, secs, off):
    for va, _vs, ra, rs in secs:
        if ra <= off < ra + rs:
            return base + va + off - ra
    return None


def va_to_off(base, secs, v):
    for va, vs, ra, rs in secs:
        if base + va <= v < base + va + min(vs, rs):
            return ra + v - base - va
    return None


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    d = open(sys.argv[1], "rb").read()
    base, secs = sections(d)
    results = set()
    for fmt in FORMATS:
        soff = d.find(fmt)
        if soff < 0:
            continue
        sva = off_to_va(base, secs, soff)
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
                o = va_to_off(base, secs, cand[0])
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
    main()
