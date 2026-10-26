#!/usr/bin/env python3
"""Stream an ISO9660 image from stdin; save only files whose path matches a regex.

    7z e -so dvd.7z image.mdf | python3 -I iso_stream_extract.py '(?i)angel|aoa' outdir

Reads the first HEAD bytes to parse the directory tree (Joliet names when
present), then copies target extents as the stream passes them. Never seeks.
"""
import sys, os, re, struct
pat, out = re.compile(sys.argv[1]), sys.argv[2]
HEAD = 96 * 1024 * 1024
SS = 2048
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
