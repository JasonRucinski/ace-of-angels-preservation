# Contributing

Thanks for helping keep *Ace of Angels* alive. Four kinds of help matter most.

## Leads and old material

The project is still missing builds and history. Especially wanted:

- **Discs**: magazine cover CDs/DVDs from 2001–2004 with an Ace of Angels demo
  or beta, such as Joystick #134/#136 (FR), GameStar CZ #36–#40, Gamers
  Workshop #37 (BG), the CD-Action 01/2003 Bonus section (PL), PC Guru (HU).
- **Builds**: the early-2001 demo, any arena beta, or any version not in
  [`manifest/downloads.json`](manifest/downloads.json).
- **The universe**: manuals, lore pages, forum posts, screenshots or videos.
- **The people**: anything from former Flying Rock staff or players, and any
  sign of the 2009–2010 OGRE or 2020 Unreal Engine 4 revival attempts.

Open a **Lead** issue with what you have and where it came from. Please do not
upload game files to this repository; a description, a hash and a public
archive link are enough. [CONTEXT.md](CONTEXT.md) section 6 lists what has
already been searched.

## Play reports

Separate PCs have played only through the Linux host on a LAN; a
Windows-hosted LAN game and VPN play between separate connections have not
been recorded ([docs/STATUS.md](docs/STATUS.md)), so any session is
valuable. Open a **Play report** issue with your Windows version, GPU, whether
you used the dgVoodoo wrapper, LAN or VPN, the player count, and what did or
didn't work. The client log in `game\2.9.2\Logs\` helps with crashes.

## Code and reverse engineering

Setup is in [docs/play/README.md](docs/play/README.md); every command and
module is indexed in [docs/reference/tools.md](docs/reference/tools.md); the
docs are indexed by reader in [docs/README.md](docs/README.md). Code lives in
the `aoa` package, suites in `tests/`, command shims in `tools/` and frozen
one-off scripts in `archive/`.

House rules, from how the project has worked so far:

- **Evidence over claims.** Say what was verified and how: a test, an
  emulation run, a live client check. Keep "untested" visible. Machine-readable
  results go in `evidence/`.
- **Client patches are reversible and hash-checked.** A new patch accepts only
  known images, records its undo, and gets a `test_*.py` that checks it, often
  by running the original code in Unicorn.
- **No game files in commits.** Extracted assets and renders go to the ignored
  `work\` folder.
- **Untrusted downloads stay contained.** Each download goes in its own new,
  empty folder under `builds\` or `wb\`. Run Python on it with `-I`, from
  outside that folder.
- **Be gentle with archive.org and the Wayback Machine**: pause between
  requests and back off on HTTP 429.

## Design rules

How the code is laid out, from the November 2026 restructure
([plan](docs/restructure/PLAN.md#2-target-design)). Tests enforce the first,
second, third and eighth.

1. **Layering.** `aoa/formats` imports nothing else in `aoa`. `protocol` and
   `maps` may import `formats`. `client` and `host` may import those three and
   never each other. `launchers` sits on top. `research`, `analysis`,
   `emulation`, `live` and `reel` are leaves: nothing in `client`, `host` or
   `launchers` imports them. `aoa.paths`, `aoa.cli` and `aoa.builds` are the
   base every layer may use (`tests/test_layering.py`).
2. **One entry convention.** Every command has `main(argv=None)` with
   argparse. `--help` never touches the network or writes a file. Missing
   input exits non-zero with one line, not a traceback. Commands people use
   keep their `tools/<name>.py` path as a three-line shim, so documented
   commands and `python -I` keep working (`tests/test_cli_help.py`).
3. **One source for each fact.** Build hashes in `aoa/builds.py` (checked
   against `manifest/downloads.json`). Maps in `aoa/maps/registry.py`;
   profiles, ports, aliases, backdrops and defaults in `aoa/host/defaults.py`;
   vessels and object slots in their own data modules, which import nothing
   from the server. A table in the docs that repeats one of these is generated
   from it (see [Where docs go](#where-docs-go)).
4. **Patches are data.** Each client patch is one descriptor
   (`aoa/client/patches/base.py`: id, the version it arrived in, option,
   label, default, requires, conflicts, constants read, regions) in one
   registry. One engine strips and applies them, and the command line, the
   launcher checkboxes and `check` read the same registry. An option you do
   not name keeps its installed state. One backup, one record, one undo.
5. **One host configuration.** `HostConfig` (`aoa/host/config.py`) builds and
   validates the server command line, so "validated" means "will start". The
   host window and the headless host read the same settings file and use the
   same supervisor (restart, rotation, recycling, watchdog).
6. **Output.** Tools write to the ignored `work/` folder by default. Committed
   evidence is written only with an explicit `--evidence PATH`.
7. **Network.** All archive.org and Wayback requests go through
   `aoa/research/http.py`, which paces requests, identifies itself the same
   way each time and backs off on HTTP 429 and 5xx.
8. **Tests.** One runner, `tools/test.py`, for CI and the local gate. A
   missing game file or optional package is a skip with a reason, never an
   import error. Suites are listed by tier in `tests/tiers.py`.

## Tests

Before opening a pull request, run the tests that cover your change, and the
full gate if you have the game set up. `tools/test.py` runs suites, each in
its own `python -I` process; the lists are in `tests/tiers.py`:

```powershell
.venv\Scripts\python.exe -I tools\test.py --tier ci
.venv\Scripts\python.exe -I tools\test.py test_station_stub
.venv\Scripts\python.exe -I tools\verify_local.py
```

`--tier ci` runs the suites that need no game files; CI runs them on every
push and pull request, on Windows and Ubuntu, with the packages of
`requirements-research.txt` installed and `--strict`
([`.github/workflows/tests.yml`](.github/workflows/tests.yml)). Without those
packages, a suite that needs `unicorn`, `capstone` or `pefile` is reported as
skipped.

`verify_local.py` runs the supported regression gate: the suites in the
`LOCAL` list of `tests/tiers.py` (most, not all, of the `test_*.py` files) and
the emulators, about 10 minutes. It does not launch the game, but it needs a
prepared `game\2.9.2` folder (it reads the original `AOACLIENT.EXE.orig`).

## Where docs go

Every doc is listed once in [docs/README.md](docs/README.md), by reader.

| Kind | Where | How it is kept |
|---|---|---|
| What works, what is untested | [docs/STATUS.md](docs/STATUS.md) | The only place that states it as current fact. Change it in the same commit as anything that makes a row untrue; keep "untested" visible. Guides link its rows instead of restating them. |
| Player, host and creator guides | `docs/play/`, `docs/host/`, `docs/create/` | Undated and kept current. Steps that several pages share are written once (for hosts, in `host/README.md` and `host/console.md`). |
| References | `docs/reference/` | Facts to look up. A table generated from the code sits between two marker comments and is rewritten with `python -I tools/run.py MODULE --write`: `aoa.client.patchdoc` (patches), `aoa.maps.mapdoc` (maps), `aoa.host.defaultsdoc` (host defaults), `aoa.host.flagdoc` (server flags) and `aoa.tools_index` (every command). `tests/test_doc_tables.py` fails when one is stale. |
| Research records | `docs/research/` | Dated and not rewritten; a correction is a new dated entry that links forward. New work: an entry at the top of `research/log.md`, and for an investigation the next numbered section of `research/findings.md` with its `<a id="s9-N">` anchor ([how](docs/research/README.md)). |
| Archive research | [CONTEXT.md](CONTEXT.md), `docs/archive/` | CONTEXT is the record of the search for builds, the website and revival; its tables are updated in the same session as a verified build or a ruled-out source. |
| Roadmaps | `docs/roadmap/` | Proposed work. Tick an item only with its evidence. |

Moving a doc: `git mv` it, leave a three-line stub at the old path ("Moved
to …"), and point every link in the repository at the new path.
`tests/test_doc_links.py` checks every link and anchor (and that none lands
on a stub or in an ignored folder); `tests/test_doc_commands.py` checks that
every documented command names a real tool and real flags. Machine-readable
results go in `evidence/` and are listed in `evidence/INDEX.tsv`.

## Searching tips

"Ace of Angels" is also the K-pop group AOA. Pair searches with
"Flying Rock" or "space". Anything taken only from a search-engine summary is
marked *(snippet)* in the notes until the source itself is read.
