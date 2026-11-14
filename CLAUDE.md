# Ace of Angels preservation

Preservation of *Ace of Angels*, Flying Rock Enterprises' online
space-combat sim (2000–2006). The repository has four parts:

- **Archive research**: find every surviving build, the old universe
  website, and any sign of a revival. **Read `CONTEXT.md` first** for this
  work. It holds the findings, links, hashes, what was already searched, and
  the ordered next steps. Keep it current: when you verify a build or rule a
  source out, update its tables in the same session.
- **Client patches** (`tools/prepare_client.py` and the patch modules): fixes
  and additions for the 2.9.2 client, reversible and hash-checked.
- **The stand-in host** (`tools/station_stub.py`, the host window, the
  Linux host in `tools/dedicated_host.py` and `deploy/linux/`).
- **Asset and analysis tools**, indexed in `tools/README.md`.

What is verified and what is not: `docs/STATUS.md`. House rules:
`CONTRIBUTING.md`. Docs index: `docs/README.md`.

## Rules

- Each download goes in its own new, empty directory under `builds/` or
  `wb/` (both git-ignored). Run Python on downloaded data with `python3 -I`,
  from outside that directory.
- A build counts as found only when it is downloaded, hashed and versioned.
  A listing or a magazine mention is a lead, not a build.
- A "no hits" from `tools/ia_disc_find.py` counts only when the disc's files
  were actually listed; record it in `data/disc_search.tsv` either way.
- Be gentle with archive.org and the Wayback Machine: pause between
  requests and back off on 429. All archive access goes through
  `aoa/research/http.py`; do not add another fetch path.
- Mark anything taken only from a search-engine summary as *(snippet)*.
- "Ace of Angels" is also the K-pop group AOA. Pair searches with
  "Flying Rock" or "space".
- Never run a tool you have not read. Some act on their arguments at once
  (download, query archive.org, rewrite a game executable).
- Tools write to the ignored `work/` folder. An audit replaces a committed
  file under `evidence/` only when given `--evidence PATH`.
- Never commit game files, and never link docs into `builds/`, `game/`,
  `originals/`, `wb/` or `work/`.
- When a change makes a row of `docs/STATUS.md` untrue, update it in the
  same commit. Keep "untested" visible.
