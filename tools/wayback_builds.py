#!/usr/bin/env python3
"""List, and optionally download, every build the Wayback Machine saved from
Flying Rock's sites.

    # 1. every saved URL (site map) + the downloadable candidates
    python3 -I wayback_builds.py --out wb/

    # 2. same, then fetch the original bytes of each candidate
    python3 -I wayback_builds.py --out wb/ --download

    # offline: parse a CDX dump you saved yourself (output=json)
    python3 -I wayback_builds.py --out wb/ --cdx-file dump.json

Writes wb/all_urls.tsv (one row per unique URL+content) and wb/builds.tsv
(the installers/archives). Downloads go to wb/files/<timestamp>_<name> and get
an md5/sha256 line in wb/files/hashes.txt. Files are only saved, never run.

The `id_` form of a Wayback URL returns the archived bytes without the
Wayback toolbar or link rewriting -- that is what gets downloaded.
"""
import argparse
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

DOMAINS = ["aceofangels.com", "flyingrockllc.com", "flyingrock.com"]
CDX = "https://web.archive.org/cdx/search/cdx"
FIELDS = "timestamp,original,mimetype,statuscode,digest,length"
BUILD_EXT = re.compile(r"\.(exe|zip|msi|cab|rar|7z|ace|lzh|tgz|gz|sit|bin)$", re.I)
BUILD_MIME = re.compile(r"application/(x-)?(msdownload|msdos-program|dosexec|zip|"
                        r"zip-compressed|octet-stream|x-msi|rar|7z)", re.I)
UA = {"User-Agent": "aoa-preservation-research/1.0 (personal, polite; contact via repo)"}


def get(url, tries=6):
    delay = 5
    for n in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA),
                                        timeout=180) as r:
                return r.read(), r.headers.get_content_type()
        except urllib.error.HTTPError as e:
            if e.code not in (429, 502, 503, 504) or n == tries - 1:
                raise
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            if n == tries - 1:
                raise
        print(f"   retry in {delay}s: {url[:90]}", file=sys.stderr)
        time.sleep(delay)
        delay *= 2


def cdx_rows(domain):
    q = urllib.parse.urlencode({"url": domain, "matchType": "domain",
                                "output": "json", "fl": FIELDS})
    body, _ = get(f"{CDX}?{q}")
    rows = json.loads(body or b"[]")
    return rows[1:] if rows and rows[0][:2] == ["timestamp", "original"] else rows


def is_build(row):
    _ts, original, mime, status, _dg, _ln = row
    path = urllib.parse.urlsplit(original).path
    ok_status = status in ("200", "-", "")
    return ok_status and (BUILD_EXT.search(path) or BUILD_MIME.search(mime or ""))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", required=True)
    ap.add_argument("--domains", nargs="*", default=DOMAINS)
    ap.add_argument("--cdx-file", help="parse a saved CDX JSON dump instead of querying")
    ap.add_argument("--download", action="store_true")
    ap.add_argument("--pause", type=float, default=4.0, help="seconds between downloads")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)

    rows = []
    if a.cdx_file:
        data = json.load(open(a.cdx_file))
        rows = data[1:] if data and data[0][:2] == ["timestamp", "original"] else data
    else:
        for dom in a.domains:
            print(f"querying CDX for {dom} ...", file=sys.stderr)
            got = cdx_rows(dom)
            print(f"   {len(got)} captures", file=sys.stderr)
            rows += got
            time.sleep(a.pause)

    # One row per (URL, content digest): the earliest capture of each version.
    uniq = {}
    for r in sorted(rows):
        uniq.setdefault((r[1].lower(), r[4]), r)
    rows = sorted(uniq.values(), key=lambda r: (r[1].lower(), r[0]))

    with open(os.path.join(a.out, "all_urls.tsv"), "w") as f:
        f.write("\t".join(FIELDS.split(",")) + "\n")
        for r in rows:
            f.write("\t".join(r) + "\n")
    builds = [r for r in rows if is_build(r)]
    with open(os.path.join(a.out, "builds.tsv"), "w") as f:
        f.write("\t".join(FIELDS.split(",")) + "\twayback_url\n")
        for r in builds:
            f.write("\t".join(r) + f"\thttps://web.archive.org/web/{r[0]}id_/{r[1]}\n")
    print(f"{len(rows)} unique URL versions, {len(builds)} build candidates")
    for r in builds:
        print(f"  {r[0]}  {r[5]:>10}  {r[2]:<28}  {r[1]}")

    if not a.download:
        return
    fdir = os.path.join(a.out, "files")
    os.makedirs(fdir, exist_ok=True)
    with open(os.path.join(fdir, "hashes.txt"), "a") as hf:
        for r in builds:
            name = os.path.basename(urllib.parse.urlsplit(r[1]).path) or "index"
            name = re.sub(r"[^A-Za-z0-9._-]", "_", name)
            target = os.path.join(fdir, f"{r[0]}_{name}")
            if os.path.exists(target):
                continue
            try:
                body, ctype = get(f"https://web.archive.org/web/{r[0]}id_/{r[1]}")
            except Exception as e:
                print(f"  FAILED {r[1]}: {e}")
                continue
            with open(target, "wb") as f:
                f.write(body)
            note = ""
            if ctype == "text/html" or body[:2] != b"MZ" and name.lower().endswith(".exe"):
                note = "  (not a Windows executable -- probably an error page)"
            line = (f"{hashlib.md5(body).hexdigest()}  {hashlib.sha256(body).hexdigest()}"
                    f"  {len(body):>10}  {target}{note}")
            print(" ", line)
            hf.write(line + "\n")
            time.sleep(a.pause)


if __name__ == "__main__":
    main()
