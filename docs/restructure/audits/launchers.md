# Audit: launcher user experience (client launcher, host control, headless host)

Auditor area: `tools/client_launcher.*`, `tools/host_control.*`, `tools/dedicated_host.py` + `deploy/linux/`,
the PowerShell helpers, `install_wrapper.py`, `fetch_known_builds.py`, `make_install.py`, the CLIs of
`prepare_client.py` / `map_viewer.py`, `build_texture_pack.py`, and the player/host docs.
Branch `architecture-cleanup`. Read-only audit; scratch files only under the scratchpad.

## 1. Summary

- **A first-time player goes through about 13 manual steps, 7 different programs or windows, and types 6 command lines plus a hand-made folder path** before they can fly offline (Appendix A). The GUI launcher only appears at step 11. Everything before it (venv, pip, download, wrapper placement, `setup_game.ps1`) is command line.
- **Joining a friend needs admin rights on every player's PC** (editing the `hosts` file in Notepad as administrator), and the documented way to repoint the client is the `prepare_client.py` CLI. **That CLI silently turns back on 5 options the player switched off in the client launcher** (frame clock, visibility math, chase camera, widescreen framing, power-up pickups), because its flags default to `True` while the launcher has written explicit choices (F-01). The client launcher's own "Station host" box does the same job without this problem, but neither the docs nor the host window mention it.
- **The two launchers share no code, no settings and no vocabulary.** The client is "Station host" (free text). The host is "Mode" + "Host address" plus a hint telling players to run a CLI flag (`--station aoalan`). The game folder is a read-only path with Browse… in one and a free-text relative path in the other. One requirement is called "patch v11" in the GUI, "patch version 11" in the docs and "online-terrain-v2" in the Linux docs, and **no tool shows a player their patch version**.
- **Headless and GUI hosting are two different products.** `dedicated_host.py` builds the `station_stub` command line itself, with other defaults (10 kills/15 min vs 20/10), and has no backdrop, target ships, map objects or power-up zones. `host_control.py` has no rotation and no recycling, so a Windows GUI host hits the 49-join lifetime limit. A third builder (`start_lan_dogfight.ps1`) allows only 2 of the 20 maps and prints a wrong terrain label. Two more builders sit in `map_viewer.py serve` and `make_map.py serve` (F-05, F-06).
- **Failures are mostly quiet.** Both `.cmd` files start `pythonw`. Any exception outside the caught set produces no window and no log at all. For example, a hand-edited or out-of-date `host_control.json` with an unknown `mode` raises `KeyError` before the window appears (F-03). A port already in use or a wrong address shows only in the in-memory log pane, with no dialog. Neither launcher writes a log file.
- **The host window can kick everyone for nothing.** "Load map (restart)" stops the server before it checks the new settings (F-04). Stop, validate and the startup address detection all block the Tk thread, for up to 15 s each.
- **Some prerequisites are invisible.** JRMAP terrain needs `jrmap292.trn` on *every client*, but only the host's folder is checked. "Navigation buoys" (on by default) needs an asset export (`work/2.9.2/export/AOAOBJECTS`) that no player guide explains how to make. `requirements.txt` makes players install capstone/unicorn/pefile, which no player or host path imports (verified, F-10).
- **The logic layer is in good shape and worth keeping.** `client_launcher.read_settings/apply_settings/validate_options` and `host_control.server_args/HostProcess/node_availability` are free of tkinter and tested. The Tk-only parts are restart policy, status formatting, hints and the map-switch sequence, and those have no tests.
- **Redesign (section 4):** one `aoa` core package (settings model, game folder, client profile, host profile → `station_stub` args, supervisor), with two thin Tk views ("Play" and "Host") and one headless runner that reads the *same* host profile JSON. `dedicated_host.py`, `start_lan_dogfight.ps1` and `host_control.py` collapse onto one supervisor. A first-run wizard replaces `setup_game.ps1` plus the manual dgVoodoo placement.

## 2. Findings

Severity: H = breaks or misleads users, M = significant friction or drift, L = minor.

| ID | Sev | Where | What is wrong | How verified | Suggested fix |
|---|---|---|---|---|---|
| F-01 | H | `tools/prepare_client.py:329-340, 348-354`; `docs/play.md:108`, `docs/lan-dogfight.md:87`, `docs/vpn-dogfight.md:121`, `docs/client-setup.md:70,221`; also `world_detail.py:68` and siblings | The CLI defaults `--frame-clock/--visibility-math/--third-person/--powerup-pickup/--menu-framing` to `True`. The experimental ones (`None`) are preserved instead. So every documented `prepare --station aoalan` resets 5 launcher choices to on, without telling the user. The standalone patch tools (`world_detail.py`, `station_detail.py`, …) call `prepare()` with the same defaults. | Read `main()` and the `prepare()` signature. The launcher passes explicit values (`client_launcher.py:153`). | Default every flag to `None` (preserve the installed state), as `--distant-objects` already does. Point the docs at the launcher's Station box. In the future core, a client profile is applied whole, never "defaults + delta". |
| F-02 | H | `docs/lan-dogfight.md:81-85`, `vpn-dogfight.md:113-117`, `host_control.py:360-362` | Joining needs an admin Notepad edit of `C:\Windows\System32\drivers\etc\hosts` on every client, plus a CLI re-prepare. Nothing checks that the alias resolves before Play. `docs/play.md` troubleshooting ("Play Online greyed out") is the only feedback. | Read the docs and the launcher. `client_launcher.validate_options` only checks the syntax (`host_field`). | Short term: the client launcher runs `socket.gethostbyname(station)` on Apply/Play and warns. When the address fits in 11 characters (e.g. `10.0.0.5`, `192.168.1.5`), let players type the IP directly and skip the hosts file. Investigate (unverified) whether `localhost` + typing the host IP in the login dialog's editable Station IP box (findings.md §4) avoids the hosts file entirely. |
| F-03 | H | `host_control.py:182-187, 205, 344, 508`; `host_control.cmd:9` | `load_settings` copies saved values without validating them. `mode` stores the *display label* ("This PC only"). An unknown label (hand edit, or a later label rename) makes `MODES[...]` raise `KeyError` in `refresh_controls()` at line 508, inside `gui()` and before `mainloop`. Under `pythonw` the window never opens and nothing is printed. | Read the code. `pythonw` has no stderr. | Store profile ids (`local-relay`) rather than labels. Validate the loaded settings against a schema and fall back to defaults with a notice. Wrap `main` in a handler that writes `work/logs/launcher.log` and shows `messagebox.showerror`. |
| F-04 | M | `host_control.py:394-402` | "Load map (restart)" sends `say`, then `host.stop()`, and only then `do_start()` → `validate()`. Invalid new settings (e.g. JRMAP without `jrmap292.trn`, a bad address) mean players are disconnected and the host stays down. | Read the code. `start()` validates at line 131, after the stop. | Call `host.validate(new)` (and the file checks) before `stop()`. |
| F-05 | M | `host_control.py:57-83`; `dedicated_host.py:76-91`; `start_lan_dogfight.ps1:42-47`; `map_viewer.py:79-85`; `make_map.py serve` | Five independent builders of the `station_stub.py` argument list. They have drifted: only host_control passes `--backdrop`, `--target-ships`, node options and `--powerup-zones`. Only dedicated passes ports, `--managed-session` and recycling. The ps1 restricts `-Map` to `CTF_arena`/`Arena1a` (`:19`). | Read all five. | One `host_profile → argv` function in the core. Every entry point calls it. |
| F-06 | M | `host_control.py:35-37`; `dedicated_host.py:23-34`; `station_runtime.py:77,81-82`; `start_lan_dogfight.ps1:18,77`; `deploy/linux/rotation.json.example`, `host.env.example` | Defaults disagree. Kills/time: 20/10 min (GUI, server, ps1 text) vs 10/900 s (dedicated, rotation example). Max players: 4 (GUI), 2 (ps1, host.env), 2 (dedicated), 8 (server). Units differ too: `time_limit_min` vs `time_limit_seconds`. The ps1 prints a hard-coded "20 kills / 10 minutes" (`:77`). | grep, listed in Appendix D. | One defaults table in the core settings model, in seconds. Generate the doc tables from it. |
| F-07 | M | `dedicated_host.py:170-180, 193-194` | The default `--profile vpn-dogfight` plus the default `--bind-address 127.0.0.1` are always invalid. The resulting error comes from `station_runtime.parse_args` → `parser.error` → `SystemExit(2)`. That is not caught by `except (OSError, ValueError, RuntimeError)`, so the user sees the **server's** 40-line usage text titled `dedicated_host.py`. | Ran `dedicated_host.py key log --config {} … --check` (scratchpad probe): it printed the station usage and `error: vpn-dogfight requires a specific IPv4 address…`. | Make `--bind-address` required (or detect it). Catch `SystemExit` from `server_config` and re-raise as `ValueError` with the message only. |
| F-08 | M | `dedicated_host.py:39-43` | The strict-keys error does not name the offending key ("rotation config must be an object containing only documented settings"). `"backdrop"` is rejected even though every other host accepts it. Maps that "load nothing alone" (`Hittest`, `hy_winga`, …) and JRMAP (which needs `jrmap292.trn` on clients and has power-up zones) are accepted without comment. | Probe with `{"maps":["JRMAP","Arena1a"],"backdrop":…}` → generic error. `{"maps":["JRMAP","Hittest"]}` → accepted. | Name the unknown keys. Share the map metadata (playable / component / needs-client-file) in `online_terrain.MAPS` and warn about or refuse component maps. |
| F-09 | M | `host_control.py:129-130, 237`; `map_viewer.py:43-55` | JRMAP terrain needs `jrmap292.trn` **beside each client**, made by `map_viewer.py install`. The host GUI checks only the host's folder, and its error tells the host to run a CLI. The map dropdown lists all 20 names, including components that show empty space. The notes that explain them live only in `map_viewer.NOTES`. | Read the code. `online_terrain.MAPS[...][2] == "jrmap292.trn"`. | Move the map notes and "playable" flags into `online_terrain`. The host dropdown shows only playable maps, with their notes. The client launcher gets a "JRMAP terrain: install" action. |
| F-10 | M | `requirements.txt`; `docs/play.md:23`, README Quick start | Players are told to `pip install -r requirements.txt` (capstone, unicorn, pefile, Pillow). No launcher or host chain imports any of them. Only `build_texture_pack.py` imports Pillow, lazily. That is extra download, an extra failure point, and a reason to need a venv at all. | Imported each launcher/host module and listed the third-party modules loaded: none. | Split into `requirements-research.txt` and `requirements-texture.txt`. The player path then needs only stdlib Python. |
| F-11 | M | `host_control.py:239`; `docs/host-control.md:28`; `docs/linux-host.md:169`; `prepare_client.py:38` | The terrain requirement is named three ways ("patch v11", "patch version 11", "online-terrain-v2"). `PATCH_VERSION` is 22. The client launcher never displays the patch version or the installed patch names, so the player cannot act on the hint. | Read the code and docs. | The client launcher shows "Client version: 2.9.2, patch level 22 (up to date)". The host shows a requirement as a *feature name*, and the core maps feature → minimum patch. |
| F-12 | M | `host_control.py:48-54, 73`; `docs/host-control.md:44-47` | "Navigation buoys" defaults to on but needs `work/2.9.2/export/AOAOBJECTS` + `_export.json`, produced by the research asset exporter. No player or host guide says how to make it. The path is hard-coded to `work/2.9.2` and does not follow the Game folder setting. The disabled checkbox just says "Original exported map assets are missing." | Read the code and grepped the docs. | Either give the host a one-click "Export map objects from my game folder" (if the exporter is stdlib-only), or hide the option behind an "Experimental" section with a link. Derive the path from the game folder. |
| F-13 | M | `host_control.py:204, 389, 401, 116-117`; `client_launcher.py:304-316` | Blocking calls on the Tk thread: `detect_addresses()` (PowerShell, 15 s timeout) before the window exists, `host.stop()` (up to 10 + 5 s), `validate()` (a Python subprocess), and `apply_settings` (hashes ~28 MB of assets 3 times plus the EXE). The window shows "Not responding". | Read the code. `config/client-2.9.2.json`: 10 required files, 27.6 MB. | Run long work in a worker thread and post the results back with `root.after`. Detect addresses with `socket.getaddrinfo` / `ipconfig`-free stdlib, or asynchronously. |
| F-14 | M | `host_control.py:438-456`; `start_lan_dogfight.ps1:83-92`; `deploy/linux/aoa-host.service:5-6,21-22` | Three restart policies: GUI (3 per 10 min, 5 s, only if it ran >5 s, restarts with the *current* GUI values rather than the crashed run's `host.settings`), ps1 (3 per 10 min, any non-zero), systemd (4 per 10 min, 30 s). The GUI policy lives inside a Tk callback and is untested. | Read the code. `test_host_control.py` has no restart test. | A single `Supervisor` class in the core (policy + rotation + watchdog), unit-tested. The GUI and headless runners both use it. Restart with `host.settings`. |
| F-15 | M | `host_control.py:63,87`; `start_lan_dogfight.ps1:33-34`; `docs/lan-dogfight.md:58`, `host-control.md:68` | Status and log paths differ by launcher: `work/host/<profile>-status.json` (GUI) vs `work/<profile>-status.json` (ps1), and logs `work/host/…jsonl` vs `work/…jsonl`. Instructions that tell users to "look at the status file" depend on which tool they used. | Read the code and docs. | One `work/host/` layout owned by the core. |
| F-16 | L | `start_lan_dogfight.ps1:67` | With `-Terrain` it prints "with Arena1a terrain" for any map, including the default `CTF_arena`. | Read the line. | Print `$Map` terrain, or retire the script (section 4). |
| F-17 | L | `tools/setup_game.ps1:7` | The synopsis says step 2 is `tools\patch_client.py`. The script runs `prepare_client.py prepare` (twice: `:46` and `:58`). When the wrapper zip is missing it tells the user to "delete $Dest and run this again" (`:53`), although `install_wrapper.py` can be run on its own later. | Read the script. `prepare_client.check` does not compare the recorded `wrapper` field. | Fix the synopsis. Offer `install_wrapper.py` (or the launcher) as the later fix instead of rebuilding. |
| F-18 | L | `install_wrapper.py:61`; `make_install.py:31` | Run without arguments they crash with `IndexError` / `ValueError: not enough values to unpack` tracebacks. `install_wrapper` writes non-atomically and overwrites `dgVoodoo.conf` completely, which discards the launcher's quality choices. | Ran both with no arguments. | Use argparse. Write the conf with `prepare_client.atomic_write` and keep the existing `[DirectX]` keys. |
| F-19 | L | `host_control.cmd:9` vs `client_launcher.cmd:9`; `host_control.py:3` | The client is started with `pythonw -I` and the host with `pythonw` without `-I`, which goes against the project's `-I` convention and loads user site-packages and `PYTHON*` env vars. | Read both. | Use `-I` in both, through one shared launcher stub. |
| F-20 | L | `host_control.py:262-264` vs `client_launcher.py:217-251` | The game folder is a free-text relative Entry with no Browse… in the host. In the client it is a read-only absolute path with Browse…. The client does not remember the last folder chosen. | Read the code. | One shared "game folder" widget backed by the shared settings file. |
| F-21 | L | `client_launcher.py:27-38, 278-281` | "Original visuals (all off)" also turns off `smooth_frame_clock` and `bounded_visibility`, which the CLI treats as default-on fixes rather than visuals. Labels such as "Corrected object visibility math", "Preserve point-sampled textures" and "Station host" are jargon for a newcomer. | Read the code. | Group the options as "Fixes (recommended)", "Visual extras" and "Experimental". Rename Station host to "Server address". Put the longer explanation in a hover or "?" text. |
| F-22 | L | `client_launcher.py:117-121`; `prepare_client.py:172-175` | If the experimental protection probe is installed, an Apply with a non-loopback Station fails with "experimental protection requires a loopback Station". The launcher has no control for that patch, so the user must use the CLI flag `--no-experimental-protection`. | Read the code. `apply_settings` never passes `experimental_protection`. | The launcher passes `experimental_protection=False` whenever the station is not loopback, or exposes it under Experimental. |
| F-23 | L | `fetch_known_builds.py:15-23` | The player guide uses it to fetch 2.9.2, but it also downloads 2.8.2 (unneeded for play) and checks MD5 only. | Read the code. | Add a `--only v2.9.2` option, used by the wizard. Keep both for research. |
| F-24 | L | `docs/texture-pack.md:52-56` vs the launcher's "32-bit textures" checkbox | The same patch (`texture32`) has two control paths. The standalone tool leaves `.EXE.before-texture32` backups that go stale once the launcher toggles the patch. Its `--undo` then refuses ("backup does not match this client"). The same applies to `world_detail.py`, `station_detail.py` etc. (`world_detail.py:55-64`). | Read `world_detail.install`. The same pattern is in the siblings. | Point player docs at the launcher only. Keep the standalone patch CLIs as developer tools. |

## 3. File classification

`path | role | verdict | proposed new home`

- `tools/client_launcher.py | client options GUI + apply/rollback logic | keep (split into core + view) | launchers/play_app.py (view) + aoa/client_profile.py (read_settings/apply_settings/validate/texture cache)`
- `tools/client_launcher.cmd | double-click stub | merge-into one `Ace of Angels.cmd` (runs launchers with -I) | launchers/`
- `tools/test_client_launcher.py | tests for the client logic and GUI wiring | keep | tests/launchers/`
- `tools/host_control.py | host GUI + HostProcess + args builder | keep (split) | launchers/host_app.py (view) + aoa/host_profile.py (args) + aoa/supervisor.py (process, restart, rotation)`
- `tools/host_control.cmd | double-click stub | merge-into the shared stub | launchers/`
- `tools/test_host_control.py | host logic tests (5 of 8 need game files) | keep, extend with supervisor tests | tests/launchers/`
- `tools/dedicated_host.py | headless supervisor with rotation and watchdog | merge-into aoa/supervisor.py; keep a thin `aoa-host` CLI | host/server`
- `deploy/linux/aoa-host.service | systemd unit | keep (ExecStart → `aoa-host run /etc/ace-of-angels/host.json`) | deploy/linux/`
- `deploy/linux/host.env.example | bind address + max players | merge-into host.json | deploy/linux/`
- `deploy/linux/rotation.json.example | rotation settings | merge-into host.json (same schema as the GUI) | deploy/linux/`
- `tools/setup_game.ps1 | first-time build of game folder | archive once the wizard ships (keep as fallback for one release) | launchers/legacy/`
- `tools/start_lan_dogfight.ps1 | console LAN/VPN host | delete after `aoa-host run --profile lan` exists (it duplicates host_control + supervisor) | (none)`
- `tools/client_login.ps1 | test driver that fills the login dialog | keep (dev/test only, not player-facing) | tests/windows/ or analysis/RE`
- `tools/register_activeskin.ps1 | per-user OCX registration | keep; call it from the wizard (or port it to ctypes) | client patching/windows`
- `tools/install_wrapper.py | dgVoodoo install + manifest | keep (fix argv/atomicity); call it from the wizard | client patching`
- `tools/fetch_known_builds.py | archive.org fetch of installers | keep; add `--only` for the wizard | archive research (player use through the wizard)`
- `tools/make_install.py | extract the installer payload | keep (argparse); call it from the wizard | client patching/install`
- `tools/prepare_client.py | patch engine + CLI | keep as engine; CLI defaults → preserve | client patching`
- `tools/map_viewer.py | list/install JRMAP/serve one map | keep `install`/`list` (map metadata → online_terrain); `serve` → host profile "This PC only" | assets/maps`
- `tools/build_texture_pack.py | Real-ESRGAN pack builder | keep (optional, GPU) | assets/texture pack`
- `docs/play.md | player guide | keep, rewrite around the wizard | docs/`
- `docs/host-control.md | host GUI guide | keep, merge the LAN/VPN host parts | docs/`
- `docs/client-setup.md | patch reference + launcher | keep as the reference; move the player parts to play.md | docs/`
- `docs/linux-host.md | headless deployment | keep; point it at the shared host.json | docs/`
- `docs/lan-dogfight.md, docs/vpn-dogfight.md | network runbooks | merge into one "play with friends" guide plus acceptance notes | docs/`
- `docs/texture-pack.md | optional pack build | keep; replace step 3 with the launcher checkbox | docs/`
- `docs/custom-maps.md | map authoring | keep (developer) | docs/`
- `README.md Quick start | entry point | keep; reduce to "download, double-click setup" once the wizard exists | /`

## 4. Recommendations: one player launcher and one host launcher

### 4.1 Design goals

1. One click to install a missing piece, with no hand-typed paths. Every manual step that remains (firewall, hosts file, VPN) is shown as a checklist item with a **Do it** button where the system allows it (UAC prompt), or **Copy command** where it does not.
2. **One settings model** and one core library. The GUI and headless hosts read the *same* JSON.
3. The current engines stay: `prepare_client`, `install_wrapper`, `make_install`, `register_activeskin.ps1`, `texture_pack`, `station_stub`/`station_runtime`. The launchers only call them.
4. Standard-library tkinter/ttk only, Windows 10/11 first. The core must run on Linux (headless host, CI tests).

### 4.2 Module split

```
aoa/                        # pure logic, no tkinter, all unit-tested on Linux
  paths.py                  # repo root, work/, logs/, game folder resolution (one place)
  settings.py               # load/validate/save settings.json (schema below), migrations
  catalog.py                # maps (from online_terrain + notes + playable flag + client file needed),
                            # backdrops, ports, aliases, defaults, feature→min patch level
  game_folder.py            # find/verify: exe state, assets, wrapper, ActiveSkin registered?, jrmap292.trn
  install.py                # wizard steps as functions returning Step results (fetch, extract, prepare,
                            # register, wrapper); each idempotent, each with check() and run()
  client_profile.py         # today's client_launcher logic (read_settings/apply_settings/validate,
                            # texture cache), plus station resolution check
  host_profile.py           # settings → station_stub argv (the only builder), validation, share text
  supervisor.py             # HostProcess + restart policy + rotation/recycling + watchdog + status reader
  netinfo.py                # local IPv4 addresses (stdlib, non-blocking), VPN range classification
launchers/
  tkcommon.py               # worker-thread runner, error dialog + log file, game-folder picker widget
  play_app.py               # player window (wizard + Play + Join)
  host_app.py               # host window
  aoa_host.py               # headless: `aoa-host run|check|status [host.json]` (systemd ExecStart)
  Ace of Angels.cmd         # pythonw -I launchers\play_app.py ; Host.cmd likewise
```

What carries over from today's code:

- `client_launcher.py:52-196` → `client_profile.py`, nearly as is. Keep the rollback in `apply_settings`, `require_closed` and the `PATCHES`/`QUALITY` tables as the option registry.
- `host_control.py:46-180` → `host_profile.py` + `supervisor.py`. Keep `node_availability` with its reason strings.
- `dedicated_host.py:36-152` → `supervisor.py`. Its `load_config` validation becomes `settings.validate_host()`. Rotation, watchdog and planned exit 75 become supervisor modes. The GUI gains rotation for free.
- The Tk widget code in both launchers is mostly re-laid-out, not rewritten. The status table, kick/ban/say and log pane are fine as they are.

### 4.3 Settings file (single source of truth)

`work/settings.json` (Windows, per checkout) or `/etc/ace-of-angels/host.json` (Linux; same `host` object):

```json
{
  "schema": 1,
  "game_folder": "game/2.9.2",
  "client": {
    "server": "localhost",
    "options": {"distant_objects": true, "chase_camera": true, "...": "keys = client_profile.PATCHES/QUALITY"},
    "friends": [{"name": "Sam's LAN", "address": "192.168.0.61", "alias": "aoalan"}]
  },
  "host": {
    "profile": "local-relay",            // ids, never UI labels: local-relay | lan-dogfight | vpn-dogfight
    "bind_address": "auto",              // or literal IPv4
    "max_players": 4,
    "maps": ["CTF_arena"],               // 1 map = fixed, >1 = rotation (managed sessions)
    "backdrop": "spacebkgd3",
    "terrain": true,
    "kill_limit": 20,
    "time_limit_seconds": 600,
    "target_ships": 0,
    "map_objects": {"navigation_buoys": false, "turret_trial": false, "warp_trial": false},
    "restart": {"max_per_10_min": 3, "delay_seconds": 5},
    "recycle": {"arena_joins": 40, "station_admissions": 56, "idle_seconds": 300,
                "restart_warning_seconds": 30, "intermission_seconds": 5, "health_timeout_seconds": 30},
    "ports": {"station_udp": 5033, "arena_udp": 5031, "list_tcp": 5034}
  }
}
```

- Every default lives once, in `catalog.DEFAULTS`. The file stores only the values that differ from the defaults, so changing a default reaches everyone.
- `client.options` is a *desired* state. The installed state is still read from the EXE (today's design is right: the EXE is the truth). The launcher shows a "differs from installed" badge when the two disagree, for example after a CLI prepare.
- Unknown keys fail with the key's name. A legacy `host_control.json` and `rotation.json` get a one-time migration.

### 4.4 Player launcher ("Ace of Angels")

**First run (wizard)**, shown whenever `game_folder.verify()` is not all green. Each row shows a status icon and one button:

1. **Game files**: "Find my game" (browse to an existing folder or installer) or "Download the 2.9.2 installer (63 MB from archive.org)". The button runs `fetch_known_builds --only v2.9.2`, then `make_install`, in a worker thread with a progress line.
2. **Verify**: hashes against `config/client-2.9.2.json`. A failure names the file and offers "rebuild folder".
3. **Compatibility fixes**: `prepare` with the recommended profile. Shows "patch level 22".
4. **Login dialog skin**: runs `register_activeskin.ps1` (no admin). Re-checks the HKCU CLSID key, which also catches the folder-moved case.
5. **Graphics wrapper (recommended)**: "Open download page" + "I've downloaded it". It looks in `%USERPROFILE%\Downloads` for `dgVoodoo2_87_5.zip`, checks the hash and installs it. No hand-made `originals\wrappers\…` folder.
6. Warns if a Windows compatibility layer is set on the EXE (today's `setup_game.ps1:54-56` check).

**Main window**, three tabs:

- **Play**: a large Play button and a "Server: This PC / <friend name>" dropdown. A status strip shows "Game ready · patch 22 · wrapper on · 32-bit textures on".
- **Join a friend**: paste the address the host shared (a `aoa://192.168.0.61?alias=aoalan` string or a plain IP). The launcher:
  1. If the IP fits in 11 characters, sets the server to the IP directly, with no hosts file.
  2. Otherwise it checks whether the alias already resolves to that IP. If not, **Add to hosts file** runs an elevated helper (UAC) that edits only the `aoalan`/`aoavpn` line, and **Remove** undoes it.
  3. It applies the station through `client_profile.apply_settings`, so options are preserved (F-01), and resolves the name before launching.
  4. It pings the host's TCP 5034 list port and shows "Host reachable" or the firewall hint.
- **Options**: today's checkboxes, grouped as Fixes (recommended), Visual extras, Graphics quality (wrapper) and Experimental, with plain-language labels. Also: "Restore original game" (`prepare undo`), "Install JRMAP terrain" (`map_viewer install`), and the texture pack status with a link to the guide.

Every failure shows a dialog with a one-line cause and a **Details** expander, and is appended to `work/logs/launcher.log`.

### 4.5 Host launcher ("Ace of Angels Host") and the same thing headless

**Setup panel** (collapsed once the host is running):

- "Who can join?": This PC only / My home network / Friends over a VPN. This maps to the profile id.
- Address: auto-detected for the chosen kind (private LAN vs `100.64/10`), with an explanation when none is found ("VPN not connected").
- Maps: a single map or "Rotate through…" (multi-select), playable maps only, each with its note. Then rules (kills, minutes, players) and an Advanced expander (backdrop, target ships, map objects, ports).
- A firewall checklist row: "Rules for UDP 5031/5033 + TCP 5034 on <address>". **Create rules** runs the elevated `New-NetFirewallRule` with the exact address and range. The rules are named so that **Remove** works too.

**Start** runs `host_profile.validate()` in a worker thread, then starts `supervisor`. The panel then shows a share box: *"Tell players: address `192.168.0.61` (or paste `aoa://192.168.0.61?alias=aoalan`) and use 'Join a friend'."* with a Copy button.

**Running view**: today's status line, player table, kick/ban/end/say and log pane, unchanged. "Change map" validates first, then announces and restarts (F-04). When the joins counter nears its limit, the supervisor's recycle logic restarts on its own (from dedicated).

**Headless**: `python3 -I launchers/aoa_host.py run /etc/ace-of-angels/host.json`, with `check` and `status` subcommands. The same `supervisor` and `host_profile`. systemd keeps its unit, with ExecStart pointing at this. An optional console on stdin when it runs attached to a terminal replaces `start_lan_dogfight.ps1`.

### 4.6 Rollout order (each step shippable)

1. Quick fixes: F-01 (CLI defaults → preserve), F-03 (store ids, validate, catch at top level, log file), F-04, F-07, F-10, F-16/17/18/19.
2. Extract `aoa/host_profile.py` + `aoa/supervisor.py`. Point `host_control`, `dedicated_host` and `map_viewer serve` at them, and delete `start_lan_dogfight.ps1`. Add supervisor tests with a fake child process; they need no game files.
3. Shared `settings.json` + `catalog.py`. Migrate `host_control.json`/`rotation.json`. Generate the doc defaults table from the catalog.
4. Player wizard + Join tab. Retire `setup_game.ps1` (keep it one release as a fallback).
5. Host firewall/share helpers.

### 4.7 Risks

- **Elevation:** editing hosts or the firewall from a non-elevated `pythonw` needs a separate elevated helper (`ShellExecuteW "runas"`). The UAC prompt and antivirus heuristics around hosts-file edits can scare users. Keep the helper tiny and auditable. Edit only the named lines and always offer Remove.
- **ActiveSkin registration from automated shells** is already known to fail invisibly (play.md:48-50). The wizard runs it as the user from the GUI process, which should work, but this needs testing on a clean Windows 10 and 11.
- **Downloading on the player's behalf** (archive.org installer, opening the dgVoodoo page) must stay "user's own copy". Keep hash pinning, never redistribute, and keep archive.org courtesy (one request, back off on 429).
- **The login-dialog Station IP shortcut** (F-02) is a hypothesis. Verify it on a real client before building UX on it. Until then the hosts alias stays the path for addresses longer than 11 characters.
- **Two control paths for patches** (launcher vs standalone patch CLIs) will keep producing stale backups (F-24) unless the standalone CLIs are clearly marked as developer tools.
- **The tests mostly skip without game files** (5/6 client, 5/8 host here). The core split must add game-free tests for profile→argv, settings validation and the supervisor, or the redesign will be no better verified than today.
- **Changing the systemd ExecStart** on deployed Linux hosts needs a documented upgrade step, plus a migration from `rotation.json` + `host.env`.

---

## Appendix A. Journeys today

Counted from `docs/play.md`, `lan-dogfight.md`, `vpn-dogfight.md`, `host-control.md` and `linux-host.md` as written.

### (A) First-time player → flying offline

| # | Step | Tool/window | Typed |
|---|---|---|---|
| 1 | Download and install Python 3.12 (tick PATH) | browser, installer | |
| 2 | Download and install Git | browser, installer | |
| 3 | `git clone https://github.com/…/ace-of-angels-preservation.git ace-of-angels` | PowerShell | URL, folder |
| 4 | `cd ace-of-angels` | PowerShell | path |
| 5 | `py -3.12 -m venv .venv` | PowerShell | command |
| 6 | `.venv\Scripts\python.exe -m pip install -r requirements.txt` (installs 4 packages players don't need) | PowerShell | path |
| 7 | `.venv\Scripts\python.exe -I tools\fetch_known_builds.py builds\` (downloads 2 installers) | PowerShell | path + `builds\` |
| 8 | Download `dgVoodoo2_87_5.zip` | browser | |
| 9 | Create `originals\wrappers\dgvoodoo2-2.87.5\` and move the zip there "unopened" (play.md gives no command for this) | Explorer | full folder path |
| 10 | `powershell -ExecutionPolicy Bypass -File tools\setup_game.ps1` (must be your own shell) | PowerShell | flag + path |
| 11 | Double-click `tools\client_launcher.cmd` | Explorer → launcher | |
| 12 | Click **Play** | launcher | |
| 13 | Login dialog → **Play Offline** → Play | game | |

**About 13 steps, 7 programs/windows** (browser, 2 installers, PowerShell, Explorer, launcher, game). **6 typed command lines, 1 hand-made folder path, 2 flags** (`-I`, `-ExecutionPolicy Bypass`). No admin.

### (B) Joining a friend's game (LAN; VPN adds the VPN steps)

| # | Step | Tool | Typed / admin |
|---|---|---|---|
| 1 | Get the host's IP (out of band) | chat | |
| 2 | (VPN) install the VPN, sign in, accept the share, `ping`/`tailscale ping` | VPN app, PowerShell | IP |
| 3 | Close the game | | |
| 4 | Notepad **as administrator** → open `C:\Windows\System32\drivers\etc\hosts` (switch the filter to All files) → add `<IP> aoalan` → save, not as `hosts.txt` | Notepad (admin) | path, IP, alias, **admin** |
| 5 | (optional) `[System.Net.Dns]::GetHostAddresses('aoalan')` | PowerShell | command |
| 6 | `prepare … --station aoalan --no-experimental-protection` (**resets 5 launcher options, F-01**) | PowerShell | exe path, 2 flags, alias |
| 7 | `prepare_client.py check …` | PowerShell | exe path |
| 8 | `prepare_client.py launch …` (or the launcher's Play) | PowerShell/launcher | exe path |
| 9 | Login with dummy values; "if the login dialog retains an old Station IP, set it to the host's LAN IPv4"; Play Online → pilot → **LAN Dogfight** | game | IP again |
| 10 | Later: re-prepare `--station localhost` and remove the hosts line | PowerShell, Notepad (admin) | again |

**About 9 steps (LAN), 4–5 tools, the IP typed 2–3 times, 3 exe paths, admin required.**

### (C) Hosting on Windows with the GUI (LAN)

| # | Step | Tool | Typed / admin |
|---|---|---|---|
| 1 | `ipconfig` to find the IP (the GUI can also detect it) | PowerShell | |
| 2 | Elevated PowerShell: 2 × `New-NetFirewallRule … -LocalAddress <IP> -RemoteAddress LocalSubnet …` | PowerShell (admin) | 2 long commands, IP ×2, **admin** |
| 3 | Double-click `tools\host_control.cmd` | Explorer → host window | |
| 4 | Mode = LAN, pick address, map, terrain, limits → **Start host** | host window | |
| 5 | Tell each player the IP, the alias `aoalan`, and the hosts/prepare instructions (the GUI hint says "client prepared with `--station aoalan`") | chat | |
| 6 | If the host also plays: all of journey (B) on the same PC, pointing `aoalan` at its own LAN IP | Notepad (admin), PowerShell, game | |

**About 6 steps + journey B, 3–4 tools, the IP typed 2–3 times, admin.** VPN adds VPN install, admin-console sharing and a different `-RemoteAddress` range.

### (D) Hosting unattended on Linux

Windows side: 4 typed commands (`$LinuxHost = …`, `ssh mkdir`, `scp -r tools deploy`, `scp SCRTY.BIN`). Linux side: `apt-get` ×2, optional Tailscale install + `tailscale up`, 9 `useradd`/`install`/`cp`/`chown`/`chmod` lines, `sudoedit host.env` (type the bind IP), optional `rotation.json` edit, 3 test suites + `wc -c` + `systemd-analyze verify`, then `daemon-reload`, `enable --now`, `status`, `journalctl`, `cat status.json`, `ss`.
**About 25 typed commands over SSH, 2 machines, 1 IP typed, no install script, and no update path** other than repeating the scp/cp by hand. There is no kick/ban/say interface (linux-host.md:146). Players then do journey (B) with `aoavpn`.

## Appendix B. Widget → engine map

### Client launcher (`tools/client_launcher.py`)

| Widget (label) | Maps to | Default shown | Newcomer-clear? | End to end? |
|---|---|---|---|---|
| Game folder (read-only) + Browse… | `read_settings(folder)` | `ROOT/game/2.9.2` or argv; not remembered | yes | yes |
| Distant objects — extended visibility | `prepare(distant_objects=)` → `object_persistence` | installed state | ok | yes |
| Solid world models — reduce distant shape popping | `experimental_solids` → `solid_world_render`; exclusive with the next | installed | ok | yes (exclusivity in GUI `changed()` and `validate_options`) |
| Asteroid models only — reduce shape popping | `experimental_asteroids` → `asteroid_render` | installed | ok | yes |
| Full world mesh and texture detail | `experimental_world_detail` → `world_detail`; exclusive with the next | installed | ok | yes |
| Full station detail only | `experimental_station_detail` → `station_detail` | installed | "only" is confusing | yes |
| 32-bit textures — richer color and alpha | `experimental_texture32` → `texture32` | installed | ok | yes (second path: `texture32.py`, F-24) |
| Smoother frame timing | `smooth_frame_clock` → `frame_clock` | installed (CLI default on) | ok | yes; reset by the CLI (F-01) |
| Corrected object visibility math | `bounded_visibility` → `visibility_fix` | installed | jargon | yes; reset by the CLI |
| Chase camera, orbit view and visible player ship (F2/F4) | `chase_camera` → `third_person` + `own_ship_model` + `own_ship_menu` | installed | yes | yes; reset by the CLI |
| Widescreen ship-selection framing | `menu_framing` → `menu_aspect` | installed | ok | yes; reset by the CLI |
| Anti-aliasing (8x) / Anisotropic (16x) / Preserve point-sampled / Generated mipmaps / Per-pixel lighting | `dgVoodoo.conf [DirectX]` keys via `install_wrapper.set_key` | installed; disabled without the wrapper | the middle two are jargon | yes (custom values preserved); key presence in 2.87.5 not verifiable here |
| Replacement texture pack | `set_texture_pack` → `texture_pack` records + `.launcher-texture-pack` cache | installed; disabled when no pack is installed or cached | yes | yes (test passes game-free) |
| Original visuals (all off) | clears `VISUAL_KEYS` (includes 2 fixes, F-21) | — | yes | yes |
| Reload installed settings | `load()` | — | yes | yes |
| Station host | `prepare(host=)` → 12-byte EXE field, `host_field` (≤11 chars); shows `localhost` for `aoahost.com` | installed | **no** ("Station") | yes, but resolution is not checked (F-02); fails if the protection probe is installed (F-22) |
| Restored power-up pickups | `powerup_pickups` → `powerup_pickup` | installed | yes | yes; reset by the CLI |
| Apply / Play | `apply_settings` (preflight, rollback, re-read verify) / then `Popen(AOACLIENT.EXE)` | — | yes | yes; blocked while the game runs (`require_closed`) |

Not reachable from the client launcher: `experimental_protection` (preserved), undo/restore, check, wrapper install, ActiveSkin registration, JRMAP `jrmap292.trn` install, texture pack build/install, patch version display.

### Host control (`tools/host_control.py`)

| Widget | Maps to (`station_stub` flag) | Default | Clear? | End to end? |
|---|---|---|---|---|
| Mode | `--profile` local-relay / lan-dogfight / vpn-dogfight (saved as the **label**, F-03) | This PC only | yes | yes |
| Host address (editable combo, PowerShell-detected) | `--bind-address` (forced to 127.0.0.1 for local) | 127.0.0.1 | ok | the range is checked by `--print-config`; ownership only at bind time → log pane only |
| Map (20 names) | `--map`; JRMAP + terrain → host-side `jrmap292.trn` check only (F-09) | Arena1a | components unexplained | yes |
| Build map terrain (clients need patch v11) | `--experimental-terrain` (+ `--powerup-zones game/<trn>` for TRN maps) | on | "patch v11" not actionable (F-11) | yes |
| Backdrop | `--backdrop` | spacebkgd3 | names opaque | yes |
| Max players 1–8 | `--max-players` | 4 | yes | yes |
| Kill limit / Time limit (min) | `--kill-limit` / `--time-limit` ×60 | 20 / 10 | yes | yes |
| Target ships 0–20 | `--target-ships` | 4 | explained inline | yes |
| Game folder (free text) | key path `SCRTY.BIN`, power-up TRN | `game/2.9.2` | no Browse (F-20) | yes; the node export path ignores it (F-12) |
| Navigation buoys / Turret trial / Warp gates trial | `--navigation-buoys/--turret-trial/--warp-trial <work/2.9.2/export/AOAOBJECTS>` + `--sustained-delivery` | on / off / off | prerequisite not explained (F-12) | yes; availability rules match `station_runtime` (tested) |
| Start / Load map (restart) / Stop | `HostProcess.start/stop` (console `quit`, then terminate) | — | yes | Load map stops before validating (F-04); stop blocks the UI |
| Kick / Ban / End match / Send message | console `kick N`, `ban N`, `end`, `say …` | — | yes | yes (kick/ban not tested with a real client per host-control.md) |
| `--autostart` (CLI) | starts with the saved settings | — | — | yes |

Shared by both launchers: the game folder concept (different widgets and defaults) and knowledge of the station alias (`ALIASES` in host vs free text in client). Nothing is shared in code.

## Appendix C. Errors, feedback, logs

| Situation | Client launcher | Host control | dedicated_host / ps1 |
|---|---|---|---|
| `.venv` missing | the `.cmd` prints a message and pauses (good) | same | ps1 throws "Missing project Python environment"; systemd uses `/usr/bin/python3` |
| Game folder missing | status line "Cannot load this game folder: [Errno 2] … AOACLIENT.EXE". Apply/Play disabled, Browse works. No hint to run setup | messagebox "no SCRTY.BIN in …" | journal: "SCRTY.BIN must contain exactly 256 bytes" or OSError text |
| Unknown EXE hash / foreign patches | status "unsupported client or conflicting patches" / "executable changed outside the recorded setup; refusing to overwrite". No next step offered | n/a | n/a |
| Python packages missing | not needed (stdlib only; tkinter ships with python.org) | same | same |
| Wrapper not installed | quality boxes disabled, note shown (good) | n/a | n/a |
| ActiveSkin not registered | not detected; the game shows a taskbar button and no dialog | n/a | n/a |
| Port in use / address not on this PC | n/a | server exits <5 s with "Host I/O failed: … Check that X belongs to this PC and the ports are free." **log pane only**, status "Stopped", no dialog, not restarted | ps1 restarts 3× every 5 s, then throws; systemd retries 4× per 10 min |
| Server crashes | n/a | auto-restart 3 per 10 min with the *current* GUI values; message in the log pane | dedicated raises → exit 1 → systemd restart; ps1 loop |
| Uncaught launcher exception | lost (`pythonw`, no log) | lost; F-03 makes the window never appear | traceback in journal / console |
| Saved settings corrupt | n/a (no settings file) | bad JSON → defaults (silent); bad values → crash or late ValueError | strict validation (good), generic message (F-08) |

Logs: client launcher none. Host control: server JSONL `work/host/<profile>.jsonl` (rotating, 4 files); the GUI log pane is in memory, 1000 lines, lost on close. ps1: `work/<profile>.jsonl` + console. Dedicated: `/var/lib/ace-of-angels/host.jsonl` + journal. Game: `game\2.9.2\Logs\`.

## Appendix D. State, config and duplicated constants

Where settings live:
- **Client launcher:** no settings file. State is derived from `AOACLIENT.EXE` bytes + `_client_setup.json` + `AOACLIENT.EXE.setup-original` + `dgVoodoo.conf` + `_texture_pack*.json` + the `.launcher-texture-pack` cache. The last folder is not remembered. No registry use (only `setup_game.ps1` reads the AppCompat key, and `register_activeskin.ps1` writes HKCU\Software\Classes).
- **Host control:** `work/host/host_control.json`. Unversioned, unvalidated, saved only after a successful start, `mode` stored as a UI label, time in minutes.
- **start_lan_dogfight.ps1:** none (parameters only).
- **dedicated_host:** `rotation.json` (strict, seconds, `maps` list) + `host.env` (bind, players) + `rotation-state.json` (schema 1).
- Host and client formats are not compatible with each other, and neither is the GUI host with the headless host (`time_limit_min` vs `time_limit_seconds`, `map` vs `maps`, label vs profile id, `game` folder vs key path).

Copies of the same fact:

| Fact | Copies (file:line) |
|---|---|
| Map list | `online_terrain.py:46-68` (source); `start_lan_dogfight.ps1:19` (2 maps); `map_viewer.py:30-44` (notes only); `dedicated_host.py:24` + `rotation.json.example:2` (default rotation); docs |
| Backdrops | `host_control.py:34`; `station_runtime.py:67-68`; `start_lan_dogfight.ps1:20`; `map_viewer.py:63` (default, unchecked) |
| Ports 5031/5033/5034 | `station_runtime.py:69-71,204-205`; `dedicated_host.py:173-175`; `host_control.py:361` (text); `start_lan_dogfight.ps1:69` (text); `deploy/linux/aoa-host.service` (implicit); firewall commands in lan/vpn/linux docs |
| Aliases aoalan/aoavpn | `host_control.py:33`; `start_lan_dogfight.ps1:65`; play/lan/vpn/linux docs |
| Kill/time/players defaults | `station_runtime.py:77,81,82`; `host_control.py:35-37`; `dedicated_host.py:23-34`; `start_lan_dogfight.ps1:18,77`; `rotation.json.example`; `host.env.example:4` |
| Game folder default | `client_launcher.py:22`; `host_control.py:37`; `map_viewer.py:62`; `start_lan_dogfight.ps1:26`; `setup_game.ps1:19`; export path `host_control.py:48,72` |
| Patch option registry | `client_launcher.py:27-38` (launcher), `prepare_client.py:149` (configure signature), `:269` (prepare signature), `:327-340` (CLI flags: 7 of 12 options, different defaults), `:76-146` (inspect) |
| Restart policy | `host_control.py:43,449-452`; `start_lan_dogfight.ps1:28,83-92`; `aoa-host.service:5-6,21-22` |
| Status/log paths | `host_control.py:63,87`; `start_lan_dogfight.ps1:33-34`; `map_viewer.py:76`; deploy unit |
| Python invocation | `client_launcher.cmd:9` (`pythonw -I`); `host_control.cmd:9` (`pythonw`); `setup_game.ps1:26` (venv or `python`); `start_lan_dogfight.ps1:38` (venv only); unit file (`/usr/bin/python3 -I -u`) |

## Appendix E. Architecture today

- `client_launcher.py` (332 lines): lines 1-197 are logic (≈60 %), Tk-free and importable. `gui()` (199-325) is pure view. Tests import the logic directly. Good separation, but the logic sits in the launcher module rather than next to `prepare_client`.
- `host_control.py` (521 lines): lines 1-193 are logic (≈37 %). `gui()` (195-517) also contains behaviour: crash-restart policy (438-456), the map-switch sequence (394-402), share/firewall hint text (353-362) and status formatting (458-498). That behaviour cannot be tested without Tk. `test_real_checkboxes…` skips here because there is no tkinter.
- Tests here: client 1 of 6 ran, host 3 of 8 ran (the rest need game files or Windows).
- Duplicated logic: the `station_stub` argv builder ×5 (F-05); the restart loop ×3 (F-14); status-file reading ×2 (`HostProcess.status`, `dedicated_host.monitor`); child-process flags (`-I -u`, `CREATE_NO_WINDOW`) ×3; game-folder resolution ×4; the "players must quit and rejoin" messaging ×4 (GUI, ps1, dedicated, docs).
- The docs' command lines duplicate code defaults by hand (firewall ports, `--station` values, default limits). They drift (F-06, F-15).

## What I did not check

- Did not run either GUI (no Windows, no tkinter here). Widget behaviour is from reading the code. `.cmd` and `.ps1` behaviour is from reading, not from running them.
- Did not verify the dgVoodoo `[DirectX]` key names against the 2.87.5 zip (not available here), the ActiveSkin registry footprint, or the login dialog Station IP shortcut (F-02 hypothesis).
- Did not run game-dependent tests (no `game/`). Did not test `make_map.py serve` beyond reading the docs. Did not audit `station_stub` internals beyond the CLI validation and bind error handling.
- Did not check whether capstone 5.0.3 / unicorn 2.1.1 wheels exist for every Python the docs allow.
