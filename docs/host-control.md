# Host control window

Added 23 October 2026. `tools/host_control.py` is one window for running a
host: start it, watch players and scores, message everyone, kick or ban,
end a match, switch maps and stop. It runs the existing server
(`tools/station_stub.py`) as a child process and uses that server's own
status file and console commands, so the server behaves exactly as it does
from the command line.

## Opening it

Double-click `tools\host_control.cmd`, or run:

```powershell
.venv/Scripts/python.exe tools/host_control.py
```

`--autostart` starts the host with the last-used settings as soon as the
window opens. Settings are remembered in `work/host/host_control.json`.

## Settings

| Setting | What it does |
|---|---|
| Mode | **This PC only** (`local-relay` on 127.0.0.1), **LAN** (`lan-dogfight`) or **VPN (internet)** (`vpn-dogfight`) |
| Host address | LAN/VPN only: pick this PC's address from the list (found automatically) or type it |
| Map | Any of the 20 maps from [map-viewer.md](map-viewer.md) |
| Build map terrain | Sends the map so clients build it on flight entry. Clients need patch version 11 or later; without it they still join, in empty space |
| Navigation buoys | Restore navigation markers for the selected map. Initially checked, preserving the previous automatic behavior when exported assets are available |
| Turret trial | Restore five Arena1a turrets with firing disabled. Initially unchecked; this does not enable turret combat |
| Warp gate trial | Restore one Arena1a gate to WarpTgt01. Initially unchecked; available only in **This PC only** mode |
| Backdrop, max players, kill limit, time limit | Passed straight to the server; 0 turns a limit off |
| Target ships | Passive hostile ships 12,000 units ahead of the spawn that T, J and missiles can target (`--target-ships`, [findings 9.45](findings.md)); 0 turns them off. Guns and missiles destroy them, the server keeping score of the damage ([findings 9.46](findings.md)), and they return after 15 s |
| Game folder | Where `SCRTY.BIN` (and, for JRMAP, `jrmap292.trn`) is read from. With terrain on, JRMAP's power-up zones are passed to the host (`--powerup-zones`, [findings 9.44](findings.md)); clients need patch version 19 to pick them up |

The server checks every setting (`--print-config`) before it binds a port, so
an address that isn't on this PC, or the wrong range for the mode, is
refused with the server's own error message. The window shows what players
need for LAN/VPN (hosts-file alias, `--station` value, firewall ports); see
[lan-dogfight.md](lan-dogfight.md) and [vpn-dogfight.md](vpn-dogfight.md).

The **Map objects** checkboxes require terrain and the original exported assets
in `work/2.9.2/export/AOAOBJECTS` with their `_export.json` manifest beside that
directory. Unavailable options are unchecked and disabled, with the reason shown.
Changing maps, mode or terrain can clear incompatible selections; recheck them
when returning to a supported configuration. Choices are saved on successful start.

Use **Start host**, or **Load map (restart)** if the host is already running, to
apply checkbox changes. Connected players must quit and rejoin; the checkboxes
do not change objects during an active flight. The status panel shows the object
counts from the running host, even while you edit the next run's settings.
Turret and warp trials retain the [documented limitations](arena1a-rebuild.md):
editor orientation and live gameplay acceptance remain unverified.

## While it runs

- **Status:** mode, map, match number, uptime, players / max, arena joins
  used out of 49, Station logins, banned IPs and traffic counters, refreshed
  every second from `work/host/<profile>-status.json`. If the file stops
  updating for more than 8 seconds, the status line says the host may be
  stuck.
- **Players (sorted by kills):** slot, temporary pilot name, kills, deaths,
  ping, traffic, idle time and whether the player is in flight.
- **Kick / Ban selected:** removes the player; Ban also refuses their IP
  until the host restarts.
- **End match:** finishes the current match and announces the result.
- **Send message to all:** an arena text message to everyone in flight
  (printable ASCII, up to 120 characters).
- **Host log:** the server's own output.

## Changing maps and stopping

**Load map (restart)** stops the host cleanly and starts it again on the map
now selected. Connected players get an arena message and must quit the game
and rejoin, because a client builds terrain only once per flight session. The
window asks first if anyone is connected.

**Stop host** sends the console `quit` command. Players get "Host is shutting
down", and the server runs its normal cleanup and prints its final traffic
and kill counts. If it hasn't exited after 10 seconds, it is terminated.
Closing the window offers to stop a running host.

If the host crashes (a non-zero exit after running for 5 seconds), the window
restarts it after 5 seconds, at most three times in 10 minutes, like
`start_lan_dogfight.ps1`. Players must rejoin after a restart.

## Server console additions

Two commands were added to the server console (also usable from
`start_lan_dogfight.ps1`):

- `say <text>`: arena message to everyone in flight.
- `quit`: tell players, then stop with normal cleanup (exit code 0).

## Verification (23 October 2026)

- `tools/test_host_control.py` starts the real server (ephemeral ports)
  through the same process wrapper. It checks the status file, `say`, a clean
  `quit` with cleanup output, settings refused before starting, and the
  arguments for every map and mode. It is part of `verify_local.py`.
- Live, on this PC, with the real window's buttons and a real 2.9.2 client
  (scratch copy):
  - Start on CTF_arena: the client joined, the table showed it in flight,
    and its terrain list held 55 objects.
  - Load map → JRMAP: the host restarted with exit code 0; after the client
    rejoined, it built 18 JRMAP objects and showed in the table again.
  - End match and Stop host: both exited with code 0, with the server's
    cleanup output.
  - `say` reached 1 connected player, and the client stayed connected for
    the next 60 seconds.
- Not tested: LAN/VPN mode with players on other machines, kick/ban with a
  real client, and automatic crash restart.
