# Audit: tests and CI

The Opus agent for this area was cut off by a usage limit after running every suite. The architect
completed the audit from its saved results and from the other five audits.

## Outcome of every suite on Linux, Python 3.13, no game files, no optional packages

`python3 -I tools/<suite>.py`. "ran" is the unittest count; a dash means the script died before unittest started.

| Suite | In CI | In verify_local | Exit | Ran | Result | Seconds |
|---|---|---|---|---|---|---|
| `test_aoapack_write` |  | yes | 1 | 0 | FAILED (errors=1) | 0.1 |
| `test_asteroid_render` |  | yes | 1 | - | ModuleNotFoundError: No module named 'unicorn' | 0.1 |
| `test_build_texture_pack` | yes | yes | 0 | 5 | OK | 0.9 |
| `test_client_extensions` | yes | yes | 0 | 1 | OK | 15.2 |
| `test_client_launcher` | yes | yes | 0 | 6 | OK (skipped=5) | 0.2 |
| `test_combat_delivery` | yes | yes | 0 | 1 | OK | 9.5 |
| `test_cursor_warp` |  | yes | 1 | - | ModuleNotFoundError: No module named 'unicorn' | 0.1 |
| `test_dedicated_host` | yes |  | 0 | 7 | OK | 18.9 |
| `test_frame_clock` |  | yes | 1 | - | ModuleNotFoundError: No module named 'unicorn' | 0.1 |
| `test_guest_admission` | yes | yes | 0 | 1 | OK | 7.3 |
| `test_host_control` | yes | yes | 0 | 8 | OK (skipped=5) | 0.1 |
| `test_internet_play` | yes | yes | 0 | 8 | OK | 21.0 |
| `test_lan_dogfight` | yes | yes | 0 | 4 | OK | 15.6 |
| `test_make_map` | yes |  | 0 | 12 | OK (skipped=1) | 0.2 |
| `test_make_object` | yes |  | 0 | 8 | OK (skipped=2) | 0.6 |
| `test_menu_aspect` |  |  | 1 | - | ModuleNotFoundError: No module named 'unicorn' | 0.1 |
| `test_navigation_buoys` |  |  | 0 | 4 | OK (skipped=4) | 0.1 |
| `test_network_bounds` | yes | yes | 0 | 6 | OK | 2.6 |
| `test_object_lod` |  |  | 1 | - | ModuleNotFoundError: No module named 'unicorn' | 0.1 |
| `test_object_persistence` |  | yes | 1 | - | ModuleNotFoundError: No module named 'unicorn' | 0.1 |
| `test_object_persistence_pipeline` |  | yes | 1 | - | ModuleNotFoundError: No module named 'unicorn' | 0.1 |
| `test_online_terrain` |  | yes | 1 | - | ModuleNotFoundError: No module named 'unicorn' | 0.1 |
| `test_physics_timestep` |  |  | 1 | - | IndexError: list index out of range | 0.1 |
| `test_powerup_pickup` |  | yes | 1 | - | ModuleNotFoundError: No module named 'pefile' | 0.1 |
| `test_powerups` | yes | yes | 0 | 7 | OK | 7.8 |
| `test_prepare_client` | yes | yes | 0 | 8 | OK (skipped=8) | 0.1 |
| `test_reel` |  |  | 0 | 4 | OK | 0.1 |
| `test_relay_motion` | yes | yes | 0 | 7 | OK | 0.1 |
| `test_relay_recovery` | yes | yes | 0 | 1 | OK | 5.2 |
| `test_render_clock_experiment` |  |  | 1 | - | ModuleNotFoundError: No module named 'unicorn' | 0.1 |
| `test_render_culling` |  | yes | 1 | - | ModuleNotFoundError: No module named 'unicorn' | 0.1 |
| `test_render_motion` |  |  | 1 | - | ModuleNotFoundError: No module named 'unicorn' | 0.1 |
| `test_scene_nodes` |  | yes | 1 | 6 | FAILED (errors=5) | 0.1 |
| `test_solid_world_render` |  | yes | 1 | - | ModuleNotFoundError: No module named 'unicorn' | 0.1 |
| `test_station_detail` |  | yes | 1 | - | ModuleNotFoundError: No module named 'unicorn' | 0.1 |
| `test_station_runtime` | yes | yes | 0 | 8 | OK | 7.1 |
| `test_station_sessions` | yes | yes | 0 | 5 | OK | 9.5 |
| `test_station_stub` | yes | yes | 0 | 27 | OK | 53.2 |
| `test_target_ships` | yes | yes | 0 | 10 | OK | 8.8 |
| `test_texture32` |  | yes | 1 | - | ModuleNotFoundError: No module named 'unicorn' | 0.1 |
| `test_third_person` |  | yes | 1 | - | ModuleNotFoundError: No module named 'capstone' | 0.1 |
| `test_turret_groups` |  |  | 0 | 3 | OK (skipped=2) | 0.1 |
| `test_turret_trial` |  |  | 0 | 2 | OK (skipped=2) | 0.1 |
| `test_visibility_fix` |  | yes | 1 | - | ModuleNotFoundError: No module named 'unicorn' | 0.1 |
| `test_warp_headless` |  |  | 0 | 4 | OK (skipped=4) | 0.1 |
| `test_warp_trial` |  |  | 0 | 6 | OK (skipped=6) | 0.1 |
| `test_world_detail` |  | yes | 1 | - | ModuleNotFoundError: No module named 'unicorn' | 0.1 |

## Findings

- **T1 (medium).** 18 suites die at import with `ModuleNotFoundError` (`unicorn`, `capstone` or `pefile`) instead of skipping. The Linux CI job installs none of these, so none of the patch suites can run there.
- **T2 (medium).** `test_prepare_client` (8 of 8) and `test_client_launcher` (5 of 6) are listed as CI gates but skip almost everything without the game.
- **T3 (medium).** 11 suites are in neither CI nor `verify_local.py`: `test_menu_aspect`, `test_navigation_buoys`, `test_object_lod`, `test_physics_timestep`, `test_reel`, `test_render_clock_experiment`, `test_render_motion`, `test_turret_groups`, `test_turret_trial`, `test_warp_headless`, `test_warp_trial`. `test_reel` is game-free and passes.
- **T4 (medium).** `test_physics_timestep` is an argv script (`IndexError` when run plainly). `test_aoapack_write` and `test_scene_nodes` error instead of skipping without game files. `test_make_map` and `test_make_object` print progress lines instead of a unittest summary.
- **T5 (medium).** 14 suites import `test_station_stub` as a library and 5 import `test_station_runtime`; `test_object_persistence_pipeline` imports `test_object_persistence`. Shared fixtures belong in a support module.
- **T6 (low).** `python -m unittest discover -s tools` ends with 24 errors and `pytest tools` with 81 failures and 59 errors, mostly from T1, T4 and import-time side effects. Neither is usable as a runner today.
- **T7 (low).** `verify_local.py` treats any skip as a failure and stops at the first failing suite, so one missing asset hides the state of every later suite.
- **T8 (low).** CI uses Python 3.12 and this audit ran 3.13; the 20 CI suites pass on both.

## Not checked

Port use and files left behind by suites, the emulator scripts as gate checks, and whether the pinned requirements install on Python 3.13 on Windows.
