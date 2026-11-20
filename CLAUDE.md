# Ace of Angels preservation

Preservation of *Ace of Angels*, Flying Rock Enterprises' online
space-combat sim (2000–2006). The repository has four parts:

- **Archive research**: find every surviving build, the old universe
  website, and any sign of a revival. **Read `CONTEXT.md` first** for this
  work. It holds the findings, links, hashes, what was already searched, and
  the ordered next steps. Keep it current: when you verify a build or rule a
  source out, update its tables in the same session.
- **Client patches** (`tools/prepare_client.py` and `aoa/client/patches/`):
  fixes and additions for the 2.9.2 client, reversible and hash-checked.
- **The stand-in host** (`aoa/host/`: `tools/station_stub.py`, the host
  window, the headless host `tools/aoa_host.py` and `deploy/linux/`).
- **Asset and analysis tools**, indexed in `docs/reference/tools.md`.

Where to read: what is verified and what is not, `docs/STATUS.md`; the
house rules, the design rules, how to run the tests and where each kind of
doc goes, `CONTRIBUTING.md` (follow it; it is not repeated here); the
reverse-engineering history, `docs/research/` (`log.md` by date,
`findings.md` by section); every doc by reader, `docs/README.md`.

## Rules

- Each download goes in its own new, empty directory under `builds/` or
  `wb/` (both git-ignored). Run Python on downloaded data with `python3 -I`,
  from outside that directory.
- A build counts as found only when it is downloaded, hashed and versioned.
  A listing or a magazine mention is a lead, not a build.
- A "no hits" from `tools/ia_disc_find.py` counts only when the disc's files
  were actually listed; record it in `data/disc_search.tsv` either way
  (`--log data/disc_search.tsv` appends the row).
- Be gentle with archive.org and the Wayback Machine: pause between
  requests and back off on 429. All archive access goes through
  `aoa/research/http.py`; do not add another fetch path.
- Mark anything taken only from a search-engine summary as *(snippet)*.
- "Ace of Angels" is also the K-pop group AOA. Pair searches with
  "Flying Rock" or "space".
- Never run a tool you have not read. Some act on their arguments at once
  (download, query archive.org, rewrite a game executable). Never run an
  original installer.
- Tools write to the ignored `work/` folder. An audit replaces a committed
  file under `evidence/` only when given `--evidence PATH`.
- Never commit game files, and never link docs into `builds/`, `game/`,
  `originals/`, `wb/` or `work/`.
- When a change makes a row of `docs/STATUS.md` untrue, update it in the
  same commit. Keep "untested" visible.

## Tests

`python3 -I tools/test.py --tier ci` runs the game-free suites (CI runs the
same list with `--strict`); one suite: `python3 -I tools/test.py test_doc_links`.
The full gate needs Windows and the game: `tools/verify_local.py`. On Linux
the Windows-only parts cannot run: the live process readers (`aoa/live/`),
the highlight reel (`aoa/reel/`), the windows' Windows steps (registry,
firewall, elevation), PowerShell and `.cmd` scripts. Say so when a change
touches them.
