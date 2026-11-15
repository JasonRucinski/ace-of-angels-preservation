# Phase 3: the two launchers

Rebuild the player launcher and the host launcher so that a person who has
never used a command line can install, play, join a friend and host. The
engines stay: phase 2 gave you the patch registry and `prepare`
(`aoa/client/`), `HostConfig`, `Supervisor` and the headless
`tools/aoa_host.py` (`aoa/host/`), the map registry (`aoa/maps/registry.py`)
and the manifest-driven fetcher (`aoa/research/fetch.py`). The launchers
only call them. Read `docs/restructure/audits/launchers.md` first: section
4 is the design this brief adopts, appendix A the journeys to shorten,
appendix B every widget today.

Files: `aoa/launchers/` (rewrite freely), `Play.cmd`, `Host.cmd`,
`tools/client_launcher.*`, `tools/host_control.*` (shims and forwarders),
`tools/setup_game.ps1`, `tools/start_lan_dogfight.ps1`, launcher suites in
`tests/`, `docs/play.md`, `docs/host-control.md`, `docs/client-setup.md`
(launcher sections), `docs/lan-dogfight.md`, `docs/vpn-dogfight.md`,
`docs/linux-host.md` (settings file only), `docs/STATUS.md`, `README.md`
quick start. You may add small, tested functions to `aoa/client/` and
`aoa/host/` when a launcher needs a fact they own, but not change their
behaviour.

## Structure

```
aoa/launchers/
  settings.py     one settings file, schema, validation, migration
  catalog.py      what the windows offer: maps (playable first, with notes), backdrops,
                  profiles, option groups and labels, feature -> minimum patch level
  game_folder.py  find and verify a game folder: executable state, assets, wrapper,
                  login skin registered, extra terrain file
  install.py      the first-run steps; each has check() -> Status and run(progress)
  join.py         parse what a host shares, decide how the client reaches it, check it
  netinfo.py      this PC's addresses, classified (loopback, home network, VPN range)
  tkcommon.py     worker-thread runner, error dialog + log file, shared widgets
  play_app.py     the player window (view only)
  host_app.py     the host window (view only)
```

Everything except `tkcommon`, `play_app` and `host_app` imports without
tkinter and is unit-tested on Linux with no game files. The two `*_app`
modules hold no decisions: they map widgets to the logic modules.

## One settings file

`work/settings.json`, `schema: 1`: `game_folder`; `client` (`server`,
remembered `friends`); `host` (exactly `HostConfig.to_json()`), so the same
`host` object works as the Linux host's config file. Defaults live in the
engines' tables, never in the launchers; the file stores only what differs.
Unknown keys are refused by name. Old `host_control.json` and the Linux
`rotation.json` + `host.env` are migrated once and left in place. A bad file
never stops a window opening: it opens with defaults and says what it
ignored.

## Player window (`Play.cmd`, title "Ace of Angels")

**Setup checklist**, shown first until every row is green, and reachable
later from a "Setup" button. One row per step, each with a status, one plain
sentence, and one button:

1. Game files: "Find my game folder…" or "Download the 2.9.2 installer"
   (about 35 MB from archive.org, through the fetcher, with the hash
   checked; say where it comes from before starting).
2. Game folder built and verified against `config/client-2.9.2.json`.
3. Compatibility fixes applied (shows the patch level).
4. Login screen skin registered (runs `tools/register_activeskin.ps1`;
   Windows only: on other systems the row says so).
5. Graphics wrapper (recommended, optional): "Open the download page" and
   "I've downloaded it" (looks in the user's Downloads folder, checks the
   hash, installs). Skippable, with one sentence on what you lose.

**Play tab:** one large Play button; "Play on: This PC / <friend>"; a
one-line status ("Game ready · patch level 22 · wrapper on").

**Join a friend tab:** a box to paste what the host shared (an address, or
the share line the host window produces). The launcher then shows three
checks with plain results: the address is usable by the game (it must fit
the client's 11-character limit, or go through a name: explain which);
the name resolves to that address (if not, show the exact line to add to
the hosts file, a Copy button, and "Open Notepad as administrator": do not
edit system files silently); the host answers on its list port. "Save as
friend" and "Join" apply the server through `prepare` without touching any
other option.

**Options tab:** the registry's options in its groups (Fixes, Visual
extras, Experimental) plus Graphics quality (wrapper), each with a short
label and a longer hover text; "Recommended settings" and "Original
visuals"; "Restore the original game"; "Install JRMAP terrain"; texture
pack status. Conflicting options explain themselves instead of silently
unticking.

## Host window (`Host.cmd`, title "Ace of Angels Host")

**Setup panel:** "Who can join?" (This PC only / My home network / Friends
over a VPN); the address, auto-detected for that choice, with a sentence
when none is found; map (one, or "Rotate through…", playable maps only,
each with its note); kills, minutes, players; an Advanced section (backdrop,
target ships, map objects with their requirements, ports). Start validates
in a worker thread and shows a single clear error if the settings cannot
start.

**Running panel:** a share box ("Tell your players: …" with a Copy button,
producing a line the player window's Join tab accepts); status; the player
table; kick, ban, end match, message; "Change map" (validates first, then
warns players, then restarts); the log. The supervisor's restart, rotation
and recycling are the same as the headless host.

**Firewall:** a row that says which ports and address need an inbound rule
and offers "Copy the command" (the exact `New-NetFirewallRule` lines from
`docs/lan-dogfight.md`). Do not run elevated commands.

## Behaviour both windows share

- Nothing slow runs on the window thread (hashing, prepare, validation,
  process stop, address detection): use the worker runner; the window stays
  responsive and shows progress.
- Any error shows one sentence and a Details section, and is appended to
  `work/logs/launcher.log` (player) or `work/logs/host.log` (host).
- `Play.cmd` and `Host.cmd` use `-I`; start-up failures are visible.
- The words on screen are for players: "Server address", not "Station
  host"; "patch level", not "online-terrain-v2".

## Verifying it here

There is no Windows, but the windows can be opened on a virtual screen:
install tkinter with `apt-get install -y python3-tk` (it serves
`/usr/bin/python3.12`), then use `docs/restructure/briefs/tk_shot.sh
OUT.png SECONDS /usr/bin/python3.12 -I tools/<shim>.py [args]` to run a
window under Xvfb and capture it. Build a throwaway game folder from
`tests/support_patches.synthetic_pristine` in a temp directory to drive the
player window past its checklist. Give each window a `--demo STATE` switch
(or equivalent test hook) that opens it in a named state with fake data, so
every state can be captured without a game or a network: checklist with
mixed results, Play tab ready, Join tab with a failing and a passing check,
Options tab, host setup, host running with three fake players, an error
dialog. Capture each, LOOK at the image (read the PNG), fix what is cut
off, overlapping, misaligned or unclear, and capture again. Commit the
final captures under `docs/restructure/screens/`.

Tests (game-free, CI tier): settings validation and migration; catalog
contents against the registries; `join` parsing and the three checks with a
fake resolver and a fake socket; install steps with fake engines; netinfo
classification; the worker runner; and view smoke tests that build each
window in every `--demo` state under Xvfb when tkinter and a display are
available, skipping with a reason otherwise.

## Done when

- The first-time journey in `docs/play.md` is: install Python, download the
  project, double-click `Play.cmd`, follow the checklist. Count the manual
  steps before and after in your report.
- The host journey in `docs/host-control.md` is: double-click `Host.cmd`,
  choose who can join, Start, send players the share line.
- `tools/test.py --tier ci` passes; the screenshots are committed; the old
  double-click files still work as forwarders.
- `docs/STATUS.md` says exactly what was and was not run: these windows have
  been opened on Linux under a virtual screen only, never on Windows, and
  the checklist steps that touch Windows (skin registration, wrapper,
  downloading) have not been run at all.
