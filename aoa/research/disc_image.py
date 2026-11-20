#!/usr/bin/env python3
"""Get files out of disc images without unpacking them to disk.

    7z e -so dvd.7z image.mdf | python -I tools/run.py aoa.research.disc_image iso '(?i)angel|aoa' outdir
    python -I tools/run.py aoa.research.disc_image rar disc.rar "Disc.img" disc.iso

`iso PATTERN OUT` streams an ISO9660 image from stdin and saves only the
files whose path matches the regex. It reads the first HEAD bytes to parse
the directory tree (Joliet names when present), then copies target extents
as the stream passes them. Never seeks.

`rar RAR ENTRY OUT.iso` streams a raw 2352-byte-sector CD image (CloneCD
.img) out of a RAR and writes a 2048-byte ISO, without unpacking the .img
to disk. Needs `pip install libarchive-c` (requirements-research.txt).

The older module names aoa.research.iso_stream_extract and
aoa.research.rar_img2iso still run the two commands.
"""
import os
import re
import struct
import sys

from aoa import cli

HEAD = 96 * 1024 * 1024
SS = 2048
def add_iso(sub):
    ap = sub.add_parser("iso", help="stream an ISO from stdin, save the matching files")
    ap.add_argument("pattern", help="regex matched against each file's path in the image")
    ap.add_argument("out", type=cli.output_dir, help="folder to write matching files to")
    ap.set_defaults(run=extract_iso)


def extract_iso(a):
    pat, out = re.compile(a.pattern), a.out
    inp = sys.stdin.buffer
    head = bytearray()
    while len(head) < HEAD and (chunk := inp.read(1 << 20)):
        head += chunk
    def sector(n): return bytes(head[n * SS:(n + 1) * SS])
    # find descriptors
    pvd = joliet = None
    for n in range(16, 40):
        s = sector(n)
        if s[1:6] != b"CD001": break
        if s[0] == 1 and pvd is None: pvd = s
        if s[0] == 2 and s[88:91] in (b"%/@", b"%/C", b"%/E"): joliet = s
        if s[0] == 255: break
    vd = joliet or pvd
    if vd is None: sys.exit("no ISO9660 volume descriptor (raw sectors or UDF-only?)")
    enc = "utf-16-be" if vd is joliet else "latin1"
    print("using", "Joliet" if vd is joliet else "primary", "names")
    def records(lba, size):
        data = b"".join(sector(lba + i) for i in range((size + SS - 1) // SS))
        i = 0
        while i < len(data):
            ln = data[i]
            if ln == 0: i = (i // SS + 1) * SS; continue
            r = data[i:i + ln]; i += ln
            ext, sz, flags, nl = struct.unpack_from("<I", r, 2)[0], struct.unpack_from("<I", r, 10)[0], r[25], r[32]
            name = r[33:33 + nl]
            if name in (b"\x00", b"\x01"): continue
            yield name.decode(enc, "ignore").split(";")[0], ext, sz, bool(flags & 2)
    root = vd[156:156 + 34]
    targets, stack, ndirs = [], [("", struct.unpack_from("<I", root, 2)[0], struct.unpack_from("<I", root, 10)[0])], 0
    while stack:
        path, lba, size = stack.pop()
        if (lba + size // SS + 1) * SS > len(head):
            print("WARNING directory beyond head buffer:", path); continue
        ndirs += 1
        for name, ext, sz, isdir in records(lba, size):
            p = f"{path}/{name}"
            if isdir: stack.append((p, ext, sz))
            elif pat.search(p): targets.append((ext, sz, p))
    print(f"{ndirs} directories read, {len(targets)} matching files")
    for ext, sz, p in sorted(targets): print(f"  lba {ext:>8}  {sz:>11}  {p}")
    os.makedirs(out, exist_ok=True)
    opened = {}
    pos = 0  # byte offset of start of `buf` in the image
    buf = bytes(head); head = None
    def handle(buf, pos):
        end = pos + len(buf)
        for ext, sz, p in targets:
            a, b = ext * SS, ext * SS + sz
            lo, hi = max(a, pos), min(b, end)
            if lo < hi:
                f = opened.get(p) or opened.setdefault(p, open(os.path.join(out, p.strip("/").replace("/", "__")), "wb"))
                f.seek(lo - a); f.write(buf[lo - pos:hi - pos])
    handle(buf, pos); pos += len(buf)
    last = max((e * SS + s for e, s, _ in targets), default=0)
    while pos < last and (chunk := inp.read(8 << 20)):
        handle(chunk, pos); pos += len(chunk)
    for f in opened.values(): f.close()
    print("done at byte", pos)
def add_rar(sub):
    ap = sub.add_parser("rar", help="raw CD .img inside a RAR to an ISO (needs libarchive-c)")
    ap.add_argument("rar", help="RAR archive holding the image")
    ap.add_argument("want", help="path of the .img inside the archive")
    ap.add_argument("dst", help="ISO file to write")
    ap.set_defaults(run=rar_to_iso)


def rar_to_iso(a):
    try:
        import libarchive
    except ImportError:
        sys.exit("disc_image rar: needs libarchive-c (pip install libarchive-c)")
    rar, want, dst = a.rar, a.want, a.dst
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


def main(argv=None):
    ap = cli.parser(__doc__)
    sub = ap.add_subparsers(dest="command", required=True, metavar="{iso,rar}")
    add_iso(sub)
    add_rar(sub)
    a = ap.parse_args(argv)
    return a.run(a)


if __name__ == "__main__":
    sys.exit(cli.run(main))
