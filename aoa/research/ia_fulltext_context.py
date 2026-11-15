#!/usr/bin/env python3
"""Fetch the OCR text of every hit in <dir>/ia_fulltext_hits.json and extract
the passages about the game (+-600/900 chars around each "Ace of Angels" that
also has a game-related word nearby). Writes <dir>/ia_fulltext_passages.txt,
keeping only the sentences that name the game or Flying Rock (see trim_item),
and prints a summary with disc/demo/download words found near each mention.
Both names default to the files committed in data/ (--hits, --out change
them). OCR files are cached in <dir>/txt/; requests go through
aoa/research/http.py (paced, backs off on HTTP 429/5xx).

    python3 -I ia_fulltext_context.py data/
    python3 -I ia_fulltext_context.py --trim data/ia_fulltext_passages.txt

--trim applies the same sentence filter to an untrimmed contexts file in place
(run on an already trimmed file, it can drop bridging sentences).

Some scans only have ABBYY XML text, which this misses; re-read those via the
item's _djvu.txt (see CONTEXT.md, "full-text search").
"""
import json, sys, urllib.parse, gzip, re, os
from aoa import cli  # noqa: E402
from aoa.research.http import polite_get  # noqa: E402
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
def main(argv=None):
    ap = cli.parser(__doc__)
    ap.add_argument("dir", nargs="?", help="folder holding the hits file, e.g. data/")
    ap.add_argument("--hits", default=HITS, help="hits file name inside DIR (default: %(default)s)")
    ap.add_argument("--out", default=PASSAGES, help="passages file name inside DIR (default: %(default)s)")
    ap.add_argument("--trim", metavar="FILE", help="only re-apply the sentence filter to FILE, in place")
    a = ap.parse_args(argv)
    if a.trim:
        items = []
        for line in open(a.trim, encoding="utf-8"):
            if line.startswith("##### "): items.append((line[6:].rstrip("\n"), []))
            elif line.lstrip().startswith(">> "): items[-1][1].append(line.lstrip()[3:].rstrip("\n"))
        write_contexts(a.trim, items); return
    if not a.dir:
        ap.error("give the folder holding the hits file, or --trim FILE")
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
if __name__ == "__main__":
    sys.exit(cli.run(main))
