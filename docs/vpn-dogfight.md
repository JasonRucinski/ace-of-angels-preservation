# Internet dogfight over a private VPN

This is the supported route for playing with friends on other internet
connections. Everyone joins a private VPN (Tailscale, ZeroTier, WireGuard or
similar), and the host runs the `vpn-dogfight` profile on its VPN address.
Nothing is forwarded through a router, and the game server is never exposed to
the public internet.

As with the [LAN dogfight](lan-dogfight.md), the original 2.9.2 clients handle
flight, weapons and damage. The host relays events, assigns temporary pilots
and counts client-reported kills.

Status, 22 October 2026: implemented and verified on loopback only
(`tools/test_internet_play.py`, including a session under 60 ms RTT, 3% loss
and 1% duplication; [full gate: 77 tests and nine emulators](../evidence/2.9.2/local_gate_20261022_internet_play.json)).
A real internet session between separate connections has
**not** been recorded yet. See [Acceptance](#acceptance) below.

## Why a VPN and not port forwarding

- The server list tells clients a literal arena IPv4 address, and the host must
  bind that same address. Behind a home router, the public address and the
  host's own address differ, so port forwarding does not work as-is.
- The legacy cipher/CRC is not authentication, and guest tickets travel
  unencrypted. Anyone who could reach a public port could impersonate players
  or flood the host.
- A VPN gives the host an address every player can reach directly. Only people
  you invite can reach it, and their traffic is encrypted. Game datagrams are at
  most 512 bytes, well inside a VPN's MTU (Tailscale uses 1280).

## What vpn-dogfight adds over lan-dogfight

- **Accepts VPN addresses**: `100.64.0.0/10` (Tailscale and other overlay
  networks) as well as private RFC1918 ranges (ZeroTier, WireGuard). The address
  must belong to this PC. Public addresses are rejected.
- **Sustained delivery is on** (`--sustained-delivery`). Despawns, missile
  launches/impacts, death notices, the join sequence (ship load, flight
  entry, spawn position, player loads), respawn positions, score records and
  match announcements are sent reliably and in order. They no longer stop after
  30 messages per player. The design is in
  [findings 9.33](findings.md#933-sustained-reliable-delivery-without-a-client-patch-22-october-2026).
- **Rejoin after a crash or dropout.** The player restarts the game and logs in
  again. If their old ship has been silent for 5 seconds, a new login from
  the same VPN address removes it at once rather than after the 30-second
  timeout. The host serves 49 arena joins per run before it needs a
  restart. A rejoining player gets a new temporary pilot name and a zero score.
- **Operator tools** (also available on LAN through the launcher): a console
  (`status`, `kick <slot>`, `ban <slot>`, `end`, `help`), a status file with
  per-player ping, bandwidth and idle time, and automatic restart after a crash
  (at most three restarts within 10 minutes).

## Host setup

For a dedicated Linux machine, use [Minimal Linux host](linux-host.md).
The instructions below run the host on Windows.

1. Install your VPN on the host and sign in. Note the host's VPN IPv4 address.
   With Tailscale, run `tailscale ip -4`.
2. Give each player access to the host only. With Tailscale, share the host
   machine with each player's own Tailscale account from the admin console.
   They then see only that machine, not the rest of your network. With
   ZeroTier, authorize each player's node in your network. The exact menus
   depend on the VPN product; follow its documentation.
3. Allow the game ports **only from the VPN's address range** (elevated
   PowerShell, once). Replace the host address. For ZeroTier or WireGuard,
   replace `100.64.0.0/10` with your VPN subnet, for example `10.147.17.0/24`:

```powershell
New-NetFirewallRule -Name AoA-VPN-UDP -DisplayName "Ace of Angels VPN UDP" -Direction Inbound -Action Allow -Protocol UDP -LocalPort 5031,5033 -LocalAddress 100.101.102.103 -RemoteAddress 100.64.0.0/10 -Profile Any
New-NetFirewallRule -Name AoA-VPN-TCP -DisplayName "Ace of Angels VPN TCP" -Direction Inbound -Action Allow -Protocol TCP -LocalPort 5034 -LocalAddress 100.101.102.103 -RemoteAddress 100.64.0.0/10 -Profile Any
```

   `-Profile Any` is used because VPN adapters are often classified as Public.
   The local-address and remote-range restrictions keep the rules VPN-only.
   Remove them later with `Remove-NetFirewallRule -Name AoA-VPN-UDP,AoA-VPN-TCP`.

4. Check the configuration, then start the host and leave the window open:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools/start_lan_dogfight.ps1 -Vpn -HostAddress 100.101.102.103 -MaxPlayers 4 -PrintConfig
powershell -NoProfile -ExecutionPolicy Bypass -File tools/start_lan_dogfight.ps1 -Vpn -HostAddress 100.101.102.103 -MaxPlayers 4
```

   The launcher prints the VPN adapter it found. If the address is missing, the
   VPN is not connected. Add `-Map Arena1a -Terrain` to load the Arena1a
   geometry (see [arena1a.md](arena1a.md); its collision is not yet accepted).
   Logs go to `work/vpn-dogfight.jsonl`. The status file is
   `work/vpn-dogfight-status.json`.

If the host PC also plays, it is a client like the others. Use the same
`aoavpn` hosts entry below.

## Each player

1. Install and connect the VPN, and accept the host's share or invite. Check the
   path: `ping 100.101.102.103` (use the host's address). With Tailscale,
   `tailscale ping 100.101.102.103` also reports whether the connection is
   direct or relayed. A relayed (DERP) connection works but adds latency.
2. Use matching 2.9.2 assets and the supported setup from
   [client setup](client-setup.md). Close the game.
3. As administrator, edit `C:\Windows\System32\drivers\etc\hosts` and add
   `100.101.102.103 aoavpn` (the host's VPN address). The client's Station name
   field is limited to 11 characters, which most VPN addresses exceed, so the
   short alias is required.
4. Prepare, check and launch:

```powershell
.venv/Scripts/python.exe -I tools/prepare_client.py prepare game/2.9.2/AOACLIENT.EXE --station aoavpn --no-experimental-protection
.venv/Scripts/python.exe -I tools/prepare_client.py check game/2.9.2/AOACLIENT.EXE
.venv/Scripts/python.exe -I tools/prepare_client.py launch game/2.9.2/AOACLIENT.EXE
```

5. Log in with dummy values, choose Play Online, your temporary pilot and
   **VPN Dogfight**.

**If you crash or drop out:** restart the game and log in again. Your old ship
disappears and you get a fresh pilot. Do not keep a crashed client window open
while rejoining.

## Host console

Type into the host window:

| Command | Effect |
|---|---|
| `status` | Slot, pilot, kills/deaths, ping, inbound/outbound kbit/s and idle seconds per player |
| `kick 3` | Sends "You were removed by the host" and removes slot 3. The client then shows `Server Not Responding`. They may rejoin. |
| `ban 3` | Kick, and ignore that VPN address until the host restarts |
| `end` | Finish the current match now and announce the result |

The status file has the same per-player data plus uptime, joins used, reliable
messages pending/expired and traffic totals. If its `updated_utc` stops
advancing, the host loop has stopped. It contains no IP addresses or login data.

## Lag testing before inviting people

The host can add artificial delay, jitter and loss to its own traffic, so a LAN
session can rehearse internet conditions without extra tools. Both directions
are affected, so the RTT setting is the added round trip. The
launcher prints a yellow warning while this is on. Never use it for real play.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools/start_lan_dogfight.ps1 -HostAddress 192.168.0.61 -TestRttMs 80 -TestLossPercent 1
```

Run the grid that the [roadmap](internet-server-todo.md#7-performance-and-enjoyable-play-gates--both-applications)
specifies: 30, 80 and 150 ms with 0, 1 and 3% loss. At each step, record:

- whether remote ships move smoothly or snap (relay snapshots refresh once a second)
- whether hits the shooter sees are counted (damage is computed on the victim's PC)
- whether kills, deaths, respawns and score records always arrive
- whether joins complete, how long they take, and whether rejoining works
- ping and kbit/s from `status`

The LAN profile keeps best-effort delivery unless it is started with the Python
option `--sustained-delivery`. Test that option on LAN with the
same grid to separate delivery effects from latency effects.

## Acceptance

Not yet done. Record each result with client hashes, VPN product, direct or
relayed path, and measured ping:

- Two players on **genuinely separate internet connections** join, see each other,
  fight, score and respawn. A same-house or same-LAN test does not count.
- A real client applies the wrapped join sequence (ship load, flight entry,
  position, player loads), respawn position, score record and match text. The
  dispatch path is shared (0x486464), but these types have only been verified
  unwrapped on real clients.
- A player closes the game mid-match and rejoins. Their old ship disappears for
  others within a few seconds, and they can fight again.
- `kick` and `ban` behave as described, and the remaining players continue.
- Four, then eight players, with `status` bandwidth recorded.
- The lag grid above, with notes on hit registration and smoothness.

## Known limits

- Damage is decided on the victim's PC from relayed fire state. At high ping,
  shots that look like hits to the shooter can miss. There is no lag
  compensation. This was the original game's model over 2000s internet, so
  measure it before redesigning it.
- Reliable messages to each player are delivered one at a time, about one per
  round trip. At 150 ms that is roughly 6 per second per player, enough for
  dogfight events. A join with 8 players takes about 10 round trips.
- The reorder margin (`--reorder-margin`, 3 s) assumes no datagram arrives more
  than 3 seconds behind a later one on the same path. A VPN path that holds
  packets longer could, in principle, replay an old event.
- Slots are not reused. After 49 arena joins, or 64 Station logins, restart the
  host. Station logins also count returns to Station (Alt+Q).
- Movement remains best effort with one-second absolute snapshots.
  Collision forwarding (`0x48`) and pings are best effort.
- Anyone you admit to the VPN can join. Tickets are still legacy unencrypted
  fields, but they only travel inside the VPN.
