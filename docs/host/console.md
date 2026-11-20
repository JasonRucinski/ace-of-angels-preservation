# Running a host: console, status file, crash restarts

What every host offers while it runs, however it was started. The host
window shows the same things as buttons and tables
([host-window.md](host-window.md#while-it-runs)). The Linux service has no
interactive console or remote kick/ban; use `systemctl` there
([linux.md](linux.md#3-check-and-start)).

## Host console

`tools/start_lan_dogfight.ps1` (LAN or VPN), and `tools/aoa_host.py run` or
`tools/station_stub.py` with `--console`, read these commands from the
terminal they run in:

| Command | Effect |
|---|---|
| `status` | Slot, pilot, kills/deaths, ping, inbound/outbound kbit/s and idle seconds per player |
| `kick 3` | Sends "You were removed by the host" and removes slot 3. The client then shows `Server Not Responding`. They may rejoin. |
| `ban 3` | Kick, and ignore that VPN address until the host restarts |
| `end` | Finish the current match now and announce the result |
| `say <text>` | Arena message to everyone in flight |
| `quit` | Tell players the host is stopping, then stop with normal cleanup |
| `help` | List the commands |

`say` and `quit` were added for the host window (23 October 2026); `quit`
exits with code 0.

## The status file

The host rewrites a JSON status file every two seconds:
`work/host/<profile>-status.json` on Windows (`lan-dogfight-status.json`,
`vpn-dogfight-status.json`; the host window reads the same file), and
`/var/lib/ace-of-angels/status.json` for the Linux service.

The status file has the same per-player data plus uptime, joins used, reliable
messages pending/expired and traffic totals. If its `updated_utc` stops
advancing, the host loop has stopped. It contains no IP addresses or login data.

## Crash restarts

If the host crashes, it is restarted with the settings that run had, at most
three times in 10 minutes and 5 s apart, and only after a run of at least
5 s, as the headless host does. A host that cannot start is not restarted:
the window shows the server's reason in plain words (for example, an address
that is no longer this PC's) with the server output under **Show details**.

The host window, `start_lan_dogfight.ps1` and the Linux service share this
supervisor (`aoa/host/supervisor.py`). On Linux, systemd also restarts the
controller itself when that budget runs out ([linux.md](linux.md#3-check-and-start)).

## Lag testing before inviting people

The host can add artificial delay, jitter and loss to its own traffic, so a LAN
session can rehearse internet conditions without extra tools. Both directions
are affected, so the RTT setting is the added round trip. The
launcher prints a yellow warning while this is on. Never use it for real play.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools/start_lan_dogfight.ps1 -HostAddress 192.168.0.61 -TestRttMs 80 -TestLossPercent 1
```

Run the grid that the [roadmap](../roadmap/internet-server.md#7-performance-and-enjoyable-play-gates--both-applications)
specifies: 30, 80 and 150 ms with 0, 1 and 3% loss. At each step, record:

- whether remote ships move smoothly or snap (relay snapshots refresh once a second)
- whether hits the shooter sees are counted (damage is computed on the victim's PC)
- whether kills, deaths, respawns and score records always arrive
- whether joins complete, how long they take, and whether rejoining works
- ping and kbit/s from `status`

The LAN profile keeps best-effort delivery unless it is started with the Python
option `--sustained-delivery`. Test that option on LAN with the
same grid to separate delivery effects from latency effects.
