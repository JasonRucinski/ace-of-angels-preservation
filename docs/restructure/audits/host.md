# Audit: host / stand-in server stack

Auditor scope: `tools/station_stub.py` and its satellites, the four launchers
(`host_control.py`/`.cmd`, `dedicated_host.py`, `start_lan_dogfight.ps1`,
`map_viewer.py serve`), `deploy/linux/`, their tests and the host docs.
Repository untouched. Scratch harnesses live in
`/tmp/claude-0/-home-user-ace-of-angels-preservation/aa6c448b-b9bf-502a-a8dd-784488e1ac3d/scratchpad/arch/host/`
(`hc_check.py`, `doc_cmds.py`, `doc2.py`, `fake/`, `opt/`).

## 1. Summary

- The CLI surface is one argparse in `station_runtime.parse_args` (56 flags,
  5 profiles). Every flag is read somewhere: no flag is entirely dead. Several
  are silently ignored outside the combination they need, though, and
  `--advertised-address` cannot change anything because it must equal
  `--bind-address`.
- Every launcher passes flags that still exist and mean the same thing. I fed
  all 2,880 settings combinations of `host_control.server_args` through
  `parse_args` and none was rejected. The dedicated controller's own defaults
  are invalid: its default profile `vpn-dogfight` with default bind
  `127.0.0.1` fails, and the argparse error escapes its error handling.
- **Defaults and policy have drifted across four launchers.** Max players is
  8/4/2/2, kill/time limits are 20/600 vs 10/900, status paths differ, and so
  do restart budgets, Python resolution and map lists. The PowerShell launcher
  hard-codes a wrong "with Arena1a terrain" message and only allows 2 of the 20
  maps. "This PC only" in the GUI uses `local-relay` (no guest ownership, no
  sustained delivery), so local testing does not exercise the LAN/VPN code
  path.
- `--print-config` validation is shallow: settings that pass it can still fail
  in `run()`. A missing `JRMAP.TRN` (navigation buoys are on by default in the
  GUI) gives a misleading "check that 127.0.0.1 belongs to this PC and the ports
  are free". `--start-vessel Bogus` ends in an uncaught traceback.
- `station_stub.py` is 1,900 lines. `run()` alone is 780 lines (1117–1897) with
  ~16 closures over ~25 mutable locals. Protocol codecs, session state, two
  reliable-delivery engines, combat ledgers, power-ups, target ships and the
  TCP list format share one module. Dead or test-only code: `connect_req_fields`,
  `TCP_REQUEST_LEN`, `reported_motion`, `motion_snapshot`, the trailing
  `udp_replies` call (can never emit), and `TCP_JOB_BODIES[5]`.
- **Layering is inverted.** Importing the server pulls in the client patcher
  (`patch_client` via `online_terrain`), asset tools (`aoapack`, `scene2obj`,
  `gob2obj`) and two RE audit scripts (`audit_turret_groups`,
  `audit_warp_gates`). There is a real cycle:
  `station_stub -> warp_trial -> audit_warp_gates -> (lazy) station_stub`. The
  generator `make_vessel_combat.py` imports the whole server for one frozenset.
- Object-slot allocation is spread across 5 modules and 6 literal numbers:
  test object 1, targets 2..99, warp 71..79, turrets 80..84, buoys 90..99,
  power-ups 100..499, missiles 500+. `parse_args` re-encodes these ranges as 69, 78, 88 and 98.
- **Test gaps.** `test_turret_trial`, `test_warp_trial`, `test_warp_headless`,
  `test_turret_groups` and `test_navigation_buoys` are in neither CI nor
  `verify_local.py`. `start_lan_dogfight.ps1`, `map_viewer.py serve` and the
  deploy env/rotation files have no tests. `test_dedicated_host` is CI-only.
- Docs mostly run as written: all 21 doc command lines I extracted parse. Gaps:
  15 flags are documented nowhere (console, impairment, managed-session
  tuning), several claims are stale, and the "experimental" prefix now marks
  the mandatory production path (`--experimental-relay` and
  `--experimental-terrain` are on in every dogfight or rotation host).

## 2. Findings

Severity: H = breaks or misleads users/operators, M = misleads contributors or
latent bug, L = cleanup.

| ID | Sev | Location | Problem | Verified by | Suggested fix |
|---|---|---|---|---|---|
| H1 | M | `dedicated_host.py:169-171` | Defaults `--profile vpn-dogfight` + `--bind-address 127.0.0.1` are mutually invalid. The `parse_args` SystemExit raised inside `server_config(...)` (line 186) bypasses the `try/except` (it is not OSError/ValueError/RuntimeError), so the operator gets the **server's** full usage text under the prog name `dedicated_host.py`, exit 2. | Ran `dedicated_host.py ... --check` without `--bind-address`: rc=2, station usage printed. | Make `--bind-address` required for dogfight profiles (or default to local-guests on loopback). Call `parse_args` with `exit_on_error=False`, or catch SystemExit and re-raise as ValueError with the last message line. |
| H2 | M | `station_stub.py:1121-1125`, `main()` 1104-1113; `host_control.py:57-76,128-129` | With terrain on, the GUI passes `--navigation-buoys` by default (`DEFAULTS["navigation_buoys"]=True`). For JRMAP, `navigation_buoys.map_placements` reads `--buoy-trn`, which defaults to `<key dir>/JRMAP.TRN`. `HostProcess.start` checks only `jrmap292.trn`. If the file is missing, `main()` turns the FileNotFoundError into "Host I/O failed … Check that 127.0.0.1 belongs to this PC and the ports are free". | Ran the stub with `--map JRMAP --navigation-buoys <dir>` and no JRMAP.TRN; got exactly that message. | Move placement loading (and the asset-inventory checks) into config validation so `--print-config` catches it. Give asset-loading errors their own message. Have the GUI check JRMAP.TRN. |
| H3 | M | `station_runtime.py:104,154`; `station_stub.py:1183-1185` | `--start-vessel` is checked against `SELECTABLE_VESSELS` only in `run()`, so `--print-config` accepts `Bogus` and the real run dies with an uncaught ValueError traceback. The `"Ym Khtat"` literal is duplicated (runtime:104,154; stub:286,797,962). | Ran with `--start-vessel Bogus`: traceback at stub:1185. | Move `SELECTABLE_VESSELS` and `DEFAULT_VESSEL` into a data module (they equal `vessel_combat.VESSELS` keys, verified) and use `choices=` in argparse. |
| H4 | M | `start_lan_dogfight.ps1:67` | Prints "with Arena1a terrain" whenever `-Terrain` is given, even for `-Map CTF_arena`. | Read. | Print `with $Map terrain`. |
| H5 | M | `start_lan_dogfight.ps1:19` | `ValidateSet('CTF_arena','Arena1a')`: the LAN/VPN script offers 2 maps, while the server, GUI and dedicated host accept all 20 (`online_terrain.MAP_NAMES`). The script also cannot pass target ships, power-ups, objects or limits. | Read; compared with `online_terrain.MAPS`. | Retire the script in favour of a Python launcher CLI (see §4), or let it forward extra arguments to the server. |
| H6 | M | `host_control.py:31`, `MODES["This PC only"]="local-relay"` | Local mode uses `local-relay`, so `guest_sessions=False` (no Station ticket/pilot ownership) and sustained delivery is off unless map objects are on. LAN/VPN use guest admission (plus sustained on VPN). A "works on this PC" test does not cover the admission and delivery path friends will use. `dedicated_host` does not even offer `local-relay`; its loopback choice is `local-guests` (line 169). | `parse_args` output in `doc_cmds.py` (`guests=False` for local-relay, `True` for dogfight). | Use `local-guests` + `--sustained-delivery` for the GUI's local mode, or add a "like VPN" local option. |
| H7 | M | defaults in `station_runtime.py:77,81-82`, `host_control.py:36-38`, `start_lan_dogfight.ps1:18,77`, `dedicated_host.py:23-26,172`, `deploy/linux/host.env.example` | Default drift. Max players: server 8, GUI 4, PS1 2, dedicated 2. Kill/time limits: server, GUI and PS1 20/600 s; dedicated rotation 10/900 s. PS1 hard-codes the text "20 kills / 10 minutes" (line 77) instead of reading it from config. play.md says "20 kills or 10 minutes" without noting the Linux difference. | Read. | One `HostConfig` default table (see §4). The rotation file overrides it explicitly. |
| H8 | L | `host_control.py:142,169-171` vs `start_lan_dogfight.ps1:34` vs deploy | Three status-file conventions: `work/host/<profile>-status.json`, `work/<profile>-status.json` and `/var/lib/ace-of-angels/status.json`. Two staleness checks: the GUI uses `updated_utc` age > 8 s, dedicated uses mtime + pid with a 30 s timeout. | Read. | Shared `status_path(profile)` plus one `read_status(path, pid)` helper in `host_ops`. |
| H9 | M | `station_runtime.py:64,206-213` | `--advertised-address` must equal `--bind-address`, so the flag is a no-op that still appears in docs (`lan-dogfight.md:72`, `arena1a-rebuild.md:140,265`). | Read and `parse_args`. | Remove it, or implement a real NAT/advertise split. Until then, drop it from doc commands. |
| H10 | L | `station_runtime.py` (various) | Flags silently ignored outside their mode, all accepted by `--print-config`. `--next-map`, `--restart-warning`, `--recycle-*` and `--idle-recycle` need `--managed-session`. `--reorder-margin` needs sustained delivery. `--buoy-trn` needs `--navigation-buoys` + JRMAP. `--spawn-axis`, `--spawn-spacing`, `--kill-limit`, `--time-limit` and `--start-vessel`'s menu need the relay. `--pilot` becomes only a prefix with guest profiles. | Read `parse_args`; grep of `args.<flag>` uses in the stub (script in transcript). | Reject or warn on mode-irrelevant flags. Group them in argparse argument groups per feature. |
| H11 | M | `station_runtime.py:218-221` vs `156-195` | Policy inconsistency: dogfight profiles forbid "experimental … objects or teams" (`--experimental-object`, one passive ship), yet allow `--target-ships`, `--turret-trial` (provisional model, firing disabled) and `--navigation-buoys` on LAN/VPN. Only the warp trial is restricted to loopback. The GUI exposes the turret trial in LAN/VPN mode. | `doc2.py`: `lan-dogfight ... --turret-trial` parses OK. | Decide the rule explicitly (e.g. "trials are loopback-only") and put it in one table that the GUI's `node_availability` reads too. |
| H12 | M | `station_stub.py:59-66` (imports), `warp_trial.py:9-10`, `turret_trial.py:9-10`, `audit_warp_gates.py:168`, `online_terrain.py:23` | Inverted layering and a cycle. The server imports `audit_turret_groups` and `audit_warp_gates` (RE scripts), `patch_client` (client patcher), `aoapack`, `scene2obj` and `gob2obj`. `audit_warp_gates` lazily imports `station_stub.movement_update`, which closes the cycle. The Linux host is described as "standard-library-only" (`tests.yml:30`). That is true today only because `emulate_codec`/unicorn are imported lazily. | `imports.json` closure; imported `station_stub` with `-I` and listed `sys.modules`: audit_* and patch_client present, unicorn absent. | Move `hierarchy()` and `routes()` into the maps/assets package. Split `online_terrain` into a map registry (`MAPS`, `marker`, `spawn`) and a client patch. Put movement codecs in protocol. |
| H13 | L | `station_stub.py:76-85,121,970-998,269-283,1895-1896,1064-1071` | Dead or test-only code inside the server. `connect_req_fields` and `TCP_REQUEST_LEN` are unused; the runtime hard-codes 142. `reported_motion` and `motion_snapshot` are used only by `emulate_movement.py`/`test_warp_headless.py`. The final `udp_replies(...)` call can never emit: every 0x0A/381 path `continue`s earlier and a nested 0x1B is dropped. `TCP_JOB_BODIES[5]` is used only by tests, because `run()` replaces job 5. | grep counts (definition-only); read control flow 1683-1785. | Delete. Move the emulator-only helpers into the emulator or protocol module. |
| H14 | M | `station_stub.py:371-449` + `reliable_window.py` | Two reliable-delivery engines behind an implicit interface. The stub duck-types them (`getattr(removals, "expired", 0)`, `getattr(removals, "next_due", …)`, and `essential=` is passed only on the windowed path). `--experimental-reliable-combat` (30-event budget) and `--experimental-protection-probe` exist only to keep the old engine alive; `ReliableRemovals` is also used by `emulate_reliable_history.py`. | Read 1194-1200, 1318-1360, 1534-1549. | Define a small `Delivery` protocol class and keep one engine for play. Move `ReliableRemovals` and the two flags under a `diagnostics` module or retire them. |
| H15 | M | `station_runtime.py:156-195`; `station_stub.py:707-893,946-969`; `warp_trial.py:12`; `turret_trial.py:12`; `navigation_buoys.py:20` | The object index/tag space is allocated in six places and checked with literals: targets ≤98, ≤69 with warp, ≤78 with turrets, ≤88 with buoys. Power-ups use tag high bits `0x4000xxxx`, the others `0x4001xxxx`. Adding any new object kind means editing 5 files. | Read all ranges. | One `object_slots.py` registry (`allocate(kind, count)`) used by both validation and placement. |
| H16 | M | `make_vessel_combat.py:21`; `vessel_combat.py` | The generator imports the entire server (`import station_stub`) only for `SELECTABLE_VESSELS`. Nothing checks that the generated `vessel_combat.py` still matches its generator. `make_vessel_combat.py --help` crashes (`ValueError: not enough values to unpack`), because there is no argparse. | Ran it; compared sets (equal, 32). | Put the vessel list in a data module. Add argparse and a `--check` mode that regenerates into memory and diffs. |
| H17 | M | `.github/workflows/tests.yml:37-43`, `tools/verify_local.py:16-26` | Never run by any gate: `test_turret_trial`, `test_warp_trial`, `test_warp_headless`, `test_turret_groups` and `test_navigation_buoys`. `test_dedicated_host` runs in CI but not in `verify_local.py`. `host-control.md:97-99` says `test_host_control` "is part of `verify_local.py`", which is true, but 5 of its 8 tests skip without game files. There are no tests for the PS1, `map_viewer serve` or `deploy/linux/*.example`. | Ran each suite: all OK (mostly skipped, no assets). Grepped tests for launcher names. | Add the five suites to `verify_local.py` (they need assets) and `test_dedicated_host` too. Add a game-free test that builds each launcher's argv and runs `parse_args`, including the deploy example. `doc_cmds.py` is a template. |
| H18 | L | `host_control.py:520-521` | No argparse: `host_control.py --help` (or any typo) opens the Tk window, and only `--autostart` is recognised. | Read. | Add argparse. |
| H19 | L | `start_lan_dogfight.ps1:7`; `lan-dogfight.md:52-53` | The help and docs list console commands as "status, kick, ban, end, help". `say` and `quit` exist (`host_ops.HELP`). `lan-dogfight.md:66-70` calls a bare `station_stub` line "the equivalent Python command", but it lacks the `--map`, `--backdrop`, `--console` and `--status-file` the PS1 adds. | Read. | Point to `host_ops.HELP`. Show the exact PS1-equivalent line. |
| H20 | L | `station_stub.py:1-38`, `local-server.md:20-23,87-89` | Stale prose. The stub's Usage line omits `--profile`. local-server.md says "there is no public bind option" (LAN/VPN profiles now bind private/VPN addresses) and that console output is "limited to startup addresses and a shutdown summary" (it now prints counts, a console prompt and other messages). | Read. | Regenerate the flag reference from argparse (`--help` dump) into local-server.md. |
| H21 | L | docs vs `parse_args` | 15 flags are documented in no doc: `--console`, `--impair-rtt-ms`, `--impair-jitter-ms`, `--impair-loss`, `--impair-duplicate`, `--impair-seed`, `--next-map`, `--restart-warning`, `--recycle-arena-joins`, `--recycle-station-admissions`, `--idle-recycle`. `--experimental-relay` and `--status-file` appear only in findings and rebuild notes. | grep of every flag over `docs/`, CONTEXT.md and README (loop in transcript). | Same as H20: one generated flag table. |
| H22 | L | `docs/first-playable-release.md:22-31,93-111`; `internet-server-todo.md:282,357,401` | Stale status. The release spec says ship selection "remain[s]" and calls `Ym Khtat` the only ship, but `change_vessel` serves 32 ships. "Current gate passes 60 tests" (`test_station_stub` alone now has 27). The todo lists unchecked "map selection, rotation" and "one dedicated host" with no pointer to `dedicated_host.py`/linux-host.md. Item 121 still says "(10 tests)". | Read; ran `test_station_stub` (27 tests). | Add "implemented by …" notes. Mark date-stamped counts as historical. |
| H23 | L | `host_control.py:239`, `host-control.md:28,34`, `station_runtime.py:94-95`, `map-viewer.md:11-12` | Two names for the same client requirement: "patch v11" / "patch version 19" (`prepare_client.PATCH_VERSION`, now 22) vs "online-terrain-v2 (or later)" (the patch is now `online-terrain-v3`). | grep. | Name client capabilities once (e.g. `REQUIRES = {"terrain": 11, "powerups": 19}` in the client package). Have the host and GUI print from it. |
| H24 | L | `turret_groups.py:1` | Docstring says "not enabled in the host yet", but `turret_trial.loads` uses `status()` in every turret-trial host to disable turrets. | Read. | Update the docstring. |
| H25 | L | `station_stub.py:1696-1704` | The version-rejection reply (result 8) is sent before the `banned_ips` check, so a banned IP still gets answers to wrong-version handshakes. | Read order. | Check bans first. |
| H26 | L | `dedicated_host.py:93-97` | On Windows, `stop_child` uses `terminate()`, which skips the child's log drain. The module sets `CREATE_NO_WINDOW` (so Windows was considered), but there is no console/quit path. | Read. | Send `quit` over stdin as `host_control` does, or document the controller as Linux-only. |
| H27 | L | `local_station.py` | Listed in my area, but it is a client patch (hostname edit). Its CLI is historical (`running-on-windows-11.md:98` says "Historically"). Only its constants are imported, by `prepare_client`, `physics_timestep` and `prepare_offline_baseline`. | Read; import graph. | Move the constants into the client-patching package and archive the CLI. |
| H28 | L | `aoanet.py:1`, `aoanet.py:__main__`, `aoacrypt.py:__main__` | The protocol codec docstring cites the 2.7.1 client while the server targets 2.9.2. Both `__main__` blocks take a key path, so `--help` is read as a filename. `aoanet` depends on `aoapack` (asset archive module) for CCompress and CRC. | Ran `--help` (FileNotFoundError). | Move CCompress and CRC16 into a protocol/codec module that both aoapack and aoanet import. |

What I ran, and the cleanup afterwards:
- `--help` on station_stub, dedicated_host, map_viewer, local_station,
  net_impair, relay_motion, reliable_window, make_vessel_combat,
  turret_trial, warp_trial, navigation_buoys, online_terrain, aoanet and
  aoacrypt. I read the risky ones afterwards (after the safety note) and none
  of them had side effects for that invocation. make_vessel_combat
  crashed while unpacking argv before it read or wrote anything. aoanet and
  aoacrypt failed opening the file "--help". The library modules have no
  `__main__` or failed on import.
- `station_stub` runs with a fake key, from inside the scratch `fake/` dir,
  with ephemeral ports and logs in scratch.
- The host test suites, run in place from the repo.
- Cleanup: `git status --short` showed no tracked changes and no untracked
  files. I removed `tools/__pycache__/`, created by my imports. I left alone
  the pre-existing ignored `wb/` (dated 2026-10-26) and
  `tools/reel/__pycache__/` (not mine).

What I did NOT check: real-client behaviour, Windows-only code paths
(Tk GUI widgets, PowerShell `Get-NetIPAddress`, `.cmd`), `systemd-analyze
verify` (not available here), game-asset-dependent suites (all skipped),
`relay_motion`/`reliable_window` math correctness, the reel/bot tools, and
every non-command claim in the 540-line `internet-server-todo.md`.

## 3. Answers to the specific questions

### Q1 Profiles and flags

Profiles (`station_runtime.py:60`): `diagnostic` (default; no replies,
loopback), `local-relay` (ack+arena+relay+TCP 5034, loopback, direct
admission), `local-guests` (same plus Station ticket/guest pilots),
`lan-dogfight` (plus RFC1918 bind, max 8 players, no experiments), and
`vpn-dogfight` (lan-dogfight plus the 100.64/10 range, sustained delivery on by
default). Profiles only set the defaults of `ack`, `arena`,
`experimental_relay`, `tcp`, `guest_sessions` and `sustained_delivery`. They
are not a separate config object.

Flag classes:
- Core and play: key, log, `--profile`, `--bind-address`, `--port`,
  `--arena-port`, `--tcp`, `--map`, `--backdrop`, `--max-players`,
  `--kill-limit`, `--time-limit`, `--peer-timeout`, `--seconds`, `--pilot`,
  `--status-file`, `--console`, `--log-max-bytes`, `--log-backups`,
  `--raw-capture`, `--print-config`.
- Named "experimental" but used in production: `--experimental-relay`
  (required by every dogfight profile) and `--experimental-terrain` (on in the
  dedicated rotation and the GUI default). `--sustained-delivery` is
  production too, but not prefixed.
- Truly experimental or diagnostic: `--experimental-flight`,
  `--experimental-object`, `--experimental-teams`,
  `--experimental-reliable-combat`, `--experimental-protection-probe`,
  `--spawn-axis`/`--spawn-spacing`, `--impair-*` (TEST ONLY).
- Trials: `--turret-trial`, `--warp-trial`, `--arena1a-buoys` (legacy,
  superseded by `--navigation-buoys`; mutually exclusive),
  `--navigation-buoys`, `--buoy-trn`, `--map-waypoints`, `--powerup-zones`,
  `--target-ships`, `--start-vessel`, `--spawn-at`.
- Managed session (dedicated only): `--managed-session`, `--next-map`,
  `--restart-warning`, `--recycle-arena-joins`,
  `--recycle-station-admissions`, `--idle-recycle`.
- Does nothing: `--advertised-address` (H9).
- Silently ignored outside their mode: see H10.
- Conflicts (enforced): sustained vs reliable-combat/protection-probe;
  protection-probe vs relay; dogfight profiles vs flight/object/teams/
  reliable-combat; navigation-buoys vs arena1a-buoys vs map-waypoints; slot
  budgets vs target-ships.

Launcher mismatches. No launcher passes a removed flag or a flag whose meaning
changed. The argv for all 2,880 host_control settings combinations parses;
`doc_cmds.py` covers the PS1, map_viewer, deploy and docs. Mismatches:
1. dedicated_host's default bind is invalid for its default profile (H1).
2. PS1: 2 of 20 maps, a wrong terrain message, a hard-coded limits string, a
   different status path, and the console help omits say/quit (H4, H5, H7, H8,
   H19).
3. GUI local mode is `local-relay`, while dedicated's loopback is
   `local-guests` (H6).
4. The GUI passes `--navigation-buoys` and therefore depends on JRMAP.TRN for
   JRMAP, and it does not check that file (H2).
5. map_viewer `serve` runs `local-relay` without sustained delivery, objects or
   power-ups. That is intended ("viewing only"), but it is a fourth hand-built
   argv.
6. deploy: `ExecStart` passes only `--profile vpn-dogfight`. To run the LAN
   test that linux-host.md §2 suggests ("VM's private LAN address for the first
   test"), the operator must also know the address is allowed. RFC1918 is
   accepted by vpn-dogfight, so it works, but the service description says
   "VPN dogfight host".

### Q2 Duplication across launchers

| Concern | host_control.py | dedicated_host.py | start_lan_dogfight.ps1 | map_viewer.py |
|---|---|---|---|---|
| Build server argv | `server_args` 79-104 | `child_args` 75-90 | `$serverArgs` 40-47 | 79-85 |
| Validate | subprocess `--print-config` 127-133 | in-process `parse_args` 186 | subprocess `--print-config` 49 | none |
| Key check | file exists | 256 bytes | Test-Path | none (stub checks) |
| Python | `sys.executable` | `sys.executable` | `.venv/Scripts/python.exe` | `sys.executable` |
| Stop | stdin `quit`, then terminate | SIGINT, or terminate on Windows | Ctrl+C | Ctrl+C |
| Restart policy | 3 per 10 min, uptime > 5 s | none (systemd 4 per 600 s) | MaxRestarts 3 per 10 min | none |
| Status read | `updated_utc` age | mtime + pid | n/a | n/a |
| Constants copied | BACKDROPS, ALIASES, ports, "patch v11" | SESSION_COMPLETE, ports, map limits | backdrops, aliases, ports, limits text | backdrop |

`host_ops.py` holds only the status writer, console and table. It does not hold
launcher logic. Proposed shared core (`host/launcher.py` plus
`host/config.py`):
- `HostConfig` (dataclass): profile, bind, ports, map, backdrop, limits,
  objects (`buoys`/`turrets`/`warps`/`targets`/`powerups`), paths (key, log,
  status), plus `managed: RotationStep | None`. It has `to_argv()` and
  `validate()`, which calls `parse_args(self.to_argv())` in-process with
  argparse errors turned into ValueError and also runs the asset-dependent
  checks from H2/H3. It also has `status_path()`. Defaults come from one table
  and `DOGFIGHT_PROFILES`/`BACKDROPS`/ports/aliases live there.
- `HostProcess`: `start(config)`, `command(line)`,
  `stop(graceful="quit"|"sigint", timeout)`, `status()` (pid-checked,
  freshness), and `exit_code` with `SESSION_COMPLETE`.
- `RestartBudget(max, window_s, min_uptime_s)`.
- Front-ends become thin. The Tk GUI maps widgets to `HostConfig`.
  `dedicated_host` holds the rotation loop plus the watchdog. A new
  `python -I tools/host.py lan|vpn|local --address … [--map …]` replaces the
  PS1 logic (keep a two-line PS1 wrapper for docs continuity), and map_viewer
  `serve` calls `HostConfig(profile="local-relay", map=…, terrain=True)`.

### Q3 station_stub.py structure and split

| Lines | Section | Proposed module |
|---|---|---|
| 1-38 | docstring (stale usage) | CLI help |
| 39-67 | imports (`sys.path` hack) | n/a |
| 69-75, 121 | constants (`SESSION_COMPLETE`, relations, TYPE_NAMES, dead TCP_REQUEST_LEN) | `protocol/messages.py` |
| 76-119 | handshake codecs: `connect_req_fields` (dead), `ack_connect`, `ack_reliable` | `protocol/station.py` |
| 124-254 | `StationSessions` (Station identity, guests, aliases, arena lease) | `host/sessions.py` |
| 256-283 | `pilot_list`, `udp_replies` (dead in loop) | `protocol/station.py` |
| 286-369 | vessels list, `ship_config_list`, `ship_request`, `load_ship`, `flight_bootstrap`, `arena_ping`, `remove_player` | `protocol/arena.py` + `host/vessels.py` (data) |
| 371-481 | `ReliableRemovals`, `InboundReliable` | `host/delivery.py` (with `reliable_window`) |
| 483-562 | `ffa_team`, `object_to_team`, `load_player`, `player_tag`, `collision_target` | `protocol/arena.py` |
| 563-706 | `DeathLedger`, `MissileLedger` | `host/combat.py` |
| 707-769 | `PowerUps` | `host/objects/powerups.py` |
| 770-893 | `TargetShips` (uses `vessel_combat`) | `host/objects/targets.py` |
| 894-945 | `arena_message`, `Match` | `host/match.py` |
| 946-969 | `spawn_position`, `scenario_test_object` | `host/spawn.py`, `host/objects/test_object.py` |
| 970-1044 | `reported_motion`, `motion_snapshot` (emulator-only), `movement_update` | `protocol/motion.py` (merge with `relay_motion`) |
| 1045-1096 | `server_record`, `TCP_JOB_BODIES`, `tcp_reply`, `server_list_body` | `protocol/tcp_list.py` |
| 1098-1115 | `main()` | `host/cli.py` |
| 1117-1230 | `run()` setup: objects, sockets, delivery, ledgers | `ArenaServer.__init__` |
| 1231-1480 | 16 closures: restart, stats, `own_record`, `change_vessel`, `end_match`, server list, `combat_send`, `deliver`, departures, status, console | `ArenaServer` methods; `host/console.py` (status/commands) |
| 1482-1643 | loop housekeeping: managed restart, flush, console, status, expiry, retries, protection probe, match end, motion refresh, bootstrap delivery, pings, alias notices | `ArenaServer.tick()` |
| 1644-1703 | receive, decode, ingress budget, reliable unwrap, version gate | `host/transport.py` |
| 1704-1735 | Station UDP | `host/sessions.py` handler |
| 1736-1803 | arena admission, keepalive, ack, quit | `ArenaServer.on_admission()` etc. |
| 1804-1897 | relay gameplay: movement, vessel change, power-ups, missiles, collision, deaths | `host/relay.py` + `host/combat.py` |

Expected import cycles and how to avoid them:
- The `run()` closures share ~25 locals, and `depart`, `deliver`,
  `refresh_server_list` and `end_match` call each other. Splitting them into
  modules without first turning `run()` into an `ArenaServer` class would mean
  passing callbacks back and forth, which in practice is a cycle. Step 1 is
  "closures become methods" inside one file.
- `audit_warp_gates` lazily imports `station_stub.movement_update`, and
  `warp_trial` imports `audit_warp_gates`. Moving `movement_update` to
  `protocol/motion` and `routes()`/`hierarchy()` to `maps/` breaks the cycle.
- `station_runtime.parse_args` needs vessels and object-slot budgets. Put both
  in data modules (`host/vessels.py`, `host/object_slots.py`) that import
  nothing from the server.
- `online_terrain` is used by the server (MAP_NAMES/marker/spawn), the config,
  the GUI, `map_viewer` and the client patcher. Split it into `maps/registry.py`
  (pure data) and `client/patches/online_terrain.py`, or the host package keeps
  importing `patch_client`.
- 23 modules import `station_stub` (tests, emulators, reel, make_vessel_combat,
  audit_warp_gates). Keep `station_stub.py` as a re-export shim during the move.

### Q4 Docs vs code (commands)

Parsed OK (`parse_args`, with fake asset dirs where a path must exist):
local-server.md:17, 30, 41, 56, 57; lan-dogfight.md:69 and the PS1 lines at
30/59 (argv reconstructed); vpn-dogfight.md:80/81/143 (reconstructed);
client-extension-gate.md:54; findings.md:321; arena1a-rebuild.md:24, 140, 265;
arena1a.md:57; map-viewer.md:17/29/30 (`map_viewer.py --help` OK, serve argv
OK); and the flag examples in local-server.md:67-70 and lan-dogfight.md:148.
`host_control.py` (host-control.md:15) cannot be parse-tested (no argparse,
Tk). linux-host.md's test commands (`test_station_runtime`,
`test_internet_play`, `test_dedicated_host`) pass in a copy containing only
`tools/` + `deploy/`, matching the documented upload. The deploy `ExecStart`
argv with the example env/rotation passes `dedicated_host --check`.
Nothing failed. The problems are content-level (H9, H19-H23).

### Q5 Half-finished or "done but unverified"

- Turret trial: model "provisional TurretA", orientation zero, firing
  disabled. Code reports this honestly in status (`enabled: False`,
  `orientation_restored: False`). It is allowed on LAN/VPN (H11).
- Warp trial: no host-authorised transit, orientation not restored.
  Loopback-only. `warp_trial.placement`/`INDEX`/`TAG` remain only for tests.
- Navigation buoys: orientation not restored. On by default in the GUI.
  `--arena1a-buoys` is the legacy duplicate path (remove).
- Protection probe and reliable-combat: bounded 30-event experiments kept
  alive alongside sustained delivery (H14).
- `--experimental-object`: fixed test-object slot 1. The todo says to replace
  it with an entity registry; object slots are still ad hoc (H15).
- Code and docs treat these as normal play features, though the docs record
  them as unverified on separate PCs: the "experimental" relay and terrain
  power every dogfight/rotation host; sustained delivery (a 3 s reorder-margin
  assumption, with real-client wrapped-join confirmation open per the todo) is
  the VPN default and is required for any map objects; LAN/VPN separate-PC
  play is "not recorded yet" (play.md) while the PS1 prints "players can rejoin
  after a crash". The code is honest in its status flags. The launcher text is
  more confident than the evidence.
- `turret_groups.py` docstring is stale (H24). `local_station.py` CLI is
  historical (H27).

## 4. File classification

`path | role | action | proposed home`

- `tools/station_stub.py` | stand-in Station/arena server and relay | split (see §3) | `host/` + `protocol/`; leave a shim
- `tools/station_runtime.py` | argparse config, EventLog, DatagramBudget, TCP list server | split | `host/config.py`, `host/eventlog.py`, `host/transport.py`
- `tools/relay_motion.py` | movement prefix codec and stats | keep, merge with stub motion codecs | `protocol/motion.py`
- `tools/reliable_window.py` | windowed reliable delivery | keep | `host/delivery.py`
- `tools/host_ops.py` | status file, console parser, player table | keep, add shared status reader | `host/console.py`
- `tools/host_control.py` | Windows Tk host GUI | keep, thin it onto the launcher core | `launchers/host_gui.py`
- `tools/host_control.cmd` | double-click wrapper | keep | `launchers/`
- `tools/dedicated_host.py` | Linux rotation controller and watchdog | keep, thin it onto the launcher core | `host/dedicated.py`
- `tools/start_lan_dogfight.ps1` | LAN/VPN console launcher | merge-into the Python launcher CLI (keep a thin PS1 wrapper) | `launchers/`
- `tools/map_viewer.py` | JRMAP install + map-view server launcher | keep; `install` goes to maps, `serve` to the launcher core | `maps/` + `launchers/`
- `tools/local_station.py` | hostname client patch (historical CLI) | merge-into client patching | `client/patches/`
- `tools/net_impair.py` | metered socket and test impairment | keep | `host/net_impair.py`
- `tools/aoanet.py` | UDP datagram codec | keep | `protocol/codec.py`
- `tools/aoacrypt.py` | cipher | keep | `protocol/crypt.py`
- `tools/vessel_combat.py` | generated vessel HP/damage table | keep (generated data) | `host/data/vessel_combat.py`
- `tools/make_vessel_combat.py` | generator for the above | keep; stop importing the server; add `--check` | `analysis/` or `host/data/`
- `tools/powerup_pickup.py` | client patch for power-up pickup | keep (client side, not host) | `client/patches/`
- `tools/turret_trial.py` | turret placement trial | keep (trial) | `host/objects/trials/`
- `tools/warp_trial.py` | warp gate trial | keep (trial); drop the single-gate compatibility helpers | `host/objects/trials/`
- `tools/navigation_buoys.py` | buoy placements from assets/TRN | keep; drop the `placements()` legacy Arena1a path | `host/objects/` (asset reading goes to `maps/`)
- `tools/online_terrain.py` | client terrain patch + server map registry | split | `maps/registry.py` + `client/patches/online_terrain.py`
- `tools/turret_groups.py` | turret status codec | keep | `protocol/objects.py`
- `deploy/linux/aoa-host.service` | systemd unit | keep | `deploy/linux/`
- `deploy/linux/host.env.example` | bind/max-players env | keep; add a test | `deploy/linux/`
- `deploy/linux/rotation.json.example` | rotation config | keep; add a test | `deploy/linux/`
- `tools/test_station_runtime.py`, `test_station_sessions.py`, `test_station_stub.py`, `test_relay_motion.py`, `test_relay_recovery.py`, `test_lan_dogfight.py`, `test_internet_play.py`, `test_guest_admission.py`, `test_combat_delivery.py`, `test_network_bounds.py`, `test_powerups.py`, `test_target_ships.py`, `test_host_control.py`, `test_dedicated_host.py` | host tests (in CI) | keep | `tests/host/`
- `tools/test_powerup_pickup.py` | client patch test (verify_local only) | keep | `tests/client/`
- `tools/test_station_detail.py` | client LOD emulation test (named "station" but not the server) | keep; rename | `tests/client/`
- `tools/test_turret_groups.py`, `test_turret_trial.py`, `test_warp_trial.py`, `test_warp_headless.py`, `test_navigation_buoys.py` | asset-dependent trial tests in no gate | keep; add to `verify_local` | `tests/host/`
- `docs/local-server.md` | flag reference | keep; regenerate the flag table from argparse | `docs/host/`
- `docs/lan-dogfight.md`, `vpn-dogfight.md`, `host-control.md`, `linux-host.md`, `play.md` | runbooks | keep; fix H19-H23 | `docs/host/`, `docs/play.md`
- `docs/internet-server-todo.md`, `first-playable-release.md` | roadmap/spec | keep; refresh status notes | `docs/roadmap/`

## 5. Recommendations for the redesign

1. Do this before moving any files. Turn `run()` into an `ArenaServer` class
   in place (closures become methods, locals become attributes). Every later
   split depends on it, and it can be checked against the existing 14 host
   suites unchanged.
2. Make data modules import nothing from the server: vessels, object-slot
   registry, ports/aliases/backdrops/profiles, and the map registry split out of
   `online_terrain`. `parse_args`, the GUI, the PS1 replacement and
   `dedicated_host` read them. This removes H3, H7, H15, H16 and the
   `patch_client` dependency.
3. One `HostConfig` + `HostProcess` + `RestartBudget` core (§3 Q2). Every
   launcher becomes a front-end. `validate()` covers everything `run()` can
   reject (assets, vessels), so "validated" means "will start".
4. Rename by role, not history. Use `--relay`/`--terrain` (keep the old names
   as hidden aliases for a release). Put real experiments under one
   `--diag-*` group or a separate `diagnostic` entry point (flight-only,
   object, teams, reliable-combat, protection probe, impairment). Remove
   `--advertised-address` and `--arena1a-buoys`.
5. Separate packages: `protocol/` (codec, crypt, message builders,
   motion), `host/` (sessions, delivery, match, combat, objects, transport,
   console, config), `launchers/`, `maps/` (registry and asset readers used by
   the trials), and `client/patches/`. The server must not import `audit_*`.
6. Gates: add the 5 orphan suites and `test_dedicated_host` to
   `verify_local.py`. Add one game-free "launcher argv" test that covers
   host_control (all combos), dedicated (deploy examples), map_viewer serve and
   every doc command line.
7. Docs: generate the server flag table from argparse, decide one client
   capability naming (patch version vs `online-terrain-vN`), and annotate
   roadmap items that `dedicated_host`, ship change and sustained delivery now
   partially implement.
