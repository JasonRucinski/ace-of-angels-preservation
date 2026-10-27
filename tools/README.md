# Tools

Run everything from the repository root with the project's Python:
`.venv\Scripts\python.exe -I tools\<script>.py`. Each script's docstring
gives its usage. The player-facing scripts need only the standard library;
the analysis and emulation scripts need `requirements.txt`
(`pefile`, `capstone`, `unicorn`).

None of these runs the original installer. Scripts that change a game
executable accept only known, hash-checked builds and record an exact undo.

## Playing and hosting

| Script | Does |
|---|---|
| `fetch_known_builds.py DIR` | Downloads the verified 2.8.2 and 2.9.2 installers from archive.org and checks their hashes |
| `setup_game.ps1` | Builds a playable `game\2.9.2` folder: extract, patch, register, wrapper ([play.md](../docs/play.md)) |
| `prepare_client.py prepare/check/undo/launch EXE` | Applies every client fix with an exact undo, verifies the result, and launches the game |
| `host_control.cmd` / `host_control.py` | The host window: start, watch players, message, kick, switch maps, stop |
| `start_lan_dogfight.ps1` | Starts the LAN or VPN dogfight server from the command line |
| `map_viewer.py serve MAP` | Serves one recovered map for flying around |
| `station_stub.py` | The stand-in Station and arena server that all of the above run |
| `register_activeskin.ps1` | Registers the game's dialog skin control for the current user (no admin) |
| `make_install.py` / `install_wrapper.py` | The extract and wrapper steps of `setup_game.ps1` |
| `build_texture_pack.py GAME_DIR` | Builds the 2x skin pack from your own archives with Real-ESRGAN ([texture-pack.md](../docs/texture-pack.md)) |
| `texture_pack.py` | Installs or removes replacement TGA skins in a game folder |

## Server internals

`aoanet.py` (datagram codec), `aoacrypt.py` (packet cipher), `aoapack.py`
(`.aoa` archives and compression), `station_runtime.py` (configuration, logs,
TCP list), `relay_motion.py` (movement relay), `reliable_window.py` (ordered
reliable delivery), `host_ops.py` (status file and console), `net_impair.py`
(lag and loss testing), `decode_trn.py` and `online_terrain.py` (maps).

## Client patches

Each is a library used by `prepare_client.py`, with a matching `test_*.py`.
Details and addresses are in [client-setup.md](../docs/client-setup.md).

| Module | Fixes or adds |
|---|---|
| `patch_client.py` | Start-up heap overflow and logger thread-safety crashes |
| `physics_timestep.py` | NaN positions from zero-time physics steps |
| `archive_terminator.py` | Crash on arena entry from unterminated decompressed text |
| `frame_clock.py` | Uneven frame pacing from the 15.6 ms system tick |
| `visibility_fix.py` | Invalid trigonometry in visibility culling |
| `cursor_warp.py` | Dragged panels jumping to the corner |
| `menu_aspect.py` | Ship-selection framing on wide screens |
| `third_person.py` | F2 chase camera |
| `own_ship_model.py` / `own_ship_menu.py` | Drawing your own ship in the chase camera and after a ship change |
| `online_terrain.py` | Server-chosen maps, safe-zone cubes |
| `powerup_pickup.py` | Picking up server-placed power-ups |
| `texture32.py`, `world_detail.py`, `station_detail.py`, `solid_world_render.py`, `asteroid_render.py` | Optional rendering quality |
| `local_station.py`, `explicit_protection.py` | Station hostname; protection setter prototype |

## Finding builds and history

| Script | Does |
|---|---|
| `fetch.py` | Downloads one `manifest/downloads.json` entry and verifies it |
| `wayback_builds.py` | Lists and downloads builds the Wayback Machine saved |
| `restore_web_archive.py` | Rebuilds the old website and forums from Wayback captures |
| `ia_disc_find.py` | Searches inside archive.org disc images (log results in `data/disc_search.tsv`) |
| `ia_fulltext_search.py`, `ia_fulltext_context.py` | Full-text search of scanned magazines |
| `iso_stream_extract.py`, `rar_img2iso.py` | Pull files out of disc images without full extraction |
| `wise_extract.py`, `inventory.py` | List or extract a Wise installer without running it |
| `aoa_version.py`, `version_probe.py` | Read a client's real version from its code |

## Analysing the client

Static analysis: `pe_facts.py`, `pe_util.py`, `explore.py`, `dialogs.py`,
`config_records.py`, `packet_sizes.py`, `send_sites.py`, `dispatch_table.py`,
`message_table.py`, `match_funcs.py`, `offline_refs.py`, `server_senders.py`,
`gun_table.py`.

Emulation of original client code in Unicorn, without running the game:
`emulate_*.py`, `audit_render_pipeline.py`, `compare_render_clocks.py`.

Assets and maps: `export_assets.py`, `gob2obj.py`, `scene2obj.py`,
`export_legacy_models.py`, `render_obj.py`, `render_map_previews.py`,
`sco_dump.py`, `decode_scenario.py`, `decode_legacy_layout.py`,
`arena_inventory.py`, `check_arena_geometry.py`, `audit_*.py`,
`compare_version_assets.py`, `compare_client_resources.py`. Output goes to the
ignored `work\` folder and is never committed.

Live debugging of a running client: `crashdbg.py`, `inspect_arena.py`,
`sample_rendering.py`, `measure_frame_pacing.py`, `client_login.ps1`, and the
offline-only experiments `prepare_offline_baseline.py`,
`render_clock_experiment.py`, `render_culling_experiment.py`,
`seed_offline_velocity.py`.

## Tests

```powershell
.venv\Scripts\python.exe -I tools\verify_local.py
```

`verify_local.py` runs the supported regression gate: the `test_*.py` suites
and the emulators, about 10 minutes. It does not launch the game, but it needs
a prepared `game\2.9.2` folder (it reads the original `AOACLIENT.EXE.orig`).
Run a single suite with `.venv\Scripts\python.exe -I tools\test_station_stub.py`.

Without the game, the server, relay and host suites still run; the client-patch
suites fail for lack of the executable. CI runs the game-free list on every
push and pull request ([`.github/workflows/tests.yml`](../.github/workflows/tests.yml)).
