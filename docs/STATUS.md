# Project status: what works, what is untested, what does not exist

This is the one page that states, as current fact, what has been verified
and what has not. Other docs link here instead of repeating it. Change this
page in the same commit as any change that makes a row untrue.

Last reviewed 14 November 2026, against the code on the `architecture-cleanup`
branch.

**How to read it.** "Verified" means someone saw it work and the evidence is
named: an evidence file under `evidence/`, or the dated section of a doc that
records the run. A test that uses synthetic clients on one machine is named
as such; it is not a play session. "Patch level" is the `patch_version` that
`tools/prepare_client.py` records in the game folder's `_client_setup.json`;
it is 22 today.

## Works, and how it was checked

| What | Checked | Evidence | Limits |
|---|---|---|---|
| Offline play on Windows 11 (training mission, tutorial) | 20 Oct 2026, Windows 11 23H2, 1920x1080 | [running-on-windows-11.md](running-on-windows-11.md) | Windows 10 and a clean, non-development PC have not been tried. |
| **Play between separate PCs, over a LAN, through the Linux host** | 26 Oct 2026: two Windows PCs fought; the operator reported damage and destruction, and the server log shows two valid player deaths, one per player | [linux_two_pc_combat_20261026.json](../evidence/2.9.2/linux_two_pc_combat_20261026.json) | Two players. The host ran the `vpn-dogfight` profile on a LAN address. The two-PC setup is the operator's report (the log hides addresses). The scoreboard on screen and visible respawns were not observed. The map is not recorded. |
| Linux host as a service | 26 Oct 2026 on an Ubuntu 24.04 VM: start at boot, recovery after a forced crash, a stalled process and a reboot; map rotation with two synthetic Windows clients over the LAN | [linux_host_20261026.json](../evidence/2.9.2/linux_host_20261026.json), [linux_rotation_20261026.json](../evidence/2.9.2/linux_rotation_20261026.json) | `dedicated_host.py` changed on 13 Nov 2026 (shared defaults, `--bind-address` required, status path); that version passes `test_dedicated_host.py` but has not been deployed. |
| Multiplayer on one PC with the host window | 23 Oct 2026: a real client joined CTF_arena, the host switched to JRMAP and the client rejoined; End match, Stop host and `say` worked | [host-control.md](host-control.md#verification-23-october-2026) | Run in the old "This PC only" mode (`local-relay`). See the host window row below for what changed since. |
| Client launcher (visual checkboxes, Apply, Play) | Toggles, persistence, rollback and checkbox wiring on temporary game copies | [client-setup.md](client-setup.md#client-launcher-and-visual-options) | No in-flight check of the individual visual effects. See the launcher row below for the 13 Nov changes. |
| F2 chase camera | On screen for the Ym Khtat, and for a Zkole picked from the fighter menu | [findings 9.41](findings.md#941-f2-showed-no-hull-after-a-fighter-menu-switch-25-october-2026) | |
| F4 orbit camera | A full lap on screen in the training mission (patch level 20); the level 21 culling fix checked with F5 captures at four lap angles | [orbit_camera_20261027.json](../evidence/2.9.2/orbit_camera_20261027.json), [findings 9.47](findings.md#947-an-orbit-camera-on-f4-f2-was-never-unbound-2627-october-2026), [9.48](findings.md#948-orbit-view-objects-blinked-because-culling-used-the-stock-camera-27-october-2026) | |
| Power-ups | One real client picked up a power-up 22 times in a row (F5 capture of "Shield +5"); the owner confirmed pickups on JRMAP hosted from the host window | [powerups_live_20261025.json](../evidence/2.9.2/powerups_live_20261025.json), [findings 9.44](findings.md#944-power-ups-decoded-hosted-and-blocked-by-two-292-client-changes-25-october-2026) | Only JRMAP has power-up zones. A second client watching a pickup, and which effects were covered, are not verified. Clients need patch level 19. |
| Target ships | One real client on Arena1a: gunfire brought a ship's hit points to 0, it was removed, and it came back 15 s later | [target_ships_damage_live_20261025.json](../evidence/2.9.2/target_ships_damage_live_20261025.json), [findings 9.46](findings.md#946-target-ships-take-damage-and-blow-up-the-original-servers-channels-25-october-2026) | Read from memory. Not verified: the explosion on screen, missile kills, a second client, other maps. The ships never fire back. |
| Maps load as native terrain | All 20 entries driven to flight in a real client; object counts read from memory | [map_viewer_tour_20261023.json](../evidence/2.9.2/map_viewer_tour_20261023.json) | See [Maps](#maps) for which have content and which have been seen. |

## Maps

The terrain hook has a table of 20 entries: the 19 layouts in the 2.9.2
archives plus JRMAP from the 2.0.0 editor file ([map-viewer.md](map-viewer.md#maps)).

- **11 have real content:** the 9 full layouts (Arena1a, CTF_arena,
  CTF_arena_b, newterrain, outerchange, ast_fld_a, ast_fld_b, ast_fld_c,
  ast_fld_d), the irrosa01 component (457 objects) and JRMAP (23).
- **5 are small components** shown alone (1 to 10 objects): CTF_base,
  hu_base_a, hu_base_b, hy_base_test, HyBase2Lay.
- **4 build nothing alone:** hy_winga, ze_winga, ze_wingb, Hittest.

**Seen on screen: 8 of the 20.**

| Map | Seen | Evidence |
|---|---|---|
| Arena1a | 22 Oct, owner confirmed the geometry is visible; 25 Oct, F5 captures | [online_terrain_20261022.json](../evidence/2.9.2/online_terrain_20261022.json), [safe_zones_20261025.json](../evidence/2.9.2/safe_zones_20261025.json) |
| CTF_arena, irrosa01 | 25 Oct, F5 captures | [safe_zones_20261025.json](../evidence/2.9.2/safe_zones_20261025.json) |
| irrosa01, ast_fld_a, ast_fld_b, outerchange, CTF_arena_b, JRMAP | 27 Oct, filmed for the highlight reel | the shot list [`aoa/reel/shots.json`](../aoa/reel/shots.json) and [hype-reel.md](hype-reel.md); the footage is not committed |

Not seen on screen: newterrain, ast_fld_c, ast_fld_d, and every component.

"Loaded" or "seen" does not mean playable as the original game was. No map
has verified collision, and turrets, warp gates, flags and missions are not
restored (see [below](#does-not-exist)). The Linux rotation uses CTF_arena,
CTF_arena_b and ast_fld_a.

## Implemented but not tested

| What | What has been done | What is missing |
|---|---|---|
| **LAN play between separate PCs with a Windows host** (host window in LAN mode, or `start_lan_dogfight.ps1`) | Synthetic clients on one PC, including through its LAN address ([lan_binding_20261021.json](../evidence/2.9.2/lan_binding_20261021.json)) | Any session between separate PCs. |
| **Internet play over a VPN** between separate connections | Loopback tests with simulated delay and loss (`test_internet_play.py`) | Any session between separate connections. The Linux host has not been reached over a VPN either. |
| More than two real players | Configuration only: up to 8 | Any session with three or more. |
| Rejoining after a map change, with terrain | Protocol tests; synthetic clients rejoined after rotation | A real client seen to load the next map after rejoining. |
| Host window, as changed on 13 Nov 2026: "This PC only" runs `local-guests` with sustained delivery; saved settings are checked; start-up errors go to `work/logs/host.log`; "Load map" checks the new settings before it stops the host | Game-free tests (`test_host_control.py`, `test_host_argv.py`) | The window and `host_control.cmd` have not been run on Windows since. LAN/VPN mode with other machines, kick/ban with a real client and automatic crash restart were never tested. |
| Client launcher and setup, as changed on 13 Nov 2026: options not named keep their state; older camera variants shown and upgraded; experimental protection switched off for a remote Station; `client_launcher.cmd` keeps its console open; `setup_game.ps1` requires `.venv` | Game-free tests (`test_prepare_client.py`, `test_client_launcher.py`, `test_install_wrapper.py`) | Not run on Windows, and the client-patch tests skip without the game. |
| `start_lan_dogfight.ps1`, as changed on 13 Nov 2026 (any map, settings read back from the server, logs under `work/host/`) | Its text is checked by `test_host_argv.py` | Not run. |
| Navigation buoys on every map | Packet and asset tests ([navigation_buoys_all_maps_20261026.json](../evidence/2.9.2/navigation_buoys_all_maps_20261026.json)) | Seen in the game. (A custom map's waypoint, sent the same way, was seen and targeted live: [custom-maps.md](custom-maps.md).) |
| Turret trial (five Arena1a turrets, firing disabled) | Original-code probes and socket tests ([turret_groups_20261026.json](../evidence/2.9.2/turret_groups_20261026.json)) | A client in flight with the trial loaded. Orientation is not sent; the model is a provisional choice. |
| Warp gate trial (nine Arena1a gates) | Headless original-code and socket checks ([warp_headless_20261027.json](../evidence/2.9.2/warp_headless_20261027.json)) | A gate seen in the game, or a transit. Orientation and real collision bounds are not restored. |
| Optional rendering patches and wrapper quality | Original-code emulation tests; asteroid and solid-world rendering confirmed by the owner in flight (22 Oct) | Distant objects, world detail and the wrapper quality options in flight; performance of any of them ([client-setup.md](client-setup.md)). |
| Experimental protection probe (`--experimental-protection`) | Emulation | It has not passed the manual client gate ([client-extension-gate.md](client-extension-gate.md)). |

## Does not exist

- Accounts, persistent pilots, persistent scores. Pilots, scores and bans
  last only as long as one host process.
- A public internet server. The supported route is a private VPN.
- Server-side damage for players: each client decides the hits it takes.
  There is no lag compensation.
- Seamless map changes: players quit, relaunch and rejoin.
- CTF rules, flags, capture points, AI missions online, and turrets that fire.
- Warp gate travel authorized by the host.
- Verified collision on any recovered map.
- A free map slot: a new map replaces JRMAP in a separate play copy
  ([custom-maps.md](custom-maps.md)).
- A console, kick or ban on the Linux service (use `systemctl`).
