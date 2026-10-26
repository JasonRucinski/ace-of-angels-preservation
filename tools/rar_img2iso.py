#!/usr/bin/env python3
"""Stream a raw 2352-byte-sector CD image (CloneCD .img) out of a RAR and write
a 2048-byte ISO, without unpacking the .img to disk. Needs `pip install libarchive-c`.

    python3 -I rar_img2iso.py disc.rar "Disc.img" disc.iso
"""
import sys, libarchive
rar, want, dst = sys.argv[1], sys.argv[2], sys.argv[3]
with libarchive.file_reader(rar) as arc, open(dst, "wb") as o:
    for e in arc:
        if e.pathname != want: continue
        buf = b""; start = None; n = 0
        for blk in e.get_blocks():
            buf += blk
            while len(buf) >= 2352:
                s, buf = buf[:2352], buf[2352:]
                if start is None: start = {1: 16, 2: 24}[s[15]]; print("mode", s[15])
                o.write(s[start:start + 2048]); n += 1
        print("sectors", n); break
