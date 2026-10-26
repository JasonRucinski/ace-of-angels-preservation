# Ace of Angels research

Preservation research into *Ace of Angels*, Flying Rock Enterprises' online
space-combat sim (2000–2006): find every surviving build, the old universe
website, and any sign of a revival.

**Read `CONTEXT.md` first.** It holds the findings, links, hashes, what was
already searched, and the ordered next steps. Keep it current: when you
verify a build or rule a source out, update its tables in the same session.

## Rules

- Each download goes in its own new, empty directory under `builds/` or
  `wb/` (both git-ignored). Run Python on downloaded data with `python3 -I`,
  from outside that directory.
- A build counts as found only when it is downloaded, hashed and versioned.
  A listing or a magazine mention is a lead, not a build.
- A "no hits" from `tools/ia_disc_find.py` counts only when the disc's files
  were actually listed; record it in `data/disc_search.tsv` either way.
- Be gentle with archive.org and the Wayback Machine: pause between
  requests and back off on 429.
- Mark anything taken only from a search-engine summary as *(snippet)*.
- "Ace of Angels" is also the K-pop group AOA. Pair searches with
  "Flying Rock" or "space".
