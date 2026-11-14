#!/usr/bin/env python3
"""Stream a raw 2352-byte-sector CD image (CloneCD .img) out of a RAR and write
a 2048-byte ISO, without unpacking the .img to disk. Needs `pip install libarchive-c`.

    python3 -I rar_img2iso.py disc.rar "Disc.img" disc.iso
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import cli_util  # noqa: E402
def main(argv=None):
    ap = cli_util.parser(__doc__)
    ap.add_argument("rar", help="RAR archive holding the image")
    ap.add_argument("want", help="path of the .img inside the archive")
    ap.add_argument("dst", help="ISO file to write")
    a = ap.parse_args(argv)
    try:
        import libarchive
    except ImportError:
        sys.exit("rar_img2iso: needs libarchive-c (pip install libarchive-c)")
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
if __name__ == "__main__":
    sys.exit(cli_util.run(main))
