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
searched -- download it and use `tools/run.py aoa.research.disc_image rar|iso`.

--log data/disc_search.tsv appends one row per item to that table, as
CLAUDE.md asks for every search: the item, its title, a status and the
listed entry count of each image. The status is "listing hit" when an entry
matched (a lead, not a found build), "searched" when every image was listed
with no hit, and "NOT searched" when an image was not really listed (a
wrapped image, or the listing failed). Existing rows are never changed.

Requests go through aoa/research/http.py (paced, backs off on HTTP 429/5xx).
"""
import datetime
import html
import json
import os
import re
import sys
import urllib.parse

from aoa import cli  # noqa: E402
from aoa.research.http import polite_get  # noqa: E402

DEFAULT = r"(?i)ace.?of.?angel|aoa[-_ ]|aoaclient|flyingrock"
IMG = re.compile(r"\.(iso|zip|rar|7z)$", re.I)


def get(url, timeout=300):
    return polite_get(url, timeout=timeout)


def search(ident, pat, get=get):
    """List every image of one item, print the hits; returns the summary for --log."""
    meta = json.loads(get(f"https://archive.org/metadata/{ident}"))
    title = meta.get("metadata", {}).get("title")
    imgs = [f["name"] for f in meta.get("files", []) if IMG.search(f["name"])]
    print(f"{ident} | {title} | images: {imgs}")
    summary = {"ident": ident, "title": title, "images": []}
    for im in imgs:
        url = f"https://archive.org/download/{ident}/{urllib.parse.quote(im)}/"
        try:
            page = get(url).decode("utf-8", "ignore")
        except Exception as e:
            print(f"   {im}: listing failed: {e}")
            summary["images"].append({"image": im, "listed": None, "hits": [], "error": str(e)[:80]})
            continue
        names = [html.unescape(n) for n in
                 re.findall(r'<a href="//archive\.org/download/[^"]+">([^<]+)</a>', page)]
        hits = []
        for n in names:
            if pat.search(n):
                hits.append(n)
                print(f"   HIT {n}\n       https://archive.org/download/{ident}/"
                      f"{urllib.parse.quote(im)}/{urllib.parse.quote(n, safe='')}")
        note = "" if len(names) > 5 else "  (probably a wrapped image: not searched)"
        print(f"   {im}: {len(names)} entries listed{note}")
        summary["images"].append({"image": im, "listed": len(names), "hits": hits})
    return summary


def log_row(summary, today=None):
    """The data/disc_search.tsv row (item, title, status, result) for one search() summary."""
    images = summary["images"]
    parts = []
    for i in images:
        if i["listed"] is None:
            parts.append(f"{i['image']}: listing failed ({i['error']})")
        else:
            wrapped = "; wrapped image, not searched" if i["listed"] <= 5 else ""
            hits = f"; hits: {', '.join(i['hits'])}" if i["hits"] else ""
            parts.append(f"{i['image']}: {i['listed']} entries listed{hits}{wrapped}")
    if any(i["hits"] for i in images):
        status = "listing hit"
    elif images and all(i["listed"] is not None and i["listed"] > 5 for i in images):
        status = "searched"
    else:
        status = "NOT searched"
    result = "; ".join(parts) if parts else "no disc images in the item"
    if status == "searched":
        result = f"none ({result})"
    today = today or datetime.date.today().isoformat()
    fields = (summary["ident"], summary["title"], status, f"{result} [ia_disc_find, {today}]")
    return "\t".join(str(x or "").replace("\t", " ").replace("\n", " ") for x in fields)


def append_log(path, row):
    """Append one row to the table; adds a missing newline at the end of the file first."""
    with open(path, "rb") as f:
        size = f.seek(0, 2)
        ends = size == 0 or (f.seek(size - 1) is not None and f.read(1) == b"\n")
    with open(path, "a", encoding="utf-8", newline="\n") as f:
        f.write(("" if ends else "\n") + row + "\n")


def main(argv=None):
    ap = cli.parser(__doc__)
    ap.add_argument("ids", nargs="*", help="archive.org item identifiers")
    ap.add_argument("--ids-file", help="file with one identifier per line")
    ap.add_argument("--pattern", default=DEFAULT, help="regex for entry paths (default: %(default)s)")
    ap.add_argument("--log", metavar="TSV", help="append the result of each item to this existing table, "
                                                 "e.g. data/disc_search.tsv")
    a = ap.parse_args(argv)
    ids = list(a.ids)
    if a.ids_file:
        ids += [l.strip() for l in open(a.ids_file) if l.strip()]
    if not ids:
        sys.exit(__doc__)
    if a.log and not os.path.isfile(a.log):
        sys.exit(f"ia_disc_find: log table not found: {a.log}")
    pat = re.compile(a.pattern)
    for i in ids:
        try:
            summary = search(i, pat)
        except Exception as e:
            print(f"{i}: failed: {e}")
            summary = {"ident": i, "title": None, "images": [{"image": "metadata", "listed": None,
                                                              "hits": [], "error": str(e)[:80]}]}
        if a.log:
            append_log(a.log, log_row(summary))


if __name__ == "__main__":
    sys.exit(cli.run(main))
