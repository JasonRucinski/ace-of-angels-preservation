#!/usr/bin/env python3
"""List, and optionally download, every build the Wayback Machine saved from
Flying Rock's sites.

    # 1. every saved URL (site map) + the downloadable candidates
    python3 -I tools/wayback_builds.py --out wb/

    # 2. same, then fetch the original bytes of each candidate
    python3 -I tools/wayback_builds.py --out wb/ --download

    # offline: parse a CDX dump you saved yourself (output=json)
    python3 -I tools/wayback_builds.py --out wb/ --cdx-file dump.json

Writes wb/all_urls.tsv (one row per unique URL+content) and wb/builds.tsv
(the installers/archives). Downloads go to wb/files/<timestamp>_<name> and get
an md5/sha256 line in wb/files/hashes.txt. Files are only saved, never run.

The `id_` form of a Wayback URL returns the archived bytes without the
Wayback toolbar or link rewriting -- that is what gets downloaded.

`cdx_query` and `cdx_rows` are the one CDX helper of the research tools;
`tools/restore_web_archive.py cdx` uses them to write the index files it
imports.

Requests go through aoa/research/http.py: at least --pause seconds apart,
with backoff on HTTP 429/5xx.
"""
import hashlib
import json
import os
import re
import sys
import urllib.parse

from aoa import cli  # noqa: E402
from aoa.research import http  # noqa: E402

DOMAINS = ["aceofangels.com", "flyingrockllc.com", "flyingrock.com"]
CDX = "https://web.archive.org/cdx/search/cdx"
FIELDS = "timestamp,original,mimetype,statuscode,digest,length"
BUILD_EXT = re.compile(r"\.(exe|zip|msi|cab|rar|7z|ace|lzh|tgz|gz|sit|bin)$", re.I)
BUILD_MIME = re.compile(r"application/(x-)?(msdownload|msdos-program|dosexec|zip|"
                        r"zip-compressed|octet-stream|x-msi|rar|7z)", re.I)
HTTP = http.Polite(min_interval=4.0)


def get(url, http=None):
    with (http or HTTP).open(url, timeout=180) as r:
        return r.read(), r.headers.get_content_type()


def without_header(rows):
    """CDX JSON rows without the leading field-name row, if it has one."""
    return rows[1:] if rows and rows[0][:2] == ["timestamp", "original"] else rows


def cdx_query(url, match_type="domain", fields=FIELDS, filters=(), collapse=None, http=None):
    """The raw CDX JSON answer for url (field-name row first), through aoa/research/http.py."""
    params = [("url", url), ("matchType", match_type), ("output", "json"), ("fl", fields)]
    params += [("filter", f) for f in filters]
    if collapse:
        params.append(("collapse", collapse))
    body, _ = get(f"{CDX}?{urllib.parse.urlencode(params)}", http)
    return json.loads(body or b"[]")


def cdx_rows(domain, http=None):
    return without_header(cdx_query(domain, http=http))


def is_build(row):
    _ts, original, mime, status, _dg, _ln = row
    path = urllib.parse.urlsplit(original).path
    ok_status = status in ("200", "-", "")
    return ok_status and (BUILD_EXT.search(path) or BUILD_MIME.search(mime or ""))


def main(argv=None):
    ap = cli.parser(__doc__)
    ap.add_argument("--out", required=True, type=cli.output_dir, help="folder for the listings and downloads")
    ap.add_argument("--domains", nargs="*", default=DOMAINS)
    ap.add_argument("--cdx-file", help="parse a saved CDX JSON dump instead of querying")
    ap.add_argument("--download", action="store_true")
    ap.add_argument("--pause", type=float, default=4.0, help="minimum seconds between requests to one host")
    a = ap.parse_args(argv)
    HTTP.min_interval = max(1.0, a.pause)
    os.makedirs(a.out, exist_ok=True)

    rows = []
    if a.cdx_file:
        rows = without_header(json.load(open(a.cdx_file)))
    else:
        for dom in a.domains:
            print(f"querying CDX for {dom} ...", file=sys.stderr)
            got = cdx_rows(dom)
            print(f"   {len(got)} captures", file=sys.stderr)
            rows += got

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


if __name__ == "__main__":
    sys.exit(cli.run(main))
