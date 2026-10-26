# Minimal Linux host

First milestone: a dedicated Linux host runs independently of an SSH session,
starts at boot, and accepts two clients on the LAN. Then add Tailscale for
internet play. Start with Ubuntu 24.04 LTS and Python 3.12.
The Python server uses only the standard library;
no pip packages, GPU, Wine, Windows executable or desktop session are needed.

For a first test on an existing Proxmox host, create a separate Ubuntu Server
VM with **1 vCPU, 2 GiB RAM and a 12 GiB disk**, using its existing LAN bridge
and DHCP. Install SSH and `qemu-guest-agent` in the guest. Check the node's
available capacity before allocating the VM. The game runs in the guest;
the Proxmox management host does not need game packages.

You can verify the Linux service on a trusted LAN before installing Tailscale:
set `AOA_BIND_ADDRESS` to the VM's private LAN IPv4 address. `vpn-dogfight`
accepts private LAN addresses and keeps sustained delivery enabled. Players
on that LAN use the VM's address for their `aoavpn` hosts entry. Internet
players still need the VPN setup below. Record the DHCP lease or reserve its
address before relying on unattended restarts, because the configured bind
address must remain assigned to the VM.

This is the existing `vpn-dogfight` relay under a dedicated session controller.
Pilots, scores and bans are temporary. The controller starts a fresh game
process between maps, recycling its admission counters. Persistent service operation does not
yet provide persistent pilot accounts or scores. Verify startup and recovery
on each deployment, and real gameplay separately from synthetic tests.

Verified on 26 October 2026: Ubuntu Server 24.04.4 on Proxmox, with the small
VM allocation above. All 15 server suites passed (87 tests passed, 11 skipped
for missing game assets), including clean SIGINT shutdown. The deployed
service recovered after a forced process crash and a guest reboot. Two
synthetic clients on a separate Windows computer passed Station, arena,
combat and respawn checks over the LAN before and after reboot.
Later that day, the user confirmed entering the arena and flying around from
their real Windows client connected to this host over the LAN, then reported
combat, damage and destruction between two separate Windows PCs. A read-only
server audit confirmed two valid player deaths, one per fighting slot, missile
activity from both slots, normal client quits and healthy service operation.
Client scoreboard display, visible respawns and the VPN/internet path still
need direct acceptance checks. See the
[deployment verification](../evidence/2.9.2/linux_host_20261026.json) and
[two-PC combat audit](../evidence/2.9.2/linux_two_pc_combat_20261026.json).

## 1. Prepare the Linux machine

Use an ordinary SSH account with sudo access. Install Python:

```sh
sudo apt-get update
sudo apt-get install -y python3
python3 --version
```

For LAN-only testing, use the VM's private IPv4 address and continue with
section 2. For internet play, follow the
[official Tailscale Linux installation instructions](https://tailscale.com/docs/install/linux),
then connect the host with `sudo tailscale up` and record `tailscale ip -4`.
Use the normal Linux TUN interface, not userspace proxy mode: the server must
bind its own VPN IPv4 address. Enable `tailscaled` at boot and configure device
key expiry for an unattended server in the Tailscale admin console.

Share only this machine with the invited players. Configure Tailscale access
controls to permit **UDP 5031 and 5033, TCP 5034** from those players, with SSH
administration limited to the operator. Keep those game ports closed on the
public interface/provider firewall. The host binds only its VPN address.
See [Tailscale sharing](https://tailscale.com/docs/features/sharing) and the
[VPN runbook](vpn-dogfight.md) for the client connection path.

## 2. Upload this checkout and your key

From PowerShell in this repository, replace the SSH destination and the key
path. Upload the current files so local changes are included even before a
GitHub release. The key comes from your own extracted 2.9.2 installation;
never commit it or substitute a synthetic test key for real play.

```powershell
$LinuxHost = 'your-user@your-linux-host'
ssh $LinuxHost 'mkdir -p aoa-upload'
scp -r tools deploy "${LinuxHost}:aoa-upload/"
scp game/2.9.2/SCRTY.BIN "${LinuxHost}:aoa-upload/SCRTY.BIN"
```

On Linux, install the files with a separate service account:

```sh
id aoa >/dev/null 2>&1 || sudo useradd --system --user-group --home-dir /var/lib/ace-of-angels --shell /usr/sbin/nologin aoa
sudo install -d -m 0755 /opt/ace-of-angels
sudo cp -R ~/aoa-upload/tools /opt/ace-of-angels/
sudo chown -R root:root /opt/ace-of-angels/tools
sudo chmod -R a+rX /opt/ace-of-angels/tools
sudo install -d -o root -g aoa -m 0750 /etc/ace-of-angels
sudo install -o root -g aoa -m 0640 ~/aoa-upload/SCRTY.BIN /etc/ace-of-angels/SCRTY.BIN
sudo install -o root -g aoa -m 0640 ~/aoa-upload/deploy/linux/host.env.example /etc/ace-of-angels/host.env
sudo install -o root -g aoa -m 0640 ~/aoa-upload/deploy/linux/rotation.json.example /etc/ace-of-angels/rotation.json
sudo install -o root -g root -m 0644 ~/aoa-upload/deploy/linux/aoa-host.service /etc/systemd/system/aoa-host.service
sudoedit /etc/ace-of-angels/host.env
```

Set `AOA_BIND_ADDRESS` to the VM's private LAN address for the first test,
or the actual `tailscale ip -4` result for VPN play. Keep
`AOA_MAX_PLAYERS=2` for the first session. Do not reinstall the example over
an existing configuration during later updates. The rotation example selects
10 kills or 15 minutes, with native terrain enabled; see section 5 to change it.

## 3. Check and start

Run the game-free checks first (synthetic clients on loopback):

```sh
cd /opt/ace-of-angels
python3 -I tools/test_station_runtime.py
python3 -I tools/test_internet_play.py
python3 -I tools/test_dedicated_host.py
sudo -u aoa wc -c /etc/ace-of-angels/SCRTY.BIN
sudo systemd-analyze verify /etc/systemd/system/aoa-host.service
```

The key must be exactly 256 bytes. The tests use temporary synthetic keys and
do not verify your real game key or a real VPN path.

```sh
sudo systemctl daemon-reload
sudo systemctl enable --now aoa-host
sudo systemctl status aoa-host --no-pager
sudo journalctl -u aoa-host -n 40 --no-pager
sudo cat /var/lib/ace-of-angels/status.json
sudo ss -lntup | grep -E ':5031|:5033|:5034'
```

Verify all three listeners use the configured address. `updated_utc` in the status
file should advance every two seconds; check it again after a few seconds.
An `active` systemd state alone does not prove the game loop is healthy.

The service starts the dedicated controller after the network (and Tailscale
when enabled), and retries failed starts every 30 seconds, up to four starts
in ten minutes. Planned map changes happen inside the controller and do not
consume this crash budget. A missing VPN
address, incorrect key or occupied port is visible in the journal. After
fixing a failure or connecting a slow VPN, recover with:

```sh
sudo systemctl reset-failed aoa-host
sudo systemctl start aoa-host
```

Normal logs rotate in `/var/lib/ace-of-angels/host.jsonl` through `.3` (about
4 MiB total for newly created logs). The status file contains current player
counts, admission usage, traffic, delivery counters, game PID and a `lifecycle`
section with limits, next map and restart countdown. This service
has no interactive console or remote kick/ban interface. Use SSH and
`systemctl stop`, `start` or `restart aoa-host` for service control. Stopping
uses SIGINT to close sockets and drain logs; players must relaunch and rejoin.

Service behavior follows the [systemd service](https://www.freedesktop.org/software/systemd/man/latest/systemd.service.html)
and [execution](https://www.freedesktop.org/software/systemd/man/latest/systemd.exec.html)
references. The process runs as `aoa`, with read-only code/configuration and
a writable state directory. `KillMode=mixed` sends the initial stop signal to
the controller, which stops its child cleanly; systemd can still kill remaining
processes on timeout ([systemd.kill](https://www.freedesktop.org/software/systemd/man/latest/systemd.kill.html)).

## 4. Join from Windows and record the first result

Use the [VPN client instructions](vpn-dogfight.md#each-player): add the host's
configured address as `aoavpn` in the Windows hosts file, prepare the supported 2.9.2
client for that Station name, and select **VPN Dogfight**. Each player's VPN
connection must be active for VPN play; LAN clients can connect directly.
The rotation enables native terrain. Both clients need the supported prepared
client with **online-terrain-v2 or later** (included in current preparation).
Older clients may connect without displaying the selected terrain. The initial
playlist uses original layout assets; it needs no extra JRMAP terrain file.

For real-client internet acceptance, record these checks:

- Two real clients on separate internet connections join, see each other,
  fight, score and respawn; record ping and direct/relayed Tailscale paths.
- Close the SSH session; the game continues. Restart a client and rejoin.
- Stop/start the service; logs flush and both clients can relaunch and rejoin.
- Reboot the Linux machine; Tailscale and the game service return, status
  updates resume and clients can join again.

## 5. Unattended rotation and recovery

Verified on the Linux VM on 26 October 2026: a 10-kill match from two synthetic
Windows clients advanced to CTF_arena_b, where they could rejoin and fight.
A deliberately stalled game process recovered automatically, and a guest
reboot retained the selected map. All 16 suites passed on Linux and Windows.
Timed rotation was tested with an accelerated timer; the deployed limit is
900 seconds. Native terrain markers/spawns are verified in protocol tests;
visual map loading after real-client rejoin remains an acceptance check.
See the [rotation verification](../evidence/2.9.2/linux_rotation_20261026.json).

Edit `/etc/ace-of-angels/rotation.json`, then restart `aoa-host` to apply changes.
The shipped configuration is:

| Setting | Behavior |
|---|---|
| Maps | `CTF_arena` → `CTF_arena_b` → `ast_fld_a` → repeat |
| Kill limit | First pilot to **10 kills** ends the session |
| Time limit | **900 seconds (15 minutes)** from first flight entry; whichever limit comes first |
| Restart warning | Announce next map, allow **30 seconds** to quit, then pause **5 seconds** before reopening |
| Arena admissions | Recycle at **40**, before the hard lifetime limit of 49 |
| Station admissions | Recycle at **56**, before the hard lifetime limit of 64 |
| Empty used session | Recycle after **5 minutes** without arena players; an unused server stays idle |
| Health timeout | Stop an unresponsive game process after **30 seconds** without fresh status; systemd restarts the controller |

During the countdown, the arena disappears from new server listings and new
logins/joins are refused; connected players still receive announcements and
can quit. The match result remains available until the process closes.
**Players must quit/relaunch and rejoin after a map change.** The original
client has no verified server-driven return-to-Station or terrain reload path.
The automation makes server operation unattended; it does not add seamless
client transitions. The map name and native flight-entry marker change together.

Rotation state is saved atomically in
`/var/lib/ace-of-angels/rotation-state.json`. A completed session advances the
map; a crash or manual restart resumes the saved map with a fresh match.
This also survives a VM reboot. Admission cleanup advances the playlist too.
The timer stops when the arena empties and starts again at the next flight
entry; the idle cleanup prevents a used empty session lingering indefinitely.

Pilots, scores and bans reset with each fresh game process. Only the selected
map and completed-session counter persist. Logs record `match_end`,
`session_restart_scheduled` and `session_restart` with the reason and map names.
The controller verifies status belongs to its own child, so an old status file
cannot satisfy the health check. Repeated crashes still hit systemd's restart
limit and require fixing the cause before `systemctl reset-failed aoa-host`.

Direct `station_stub.py` launches retain their existing same-map round behavior
unless `--managed-session` is supplied. Their lifetime admission limits still
require a manual restart. Dedicated service sessions handle that recycling.
