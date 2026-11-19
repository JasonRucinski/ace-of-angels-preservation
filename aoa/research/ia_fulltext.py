#!/usr/bin/env python3
"""Full-text search of archive.org's scanned books and magazines (OCR text).

Web search engines do not index this. Two steps, both through
aoa/research/http.py (paced, backs off on HTTP 429/5xx):

    python -I tools/run.py aoa.research.ia_fulltext search data/
    python -I tools/run.py aoa.research.ia_fulltext context data/
    python -I tools/run.py aoa.research.ia_fulltext context --trim data/ia_fulltext_passages.txt

`search OUT` runs a fixed list of queries (QUERIES below) against
archive.org's full-text backend and writes OUT/ia_fulltext_hits.json (the
name committed in data/): one row per (item, file) with the queries that
matched. OUT must already exist and be given explicitly; a name starting
with "-" is refused.

`context DIR` fetches the OCR text of every hit in DIR/ia_fulltext_hits.json
and extracts the passages about the game (+-600/900 chars around each "Ace
of Angels" that also has a game-related word nearby). It writes
DIR/ia_fulltext_passages.txt, keeping only the sentences that name the game
or Flying Rock (see trim_item), and prints a summary with disc/demo/download
words found near each mention. Both names default to the files committed in
data/ (--hits, --out change them). OCR files are cached in DIR/txt/.
`--trim FILE` applies the same sentence filter to an untrimmed contexts file
in place (run on an already trimmed file, it can drop bridging sentences).

Some scans only have ABBYY XML text, which this misses; re-read those via the
item's _djvu.txt (see CONTEXT.md, "full-text search").

The older module names aoa.research.ia_fulltext_search and
aoa.research.ia_fulltext_context still run the two steps.
"""
import gzip
import json
import os
import re
import sys
import urllib.parse

from aoa import cli
from aoa.research.http import polite_get

HITS, PASSAGES = "ia_fulltext_hits.json", "ia_fulltext_passages.txt"
KEY = re.compile(r"(?i)ace\s*of\s*ang|aceofangel|flying\s*rock|flyingrock")
def trim_item(ctxs, gap=2, cap=400):
    """Cut one item's OCR windows down to the sentences naming the game, plus up to
    `gap` sentences between two such sentences (same article). OCR run-ons longer
    than `cap` keep 150/250 chars around the mention. Overlapping windows repeat
    sentences, often cut at the window edge, so a sentence already written for
    this item, or contained in a longer one, is dropped."""
    wins = []
    for c in ctxs:
        s = re.split(r"(?<=[.!?])\s+", c.strip())
        hit = [i for i, x in enumerate(s) if KEY.search(x)]
        keep = set(hit) | {j for a, b in zip(hit, hit[1:]) if b - a <= gap + 1 for j in range(a, b)}
        win = []
        for i in sorted(keep):
            x, m = s[i], KEY.search(s[i])
            if len(x) > cap and m:
                a, b = max(0, m.start() - 150), m.start() + 250
                x = x[a:b].join(("… " if a else "", " …" if b < len(x) else ""))
            win.append((i, x))
        wins.append(win)
    every = {x.strip("… ") for win in wins for _, x in win}
    out, seen = [], set()
    for win in wins:
        parts, prev = [], None
        for i, x in win:
            core = x.strip("… ")
            if core in seen or any(core != y and core in y for y in every): prev = None; continue
            seen.add(core)
            parts.append(("… " if parts and i != prev + 1 else "") + x); prev = i
        if parts: out.append(" ".join(parts))
    return out
def write_contexts(path, items):
    with open(path, "w", encoding="utf-8") as f:
        for head, ctxs in items:
            f.write(f"\n##### {head}\n")
            for c in trim_item(ctxs): f.write("  >> " + c + "\n")
DISC = re.compile(r"(?i)\b(cd|dvd|cover|coverdisc|heft-cd|płyt\w*|plyt\w*|lemez\w*|mellékl\w*|melleklet\w*|disque|cd-rom|"
                  r"demo\w*|béta|beta\w*|download\w*|letölt\w*|pobierz\w*|stáhn\w*|herunterlad\w*|télécharg\w*|baixar|"
                  r"install\w*|client|klient\w*|kliens\w*|ftp|http|www\.\S+)\b")
GAME = re.compile(r"(?i)flying\s*rock|space|kosmic|kosmicz|űr|vesmír|spatial|espacial|weltraum|raum|simul|szimul|naroch|sphere|"
                  r"aceofangels|massively|multiplayer|squad|fighter|myśliw|vadász")
def get(u):
    return polite_get(u, timeout=180)
def add_context(sub):
    ap = sub.add_parser("context", help="fetch the OCR text of each hit and write the passages")
    ap.add_argument("dir", nargs="?", help="folder holding the hits file, e.g. data/")
    ap.add_argument("--hits", default=HITS, help="hits file name inside DIR (default: %(default)s)")
    ap.add_argument("--out", default=PASSAGES, help="passages file name inside DIR (default: %(default)s)")
    ap.add_argument("--trim", metavar="FILE", help="only re-apply the sentence filter to FILE, in place")
    ap.set_defaults(run=context, error=ap.error)


def context(a):
    if a.trim:
        items = []
        for line in open(a.trim, encoding="utf-8"):
            if line.startswith("##### "): items.append((line[6:].rstrip("\n"), []))
            elif line.lstrip().startswith(">> "): items[-1][1].append(line.lstrip()[3:].rstrip("\n"))
        write_contexts(a.trim, items); return
    if not a.dir:
        a.error("give the folder holding the hits file, or --trim FILE")
    d = a.dir; hits = json.load(open(os.path.join(d, a.hits)))
    os.makedirs(os.path.join(d, "txt"), exist_ok=True)
    report = []
    for h in hits:
        ident, fn = h["identifier"], h["filename"]
        if not fn: continue
        local = os.path.join(d, "txt", (ident + "__" + fn).replace("/", "_"))
        if not os.path.exists(local):
            try: raw = get(f"https://archive.org/download/{urllib.parse.quote(ident)}/{urllib.parse.quote(fn)}")
            except Exception as e: report.append((ident, fn, h["title"], "FETCH-ERR " + str(e)[:60], [])); continue
            open(local, "wb").write(raw)
        raw = open(local, "rb").read()
        try: t = gzip.decompress(raw).decode("utf-8", "ignore")
        except OSError: t = raw.decode("utf-8", "ignore")
        flat = re.sub(r"\s+", " ", t)
        ctxs = []
        for m in re.finditer(r"(?i)ace\s*of\s*angel", flat):
            c = flat[max(0, m.start() - 600): m.start() + 900]
            if GAME.search(c): ctxs.append(c)
        report.append((ident, fn, h["title"], f"{len(ctxs)} game mentions", ctxs))
    write_contexts(os.path.join(d, a.out), [(f"{i} / {fn} | {t} | {s}", c) for i, fn, t, s, c in report])
    for ident, fn, title, status, ctxs in sorted(report):
        if not ctxs: continue
        words = sorted({w.lower() for c in ctxs for w in DISC.findall(c)})
        print(f"{ident} / {fn.replace('_hocr_searchtext.txt.gz','')} | {title[:45]} | {status} | {', '.join(words)[:200]}")
    print("files with no game mention:", sum(1 for r in report if not r[4]))
QUERIES = ['"ace of angels" "flying rock"', '"flying rock enterprises"', '"aceofangels.com"', '"aceofangels"',
           '"flyingrockllc"', '"ace of angels" beta', '"ace of angels" demo', '"ace of angels" space',
           '"ace of angels" simulator', '"flying rock" angels space']
def add_search(sub):
    ap = sub.add_parser("search", help="query archive.org and write the hits file")
    ap.add_argument("out", type=cli.output_dir, help=f"existing folder to write {HITS} to, e.g. data/")
    ap.add_argument("--hits", default=HITS, help="output file name inside OUT (default: %(default)s)")
    ap.set_defaults(run=search)


def search(a):
    out = a.out
    if not os.path.isdir(out):
        sys.exit(f"ia_fulltext search: output folder not found: {out}")
    hits = {}
    for q in QUERIES:
        for page in (1, 2, 3):
            u = ("https://archive.org/services/search/beta/page_production/?service_backend=fts&user_query="
                 + urllib.parse.quote(q) + f"&hits_per_page=100&page={page}")
            try: j = json.loads(polite_get(u, timeout=120))
            except Exception as e: print("ERR", q, e); break
            hh = j["response"]["body"]["hits"]
            for h in hh["hits"]:
                f = h["fields"]; key = (f["identifier"], f.get("filename"))
                hits.setdefault(key, {"title": f.get("title"), "date": f.get("date") or f.get("publicdate"), "queries": set()})["queries"].add(q)
            print(f"{q!r} page {page}: total {hh.get('total')}, got {len(hh['hits'])}")
            if len(hh["hits"]) < 100: break
    print(len(hits), "unique files")
    with open(os.path.join(out, a.hits), "w") as f:
        json.dump([{"identifier": k[0], "filename": k[1], **{**v, "queries": sorted(v["queries"])}} for k, v in hits.items()],
                  f, indent=1)


def main(argv=None):
    ap = cli.parser(__doc__)
    sub = ap.add_subparsers(dest="command", required=True, metavar="{search,context}")
    add_search(sub)
    add_context(sub)
    a = ap.parse_args(argv)
    return a.run(a)


if __name__ == "__main__":
    sys.exit(cli.run(main))
