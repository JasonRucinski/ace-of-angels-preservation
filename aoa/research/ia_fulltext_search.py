#!/usr/bin/env python3
"""Full-text search of archive.org's scanned books and magazines (OCR text).

Web search engines do not index this. Runs a fixed list of queries against
archive.org's full-text backend and writes <out>/ia_fulltext_hits.json (the
name committed in data/): one row per (item, file) with the queries that
matched. The output folder must already exist and be given explicitly; a
name starting with "-" is refused. Requests go through aoa/research/http.py
(paced, backs off on HTTP 429/5xx).

    python3 -I ia_fulltext_search.py data/        # then ia_fulltext_context.py data/

Edit `queries` below to change what is searched.
"""
import json, sys, urllib.parse, os
from aoa import cli  # noqa: E402
from aoa.research.http import polite_get  # noqa: E402
HITS = "ia_fulltext_hits.json"
queries = ['"ace of angels" "flying rock"', '"flying rock enterprises"', '"aceofangels.com"', '"aceofangels"',
           '"flyingrockllc"', '"ace of angels" beta', '"ace of angels" demo', '"ace of angels" space',
           '"ace of angels" simulator', '"flying rock" angels space']
def main(argv=None):
    ap = cli.parser(__doc__)
    ap.add_argument("out", type=cli.output_dir, help=f"existing folder to write {HITS} to, e.g. data/")
    ap.add_argument("--hits", default=HITS, help="output file name inside OUT (default: %(default)s)")
    a = ap.parse_args(argv)
    out = a.out
    if not os.path.isdir(out):
        sys.exit(f"ia_fulltext_search: output folder not found: {out}")
    hits = {}
    for q in queries:
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
if __name__ == "__main__":
    sys.exit(cli.run(main))
