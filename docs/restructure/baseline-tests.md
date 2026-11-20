# Test baseline (phase 0a)

The outcome of every `tools/test_*.py` before any restructuring, for later
phases to diff against. Recorded on 13 November 2026 at `1852532` (the
`architecture-cleanup` branch with the two snapshot tests added), on Linux
with Python 3.13.17 and no game files (`game/`, `builds/`, `work/` absent).

Each suite was run from the repository root as `python -I tools/<suite>.py`:

- **Standard library only:** the system `python3`, with no packages installed.
- **With requirements:** a scratch venv with `requirements.txt` installed
  (capstone 5.0.3, pefile 2024.8.26, unicorn 2.1.1, Pillow 11.0.0).

"Ran" is the unittest count; a dash means the script died before unittest
started. "Skipped" is taken from the result line. Of 49 suites (the 47 the
audit counted plus `test_patch_layout` and `test_host_argv`), 28 pass in both
runs. Installing the requirements turns 18 import errors into errors at test
time: those suites read `game/2.9.2/AOACLIENT.EXE.orig` instead of skipping
without it (audit T1, C14). No suite changed from pass to fail or back.

The 22 suites in the CI list (`.github/workflows/tests.yml`) were also run
with only capstone, unicorn and pefile installed, as the Linux CI job now
does: all 22 exit 0 with the same counts as below.

Columns 2 to 5 are the standard-library run, columns 6 to 9 the run with
requirements.

## Refreshed before phase 1

Re-measured on 14 November 2026 at `28634d0` (phase 0 complete), the same
way: Linux, Python 3.13.17, no game files, each suite run from the
repository root as `python -I tools/<suite>.py`, once with the system
`python3` alone and once in a scratch venv with `requirements.txt`. This is
the table phase 1 is checked against. 53 suites; 33 pass in both runs.

Changes since the phase 0a table, all from phase 0b to 0d:

- New suites: `test_cli_help`, `test_polite_http`, `test_install_wrapper`,
  `test_make_vessel_combat`. `test_cli_help` skips the 28 entry points whose
  imports need a package that is not installed.
- More tests in existing suites: `test_client_launcher` 6 to 7,
  `test_dedicated_host` 7 to 8, `test_host_argv` 3 to 5, `test_host_control`
  8 to 15, `test_prepare_client` 8 to 14 (still all game tests skipped),
  `test_station_runtime` 8 to 10, `test_station_stub` 27 to 28.
- `test_physics_timestep` no longer dies with `IndexError`: it runs 1 test
  and skips it without the game.
- No suite changed from pass to fail.

Columns 2 to 5 are the standard-library run, columns 6 to 9 the run with
requirements.

| Suite | Exit | Ran | Skipped | Result | Exit | Ran | Skipped | Result |
|---|---|---|---|---|---|---|---|---|
| `test_aoapack_write` | 1 | 0 | 0 | FAILED (errors=1) | 1 | 0 | 0 | FAILED (errors=1) |
| `test_asteroid_render` | 1 | - | - | ModuleNotFoundError: No module named 'unicorn' | 1 | 5 | 0 | FAILED (errors=5) |
| `test_build_texture_pack` | 0 | 5 | 0 | OK | 0 | 5 | 0 | OK |
| `test_cli_help` | 0 | 108 | 28 | OK (skipped=28) | 0 | 108 | 0 | OK |
| `test_client_extensions` | 0 | 1 | 0 | OK | 0 | 1 | 0 | OK |
| `test_client_launcher` | 0 | 7 | 5 | OK (skipped=5) | 0 | 7 | 5 | OK (skipped=5) |
| `test_combat_delivery` | 0 | 1 | 0 | OK | 0 | 1 | 0 | OK |
| `test_cursor_warp` | 1 | - | - | ModuleNotFoundError: No module named 'unicorn' | 1 | 0 | 0 | FAILED (errors=1) |
| `test_dedicated_host` | 0 | 8 | 0 | OK | 0 | 8 | 0 | OK |
| `test_frame_clock` | 1 | - | - | ModuleNotFoundError: No module named 'unicorn' | 1 | 5 | 0 | FAILED (errors=2) |
| `test_guest_admission` | 0 | 1 | 0 | OK | 0 | 1 | 0 | OK |
| `test_host_argv` | 0 | 5 | 0 | OK | 0 | 5 | 0 | OK |
| `test_host_control` | 0 | 15 | 5 | OK (skipped=5) | 0 | 15 | 5 | OK (skipped=5) |
| `test_install_wrapper` | 0 | 3 | 0 | OK | 0 | 3 | 0 | OK |
| `test_internet_play` | 0 | 8 | 0 | OK | 0 | 8 | 0 | OK |
| `test_lan_dogfight` | 0 | 4 | 0 | OK | 0 | 4 | 0 | OK |
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

## Phase 0a table (13 November, superseded)

| Suite | Exit | Ran | Skipped | Result | Exit | Ran | Skipped | Result |
|---|---|---|---|---|---|---|---|---|
| `test_aoapack_write` | 1 | 0 | 0 | FAILED (errors=1) | 1 | 0 | 0 | FAILED (errors=1) |
| `test_asteroid_render` | 1 | - | - | ModuleNotFoundError: No module named 'unicorn' | 1 | 5 | 0 | FAILED (errors=5) |
| `test_build_texture_pack` | 0 | 5 | 0 | OK | 0 | 5 | 0 | OK |
| `test_client_extensions` | 0 | 1 | 0 | OK | 0 | 1 | 0 | OK |
| `test_client_launcher` | 0 | 6 | 5 | OK (skipped=5) | 0 | 6 | 5 | OK (skipped=5) |
| `test_combat_delivery` | 0 | 1 | 0 | OK | 0 | 1 | 0 | OK |
| `test_cursor_warp` | 1 | - | - | ModuleNotFoundError: No module named 'unicorn' | 1 | 0 | 0 | FAILED (errors=1) |
| `test_dedicated_host` | 0 | 7 | 0 | OK | 0 | 7 | 0 | OK |
| `test_frame_clock` | 1 | - | - | ModuleNotFoundError: No module named 'unicorn' | 1 | 5 | 0 | FAILED (errors=2) |
| `test_guest_admission` | 0 | 1 | 0 | OK | 0 | 1 | 0 | OK |
| `test_host_argv` | 0 | 3 | 0 | OK | 0 | 3 | 0 | OK |
| `test_host_control` | 0 | 8 | 5 | OK (skipped=5) | 0 | 8 | 5 | OK (skipped=5) |
| `test_internet_play` | 0 | 8 | 0 | OK | 0 | 8 | 0 | OK |
| `test_lan_dogfight` | 0 | 4 | 0 | OK | 0 | 4 | 0 | OK |
| `test_make_map` | 0 | 12 | 1 | OK (skipped=1) | 0 | 12 | 1 | OK (skipped=1) |
| `test_make_object` | 0 | 8 | 2 | OK (skipped=2) | 0 | 8 | 2 | OK (skipped=2) |
| `test_menu_aspect` | 1 | - | - | ModuleNotFoundError: No module named 'unicorn' | 1 | 2 | 0 | FAILED (errors=1) |
| `test_navigation_buoys` | 0 | 4 | 4 | OK (skipped=4) | 0 | 4 | 4 | OK (skipped=4) |
| `test_network_bounds` | 0 | 6 | 0 | OK | 0 | 6 | 0 | OK |
| `test_object_lod` | 1 | - | - | ModuleNotFoundError: No module named 'unicorn' | 1 | 0 | 0 | FAILED (errors=1) |
| `test_object_persistence` | 1 | - | - | ModuleNotFoundError: No module named 'unicorn' | 1 | 0 | 0 | FAILED (errors=1) |
| `test_object_persistence_pipeline` | 1 | - | - | ModuleNotFoundError: No module named 'unicorn' | 1 | 2 | 0 | FAILED (errors=2) |
| `test_online_terrain` | 1 | - | - | ModuleNotFoundError: No module named 'unicorn' | 1 | 8 | 0 | FAILED (errors=46) |
| `test_patch_layout` | 0 | 7 | 0 | OK | 0 | 7 | 0 | OK |
| `test_physics_timestep` | 1 | - | - | IndexError: list index out of range | 1 | - | - | IndexError: list index out of range |
| `test_powerup_pickup` | 1 | - | - | ModuleNotFoundError: No module named 'pefile' | 1 | 0 | 0 | FAILED (errors=1) |
| `test_powerups` | 0 | 7 | 0 | OK | 0 | 7 | 0 | OK |
| `test_prepare_client` | 0 | 8 | 8 | OK (skipped=8) | 0 | 8 | 8 | OK (skipped=8) |
| `test_reel` | 0 | 4 | 0 | OK | 0 | 4 | 0 | OK |
| `test_relay_motion` | 0 | 7 | 0 | OK | 0 | 7 | 0 | OK |
| `test_relay_recovery` | 0 | 1 | 0 | OK | 0 | 1 | 0 | OK |
| `test_render_clock_experiment` | 1 | - | - | ModuleNotFoundError: No module named 'unicorn' | 1 | 2 | 0 | FAILED (errors=1) |
| `test_render_culling` | 1 | - | - | ModuleNotFoundError: No module named 'unicorn' | 1 | 0 | 0 | FAILED (errors=1) |
| `test_render_motion` | 1 | - | - | ModuleNotFoundError: No module named 'unicorn' | 1 | 3 | 0 | FAILED (errors=3) |
| `test_scene_nodes` | 1 | 6 | 0 | FAILED (errors=5) | 1 | 6 | 0 | FAILED (errors=5) |
| `test_solid_world_render` | 1 | - | - | ModuleNotFoundError: No module named 'unicorn' | 1 | 5 | 0 | FAILED (errors=5) |
| `test_station_detail` | 1 | - | - | ModuleNotFoundError: No module named 'unicorn' | 1 | 5 | 0 | FAILED (errors=5) |
| `test_station_runtime` | 0 | 8 | 0 | OK | 0 | 8 | 0 | OK |
| `test_station_sessions` | 0 | 5 | 0 | OK | 0 | 5 | 0 | OK |
| `test_station_stub` | 0 | 27 | 0 | OK | 0 | 27 | 0 | OK |
| `test_target_ships` | 0 | 10 | 0 | OK | 0 | 10 | 0 | OK |
| `test_texture32` | 1 | - | - | ModuleNotFoundError: No module named 'unicorn' | 1 | 6 | 0 | FAILED (errors=6) |
| `test_third_person` | 1 | - | - | ModuleNotFoundError: No module named 'capstone' | 1 | 0 | 0 | FAILED (errors=3) |
| `test_turret_groups` | 0 | 3 | 2 | OK (skipped=2) | 0 | 3 | 2 | OK (skipped=2) |
| `test_turret_trial` | 0 | 2 | 2 | OK (skipped=2) | 0 | 2 | 2 | OK (skipped=2) |
| `test_visibility_fix` | 1 | - | - | ModuleNotFoundError: No module named 'unicorn' | 1 | 0 | 0 | FAILED (errors=1) |
| `test_warp_headless` | 0 | 4 | 4 | OK (skipped=4) | 0 | 4 | 4 | OK (skipped=4) |
| `test_warp_trial` | 0 | 6 | 6 | OK (skipped=6) | 0 | 6 | 6 | OK (skipped=6) |
| `test_world_detail` | 1 | - | - | ModuleNotFoundError: No module named 'unicorn' | 1 | 0 | 0 | FAILED (errors=1) |
