#!/usr/bin/env python3
"""Download the verified Ace of Angels builds from archive.org and check them.

    python3 -I fetch_known_builds.py builds/

Each file goes to builds/<version>/aoa-current.exe and is checked against the
MD5 recorded in CONTEXT.md. Nothing is executed. Already-present files with
the right hash are skipped. The output folder must be given explicitly; a
name starting with "-" is refused. Requests go through tools/polite_http.py
(paced, backs off on HTTP 429/5xx).
"""
import hashlib
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cli_util  # noqa: E402
from polite_http import polite_open  # noqa: E402

BUILDS = [
    ("v2.8.2_2002-03_CD-Action-06-2002", "96c852b07a7d55c7894dbdda624fa3db",
     "https://archive.org/download/cda_20260908/CDA%2006-2002.iso/"
     "%23dema%2Face%20of%20angels%2Faoa-current.exe"),
    ("v2.9.2_2004_FamilyGamePack3", "ddb6a3217a0987bdf0eedef7c19767af",
     "https://archive.org/download/family-game-pack-3-mmh-269/Family%20GamePack%203%20MMH269.iso/"
     "Games%2FAce%20of%20Angels%2Faoa-current.exe"),
]
MIRRORS = {  # same bytes, second upload of the disc
    "v2.9.2_2004_FamilyGamePack3":
    "https://archive.org/download/family_game_pack32004/family_game_pack3%282004%29.iso/"
    "Games%2FAce%20of%20Angels%2Faoa-current.exe",
}


def md5(path):
    h = hashlib.md5()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def fetch(url, dest):
    with polite_open(url, timeout=600) as r, open(dest + ".part", "wb") as f:
        while (b := r.read(1 << 20)):
            f.write(b)
    os.replace(dest + ".part", dest)


def main(argv=None):
    ap = cli_util.parser(__doc__)
    ap.add_argument("out_dir", type=cli_util.output_dir, help="folder to save the builds in, e.g. builds/")
    a = ap.parse_args(argv)
    ok = True
    for name, want, url in BUILDS:
        d = os.path.join(a.out_dir, name)
        os.makedirs(d, exist_ok=True)
        dest = os.path.join(d, "aoa-current.exe")
        if not (os.path.exists(dest) and md5(dest) == want):
            for u in (url, MIRRORS.get(name)):
                if not u:
                    continue
                try:
                    fetch(u, dest)
                    break
                except Exception as e:
                    print(f"  {name}: {e}; trying mirror" if u == url else f"  {name}: {e}")
        got = md5(dest) if os.path.exists(dest) else None
        status = "OK" if got == want else f"MISMATCH (got {got})"
        ok &= got == want
        print(f"{status:8}  {name}  {dest}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(cli_util.run(main))
