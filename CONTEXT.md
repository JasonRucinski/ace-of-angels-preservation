# Ace of Angels (Flying Rock Enterprises): research context

Everything found so far about *Ace of Angels*, Flying Rock Enterprises' online
3D space-combat sim (2000–2006). The work was done in a cloud Claude Code
session on 2026-10-20; this file carries it to a local project.

Items marked *verified* were checked directly: downloaded, hashed, parsed,
read in OCR text, or read from a registry. Items marked *(snippet)* came from
a search-engine summary only.

## 1. The asks

1. Download links for every release, demo, beta and alpha.
2. A link to the website with the game's universe and lore.
3. Any sign that the project is coming back.

## 2. Status

Nine-gate expansion (27 Oct 2026): `--warp-trial` and the host checkbox now
restore all nine Arena1a warp gates, adding eight placements. Slots 71–79
replace the old single slot 85; maximum practice targets becomes 69. Original
names/destinations and duplicate Home_Rail labels retain separate tags. Native
headless checks cover coexistence, duplicate loads, 54 transit vectors and
486 exit/gate overlap checks using fixture bounds. Actual UDP checks cover
all nine routes with lost-update recovery, late join and reconnect. Still
loopback-only and opt-in; orientation/real collision geometry/live acceptance
remain unverified. See [warp trial](docs/arena1a-rebuild.md#arena1a-warp-gate-trial).

Headless warp validation (26 Oct 2026): user deferred manual playtesting.
Three additional tests pass: complete original LoadObject receiver with explicit
allocation/model/team/event service fixtures, duplicate-load suppression,
eight original overlap/guard cases, six transit velocities and no same-gate
retrigger at the remote exit. Actual UDP host with four synthetic connections
passes native-transit -> relay -> original movement decoder, lost-update
recovery without a second upload, late join and observer reconnect. No UI
needed. Real model bounds, orientation and full game-loop acceptance remain
deferred. See [headless checks](docs/arena1a-rebuild.md#headless-warp-validation).

Single warp trial (26 Oct 2026): opt-in `--warp-trial EXPORT_DIR` loads
HyBase1_Rail / WarpTgt01 in slot 85, using native kind 7 and WarpGate/WarpA.
Loopback-only, Arena1a terrain and sustained delivery required. Four focused
tests pass, including native destination receipt, exact ordered first/late joins
with buoys/turrets, gate ACK loss/retransmission and verifier rejection cases.
Isolated host prepared at 127.0.0.2; live entry remains pending because both
UI interfaces fail on the pilot dialog. Editor orientation is not restored;
transit is handled by the original local client, not authorized by the host.
See [warp trial](docs/arena1a-rebuild.md#arena1a-warp-gate-trial).

Warp investigation (26 Oct 2026): user deferred flags/control points. Recovered
all nine Arena1a gate-to-child destination links, including four `Dummy` nodes.
Original-code probes verify world destinations, kind-7 network fields and local
collision transit. Native model is WarpGate / WarpA. Transit preserves velocity
and uses destination + velocity/max(speed,100)*1000. Existing relay codecs accept
all nine destination jumps; gate authorization and live synchronization remain
unverified. No gates enabled. See [warp recovery](docs/arena1a-rebuild.md#warp-gate-recovery--26-october-2026).

Turret placement trial (26 Oct 2026): opt-in `--turret-trial` loads the five
Flag ND1-C children with neutral relations and immediately disables each.
TurretA is a provisional model choice; rotations remain zero. Original-code
checks confirm the disabled AI firing gate, and synthetic first/late joins
pass with buoys and ACK loss. Separate 127.0.0.2 loopback host prepared;
live acceptance still awaits flight entry. No automatic host-control enable
or Linux deployment. See [trial](docs/arena1a-rebuild.md#inactive-five-turret-placement-trial).

Turret hierarchy recovery (26 Oct 2026): all 80 Arena1a turret markers link
to 18 flag parents (eight groups of five, ten of four). Their saved transforms
are local; original-code execution verified all 383 root-node world transforms
within 0.05 units. Native LoadObject kind 1 attaches turret AI; embedded model
turrets use the same script/constructor through a separate enumeration path.
Added a bounded turret-group status codec and original-client disable tests
(0/1/5/50 objects). No turrets spawned; model selection, ownership, orientation,
firing/damage and live acceptance remain unresolved. See
[turret recovery](docs/arena1a-rebuild.md#turret-group-recovery--26-october-2026).

Navigation restoration (26 Oct 2026): server opt-in `--navigation-buoys` reads
original exported assets for the selected map, expanding nested placements;
JRMAP uses original TRN kind-3 Buoy/Cube objects. All 20 selections handled,
41 placements across eight maps. Local host-control enables this when the
export tree exists. Reliable first/late joins and lost-ACK delivery tested;
live visual acceptance and editor rotations remain pending. See
[navigation support](docs/arena1a-rebuild.md#all-map-navigation-support).

Arena1a in-game rebuild investigation (26 Oct 2026): user entered the local
map; live inventory reconciles all 394 expanded records: 235 static placements,
4 safe zones, 136 absent gameplay markers, absent Cube Home, 17 helpers and one
nested-layout reference. Missing gameplay markers comprise 80 turrets, 18 flags,
10 navigation markers, 9 warps and 19 service markers. Twenty-one original-code
gate probes passed. At the time of this baseline capture, no restoration patch had been applied. See
[rebuild investigation](docs/arena1a-rebuild.md) and
`evidence/2.9.2/arena1a_rebuild_20261026.json`.

Map-node investigation (26 Oct 2026): corrected nested-layout resolution to
use the original client's case-insensitive prefix comparison and archive order.
Recovered 60 geometry instances in outerchange and 10 in irrosa01 in expanded
exports. Their resolved object counts plus safe zones match prior live counts
(616 / 457). Audited all 17 node-layout Gobs; gameplay markers remain separate
from asset availability. Six tests pass, including original comparison-code
emulation. See [map-node findings](docs/map-viewer.md#unfilled-node-investigation-26-october-2026)
and `evidence/2.9.2/map_nodes_20261026.json`. No client/server deployment changed.

Unattended Linux host (26 Oct 2026): deployed `tools/dedicated_host.py` under
systemd. User-selected limits are first pilot to 10 kills or 15 minutes;
playlist is CTF_arena → CTF_arena_b → ast_fld_a, with native terrain enabled,
a 30-second warning and 5-second intermission. Each transition uses a fresh
game process; extra recycling occurs at 40 arena / 56 Station admissions or
after 5 minutes with no arena players in a used session. A 30-second stale
status watchdog stops a hung child, then systemd applies bounded crash recovery.
Only map position and completed-session count persist; players must relaunch
and rejoin between maps. Linux TCP listeners now permit safe POSIX rebinding
after a session closes. The existing network-loss test also needed a console
initialization barrier and explicit fixture shutdown to avoid timing races.
Verified: all 16 suites (Linux 94 passed / 11 skipped; Windows 103 passed /
2 POSIX-only skips, with local game assets now available), a live 10-kill
Windows-to-VM transition, combat on the next map, deliberate SIGSTOP watchdog
recovery and guest reboot preserving CTF_arena_b / one completed session.
The timer path was tested with an accelerated limit; production is set to 900 s.
Real-client terrain/rejoin acceptance and internet access remain separate.
See [rotation verification](evidence/2.9.2/linux_rotation_20261026.json) and
[operation/configuration](docs/linux-host.md#5-unattended-rotation-and-recovery).

Minimal Linux host deployed (26 Oct 2026): a separate Ubuntu Server 24.04.4
VM on the existing network Proxmox host, with 1 vCPU, 2 GiB RAM and a 12 GiB
disk. The unprivileged systemd service starts at boot, survives SSH disconnects,
restarts after a crash, and exits cleanly on SIGINT after socket/log cleanup.
Verified actual guest reboot and crash recovery, plus two synthetic Windows
clients over the LAN: Station login/listing, arena entry, remote players,
missile launches/impacts and death/respawn, repeated after reboot.
All 15 game-free suites passed with third-party packages disabled (`-I -S`):
Linux 87 passed / 11 skipped; Windows 86 passed / 12 skipped. Fixed the TCP
reset test's Windows-only `SO_LINGER` layout for Linux. CI now includes Ubuntu
24.04, but the hosted CI job itself has not been run in this session.
The original 2.9.2 installer was downloaded and hash-verified again; its
256-byte `SCRTY.BIN` matches the pinned client configuration and is installed
privately in the guest. No game files are committed.
See the [Linux runbook](docs/linux-host.md) and
[verification record](evidence/2.9.2/linux_host_20261026.json); local connection
details are in ignored `work/proxmox/README.md`. Reserve the DHCP address before
depending on indefinite unattended operation. Later on 26 Oct, the user
confirmed connecting from their Windows PC, entering the arena and flying
around on this Linux host, then fought using two separate Windows PCs with
visible damage and destruction. A read-only server audit corroborated the
session: slots 2 and 3 exchanged missile reports and each recorded a death
with a valid opposing killer. Both left by explicit client quit. The expected
runtime/configuration and game key were deployed; the service had no restarts,
invalid logged packets or expired reliable events during the session.
See the [two-PC combat audit](evidence/2.9.2/linux_two_pc_combat_20261026.json).
Exact client damage values, displayed scoreboard and visible respawns were not
independently observed. VPN installation and internet acceptance remain pending.
Admission limits and temporary pilots/scores still apply.

Internet play (22 Oct 2026): friends on other connections play through a private
VPN with the `vpn-dogfight` profile ([runbook](docs/vpn-dogfight.md)). Sustained
reliable delivery replaces the 30-message lifetime cap without a client patch,
crashed players can rejoin, and the host has status/kick/ban, crash restarts and
a lag/loss test mode ([findings 9.33](docs/findings.md#933-sustained-reliable-delivery-without-a-client-patch-22-october-2026)).
Internet impairment/delivery tests use loopback; LAN acceptance is recorded
above. Separate-internet-connection acceptance is pending.

Implementation roadmaps (21 Oct 2026):
[Internet server, maps and performance](docs/internet-server-todo.md) and
[client/game modernization](docs/modernization-todo.md). These distinguish
verified progress from proposed work and define initial release gates.

Arena lifecycle continuation (21 Oct 2026): handshake retries are idempotent;
explicit quit and heartbeat expiry clear arena state. Removal now uses bounded
reliable retries; original-client emulation confirms its duplicate history
holds only 30 IDs. Observers retire on delivery failure or history exhaustion.
Verified with synthetic localhost sockets, not a real-client despawn test.
Retired slots/endpoints remain reserved until restart (49 lifetime admissions);
safe reuse/reconnect needs a compatibility decision. See
[findings 9.13](docs/findings.md#913-reliable-removal-and-the-slot-reuse-limit-21-october-2026).
Original-client receive-path emulation now verifies five reliable removal
packets yield five ACKs and only two removal calls (correct slots, duplicates
suppressed). Real-client launch was blocked by the Windows automation helper's
access error; visible despawn remains unverified. See [findings 9.14](docs/findings.md#914-original-client-reliable-receive-path-verification-21-october-2026).
Local runtime work now provides a validated `--profile local-relay`, bounded
rotating metadata logs with opt-in raw capture, an independent bounded TCP
list worker, and live arena population/availability. Six runtime tests and
the 14 existing protocol tests pass. See [local server runbook](docs/local-server.md).
Station now tracks per-client sessions and routes TCP list/file-state requests
by a recovered player-record ID plus source IP. Original-client emulation
verifies ID transfer and the separate u8 job/flag fields. Three session tests
cover same-IP clients, alias isolation, stale TCP, quit/expiry and bounded
admissions. Station login counts are live. IDs/endpoints are not reused within
a run (64 Station admissions); this adds no authentication, pilot ownership
or arena authorization. Real-client Station transitions remain unverified.
See [findings 9.16](docs/findings.md#916-per-client-station-sessions-and-tcp-correlation-21-october-2026).

Larger continuation (21 Oct 2026): UDP decoding now enforces the original
512-byte wire/output bounds with bounded per-pass expansion, fuzz tests and
pre-decode rate limits. Version mismatches are rejected before admission;
active arena capacity defaults to eight. The new client preparation/launcher
composes known patches, records exact undo, validates pinned static assets and
wrapper hashes, and recovers interrupted replacements on temporary-copy tests.
The relay tracks all 16 safe movement groups and sends periodic absolute
snapshots; 300 original-code state cases and 200 recovery cases pass. Upstream
ordering and authoritative simulation remain open. `local-guests` adds unique
pilot names and Station-ticket/arena binding with revocation, while retaining
explicit legacy diagnostic profiles. These are local limits, not public auth.
See [client setup](docs/client-setup.md), [local protocol](docs/local-protocol.md),
[release specification](docs/first-playable-release.md), and findings 9.17–9.20.
Inbound reliable envelopes are now deduplicated per channel/endpoint (last 64
IDs); duplicates are still ACKed, and only handshakes are re-answered. 46 tests
pass; see [findings 9.21](docs/findings.md#921-inbound-reliable-duplicate-suppression-21-october-2026).
Static analysis: server `0x3E` is a silent "hang up" that suppresses the
client's `Server Not Responding` timer, so it is unsuitable for shutdown. The
client's server-silence grace is `CLIENTGRACE` 16000 (likely ms), overridable
by an unshipped `params.aoa`; no server-driven return-to-Station message
is known yet ([findings 9.22](docs/findings.md#922-server-hang-up-0x3e-client-grace-timers-and-shutdown-21-october-2026)).
Real-client check (21 Oct 2026, [findings 9.23](docs/findings.md#923-real-client-check-21-october-2026)):
closing each TCP connection after its reply hung the real client's UI thread
(stuck queue mutex in `ShutdownTCPBySocket`). Fixed: connections stay open
while their Station session lives. Other fixes: Station heartbeats ignore the
echoed tag (Station and arena share one client socket), and removal retries
last until the peer timeout. Verified live: Alt+Q quit → observer ACK and
despawn from its player table. The client relaunches itself
(`autologin`) back to Station. `CLIENTGRACE` is 16.2 s, or 5.8 s with a
`params.aoa` override. Background clients stalled 38–64 s because the
inactive-window timer skips frames in (believed) exclusive mode. The new
client patch `background-network-v1` (prepare patch version 2, `0x446EAF`)
fixes this under dgVoodoo windowed output
([findings 9.24](docs/findings.md#924-background-client-network-stall-and-fix-21-october-2026)).
Combat groundwork ([findings 9.25](docs/findings.md#925-combat-protocol-survey-and-gun-table-21-october-2026)):
gun damage per level (7–130, ids 250–850) decoded from the client
(`tools/gun_table.py`, `evidence/2.9.2/gun_table.json`). Gunfire is `0x1F`
status bits plus a per-gun fire-state block. Live test ([findings 9.26](docs/findings.md#926-victim-side-damage-gun-state-relay-and-death-report-21-october-2026)):
the **victim's client computes damage** from relayed fire state and reports
death with `0x37` (killer tag). The relay now forwards the bounded gun block,
so real clients damage and kill each other. Next: server-side scoring, death
broadcast and respawn. Done since (9.27): death notices, kill counts, respawn
position and targeted collision forwarding. The intermittent arena-join crash is
**fixed** ([findings 9.29](docs/findings.md#929-arena-join-crash-unterminated-archive-text-21-october-2026)):
the decompressor returned `tgtwin2.cfg` without a NUL terminator. Client patch
`archive-terminator-v1` (prepare patch version 3) fixes it; 25/25 joins were clean.
Match loop (9.30): scoreboard (kills/deaths) and kill/time match limits work with real
clients. Spawn protection needs reliable delivery (toggle `0x81`). Missiles are blocked
on team definitions (ad-hoc teams crashed the client). Update (9.31): that crash was a
null team leader in `0x50`; free-for-all teams work behind `--experimental-teams`, and
targeting works. Update (9.32): **missiles work.** The racks were full; launches were refused
because player loads marked everyone Friendly (now Hostile at `0x26` +0x44/+0x45). The server
assigns missile tags, echoes `0x2A` to all players and relays one `0x30` impact per missile;
6/6 live launches hit and damaged the target. Missiles need 5000+ units of separation.
Run `.venv\Scripts\python.exe -I tools/verify_local.py` (needs `unicorn`) for the full synthetic/emulation gate;
combat, collision, real-client transition checks and external release gates
are still incomplete. Do not describe the overall internet todo as finished.

Local continuation (20 Oct 2026): the stand-in reaches Station and explicit
flight entry on localhost. An experimental relay creates a remote player in
one of two real clients. A late-join decoder crash was traced to unsafe raw
position-packet forwarding and replaced with a filtered kinematic prefix.
Arena pings now produce real-client replies and remove the server-not-responding
warning. A synthetic peer's position plus velocity produces actual remote
motion; two instrumented real clients load each other's pilots without the
earlier fatal late-join exception. On 21 Oct the user confirmed all local
movement works in the patched client during the held-input retry. Earlier
automated key taps did not establish that result. Two real clients now hold
each other's player-input movement state; inactive-client drift and accurate
continuous synchronization remain unresolved. Inactive
windows pause processing until reactivated. See `docs/findings.md`
sections 9.3–9.11. The relay now includes explicit consistent local spawn
positions and cached position/velocity seeds for late joiners (socket and
original-decoder tested). Live testing found EnterFlight resets coordinates;
sending the position after EnterFlight now preserves the local spawn.
Remote NaNs were traced to zero-time physics updates. A reversible client
guard now skips those updates; 600 live samples remained finite after the
patch, versus 38/100 invalid before it. The guard is applied to the local
2.9.2 game copy; full multiplayer remains incomplete. See 9.10 for limits.
An opt-in `--experimental-object` flag now spawns one passive mission ship
using recovered type 0x25; object state and visible rendering were verified
in the real client. AI/combat/scenario rules are not implemented.
The 2.9.2 assets
include 17 exported layouts, five backdrops, and one binary scenario (`Curt3`);
inventory and hosting limits are in `docs/hosting-assets.md`.

Level-data audit (22 Oct 2026, [docs/level-data.md](docs/level-data.md)):
all clients were searched for missed maps and missions. **New:** `JRMAP.TRN`,
a loose file in every installer, is a world map saved by the in-game editor:
74 placed objects (3 flag stations, 13 turrets linked to flags, a segmented
station, 6 warp gates, docks and capital ships) in the format of the client's
`ReadInTerrain`. It is fully decoded but not yet loaded; the edit-mode command
names are unknown. `Curt3` now parses completely (2 teams, 5 AI groups, orders,
13 waypoints) and is the offline "ZCVS carrier group" mission. 2.0.0's
`TestScene` layout yields 178 nodes (hierarchy not decoded). Ruled out: no
orphaned bytes in any of 41 archives, no installer slack, no extra scenarios.
Other missions were server-side and are in no client.

Map viewer (23 Oct 2026, [docs/map-viewer.md](docs/map-viewer.md)): client patch
version 11 (`online-terrain-v2`) lets the loopback server load any of 20 maps
as native terrain: the 19 original 2.9.2 layouts, plus `JRMAP` converted to
2.9.2's 540-byte `.TRN` records. Run `tools/map_viewer.py serve <map>`. In a
real client, JRMAP loaded 18 objects (station segments, docked capital ships).
This is for viewing only: no collision, turrets, warps or flags.

Host control window (23 Oct 2026, [docs/host-control.md](docs/host-control.md)):
`tools/host_control.cmd` opens one window that starts the host (this PC, LAN or
VPN), shows players with kills/deaths/ping, sends messages, kicks/bans, ends
matches, switches maps (clean restart) and stops the host. The server console
gained `say` and `quit`. Tested live with a real client on this PC (map switch
CTF_arena → JRMAP); LAN/VPN players on other machines are untested.

Panel drag fix (23 Oct 2026, [findings 9.34](docs/findings.md#934-dragged-panels-stick-to-the-lower-right-corner-23-october-2026)):
dragged in-game panels jumped to the lower-right corner because the client
caches its window origin from `WM_MOVE` as unsigned words (65535,65535 live)
and adds it in every `SetCursorPos` warp. Client patch version 12
(`cursor-warp-origin-v1`) asks Windows for the live origin instead. Tested in
emulation; a real drag test is still pending.

Frame pacing fix (23 Oct 2026, [findings 9.35](docs/findings.md)): the game clock
was `GetTickCount` (~15.6 ms), so at 60 Hz about one frame in ten jumped 31 ms.
Patch version 13 (`frame-clock-v1`, default on) uses a millisecond QPC clock
and gates the background wakeup timer so it cannot draw extra frames beside the
main loop. Measured live: even 16/17 ms steps, RMS vs 60 Hz 4.7 → 1.5–2.0 ms.
Patch version 14 adds `visibility-math-v1` (Codex's culling fix, promoted
without its exact-centre change, which would have drawn the player's own ship
at the camera; [findings 9.36](docs/findings.md)).
Patch version 15 adds `third-person-camera-v1`: F2 in flight toggles a chase
camera that the renderer already had (`0x43B1D0`, gated on the never-written
byte `0x5E6879`), plus culling from that eye so your own ship is drawn.
Patch version 16 adds `own-ship-model-v1`: the client never gave your own
ship a model, and reset its LOD children to hidden every frame. Draw-call
traces now show your hull drawn with F2 on ([findings 9.37](docs/findings.md),
[9.39](docs/findings.md)). Patch version 17 adds `own-ship-menu-model-v1`:
the fighter menu's preview hid the parts of the model it showed, so a hull
picked in flight was not drawn; now confirmed on screen by the user
([9.41](docs/findings.md)).
Patch version 18 (`online-terrain-v3`, 25 Oct 2026, [findings 9.42](docs/findings.md)):
safe zones now draw as the original translucent blue wave cubes. The client
builds them in `SetupFlightMode`, which ran before our hook loaded the map,
so none were ever made; the hook now registers them after loading. Seven
maps have safe zones (Arena1a and newterrain 4, JRMAP 5, outerchange,
irrosa01, hy_base_test and CTF_arena_b 1); JRMAP's needed a converter fix
(re-run `map_viewer.py install`). Checked in memory on all of them, on
screen by Claude and confirmed by the user; zone rules (no damage etc.) are untested.
Targeting (23 Oct 2026, [findings 9.38](docs/findings.md)): T/G/J only
scan players and world objects. Map terrain (stations, ships, asteroids) is a
separate list that no target scan walks, and the server spawns no world
objects, so only players can be cycled. Update (25 Oct, [findings 9.45](docs/findings.md)):
`--target-ships N` (host window "Target ships", default 4) spawns passive hostile
ships 12,000 units ahead of the spawn. A real client cycled them with T, picked one
with J, and fired a missile that hit. Update ([findings 9.46](docs/findings.md)):
they are now destroyable through the original server channels, with no client
patch. The shooter reports its gun hits in its `0x1F` upload (submask 2,
"perceived damage"); the server subtracts gun-table damage × 0.4 from the ship's
Shield HP, sends `0x45` RemoveObject (blow up) at 0, and reloads the ship 15 s
later. Verified live with one client; missile kills and two clients are untested.
Server code in the client (25 Oct 2026, [findings 9.43](docs/findings.md)):
2.7.1 still links the server's `CAOAComm` senders (20 named routines,
32 packet types that 2.9.2 no longer sends), e.g. `SendLoadPlayer`, `SendGainScore`,
`SendSetupTFCGame`, `SendMovePowerupTo`; `tools/server_senders.py` lists them.
A few still have live callers (turret group status, set-param, load scenario).
Power-ups (25 Oct 2026, [findings 9.44](docs/findings.md)): spawn `0x43`,
pickup `0x44` and move `0x53` decoded from those senders and the 2.9.2
receivers. JRMAP's 11 kind-6 records are **power-up zones**. The relay places
one per zone (`--powerup-zones`, on automatically for JRMAP in the host
window) and moves it when taken. A real client shows all of them, but
**unmodified 2.9.2 cannot pick them up**. Type 6 was made non-collidable, and a
taken power-up never re-enables its model. Patch version 19
(`powerup-pickup-v1`, on by default) fixes both. Verified by emulation and
live with no memory writes: 22 pickups in a row, one every 5 s, and the HUD
showed "Shield +5". The user confirmed it on JRMAP's own zones with
`game/2.9.2` at version 19. A second player watching is untested.
Ship changes (24 Oct 2026, [findings 9.40](docs/findings.md)): **fixed in the
relay.** The in-flight fighter menu needs a config list (TCP job 4, one
`_all` entry) and an answer to its `0xA0` request. The relay sent neither,
so Commit said "Fighter Not Available". Now the pilot and observers get `0x27`
with the new hull, the pilot returns to spawn, and late joiners see it.
A second bug: the join's own-slot `0x26` blanked the Station ID (+0x7B) that
TCP requests carry, so job 4 was refused until the pilot's first death;
the self-load now carries the pilot's own ID. (Sending `0x42` after flight
entry instead left ghost HUD panels on the background.)
Verified live after both fixes, with no death first. The config list arrives
≈5 s into flight, so click a ship after that. A second player's view is untested.

| Ask | Status |
|---|---|
| Builds | **Six recovered client versions, verified locally:** full installers 2.0.0, 2.7.1, 2.8.0, 2.8.2, 2.9.2, plus replacement client 2.3.1 (no complete asset bundle). See `manifest/downloads.json` for sources/hashes and `docs/version-assets.md` for the cross-version inspection. The older source table below is historical and incomplete. |
| Universe site | **aceofangels.com**; before that, **flyingrockllc.com** (2000–01 magazines). Both are offline. **Restored** from the Wayback Machine on 21 Oct 2026: 2,894 archived pages, including 949 forum pages. Kept private because it copies third-party pages; rebuild it with `tools/restore_web_archive.py` ([docs/private-web-archive.md](docs/private-web-archive.md)). |
| Revival | **No public sign.** A March 2006 release was scheduled, then nothing. The domains are still renewed (to 2027), registrant hidden. |

## 3. Builds and media

**Local asset review, 20 October 2026:** the six-version manifest supersedes
the original three-build search below. Missing packages were downloaded into
`builds/asset-review/`; previously retained 2.7.1 and 2.9.2 originals were
reverified. Static extraction and comparisons live under `work/asset-review/`
and `evidence/asset-review/`. See `docs/version-assets.md` for useful recovered
geometry, older arena markers, limitations, and reproduction commands.

| What | Version | Date | Size | MD5 / SHA-256 | Where (live 2026-10-20) | Status |
|---|---|---|---|---|---|---|
| Client installer `aoa-current.exe`, from the **CD-Action 06/2002** cover CD (PL) | **v2.8.2** | file 2002-03-28; © 1997–2001 | 28,083,710 B | `96c852b07a7d55c7894dbdda624fa3db` / `9edcb5376d875188a6986067a3fd05952fb25086db0c456f01bfdfd84e840052` | https://archive.org/download/cda_20260908/CDA%2006-2002.iso/%23dema%2Face%20of%20angels%2Faoa-current.exe | **verified**; every packed file passes CRC |
| Beta v2.8.0 on FilePlanet | v2.8.0 | 2002-06-04 | ~26.6 MB | MD5 `7401dd3d2a54256e60c1bb3e5b35f752` (as listed) | https://www.fileplanet.com/56934/download/Ace-of-Angels-Beta-v2.8.0 | **not verified**: Cloudflare 403 even in headless Chromium |
| ″, Archive Team's 2012 FilePlanet rescue (ID 56934) | ″ | | | | https://archive.org/details/FileplanetFiles_50000-559999 (IDs 55000–59999, 24 GB tar) | **restricted** (401/403) |
| Client installer `aoa-current.exe`, from *Family Game Pack 3* (HU, Woodstone, MMH 269) | **v2.9.2** | file 2004-07-20; © 1997–2004 | 35,461,120 B | `ddb6a3217a0987bdf0eedef7c19767af` / `90c4a47e5df320171667209288edbe9899f957a397cb982bc459f17c785cbe38` | https://archive.org/download/family-game-pack-3-mmh-269/Family%20GamePack%203%20MMH269.iso/Games%2FAce%20of%20Angels%2Faoa-current.exe and the mirror https://archive.org/download/family_game_pack32004/family_game_pack3%282004%29.iso/Games%2FAce%20of%20Angels%2Faoa-current.exe | **verified**; both copies byte-identical |
| Trailer `ace of angels.wmv`, from the **PC Zone 118 cover DVD**, Aug 2002 (UK), "Best of E3" | – | 2002 | 2,978,383 B | `cc14e4e112e7ad64644d64fbbe51e8cc` / `b4e1fd1ad82dbceeaa1b17e278144757ee56e07db79a51c5f8df36fa8eaf399d` | kept locally, not in this repository; on archive.org only inside the 3.96 GB https://archive.org/details/dppcz-0802-dvd.-7z | **verified** (valid ASF) |
| Demo (early 2001) | ? | early 2001 | ? | – | Mega Game 03/2001 reviewed it, "downloaded from Flying Rock's site" | **not found** (not on Mega Game 02–05/2001 discs) |
| Intro video (< 3 MB) on the CD-Action 01/2003 cover CD, Bonus section | – | 2002–03 | < 3 MB | – | That CD isn't on archive.org; maybe in `cd-action-bonus-2003` (`2003.zpaq`, 866 MB) | not checked; probably the same as the trailer |
| Gamers Workshop #37 disc (BG, Apr 2002) | ? | 2002-04 | ? | – | The magazine lists Ace of Angels in its disc contents; the disc isn't on archive.org | **not found** |

`tools/fetch_known_builds.py builds/` downloads both verified builds and
checks their MD5s (tested).

### What's in the builds (inspected without running them)

- Both are Wise installers holding the full client: AOACLIENT.EXE,
  TEXTURES/SOUNDS/HUD/DATA/IMAGES/FX/SCENARIOS/SCRIPTS `.AOA` packs,
  AOAOBJECTS.ODB, MUSIC.MP3, KEYMAP.PDF, a tutorial, notes and the EULA.
- **Versions come from compiled-in globals** (`tools/aoa_version.py`). The
  bundled AOANOTES.TXT says "v2.3.0" in both builds; it was never updated.
- There is an **offline training mission**: waves of 6 enemies, with 3 AI
  wingmen you command. CD-Action's disc text says "offline mission and
  tutorial available". **Online play is dead**: the server address is
  hard-coded to 66.154.81.18 (Cyber Wurx, Atlanta colocation).
- The client contains the string "Ace of Angels is not supported on Windows
  NT", though Windows 2000 was supported (likely an NT4 check). Needs DirectX
  7; use a Windows 98/XP VM. It has not been run.
- The EULA forbids redistribution without Flying Rock's written permission.
  Linking to archive.org copies is fine; re-hosting is a separate decision.

## 4. The game and the company

- **Timeline from magazines** (`data/magazine-mentions.md`):
  - in development "since 1996", by a team of five over four years
  - previews from 2000 onward, aimed at "mid-2000", then Q1 2001, then Q1 2002
  - a demo and arena betas in 2001
  - IGF 2002 finalist, then **Technical Excellence winner** (Mar 2002)
  - Milia 2002, Cannes
  - free client downloads and cover-CD betas in 2002, "still without a
    publisher" in Nov 2002 and Oct 2003
  - "online-only, never in shops" (CD-Action, Apr 2003)
  - a new beta "expected soon" (GameStar HU, Jan 2004); v2.9.2 dates from 2004
  - **scheduled release 20 Mar 2006** (Come to Game #2, 2006); nothing after
- **Flying Rock Enterprises, L.L.C.**: Georgia company no. K822302 (previously
  1072437), administratively dissolved 26 Aug 2011 (OpenCorporates). In the
  game files: 488 Kennesaw Ave NW, Marietta GA 30060, support@aceofangels.com.
- People: Bryan G. Stephens spoke for Flying Rock in a Feb 2002 interview
  (Shacknews, quoting homelanfed.com). Founders were "Linda, Jamey, and Curt
  and me", plus Ahmed *(snippet, GameDev.net)*. Curt Hartung designed the
  flight model *(snippet)*. An artist did concept art for "Flying Rock
  Productions" in 1998–99 (Dragon Con 2007 program).
- Trademarks (USPTO and the Official Gazette):
  - ACE OF ANGELS, SN 75-840,543, reg. 2,395,790; first use 1998-10-28;
    cancelled 2007
  - ACE OF ANGELS AND DESIGN, reg. 2,486,838; expired 2008
  - FLYING ROCK ENTERPRISES, LLC, expired 2007
  - The only later filing found is a 2023 "ACE OF ANGELS" mark for clothing
    (SN 97903051); its owner wasn't checked and it is probably unrelated.

### Universe (for the lore search)

- Early 26th century, **"The Known Sphere"** (about a quarter of the Milky
  Way), **8 races and 10 nations**, each with its own culture and military
  philosophy (Worthplaying 2002).
- 40+ fighters, about 50 flagship classes, 200 players per server *(Gamepressure)*.
- 20 ships in the 2002 beta. The first arena, the Battlezone Area, ran from
  Earth to the Moon.
- Players climb from recruit to general and take part in their nation's
  politics. Downed pilots eject; if their side loses, they are taken prisoner
  and can be ransomed or escape (CD-Action 04/2003).
- Strings in the client (*verified*): ship names **Naroch, Mkulat, Vermok,
  Vasa Chovo**; "Please select a Race / Nation"; "Alliance", "Republican".
- Old-site URLs from the client:
  - `http://www.aceofangels.com/manual/manualframes.html`
  - `http://www.aceofangels.com/cgi-local/wrapit_nolinks.pl?file='players/signup.html'`
  - the menu path "Player Links → Information → General Player Rules of Conduct"

## 5. Revival evidence (RDAP and HTTP, 2026-10-20)

| Domain | Registered | Expires | DNS | Live state |
|---|---|---|---|---|
| aceofangels.com | 1998-10-21 | 2027-10-20 | GoDaddy / Domains By Proxy; NS67/68.WORLDNIC.COM | does not resolve |
| flyingrockllc.com (the site named in 2000–01 magazines) | **1998-10-21, same day** | 2027-10-20 | GoDaddy; DOMAINCONTROL; A 66.118.69.159 (CityNet) | resolves; HTTP 503/timeout from the cloud |
| flyingrock.com | 1997-09-11 | 2027-09-10 | Network Solutions; JOMAX | "Site Under Construction", Last-Modified 2021-07-02. **Not confirmed to be Flying Rock's.** |

LeadIQ (an aggregator, low weight) lists "Flying Rock Enterprises", about 2
employees, website flyingrockllc.com, LinkedIn
`linkedin.com/company/flying-rock-enterprises`.

## 6. Already searched (don't repeat)

- **archive.org disc images:** 142 items, logged in `data/disc_search.tsv`.
  74 were really searched; 64 could not be (raw `.bin`/`.img`, or images
  wrapped in RAR/7z/ZIP); 4 found something.
- **archive.org full-text search** of scanned magazines: 83 files, 29
  relevant (`data/magazine-mentions.md`). The search found nothing for
  `aceofangels.com` or `flyingrockllc` as single tokens.
- archive.org catalog under several spellings; Game Patches Archive "A"; the
  Yahoo Groups `aceofangels` WARC (restricted).
- Download portals and abandonware sites: nothing. FTP indexes (Mamont):
  nothing named `aoa-current.exe`, `aoaclient`, `aceofangels` or `flyingrock`.
- Steam, itch.io, IndieDB, ModDB, Reddit, Discord, YouTube: nothing.
- **Blocked from the cloud** (worth retrying locally):
  - web.archive.org (network policy)
  - Discmaster and Common Crawl (connection reset)
  - Arquivo.pt (403 on its index and search APIs)
  - Library of Congress web archive and archive.today (CAPTCHA)
  - FilePlanet, GameSpot and GameFAQs (Cloudflare)
- **Search noise:** "Ace of Angels" is also the K-pop group AOA. Pair the name
  with "Flying Rock" or "space".

## 7. Next steps (in order)

1. **Wayback Machine**, for the universe site and any builds it hosted:
   - `python3 -I tools/wayback_builds.py --out wb/`, then `--download`
   - read `wb/all_urls.tsv` for lore, manual, news and download pages
   - check `flyingrockllc.com` (the 2000–01 site) as well as aceofangels.com
   - by hand: https://web.archive.org/web/*/aceofangels.com*
2. **Discmaster** (https://discmaster.textfiles.com): search `aoa-current.exe`,
   `aoaclient.exe`, `flyingrockeula.txt`, `aoanotes.txt`. It indexes files
   inside archive.org's CD images, including the 64 unsearched ones.
3. **The unsearched discs** in `data/disc_search.tsv`, most promising first:
   - Joystick #134 (02/2002) and #136 (04/2002): raw `.img`
   - Czech GameStar #36–#40 (01–05/2002): `.bin`. Try the small
     `*_dic-files.zip` logs first; the `_volDesc`/`_mainInfo` text lists
     directory records. Skip the large `*_cd1.zip` files.
   - the PC Guru 2001 CD collection (`PCGURUCD`)
   - Hungarian GameStar and PC Guru 2003–04 zips
   - the CD-Action Bonus 2002/2003 `.zpaq` archives
   - The method: download, then `tools/rar_img2iso.py` or
     `7z e -so … | tools/iso_stream_extract.py`.
4. **FilePlanet in a real browser**: does the v2.8.0 file download? Check its
   MD5 against `7401dd3d…f752`.
5. **Revival follow-ups**:
   - open flyingrockllc.com in a browser
   - the LinkedIn company page
   - a USPTO search for new "ACE OF ANGELS" or "FLYING ROCK" filings
   - a Georgia Secretary of State search for a successor entity
   - an X or Facebook search for "Ace of Angels" with "Flying Rock"
6. **Every new build** gets the same treatment: `tools/wise_extract.py`, then
   `tools/aoa_version.py`, then hashes. Add a row to the table in section 3.

## 8. Tools (`tools/`, Python 3 standard library unless noted)

| Script | Does | Tested |
|---|---|---|
| `fetch_known_builds.py DIR` | Downloads and MD5-checks the verified builds | yes, both OK |
| `wise_extract.py INSTALLER [OUT]` | Lists or extracts the files in a Wise installer (PK scan, CRC check, basename-only writes) | yes, on v2.8.2 and v2.9.2 |
| `aoa_version.py AOACLIENT.EXE` | Reads the compiled-in version | yes: v2.8.2 and v2.9.2, different global addresses |
| `ia_disc_find.py ID… [--pattern RE]` | Finds files inside archive.org disc images (listing only) | yes |
| `ia_fulltext_search.py DIR` / `ia_fulltext_context.py DIR` | Full-text search of archive.org scans, then passage extraction | yes; produced `data/` |
| `iso_stream_extract.py RE OUT < image` | Pulls matching files out of an ISO stream without seeking (pipe from `7z e -so`) | yes, test ISO and the PC Zone DVD |
| `rar_img2iso.py RAR ENTRY OUT.iso` | Raw 2352-byte CD image in a RAR to ISO; needs `pip install libarchive-c` | yes, PC Zone 118 CD2 |
| `wayback_builds.py --out DIR [--download]` | Wayback CDX listing, build filter, `id_` download, hashes | parsing only (synthetic CDX); **never run against the live Wayback** |

Debian's `7zip` package can *list* RAR archives but can't decompress them;
use libarchive (`rar_img2iso.py`) or a 7-Zip build with the RAR codec.

## 9. Safety

- **Never run an installer on your own machine.** Use a throwaway Windows
  98/XP VM.
- One new, empty directory per download. Keep scripts elsewhere and run them
  with `python3 -I`.
- Pace requests to the archives: the Wayback script pauses 4 s and backs off
  on 429.

## 10. Sources

- Magazine scans: `data/magazine-mentions.md`, with links.
- French Wikipedia: https://fr.wikipedia.org/wiki/Ace_of_Angels_(jeu_vid%C3%A9o)
- Worthplaying, 17 Jan 2002: https://worthplaying.com/article/2002/1/17/news/1925-ace-of-angels-to-be-at-the-milia-2002/
- IGF 2002 winners: https://www.writerswrite.com/winners-announced-at-independent-games-3282002788
- Shacknews interview, 23 Feb 2002: https://www.shacknews.com/article/18846/ace-of-angels-interview
- GameDev.net interview: https://gamedev.net/tutorials/industry/interviews/flying-rock-enterprises-r1776
- GameSpot first look: https://www.gamespot.com/articles/first-look-ace-of-angels/1100-2833623/
- Gamepressure: https://www.gamepressure.com/games/ace-of-angels/zdaf6
- games.cz: https://games.tiscali.cz/ace-of-angels-2398
- OpenCorporates: https://opencorporates.com/companies/us_ga/K822302
- LeadIQ: https://leadiq.com/c/flying-rock-enterprises/5a1dd0fe2300005c00d9790b
- Justia, 2023 filing: https://trademarks.justia.com/979/03/ace-of-97903051.html
- RDAP: `https://rdap.verisign.com/com/v1/domain/<domain>`, then the registrar link
