# Hosting a game

Every way of hosting runs the same stand-in server, `tools/station_stub.py`.
The original 2.9.2 clients handle flight, weapons and damage. The host relays
events, assigns temporary pilots and counts client-reported kills. It is not
an authoritative or public internet server. What has been tested, and what
has not: [STATUS.md](../STATUS.md#implemented-but-not-tested).

## Choose how players reach you

| Players are | Host with | Guide |
|---|---|---|
| On this PC | `Host.cmd`, **This PC only** | [host-window.md](host-window.md) |
| On your home network | `Host.cmd`, **My home network**, or `tools/start_lan_dogfight.ps1` | [lan.md](lan.md) |
| Friends on other internet connections, through a private VPN | `Host.cmd`, **Friends over a VPN**, or `tools/start_lan_dogfight.ps1 -Vpn` | [vpn.md](vpn.md) |
| Any of these, from an unattended Linux machine | the systemd service | [linux.md](linux.md) |

While a host runs: [console.md](console.md) (console commands, the status
file, crash restarts, lag testing). Every server flag:
[server-reference.md](server-reference.md).

## With the windows (the short path)

Since 16 November 2026 the two windows do the steps below for you, except the
firewall rules, which they show for you to copy. They have been opened only on
Linux under a virtual screen, never on Windows ([status](../STATUS.md#implemented-but-not-tested)).

- **Host:** double-click `Host.cmd`, choose **My home network** or **Friends
  over a VPN**, check the address it found, copy the two firewall commands
  from the **Firewall** box into PowerShell opened as administrator (once),
  click **Start**, and send players the line under **Tell your players**
  ([host-window.md](host-window.md)).
- **Each player:** in `Play.cmd`, open **Join a friend**, paste the line and
  click **Check**. When the address fits the game's 11-character field (as
  `192.168.1.5` does), the game uses it directly and no hosts file is needed;
  a longer one, which includes every VPN address, goes through the name
  `aoalan` (home network) or `aoavpn` (VPN): the window shows the exact
  hosts-file line (for example `192.168.0.61 aoalan` or
  `100.101.102.103 aoavpn`) with **Copy** and **Open Notepad as
  administrator**; it never edits the file itself. Then **Join**: only the
  server address changes ([play/README.md](../play/README.md#play-with-friends)).

The rest of this page, and the LAN and VPN guides, are the same route by hand.

## Steps every host shares

### Ports and the firewall

The server uses three ports (see [Defaults](#defaults)): UDP 5033 for the
Station login, UDP 5031 for the arena and TCP 5034 for the server list. All
three listeners bind one address, and the server list gives clients that same
address. On Windows, allow the three ports in once, from PowerShell opened as
administrator; the exact two `New-NetFirewallRule` commands, limited to your
home network or to the VPN's address range, are in [lan.md](lan.md#host-setup)
and [vpn.md](vpn.md#host-setup). Neither window nor launcher changes firewall
settings. On Linux, the VPN's access controls do the same job
([linux.md](linux.md#1-prepare-the-linux-machine)).

Never forward the game ports through your router: the old protocol has no
real authentication. The VPN route keeps the host reachable only by people
you invite.

### The hosts name and the 11-character limit

The client's Station name field holds at most **11 ASCII characters** (plus
a terminating NUL; [the details](../reference/client-patches.md#change-the-station-host-without-removing-physics-fixes)).
A home-network address that fits, such as `192.168.1.5`, can be used
directly. A longer one, and every VPN address, needs a short name that each
player's Windows `hosts` file points at the host: `aoalan` for a home
network, `aoavpn` for a VPN. The [steps below](#each-player-by-hand) add it.

### Each player, by hand

1. Use matching existing 2.9.2 assets and the supported Windows setup from
   [play/README.md](../play/README.md). Keep the existing graphics wrapper and
   stability fixes. There is no automatic asset download or redistribution.
2. Close the game. Open Notepad as administrator and edit
   `C:\Windows\System32\drivers\etc\hosts`. Add one line: the host's address
   and the name, for example `192.168.0.61 aoalan` or
   `100.101.102.103 aoavpn`. Replace an old `aoalan`/`aoavpn` mapping instead
   of adding conflicting entries. Save as `hosts`, not `hosts.txt`.
3. In a normal terminal at the repository root, prepare and check the client
   (`aoavpn` instead of `aoalan` for a VPN):

```powershell
.venv/Scripts/python.exe -I tools/prepare_client.py prepare game/2.9.2/AOACLIENT.EXE --station aoalan --no-experimental-protection
.venv/Scripts/python.exe -I tools/prepare_client.py check game/2.9.2/AOACLIENT.EXE
```

It changes only the Station and switches the protection probe off; every other
client option keeps its installed state.
The short alias fits the client's 11-character startup hostname field.
Verify resolution returns the host address:

```powershell
[System.Net.Dns]::GetHostAddresses('aoalan')
```

4. Launch the game yourself:

```powershell
.venv/Scripts/python.exe -I tools/prepare_client.py launch game/2.9.2/AOACLIENT.EXE
```

Use dummy username/password values, choose Play Online, your assigned
temporary pilot (`testpilot-01`, `testpilot-02`, etc.) and the host's arena:
**LAN Dogfight** ([lan.md](lan.md#each-client-pc-including-the-host-if-it-also-plays))
or **VPN Dogfight** ([vpn.md](vpn.md#each-player)).

To return to localhost, close the game, prepare it with `--station localhost`,
and remove only your `aoalan` hosts-file entry. Existing exact client undo remains
available through `prepare_client.py undo`; do not delete unrelated hosts entries.

## Matches

Matches are free-for-all: 20 kills or 10 minutes, then scores reset and play
continues. Pilots, scores and bans last only as long as one server process.
The limits and the player count are settings of every host; the Linux
example rotation sets 10 kills or 15 minutes ([linux.md](linux.md#5-unattended-rotation-and-recovery)).

## Defaults

The defaults every host starts from, generated from `aoa/host/defaults.py`
(the server's argparse, the host window and the headless host read the same
table). A host's settings file or command line can change most of them.

<!-- host defaults: generated by python -I tools/run.py aoa.host.defaultsdoc --write; do not edit by hand -->

**Profiles.**

| Profile | Who can join | Relay | Guest pilots | Sustained delivery | Server-list name | Hosts name |
|---|---|---|---|---|---|---|
| `diagnostic` | this PC only (`127.0.0.1`) | no: listens only | no | off |  |  |
| `local-relay` | this PC only (`127.0.0.1`) | yes | no | off |  |  |
| `local-guests` | this PC only (`127.0.0.1`) | yes | yes | off |  |  |
| `lan-dogfight` | this PC's own address in `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16` | yes | yes | off | LAN Dogfight | `aoalan` |
| `vpn-dogfight` | this PC's own address in `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`, `100.64.0.0/10` | yes | yes | on | VPN Dogfight | `aoavpn` |

**Ports.**

| Port | Number |
|---|---|
| Station login (UDP) | 5033 |
| arena (UDP) | 5031 |
| server list (TCP) | 5034 |

**Matches and capacity** (0 turns a match limit off).

| Setting | Default |
|---|---|
| Kills to end a match | 20 |
| Match length | 600 s |
| Players at once | 8 |
| Arena joins per server run | 49 |
| Station logins per server run | 64 |
| Silence before a player expires | 30 s |
| Map | `CTF_arena` |
| Backdrop | `spacebkgd3` (the client ships `spacebkgd`, `spacebkgd2`, `spacebkgd3`, `spacebkgd5`, `spacebkgd6`) |

**Rotation and recycling** (managed sessions: the headless host, a window rotation).

| Setting | Default |
|---|---|
| Warning before a planned restart | 30 s |
| Pause before reopening | 5 s |
| Recycle a used session with no arena players after | 300 s |
| Recycle after arena joins | 40 |
| Recycle after Station logins | 56 |
| Stop a process whose status file is older than | 30 s |
| Exit code of a session that ended as planned | 75 |

**Map objects.** Objects that only sit in place run on any relay profile; warp gates, which move players without a host check, only on this PC (loopback).

| Object | Profiles |
|---|---|
| Navigation buoys | `local-relay`, `local-guests`, `lan-dogfight`, `vpn-dogfight` |
| Map waypoints | `local-relay`, `local-guests`, `lan-dogfight`, `vpn-dogfight` |
| Turret trial | `local-relay`, `local-guests`, `lan-dogfight`, `vpn-dogfight` |
| Warp gates trial | `local-relay`, `local-guests` |

**Client patch level each hosted feature needs.**

| Feature | Patch level |
|---|---|
| terrain | 11 or later |
| safe zones | 18 or later |
| power-ups | 19 or later |

<!-- end of generated host defaults -->
