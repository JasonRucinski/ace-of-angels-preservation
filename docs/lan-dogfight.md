# Private LAN dogfight

This is the short path to playing with trusted people on the same local network.
For friends on other internet connections, use the
[VPN dogfight](vpn-dogfight.md): the same launcher with `-Vpn`.
The original 2.9.2 clients handle flight, weapons and damage. The host relays
events, assigns temporary pilots and counts client-reported kills. It is not an
authoritative or public internet server.

Implementation is ready for manual LAN acceptance. Two synthetic clients have
exercised the profile; actual separate-PC gameplay and player capacity must still
be recorded. Start with two players, then test four and eight.

Verification: [65 tests and eight emulators passed](../evidence/2.9.2/local_gate_20261021_lan_dogfight.json).
A separate [same-PC LAN-address check](../evidence/2.9.2/lan_binding_20261021.json)
also admitted two synthetic guests through real UDP/TCP listeners on the host's
assigned IPv4, using ephemeral ports. Neither result establishes separate-PC
firewall access, actual kills or real-client capacity.

## Host setup

Use the existing repository Python environment and your own extracted game files.
Run `ipconfig` and find this PC's Wi-Fi/Ethernet IPv4 address on the shared LAN.
The examples use `192.168.0.61`; substitute your host's actual address everywhere.
Keep that address stable during a session. No router forwarding is needed.

First inspect the configuration without opening sockets or modifying the client:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools/start_lan_dogfight.ps1 -HostAddress 192.168.0.61 -PrintConfig
```

Allow the following inbound ports on the host. In an elevated PowerShell window,
create these rules once; the launcher does not change firewall settings:

```powershell
New-NetFirewallRule -Name AoA-LAN-UDP -DisplayName "Ace of Angels LAN UDP" -Direction Inbound -Action Allow -Protocol UDP -LocalPort 5031,5033 -LocalAddress 192.168.0.61 -RemoteAddress LocalSubnet -Profile Private
New-NetFirewallRule -Name AoA-LAN-TCP -DisplayName "Ace of Angels LAN TCP" -Direction Inbound -Action Allow -Protocol TCP -LocalPort 5034 -LocalAddress 192.168.0.61 -RemoteAddress LocalSubnet -Profile Private
```

Use a trusted home LAN marked **Private** in Windows network settings. Do not
open these ports on Public networks or forward them through the router. Existing
broad Python firewall rules are not narrowed by these rules; review any existing
allow rule if necessary. To remove these two rules later:

```powershell
Remove-NetFirewallRule -Name AoA-LAN-UDP,AoA-LAN-TCP
```

Start the host, leaving the terminal open. It accepts console commands
(`status`, `kick <slot>`, `ban <slot>`, `end`, `help`), writes
`work/lan-dogfight-status.json` every two seconds and restarts itself after a
crash (at most three times in 10 minutes); see
[the VPN runbook](vpn-dogfight.md#host-console). `-TestRttMs`, `-TestJitterMs`
and `-TestLossPercent` rehearse internet conditions on the LAN
([lag testing](vpn-dogfight.md#lag-testing-before-inviting-people)).

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools/start_lan_dogfight.ps1 -HostAddress 192.168.0.61
```

The launcher defaults to two players. Add `-MaxPlayers 4` or `-MaxPlayers 8` for
capacity checks. This is a configuration limit, not verified capacity. Ctrl+C
stops the host. Logs rotate under `work/lan-dogfight.jsonl` and omit raw payloads.

The equivalent Python command is:

```powershell
.venv/Scripts/python.exe -I tools/station_stub.py game/2.9.2/SCRTY.BIN work/lan-dogfight.jsonl --profile lan-dogfight --bind-address 192.168.0.61 --max-players 2
```

`--advertised-address` defaults to the bind address and must match it. All three
listeners bind that specific address. A nonexistent local address or occupied
port fails startup. Existing diagnostic/local profiles still bind `127.0.0.1`.

## Each client PC (including the host if it also plays)

1. Use matching existing 2.9.2 assets and the supported Windows setup from
   [client setup](client-setup.md). Keep the existing graphics wrapper and
   stability fixes. There is no automatic asset download or redistribution.
2. Close the game. Open Notepad as administrator and edit
   `C:\Windows\System32\drivers\etc\hosts`. Add one line:
   `192.168.0.61 aoalan`. Replace an old `aoalan` mapping instead of adding
   conflicting entries. Save as `hosts`, not `hosts.txt`.
3. In a normal terminal at the repository root, prepare and check the client:

```powershell
.venv/Scripts/python.exe -I tools/prepare_client.py prepare game/2.9.2/AOACLIENT.EXE --station aoalan --no-experimental-protection
.venv/Scripts/python.exe -I tools/prepare_client.py check game/2.9.2/AOACLIENT.EXE
```

The short `aoalan` alias fits the client's 11-character startup hostname field.
Verify resolution returns the host address:

```powershell
[System.Net.Dns]::GetHostAddresses('aoalan')
```

4. Launch the game yourself:

```powershell
.venv/Scripts/python.exe -I tools/prepare_client.py launch game/2.9.2/AOACLIENT.EXE
```

Use dummy username/password values. If the login dialog retains an old Station
IP, set it to the host's LAN IPv4. Choose Play Online, your assigned temporary
pilot (`testpilot-01`, `testpilot-02`, etc.), and **LAN Dogfight**. The selected
ship is `Ym Khtat`; the default terrain/backdrop are `CTF_arena`/`spacebkgd3`.
For map inspection, add `-Map Arena1a` to the PowerShell launcher (Python:
`--map Arena1a`). See [Arena1a recovery and blockers](arena1a.md). The optional
`-Backdrop` / `--backdrop` accepts `spacebkgd`, `spacebkgd2`, `spacebkgd3`,
`spacebkgd5` or `spacebkgd6`. Use matching local assets on every client.
The map names do not establish complete map collision or CTF mechanics.

To return to localhost, close the game, prepare it with `--station localhost`,
and remove only your `aoalan` hosts-file entry. Existing exact client undo remains
available through `prepare_client.py undo`; do not delete unrelated hosts entries.

## What a session does

- Free-for-all with the existing client flight/combat rules and immediate
  death/reset behavior. The host restores the victim's assigned spawn position.
- At 20 kills or ten minutes, announce winner/tie and reset kill/death scores.
  Play continues; this does not reset surviving ships' health, ammunition,
  positions or missiles. Restart everything for a fresh arena.
- Ordinary combat delivery is best effort. The LAN profile rejects the optional
  reliable-combat experiment, so combat does not consume its 30-event budget.
  The separate reliable removal limit remains unchanged.
- No seamless reconnect or slot reuse. Close all clients and restart the host
  and clients when someone needs to reconnect, a delivery/session limit is hit,
  or the arena becomes inconsistent. Do not repeatedly retry an exhausted session.
  The Python option `--sustained-delivery` (default in `vpn-dogfight`) removes the
  30-message delivery limit and supports rejoining; see
  [findings 9.33](findings.md#933-sustained-reliable-delivery-without-a-client-patch-22-october-2026).
- No custom respawn delay, spawn protection, rearming rule, account database,
  server physics, verified additional playable maps, CTF or AI is added.

## Acceptance and troubleshooting

Manually test two separate PCs, then expand player count only after passing:

- Both players join, see each other, maneuver and see gunfire.
- Obtain an actual gun kill and missile kill. Confirm killer/victim scores,
  observer death notification, respawn position and ability to fight again.
- Observe ammunition/loadout after death. Record original behavior; if it
  prevents continued dogfighting, investigate before calling the loop playable.
- Complete a score round, receive the same result, see cleared scores, and
  continue fighting in the next round. Temporarily use `--kill-limit 2` with
  the Python command for an initial short check, then test the default round.
- Minimize/background each client and restore it; verify continued networking.
- Close all clients, stop/restart the host and rejoin successfully.

Record client hashes, player count, OS/wrapper, observed kills/respawns/results,
and failures. Crashes, repeated false scores, unusable respawns or persistent
divergence block LAN acceptance. Synthetic packet tests do not prove real damage.

If Play Online is disabled, check `aoalan` resolution and the prepared executable.
If the server list fails, check TCP 5034 as well as UDP 5033. If Station works but
flight does not, check UDP 5031 and the advertised address. Ensure both computers
are on the same LAN, not an isolated guest Wi-Fi. An address change requires
updating hosts entries, firewall rules and the host command. A same-PC connection
to the LAN address does not verify another PC's firewall/network path.

Automated checks: `tools/test_lan_dogfight.py` validates configuration and guest
source-IP binding, then runs the actual profile with its fixture LAN address
redirected to loopback. It verifies all three requested listener addresses,
listing, two guest admissions, 120 combat events per observer, duplicate impacts,
death/respawn messages and two score-round transitions. Run the complete gate
with `tools/verify_local.py`.
