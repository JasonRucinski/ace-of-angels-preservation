# Host window

`Host.cmd` opens the host window, "Ace of Angels Host": choose who can join,
start a host, send players one line, watch players and scores, message
everyone, kick or ban, end a match, change maps and stop. It runs the
existing server (`tools/station_stub.py`) as a child process, with the
command line from `HostConfig` (`aoa/host/config.py`) and the same supervisor
as the headless host (`aoa/host/supervisor.py`): crash restarts, map rotation
and recycling.

Rebuilt on 16 November 2026 and opened only on Linux under a virtual screen,
never on Windows ([status](../STATUS.md#implemented-but-not-tested)).

## Hosting in four steps

1. Double-click `Host.cmd`.
2. Under **Who can join?** choose **This PC only**, **My home network** or
   **Friends over a VPN**. The window finds this PC's address for that choice
   and says when there is none (for a VPN: start the VPN app, then
   **Refresh**).
3. Click **Start**. The settings are checked first, off the window's thread;
   anything that would stop the server is shown as one sentence before
   anything starts.
4. Copy the line under **Tell your players** and send it to them. In the
   player window they paste it into **Join a friend** ([play.md](../play/README.md#play-with-friends)).

For players on other PCs, Windows must also let them in: the **Firewall** box
names the ports and address and has **Copy the commands** for the two
`New-NetFirewallRule` lines of [lan-dogfight.md](lan.md) or
[vpn-dogfight.md](vpn.md). Run them once in PowerShell opened as
administrator. The window never runs them itself.

## Settings

| Setting | What it does |
|---|---|
| Who can join? | **This PC only** (`local-guests` on 127.0.0.1, with the guest admission and sustained delivery that LAN and VPN players get), **My home network** (`lan-dogfight`) or **Friends over a VPN** (`vpn-dogfight`) |
| Address | This PC's address of that kind (home ranges or the VPN range `100.64.0.0/10`), found without sending anything; **Refresh** looks again |
| Map | **One map**, or **Rotate through several maps** (players rejoin between maps). Only the 11 maps with real content are offered, each with its object count ([which](../STATUS.md#maps)) |
| Rules | Kills to win, minutes per match, players (0 turns a limit off). Defaults: 20 kills, 10 minutes, 8 players (the server's own) |
| Advanced: backdrop, target ships | Backdrop is one of the five the client ships. Target ships are passive enemies ahead of the start point for practice; they come back 15 s after being destroyed ([findings 9.46](../research/findings.md#s9-46)) |
| Advanced: map terrain | Sends the map so clients build it on flight entry; clients need patch level 11 or later. A rotation always has it on. With terrain, JRMAP's power-up zones are hosted (clients need patch level 19) |
| Advanced: map objects | Navigation buoys, turret trial, warp gates trial. Each needs terrain and the map objects exported from the game files (`work/2.9.2/export/AOAOBJECTS`); the trials need Arena1a, and warp gates This PC only. An option that cannot be used is greyed out with the reason |
| Advanced: ports, game folder | The three ports (UDP 5033 login, UDP 5031 arena, TCP 5034 server list) and the folder holding `SCRTY.BIN`, shared with the player window |

The settings are saved in `work/settings.json` (its `host` object is a
`HostConfig` file as it stands). `python -I tools/aoa_host.py run
work/settings.json` runs the same host without the window. The old
`work/host/host_control.json` is read once and left in place. A saved value
that cannot be used is reset, with a line saying which.

## While it runs

- **Tell your players:** the line to copy, and what their game needs
  (for example "Players need patch level 11 or later for map terrain").
- **Status:** map, match, uptime, players out of the maximum, arena joins used
  out of 49 (a rotation restarts itself before the limit) and banned
  addresses, read every half second from `work/host/<profile>-status.json`.
  "not responding" appears when the file stops updating.
- **Players:** slot, pilot, kills, deaths, ping, idle time, flying.
- **Kick / Ban:** after a question. Ban also refuses the player's address
  until the host restarts.
- **End match** and **Message … Send to all** (printable ASCII, up to 120
  characters).
- **Host log:** the server's own output and the supervisor's notes.

## Changing maps and stopping

**Change map** first checks the new settings. If they cannot start, it says
why and the running host carries on; nothing is announced or stopped. Valid
settings send players an arena message, stop the host cleanly and start it on
the new map. Players must quit the game and rejoin, because a client builds
terrain only once per flight session. The window asks first if anyone is
connected.

**Stop host** asks the server to quit (players get "Host is shutting down")
and waits for its cleanup, off the window's thread; after 10 seconds it is
terminated. Closing the window offers to stop a running host.

If the host crashes, it is restarted with the settings that run had, at most
three times in 10 minutes and 5 s apart, and only after a run of at least
5 s, as the headless host does. A host that cannot start is not restarted:
the window shows the server's reason in plain words (for example, an address
that is no longer this PC's) with the server output under **Show details**.
Each start also writes that run's settings to `work/host/host.json`.

## Server console additions

Two commands were added to the server console (also usable from
`start_lan_dogfight.ps1`):

- `say <text>`: arena message to everyone in flight.
- `quit`: tell players, then stop with normal cleanup (exit code 0).

## Verification

- 16 November 2026, Linux only: `tests/test_launcher_windows.py` builds the
  window in each `--demo` state under a virtual screen; the screenshots are
  in [docs/restructure/screens/](../restructure/screens/). The real window was
  also driven on Linux with a stand-in key file: Start (This PC only), the
  status and log, Change map to Arena1a and Stop all worked against the real
  server. `tests/test_launcher_logic.py` covers its decisions without a
  window, and `tests/test_host_control.py` runs a real server through the
  same supervisor when `game/2.9.2/SCRTY.BIN` exists.
- 23 October 2026, on Windows, with the window of that time (since rebuilt)
  and a real 2.9.2 client: start on CTF_arena, the client joined and built 55
  objects; Load map → JRMAP restarted the host and the client rejoined with
  18 JRMAP objects; End match, Stop host and `say` worked.
- Not tested: the rebuilt window on Windows, LAN/VPN mode with players on
  other machines, kick/ban with a real client, and automatic crash restart
  ([STATUS.md](../STATUS.md#implemented-but-not-tested)).
