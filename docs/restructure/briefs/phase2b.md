# Phase 2b: the host as a server class, one configuration, one supervisor

Rebuild the inside of `aoa/host/` (PLAN.md section 2, rules 3 and 5). What
the server sends on the wire must not change: the existing host suites are
the contract, and `tests/snapshots/host_configs.json` may change only where
this brief says so, each change listed in your report.

Files: everything under `aoa/host/` and `aoa/protocol/`,
`aoa/launchers/host_control.py` (only where it builds the server command
line, starts or supervises the process, or reads status),
`aoa/maps/map_viewer.py` and `aoa/maps/make_map.py` (their `serve` commands
only), `deploy/`, `tools/start_lan_dogfight.ps1`, the host suites in
`tests/`, and `docs/local-server.md`, `docs/linux-host.md`,
`docs/host-control.md`, `docs/lan-dogfight.md`, `docs/vpn-dogfight.md`.
Not `aoa/client/`, `aoa/research/`, `aoa/analysis/`, `aoa/emulation/`.

Order matters (audit `host.md` section 5):

1. **`ArenaServer` in place.** `run()` in `aoa/host/server.py` is one
   780-line function with 16 nested functions sharing about 25 locals. Turn
   it into a class in the same file first: locals become attributes,
   nested functions become methods, the loop body becomes `tick()` and
   named handlers. No behaviour change; run the host suites after each
   step. Only then split.
2. **Split by role** (audit `host.md` Q3 gives line ranges): message
   builders to `aoa/protocol/` (`station`, `arena`, `tcp_list`, `messages`);
   `aoa/host/sessions.py`, `combat.py` (death and missile ledgers),
   `match.py`, `objects/` (`powerups`, `targets`, trials), `spawn.py`,
   `transport.py`, `console.py`; `aoa/host/cli.py` holds `main`. Keep
   `aoa/host/server.py` importable with the names tests and the reel use,
   as thin re-exports, and list them in your report for later removal.
3. **Data modules that import nothing from the server:**
   `aoa/host/defaults.py` (profiles, ports, aliases, backdrops, limits: the
   one table, in seconds), `aoa/host/vessels.py`, and
   `aoa/host/object_slots.py` (one allocator for object indices and tags,
   replacing the literals spread over five files, audit H15). Config
   validation, placement and the launchers read these.
4. **`aoa/host/config.py`: `HostConfig`** (dataclass): profile, bind
   address, ports, maps (one or a rotation), backdrop, limits, objects,
   paths, managed-session settings. `to_argv()` is the only builder of the
   server command line; `validate()` covers everything the server can reject
   at start, in process, raising `ConfigError` with one line. `from_json` /
   `to_json` with a `schema` number; unknown keys are named in the error.
5. **`aoa/host/supervisor.py`:** `HostProcess` (start, command, graceful
   stop, pid-checked status), `RestartBudget`, and `Supervisor` (restart
   policy, rotation, recycling, watchdog, planned exit). One policy:
   3 restarts per 10 minutes, 5 s delay, restart with the settings the
   crashed run had. Unit-tested with a fake child process, no game files.
6. **Every front-end uses 4 and 5.** The host window's `server_args`,
   `HostProcess` and restart logic; `aoa/host/dedicated.py`; `map_viewer
   serve`; `make_map serve`; `start_lan_dogfight.ps1` becomes a wrapper
   around a new `tools/aoa_host.py` (`run|check|status [CONFIG.json]`, with
   `--profile`, `--bind-address`, `--map` overrides) that the systemd unit
   also calls. Keep `tools/dedicated_host.py` working with its current
   arguments for deployed hosts, and document the move to the new command.
   The Linux examples (`host.env.example`, `rotation.json.example`) get a
   single `host.json.example` in the same schema the host window saves, and
   the old two-file form is still read.
7. **Flags by role.** `--relay` and `--terrain` are the names; the
   `--experimental-*` spellings stay as hidden aliases for one release.
   True diagnostics (flight-only, test object, teams, reliable-combat,
   protection probe, impairment, spawn axis) sit in one argparse group
   titled diagnostics. Remove `--arena1a-buoys` (superseded) and
   `--advertised-address`; update the two commands in
   `docs/arena1a-rebuild.md` and the snapshot keys that carry them.
   Flags that are ignored outside their mode are rejected with one line
   (audit H10). One rule for trials on LAN and VPN (audit H11): decide from
   what the code can honestly support, put it in `defaults.py`, and state it.
8. **One delivery engine for play** (audit H14): a small `Delivery`
   interface; the windowed engine is the play path; the 30-event engine and
   its two flags move under diagnostics.
9. **Client requirement wording:** the host names a requirement as a
   feature with its patch level ("terrain needs client patch level 11"),
   from one table. Replace "patch v11" and "online-terrain-v2" strings.
10. **Docs:** regenerate the server flag table in `docs/local-server.md`
    from argparse (commit the generator as `tools/run.py aoa.host.flagdoc`
    or similar, with a test that the table is current).

Gate: `tools/test.py --tier ci` passes; every existing host suite passes
unmodified except for import paths and the flag renames above; a new
game-free test drives a real `ArenaServer` on loopback through join, fight,
death, match end and rotation using the existing synthetic clients (reuse
what `tests/support.py` has); snapshot changes are exactly those listed;
`aoa.host.*` imports with the standard library only; layering test passes
with `KNOWN` empty; pyflakes clean. Not verifiable here: real clients, the
host window, PowerShell, systemd on a real machine. Say so.
