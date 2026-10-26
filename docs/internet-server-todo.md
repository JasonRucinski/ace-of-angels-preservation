# Internet multiplayer and hosting checklist

Updated 21 October 2026. This is a proposed implementation roadmap, not a
claim that the current server is internet-ready. Check items only when their
acceptance evidence is recorded. Modernization has a separate checklist in
[modernization-todo.md](modernization-todo.md).

**Current priority (22 October 2026):** internet play with friends through a
private VPN: the `vpn-dogfight` profile and [VPN runbook](vpn-dogfight.md). It
adds sustained reliable delivery without a client patch
([findings 9.33](findings.md#933-sustained-reliable-delivery-without-a-client-patch-22-october-2026)),
rejoin after dropouts, host status/kick/ban, crash restarts and a built-in
lag/loss test mode. Verified on loopback only (`test_internet_play.py`, 8 tests,
including a 60 ms / 3% loss session). Separate-connection play is the next
acceptance step.

**Previous priority:** the user selected a smaller private-LAN dogfight milestone,
implemented by the `lan-dogfight` relay profile and
[host/client runbook](lan-dogfight.md). It keeps original-client combat, temporary
pilots, immediate respawns and score-only rounds; restarting host and clients for
reconnects is accepted. Private LAN testing is now authorized. Internet exposure
is still out of scope. The authoritative completion plan below is deferred, not
deleted or marked complete, and its client-extension gate does not block this
separate relay milestone. LAN gameplay acceptance still requires real clients.

Latest LAN implementation verification: **65 tests and eight emulators passed**
([gate](../evidence/2.9.2/local_gate_20261021_lan_dogfight.json)); a
[same-PC LAN-address smoke check](../evidence/2.9.2/lan_binding_20261021.json)
also passed. Separate-PC networking and real-client dogfight acceptance are pending.

The approved authoritative completion plan starts with the
[client-extension gate](client-extension-gate.md). An opt-in protection setter
and original-code position/input/ammunition probes are now implemented.
The gate remains open: manual checks and the other client extensions are
required before dependent transport, slot reuse or authoritative gameplay.

Earlier authoritative-prototype verification: **62 tests and eight emulators passed**
([gate](../evidence/2.9.2/local_gate_20261021_ordered_events.json)).
The new [ordered-event prototype](../evidence/2.9.2/ordered_events_20261021.json)
passes 5,273 cases, including 1,000 events, using an emulator-injected guard
before the original protection handler. Trusted session/entity context is a
fixture; application ACK transmission, real receive-loop integration and manual
client checks remain unimplemented or unverified. The live 30-event cap remains.

Previous verification: **62 tests and seven original-code emulators passed**
([gate](../evidence/2.9.2/local_gate_20261021_client_extensions.json)).
The [extension probes](../evidence/2.9.2/client_extension_gate_20261021.json)
cover the explicit setter, position correction primitive, 13 control commands,
rack count setter, health reset and protection's damage/ammunition branches.
These are isolated-code/fixture checks, not real-client authoritative gameplay.

Earlier continuation: **60 tests and six original-code emulators passed** for
the opt-in ordered combat experiment
([gate](../evidence/2.9.2/local_gate_20261021_ordered_combat.json),
[original receive filter](../evidence/2.9.2/ordered_combat_history_20261021.json)).
The combat socket test was subsequently extended to exhaust the event budget;
that test also passed separately. This is still bounded to 30 essential events
per peer and does not complete sustained delivery or spawn protection.
The [static map check](../evidence/2.9.2/ctf_geometry_20261021.json) leaves
six unresolved nodes, including both bases; collision/spawn validation is open.

Previous local verification: **56 tests and six original-code emulators
passed** after the missile relay in [findings 9.32](findings.md#932-missiles-work-hostile-relations-launch-echo-and-impact-relay-21-october-2026)
([gate](../evidence/2.9.2/local_gate_20261021_missiles.json); live run:
[missile_live_20261021.json](../evidence/2.9.2/missile_live_20261021.json)). Real-client
evidence is in [real_client_check_20261021.json](../evidence/2.9.2/real_client_check_20261021.json).
The earlier [44-test gate](../evidence/2.9.2/local_gate_20261021.json) also
recorded 36 codec comparison cases; that comparison was not re-run. See the
gate files for source hashes, scope and exclusions. This is a development checkpoint; the overall roadmap
and all release exit gates remain incomplete.

## Starting point

- [x] Local Station login, pilot selection, server listing and flight entry.
- [x] Two real clients receive each other's player-input movement state.
- [x] Explicit local spawn positioning and late-join position/velocity seeds.
- [x] Reproduced unsafe movement-decoder crash and zero-time physics NaNs addressed.
- [x] One server-spawned non-player ship visibly renders in the client.
- [x] Inventory: 17 layouts, five backdrops, one Curt3 scenario in 2.9.2;
  cross-version assets and older turret placements also investigated.

These are bounded localhost results. They do not establish combat, accurate
continuous synchronization, complete maps, capacity or internet safety.
See [findings 9.11](findings.md), [hosting assets](hosting-assets.md), and
[version comparison](version-assets.md). The present server deliberately
binds loopback; changing that address alone is not a release.

## 1. Define the first playable release — prerequisite for scope and budgets

- [x] Choose a first mode: eight-player free-for-all dogfight with `Ym Khtat`
  initially. This is the implementation target, not a playable-mode claim.
  See [first-playable-release.md](first-playable-release.md).
- [ ] Choose one layout, preferably CTF_arena or Arena1a after validating
  geometry and collision. Do not require CTF rules for the first dogfight.
- [x] Define the full match loop: connect, choose pilot/ship, spawn, fly,
  fight, die, respawn, see results, return to Station, reconnect. Proposed
  scoring/respawn rules and the acceptance scene are recorded in the release
  specification; implementation and end-to-end acceptance remain open.
- [x] Specify supported client/patches: hash-pinned 2.9.2 with versioned
  logger/physics/discovery preparation. Well-sized incompatible handshakes
  receive legacy result 8 without admission; original login code maps this
  to “Incorrect version.” The wire version does not prove patch integrity.
  See [client-setup.md](client-setup.md) and `test_network_bounds.py`.
- [ ] Define minimum and recommended client hardware, supported Windows
  versions, resolution, expected player count and hosting hardware.
- [ ] Write a short gameplay reference: units, speeds, turn rates, weapons,
  damage and win conditions. Mark reconstructed behavior versus new design.
  Recovered so far: per-shot damage for gun levels 1–10 (7–130) from the
  client's static table (`tools/gun_table.py`), plus per-system hit points
  from `.Sco` configs. Other gun fields remain unnamed. See [findings 9.25](findings.md#925-combat-protocol-survey-and-gun-table-21-october-2026).
- [x] Set a compatibility decision point: use a maintained, versioned client/
  protocol change before claiming safe slot reuse, ordered input or essential
  delivery beyond the legacy duplicate history. Required capabilities and the
  replacement-client fallback are explicit in the release specification.

**Exit gate:** an agreed one-map match specification and a reproducible test
scene, including the busiest combat situation expected in that release.

## 2. Complete the protocol and session lifecycle

- [x] First bounded step (21 October 2026): direct and reliable-wrapped arena
  handshake retries retain their assigned tag and neither postpone nor repeat
  flight initialization. A different login on an occupied endpoint is ignored;
  nested reliable envelopes cannot bypass admission. Verified with synthetic
  localhost sockets in both flight and relay modes by
  `python -I tools/test_station_stub.py` (10 tests). No real-client retry or
  internet validation yet. This does not complete general reliable-message
  deduplication, departure, expiry, slot reuse, or reconnect support below.
- [x] Second bounded step (21 October 2026): arena quit (`0x4E`) and
  configurable inactivity expiry clear admission, bootstrap, heartbeat and
  motion state; loaded observers receive a best-effort removal (`0x2D`).
  Heartbeat replies must match a recent issued timestamp and assigned slot;
  consumed replies cannot extend expiry twice. Synthetic socket tests cover
  loading cancellation, duplicate quit, invalid/replayed heartbeat traffic,
  stale movement, surviving peers and late-join absence of departed players.
  See [findings 9.12](findings.md#912-arena-departure-and-expiry-21-october-2026).
  Slots and departed endpoints remain reserved until restart (49 admissions
  per run), because reliable removal, replay-safe reconnect and slot reuse
  are not yet implemented. Station sessions and file jobs are unchanged.
- [x] Third bounded step (21 October 2026): removal now uses reliable `0x1B`
  envelopes, peer-specific `0x0F` ACKs and five bounded delivery attempts.
  An observer retires on failure or before exceeding 30 distinct removals.
  Original-client emulation verifies that the duplicate cache holds only 30
  IDs and accepts an evicted replay. Slot/endpoint reuse therefore remains
  disabled. See [findings 9.13](findings.md#913-reliable-removal-and-the-slot-reuse-limit-21-october-2026)
  for evidence, loss tests and the compatibility decision needed for reuse.
  Real clients (21 October 2026): an observer ACKed a quit-triggered removal
  in 39 ms and dropped the slot from its player table. Retries now back off
  until the peer timeout. Visible rendering was not captured ([9.23](findings.md#923-real-client-check-21-october-2026)).
- [x] Fourth bounded step (21 October 2026): original 2.9.2 receive-code
  emulation confirms actual server removal envelopes are unwrapped and
  acknowledged; five received packets produce exactly two `RemovePlayer`
  calls for slots 2 and 3. Retry and reordered duplicates are suppressed.
  The resulting ACK clears the server's pending retry. This excludes world
  destruction/rendering; real-client launch was blocked by a Windows helper
  access error. See [findings 9.14](findings.md#914-original-client-reliable-receive-path-verification-21-october-2026).
- [x] Turn the experimental flags into a documented, reproducible local
  configuration. `--profile local-relay`, validated overrides and
  `--print-config` are implemented; the default diagnostic mode remains.
  See [local-server.md](local-server.md) and `tools/test_station_runtime.py`.
- [ ] Record every required message's direction, fields, units, size bounds,
  reliability, ordering, legal state and evidence source.
  The implemented local message set and all 16 safe movement groups are now
  documented in [local-protocol.md](local-protocol.md). Combat/world-loading
  contracts and unresolved physical units still prevent completing this item.
- [ ] Implement server-to-client reliable delivery for essential spawn,
  despawn, load, inventory, team and match-state events, with bounded retries.
  Update (22 October 2026): `--sustained-delivery` replaces the 30-event
  lifetime budget with a time window over the client's 30-ID history, under
  a stated 3 s reorder-margin assumption. It delivers despawns, combat, join
  sequence, respawn, score and match text in order for a whole session.
  7,200 modelled events and a live impaired loopback session pass
  ([findings 9.33](findings.md#933-sustained-reliable-delivery-without-a-client-patch-22-october-2026)).
  Open: real-client confirmation of the wrapped join messages; inventory/team
  events; a sound proof without the margin assumption.
  Bounded continuation: `--experimental-reliable-combat` adds ordered death
  notices and missile launches/impacts to the same 30-event lifetime budget
  as removals. Synthetic loopback verifies lost ACK recovery and an impact
  waiting for its launch; 90 deterministic latency/loss scenarios cover the
  delivery queue. This is not a real-client impaired-match result. Sustained
  delivery, spawn protection and the other essential event types remain open.
- [ ] Handle duplicate handshakes and reliable messages idempotently; a retry
  must not restart flight, allocate a second entity or duplicate an award.
  Bounded step (21 October 2026): inbound `0x1B` envelopes are acknowledged
  on every copy, but a repeated sequence per channel/endpoint is dispatched
  only for the idempotent handshake. History is 64 IDs per endpoint, kept
  after departure, 512 endpoints. Unit and live Station socket tests pass.
  Older replays beyond the window are accepted, so handlers stay idempotent;
  no award/combat handlers exist yet, and the client's send-side sequence
  origin is unverified. See [findings 9.21](findings.md#921-inbound-reliable-duplicate-suppression-21-october-2026).
- [x] Track Station sessions per client. The implemented list/file-state jobs
  require a per-session correlation ID and matching source IP; alias delivery
  targets that session and rechecks it after TCP completion. Retries, quit,
  validated heartbeats, expiry and live login counts are covered. This is
  loopback diagnostic correlation, not authentication or pilot ownership;
  actual file downloads remain unimplemented. Station IDs/endpoints are not
  reused within a run (64 lifetime admissions). See
  [findings 9.16](findings.md#916-per-client-station-sessions-and-tcp-correlation-21-october-2026).
- [x] Implement explicitly limited local guests: `--profile local-guests`
  assigns unique synthetic handles and random, non-reused 32-bit tickets.
  A bound ticket cannot be taken over by another arena endpoint. Original
  request construction and live same-IP takeover/revocation tests pass.
  This is not a public account system; tickets are unencrypted legacy fields.
- [x] Bind local guest admission to Station: ticket, assigned name, source IP
  and lease must match before a player tag is allocated. Arena activity keeps
  the owning lease alive; Station quit/expiry revokes the arena admission.
  The older diagnostic/relay profiles remain explicitly unbound. Authenticated
  internet transport is still required; see [local-server.md](local-server.md).
- [ ] Allocate/release player and object slots, validate capacity and avoid
  stale packets affecting a new entity that reuses an old slot.
- [ ] Implement orderly departure, heartbeat expiry, despawn and cleanup of
  pending deliveries, motion baselines, teams, scores and file jobs.
- [ ] Define reconnect behavior, session replacement, loading timeout,
  server-full response, shutdown and return-to-Station behavior.
  Update (22 October 2026): with sustained delivery, a crashed player rejoins
  from a new endpoint (new slot and temporary pilot). A login from the IP of
  an arena player silent for 5 s or more replaces it immediately. Bounded at
  49 arena joins / 64 Station logins per run; no slot reuse.
  Static analysis (21 October 2026): server `0x3E` only marks the server
  peer dead. The client stops sending, and it also suppresses its own
  `Server Not Responding` timeout, so `0x3E` must not be used as a shutdown
  notice. Shutdown is currently socket closure, then `Server Not Responding`
  after the client's `CLIENTGRACE`: measured at 16.2 s on a real client,
  and 5.8 s with a `params.aoa` override of 4000 ms. Leaving an arena with
  Alt+Q sends `0x4E` and relaunches the client as `AoAClient.exe autologin`
  back into Station; no server message is involved. Closing the window sends
  no quit. See [findings 9.22](findings.md#922-server-hang-up-0x3e-client-grace-timers-and-shutdown-21-october-2026)
  and [9.23](findings.md#923-real-client-check-21-october-2026).
- [x] Update server-list population, mode, map and availability from actual
  arena state; remove the permanently zero arena player count. The row reports
  the configured local mode/map/backdrop and bound port; it is omitted when
  not hosted or lifetime admissions are exhausted. Station login count
  reflects active Station sessions. Verified by live TCP/UDP tests.
- [x] Separate diagnostics from normal operation: opt-in raw capture,
  redacted normal logs, rotation and bounded disk use. Default logs omit
  credentials/payloads/addresses; `--raw-capture` is private diagnostic data.
  Bounds and existing-log caveats are documented in [local-server.md](local-server.md).

**Exit gate:** repeated join/leave/rejoin and malformed/duplicate requests
cannot leak slots, create ghost ships or corrupt another player's session.

## 3. Make movement and combat authoritative

- [ ] Recover the remaining movement fields, coordinate conventions,
  orientation, angular motion, timestamps and absolute/delta rules.
  All 16 safe prefix groups now have verified byte layouts, delta precedence,
  float32 rounding and the two scaled-delta rules. Original-code emulation
  passes 300 accumulated-state cases. Unverified physical meanings/units and
  unsafe optional blocks remain open; see [local-protocol.md](local-protocol.md).
- [ ] Establish a monotonic server clock and fixed simulation step,
  independent of rendering and packet arrival; handle stalls and tick wrap.
- [ ] Determine whether the legacy client exposes usable control commands.
  If it sends only state, document the limits of server validation and the
  client/protocol changes needed for true authoritative simulation.
- [ ] Maintain server-owned ship state; reject impossible speed,
  acceleration, teleportation, illegal loadouts and non-finite values.
- [ ] Supply complete initial baselines for position, velocity, orientation,
  rotation and other delta-dependent fields when a client joins.
  Late join now seeds every observed safe float group. Unobserved delta bases
  stay unknown until an absolute sample arrives; this is not yet guaranteed
  complete initialization from an authoritative world state.
- [ ] Add sequence/order handling, absolute refreshes and recovery from
  dropped/reordered deltas. Do not let one missing packet cause lasting drift.
  Relay output is now absolute, with one-second recovery snapshots. Two
  hundred original-decoder refresh cases and a live UDP recovery test pass.
  Upstream loss/reorder/duplicate detection remains blocked on a proven
  sequence field or maintained protocol change; this item remains open.
- [ ] Implement bounded remote interpolation/extrapolation and correction.
  Test stop, turn, collision and teleport/spawn discontinuities explicitly.
- [ ] Reconcile local predicted movement with server decisions where the
  supported client permits it; tune visible correction against responsiveness.
- [ ] Fix or explicitly handle inactive/minimized-client behavior. Network
  state must not become stale merely because rendering pauses.
  Real-client check (21 October 2026): user-switched background clients
  stopped servicing UDP for 38–64 s and then drained their queue. Removal
  retries now last until the peer timeout. Cause found: the inactive-window
  timer skips the frame when the client believes it is in exclusive
  fullscreen. Client patch `background-network-v1` (prepare patch
  version 2) cut a 15 s simulated deactivation's heartbeat gap from 16.1 s
  to 1.3 s. A real focus change, minimizing and native fullscreen are still
  untested. See [findings 9.23–9.24](findings.md#924-background-client-network-stall-and-fix-21-october-2026).
- [ ] Implement ship selection and equipment definitions, energy, shields,
  hull, ammunition, cooldowns and firing validation.
- [ ] Implement authoritative projectiles/hitscan, collision, damage, kills,
  death, respawn and spawn protection; clean up all related entities.
  Live finding (21 October 2026): in the original design the **victim's
  client** computes damage from relayed fire state, then reports death with
  `0x37` (killer tag). The relay now forwards per-gun fire state, so real
  clients damage and kill each other. The server still needs scoring, death
  broadcast, respawn policy, forwarding of `0x48` (only to its target, or that
  client exits), and missiles. Victim authority is a fairness limit to weigh
  against the authoritative goal. See [findings 9.25–9.26](findings.md#926-victim-side-damage-gun-state-relay-and-death-report-21-october-2026).
  Server side (9.27): `0x37` deaths now produce `0x38` death notices for other
  players, kill and death counts, and a respawn at the assigned spawn (`0x24`).
  `0x48` is forwarded only to its validated target. Open: score display,
  match end, spawn protection, reliable `0x38`, missiles.
  Update (9.30): scoreboard (own record via `0x42`, others via `0x1F` stats)
  and kill/time match limits with an arena-text result are done and live-verified.
  Spawn protection is a client toggle (`0x81`) needing reliable delivery.
  Missiles need team definitions first (ad-hoc teams crashed the client).
  Update (9.32): missiles launch, fly and damage their target with real clients.
  Open: missile kills not yet observed, hits on non-player objects dropped,
  no rearming, best-effort (not reliable) launch/impact relay.
- [ ] Choose and test lag compensation per weapon type. Apply consistent
  limits so latency compensation cannot create unfair unlimited rewinds.
- [ ] Implement team ownership, friendly-fire policy, scores and match end.
  Scores and match end are implemented for the relay ([findings 9.30](findings.md#930-scoreboard-match-limits-and-why-missiles-need-teams-21-october-2026)).
  Teams are next: `0x50`/`0x26` team records reach `CGameRuleHdlr::AddToTeam`, but
  need definitions from scenario/game-rule setup; missile lock depends on them.
  Update (9.31): the team crash was a null team leader in `0x50`; free-for-all
  teams now work behind `--experimental-teams` and hostile targeting works.
  Missiles still do not launch: racks appear empty (loadout via custom config).
  Update (9.32): wrong diagnosis. The racks were full; every player was Friendly
  (`0x26` +0x44/+0x45 = 0). Player loads now say Hostile, and missiles work:
  server-assigned tags, `0x2A` echo to all, first `0x30` impact relayed. See
  [findings 9.32](findings.md#932-missiles-work-hostile-relations-launch-echo-and-impact-relay-21-october-2026).
- [ ] Replicate visible effects/sounds separately from authoritative results;
  a missed visual packet must not change damage or scoring.
- [ ] Add interest/range filtering after correctness is established; clients
  still need the state required for nearby combat and newly visible objects.

**Exit gate:** two players on separate machines can complete the whole match
loop with consistent hits, deaths, positions and scores under induced delay
and loss. Expanding the current raw relay is not sufficient by itself.

## 4. Turn recovered layouts into hostable maps and scenarios

- [ ] Resolve all node types, model/material references, transforms, scale,
  axes and hierarchy in the chosen layout. Validate against the original view.
- [ ] Separate arena layouts, reusable base components, asteroid fields,
  backdrops, spawn markers and gameplay objects in a map manifest.
- [ ] Load terrain/world geometry through the correct client path; listing
  a map name or spawning one ship is not equivalent to loading its world.
- [ ] Build matching server collision geometry; validate tunnels, bases,
  docking entrances, large objects and high-speed projectile/ship collision.
- [ ] Replace the fixed test-object slot with an entity registry and real
  spawn/despawn rules. Preserve stable identity throughout a match.
- [ ] Define safe player/team spawn points, orientation, boundaries, recovery
  for out-of-world ships and protections against spawn camping.
- [ ] Implement a bounded world-loading sequence with readiness acknowledgments,
  dependency order and a full late-join world snapshot.
- [ ] Decode Curt3's groups, members, objectives, spawn locations, teams,
  triggers and completion rules; label unknown fields instead of guessing.
  Teams, groups, members, orders and waypoints are parsed
  (`tools/decode_scenario.py`, [level-data.md](level-data.md)); the file
  holds no trigger/completion records, so those need the client loader.
- [ ] Load `JRMAP.TRN` (editor-saved map, 74 objects, 3 flags) in a real
  client: recover the edit-mode command names first.
- [ ] Implement required AI behavior and server ownership for mission ships,
  turrets and bots. Start with one simple deterministic behavior.
- [ ] Investigate the 80 older Arena1a turret markers; verify transforms,
  teams and intended assets before using them as placements.
- [ ] Implement CTF flag/base/capture/return/reset and victory rules as a
  separate milestone, with scoring and state verified on every client.
- [ ] Decide how unresolved/missing assets are handled: recover, replace with
  an approved asset, or remove the unsupported map from the playable list.
- [ ] Add map selection, rotation, round transitions and cleanup without
  stale objects, scores or collision from the previous map.
- [ ] Validate each remaining layout individually. Keep a matrix of visual,
  collision, spawn, mode, dependency and load/performance test results.

**Exit gate:** one complete map/mode passes a match and a map restart; only
then mark additional maps hostable. Recovered assets are not recovered rules.

## 5. Package a repeatable client and content update path

- [x] Provide a supported local setup/launcher: `prepare_client.py` composes
  stability/physics/discovery changes, checks the whole EXE and ten static
  dependencies, detects known wrapper DLLs, and records patch version 1.
  `setup_game.ps1` uses it. Mutable sound data has an explicit bounded
  exception; clean-machine/real-launch acceptance below remains open.
- [x] Preserve exact undo and detect unsupported binaries or conflicting
  wrappers/patches. Exact first-input backups, hash-checked records, atomic
  replacement and interrupted-operation recovery are tested on temporary
  copies. The user's game/original files were not altered by these tests.
- [ ] Replace the localhost discovery override with configurable Station
  host and advertised arena address; retain an explicit local-test profile.
- [x] Consolidate startup fixes: changing the Station host preserves the
  physics guard and logger fixes. Legacy hostname width is enforced at 11
  ASCII characters; arbitrary long hostnames/IPv6 are not silently truncated.
- [ ] Verify setup on a clean non-development Windows machine, including
  ActiveSkin registration, graphics wrapper, DPI, audio and permissions.
- [ ] Replace the stub's blanket “files current” response with actual content
  versions/hashes and a correct required-versus-optional dependency manifest.
- [ ] Implement safe downloads: bounded sizes, allowed paths, integrity
  verification, atomic installation, interrupted-download recovery and rollback.
- [ ] Keep downloads out of the arena simulation loop. Use a separate content
  delivery path/worker appropriate to supported clients.
- [ ] Give players useful connection, version mismatch, missing map,
  timeout and graphics/setup error messages.
- [x] Use the user's own data: preparation ships code and checksum metadata,
  with no installer, game assets or wrapper binaries. It does not download or
  execute an installer. This does not establish permission to redistribute
  game assets or third-party wrappers; those remain outside this delivery.

**Exit gate:** a tester without the repository can install, update, connect
and return to a previous working version using documented steps.

## 6. Internet transport, exposure and hosting

- [ ] Start with one dedicated host with a stable reachable address, rather
  than requiring every player to expose a home machine.
- [ ] Make bind address, advertised address, ports and Station hostname
  distinct configuration fields; reject advertising loopback for public play.
  Not needed for the VPN route: the host binds and advertises its VPN address.
- [x] Verify recovered port roles: Station UDP 5033, file/list TCP 5034,
  arena UDP 5031. Static/live evidence and separate ephemeral-port socket
  tests cover these roles; optional services only bind when configured.
- [x] Choose the initial trust model. Prefer an authenticated encrypted
  tunnel/gateway for a small private internet alpha while legacy ingress is
  being hardened. Arbitrary public clients are a later gate.
  Chosen (22 October 2026): a private VPN (Tailscale/ZeroTier/WireGuard). The
  `vpn-dogfight` profile binds only RFC1918 or `100.64.0.0/10` host addresses;
  firewall rules allow only the VPN range. See [vpn-dogfight.md](vpn-dogfight.md).
- [ ] Do not treat the legacy cipher/CRC or echoed login data as modern
  authentication. Provide authenticated transport and session integrity
  before accepting real credentials or exposing a public service.
- [ ] Choose between a compatible client-side gateway, maintained protocol
  patch, or replacement client for secure transport; verify legacy address
  checks, source-port expectations and datagram framing through it.
- [ ] For public accounts, implement secure credential storage, throttled
  login, revocable sessions and protected account administration.
- [x] Bound the implemented UDP/TCP-list channels: 512-byte wire/decoded UDP,
  per-pass decompression caps, finite safe movement fields, fixed message/
  string/slot sizes, bounded sessions/queues and pre-decode ingress budgets.
  Four thousand seeded fuzz cases, expansion bombs, 60 KiB UDP input, TCP
  truncation and live recovery tests pass. Future combat/download handlers
  require their own bounds; this does not certify public ingress security.
- [ ] Reject unauthenticated state changes, replayed session messages,
  forged player IDs and invalid transitions; limit amplification and floods.
- [ ] Configure host firewall and provider networking. If home-hosted,
  document router forwarding, NAT loopback and CGNAT alternatives.
- [ ] Test from a genuinely separate internet connection; a same-LAN test
  or public-IP hairpin test does not establish outside reachability.
- [ ] Test MTU/fragmentation limits, NAT idle expiry, endpoint changes,
  reconnects and TCP job failures on real internet links.
- [ ] Decide IPv4/IPv6 and hostname-resolution support based on tested client
  capability; add a compatible bridge where necessary.
- [ ] If evaluating relay/NAT-traversal services, verify eligibility,
  integration requirements, bandwidth costs and compatibility first.
- [ ] Run the server with least privilege as a supervised service; add clean
  startup/shutdown, health checks, restart limits and versioned deployment.
  Started: the launcher restarts a crashed host (three times per 10 minutes)
  and the status file's `updated_utc` is a health check. Not yet a Windows
  service; versioned deployment is open.
- [ ] Restrict administration separately from gameplay; provide kick/ban,
  maintenance, capacity and audit controls appropriate to the initial group.
  Started: host console `status`/`kick`/`ban`/`end` (stdin of the host
  process only), status file with per-player ping/bandwidth, and logged
  `host_kick`/`host_ban` events. Bans are per IP until restart.
- [ ] Persist necessary accounts/configuration/results; test backups and
  restoration. Do not make transient physics state a needless database load.
- [ ] Document installation, host setup, monitoring, upgrades, rollback,
  incident handling and how players report a reproducible problem.

**Exit gate:** an outside tester completes a match through the supported
connection path, with no dependency on the developer's desktop or debugger.

## 7. Performance and enjoyable-play gates — both applications

These are **proposed initial budgets**, not measured capability or guaranteed
limits. Confirm hardware and encounter load before adopting them. Optimize
the measured bottleneck; do not rewrite Python or the renderer by assumption.

| Area | Initial target / acceptance experiment |
|---|---|
| Client rendering | 1080p low/medium at 60 FPS target on named minimum hardware; p95 frame time ≤20 ms, p99 ≤33 ms during a busy match |
| Client responsiveness | Measure input-to-visible response; aim for ≤50 ms locally, with no frame-rate-dependent flight speed |
| Server simulation | Start by evaluating 20 Hz; p99 simulation work ≤25 ms of its 50 ms interval at the chosen load; compare higher rates if combat requires them |
| State delivery | Evaluate 10–20 snapshots/sec separately from simulation; tune against bandwidth and correction quality |
| First capacity | Eight real/simulated pilots; stress at 16 plus an explicitly recorded bot/projectile/object load before increasing the advertised limit |
| Internet conditions | Test 30/80/150 ms RTT, 0/1/3% loss, jitter, duplication, reordering and short interruptions; no crashes or permanent state divergence |
| Bandwidth | Measure bytes/sec per client and total server egress for idle, combat, join and content transfer; set enforced budgets from those measurements |
| Reliability | Two-hour full-match soak before private alpha; eight-hour soak before broader release; no crashes, unbounded queues or continuing memory growth |
| Session churn | At least 100 automated joins/leaves/rejoins, including during map changes; no ghost entities or depleted slots |

- [ ] Capture baselines without debugger/guard-heap overhead; repeat with
  representative graphics settings, busy scenes and clean installations.
- [ ] Instrument tick work, tick lateness, packet rates, queue depth,
  CPU, memory, bandwidth, frame-time distributions and corrections.
  Started: per-player ping, kbit/s in/out, reliable pending/expired and
  traffic totals in the host status file. Built-in test impairment
  (`--impair-*`, launcher `-Test*`) runs the RTT/loss grid on real clients.
- [ ] Profile parsing, encryption/compression, allocations, serialization,
  collision, AI and per-peer work before changing architecture.
- [x] Remove synchronous per-packet printing/file writes from the hot path;
  a bounded 1,024-record logging queue feeds a rotating worker. Overflow drops
  records without blocking networking; shutdown reports event/drop/failure
  counters. Rotation, overflow and redaction tests pass.
- [ ] Ensure file transfers and slow TCP clients cannot stall UDP simulation.
  Existing list requests now use an independent nonblocking worker with
  16-client and three-second bounds; concurrent slow-client/UDP tests pass.
  Actual file transfer and authoritative simulation are not implemented yet.
- [ ] Reduce redundant updates, use bounded delta/full snapshots and batch
  appropriate work; avoid frequent heap allocation in the simulation loop.
- [ ] Add spatial partitioning/interest management when entity counts justify
  it; benchmark collision and broadcast cost as population grows.
- [ ] Measure client CPU/GPU time, draw calls, transparent effects, HUD cost,
  texture memory, loading stalls and wrapper overhead.
- [ ] Add frame limiting, stable pacing and sensible background behavior;
  preserve responsive input without consuming unlimited idle CPU/GPU.
- [ ] Test the timestep guard across frame caps, high-refresh displays,
  long pauses and alt-tab; resolve remaining crashes with reproducible traces.
  Arena-join crash (about 1 in 6 joins) traced and fixed by client patch
  `archive-terminator-v1`: 25/25 patched joins clean ([findings 9.29](findings.md#929-arena-join-crash-unterminated-archive-text-21-october-2026)).
- [ ] Use realistic bots plus real-client tests. Packet generators alone
  cannot validate rendering, input feel or complete gameplay.
- [ ] Hold external playtests and record handling, target readability,
  hit-registration fairness, spawn fairness, audio cues and match pacing.
- [ ] Define a stop-release threshold for crashes, severe desync, stalled
  loading, unfair hits and repeated frame spikes; fix those before more art.

## Recommended execution order

1. Finish session cleanup and complete movement baselines/recovery.
2. Implement one authoritative dogfight loop on one verified map.
3. Build repeatable client installation and content/version checks.
4. Run a small private internet alpha through a protected connection path.
5. Profile, fix, and pass the client/server budgets with real testers.
6. Harden public ingress and deployment; release one supported map/mode.
7. Add CTF, Curt3/AI and further maps one validated mode at a time.

Modern UI and asset experiments can proceed separately, but should not delay
the networking/gameplay proof or alter the benchmark scene without recording it.

## Design references

Interpolation, prediction and lag compensation require an explicit latency
design; the relevant concepts are described in Valve's
[networking discussion](https://developer.valvesoftware.com/wiki/Latency_Compensating_Methods_in_Client/Server_In-game_Protocol_Design_and_Optimization).
This is a reference, not evidence that AoA implements the same protocol.

Relay services have integration and access requirements; verify those rather
than assuming a drop-in solution. See
[Steam Datagram Relay](https://partner.steamgames.com/doc/features/multiplayer/steamdatagramrelay).

Choose profiling tools that actually support the active graphics API/wrapper.
Microsoft's [PIX timing-capture guidance](https://learn.microsoft.com/en-us/windows/win32/direct3dtools/pix/articles/timing-captures/pix-timing-captures)
is a reference for measuring CPU/GPU work, not a claim of compatibility with
the current DirectX 7 client.
