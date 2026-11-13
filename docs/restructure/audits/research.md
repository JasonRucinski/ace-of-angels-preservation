# Audit: research, RE analysis, assets/maps tooling and data folders

Auditor area: the `tools/` files that are not server/host, client-patch or tests (archive research,
binary analysis/emulation, assets and maps, `tools/reel/`, `tools/README.md`), plus `config/`, `data/`,
`evidence/`, `manifest/`, `deploy/`, `docs/images/`. Repo state: branch `architecture-cleanup`.
Nothing in the repo was edited.

Scratch artefacts (help outputs, venv, regenerated files) are in
`/tmp/claude-0/-home-user-ace-of-angels-preservation/aa6c448b-b9bf-502a-a8dd-784488e1ac3d/scratchpad/arch/research/`.

> Side effect to note: while probing `--help`, two scripts contacted archive.org because they have no
> argument parsing (findings R1, R2). `fetch_known_builds.py --help` downloaded both installers (~61 MB)
> into a scratch directory named `--help/`, and `ia_fulltext_search.py --help` ran about 20 s of full-text
> queries before my 20 s timeout stopped it. I hashed the downloads (they match the manifest) and then deleted them.

## 1. Summary

- **CLI hygiene is the biggest user-facing problem.** I ran 70 scripts in this area with `--help` (requirements.txt installed in a scratch venv). **50 end in a Python traceback.** They unpack `sys.argv[1:N]` with no usage check. Only 16 use argparse (21 counting `reel/`). Three are dangerous rather than just unfriendly. `fetch_known_builds.py` and `ia_fulltext_search.py` treat `--help` as an output directory and start network work. `audit_object_lod.py` writes an empty report to a file called `--help` and exits 0.
- **The archive-research scripts do not follow CLAUDE.md's "pause and back off on 429" rule consistently.** Only `wayback_builds.py` and `restore_web_archive.py` do. There are 7 separate HTTP-GET copies with 4 different User-Agents.
- **Library and one-off code are mixed in the same files.** `emulate_codec.py` holds both the shared Unicorn `Emu` (imported by 25 modules) and a 2.7.1-only CLI with hard-coded VAs. The server runtime imports `audit_turret_groups`/`audit_warp_gates`, and through them `patch_client`, to get decoders and a hash constant. `navigation_buoys.py` reads committed `evidence/` at runtime.
- **`tools/README.md` is incomplete and partly wrong.** It omits 15 files. It claims analysis output "goes to the ignored `work\` folder and is never committed", but at least 8 scripts write or overwrite committed `evidence/` files, some of them dated files rewritten in place. It also claims player tools are stdlib-only, but `make_map`/`make_object`/`texture_pack` need capstone and pefile through `aoapack.builtin_key`.
- **Duplication:** 9 hard-coded copies of the 2.9.2 pristine SHA-256, plus 17 imports of `PRISTINE_292` from the client-patch module. Also 4 installer-member extractors, 3 `ReadProcessMemory` wrappers, 2 PE section mappers, 2 tagged-string scanners and about 10 copies of "pristine check, then Emu, then stop-hook". There are 129 `sys.path.insert` lines in tools/ (122 identical).
- **Data integrity is mostly good.** The manifest, CONTEXT.md, the download log, fetch_known_builds and an actual download all agree on hashes. All 11 `docs/images` hashes match SOURCES.md. Both `config/maps/crucible.json` and `config/objects/bennu.json` validate with their tools. Rebuilding crucible reproduces the TRN hash recorded in `custom_object_bennu_20261027.json`. `message_table.py` regenerates `docs/message-types.md` byte-for-byte.
- **Evidence provenance is weak.** About 45 committed evidence files are referenced by no doc or tool. Several have no generator in `tools/` at all: `asset-review/*-layouts.json` (the 2.8.0 and 2.8.2 copies are byte-identical), `*-download.json`, `arena1a-node-comparison.json`, `verification.json`, `code-clues.json` and `2.7.1/config_keys_looked_up.json`. There are 15 `local_gate_*` snapshots, the last from 23 Oct.
- **Area tests that nothing runs:** `test_reel` (game-free, 4 tests pass here), `test_navigation_buoys`, `test_turret_groups`, `test_turret_trial`, `test_warp_trial`, `test_warp_headless`, `test_object_lod` and `test_render_motion` are in neither CI nor `verify_local.py`. The last two error rather than skip when the game is absent.
- **Two broken doc references in tool docstrings:** `docs/file-formats.md` and `docs/protocol-notes.md` do not exist. `rar_img2iso.py` needs `libarchive-c`, which is not in `requirements.txt`.

## 2. Findings

Severity: H = breaks or misleads users or hits external services wrongly; M = misleads contributors or is
fragile design; L = cleanup.

| ID | Sev | Location | What is wrong | How verified | Suggested fix |
|---|---|---|---|---|---|
| R1 | H | `tools/fetch_known_builds.py:47-50` | Any single argument is taken as the output dir. `--help` (or a typo such as `-h`) downloads both installers (~61 MB) from archive.org into `./--help/`. | Ran `python3 -I tools/fetch_known_builds.py --help` from an empty scratch dir. It printed `OK v2.8.2… --help/v2.8.2…/aoa-current.exe` and created the files. sha256 9edcb537… / 90c4a47e… match `manifest/downloads.json`. | Use argparse with an explicit `--out`. Refuse names starting with `-`. Merge into the manifest-driven fetcher (R16). |
| R2 | H | `tools/ia_fulltext_search.py:11-36` (module-level code, no `main`) | No argument handling. `--help` becomes the output dir, but up to 30 archive.org full-text queries run *first*. The only pacing is a 1 s sleep between pages, with no 429 backoff (breaks the CLAUDE.md rule). It then crashes writing `--help/hits.json`, so the work is lost. Importing the module also runs it. | `--help` run hit my 20 s timeout mid-query. Source read. | Add `main()`, argparse and a shared `polite_get` with backoff. Write the output path before querying, or check that it exists first. |
| R3 | M | 50 scripts (list in §3 "CLI" column). Worst cases: `audit_object_lod.py:89-94`, `emulate_codec.py:129,210`, `emulate_warp_trial.py`, `pe_util.py` | Positional `sys.argv[1:N]` unpacking gives a `ValueError`/`IndexError` traceback instead of usage. `audit_object_lod.py` takes `argv[1]` as the output path, audits a hard-coded `work/2.9.2/export/AOAOBJECTS`, and when that is missing **writes `{"mesh_models": 0}` and exits 0**. `emulate_codec.py` exits 0 silently for any argument count other than 2 or 3. | Ran `--help` for all 70 scripts (outputs saved as `h2_*.out`). `audit_object_lod` created a file named `--help` containing empty JSON. | Use one CLI convention (argparse via a small `aoa.cli` helper). Exit non-zero on missing inputs. `audit_object_lod` should fail when the export folder is absent. |
| R4 | M | `tools/warp_trial.py:9-10`, `turret_trial.py:10`, `audit_warp_gates.py:17-19,168`, `audit_turret_groups.py:15-18`, `navigation_buoys.py:41` | The server runtime (`station_stub → warp_trial/turret_trial`) imports `hierarchy()`/`routes()` from **audit** scripts. Those import `patch_client` (client-patch stack) only for `PRISTINE_292`. `audit_warp_gates` lazily imports `station_stub`, which is a cycle. `navigation_buoys.map_placements` reads `ROOT/evidence/2.9.2/archives.json` at runtime, but `docs/linux-host.md:80` deploys only `tools` and `deploy`, so evidence-backed paths cannot work on the Linux host. | Read `imports.json` and the source lines. | Move scene-hierarchy and warp-route decoding into `aoa/formats/scene.py`/`aoa/maps`. Put hash constants in `aoa/known_builds.py`. Ship the expected ODB inventory as package data, not as evidence. **The server auditor should confirm the non-JRMAP navigation path on Linux.** |
| R5 | M | `tools/emulate_codec.py:1-10,85-130,133-211` | The shared `Emu` class (25 importers, all on 2.9.2) lives in a script whose CLI is **2.7.1-only**: hard-coded `0x60E820/0x60EB60/0x60EED0`, no hash check. A hidden 3-arg mode calls `ccomm_check(argv[1], argv[3], argv[2])` (argument order swapped, not in Usage). | Source read. `--help` exits 0 doing nothing. | Split into `aoa/emulation/emu.py` (library) and `archive/emulate_codec_271.py` (one-off whose results are frozen in `evidence/2.7.1/{codec,ccomm_framing}_emulation.json`). |
| R6 | M | `tools/pe_util.py:108-115` (and the 13 CLIs that take `<cache.pkl>`) | The disassembly cache is not tied to the EXE. Passing another build's `cache.pkl` silently gives wrong xrefs and functions. It is loaded with `pickle.loads`. | Source read. | Key the cache by the EXE's sha256 (`work/cache/<sha>.pkl`) and drop the positional cache argument. Optionally store it as JSON or marshal. |
| R7 | M | `tools/ia_fulltext_search.py:36`, `ia_fulltext_context.py:60,87`; `data/` | The scripts write and read `<dir>/hits.json` and `<dir>/contexts.txt`, and their docstrings say to run them on `data/`. The committed files are `data/ia_fulltext_hits.json` and `data/ia_fulltext_passages.txt`, so the documented `ia_fulltext_context.py data/` fails (no `data/hits.json`). | Source read. `ls data`. `--help` run showed `FileNotFoundError: '--help/hits.json'`. | Give explicit `--hits`/`--out` paths that default to the committed names. |
| R8 | M | `tools/README.md` (§"Analysing the client" and intro) | (a) "Output goes to the ignored `work\` folder and is never committed" is false. These write committed evidence by default: `audit_arena1a.py:91`, `audit_turret_groups.py:124`, `audit_warp_gates.py:214`, `audit_arena1a_rebuild.py`, `audit_map_nodes.py`, `audit_level_data.py:30`, `compare_version_assets.py:17`, `compare_client_resources.py:45`, `fetch.py:68`. Re-runs overwrite *dated* files such as `arena1a_audit_20261021.json`. (b) "Player-facing scripts need only the standard library" is false for `make_map install`, `make_object install` and `texture_pack`: `aoapack.builtin_key` imports `pe_util`, which imports capstone and pefile. (c) 15 files are missing (R12). | grep for output paths. Read `aoapack.py:56`, `make_map.py:185`, `make_object.py:258`. | Rewrite the index (generated from module docstrings, see §4). Audits should write to `work/` by default and take an explicit `--evidence PATH`. |
| R9 | L/M | `fetch.py:68`, `message_table.py:45-49`, `compare_version_assets.py:16-32`, `compare_client_resources.py:14-45` | Repo-relative paths depend on the working directory. Most other scripts use `ROOT = Path(__file__).parents[1]`. From another directory they fail, or `fetch.py` writes a stray `evidence/` there. | Ran from an empty dir: `FileNotFoundError: 'manifest/downloads.json'` and `'evidence/2.7.1/dispatch_4d1830.json'`. | Resolve everything from a single `aoa.paths.ROOT`. |
| R10 | L | `tools/rar_img2iso.py:6` | Needs `libarchive-c`, which is not in `requirements.txt` (only its docstring and CONTEXT.md mention it). | `ModuleNotFoundError: libarchive` in the venv built from requirements.txt. | Add an optional extra (`requirements-research.txt`) or import lazily with a clear message. |
| R11 | L | `tools/aoapack.py:3`, `tools/packet_sizes.py:11` | They reference `docs/file-formats.md` and `docs/protocol-notes.md`, neither of which exists. | `ls docs`. A scripted check of every `docs/*.md` path cited in tools found only these two. | Point to `docs/findings.md` sections, or write `docs/file-formats.md` (the aoapack docstring already holds most of it). |
| R12 | L | `tools/README.md` | Missing from the index: `navigation_buoys.py`, `verify_navigation_buoys.py`, `verify_turret_trial.py`, `verify_warp_trial.py`, `reel/bot.py`, `reel/scout.py`, `reel/client_mem.py`, `reel/shots.json`, `reel/edit.json`, plus (other areas) `dedicated_host.py`, `make_vessel_combat.py`, `turret_groups.py`, `turret_trial.py`, `vessel_combat.py`, `warp_trial.py`. Every file the index names exists, and its links resolve. `emulate_*`/`audit_*` are covered only by glob. | Scripted comparison of `ls tools` against the README. | Generate the index; see §4. |
| R13 | M | `.github/workflows/tests.yml`, `tools/verify_local.py:15-28` | Area tests that never run: `test_reel` (game-free; **4 tests pass on Linux**), `test_navigation_buoys`, `test_turret_groups`, `test_turret_trial`, `test_warp_trial`, `test_warp_headless` (all skip cleanly without the game), `test_object_lod` and `test_render_motion` (these **error** instead of skipping: `AssertionError`/`FileNotFoundError`). `emulate_cipher.py` and the `emulate_codec.py` CLI are not in the gate. | Ran each with the venv. Compared the names against both lists. | Add `test_reel` to CI now. Put the game-dependent suites in `verify_local`. Make missing-game a skip everywhere (shared `requires_game()` decorator). |
| R14 | L/M | 2.9.2 SHA literal in `aoapack.py:43`, `compare_render_clocks.py:44`, `emulate_motion_state.py:41`, `emulate_movement.py:33`, `emulate_reliable_history.py:130`, `emulate_station_aliases.py:70`, `emulate_station_request.py:79`, `gun_table.py:21`, `patch_client.py:36` | There are 9 literal copies, and 17 modules import `PRISTINE_292` from `patch_client`. `audit_arena1a_rebuild.py:27` and `compare_render_clocks.py:44` check it with `assert`, which `python -O` strips. | grep. | Add an `aoa/known_builds.py` holding the installer/client hashes, loaded from `manifest/downloads.json` or checked against it by a test. Add `require_build(path, "2.9.2")` that raises. |
| R15 | L/M | `evidence/` | Referenced by no doc and no tool (basename and glob-pattern search): `2.7.1/{config_keys_looked_up,config_records(.json/.txt),dialogs,installer_inventory,offline_refs,pe_facts,version_probe,world_offline_refs}.json`, `2.9.2/{asteroid_render_20261022,cipher_emulation,config_records(.json/.txt),dialogs,installer_inventory,object_persistence_review_20261027,pe_facts,render_clock_comparison,solid_world_render_20261022,station_detail_20261022,version_probe,visibility_fix_20261023,warp_headless_20261026,warp_trial_20261026,world_detail_20261022}.json`, 5 of the 15 `local_gate_*`, and `asset-review/{2.8.0-download,2.8.0-layouts,2.8.2-layouts,arena1a-node-comparison}.json`. **No generator exists in tools/** for `*-layouts.json` (2.8.0 and 2.8.2 are byte-identical), `2.8.0-download.json`, `arena1a-node-comparison.json`, `verification.json`, `code-clues.json` or `config_keys_looked_up.json`. Most evidence JSON does not record the command that made it. | Scripted `git grep` for each basename. sha256 duplicate scan. grep tools for distinctive keys (`older_only_names`, `versions_verified`, `selector_url`). | Add `evidence/INDEX.tsv` (file, generator command, input hashes, date, cited-by). Archive the superseded `local_gate_*` and dated duplicates. Remove the duplicate layouts file or record why both exist. |
| R16 | L/M | `fetch.py`, `fetch_known_builds.py`, `setup_game.ps1:18,28` | There are two downloaders. `fetch.py` is manifest-driven and uses sha256 plus a provenance log. `fetch_known_builds.py` has its own hard-coded list, checks MD5 only, takes 2.8.2 from archive.org while the manifest uses discmaster, and saves to `builds/v2.9.2_2004_FamilyGamePack3/aoa-current.exe`. The manifest's `suggested_local_filename` and the `setup_game.ps1` default `originals\2.9.2\aoa_2.9.2_installer_2.11.1.exe` use other names, so setup carries a fallback path. `fetch.py` raises `KeyError` for 2.8.0 (no `direct_url`). Hashes do agree everywhere (see §5). | Cross-checked the manifest, CONTEXT.md:462-465, `download_log.jsonl` and the actual download. | Use one `aoa research fetch VERSION --out DIR` driven by the manifest. Add mirrors and MD5 to the manifest. Use one on-disk naming scheme. |
| R17 | L | `tools/restore_web_archive.py:211-215` | HTTP 429/503 marks the row `missing`, so a throttle permanently drops the page from normal resumes (it is only retried with `--retry-missing`). Its inputs `work/wayback-{site,forum}-index.json` and `wayback-forum-versions.json` have no generator. The CDX query exists only as prose in `docs/private-web-archive.md:13`, while `wayback_builds.py` runs a different CDX query. | Source read. | Leave throttled rows `pending`. Add a `cdx` subcommand that produces the index files, shared with `wayback_builds`. |
| R18 | L | `tools/ia_disc_find.py:28-53` | No pause between archive.org requests and no 429 backoff. CLAUDE.md requires the result to be logged in `data/disc_search.tsv`, but the tool does not write it. | Source read. | Use the shared `polite_get`. Add `--log data/disc_search.tsv` that appends the listed count and hit status. |
| R19 | L | `tools/wise_extract.py:52-58`; CONTEXT.md §8 | CONTEXT.md says it does a "CRC check", but a mismatch only prints a warning and the file is still written. | Source read. | Write to `name.crc-bad`, or fail without `--force`. |
| R20 | L | `tools/inventory.py:28-35` | It needs a handoff text with an "Appendix C" for the given version (only `docs/history/2026-10-20-research-handoff.txt` has one). For any other version `m` is None and it crashes with `AttributeError`. It duplicates `wise_extract`/`make_install`/`compare_version_assets` member extraction. | Source read. | Make the Appendix C comparison optional and fold it into a shared installer reader. Its output is already frozen in `evidence/*/installer_inventory.json`, so the CLI can be archived. |
| R21 | L | `inspect_arena.py:14-29`, `measure_frame_pacing.py:37-60`, `reel/client_mem.py:24-56` | Three copies of an OpenProcess/ReadProcessMemory wrapper. The 2.9.2 addresses `0x5E7728/0xD32AC/0x3B0/0x5E8E5C` are duplicated with no build check. `measure_frame_pacing.Process.read` reuses a fixed 64-byte buffer, so a read larger than 64 bytes would overflow (current callers read ≤12). | Source read (Windows-only, not run). | Add one `aoa/live/procmem.py` with `Process.read/u32/write`, sized buffers, and a check of the PE timestamp in the target's memory. Put the addresses in `aoa/live/addresses_292.py`. |
| R22 | L | Many audit/emulate scripts | The pattern "hash check, then `Emu(PE(client))`, then a `stop()` hook on an address set" is copy-pasted: `audit_turret_groups.py:60`, `audit_warp_gates.py:42-58`, `audit_arena1a_rebuild.py:25-36`, `emulate_motion_state.py:40`, `emulate_movement.py:32`, `emulate_reliable_history.py:129`, `emulate_station_aliases.py:69`, `emulate_station_request.py:78`, and the others. | Source read. | `Emu.for_build(path, "2.9.2")` plus `emu.stop_at({...})`. |

## 3. File classification (every file in the area)

CLI column: **ap** = argparse; **argv** = positional `sys.argv` (traceback on `--help`); **none** = no CLI
(library, or a fixed-path script); **mod** = module-level code. "HC" = hard-coded repo paths or
single-version addresses.

`path | role | CLI / HC | verdict | proposed home`

**Archive research**
- `tools/fetch.py | download+verify one manifest entry, provenance log | argv; cwd-relative evidence/ | merge (with fetch_known_builds) | aoa/research/fetch.py`
- `tools/fetch_known_builds.py | download the 2.8.2/2.9.2 installers, MD5 | argv (R1); hard-coded URL list | merge into fetch | aoa/research/fetch.py`
- `tools/ia_disc_find.py | list archive.org disc-image contents, grep | ap | keep | aoa/research/ia_disc.py`
- `tools/ia_fulltext_search.py | archive.org OCR full-text search | mod (R2) | merge with context into one CLI | aoa/research/ia_fulltext.py`
- `tools/ia_fulltext_context.py | fetch OCR, extract passages | mod (argv) | merge | aoa/research/ia_fulltext.py`
- `tools/iso_stream_extract.py | stream files out of an ISO on stdin | mod (argv) | keep | aoa/research/disc_image.py`
- `tools/rar_img2iso.py | raw CD .img in RAR to ISO (libarchive) | mod (argv) | merge | aoa/research/disc_image.py`
- `tools/wayback_builds.py | Wayback CDX listing + build download | ap | keep (share CDX/HTTP) | aoa/research/wayback.py`
- `tools/restore_web_archive.py | rebuild private site/forum mirror | ap; ROOT-relative wb/, work/ inputs | keep | aoa/research/web_archive.py`
- `tools/wise_extract.py | list/extract a Wise installer | argv | keep CLI, lib to formats | aoa/formats/installer.py + aoa/research/cli`
- `tools/inventory.py | installer inventory vs handoff Appendix C | argv | archive (output frozen in evidence/*/installer_inventory.json) | archive/research/`
- `tools/explore.py | interactive static exploration (str/xref/dis) | argv | keep | aoa/analysis/explore.py`

**Binary analysis / RE**
- `tools/pe_util.py | PE mapping + capstone sweep + xrefs (library) | none | keep, split PE (stdlib) from Disasm | aoa/formats/pe.py + aoa/analysis/disasm.py`
- `tools/pe_facts.py | dump PE identity facts | argv | archive (frozen: pe_facts.json; referenced only by README) | archive/analysis/`
- `tools/aoa_version.py | compiled-in version, stdlib only | argv (usage on wrong count) | keep; its PE mapper becomes formats/pe | aoa/research/version.py`
- `tools/version_probe.py | version globals via capstone | argv | merge into aoa_version (`--detail`) | aoa/research/version.py`
- `tools/match_funcs.py | masked-signature function matching across builds | argv | keep (reusable for new builds); doc it | aoa/analysis/match_funcs.py`
- `tools/dispatch_table.py | MSVC switch table extraction | argv | keep | aoa/analysis/dispatch_table.py`
- `tools/message_table.py | merge dispatch/send evidence into docs/message-types.md | argv; cwd-relative evidence paths | keep (reproducible, verified) | aoa/analysis/message_table.py`
- `tools/packet_sizes.py | "SFoo (%d)" size diagnostics | argv; broken doc ref | keep | aoa/analysis/packet_sizes.py`
- `tools/send_sites.py | outgoing packet construction sites | argv | keep | aoa/analysis/send_sites.py`
- `tools/server_senders.py | 2.7.1 server-side senders (findings 9.43) | argv | archive (one-off, frozen in 2.7.1/server_senders.json) | archive/analysis/`
- `tools/offline_refs.py | readers of the offline flag | argv | archive (frozen; referenced only by README) | archive/analysis/`
- `tools/config_records.py | name/float config records | argv | archive (frozen in config_records.*) | archive/analysis/`
- `tools/dialogs.py | RT_DIALOG templates (pefile) | argv | keep (generic) | aoa/analysis/dialogs.py`
- `tools/gun_table.py | 2.9.2 static gun table | argv; HC 2.9.2 VAs + hash | archive (frozen gun_table.json consumed by make_vessel_combat) | archive/analysis/`
- `tools/measure_frame_pacing.py | live frame pacing sampler; also lib for test_frame_clock | ap; HC 2.9.2 addresses | keep | aoa/live/frame_pacing.py`
- `tools/sample_rendering.py | live render-object sampler | ap; via inspect_arena | keep | aoa/live/`
- `tools/emulate_codec.py | **library** Emu (25 importers) + 2.7.1 codec/CComm CLI | argv (silent exit 0) | split: Emu → library, CLI → archive (R5) | aoa/emulation/emu.py + archive/emulation/`
- `tools/emulate_cipher.py | aoacrypt vs client cipher | argv | archive (frozen *_cipher_emulation.json, not in gate) | archive/emulation/`
- `tools/emulate_archive_terminator.py | gate check, archive terminator | argv; HC 2.9.2 | keep (in verify_local) | aoa/emulation/checks/`
- `tools/emulate_client_extensions.py | gate check | argv; HC | keep | aoa/emulation/checks/`
- `tools/emulate_motion_state.py | gate check; lib for test_warp_headless | argv; HC | keep | aoa/emulation/checks/`
- `tools/emulate_movement.py | gate check | argv; HC | keep | aoa/emulation/checks/`
- `tools/emulate_ordered_events.py | gate check | argv; HC | keep | aoa/emulation/checks/`
- `tools/emulate_reliable_history.py | gate check | argv; HC | keep | aoa/emulation/checks/`
- `tools/emulate_station_aliases.py | gate check | argv; HC | keep | aoa/emulation/checks/`
- `tools/emulate_station_request.py | gate check | argv; HC | keep | aoa/emulation/checks/`
- `tools/emulate_terrain_nodes.py | gate check (imports audit_arena1a) | argv; HC | keep | aoa/emulation/checks/`
- `tools/emulate_warp_trial.py | headless warp emulation (library for test_warp_headless) | none (exit 0) | keep as lib | aoa/emulation/warp.py`
- `tools/audit_arena1a.py | Arena1a audit → dated evidence | none; HC game/,work/,evidence/ | archive (frozen arena1a_audit_20261021) | archive/audits/`
- `tools/audit_arena1a_rebuild.py | gate probes for the rebuild → evidence | ap; HC | archive (frozen) | archive/audits/`
- `tools/audit_level_data.py | cross-version level-data summary | none; HC | archive (frozen level-data.json) | archive/audits/`
- `tools/audit_map_nodes.py | map node review → evidence | none; HC | archive | archive/audits/`
- `tools/audit_object_lod.py | LOD audit; lib for 4 tests | argv (silent empty success, R3) | keep lib part | aoa/maps/lod.py`
- `tools/audit_render_pipeline.py | render pipeline emulation; lib for 2 tests | argv; HC 2.9.2 + offline-baseline | keep lib, archive CLI | aoa/emulation/render.py`
- `tools/audit_turret_groups.py | turret groups; **`hierarchy()` used by the server** | ap; HC | split: hierarchy → formats/scene, CLI → archive | aoa/formats/scene.py`
- `tools/audit_warp_gates.py | warp gates; **`routes()` used by the server** | ap; HC | split: routes → maps, CLI → archive | aoa/maps/warp_routes.py`
- `tools/compare_client_resources.py | PE resources across versions | none; cwd-relative | archive (frozen client-resources.json) | archive/audits/`
- `tools/compare_render_clocks.py | render clock emulation; lib for test_render_motion | argv; HC + `assert` hash | keep lib | aoa/emulation/render.py`
- `tools/compare_version_assets.py | verify 6 builds, decode, compare to 2.9.2 | none; cwd-relative; reads originals/,builds/ | keep (reusable for new builds), add CLI | aoa/research/version_assets.py`

**Assets and maps**
- `tools/aoapack.py | .aoa archive reader/writer + CCompress (library + CLI) | argv | keep | aoa/formats/aoapack.py`
- `tools/aoacrypt.py | packet/archive cipher (library + selftest) | argv | keep | aoa/formats/aoacrypt.py`
- `tools/export_assets.py | archive export, TGA→PNG; png() reused | argv | keep | aoa/maps/export.py + aoa/formats/image.py`
- `tools/export_legacy_models.py | 2.0.0 model export | argv | keep | aoa/maps/export_legacy.py`
- `tools/gob2obj.py | Gob mesh parser + tagged strings (core lib, 10 importers) | argv | keep | aoa/formats/gob.py`
- `tools/scene2obj.py | layout/scene nodes → OBJ (lib, 10 importers) | ap | keep | aoa/formats/scene.py + aoa/maps/export.py`
- `tools/sco_dump.py | .Sco decoder | argv | keep | aoa/formats/sco.py`
- `tools/render_obj.py | software OBJ renderer to PNG | ap | keep | aoa/maps/render.py`
- `tools/render_map_previews.py | HTML gallery of map previews | ap; HC work/2.9.2 defaults | keep | aoa/maps/render.py`
- `tools/decode_trn.py | .TRN decoder (server+client lib) | argv | keep | aoa/formats/trn.py`
- `tools/decode_scenario.py | SCENARIOS decoder | argv | keep | aoa/formats/scenario.py`
- `tools/decode_legacy_layout.py | legacy layout decoder (re-implements tag scan) | argv | merge into formats/scene | aoa/formats/scene.py`
- `tools/arena_inventory.py | scene/scenario inventory | argv | archive (frozen arena_inventory.json) | archive/audits/`
- `tools/inspect_arena.py | live 2.9.2 player-slot snapshot (lib for 5 tools) | argv; HC addresses | keep | aoa/live/arena.py`
- `tools/check_arena_geometry.py | CTF_arena OBJ sanity check | none; HC work/ | archive | archive/audits/`
- `tools/make_map.py | build/install/serve custom maps | ap (subcommands) | keep (model CLI) | aoa/maps/make_map.py`
- `tools/make_object.py | glTF → Gob/Sco into ODB | ap (subcommands) | keep | aoa/maps/make_object.py`
- `tools/navigation_buoys.py | server navigation placements (lib; reads evidence at runtime) | none | keep, move evidence dependency into package data | aoa/maps/navigation.py`
- `tools/verify_navigation_buoys.py | live check vs map_viewer tour evidence | ap; HC evidence path | keep | aoa/live/verify/`
- `tools/verify_turret_trial.py | live turret trial check | ap | keep | aoa/live/verify/`
- `tools/verify_warp_trial.py | live warp trial check; imported by test_warp_trial | ap | keep | aoa/live/verify/`
- `tools/verify_local.py | regression gate runner (tests area) | ap | keep | tests/`

**Highlight reel** (Windows, ffmpeg; `test_reel` passes but is not run)
- `tools/reel/record.py | film scripted shots | ap; HC game/2.9.2 | keep | aoa/reel/`
- `tools/reel/edit.py | cut the reel with ffmpeg | ap | keep | aoa/reel/`
- `tools/reel/bot.py | scripted synthetic pilots | ap | keep | aoa/reel/`
- `tools/reel/scout.py | map scouting + F5 capture | ap | keep (add to README) | aoa/reel/`
- `tools/reel/client_mem.py | live memory poke for camera/velocity | ap; HC 2.9.2 + patched-cave VAs | keep, use shared procmem | aoa/reel/ + aoa/live/procmem.py`
- `tools/reel/window.py | window find/send messages | ap | keep | aoa/live/window.py`
- `tools/reel/shots.json`, `tools/reel/edit.json | reel scripts (data) | – | keep | aoa/reel/ data`
- `tools/README.md | index | – | regenerate | docs/tools.md (generated)`

**Data folders**
- `config/client-2.9.2.json | pinned bundle hashes (prepare_client) | keep | config/`
- `config/texture-pack.json | texture pack manifest | keep | config/`
- `config/maps/crucible.json | custom map spec. Validates (`make_map.py build` → 113 records, sha256 2c63c665… = `custom_object_bennu_20261027.json`). `custom_map_crucible_20261027.json` records an older spec hash (980550…, 89 records): dated, not wrong | keep | config/maps/`
- `config/objects/bennu.json | custom object spec; `make_object.load_spec` OK; sha256 = bennu evidence | keep | config/objects/`
- `data/disc_search.tsv | disc search log (manual) | keep; let ia_disc_find append | data/`
- `data/ia_fulltext_hits.json`, `data/ia_fulltext_passages.txt | full-text search output; names do not match the script output (R7). hits.json is referenced by nothing | keep, fix names | data/`
- `data/magazine-mentions.md | curated magazine table | keep | data/ or docs/`
- `manifest/downloads.json | 6-build source/hash manifest; agrees with CONTEXT.md, download_log and a real download | keep, make it the single hash source | manifest/`
- `deploy/linux/* | systemd unit + examples (CI verifies the unit) | keep | deploy/`
- `docs/images/* | README images; all 11 sha256 match SOURCES.md | keep | docs/images/`
- `evidence/download_log.jsonl | fetch.py provenance; 7 rows, all verified and matching the manifest | keep | evidence/`
- `evidence/2.7.1/*` (19), `evidence/2.9.2/*` (≈80), `evidence/asset-review/*` (20), `evidence/code-clues.json | frozen results | keep; add INDEX with generator commands; archive the 15 local_gate_* snapshots and superseded dated duplicates (warp_headless_20261026 vs _20261027); dedupe 2.8.0/2.8.2-layouts (R15) | evidence/ + evidence/archive/`

## 4. Recommendations for the redesign

1. **Make it a package with one CLI convention.** Create `aoa/` (stdlib-importable) with `python -m aoa.<area>.<tool>` entry points. That removes the 129 `sys.path.insert` lines and makes `python -I` work without them. Use a tiny `aoa/cli.py` (argparse plus `ROOT`-relative defaults, non-zero exit on missing input, and "requires game file X" messages instead of tracebacks).
2. **Proposed layout for this area:**
   - `aoa/formats/`: `pe.py` (stdlib section mapper, from `aoa_version`/`pe_util.PE`), `aoapack.py`, `aoacrypt.py`, `gob.py`, `sco.py`, `scene.py` (scene2obj nodes, `hierarchy()` from audit_turret_groups, legacy layout), `trn.py`, `scenario.py`, `image.py` (TGA/PNG), `installer.py` (one member iterator with one sanitiser for wise_extract, inventory, make_install and compare_version_assets).
   - `aoa/known_builds.py`: client/installer hashes and per-build VAs (key VA, etc.), loaded from or tested against `manifest/downloads.json`. Remove the 9 literal hash copies and the analysis code's dependency on `patch_client`.
   - `aoa/research/`: `http.py` (`polite_get`: one UA, pacing, exponential backoff on 429/5xx, `Retry-After`), `fetch.py` (manifest-driven, merges both downloaders), `ia_disc.py`, `ia_fulltext.py`, `wayback.py` (CDX shared with web_archive), `web_archive.py`, `disc_image.py`, `version.py`, `version_assets.py`.
   - `aoa/analysis/`: `disasm.py` (cache keyed by EXE sha), `explore`, `match_funcs`, `dispatch_table`, `packet_sizes`, `send_sites`, `message_table`, `dialogs`.
   - `aoa/emulation/`: `emu.py` (`Emu.for_build`, `stop_at`), `render.py`, `warp.py`, `checks/` (the 9 gate emulators with a uniform `run(client) -> report` interface that `verify_local` calls in-process).
   - `aoa/maps/`: `export.py`, `render.py`, `make_map.py`, `make_object.py`, `navigation.py`, `warp_routes.py`, `lod.py`. The server imports from here, never from audit scripts.
   - `aoa/live/` (Windows): `procmem.py`, `addresses_292.py`, `arena.py`, `frame_pacing.py`, `window.py`, `verify/`. `aoa/reel/` sits on top.
   - `archive/` (not importable by runtime code; kept for reproducibility): `pe_facts`, `server_senders`, `offline_refs`, `config_records`, `gun_table`, `inventory`, `emulate_cipher`, the 2.7.1 `emulate_codec` CLI, `audit_arena1a*`, `audit_level_data`, `audit_map_nodes`, `arena_inventory`, `check_arena_geometry`, `compare_client_resources`, and the CLIs of audit_turret_groups/warp_gates.
3. **Evidence discipline.** Audits write to `work/` by default and to `evidence/` only with `--evidence`. Every evidence JSON gets a `generator` block (`command`, `tool_git_sha`, input sha256s). Add `evidence/INDEX.tsv` and a test that every evidence file is listed and every listed generator exists. Move the 15 `local_gate_*` snapshots to `evidence/archive/`.
4. **Network etiquette as code.** All archive.org and Wayback access goes through `aoa.research.http.polite_get`. Add a unit test with a fake opener that asserts it backs off on 429 and that no network happens on `--help`.
5. **Tests.** Add `test_reel` to CI. Make every game-dependent test skip through one helper. Move `test_navigation_buoys`/`turret*`/`warp*`/`object_lod`/`render_motion` into `verify_local`. Add CLI smoke tests (`--help` exits 0 for every entry point).
6. **Docs.** Generate the tools index from module docstrings (`python -m aoa.tools_index > docs/tools.md`). Drop the second, partial tool table in CONTEXT.md §8 or link to the index. Fix the two broken doc references. Put `libarchive-c` in an optional research requirements file.

## What I did NOT check

- I did not run any Windows-only code (`inspect_arena`, `measure_frame_pacing`, `sample_rendering`, `verify_*` live paths, `reel/record|scout|client_mem|window`, ctypes paths); I only read it.
- I did not check whether committed evidence reproduces from game files (none are present), except `message_table.py` (identical output) and `make_map build` (matches the Bennu evidence hash).
- I did not run the network tools on purpose. The only live contact was the accidental `--help` runs in R1/R2. I did not check whether archive.org URLs in the manifest are still live, apart from the two installers fetched in R1.
- Server, client-patch and test-area files were looked at only where this area depends on them (R4, R13, R14). I did not review `crashdbg.py`, `map_viewer.py` or `make_vessel_combat.py` beyond their references.
- I did not check the contents of `docs/findings.md` claims against evidence values.

## Execution log and cleanup (after the architect's safety correction)

I ran these **before** the correction arrived. All runs used a scratch working directory
(`.../scratchpad/arch/research/empty/`), not the repository root.
- I ran `python3 -I tools/<x>.py --help` for all 72 area scripts (system Python). I ran it a second time for 70 of them with a scratch venv that has requirements.txt installed. `fetch_known_builds.py` and `ia_fulltext_search.py` were excluded from the second pass.
  - `fetch_known_builds.py --help` downloaded both installers (~61 MB) from archive.org into the **scratch** dir `empty/--help/`. I hashed them (they match the manifest) and deleted them.
  - `ia_fulltext_search.py --help` sent live archive.org full-text queries for about 20 s until my timeout killed it. Nothing was written.
  - `audit_object_lod.py --help` wrote an empty-report file named `--help` in the **scratch** dir. Deleted.
  - `audit_level_data.py --help` crashed with `KeyError: 'jrmap_trn'` in my runs, before any write. Several scripts use ROOT-relative output paths, but every other one crashed on missing `game/` or `work/` input first.
- I ran these tests with the scratch venv: `test_reel`, `test_navigation_buoys`, `test_object_lod`, `test_render_motion`, `test_scene_nodes`, `test_turret_groups`, `test_warp_trial`, `test_turret_trial`, `test_warp_headless`.
- `make_map.py build config/maps/crucible.json <scratch>/crucible.trn` and `message_table.py <scratch>/mt.md` wrote their output to scratch only.
- **Repo check after the correction:** `git status --short` is empty, so no tracked file was modified (evidence/ is intact). `git status --short --ignored` shows `tools/__pycache__/` (being written at 14:51 by another agent; left alone) and `wb/` (dated 2026-10-26, pre-existing; not mine). I **deleted `tools/reel/__pycache__/`**, which my `reel/bot.py --help` and `test_reel` runs created at 14:43. Nothing else in the repo was created by me.
- After the correction I did not run anything else and made no network contact.
