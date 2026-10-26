#!/usr/bin/env python3
"""List or extract the files packed inside an Ace of Angels Wise installer.

The Flying Rock installers are Wise "self-installing executables". Each payload
file sits behind an ordinary PK\\x03\\x04 local header followed by a raw-deflate
stream, so they can be pulled out as plain data without running anything.

    python3 -I wise_extract.py aoa-current.exe              # list entries
    python3 -I wise_extract.py aoa-current.exe out_dir/     # extract all

Never run the installer itself; it is untrusted, 20+ years old, and unneeded
for inspection.
"""
import os
import struct
import sys
import zlib


def entries(data):
    i = 0
    while (i := data.find(b"PK\x03\x04", i)) >= 0:
        try:
            _ver, _flag, meth, _t, _d, crc, csz, usz, fnl, exl = struct.unpack(
                "<HHHHHIIIHH", data[i + 4:i + 30])
            name = data[i + 30:i + 30 + fnl].decode("latin1")
            start = i + 30 + fnl + exl
        except struct.error:
            break
        if name and 0 < csz <= len(data) - start:
            yield i, name, meth, csz, usz, crc, start
        i += 4


def main():
    if len(sys.argv) not in (2, 3):
        sys.exit(__doc__)
    data = open(sys.argv[1], "rb").read()
    out = sys.argv[2] if len(sys.argv) == 3 else None
    if out:
        os.makedirs(out, exist_ok=True)
    seen = {}
    for off, name, meth, csz, usz, crc, start in entries(data):
        print(f"{off:#010x}  meth={meth}  {usz:>10}  {name}")
        if not out or meth != 8:
            continue
        try:
            raw = zlib.decompressobj(-15).decompress(data[start:start + csz])
        except zlib.error as e:
            print(f"    skipped: {e}")
            continue
        if zlib.crc32(raw) != crc:
            print("    warning: CRC mismatch")
        # Basename only: an entry name must never write outside out_dir.
        base = os.path.basename(name.replace("\\", "/")) or "unnamed"
        n = seen.get(base, 0)
        seen[base] = n + 1
        target = os.path.join(out, base if n == 0 else f"{base}.{n}")
        with open(target, "wb") as f:
            f.write(raw)


if __name__ == "__main__":
    main()
