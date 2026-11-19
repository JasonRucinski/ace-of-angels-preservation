# Restructure plan

Written 13 November 2026 from six audits of `main` at `f659000` (host and
server, client patches, launcher experience, docs, research and asset tools,
tests and CI). This is a plan, not a record of completed work. Each phase
below is checked off only when its gate passes.

The audits found no data corruption and no stale documented command: build
hashes agree everywhere, 335 doc links resolve, and all 282 documented
command lines still parse. The problems are structural: one flat folder of
166 Python files, several copies of the same logic that have drifted apart,
and launchers that leave most of the work to the command line.

## 1. What is wrong today

### Breaks or misleads users (fix first)

| # | Problem | Where |
|---|---|---|
| U1 | Any `prepare` that does not name them turns five client options back on (frame clock, visibility math, chase camera, power-up pickup, menu framing). The documented "point the client at a friend's server" command does this, and so do `texture32.py`, `world_detail.py`, `station_detail.py` and `solid_world_render.py`. | `prepare_client.py` defaults |
| U2 | `asteroid_render.py` and `object_persistence.py` report "verification failed" after the executable has already been rewritten. | their `install()`/`main()` |
| U3 | Tools without argument parsing act on `--help`: `fetch_known_builds.py` downloads 61 MB from archive.org, `ia_fulltext_search.py` starts live archive.org queries, `audit_level_data.py` overwrites a tracked evidence file, `audit_object_lod.py` writes an empty report and exits 0. 50 of 70 research scripts end in a traceback. | scripts using bare `sys.argv` |
| U4 | Only 2 of 7 archive.org/Wayback fetch helpers pause and back off on HTTP 429, which `CLAUDE.md` requires. | research scripts |
| U5 | The host window fails to open, with no message and no log, when its saved settings hold an unknown value. Both launchers start under `pythonw`, so any start-up error is invisible. | `host_control.py`, both `.cmd` files |
| U6 | "Load map (restart)" stops the server before checking the new settings, so a bad setting disconnects everyone and leaves the host down. | `host_control.py` |
| U7 | Settings that pass the server's own check still crash at start: navigation buoys with JRMAP and no `JRMAP.TRN` (reported as a port problem), and an unknown `--start-vessel` (traceback). | `station_stub.py`, `station_runtime.py` |
| U8 | The headless host's default profile and default bind address are mutually invalid, and the error prints the server's 40-line usage text. | `dedicated_host.py` |
| U9 | `third_person` and `own_ship_menu` report an old code variant as the current one, so `check` passes on stale camera code. | `state()` in both |
| U10 | Docs contradict each other on what is verified: play between separate PCs ("not recorded" in two docs, recorded on 26 Oct in three), "20 maps" (11 have content), and "nobody has looked at the maps on screen" (the reel filmed six). | README, `play.md`, `CONTRIBUTING.md`, `map-viewer.md` |

### Drift between copies of the same thing

- **Five builders of the server command line** (host window, headless host,
  `start_lan_dogfight.ps1`, `map_viewer serve`, `make_map serve`) with
  different defaults: 20 kills / 10 min or 10 kills / 15 min; 2, 4 or 8
  players; three status-file paths; three crash-restart policies.
- **Six patch interface shapes** across 18 modules, six separate undo
  mechanisms that go stale, 13 backup suffixes, and hand-ordered patch
  composition called with 14 positional arguments.
- **Shared constants repeated**: the 2.9.2 hash in 9 files, object slot
  ranges in 5, ports and aliases in 4, the vessel list in 3.
- **Two hidden patch interactions**: `distant-world-objects-v1` rewrites
  constants that the asteroid and solid-world patches read; `own_ship_menu`
  keeps a byte inside `third_person`'s data block by comment only.

### Inverted structure

- The server imports the client patcher and two audit scripts, with a cycle
  (`station_stub → warp_trial → audit_warp_gates → station_stub`).
- The server's `run()` is one 780-line function with 16 nested functions.
- Library code lives inside one-off scripts (`emulate_codec.py` holds the
  emulator 25 modules import, plus a 2.7.1-only command line).
- 129 `sys.path.insert` lines; 14 tests import `test_station_stub` as a
  library.

### Tests and CI

- 20 suites run in CI (19 on Linux, one more on Windows). Two of them skip nearly everything there
  (`test_prepare_client` 8 of 8, `test_client_launcher` 5 of 6).
- 11 suites run in neither CI nor `verify_local.py`. `test_reel` is game-free
  and passes; the rest need game files.
- 18 suites error at import on a machine without `unicorn`/`capstone`/`pefile`
  instead of skipping, and several error instead of skipping without the game.
- `python -m unittest discover` and `pytest` both fail today.

## 2. Target design

### Layout

```
aoa/                    one importable package
  paths.py  cli.py  builds.py      repo paths, argparse helper, known build hashes
  formats/      archive, cipher, model, scene, map and installer formats (standard library only)
  protocol/     datagram codec, movement, object status messages
  maps/         map registry, placements, custom maps and objects, export, preview
  client/       prepare engine, base step, patches/ (one module per patch), texture pack, install
  host/         server, config, delivery, match, objects, console, supervisor, headless runner
  launchers/    settings model, catalog, player window, host window
  research/     archive.org and Wayback tools behind one polite HTTP helper
  analysis/     disassembly and static-analysis tools
  emulation/    original-code emulator and the gate checks
  live/         Windows process readers and live verifiers
  reel/         highlight reel
tests/          every suite, run through one runner
tools/          thin entry scripts for the commands people already use
archive/        frozen one-off scripts, kept for reproducibility, not imported by anything
docs/           play/ host/ create/ reference/ research/ roadmap/ archive/
```

`file-map.tsv` beside this file assigns every current file to its new home.

### Rules (the design language)

1. **Layering.** `formats` imports nothing else in `aoa`. `protocol` and
   `maps` may import `formats`. `client` and `host` may import those three and
   never each other. `launchers` sits on top. `research`, `analysis`,
   `emulation`, `live` and `reel` are leaves: nothing in `client`, `host` or
   `launchers` imports them. A test enforces this.
2. **One entry convention.** Every command has `main(argv=None)` with
   argparse. `--help` never touches the network or writes a file. Missing
   input exits non-zero with one line, not a traceback. Commands people use
   keep their `tools/<name>.py` path as a three-line shim, so documented
   commands and `python -I` keep working.
3. **One source for each fact.** Build hashes in `aoa/builds.py` (checked
   against `manifest/downloads.json`). Maps, vessels, ports, aliases, backdrops
   and defaults in data modules that import nothing from the server. Object
   slots from one allocator.
4. **Patches are data.** Each patch is one descriptor (id, version it arrived
   in, option name, label, default, requires, conflicts, constants read,
   regions). One engine strips and applies them, one registry feeds the
   command line, the launcher checkboxes and `check`. An unnamed option keeps
   its installed state. One backup, one record, one undo.
5. **One host configuration.** A single `HostConfig` builds the server
   command line and validates it, so "validated" means "will start". The host
   window and the headless host read the same settings file and use the same
   supervisor (restart, rotation, recycling, watchdog).
6. **Output.** Tools write to the ignored `work/` folder by default.
   Committed evidence is written only with an explicit `--evidence PATH`.
7. **Network.** All archive.org and Wayback requests go through one helper
   that paces, identifies itself the same way, and backs off on 429 and 5xx.
8. **Tests.** One runner (`tools/test.py`) used by CI and the local gate.
   A missing game file or optional package is a skip with a reason, never an
   import error. Suites are tagged game-free, needs-game or Windows-only.
9. **House rules stay.** Evidence over claims; "untested" stays visible;
   patches reversible and hash-checked; no game files in commits.

## 3. Phases

Each phase ends with its gate green and one or more commits on
`architecture-cleanup`. Nothing touching client patch bytes can be fully
verified without the game: see section 4.

### Phase 0. Safety net and fixes, no files move

- [x] **0a Golden snapshots** (game-free tests, added to CI):
  every patch's regions as address/bytes (proves later refactors change no
  patch byte); the server command line for each launcher and each documented
  command; region disjointness and cave/data bounds. Install the pinned
  `unicorn`, `capstone` and `pefile` in the Linux CI job. Record the pass,
  skip and error outcome of every suite as the baseline.
  Done 13 Nov: `tools/test_patch_layout.py`, `tools/test_host_argv.py`,
  `tools/snapshots/`, [baseline-tests.md](baseline-tests.md). Not run: the
  Windows CI job.
- [x] **0b Client fixes**: U1, U2, U9; legacy command lines of `patch_client`,
  `local_station` and `physics_timestep` removed (they break a prepared
  client); `setup_game.ps1` fails on an explicit missing `-Wrapper`.
- [x] **0c Host fixes**: U5, U6, U7, U8; ban check before the version reply;
  `host_control.cmd` uses `-I`.
- [x] **0d Command-line safety**: U3, U4. Every script gets `main(argv)` and
  argparse; a test runs `--help` on every entry point with the network
  blocked and asserts exit 0 and no file written.
- [x] **0e Docs truth**: U10; one `docs/STATUS.md` holds what is verified and
  what is untested, and other docs link to it.

Gate: the CI suites, the new snapshot and `--help` tests, and the 47-suite
baseline unchanged except for suites that now pass or skip cleanly.

### Phase 1. Package and move, behaviour unchanged

- [x] Create `aoa/` and move every file per `file-map.tsv`; rewrite imports;
  remove the `sys.path.insert` lines; leave `tools/` shims.
- [x] Move tests to `tests/`; shared server fixtures leave `test_station_stub`
  for `tests/support.py`; add `tools/test.py`; point CI and `verify_local.py`
  at it; add the 11 orphan suites to the right tier.
- [x] Add the layering test (rule 1) with today's known violations listed as
  expected failures to remove in phase 2.
- [x] Update the Linux deploy unit and `linux-host.md` (the host now needs
  `aoa/` as well as `tools/` and `deploy/`).

Gate: snapshots byte-identical; 47-suite outcomes identical to the phase 0
baseline; every module imports; every shim's `--help` works.

Done 14 Nov ([phase1-tests.md](phase1-tests.md)): the snapshots are the same
git blobs as before the move, every suite has its baseline outcome, and
`tools/test.py --tier ci` passes 28 of 28. Not done: the Windows run of
`verify_local.py`, both windows, the reel and the live verifiers (section 4).
Phase 2-pre (15 Nov, [phase2pre-tests.md](phase2pre-tests.md)) then removed
all 17 layering violations that the move left, the five suites that imported
another suite, and the old `tools/x.py` names in docstrings and usage lines:
`aoa/builds.py`, `aoa/formats/pe.py` and `aoa/maps/registry.py` are new, and
the layering test has no exceptions.

### Phase 2. Rebuild inside the packages

- [x] **2a Client**: patch descriptor, registry and engine (rule 4);
  per-tool installers and their backups removed; `layout.py` owns cave and
  data reservations; the two hidden interactions declared and tested;
  experiments archived.
- [x] **2b Host**: `run()` becomes an `ArenaServer` class, then splits;
  data modules for maps, vessels, object slots, ports and defaults;
  `HostConfig`, `HostProcess`, restart budget and supervisor (rule 5);
  server no longer imports `client` or audit code; one delivery engine for
  play; `--advertised-address` and `--arena1a-buoys` removed; flags renamed
  by role with the old names kept as aliases for one release.
- [x] **2c Research and analysis**: one HTTP helper; manifest-driven fetch;
  `aoa/builds.py`; emulator library split from its 2.7.1 command line;
  disassembly cache keyed by executable hash; evidence index with generator
  commands.

Done 15 Nov: 2a (patch snapshot unchanged; prepared output pinned for 25
option sets) and 2b (server command lines changed only by the flag renames
and removals listed in its commits). Open from 2b: `map_viewer serve` and
`make_map serve` still build their own command line, because `aoa/maps` may
not import `aoa/host`; phase 3 moves them. The 30-event delivery engine
still carries despawns for hosts without sustained delivery; making the
windowed engine the only path would change the wire and is a separate
decision.

Gate: snapshots byte-identical for patches; server command lines identical
or changed only as listed in the commit; layering test has no expected
failures left; all suites at baseline or better.

### Phase 3. Launchers

- [x] One settings file and one catalog (maps with notes and a playable flag,
  backdrops, ports, defaults, feature to minimum patch level).
- [x] **Player launcher** (`Play.cmd`): first-run checklist (find or download
  the game, verify, apply fixes, register the login skin, install the
  wrapper), then Play, Join a friend (paste the host's address; checks it
  resolves and that the host answers), and Options grouped as fixes, visual
  extras, graphics quality and experimental. Shows the installed patch level.
- [x] **Host launcher** (`Host.cmd`): who can join, address, maps (one or a
  rotation, playable maps only, with notes), rules, Start; then a share box
  with the address to give players, the player table, and change-map that
  validates before it restarts.
- [x] **Headless host** reads the same settings file through the same
  supervisor; `start_lan_dogfight.ps1` becomes a two-line wrapper;
  `setup_game.ps1` stays as a fallback.
- [x] Errors show a dialog with the cause and are written to
  `work/logs/launcher.log`. Long work runs off the window thread.
- [x] Player install needs no research packages: requirements split into
  player (none), texture pack and research.

Done 19 Nov: 2c (one fetcher, evidence index, requirements split, generated
tools index; the CI tier passes strictly on Python 3.12 with the research
packages, 47 of 47) and phase 3 (both windows rebuilt on the engines;
screenshots in [screens/](screens/), captured on Linux under a virtual
screen; never run on Windows).

Gate: launcher logic covered by game-free tests (settings validation,
profile to command line, supervisor with a fake child process, join address
handling). The windows themselves cannot be run here: see section 4.

### Phase 4. Docs

- [ ] Docs tree: `play/`, `host/`, `create/`, `reference/`, `research/`,
  `roadmap/`, `archive/`. `findings.md` becomes the research log under
  `research/` with real anchors.
- [ ] Generated references: tool index from module docstrings, server flag
  table from argparse, patch table from the registry, defaults from the
  catalog.
- [ ] `README.md` is the front door, `CONTEXT.md` the research record,
  `CLAUDE.md` the working rules for the whole project (it still describes
  archive research only), `CONTRIBUTING.md` the design rules above.
- [ ] CI checks links and that documented commands parse.

## 4. What cannot be verified in the cloud

This work is done in a Linux session with no game files and no Windows.

- **Patch bytes.** The snapshot tests prove the refactor writes the same
  bytes to the same addresses. They do not prove the patched game still
  runs. Before merging phase 1 or later, run on Windows with the game:
  `.venv\Scripts\python.exe -I tools\verify_local.py`.
- **The two windows.** Their logic is tested; their layout and behaviour on
  Windows 10 and 11 need a person to open them.
- **Elevation, registry and firewall steps** in the launchers need a real
  Windows machine.

## 5. Decisions made here

Say so if any of these should go the other way.

1. Package name `aoa`; commands people use keep their `tools/<name>.py` paths.
2. Host defaults follow the server's own: 20 kills, 600 seconds, 8 players.
   The Linux rotation example keeps its explicit 10 kills / 900 seconds.
3. The standalone patch installers (`texture32.py --undo` and five siblings)
   are removed in favour of `prepare` options and the launcher.
4. `start_lan_dogfight.ps1` and `setup_game.ps1` are kept as thin wrappers or
   fallbacks, not deleted.
5. One-off analysis scripts whose output is already in `evidence/` move to
   `archive/`. Nothing is deleted outright.
6. One branch, one commit or more per phase. Phase 0 can merge on its own.
