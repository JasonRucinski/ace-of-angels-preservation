#!/usr/bin/env python3
"""Search inside archive.org disc images for files matching a pattern.

archive.org lists the contents of an ISO (or ZIP/RAR/7z) when you open
https://archive.org/download/<item>/<image>/ . This walks every such image in
the given items and prints entries whose path matches.

    python3 -I ia_disc_find.py cda_20260908 family_game_pack32004
    python3 -I ia_disc_find.py --pattern '(?i)aoa|angel' --ids-file ids.txt

It only *lists*; nothing is downloaded. A result of "N entries listed" with
no hits is a real negative only when N is the disc's file count. A RAR/7z
that wraps a raw .img/.bin/.mdf shows just that one file, so it was NOT
searched -- download it and use rar_img2iso.py / iso_stream_extract.py.
"""
import argparse
import html
import json
import re
import sys
import urllib.parse
import urllib.request

DEFAULT = r"(?i)ace.?of.?angel|aoa[-_ ]|aoaclient|flyingrock"
IMG = re.compile(r"\.(iso|zip|rar|7z)$", re.I)


def get(url, timeout=300):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (research)"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def search(ident, pat):
    meta = json.loads(get(f"https://archive.org/metadata/{ident}"))
    title = meta.get("metadata", {}).get("title")
    imgs = [f["name"] for f in meta.get("files", []) if IMG.search(f["name"])]
    print(f"{ident} | {title} | images: {imgs}")
    for im in imgs:
        url = f"https://archive.org/download/{ident}/{urllib.parse.quote(im)}/"
        try:
            page = get(url).decode("utf-8", "ignore")
        except Exception as e:
            print(f"   {im}: listing failed: {e}")
            continue
        names = [html.unescape(n) for n in
                 re.findall(r'<a href="//archive\.org/download/[^"]+">([^<]+)</a>', page)]
        for n in names:
            if pat.search(n):
                print(f"   HIT {n}\n       https://archive.org/download/{ident}/"
                      f"{urllib.parse.quote(im)}/{urllib.parse.quote(n, safe='')}")
        note = "" if len(names) > 5 else "  (probably a wrapped image: not searched)"
        print(f"   {im}: {len(names)} entries listed{note}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("ids", nargs="*")
    ap.add_argument("--ids-file")
    ap.add_argument("--pattern", default=DEFAULT)
    a = ap.parse_args()
    ids = list(a.ids)
    if a.ids_file:
        ids += [l.strip() for l in open(a.ids_file) if l.strip()]
    if not ids:
        sys.exit(__doc__)
    pat = re.compile(a.pattern)
    for i in ids:
        try:
            search(i, pat)
        except Exception as e:
            print(f"{i}: failed: {e}")


if __name__ == "__main__":
    main()
