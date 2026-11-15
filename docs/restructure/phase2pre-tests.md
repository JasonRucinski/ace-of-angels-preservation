# Test outcomes after phase 2-pre

Every suite after the phase 2-pre task ([briefs/phase2pre.md](briefs/phase2pre.md)),
measured on 15 November 2026 at `bca05d1` the same way as
[phase1-tests.md](phase1-tests.md): Linux, Python 3.13.17, no game files,
once with the system `python3` alone and once in a scratch venv with
`requirements.txt`, each suite in its own `python -I` process through
`tests/runner.py` (the two archived suites by their dotted names).

## Difference from phase 1

- **Unchanged:** all 55 phase 1 suites have the same exit code, test count,
  skip count and result in both runs, except `test_imports`. The 20 suites
  that exit 1 still do so with the same counts: 18 of them need `unicorn`,
  `capstone` or `pefile` at import, and with the requirements all 20 read
  the missing game files. None of them imports the moved code without an
  optional package, so none changed column.
- **`test_imports`:** 127 to 130 tests (the new `aoa.builds`,
  `aoa.formats.pe` and `aoa.maps.registry`). Without the requirements it
  skips 20 instead of 21: `aoa.maps.arena1a_audit` no longer needs
  capstone and pefile. All 20 skips are under `aoa.analysis`,
  `aoa.emulation` and `aoa.research.version_probe`; everything under
  `aoa.formats`, `aoa.protocol`, `aoa.maps` and `aoa.host`, and
  `aoa.client.texture_pack`, imports with the standard library only.
- **New, in the CI tier:** `test_builds` (3 tests), `test_pe` (5; the
  comparison with `pefile` skips without the requirements) and
  `test_map_registry` (4).
- `test_layering` has no known violations left (`KNOWN` is empty).
- `tests/snapshots/patch_regions.json` and `host_configs.json` differ from
  phase 1 only in their `about` text; both snapshot suites pass without
  `--update`.
- `test_make_map` and `test_make_object` no longer need capstone for the
  archive key; their game checks still skip here for want of the game.

Columns 2 to 5 are the standard-library run, columns 6 to 9 the run with
requirements.

| Suite | Exit | Ran | Skipped | Result | Exit | Ran | Skipped | Result |
|---|---|---|---|---|---|---|---|---|
| `test_aoapack_write` | 1 | 0 | 0 | FAILED (errors=1) | 1 | 0 | 0 | FAILED (errors=1) |
| `test_asteroid_render` | 1 | - | - | ModuleNotFoundError: No module named 'unicorn' | 1 | 5 | 0 | FAILED (errors=5) |
| `test_build_texture_pack` | 0 | 5 | 0 | OK | 0 | 5 | 0 | OK |
| `test_builds` | 0 | 3 | 0 | OK | 0 | 3 | 0 | OK |
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
| `test_imports` | 0 | 130 | 20 | OK (skipped=20) | 0 | 130 | 0 | OK |
| `test_install_wrapper` | 0 | 3 | 0 | OK | 0 | 3 | 0 | OK |
| `test_internet_play` | 0 | 8 | 0 | OK | 0 | 8 | 0 | OK |
| `test_lan_dogfight` | 0 | 4 | 0 | OK | 0 | 4 | 0 | OK |
| `test_layering` | 0 | 3 | 0 | OK | 0 | 3 | 0 | OK |
| `test_make_map` | 0 | 12 | 1 | OK (skipped=1) | 0 | 12 | 1 | OK (skipped=1) |
| `test_make_object` | 0 | 8 | 2 | OK (skipped=2) | 0 | 8 | 2 | OK (skipped=2) |
| `test_make_vessel_combat` | 0 | 3 | 1 | OK (skipped=1) | 0 | 3 | 1 | OK (skipped=1) |
| `test_map_registry` | 0 | 4 | 0 | OK | 0 | 4 | 0 | OK |
| `test_menu_aspect` | 1 | - | - | ModuleNotFoundError: No module named 'unicorn' | 1 | 2 | 0 | FAILED (errors=1) |
| `test_navigation_buoys` | 0 | 4 | 4 | OK (skipped=4) | 0 | 4 | 4 | OK (skipped=4) |
| `test_network_bounds` | 0 | 6 | 0 | OK | 0 | 6 | 0 | OK |
| `test_object_lod` | 1 | - | - | ModuleNotFoundError: No module named 'unicorn' | 1 | 0 | 0 | FAILED (errors=1) |
| `test_object_persistence` | 1 | - | - | ModuleNotFoundError: No module named 'unicorn' | 1 | 0 | 0 | FAILED (errors=1) |
| `test_object_persistence_pipeline` | 1 | - | - | ModuleNotFoundError: No module named 'unicorn' | 1 | 2 | 0 | FAILED (errors=2) |
| `test_online_terrain` | 1 | - | - | ModuleNotFoundError: No module named 'unicorn' | 1 | 8 | 0 | FAILED (errors=46) |
| `test_patch_layout` | 0 | 7 | 0 | OK | 0 | 7 | 0 | OK |
| `test_pe` | 0 | 5 | 1 | OK (skipped=1) | 0 | 5 | 0 | OK |
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
