#!/usr/bin/env python3
"""Full-text search of archive.org's scanned books and magazines (OCR text).

Web search engines do not index this. Runs a fixed list of queries against
archive.org's full-text backend and writes <out>/hits.json: one row per
(item, file) with the queries that matched.

    python3 -I ia_fulltext_search.py data/        # then ia_fulltext_context.py data/

Edit `queries` below to change what is searched.
"""
import json, sys, urllib.parse, urllib.request, time, gzip, re, os
out = sys.argv[1]
queries = ['"ace of angels" "flying rock"', '"flying rock enterprises"', '"aceofangels.com"', '"aceofangels"',
           '"flyingrockllc"', '"ace of angels" beta', '"ace of angels" demo', '"ace of angels" space',
           '"ace of angels" simulator', '"flying rock" angels space']
def get(u):
    req = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=120) as r: return r.read()
hits = {}
for q in queries:
    for page in (1, 2, 3):
        u = ("https://archive.org/services/search/beta/page_production/?service_backend=fts&user_query="
             + urllib.parse.quote(q) + f"&hits_per_page=100&page={page}")
        try: j = json.loads(get(u))
        except Exception as e: print("ERR", q, e); break
        hh = j["response"]["body"]["hits"]
        for h in hh["hits"]:
            f = h["fields"]; key = (f["identifier"], f.get("filename"))
            hits.setdefault(key, {"title": f.get("title"), "date": f.get("date") or f.get("publicdate"), "queries": set()})["queries"].add(q)
        print(f"{q!r} page {page}: total {hh.get('total')}, got {len(hh['hits'])}")
        if len(hh["hits"]) < 100: break
        time.sleep(1)
print(len(hits), "unique files")
json.dump([{"identifier": k[0], "filename": k[1], **{**v, "queries": sorted(v["queries"])}} for k, v in hits.items()],
          open(os.path.join(out, "hits.json"), "w"), indent=1)
