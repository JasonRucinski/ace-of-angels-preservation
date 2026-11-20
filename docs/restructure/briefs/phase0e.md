# Phase 0e: docs tell the truth (no docs move)

Bring the docs in line with the code as it stands after phases 0a to 0d, and
remove the contradictions the docs audit found. This is correction, not
reorganisation: phase 4 moves and restructures docs. Do not rename or move
any doc, and do not reword prose that is still true.

Files you may edit: `README.md`, `CONTEXT.md`, `CONTRIBUTING.md`, `CLAUDE.md`,
`tools/README.md`, everything under `docs/` except `docs/restructure/` and
`docs/history/`, `data/magazine-mentions.md`, `.github/ISSUE_TEMPLATE/*`.
New: `docs/STATUS.md`. No code. The only code-adjacent edits allowed are the
two docstring references in item 6.

House rules that bind you: evidence over claims; anything untested stays
visibly marked untested; mark what you could not confirm. When two docs
disagree, find the evidence file or the code that settles it and cite it. If
nothing settles it, say "not established" and list it in your report: do
not pick the more flattering version.

1. **`docs/STATUS.md` (new): the one page for current verified and untested
   claims.** Sections: what works and how it was verified (with the evidence
   file), what is implemented but untested, what does not exist. Cover at
   least: play between separate PCs, the number of maps and which have real
   content, whether anyone has seen each map on screen, the launchers, the
   Linux host, the camera views, target ships, power-ups, trials (turret,
   warp, buoys). Every other doc that states one of these links here instead
   of restating it. Resolve the three contradictions in
   `docs/restructure/audits/docs.md` (separate-PC play, "20 maps",
   "nobody has looked at the maps on screen") from the evidence, and fix
   every place that states the losing version (README, `docs/play.md`,
   `CONTRIBUTING.md`, `docs/map-viewer.md`, issue templates).
2. **Client changes from phase 0b** (verify each against the code before
   editing):
   - An option not named on `prepare` keeps its installed state, and
     `--station` keeps the installed server when omitted; defaults apply only
     to a never-prepared client. Fix `docs/play.md`, `docs/lan-dogfight.md`,
     `docs/vpn-dogfight.md`, `docs/client-setup.md` where they describe or
     imply the old behaviour, including any instruction that relied on a
     plain `prepare` resetting the server to localhost.
   - The per-tool installers (`asteroid_render`, `solid_world_render`,
     `station_detail`, `world_detail`, `texture32`, `object_persistence`) no
     longer write `.before-*` backups or `_*.json` records, `--undo` means
     "turn this option off", and undo-ordering rules are gone:
     `docs/asteroid-rendering.md`, `docs/client-setup.md`,
     `docs/texture-pack.md` (prefer the launcher checkbox).
   - `check` fails on an older camera, menu or terrain variant with "re-run
     prepare". The launcher turns experimental protection off for a remote
     server. Remove the stale "prepared executable" hash in
     `docs/client-setup.md` and the `dgVoodoo.conf.before-quality` section no
     tool creates (audit C10, C20). Correct the claim about an undone client
     (C19).
   - The standalone command lines of `patch_client.py`, `local_station.py`
     and `physics_timestep.py` are gone: `docs/running-on-windows-11.md`,
     `tools/README.md`, `docs/findings.md` (mark as historical, do not
     delete findings).
   - `client_launcher.cmd` keeps a console window open while the launcher
     runs; `setup_game.ps1` needs `.venv` and stops on a missing explicit
     `-Wrapper`.
3. **Host changes from phase 0c** (verify each against the code):
   - "This PC only" now runs `local-guests` with sustained delivery; default
     player limit is 8; errors go to `work/logs/host.log`; "Load map" checks
     the settings before stopping: `docs/host-control.md`.
   - Status and log files are under `work/host/` for every launcher:
     `docs/lan-dogfight.md`, `docs/vpn-dogfight.md`.
   - `--advertised-address` is deprecated: remove it from commands in
     `docs/lan-dogfight.md` and `docs/arena1a-rebuild.md`.
   - The console command list includes `say` and `quit`.
   - `docs/linux-host.md`: `--bind-address` is required for the LAN and VPN
     profiles; `--status-file` is optional; rotation configs may carry a
     `"comment"`. State where the Windows and Linux defaults differ
     (20 kills / 600 s by default; the rotation example sets 10 / 900).
   - One name for client requirements: say "patch level N" and name the
     feature; fix "patch v11" / "online-terrain-v2" wording (audit H23, F-11).
4. **Tool changes from phase 0d:**
   - Audits write to `work/` by default and need `--evidence PATH` to write
     the committed copy: `tools/README.md` intro, `docs/level-data.md`,
     `docs/arena1a.md`, `docs/arena1a-rebuild.md`, `docs/map-viewer.md`,
     `docs/version-assets.md`.
   - Full-text search output names: `data/magazine-mentions.md`, `CONTEXT.md`.
   - `inventory.py`'s handoff argument is optional: `docs/findings.md`.
   - `tools/README.md`: add the files the audit found missing from the index
     (`audits/research.md` R12) and the new `cli_util.py`, `polite_http.py`,
     and correct the "standard library only" claim (R8b).
5. **`CLAUDE.md`** describes the whole project as it is now (research,
   client patches, host, tools), keeps every existing rule, and adds: never
   run a tool you have not read; tools write to `work/` unless given
   `--evidence`; all archive access goes through `tools/polite_http.py`.
   Keep it short.
6. **Small verified fixes from the docs audit:** the broken anchor at
   `docs/findings.md:2085`; links into the ignored `work/` folder in
   `docs/arena1a.md`; the two docstring references to docs that do not exist
   (`tools/aoapack.py`, `tools/packet_sizes.py`: point them at the right
   section of `docs/findings.md`); the one command without `-I`
   (`docs/host-control.md`); stale counts and dates the audit lists (test
   counts, "patch version 12" hash, roadmap items already implemented get an
   "implemented by …" note rather than a silent tick).

Checks before you finish: re-run the link checker
(`docs/restructure/audits/scripts/docs_linkcheck.py`, adapted; it must only
read files) and report its result; every command line you touched must name
a file that exists and flags its argparse accepts (read the code; do not run
tools). Run the suites in RULES.md once at the end (you changed two
docstrings).

Done when STATUS.md exists and is linked from the README, the three
contradictions are gone, and your report lists anything you could not
settle from evidence.
