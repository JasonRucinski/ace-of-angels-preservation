# Audit: client patching and client setup stack

Auditor scope: `tools/prepare_client.py` and every module it composes, the standalone patch CLIs, the
offline experiments, the Windows setup path (`setup_game.ps1`, `make_install.py`, `install_wrapper.py`,
`register_activeskin.ps1`, `client_launcher.*`, `client_login.ps1`), `crashdbg.py`, `pe_util.py`, the texture
pack tools, their tests, and the client docs (client-setup, play, running-on-windows-11, texture-pack,
client-extension-gate, offline-rendering-baseline, asteroid-rendering, render-pipeline-audit, findings 9.36+).
Read-only; nothing in the repo was changed (`git status` clean).

How I verified things:
- **Address map:** a scratch script imports every patch module and lists the exact byte ranges each one
  writes, then reports any overlaps. Script: `scratchpad/arch/client/regions.py`.
- **Synthetic client image:** a fake "stable" image has every module's original bytes at its sites, and its
  hash is monkeypatched into `STABLE_SHA256`. With it I ran the real `prepare_client.prepare/configure/inspect`,
  `texture32.install`, `object_persistence.install`, the `asteroid_render.main` flow and
  `client_launcher.read_settings` without game files. Script: `scratchpad/arch/client/sim.py`.
- **Tests:** I ran the test suites in a scratch venv with capstone, unicorn, pefile and Pillow installed.
  Windows-only code (PowerShell, ctypes, tkinter) was read, not run.

---

## 1. Summary

- **There are 22 patch IDs and no shared interface.** They come from 18 modules plus inline code in
  `prepare_client.py`. I count 6 distinct interface shapes. Adding one patch means editing at least 9 places:
  `inspect()` twice, `configure()` signature, strip and apply in `configure()`, `prepare()` signature and its
  positional call, `main()` flag and mapping, `client_launcher.PATCHES`. Ordering is implicit.
  `physics_timestep` and `local_station` check the whole-image hash, so every other patch must be stripped
  before they can run.
- **No two patches write the same bytes unless they are declared alternatives.** asteroid vs solid-world
  share 0x543222, and station vs world detail share 0x546BE4; `prepare_client` rejects both pairs together.
  Two overlaps are hidden:
  - **Shared constants (semantic overlap):** `distant-world-objects-v1` rewrites the 61000.0 and 900000.0
    constants that the asteroid and solid-world caves read. With distant objects on, both "900,000"
    horizons become 4,500,000. The docs say each constant has one code reference.
  - **Shared .data block (by convention):** `own-ship-menu-model-v1`'s state byte sits inside
    `third-person-camera`'s .data block. The two modules interleave addresses by comment, not by any shared
    allocator.
- **High: running any patch tool silently resets the user's launcher choices.**
  - **Cause:** `prepare()` forces 5 options ON (frame clock, visibility math, chase camera, power-ups,
    menu framing) but preserves the others.
  - **What resets them:** the plain `prepare` command that play.md tells LAN/VPN players to run, and
    `texture32.py`, `station_detail.py`, `world_detail.py`, `solid_world_render.py` and `asteroid_render.py`.
    `object_persistence.py` passes four of the five options through, but not menu framing.
  - **Worse case:** `asteroid_render.py` and `object_persistence.py` raise "verification failed" after the EXE
    has already been rewritten.
  - **Proof:** reproduced on the synthetic image.
- **The undo/backup story is fragmented.** There are 13 backup suffixes and 13 side-record JSONs. Six
  standalone tools each keep their own `.EXE.before-*` exact-undo backup plus a `_*.json` record. Nothing reads
  those records, and they go stale as soon as the launcher changes anything.
- **Patch version 22 matches the docs, but the number is cosmetic.** `PATCH_VERSION` is written to the setup
  record and never read. `check()` enforces a set of patch IDs instead. There is no version→patch table:
  versions 4–10 (protection, menu framing, the rendering options) are not documented anywhere.
  `client-setup.md` still publishes a "prepared localhost executable" hash from patch version 12.
- **No documented CLI flag is missing from the code.** The reverse gap exists: five options (asteroid, solid,
  station detail, world detail, texture32) have no `prepare_client` flag. They are reachable only through
  separate tools or the GUI.
- **The "experiment" modules are superseded.**
  - `render_clock_experiment`'s cave is byte-identical to `frame_clock`'s clock cave.
  - `render_culling_experiment`'s angle cave matches `visibility_fix` byte for byte. Its 347-byte cave also
    overlaps the online-terrain region.
  - They, `seed_offline_velocity` and `prepare_offline_baseline` only work on the hard-coded
    `game/offline-baseline-2.9.2` folder.
  - The legacy CLIs of `patch_client`, `local_station` and `physics_timestep` write the EXE with no record,
    which breaks a prepared client.
- **Test coverage of this area is mostly illusory in CI.**
  - **CI:** `test_prepare_client` runs 8 tests and skips all 8; `test_client_launcher` skips 5 of 6.
  - **Without the user's client:** 15 suites error instead of skipping.
  - **Never run:** `test_physics_timestep` (an argv script, not unittest), `test_menu_aspect`,
    `test_render_clock_experiment` and `test_render_motion` are in neither CI nor `verify_local.py`.
- **The player path has 6 manual downloads/steps and several silent-failure points.** For example: a
  mistyped `-Wrapper` silently falls back to native DirectX; `client_launcher.cmd` hides Python start-up errors
  behind `pythonw`. The scripts also disagree on which Python to use: `setup_game` falls back to system
  `python`, while the `.cmd` requires `.venv`.

---

## 2. Findings

Severity: H = breaks users or silently changes their state, M = misleads contributors or is a latent
breakage, L = consistency or cleanup.

| ID | Sev | Location | What is wrong | How verified | Suggested fix |
|---|---|---|---|---|---|
| C1 | H | `prepare_client.py:149,269` (defaults `smooth_frame_clock=True … menu_framing=True`, versus `experimental_*=None`, `distant_objects=None`) | Mixed defaults. Five options are forced ON by every `prepare` that does not name them; the other six are preserved. The plain `prepare … --station aoalan --no-experimental-protection` in `play.md:110`, `lan-dogfight.md:88` and `vpn-dogfight.md:108` silently re-enables anything the player turned off in the launcher. | sim.py: prepare(chase off), then prepare(host="aoalan") gives chase ON. | Default every option to `None` (= preserve installed state). Apply defaults only when the input is pristine or freshly extracted (state has no options yet). |
| C2 | H | `asteroid_render.py:72-81`, `object_persistence.py:107-117` | The tool computes `result = configure(source, X)` (its own bit only), then calls `prepare_client.prepare()`, which resets the forced-on options (C1). The verification `exe.read_bytes() != result` then raises **after** the EXE and `_client_setup.json` were rewritten. `asteroid_render.main` has no try/except, so the user gets a traceback. | sim.py: chase off, then the asteroid flow prints "FAIL (exe already rewritten, chase re-enabled=True)". `object_persistence.install` with menu framing off fails with "distant-object verification failed" and menu framing is left ON. | Delete these per-tool installers; route all toggles through one `prepare(options=…)` that preserves unspecified options (see §4). |
| C3 | H | `texture32.py:61-74`, `station_detail.py:66-79`, `world_detail.py:57-77`, `solid_world_render.py:44-64` | Same root cause as C1, but these tools compute `expected` with `prepare_client.configure()` defaults, so verification passes and the launcher choices are **silently** reset. `texture-pack.md` step 3 sends every texture-pack user through `texture32.py`. | sim.py: chase off, then `texture32.install`, then chase ON. | As C2. Have texture-pack.md use `prepare --texture32` or the launcher checkbox. |
| C4 | M | `object_persistence.py:61-66` vs `asteroid_render.py:28,37` / `solid_world_render.py:20` | Semantic overlap on data constants. `distant-world-objects-v1` rewrites 0x5B0C30 (61000.0 → 4.5e6) and 0x59D9C0 (900000.0 → 4.5e6). The asteroid cave and the solid-world in-place patch read exactly those constants. Combined, asteroid-only and solid-world modes both become 4.5M horizons, and the "900,000" in their docs and launcher labels no longer holds. `asteroid-rendering.md:221` says "The distance constants have one code reference each", which is true only of the original image. | `regions.py` plus sim.py: configure(distant+solids) gives both constants 4500000.0. | Have the registry declare the constants each patch *reads* as well as writes, and test the interaction. Alternatively, give distant-objects its own constants in the cave instead of editing shared ones. Document the interaction. |
| C5 | M | `third_person.py:116-121`, `own_ship_menu.py:51` | Interleaved .data-tail ownership. third_person's block FAKE..ARMED (0x60D300–0x60D3F9) contains own_ship_menu's RESTRICT (0x60D3EC = TICK+8). third_person leaves a hole for it by comment (`ORBIT = TICK + 0xC # after own_ship_menu's RESTRICT`). The .text caves are allocated the same way: each module hard-codes its neighbour's start in a comment or literal assert. Some modules have no bound check at all: archive_terminator, explicit_protection, physics, asteroid, station. | `regions.py` overlap report. | Keep one `layout.py` table of cave and data reservations. Add a game-free test asserting that all registry regions are disjoint (except declared alternatives) and inside .text padding [0x58B200, 0x58C000) and the .data tail [0x60D200, 0x60E000). `regions.py` is a ready starting point. |
| C6 | M | `prepare_client.py:76-201` | The composition is hand-ordered. `inspect()` strips 18 patches in one order and `configure()` strips in another. Then `physics_timestep.configure()` must run on a fully stripped image, because it (and `local_station`) assert `STABLE_SHA256` internally. `prepare()` calls `configure()` with 14 **positional** arguments (line 281), so inserting a parameter silently shifts meanings. | Read the code. | Registry-driven strip/apply (see §4). Pass keyword arguments, or a single `options` dict. |
| C7 | M | `prepare_client.py:110,128-146` | Five patch IDs are hard-coded strings with no owning module or `NAME`: `logger-size-v1`, `logger-lock-v1`, `zero-time-physics-v1`, `background-network-v1`, `archive-terminator-v1`. The background patch lives inline in `prepare_client`. The two logger patches are "detected" only through the whole-image hash, so they are always reported, and `patch_client` has no state or undo. | Read the code; grep for `NAME` across modules. | Give each its own module or registry entry with `id`, `regions()`, and an `always=True` policy. |
| C8 | M | `third_person.py:240-246`, `own_ship_menu.py:113-119`, `prepare_client.py:142-144` | `state()` returns True for **any** variant, so `inspect()` reports `third-person-camera-v3` for a client still carrying the v1 or v2 cave, and `own-ship-menu-model-v1` for its legacy cave. `check()` therefore passes on stale camera code. The launcher shows it as current. Contrast `online_terrain`, which reports its true variant via `installed_name()`. | sim.py: a v1 cave is reported as `['third-person-camera-v3']`. | Use one variant convention for all modules: `state()` returns the installed variant ID or None. |
| C9 | M | `client_launcher.py:27-38,93`, `prepare_client.py:172-175` | The launcher has no control for `explicit-protection-v1`, which is preserved. A player with protection installed who types a non-loopback Station in the launcher gets "experimental protection requires a loopback Station", and the GUI offers no fix. `client-setup.md:56` says adding an entry to `PATCHES` "supplies their checkbox, installed-state detection and explicit on/off setting". In fact `prepare()` also needs a kwarg with the same name, so the registry is not self-sufficient. | sim.py; read the code. | Derive both the launcher and the CLI from the same registry. Either show protection, or have the launcher pass `experimental_protection=False` whenever the Station is not loopback. |
| C10 | M | `prepare_client.py:38,293`; `client-setup.md:93-100`; `findings.md` | `PATCH_VERSION = 22` agrees with the docs, but it is never read. No document maps versions 4, 5, 7, 8, 9 and 10 to patches: when did protection, menu framing, asteroid, solid, station, world and texture32 arrive? `client-setup.md:99` still gives `78c5bd39…` as "the prepared localhost executable (patch version 12, no optional rendering patches)". At v22 the default output also includes frame clock, visibility, chase, own-ship ×2 and power-ups, so that hash is not what `prepare` produces now. | grep for "patch version"; read `test_prepare_client.py:67`. | Keep a `CHANGELOG`-style table in the registry module (`since=` per patch) and have `check()` report "older setup: re-prepare" based on it. Remove the stale hash, or regenerate it from a test. |
| C11 | M | `prepare_client.py:326-345` | The CLI is incomplete or inconsistent. There are no flags for asteroid, solid, station-detail, world-detail or texture32: they need separate tools, each with its own backup (C12), or the GUI. `--experimental-protection` and `--distant-objects` error with non-`prepare` actions, but `--frame-clock`, `--third-person` etc. and `--station` are silently ignored with `undo`, `check` and `launch`. `RuntimeError` (write verification) is not caught. | `python3 -I tools/prepare_client.py --help`; read the code. | Generate `--[no-]<option>` from the registry, all defaulting to None (preserve). Put them in a `prepare` subparser so they cannot be passed to other actions. |
| C12 | M | `asteroid_render.py`, `solid_world_render.py`, `station_detail.py`, `world_detail.py`, `texture32.py`, `object_persistence.py` (each `install()`/`main()`), `render_*_experiment.py` | There are six parallel exact-undo mechanisms (`.EXE.before-<x>` plus `_<x>.json`). `prepare_client` already keeps `.setup-original` and `_client_setup.json`. The side JSONs are written, never read (grep finds no readers), and go stale when the launcher toggles the same patch. A `.before-*` backup goes stale as soon as anything else changes, and `--undo` then fails with "backup does not match this client". The docs carry ordering rules such as "Undo station detail before undoing the underlying solid-world patch" and "Undo this layer before the older rendering patches". | grep for `_texture32.json` etc. (no readers); read each `install()`. | Remove the per-patch installers and backups. One transaction (`prepare` with options) plus one exact-undo backup is enough, because every option is reversible in memory. |
| C13 | M | `solid_world_render.py:39-45`, `world_detail.py:39-46` vs `prepare_client.py:160-166` | Conflict handling is inconsistent. `solid_world_render.configure(enabled=True)` and `world_detail.configure(True)` silently strip their sibling (asteroid / station). `prepare_client.configure` raises when both are requested. The launcher unticks the other box. That is three policies for one rule. | Read the code. | Declare `conflicts=` in the registry, enforce it in one place, and make module `configure()` pure (no sibling edits). |
| C14 | M | `.github/workflows/tests.yml:38-45`; `test_prepare_client.py:21`; `test_client_launcher.py` | CI lists `test_prepare_client` (8/8 skipped) and `test_client_launcher` (5/6 skipped) as passing gates. Separately, 15 suites in my area **error** rather than skip without `game/2.9.2/AOACLIENT.EXE.orig`: third_person, visibility_fix, object_persistence(_pipeline), frame_clock, cursor_warp, menu_aspect, render_clock_experiment, render_culling, render_motion, texture32, powerup_pickup, asteroid, solid, station, world, online_terrain. Several contain game-free emulation tests that pass (menu_aspect 1/2, frame_clock 3/5, render_clock 1/2), but they cannot run in CI because module import requires unicorn and the class setup reads the EXE. | Ran every suite with `python3 -I`; then in a scratch venv with requirements. | Split each suite into a game-free part (cave emulation, region and layout invariants) and a game-required part, with a uniform `skipUnless`. Install capstone and unicorn in the Linux CI job for the patch suites. Report skips as "not run" in CI. |
| C15 | M | `tools/verify_local.py:16-26` | Never run anywhere: `test_physics_timestep.py` (a script that needs argv, and dies with `IndexError` when run plainly), `test_menu_aspect.py`, `test_render_clock_experiment.py`, `test_render_motion.py`. `menu_aspect` is a default-on shipping patch with no gated test. | Diffed the SUITES list against `ls tools/test_*`; ran the scripts. | Add them to `verify_local` (convert `test_physics_timestep` to unittest, reading the `.orig`), or archive them with their experiments. |
| C16 | M | `patch_client.py:205-215`, `local_station.py:29-46`, `physics_timestep.py:46-58` | The legacy standalone CLIs still work and write the EXE in place, with no `_client_setup.json` update. On a prepared client they either fail (the hash check) or leave an unrecorded EXE that `prepare` then refuses ("executable changed outside the recorded setup"). `patch_client` writes its own `.orig` and `_patches.json`. `running-on-windows-11.md:88-121` still documents `physics_timestep.py` and `local_station.py` invocations. `setup_game.ps1:7` still lists "tools\patch_client.py" as step 2. | Read the code and docs. | Remove the `main()`s, so they become library-only like archive_terminator. Move `STABLE_SHA256`, `OFFSET` and `ORIGINAL` into the registry/base module. Move the history text in running-on-windows-11 to findings. |
| C17 | M | `setup_game.ps1:41-60` | Silent-failure points: a mistyped `-Wrapper` path (`Test-Path` false) silently installs native DirectX 7 and only prints a hint. The compatibility-mode check reads only the HKCU Layers key, not HKLM, and only warns. The final hint prints `$python -I tools\client_launcher.py` while play.md says to double-click the `.cmd`. If no `.venv` exists, `setup_game` uses whatever `python` is on PATH, and then `client_launcher.cmd` refuses to start ("Missing project Python environment"). | Read the code. | If `-Wrapper` was passed explicitly and is missing, throw. Use one Python resolution rule (require `.venv`, or create it). Also check the HKLM Layers key. |
| C18 | M | `client_launcher.cmd:9` | It uses `start "" .venv\Scripts\pythonw.exe`, so any failure before the Tk window exists (bad argument path, missing tkinter, import error) is invisible: the double-click does nothing. | Read the code. | Run `python.exe` with `pause` on a non-zero exit, or wrap the `gui()` start-up in a try/except that shows a `messagebox`. |
| C19 | L | `client-setup.md:240-241` | "The launcher refuses an undone client until it is prepared again". In fact `read_settings` accepts it (`load_record` allows a "restored" record) and Apply/Play simply re-prepares it. | sim.py: `read_settings` on an undone client is accepted. | Fix the doc, or make the launcher show "restored to original; Apply re-prepares". |
| C20 | L | `client-setup.md:344-349` | It documents `dgVoodoo.conf.before-quality` as "the exact prior file", but no tool creates it (grep found nothing). It was a hand-made artifact. The launcher now owns these five keys. | grep for `before-quality`. | Delete the section, or point it to the launcher's "Original visuals" button. |
| C21 | L | `online_terrain.py:23` | It is the only patch module without the `sys.path.insert` header. It works only because an importer inserted `tools/` first. Under `-I` (Python ≥3.11 implies `-P`) the script directory is not on `sys.path`. | Read the code. | This goes away with a package layout (relative imports). |
| C22 | L | `online_terrain.py:89-161,190-197` | The `MAPS` table is baked into the cave bytes and recognized by exact equality. Any edit to `MAPS` (adding a map) without a version bump makes every existing client fail `state()`, so `prepare` refuses ("unexpected online terrain code or cave"). Only v1, v2 and v3 are recognized. | Read the code. | Recognize the code part and the table separately, or move the table to a stable data region with its own version byte. |
| C23 | L | all modules except `patch_client` | VA→file offset is hard-coded as `va - 0x400000`, which happens to hold for this EXE. `patch_client` maps through the section table, while `pe_util` (pefile) is not used by the patch path at all. | Read the code. | Use one `va_to_off()` in the base module, asserted once against the pristine section table. |
| C24 | L | `make_install.py`, `install_wrapper.py`, `prepare_offline_baseline.py` | `install_wrapper` writes non-atomically, keeps no record and has no undo tool ("delete the files"). It has no `originals/` guard, unlike `prepare_client.paths`. `prepare_offline_baseline` only looks in `originals\` for the installer, while `setup_game` also falls back to `builds\…\aoa-current.exe`. | Read the code. | Fold these into a single `install` package with shared path guards and the same `atomic_write`. |
| C25 | L | backups and records written into the game folder | Backups use 13 different suffixes: `.orig` (setup_game, patch_client, offline baseline), `.setup-original`, `.EXE.before-{asteroid-render, solid-world-render, station-detail, world-detail, texture32, object-persistence, clock, culling}`, `<ARCHIVE>.before-texture-pack` and `.launcher-texture-pack`. Records use 13 different JSON names. `verify_local.py` and every test depend on the `.orig` copy that `setup_game.ps1:47` makes with a bare `Copy-Item`. | grep. | Keep one `.aoa-setup/` subfolder: `original.exe`, `record.json`, and texture-pack originals. |

### 2a. Patch inventory (question 1)

"Always" means it has no flag and `check()` requires it. "Forced ON" means a missing flag turns it on (C1).
"Preserved" means a missing flag keeps the installed state. VAs use image base 0x400000; file offset =
VA − 0x400000 for every site listed. "Ver" is the patch version that introduced it, from the docs; "?" means
it is not documented (C10).

| Patch ID | Module | Ver | Default / control | Code sites (VA, bytes) | Cave (.text) | Data written | Depends on / conflicts |
|---|---|---|---|---|---|---|---|
| `logger-size-v1` | patch_client | ≤1 | Always; only on pristine input | 0x551775 (2) | — | PE headers: .text VirtualSize→0x18B000, .data→0x4D000 | **Every cave and .data-tail patch depends on this header change** |
| `logger-lock-v1` | patch_client | ≤1 | Always | 0x526D00 (8), 0x526F8C (11), 0x527210 (8), 0x527233 (9) | 0x58B200–0x58B286 | runtime 0x60D200–0x60D208 | header change above; no `state()` or undo |
| Station hostname | local_station constants + `prepare_client.host_field` | ≤1 | Always; `--station` (≤11 chars) | — | — | 0x5C5C60 (12; file 0x1C5C60) | conflicts with explicit-protection unless the host is loopback |
| `zero-time-physics-v1` | physics_timestep | ≤2 | Always | 0x48AE71 (6) | 0x58B400–0x58B416 | — | configure() asserts the whole-image `STABLE_SHA256`, so it must run on a fully stripped image |
| `background-network-v1` | inline in prepare_client | 2 | Always | 0x446EAF (2, jne→nop) | — | — | adjacent to frame-clock's 0x446EB1; frame-clock's gate exists because of it |
| `archive-terminator-v1` | archive_terminator | 3 | Always | 0x52A6E3 (10) | 0x58B440–0x58B458 | — | — (module has no `NAME`) |
| `online-terrain-v3` (v2 / `online-arena1a-v1` recognized) | online_terrain | 6 / 11 / 18 | Always; check requires v3 | 0x4306AF (5) | 0x58B800–0x58BA00 (code plus map table at 0x58B8C0) | — | server `--experimental-terrain` marker |
| `explicit-protection-v1` | explicit_protection | ? | Off, preserved; `--[no-]experimental-protection`; not in the launcher | 0x4867C3 (11) | 0x58B480–0x58B4AF | — | loopback Station only |
| `ship-menu-aspect-v1` | menu_aspect | ? (≤10) | Forced ON; `--[no-]menu-framing`; launcher | 0x463D06 (5), 0x4652A1 (5) | 0x58B500–0x58B56C | — | — |
| `cursor-warp-origin-v1` | cursor_warp | 12 | Always | 0x4EAD16 (18) | 0x58B300–0x58B33C | — | — |
| `frame-clock-v1` | frame_clock | 13 | Forced ON; `--[no-]frame-clock`; launcher | 0x5296C4 (6), 0x529700 (6), 0x446EB1 (5) | 0x58B600–0x58B661, 0x58B680–0x58B697 | — | the third-person CULL_WINDOW exists because of it; **byte-identical** to render_clock_experiment |
| `visibility-math-v1` | visibility_fix | 14 | Forced ON; `--[no-]visibility-math`; launcher | 0x5431A1 (6) | 0x58B700–0x58B75B | — | same site as render_culling_experiment |
| `third-person-camera-v3` (v1, v2 upgraded) | third_person | 15 / 20 / 21 | Forced ON; `--[no-]third-person`; launcher | 0x44A091 (6), 0x49BCB8 (9), 0x43B367 (8) | 0x58BC00–0x58BDF0 | runtime 0x60D300–0x60D3F9 (FAKE…ARMED); writes the original byte 0x5E6879 (CHASE_FLAG) | reads GAME_TICK (frame clock) |
| `own-ship-model-v1` | own_ship_model | 16 | Tied to `--third-person` | 0x44C0C5 (2), 0x48FAE5 (7) | 0x58BE00–0x58BE13 | — | reads third_person.CHASE_FLAG |
| `own-ship-menu-model-v1` (legacy cave upgraded) | own_ship_menu | 17 | Tied to `--third-person` | 0x56ECDC (6), 0x56ED01 (5) | 0x58BF00–0x58BF59 | runtime RESTRICT 0x60D3EC (**inside third_person's block**) | third_person.CHASE_FLAG and TICK |
| `powerup-pickup-v1` | powerup_pickup | 19 | Forced ON; `--[no-]powerup-pickup`; launcher | 0x431E19 (10), 0x49ACC2 (17, in place) | 0x58B2C0–0x58B2D6 | — | server `--powerup-zones` |
| `asteroid-mesh-distance-v1` | asteroid_render | ? | Off, preserved; no CLI flag; own tool plus launcher | 0x543222 (6) | 0x58BA00–0x58BA41 | reads 0x5B0C30 and 0x59D9C0 | **conflicts with solid-world (same site)**; changed by distant-objects (C4) |
| `solid-world-mesh-distance-v1` | solid_world_render | ? | Off, preserved; no flag; tool plus launcher | 0x543222 (6, in place) | — | reads 0x59D9C0 | conflicts with asteroid; changed by distant-objects |
| `station-full-detail-v1` | station_detail | ? | Off, preserved; no flag; tool plus launcher | 0x546BE4 (6) | 0x58BB00–0x58BB50 | — | **conflicts with world-detail (same site)**; resumes into distant-objects' 0x546BEA hook |
| `world-full-detail-v1` | world_detail | ? | Off, preserved; no flag; tool plus launcher | 0x546BE4 (6, in place), 0x546B46 (2) | — | — | conflicts with station-detail |
| `texture-argb8888-v1` | texture32 | ? | Off, preserved; no flag; tool plus launcher | 0x562AB8 (2), 0x562ABD (2), 0x562AE3 (18) | none | — | texture pack needs it |
| `distant-world-objects-v1` | object_persistence | 22 | Off, preserved; `--[no-]distant-objects`; launcher | 0x54326A (6), 0x546BB3 (5), 0x546BEA (6) | 0x58BB80–0x58BC00 | **constants** 0x5B0C30 and 0x59D9C0 (4 each) | changes the asteroid and solid-world semantics |
| *(experiment)* clock | render_clock_experiment | — | offline-baseline only | 0x5296C4, 0x529700 | 0x58B600–0x58B661 | — | identical to frame-clock |
| *(experiment)* culling | render_culling_experiment | — | offline-baseline only | 0x543077 (6), 0x5431A1 (6) | 0x58B700–0x58B85B | — | overlaps visibility-math (site and cave) and online-terrain (cave 0x58B800+) |

Free .text padding left: about 0x200 bytes across 14 gaps, the largest being 0x58BE13–0x58BF00 (237 B) and
0x58B75B–0x58B800 (165 B). The cave area 0x58B200–0x58C000 is nearly full.

### 2b. Module interfaces as they are (question 2)

| Shape | Modules | Surface |
|---|---|---|
| A: one-way builder | patch_client | `configure(pristine) -> (bytes, record)`, `PRISTINE_292`, `Asm`, `jmp_patch`; CLI writes `.orig` |
| B: hash-gated toggle, inverted flag | physics_timestep, local_station | `configure(data, undo=False)`; asserts `STABLE_SHA256`; no `state`/`NAME`; CLI writes the EXE |
| C: state + configure, no regions | archive_terminator, explicit_protection, online_terrain | `state(data)->bool`, `configure(data, enabled=True)`; online_terrain adds `installed_name`, `is_current`, and V2/LEGACY names; archive has no NAME |
| D: regions + state + configure | cursor_warp, menu_aspect, visibility_fix, frame_clock, powerup_pickup, own_ship_model | `NAME`, `regions()->[(off, old, new)]`, `state`, `configure` (`state` copy-pasted 6×) |
| D′: variants | third_person (`regions(variant)`, `matches`, `VARIANTS`), own_ship_menu (`regions(legacy)`, `matches`) | variant reported as current (C8) |
| E: D plus its own installer CLI and backup | asteroid_render (`main`), solid_world_render, station_detail, world_detail, texture32, object_persistence (`install(exe, undo)`) | solid/world `configure` also edits the sibling patch (C13) |
| F: experiment | render_clock_experiment, render_culling_experiment | `regions`, `configure` with a whole-image gate via `prepare_client.inspect`; hard-coded EXE path |
| (inline) | `prepare_client.background_site` | — |

---

## 3. File classification

`path | role | verdict | proposed home`

Code:
- `tools/prepare_client.py` | patch orchestrator, record, check, launch | keep, rewrite registry-driven | client patching (`aoa/client/prepare.py`)
- `tools/patch_client.py` | logger fixes, `Asm`, `jmp_patch`, PE section edit | keep the library, drop `main()`; split `Asm`/`jmp_patch` into an asm helper | client patching (`patches/logger.py`, `asm.py`)
- `tools/pe_util.py` | pefile/capstone static-analysis helpers | keep (not used by the patch path) | analysis/RE
- `tools/local_station.py` | hostname constants and legacy CLI | merge into prepare/base (constants); delete CLI | client patching
- `tools/physics_timestep.py` | zero-time physics guard | keep as a patch; drop CLI and its internal hash gate | client patching
- `tools/archive_terminator.py` | archive NUL terminator | keep | client patching
- `tools/explicit_protection.py` | opt-in 0x81 protection prototype | keep, marked experimental | client patching (experimental)
- `tools/cursor_warp.py` | cursor warp origin | keep | client patching
- `tools/menu_aspect.py` | ship-menu framing | keep | client patching
- `tools/frame_clock.py` | QPC clock and timer gate | keep | client patching
- `tools/visibility_fix.py` | bounded acos/asin | keep | client patching
- `tools/third_person.py` | F2/F4 cameras | keep | client patching
- `tools/own_ship_model.py` | own-ship mesh | merge into a third_person "camera" patch group | client patching
- `tools/own_ship_menu.py` | own-ship after menu preview | merge into a third_person group | client patching
- `tools/powerup_pickup.py` | power-up pickup | keep | client patching
- `tools/online_terrain.py` | server map hook and map table | keep; split the `MAPS` table (shared with host) from the cave | client patching (cave) plus protocol/maps (table)
- `tools/asteroid_render.py` | asteroid mesh horizon | keep the patch, delete `main()` and its backup | client patching (rendering)
- `tools/solid_world_render.py` | world mesh horizon | keep the patch, delete `install()` | client patching (rendering)
- `tools/station_detail.py` | Hy_base1 LOD pin | keep the patch, delete `install()` (docs already say to prefer world detail) | client patching (rendering)
- `tools/world_detail.py` | world LOD pin | keep the patch, delete `install()` | client patching (rendering)
- `tools/texture32.py` | ARGB8888 textures | keep the patch, delete `install()` | client patching (rendering)
- `tools/object_persistence.py` | distant objects | keep the patch, delete `install()` | client patching (rendering)
- `tools/texture_pack.py` | install/undo archive texture pack | keep | client patching (assets)
- `tools/build_texture_pack.py` | Real-ESRGAN pack builder | keep | assets/maps (player tools)
- `tools/prepare_offline_baseline.py` | builds the isolated diagnostic folder | archive | analysis/RE (archive)
- `tools/render_clock_experiment.py` | superseded clock experiment (identical to frame_clock) | archive | analysis/RE (archive)
- `tools/render_culling_experiment.py` | superseded culling experiment | archive | analysis/RE (archive)
- `tools/seed_offline_velocity.py` | offline coast fixture (ctypes) | archive | analysis/RE (archive)
- `tools/install_wrapper.py` | dgVoodoo install, DPI manifest, `set_key` | keep | launchers/install
- `tools/make_install.py` | extract the Wise/ZIP installer | keep | launchers/install
- `tools/setup_game.ps1` | Windows end-to-end setup | keep, fix C17 | launchers
- `tools/register_activeskin.ps1` | per-user OCX registration | keep | launchers
- `tools/client_login.ps1` | test driver: fill login and press Play Online | keep (test/reel driver) | tests (Windows drivers)
- `tools/client_launcher.py` | Tk options GUI and apply/launch | keep, registry-driven | launchers
- `tools/client_launcher.cmd` | double-click wrapper | keep, fix C18 | launchers
- `tools/crashdbg.py` | Win32 crash debugger / guard heap | keep | analysis/RE

Tests:
- `tools/test_prepare_client.py` | composition, undo, recovery (needs the EXE) | keep; add game-free layout tests | tests
- `tools/test_third_person.py` (also covers own_ship_*) | emulation | keep, split game-free | tests
- `tools/test_visibility_fix.py` | emulation | keep | tests
- `tools/test_object_persistence.py` | emulation | keep | tests
- `tools/test_object_persistence_pipeline.py` | emulation | merge into test_object_persistence | tests
- `tools/test_frame_clock.py` | emulation | keep, split game-free | tests
- `tools/test_physics_timestep.py` | argv script, never run | convert to unittest and add to the gate | tests
- `tools/test_cursor_warp.py` | emulation | keep | tests
- `tools/test_menu_aspect.py` | emulation, not in any gate | keep, add to the gate | tests
- `tools/test_render_clock_experiment.py` | tests the superseded experiment, not in any gate | merge its game-free clock test into test_frame_clock; archive the rest | tests / archive
- `tools/test_render_culling.py` | experiment and visibility emulation | merge the visibility parts into test_visibility_fix; archive | tests / archive
- `tools/test_render_motion.py` | offline motion check, not in any gate | archive with the experiments, or add to the gate | archive
- `tools/test_texture32.py` | emulation | keep | tests
- `tools/test_powerup_pickup.py` | emulation | keep | tests
- `tools/test_asteroid_render.py`, `test_solid_world_render.py`, `test_station_detail.py`, `test_world_detail.py` | emulation and installer | keep; drop the installer tests with C12 | tests
- `tools/test_client_launcher.py` | launcher logic | keep | tests
- `tools/test_build_texture_pack.py` | game-free, CI on Windows | keep | tests
- `tools/test_online_terrain.py` | emulation | keep | tests
- `tools/test_client_extensions.py` | protection-protocol gate (game-free, 15 s) | keep | tests (protocol)

Docs:
- `docs/client-setup.md` | patch reference | keep; replace per-version narrative with a generated table; fix C10, C19, C20; remove the per-tool sections after C12
- `docs/play.md` | player guide | keep; fix the LAN `prepare` command (C1); add a `.venv` requirement note
- `docs/running-on-windows-11.md` | Windows runbook and history | keep the first half; move the legacy `local_station`/`physics_timestep` text to findings (C16)
- `docs/texture-pack.md` | player guide | keep; step 3 should use the launcher or `prepare --texture32` (C3)
- `docs/client-extension-gate.md` | protection gate | keep
- `docs/offline-rendering-baseline.md` | experiment log | archive (`docs/history/`)
- `docs/asteroid-rendering.md` | rendering investigation | keep as history; correct the "one code reference each" claim (C4)
- `docs/render-pipeline-audit.md` | audit notes | archive (history)
- `docs/findings.md` §9.36–9.48 | evidence | keep; consistent with the code (CULL_WINDOW 250, variant upgrades); no v22 entry (it is in asteroid-rendering.md)

---

## 4. Recommendations for the redesign

1. **One patch descriptor and one generic engine.** Example (`aoa/client/patches/base.py`):
   ```python
   @dataclass(frozen=True)
   class Region:  va: int; old: bytes; new: bytes; kind: str  # "site" | "cave" | "const"
   @dataclass(frozen=True)
   class Patch:
       id: str                      # "frame-clock-v1"
       since: int                   # patch version that introduced it
       policy: str                  # "always" | "option"
       option: str | None           # "frame_clock" -> --[no-]frame-clock, launcher key
       label: str | None            # launcher text
       default: bool                # for fresh/pristine input only
       requires: tuple[str, ...] = ()   # e.g. own-ship-model -> third-person
       conflicts: tuple[str, ...] = ()  # asteroid <-> solid, station <-> world
       reads: tuple[int, ...] = ()      # constants read (for C4-style checks)
       data: tuple[tuple[int, int], ...] = ()  # runtime .data reservations
       regions: Callable[[], list[Region]]
       legacy: dict[str, Callable[[], list[Region]]] = field(default_factory=dict)
   def state(p, data) -> str | None      # installed variant id, or None; raises on partial/unknown
   def apply(p, data, on: bool) -> bytes # strips any legacy variant first
   ```
   `REGISTRY: list[Patch]` in `patches/__init__.py` is the single source of truth for `inspect`, `configure`,
   CLI flags, launcher checkboxes, the `check()` requirements and the changelog.

2. **What each module needs to change to fit:**
   - D modules (cursor_warp, menu_aspect, visibility_fix, frame_clock, powerup_pickup, own_ship_model):
     delete the copy-pasted `state`/`configure`; export `PATCH = Patch(...)`.
   - third_person, own_ship_menu: express v1/v2/legacy as `legacy=`; `state` returns the variant (fixes C8).
     Take RESTRICT and the other .data addresses from a central layout.
   - archive_terminator, explicit_protection, online_terrain: add `regions()`; give archive a NAME.
     online_terrain: split the MAPS table (C22); add the `sys.path` fix, which becomes moot once it is a
     package.
   - physics_timestep, local_station: drop the internal `STABLE_SHA256` gate and `undo=` inversion; drop the
     CLIs. The base-image hash check moves into the engine.
   - patch_client: becomes the `base` step (pristine → stable). Keep `Asm`/`jmp_patch` in `asm.py`; drop
     `main()`.
   - background: new module with `regions()`.
   - asteroid, solid, station, world, texture32, object_persistence: delete `install()`/`main()` and their
     backups and records (C2, C3, C12). solid/world: remove the sibling edits from `configure` (C13).
   - render_*_experiment, seed_offline_velocity, prepare_offline_baseline: move to `archive/`, with their docs.

3. **`prepare(exe, options: dict[str, bool|None], station=None)`**: None means preserve the installed state;
   the default applies only on pristine input (fixes C1–C3). Keep the existing `.setup-original` plus
   `_client_setup.json` transaction, which is good: atomic, pending/ready, exact undo. Make `check()` compare the
   installed variants with `REGISTRY` and report "re-prepare: X is outdated".

4. **Game-free layout tests in CI**, from the registry:
   - regions are disjoint except for declared conflicts;
   - caves are inside [0x58B200, 0x58C000) and data inside [0x60D200, 0x60E000);
   - every `requires` and `conflicts` name exists;
   - `reads` do not intersect another patch's `const` writes unless declared.
   `scratchpad/arch/client/regions.py` and `sim.py` show this works without game files. Install unicorn and
   capstone in the Linux CI job and run the cave-emulation halves of the suites (C14, C15).

5. **One install entry point.** `setup_game.ps1` should require or create `.venv`, fail on an explicit
   missing `-Wrapper`, and end by opening the launcher. Its docstring should list the real steps.
   `client_launcher.cmd` should surface start-up errors. Use one backup folder (`.aoa-setup/`) instead of
   13 suffixes.

## 5. Player path, end to end (question 5)

`setup_game.ps1` → `make_install.py` → copy to `.orig` → `prepare_client prepare` (wrapper recorded as
native) → `register_activeskin.ps1` (re-launches 32-bit PowerShell) → `install_wrapper.py` (if the zip is
present) → compatibility-layer warning → `prepare` again (records the wrapper) → `check`. The player then runs
`client_launcher.cmd`, which uses `.venv\pythonw` and the Tk GUI. Its `apply_settings` → `prepare` +
dgVoodoo.conf + texture pack → `check` → `Popen(AOACLIENT.EXE)`.

**Manual steps for a new Windows player:**
1. Install Python 3.12 (on PATH) and Git.
2. Clone the repo, create `.venv`, run `pip install -r requirements.txt`. That pulls capstone, unicorn and
   pefile, which only research needs.
3. Run `fetch_known_builds.py` (it also downloads 2.8.2).
4. Hand-download the dgVoodoo zip into a hand-made `originals\wrappers\dgvoodoo2-2.87.5\` folder.
5. Run `setup_game.ps1` in their own (not sandboxed) PowerShell.
6. Remove any compatibility mode by hand (the script only warns).
7. Double-click the launcher.
8. **Multiplayer:** edit the `hosts` file (admin), open firewall rules on the host, and re-run `prepare
   --station …`, which resets launcher choices (C1).
9. **Texture pack:** hand-download Real-ESRGAN into a hand-made folder, then run 3 more commands.

**Where it can fail silently:**
- **Mistyped `-Wrapper`:** silently falls back to native DirectX (C17).
- **Sandboxed shell:** ActiveSkin registration succeeds in a shell whose registry view the game does not
  share, and the login dialog never appears (documented, not detected).
- **Launcher start-up:** `pythonw` swallows start-up errors (C18).
- **Option resets:** patch tools reset options with no message (C1, C3).
- **After launch:** `launch`/Play return immediately after `Popen`, so a client crash gives no feedback.
- **Compatibility mode:** a compatibility layer set under HKLM is not detected.

**Inconsistencies between the scripts and the tools:**
- `setup_game` docstring step 2 names `patch_client.py` (C16).
- Python resolution: `setup_game` falls back to `python`; the `.cmd` requires `.venv` (C17).
- `setup_game` prints a `python … client_launcher.py` hint; `play.md` says to double-click the `.cmd`.
- Installer lookup: `setup_game` also searches `builds\`; `prepare_offline_baseline` only `originals\` (C24).
- Backup names differ: `.orig` vs `.setup-original` vs `.before-*` (C25).
- Default Station: `client_login.ps1` uses 127.0.0.1, `setup_game` uses localhost. Both are valid, but
  documented differently.

## 6. Not checked

- No real 2.9.2 executable or game assets were available. I did not check any cave's machine-code
  correctness, the whole-image hashes, `make_install` against the real installer, or the asset manifest.
  The C1–C3, C8, C9 and C19 behaviours were reproduced on a synthetic image, not the real one.
- None of the PowerShell, ctypes, tkinter or Win32 code ran:
  - setup_game, register_activeskin, client_login;
  - the launcher GUI, `require_closed`;
  - crashdbg, seed_offline_velocity.
- `build_texture_pack` end to end (Real-ESRGAN, Vulkan) and `texture_pack.install`, beyond reading the code.
- Whether Windows honours the external DPI manifest written after the EXE was first launched (manifest
  caching): not examined.
- `findings.md` §9.36–9.48 was spot-checked against the code (CULL_WINDOW, cave sizes, variant upgrades), not
  line by line. Evidence JSONs were only grepped for `patch_version`.

## 7. What I ran, and repository cleanliness

- **Commands run in the repo:**
  - `python3 -I tools/prepare_client.py --help`. I read the file first: it uses argparse and has no side
    effects for `--help`.
  - Each test suite listed in C14, once with system Python and once with a scratch venv.
- **Library code imported from scratch scripts:** `regions.py` and `sim.py`. Every file they wrote went to
  `scratchpad/arch/client/tmp*`.
- **No script ran without arguments**, apart from the unittest suites and `test_physics_timestep.py`, which
  failed at once on a missing argv.
- **Repo state afterwards:**
  - `git status --short` is empty, so no tracked file was modified.
  - The only ignored items are `tools/__pycache__/` and `tools/reel/__pycache__/`, both git-ignored.
  - `work/` holds three **empty** directories (`arena1a-review`, `asset-review`, `map-node-review`, created
    14:42 UTC). Their names match other auditors' areas, and none of my scripts writes under `work/`, so I
    left them for the architect.
