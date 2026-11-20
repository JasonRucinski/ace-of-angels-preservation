# Documentation audit: Ace of Angels preservation repo

Auditor area: README.md, CONTEXT.md, CLAUDE.md, CONTRIBUTING.md, NOTICE.md, tools/README.md,
docs/README.md, docs/*.md (30 files), docs/history/, docs/images/SOURCES.md, .github/ISSUE_TEMPLATE/*.
Branch `architecture-cleanup` at origin/main (last commit 2026-11-01). About 9,700 lines of Markdown.

Scripts used (all in the scratchpad, `.../scratchpad/arch/docs_audit/`):
- `linkcheck.py`: every relative Markdown link, image and `#anchor` in every tracked .md/.yml file. It uses GitHub-style slugs and fence-aware parsing.
- `pathcheck.py`, plus a grep for `*.py` names: every `tools/…`, `docs/…`, `evidence/…`, `data/…` path mentioned in prose or code spans.
- `flags2.py` / `flags3.py`: extracts 282 command lines (fenced blocks with `\`/`` ` ``/`^` continuations joined, plus inline code spans) that invoke `tools/*.py|ps1|cmd`. It checks that the tool exists. It checks every flag against `--help` output (argparse tools, per subcommand), against `$Param` names (PowerShell), or by grepping the source for tools without argparse.
- `subs.py`: subcommands used in docs, checked against each CLI's `{a,b,c}` list.

> **Incident during this audit (now reverted).** Running `python3 -I tools/X.py --help` over
> every tool named in the docs had side effects. `fetch_known_builds.py --help` downloaded both
> game installers (63 MB) into a new repo folder named `--help/`. `audit_level_data.py --help`
> **overwrote the tracked file `evidence/asset-review/level-data.json`** with a 30-line partial
> report. `ia_fulltext_search.py --help` began querying archive.org and was killed at the 20 s
> timeout before it wrote anything. I restored the evidence file with `git checkout --` and deleted
> `--help/`; `git status` is clean again. This is finding D-01: about 60 tools treat any first
> argument as a path, so `--help` is not safe.

## 1. Summary

- **Links are mostly sound.** 335 relative links and anchors resolve. There is **one broken anchor** (`docs/findings.md:2085`) and **3 links into the git-ignored `work/`** (`docs/arena1a.md:37-39`). Two code docstrings point at **docs that do not exist** (`docs/protocol-notes.md`, `docs/file-formats.md`). All 231 repo paths named in prose exist. All 11 README images match the SHA-256 values in SOURCES.md.
- **Doc commands are current.** No stale flag or subcommand was found in 282 doc command lines. One command lacks `-I` (`docs/host-control.md:15`). Six interpreter spellings are mixed: `.venv\Scripts\python.exe`, `.venv/Scripts/python.exe`, `python -I`, `python3 -I`, `py -3.12 -I`, and none.
- **The tools are the real CLI hazard.** About 60 of the documented tools have no `--help`. Some take destructive or networked actions on any argument (D-01). This affects both users and the auditors.
- **"Honest status" contradicts itself across docs.** README and linux-host.md say two separate Windows PCs fought over LAN on 26 Oct. `docs/play.md:116` and `CONTRIBUTING.md:25` still say play between separate PCs "has not been recorded yet". `docs/map-viewer.md:49` says nobody has looked at the maps on screen, but the 27 Oct highlight reel filmed six of them.
- **README overclaims "20 maps" for multiplayer.** In code, 20 entries are listed, but 5 are "component" layouts and 4 "load nothing alone". map-viewer.md itself says the maps are not playable. The LAN/VPN launcher accepts only `CTF_arena` and `Arena1a`.
- **Three hosts have three sets of defaults, and no doc explains why.** Match limits are 20 kills / 10 min (station_runtime, host_control, play.md, lan-dogfight.md) against 10 kills / 15 min (Linux host). Player caps are 2 (`start_lan_dogfight.ps1`), 4 (`host_control.py`) and 8 (`station_runtime.py`).
- **CLAUDE.md is out of date.** It describes only the 2026-10-20 archive research, yet README calls it "a good summary for humans". It has no rules for client patches, tests, CI, the Linux host or doc placement. CONTEXT.md §1 and §3–§10 are frozen at 20 Oct: its "next steps", tools table and "has not been run / use a 98/XP VM" text are stale. Its §2 "Status" is a 430-line unordered changelog that duplicates findings.md.
- **Most docs are dated research logs** filed under "Playing" or "How the game works". findings.md (2,989 lines) is titled "static network/protocol findings" but now holds every client fix, the cameras, power-ups and targets. About 40 "findings 9.x" links have no anchor and land at line 1. The dated-heading anchors are fragile; the one broken anchor shows this.
- **Hosting setup is spread over 6 docs, the roadmaps are stale, and two docs are not indexed.** play.md, lan-dogfight.md, vpn-dogfight.md, linux-host.md, local-server.md and host-control.md overlap. The roadmaps (internet-server-todo.md "Updated 21 October", modernization-todo.md 0/77 ticked) never record the Linux host, map rotation, 2x texture pack, borderless window or frame pacing. `docs/arena1a-rebuild.md` is missing from docs/README.md. tools/README.md leaves out `dedicated_host.py` and 10 other non-test tools.

## 2. Findings

Severity: **H** = breaks or misleads users or repo state; **M** = misleads contributors or causes drift; **L** = hygiene.

| ID | Sev | Location | Problem | How verified | Suggested fix |
|---|---|---|---|---|---|
| D-01 | H | `tools/fetch_known_builds.py:47-52`, `tools/audit_level_data.py:96`, `tools/ia_fulltext_search.py:13` (pattern in ~60 tools) | `--help` is not recognised. fetch_known_builds downloads 63 MB into `./--help/`. audit_level_data rewrites the tracked `evidence/asset-review/level-data.json` even with no game data. ia_fulltext_search starts 30 archive.org queries. Other tools crash with tracebacks (IsADirectoryError, IndexError, missing capstone/unicorn at import). | Ran `python3 -I tools/X.py --help` for every doc-referenced tool, then `git status` and `git diff --stat` showed the side effects; reverted (see the note above). Full list: `docs_audit/flags2.out`. | Give every CLI argparse (or a shared `cli.py` helper) so that `-h` exits before any I/O. Make evidence writers require an explicit `--write-evidence` or output path, and refuse to write partial reports. Make network tools require an explicit output dir that already exists. |
| D-02 | H | `docs/play.md:116`, `CONTRIBUTING.md:25` | "Play between separate PCs has not been recorded yet" / "Multiplayer between separate PCs has not been recorded yet". This contradicts `README.md:97-99`, `docs/linux-host.md:35-39` and `CONTEXT.md:201` (two Windows PCs fought over LAN on 26 Oct, with evidence `evidence/2.9.2/linux_two_pc_combat_20261026.json`). | grep for "separate PCs"/"not recorded" across all .md files. | State once (see the STATUS proposal in §4): LAN between separate PCs is verified through the Linux host; a Windows-hosted LAN and VPN between separate connections are unverified. Link the evidence from play.md and CONTRIBUTING. |
| D-03 | H | `README.md:85` ("20 maps"), `docs/host-control.md:27`, `docs/custom-maps.md:45`, `CONTEXT.md:349` | The multiplayer feature list says "20 maps". `map_viewer.py list` shows 20 entries: 5 are "component" (1–4 objects), 4 "load nothing alone", and `docs/map-viewer.md:5-7` says loading "does not make them playable: no collision…". `start_lan_dogfight.ps1:19` accepts only `CTF_arena`/`Arena1a`; the Linux rotation uses 3. | `python3 -I tools/map_viewer.py list`; `online_terrain.MAP_NAMES` has length 20; read `start_lan_dogfight.ps1:15-28`. | README should say "3 maps in rotation (CTF_arena, CTF_arena_b, ast_fld_a); 20 recovered layouts viewable", and link the map table. |
| D-04 | M | `docs/map-viewer.md:47-49` | "Nobody has looked at these maps on screen yet: an in-flight screenshot comes back black." Superseded by the 27 Oct hype reel, which filmed irrosa01, ast_fld_a/b, outerchange, CTF_arena_b and JRMAP (`CONTEXT.md:70-78`, `docs/hype-reel.md`), and by the F5 captures for Crucible. | Read both. | Add a dated update line naming the maps seen in the reel (with evidence), and keep "not checked" for the rest. |
| D-05 | M | `docs/findings.md:2085` | Broken anchor `#947-an-orbit-camera-on-f4-f2-was-never-unbound-26-october-2026`. The heading now reads "26–27 October 2026", so the slug is `…-2627-october-2026`. | `linkcheck.py`. | Fix the anchor. Long term, add stable explicit anchors (`<a id="s9-47"></a>`) so retitling a heading doesn't break links. |
| D-06 | M | `docs/arena1a.md:37-39` | Links to `../work/arena1a-review/*.png` and `manifest.json`. `work/` is git-ignored, so these 404 on GitHub and for every other clone. | `linkcheck.py` (ignored-dir bucket). | Turn them into plain code text ("generated locally at `work/arena1a-review/…` by `tools/audit_arena1a.py`"). Never link into builds/, game/, work/ or wb/. Add this rule to the link check. |
| D-07 | M | `tools/packet_sizes.py:11`, `tools/aoapack.py:3` | Docstrings cite `docs/protocol-notes.md` and `docs/file-formats.md`, which do not exist. The content is in findings.md §3/§6 and assets.md. | grep `docs/[a-z-]+\.md` in tools/, checked existence. | Point them at the real sections, or at the new `docs/reference/` files after the move. |
| D-08 | M | `docs/findings.md:1` and the docs/README "How the game works" table | The title is "static network/protocol findings (2.7.1 reference, 2.9.2 comparison)". The file is now the master log for live protocol work, client crash fixes, cameras, power-ups, targets and the orbit view (§9.1–9.48), 2,989 lines. | Read the headings. | Split as proposed in §4: keep §1–8 as protocol reference and move §9 to research-log files. |
| D-09 | M | `CONTEXT.md` (14 links), `docs/client-setup.md` (9), `docs/host-control.md`, `level-data.md`, `local-protocol.md` (3 each), and others: about 40 total | Links written as `[findings 9.35](docs/findings.md)` have no anchor, so readers land at line 1 of a 3,000-line file. | Regex for `[...9.N...](…findings.md)`. | Add the anchors, or the stable `#s9-35` ids from D-05. |
| D-10 | M | `CLAUDE.md` (entire file) | It describes the project as archive research only ("find every surviving build…"). It has no rules for: no game files in commits, reversible hash-checked patches, which tests to run (CI list / `verify_local.py`), Windows-only vs Linux code, where new findings go, or the `game/`, `work/`, `originals/` folders. Yet `README.md:177` calls it "a good summary for humans". | Read it, compared with CONTRIBUTING house rules and the README layout. | Rewrite per §4: agent-facing rules for the whole repo that point to CONTRIBUTING for the house rules and to STATUS/CONTEXT for state. Drop the README claim. |
| D-11 | M | `CONTEXT.md:3-5`, `:487`, `:572-601`, `:603-617`, `:563-568` | Frozen at 20 Oct. The file says "done in a cloud session… carries it to a local project". §3 says the client "Needs DirectX 7; use a Windows 98/XP VM. It has not been run." (it now runs on Win 10/11). §7 "Next steps" #1 is "Wayback Machine for the universe site" (restored 21 Oct per §2) and lists unsearched discs with no date. §8 tools table lists 8 archive tools as "Python 3 standard library unless noted", and says `wayback_builds.py` was "never run against the live Wayback", although 2.0.0 was later recovered from a Wayback `id_` URL (`manifest/downloads.json:12`). §6 says web.archive.org is "blocked from the cloud", but the restore was done anyway. | Read the sections; checked against private-web-archive.md and the manifest. | Update §6/§7 with dates. Delete §8 (tools/README is the index). Fix the DirectX/VM sentence. CLAUDE.md requires CONTEXT to be kept current, and that rule is not being followed. |
| D-12 | M | `CONTEXT.md:17-444` (§2 Status) | A 430-line changelog of about 40 dated paragraphs. Entries 27→20 Oct run newest-first, then 22, 23, 23, 23, 23, 25, 25, 26, 24 Oct. It duplicates findings.md §9 and the per-topic docs, and the README "Honest status" is a third copy. | `awk` over the date-stamped paragraph openers. | Move it to `docs/research/log/` (one file per day or month). Keep a short current status matrix in one place (§4). |
| D-13 | M | `docs/internet-server-todo.md:3,7,26-62`, `docs/modernization-todo.md:3` | Roadmaps say "Updated 21 October 2026" and still list 22 Oct as "current priority". "Latest… 65 tests and eight emulators", but verify_local now has 9 emulators and 33 suites. Items done since are unticked and unannotated: dedicated host (`:401`), map rotation and round transitions (`:357`, done by `dedicated_host.py`), 2x texture test (`modernization:72`, texture-pack.md), borderless/windowed path (`:114`, dgVoodoo), frame pacing (`:116`, findings 9.35). Linux is not mentioned at all (0 hits). | Counted `[x]`/`[ ]` and greps; read `verify_local.py:16-31`. | Tick each item or mark it partial, with evidence links. Move the long "verification history" paragraphs (lines 26-70) to the research log. |
| D-14 | M | `docs/linux-host.md:30` ("All 15 server suites… 87 tests"), `:187` ("All 16 suites"), `tools/README.md:93-103`, `.github/workflows/tests.yml:37-44` | Test counts drift. CI runs 19 game-free suites (+1 on Windows) and verify_local runs 33 suites + 9 emulators out of 47 `test_*.py`. tools/README says verify_local runs "the `test_*.py` suites" (it runs 33 of 47; `test_dedicated_host`, `test_make_map`, `test_make_object`, `test_reel`, `test_menu_aspect` and others are not in it). It also says client-patch suites "fail" without the game; 13 suites skip, others fail at import of `unicorn`/`pefile`. | Read `verify_local.py`, `tests.yml`; grep skip decorators. | Never put live counts in prose. Have one generated table (CI list and gate list) in `docs/contributing/testing.md`. Dated claims stay in the dated logs only. |
| D-15 | M | `docs/play.md:115`, `docs/lan-dogfight.md:123`, `README.md:133`, `docs/linux-host.md:104` | Match rules differ by host: Windows host/CLI 20 kills or 10 min (`station_runtime.py:81-82`, `host_control.py:36`) against the Linux host's 10 kills or 15 min (`deploy/linux/rotation.json.example`). Player caps also differ: `start_lan_dogfight.ps1:18` = 2, `host_control.py:36` = 4, `station_runtime.py:77` = 8. No doc says which applies when. | Read the code defaults. | One "host defaults" table in the host guide. Ideally unify the defaults in code, which is the host/server auditor's call. |
| D-16 | M | `docs/history/2026-10-20-research-handoff.txt` | A "doc" that is also program input: `tools/restore_web_archive.py:111` reads it to seed the crawl, and `tools/inventory.py` takes it as `<handoff.txt>` (`docs/findings.md:172`). Moving the docs would break the tools. | grep for `research-handoff`. | Move it to `data/research-handoff-2026-10-20.txt` (or `evidence/`), and update both tools and the findings §8 command in the same change. |
| D-17 | M | `docs/README.md` | Index gaps and mis-filing. `arena1a-rebuild.md` (404 lines) is not listed. `local-server.md` (a host reference) sits under "How the game works". `client-setup.md` (a patch reference with addresses) and `running-on-windows-11.md` (a 20 Oct research log) sit under "Playing". The intro says "Most of these documents are working notes", so the player docs are not separated from the logs. | Script: every docs/*.md checked against the index. | Reorganise per §4. |
| D-18 | M | `tools/README.md` | Missing: `dedicated_host.py` (the Linux host entry point), `vessel_combat.py`, `make_vessel_combat.py`, `navigation_buoys.py`, `turret_groups.py`, `turret_trial.py`, `warp_trial.py`, `verify_navigation_buoys.py`, `verify_turret_trial.py`, `verify_warp_trial.py`. `tools/reel/bot.py`, `client_mem.py`, `scout.py` and `window.py` are undescribed. It also says to run everything with `.venv\Scripts\python.exe`, which is wrong for the Linux host (`python3`, no venv). | Script: tool names against README text. | Generate the index from module docstrings, or add a "Linux host" row and an "Arena1a trials" section. |
| D-19 | L | `docs/running-on-windows-11.md:49-50` | Says setup_game builds from `originals\2.9.2\aoa_2.9.2_installer_2.11.1.exe`. play.md and README use `builds\v2.9.2_2004_FamilyGamePack3\aoa-current.exe`. Both work (`setup_game.ps1:18,28-31` falls back), but the doc doesn't say so. | Read `setup_game.ps1`. | Mention the fallback, or point to play.md. |
| D-20 | L | `docs/host-control.md:15` | `.venv/Scripts/python.exe tools/host_control.py` has no `-I`, against the project rule. | Interpreter-style count. | Add `-I`. |
| D-21 | L | All docs | Inconsistent interpreter spellings: 93× `.venv\Scripts\python.exe -I`, 38× `.venv/Scripts/python.exe -I`, 10× `python -I`, 4× `python3 -I`, 2× `py -3.12 -I` (hype-reel, no venv), 1× without `-I`. Path separators are mixed inside one command. | grep count. | Pick per platform: `.venv\Scripts\python.exe -I tools\x.py` (Windows/PowerShell) and `python3 -I tools/x.py` (Linux). |
| D-22 | L | `docs/internet-server-todo.md`, `first-playable-release.md`, `client-extension-gate.md` | Three overlapping documents about the deferred authoritative server: first-playable-release opens with "Current priority: private LAN dogfight" (21 Oct), and client-extension-gate is a 21 Oct checkpoint. | Read the headers. | Merge into `docs/roadmap/authoritative-server.md`, marked deferred, and keep the gate as a section. |
| D-23 | L | `docs/README.md:3-6`, many docs | Docs refer to "the user" (the owner) and "user deferred…". This is acknowledged in the index, but player guides read oddly with it. | Read. | Keep in the research logs; remove from player and host guides. |
| D-24 | L | `README.md:178` vs `.gitignore` | README lists the ignored local folders as builds/, game/, originals/, wb/, work/. `.gitignore` also ignores `media/` (trailer), `.playwright-cli/` and `output/playwright/`. | Read `.gitignore`. | Add `media/` to the README list, or drop it. |

Checked and OK: every tool and file named in docs exists; all `--flag`s and subcommands in docs are accepted (`prepare_client {prepare,check,undo,launch}`, `make_map {build,install,serve,obj}`, `make_object {install,preview,undo}`, `map_viewer {list,install,serve}`, `--no-experimental-protection` via BooleanOptionalAction, all `start_lan_dogfight.ps1` / `setup_game.ps1` / `register_activeskin.ps1` params, reel `edit.py`/`record.py --only`). Patch version is consistent: `PATCH_VERSION = 22` (`prepare_client.py:38`) matches the newest mentions in client-setup, CONTEXT and asteroid-rendering. Older version numbers in docs are dated history, not drift. The Linux rotation defaults match between README, linux-host.md, `rotation.json.example` and `dedicated_host.py:24-32`. Ports 5031/5033/5034 are consistent. Issue templates reference existing paths and sections (CONTEXT §6, `prepare_client.py check`). NOTICE's "11 images" matches.

**Not checked:** the 56 external URLs (no network fetches, to respect the archive.org rule). Technical accuracy of addresses and offsets in findings and the reference docs. PowerShell semantics beyond parameter names, and `.cmd` wrappers. Commands whose tools need capstone/unicorn/pefile/tkinter, beyond a source grep for the flags. `data/magazine-mentions.md` content. Whether evidence JSON files support the prose claims that cite them (only existence was checked).

## 3. File classification

Roles: player guide / host guide / creator guide (maps, objects, video) / contributor guide / reference / research log / roadmap / obsolete.

```
README.md                         | front page + feature/status summary           | keep (trim status to link STATUS) | /README.md
CONTEXT.md                        | archive-research record + 430-line dev changelog | split: §1,3-7,10 keep; §2 -> research log; §8 delete; §9 -> CONTRIBUTING | /CONTEXT.md (archive research only)
CLAUDE.md                         | agent rules (archive-only, outdated)          | rewrite                          | /CLAUDE.md
CONTRIBUTING.md                   | contributor guide + house rules (canonical)    | keep; fix D-02; add testing/doc-placement | /CONTRIBUTING.md
NOTICE.md                         | legal / what the repo contains                 | keep                             | /NOTICE.md
tools/README.md                   | tool index                                     | keep; regenerate per package after tools/ reorg | tools/README.md
docs/README.md                    | docs index                                     | rewrite by audience              | docs/README.md
docs/play.md                      | player guide (install, offline, one-PC MP)     | keep; move "Play with friends" to host/README | docs/play/README.md
docs/running-on-windows-11.md     | research log (20 Oct crash diagnosis) + stale setup | split: "What was broken" -> research; setup -> delete (play.md covers) | docs/research/windows-11-compat.md
docs/client-setup.md              | reference: every client patch, addresses, undo; plus launcher player guide | split | docs/play/launcher.md (lines 8-64) + docs/reference/client-patches.md
docs/texture-pack.md              | player guide                                   | keep                             | docs/play/texture-pack.md
docs/map-viewer.md                | player guide (viewing) + reference map table + research (unfilled nodes) | split | docs/play/map-viewer.md; table -> docs/reference/maps.md; §"Unfilled-node" -> research
docs/lan-dogfight.md              | host guide (Windows LAN)                       | keep; dedupe shared parts        | docs/host/lan.md
docs/vpn-dogfight.md              | host guide (Windows VPN) + host console + lag test | keep; console/lag -> host/console.md | docs/host/vpn.md
docs/linux-host.md                | host guide (Linux systemd) + verification log  | keep; move dated verification prose to research | docs/host/linux.md
docs/host-control.md              | host guide (GUI window)                        | keep                             | docs/host/host-control.md
docs/local-server.md              | host reference: profiles, options, logs, limits | keep as reference                | docs/host/server-reference.md
docs/custom-maps.md               | creator guide (+format notes)                  | keep                             | docs/create/custom-maps.md
docs/custom-objects.md            | creator guide (+format notes)                  | keep                             | docs/create/custom-objects.md
docs/hype-reel.md                 | creator guide (video tooling)                  | keep                             | docs/create/hype-reel.md
docs/local-protocol.md            | reference: implemented protocol contract       | keep                             | docs/reference/protocol.md
docs/message-types.md             | reference (generated by message_table.py)      | keep; mark generated             | docs/reference/message-types.md
docs/assets.md                    | reference: .Gob/.Sco formats + extraction how-to | keep                           | docs/reference/asset-formats.md
docs/hosting-assets.md            | reference: 2.9.2 map/backdrop inventory (20 Oct) | merge-into reference/maps.md    | docs/reference/maps.md
docs/level-data.md                | research log (22 Oct static audit) + format facts | keep as research; formats -> asset-formats | docs/research/level-data.md
docs/version-assets.md            | reference/research: cross-version differences  | keep                             | docs/reference/versions.md
docs/code-clues.md                | research log (20 Oct static)                   | keep                             | docs/research/code-clues.md
docs/findings.md                  | protocol reference (§1-8) + master research log (§9.1-9.48) | split | docs/reference/protocol-static.md (§1-8) + docs/research/findings/9.01-9.33-network.md, 9.34-9.48-client.md (or one file per §9.x) with docs/findings.md left as a stub index
docs/arena1a.md                   | research log (Arena1a recovery, 22 Oct)        | merge with arena1a-rebuild       | docs/research/arena1a.md
docs/arena1a-rebuild.md           | research log (26 Oct trials: buoys/turrets/warps) | merge-into research/arena1a.md (or keep as arena1a-trials.md) | docs/research/arena1a-trials.md
docs/asteroid-rendering.md        | research log (rendering patches 22-27 Oct)     | keep                             | docs/research/rendering/asteroids.md
docs/render-pipeline-audit.md     | research log (emulation audit)                 | keep                             | docs/research/rendering/pipeline-audit.md
docs/offline-rendering-baseline.md| research log (21 Oct baseline, "ongoing")      | keep; mark closed or open        | docs/research/rendering/offline-baseline.md
docs/private-web-archive.md       | archive-research how-to + 21 Oct release record | keep                           | docs/archive/web-archive.md
docs/internet-server-todo.md      | roadmap (stale 21-22 Oct) + verification history | keep; refresh; move history     | docs/roadmap/internet-server.md
docs/modernization-todo.md        | roadmap (stale, 0/77 ticked)                   | keep; refresh                    | docs/roadmap/modernization.md
docs/first-playable-release.md    | roadmap (deferred authoritative release)       | merge-into roadmap/authoritative-server.md | docs/roadmap/authoritative-server.md
docs/client-extension-gate.md     | roadmap gate + 21 Oct checkpoint               | merge-into roadmap/authoritative-server.md | (same)
docs/history/2026-10-20-research-handoff.txt | original handoff; ALSO tool input (D-16) | move (data, not docs)            | data/research-handoff-2026-10-20.txt
docs/images/SOURCES.md            | provenance of README images (hashes verified)  | keep                             | docs/images/SOURCES.md
.github/ISSUE_TEMPLATE/config.yml | issue chooser (links play.md)                  | keep; update URL if play.md moves | same
.github/ISSUE_TEMPLATE/lead.yml   | archive lead form                              | keep                             | same
.github/ISSUE_TEMPLATE/play-report.yml | play report form                          | keep; add "Linux host" option to mode | same
```

**Duplicated content** (topic → where it appears now → single home):
- Windows setup (venv, fetch, wrapper, setup_game): README quick start, play.md §2-3, running-on-windows-11 §Setup, client-setup "Fresh extraction" → **play/README.md**; the others link to it.
- `prepare --station`, `check`, `launch`: in 10 docs → **reference/client-patches.md** (full) and play/README (one line).
- Firewall rules, `hosts` alias, Station-name 11-char limit, port troubleshooting (5031/5033/5034): play.md, lan-dogfight, vpn-dogfight, linux-host, local-server → **host/README.md** "common steps", with LAN/VPN/Linux pages holding only the differences.
- Host console commands, status file, crash restarts: lan-dogfight (refers to vpn), vpn-dogfight §Host console, host-control §Server console additions, linux-host → **host/console.md**.
- Match and round rules and defaults: play, lan-dogfight, first-playable-release, linux-host, README → one **defaults table in host/README.md** (D-15).
- Current status ("what works / unverified"): README Honest status, CONTEXT §2, play.md, CONTRIBUTING, linux-host, map-viewer, roadmap headers → **docs/STATUS.md** (new, the only place).
- Map list and playability: README, map-viewer, hosting-assets, level-data, host-control, custom-maps → **reference/maps.md**.
- House rules: CLAUDE.md, CONTRIBUTING, CONTEXT §9 Safety → **CONTRIBUTING.md**; CLAUDE.md links to it and adds agent-only rules.
- Test instructions and counts: tools/README, CONTRIBUTING, linux-host, roadmaps → **docs/contributing/testing.md** (or a section of CONTRIBUTING).

## 4. Recommendations

**Target tree**

```
README.md            front page: what it is, screenshots, 5-line status linking docs/STATUS.md, "start here" table, layout, licence
CONTEXT.md           ARCHIVE RESEARCH ONLY: asks, build table (all six), company/universe, revival, already-searched, next steps (dated), sources
CLAUDE.md            agent rules for the whole repo (see below)
CONTRIBUTING.md      how to help + the canonical house rules + testing + where docs go
NOTICE.md            unchanged
docs/
  README.md          index grouped by audience; each entry tagged guide/reference/log/roadmap
  STATUS.md          single "what works" matrix: feature | state (verified/partial/untested) | how verified | evidence link | date
  play/              README (install, offline, one-PC), launcher.md, texture-pack.md, map-viewer.md, troubleshooting
  host/              README (choose: one PC / LAN / VPN / Linux; common firewall+hosts+ports; defaults table),
                     lan.md, vpn.md, linux.md, host-control.md, console.md, server-reference.md
  create/            custom-maps.md, custom-objects.md, hype-reel.md
  reference/         client-patches.md, protocol.md, protocol-static.md, message-types.md (generated),
                     asset-formats.md, maps.md, versions.md
  research/          README (how logs work: dated, append-only, corrections link forward)
                     findings/ (split findings.md §9 with stable ids), log/ (CONTEXT §2 entries by date),
                     arena1a.md, arena1a-trials.md, level-data.md, code-clues.md, windows-11-compat.md,
                     rendering/{asteroids,pipeline-audit,offline-baseline}.md
  archive/           web-archive.md (and later: disc-search method, moved from CONTEXT §7)
  roadmap/           internet-server.md, modernization.md, authoritative-server.md (merged first-playable + gate)
  images/            unchanged
data/research-handoff-2026-10-20.txt   (moved from docs/history; tools updated)
```

**Who owns what (to stop the overlap)**
- **README**: never states a test count, map count or verification claim that isn't also in STATUS.md. Its "Honest status" becomes a summary of five bullets or fewer, linking STATUS.md.
- **docs/STATUS.md**: the only place where "verified / untested" is stated as current fact. Each row cites evidence. Guides link to the relevant row instead of restating it, which keeps "untested" visible. Updating it is part of any change that alters behaviour.
- **CONTEXT.md**: back to its original job, the archive-research record that CLAUDE.md's rules are about. It keeps the "update tables in the same session" rule. The dev changelog moves to `docs/research/log/`.
- **CLAUDE.md**: 1) a short description of what the repo now is (research + client patcher + stand-in host + asset tools + archive search); 2) where to read (STATUS for state, CONTEXT for archive work, docs/research for RE history); 3) agent-only rules (`-I`, download containment, archive.org politeness, (snippet) marking, AOA search pairing, never run installers, never commit game files, never link into ignored folders); 4) the test command (CI suite list / `verify_local.py`) and the Windows-only modules that cannot run on Linux; 5) a pointer to CONTRIBUTING for the house rules instead of copying them.
- **Research logs** stay dated and append-only, and corrections link forward, as 9.37→9.47 already does. **Guides** are undated and kept current. **Roadmaps** carry a "last reviewed" date and tick items with evidence links.

**Mechanical guards** (cheap, and they keep the new tree honest):
- Add `linkcheck.py` (scratchpad) to CI, failing on broken links and anchors and on links into `work/`, `game/`, `builds/`, `wb/`, `originals/`.
- Add a doc-command check to CI: extract `tools/*.py` invocations from docs and run `--help` for argparse tools. This only becomes safe after D-01 is fixed.
- Use stable explicit anchors for findings sections (`<a id="s9-47"></a>`) so retitling a dated heading cannot break links.
- When moving files, leave a one-line stub at each old path (findings.md, play.md, lan-dogfight.md, vpn-dogfight.md, linux-host.md) for one release. External links, issue templates (`config.yml`) and tool docstrings (`station_stub.py:13`, `start_lan_dogfight.ps1`, `fetch_known_builds.py`) point at them. Update the docstring references in `tools/` in the same change (8 doc paths are cited from code; two are already broken, D-07).
