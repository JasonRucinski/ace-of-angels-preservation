#!/usr/bin/env python3
"""List or extract the files packed inside an Ace of Angels Wise installer.

The Flying Rock installers are Wise "self-installing executables". Each payload
file sits behind an ordinary PK\\x03\\x04 local header followed by a raw-deflate
stream, so they can be pulled out as plain data without running anything.

    python3 -I wise_extract.py aoa-current.exe              # list entries
    python3 -I wise_extract.py aoa-current.exe out_dir/     # extract all

An entry whose CRC-32 does not match is not written and the run exits 1;
--force writes it anyway (with a warning).

Never run the installer itself; it is untrusted, 20+ years old, and unneeded
for inspection.
"""
import os
import struct
import sys
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cli_util  # noqa: E402


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


def main(argv=None):
    ap = cli_util.parser(__doc__)
    ap.add_argument("installer", help="Wise installer to read (never run)")
    ap.add_argument("out", nargs="?", help="folder to extract into (default: only list)")
    ap.add_argument("--force", action="store_true", help="write entries whose CRC does not match")
    a = ap.parse_args(argv)
    data = open(a.installer, "rb").read()
    out = a.out
    if out:
        os.makedirs(out, exist_ok=True)
    seen = {}
    bad_crc = 0
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
            if not a.force:
                print("    CRC mismatch: not written (--force writes it)")
                bad_crc += 1
                continue
            print("    warning: CRC mismatch")
        # Basename only: an entry name must never write outside out_dir.
        base = os.path.basename(name.replace("\\", "/")) or "unnamed"
        n = seen.get(base, 0)
        seen[base] = n + 1
        target = os.path.join(out, base if n == 0 else f"{base}.{n}")
        with open(target, "wb") as f:
            f.write(raw)
    if bad_crc:
        sys.exit(f"wise_extract: {bad_crc} entr{'y' if bad_crc == 1 else 'ies'} failed the CRC check")


if __name__ == "__main__":
    sys.exit(cli_util.run(main))
