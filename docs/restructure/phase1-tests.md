# Test outcomes after phase 1

Every suite after the move into `aoa/`, `tests/` and `archive/`, measured
on 14 November 2026 at `9a61ca7` the same way as the refreshed table in
[baseline-tests.md](baseline-tests.md): Linux, Python 3.13.17, no game
files, once with the system `python3` alone and once in a scratch venv with
`requirements.txt`. Each suite ran in its own `python -I` process from the
repository root, as `python -I tools/test.py <suite>` runs it (the two
archived suites by their dotted names under `archive/offline_baseline/`).

## Difference from the baseline

- **Unchanged:** all 53 baseline suites have the same exit code, test
  count, skip count and result in both runs, except `test_cli_help`. The 20
  suites that exit 1 (18 of them at import without `unicorn`, `capstone` or
  `pefile`; with the requirements, all 20 because they read the missing
  game files instead of skipping) still do so with the same counts; making
  them skip is later work, not a move.
- **`test_cli_help`:** 108 to 133 tests. It now runs `--help` on every
  `tools/` script (23 shims, `run.py`, `test.py`, `verify_local.py`) and,
  through `tools/run.py`, on every `aoa` and `archive` module with a
  `__main__` block (98), plus its 9 fixed checks. Skips stay 28 without the
  requirements (modules that need a package that is not installed) and 0
  with them.
- **New:** `test_imports` (127 tests: every `aoa` module imports alone;
  21 skipped without the requirements, none with them) and `test_layering`
  (3 tests; 17 known violations listed under H12 and R4).
- `tests/snapshots/patch_regions.json` and `host_configs.json` are the same
  blobs as `tools/snapshots/` before the move, and both snapshot suites
  pass without `--update`.

Columns 2 to 5 are the standard-library run, columns 6 to 9 the run with
requirements.

| Suite | Exit | Ran | Skipped | Result | Exit | Ran | Skipped | Result |
|---|---|---|---|---|---|---|---|---|
| `test_aoapack_write` | 1 | 0 | 0 | FAILED (errors=1) | 1 | 0 | 0 | FAILED (errors=1) |
| `test_asteroid_render` | 1 | - | - | ModuleNotFoundError: No module named 'unicorn' | 1 | 5 | 0 | FAILED (errors=5) |
| `test_build_texture_pack` | 0 | 5 | 0 | OK | 0 | 5 | 0 | OK |
| `test_cli_help` | 0 | 133 | 28 | OK (skipped=28) | 0 | 133 | 0 | OK |
| `test_client_extensions` | 0 | 1 | 0 | OK | 0 | 1 | 0 | OK |
| `test_client_launcher` | 0 | 7 | 5 | OK (skipped=5) | 0 | 7 | 5 | OK (skipped=5) |
| `test_combat_delivery` | 0 | 1 | 0 | OK | 0 | 1 | 0 | OK |
| `test_cursor_warp` | 1 | - | - | ModuleNotFoundError: No module named 'unicorn' | 1 | 0 | 0 | FAILED (errors=1) |
| `test_dedicated_host` | 0 | 8 | 0 | OK | 0 | 8 | 0 | OK |
| `test_frame_clock` | 1 | - | - | ModuleNotFoundError: No module named 'unicorn' | 1 | 5 | 0 | FAILED (errors=2) |
| `test_guest_admission` | 0 | 1 | 0 | OK | 0 | 1 | 0 | OK |
| `test_host_argv` | 0 | 5 | 0 | OK | 0 | 5 | 0 | OK |
| `test_host_control` | 0 | 15 | 5 | OK (skipped=5) | 0 | 15 | 5 | OK (skipped=5) |
| `test_imports` | 0 | 127 | 21 | OK (skipped=21) | 0 | 127 | 0 | OK |
| `test_install_wrapper` | 0 | 3 | 0 | OK | 0 | 3 | 0 | OK |
| `test_internet_play` | 0 | 8 | 0 | OK | 0 | 8 | 0 | OK |
| `test_lan_dogfight` | 0 | 4 | 0 | OK | 0 | 4 | 0 | OK |
| `test_layering` | 0 | 3 | 0 | OK | 0 | 3 | 0 | OK |
| `test_make_map` | 0 | 12 | 1 | OK (skipped=1) | 0 | 12 | 1 | OK (skipped=1) |
| `test_make_object` | 0 | 8 | 2 | OK (skipped=2) | 0 | 8 | 2 | OK (skipped=2) |
| `test_make_vessel_combat` | 0 | 3 | 1 | OK (skipped=1) | 0 | 3 | 1 | OK (skipped=1) |
| `test_menu_aspect` | 1 | - | - | ModuleNotFoundError: No module named 'unicorn' | 1 | 2 | 0 | FAILED (errors=1) |
| `test_navigation_buoys` | 0 | 4 | 4 | OK (skipped=4) | 0 | 4 | 4 | OK (skipped=4) |
| `test_network_bounds` | 0 | 6 | 0 | OK | 0 | 6 | 0 | OK |
| `test_object_lod` | 1 | - | - | ModuleNotFoundError: No module named 'unicorn' | 1 | 0 | 0 | FAILED (errors=1) |
| `test_object_persistence` | 1 | - | - | ModuleNotFoundError: No module named 'unicorn' | 1 | 0 | 0 | FAILED (errors=1) |
| `test_object_persistence_pipeline` | 1 | - | - | ModuleNotFoundError: No module named 'unicorn' | 1 | 2 | 0 | FAILED (errors=2) |
| `test_online_terrain` | 1 | - | - | ModuleNotFoundError: No module named 'unicorn' | 1 | 8 | 0 | FAILED (errors=46) |
| `test_patch_layout` | 0 | 7 | 0 | OK | 0 | 7 | 0 | OK |
| `test_physics_timestep` | 0 | 1 | 1 | OK (skipped=1) | 0 | 1 | 1 | OK (skipped=1) |
| `test_polite_http` | 0 | 15 | 0 | OK | 0 | 15 | 0 | OK |
| `test_powerup_pickup` | 1 | - | - | ModuleNotFoundError: No module named 'pefile' | 1 | 0 | 0 | FAILED (errors=1) |
| `test_powerups` | 0 | 7 | 0 | OK | 0 | 7 | 0 | OK |
| `test_prepare_client` | 0 | 14 | 8 | OK (skipped=8) | 0 | 14 | 8 | OK (skipped=8) |
| `test_reel` | 0 | 4 | 0 | OK | 0 | 4 | 0 | OK |
| `test_relay_motion` | 0 | 7 | 0 | OK | 0 | 7 | 0 | OK |
| `test_relay_recovery` | 0 | 1 | 0 | OK | 0 | 1 | 0 | OK |
| `test_render_clock_experiment` | 1 | - | - | ModuleNotFoundError: No module named 'unicorn' | 1 | 2 | 0 | FAILED (errors=1) |
| `test_render_culling` | 1 | - | - | ModuleNotFoundError: No module named 'unicorn' | 1 | 0 | 0 | FAILED (errors=1) |
| `test_render_motion` | 1 | - | - | ModuleNotFoundError: No module named 'unicorn' | 1 | 3 | 0 | FAILED (errors=3) |
| `test_scene_nodes` | 1 | 6 | 0 | FAILED (errors=5) | 1 | 6 | 0 | FAILED (errors=5) |
| `test_solid_world_render` | 1 | - | - | ModuleNotFoundError: No module named 'unicorn' | 1 | 5 | 0 | FAILED (errors=5) |
| `test_station_detail` | 1 | - | - | ModuleNotFoundError: No module named 'unicorn' | 1 | 5 | 0 | FAILED (errors=5) |
| `test_station_runtime` | 0 | 10 | 0 | OK | 0 | 10 | 0 | OK |
| `test_station_sessions` | 0 | 5 | 0 | OK | 0 | 5 | 0 | OK |
| `test_station_stub` | 0 | 28 | 0 | OK | 0 | 28 | 0 | OK |
| `test_target_ships` | 0 | 10 | 0 | OK | 0 | 10 | 0 | OK |
| `test_texture32` | 1 | - | - | ModuleNotFoundError: No module named 'unicorn' | 1 | 6 | 0 | FAILED (errors=6) |
| `test_third_person` | 1 | - | - | ModuleNotFoundError: No module named 'capstone' | 1 | 0 | 0 | FAILED (errors=3) |
| `test_turret_groups` | 0 | 3 | 2 | OK (skipped=2) | 0 | 3 | 2 | OK (skipped=2) |
| `test_turret_trial` | 0 | 2 | 2 | OK (skipped=2) | 0 | 2 | 2 | OK (skipped=2) |
| `test_visibility_fix` | 1 | - | - | ModuleNotFoundError: No module named 'unicorn' | 1 | 0 | 0 | FAILED (errors=1) |
| `test_warp_headless` | 0 | 4 | 4 | OK (skipped=4) | 0 | 4 | 4 | OK (skipped=4) |
| `test_warp_trial` | 0 | 6 | 6 | OK (skipped=6) | 0 | 6 | 6 | OK (skipped=6) |
| `test_world_detail` | 1 | - | - | ModuleNotFoundError: No module named 'unicorn' | 1 | 0 | 0 | FAILED (errors=1) |
