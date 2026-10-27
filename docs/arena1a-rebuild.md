# Arena1a in-game rebuild investigation — 26 October 2026

The live client has the ordinary scenery. The missing work is mainly gameplay
objects and systems. No restoration patch was applied during this investigation.

## Navigation-buoy restoration experiment

The server now supports `--arena1a-buoys <original Arena1a.Gob>`. It reads and
hash-checks the user's layout, selects the ten category-4 placements, and sends
native `Buoy` objects with kind 3 and neutral relations after flight entry.
It requires `--map Arena1a --experimental-terrain --sustained-delivery`.
Every joining player gets the same names, positions and tags; retries use the
existing ordered delivery and the client's duplicate-tag protection.

Slots 90–99 are reserved while enabled; target ships are limited to 88 so they
cannot collide with the buoys, and power-ups/missiles retain their existing slots.
The original archives and executable are not modified. The current LoadObject
path initializes rotation to zero, so **editor rotations are not yet restored**.
This restores navigation-object placements, not turret/flag/warp gameplay.

Example, with a prepared client and previously exported original assets:

```powershell
.venv/Scripts/python.exe -I tools/station_stub.py game/2.9.2/SCRTY.BIN work/buoy-host.jsonl --profile local-relay --map Arena1a --experimental-terrain --sustained-delivery --arena1a-buoys work/2.9.2/export/AOAOBJECTS/Arena1a.Gob
```

Stop any other local host first. The host window now uses the generalized
all-map option below when the exported assets are available.
`test_navigation_buoys.py` verifies original data, configuration
guards and first/late-join delivery with a deliberately lost acknowledgment.
`verify_navigation_buoys.py <PID> <Arena1a.Gob> <report.json>` checks all ten
live names, tags, kinds, positions, graphics pointers and visibility/collision
flags, plus the unchanged 239-terrain/four-safe-zone baseline. Flag checks do
not substitute for looking at the rendered model or testing collision behavior.

### All-map navigation support

Use `--navigation-buoys work/2.9.2/export/AOAOBJECTS` in place of the legacy
`--arena1a-buoys` argument to follow `--map`. Original Gobs, object configurations
and archive ordering are validated before any network socket opens. Nested
placements use their parent transforms; repeated labels retain distinct tags.
JRMAP reads the original `JRMAP.TRN` beside the server key (override with
`--buoy-trn`), preserving its three Buoy and four Cube navigation objects.

| Map | Navigation objects |
|---|---:|
| Arena1a | 10 |
| CTF_arena | 1 |
| newterrain | 10 |
| outerchange | 6 |
| hu_base_a | 1 |
| hu_base_b | 1 |
| irrosa01 | 5 |
| JRMAP | 7 |
| Other twelve selections | 0 |

Total: 41 placements across eight map selections (some reuse base components).
The host-control window enables this automatically for terrain when
`work/2.9.2/export/AOAOBJECTS` and its export manifest exist. Restart the host
window to pick up the change; switching maps still requires clients to quit and
rejoin. No Linux deployment was changed.

Validation covers all 20 selections, nested world positions, original JRMAP
model choices, and reliable first/late-join delivery for Arena1a, outerchange,
JRMAP and a zero-buoy map. **Live in-game visual acceptance remains pending**;
the initial Arena1a client never entered the restoration test session. Editor
rotations remain zero in LoadObject and are not claimed restored.
Counts: [all-map evidence](../evidence/2.9.2/navigation_buoys_all_maps_20261026.json).

## Turret-group recovery — 26 October 2026

`audit_turret_groups.py` now decodes the original Arena1a parent links. All
80 turret markers are direct children of the 18 flag markers: eight groups
contain five turrets and ten contain four. Flags themselves are children of
navigation markers. The first recovered chain is `NavRing2` → `Flag ND1-C`
→ `Turret ND-`, `Turret ND0`, `Turret ND1`, `Turret ND2`, `Turret ND3`.

The previous flat inventory's turret positions are **local**, not world
coordinates. Relative to the end of the tagged node name, animation format
`0x8237 / 0x10003` stores the parent ID at +0x24 and, for the one-key records
in this map, the node ID at +0xF4. The saved matrix at +0xF8 is also local.
The original animation writer at `0x5490C0` confirms parent-ID serialization.
Executing the original recursive world-transform routine at `0x542C80`
validated all 383 root-layout matrices against the recovered hierarchy;
maximum absolute matrix-element difference was 0.04825, from float precision.
No shared scene-export behavior has been changed by this research tool.

There are two distinct placement paths: terrain/network-created turret
objects and turret attachment points embedded in an object's graphics.
`EnumerateTurrets` at `0x4A4650` finds graphics entries with type `0x11` and
attaches the same `gen_turret.scr` / turret AI constructor (`0x4E8DB0`) used
by standalone turrets. Network LoadObject **kind 1** selects that AI branch;
the world object's later type `0xB` is not the packet kind. This establishes
shared AI machinery, not identical ownership or attack rules. Station/base
turrets attacking every player cannot be inferred from their model alone.

`turret_groups.py` encodes native `0x70` status packets: enabled DWORD,
50 object tags, then a 32-byte team name. The `0x4AFD20` receiver stops at a
zero tag or 50 entries. Original-code tests with no receiver stubs verify
that disabling groups of 0, 1, 5 and 50 changes exactly the referenced
objects' +0x1DC field. Packet bounds and explicit-team requirements are
tested. Enabling/team assignment is not yet emulation-verified.

Per-marker model choice, initial team/capture rules, orientation delivery,
authoritative firing and synchronized damage remain unresolved. Full
transforms are in ignored local reports; the
[committed evidence](../evidence/2.9.2/turret_groups_20261026.json) contains
group names/counts and verification results.

### Inactive five-turret placement trial

`--turret-trial <AOAOBJECTS export directory>` now loads the five markers
under `Flag ND1-C` at their composed world positions. It validates the original
asset hashes and requires Arena1a, terrain, relay and sustained delivery.
Slots 80–84 are reserved, limiting practice targets to 78; navigation buoys
retain slots 90–99. Each first/late join receives a neutral native kind-1
LoadObject followed by a disable message for that turret. Host control does
not enable this experiment automatically.

**This is a placement prototype, not restored turret gameplay.** `TurretA` is
the model used by the original client's debug-spawn command, chosen here
provisionally because a per-marker model assignment has not been recovered.
Original orientation is not sent yet. Flags, capture, ownership, damage and
respawn are not implemented. The original generic script was extracted with
all eight SCRIPTS.AOA entries passing CRC; its parameters do not specify these
map markers' model assignments.

The native AI gate at `0x4E9261` requires activation -1; zero reaches its
skip branch at `0x4E9720`. Original-code probes cover that disabled path,
the enabled path with a target, and the separate world-flag gate. Socket tests
verify load/disable ordering for first and late joiners with ten navigation
buoys present and a deliberately lost ACK. **Live memory/visual acceptance
is still pending**, and this experiment has not been deployed to Linux.

Local profiles now accept IPv4 loopback addresses throughout 127/8, allowing
the trial to bind 127.0.0.2 while the regular host uses 127.0.0.1. Wildcard
and LAN addresses remain rejected for these profiles.

```powershell
.venv/Scripts/python.exe -I tools/station_stub.py game/2.9.2/SCRTY.BIN work/turret-host.jsonl --profile local-relay --bind-address 127.0.0.2 --advertised-address 127.0.0.2 --map Arena1a --experimental-terrain --sustained-delivery --navigation-buoys work/2.9.2/export/AOAOBJECTS --turret-trial work/2.9.2/export/AOAOBJECTS --target-ships 0 --spawn-at 145041 -29123 100278 --seconds 1800
```

Connect the prepared client to Station IP 127.0.0.2. Once flying,
`verify_turret_trial.py <PID> <export-directory> <output.json>` checks the
five names/tags, native kind, positions, graphics, visibility, AI pointers,
disabled activation and unchanged terrain count. These are memory checks;
they do not replace rendered-model or gameplay inspection.

The isolated client connected to Station 127.0.0.2 as disposable pilot `test`,
but has not entered the arena. The UI tool can read the lobby; screenshot
capture times out and clicking Play fails with "coordinate input geometry is
unavailable", including after window recovery. Host status confirms one Station
session and zero arena joins. This is a UI automation limitation, not an
authentication restriction or evidence of a turret-loading failure. Live
acceptance remains pending until Play enters flight.

## Warp gate recovery — 26 October 2026

Flags/control points are deferred at the user's request. All nine category-6
Arena1a warp markers have one direct child supplying a destination. Five are
named WarpTgt and four are named Dummy; those four are functional destination
helpers, not missing decorative objects. These gates move the local ship within
the current map. No destination gate pairing is required by the recovered path.

| Gate marker | Destination child |
|---|---|
| Rail_Hy1 HyBase1_Rail | WarpTgt01 |
| Rail_Hy2 HyBase2_Rail | WarpTgt02 |
| Rail_Home1 Home_Rail | WarpTgt03 |
| Rail_Home2 Home_Rail | WarpTgt04 |
| Rail_Hy_k1 Rail_Hy1a | Dummy04 |
| Rail_Hy_J1 Rail_SSa | Dummy01 |
| Rail_Hy_J2 Rail_SSb | Dummy02 |
| Rail_Hy_J3 RailSSc | Dummy03 |
| Rail_Hy_k2 Rail_Hy1b | WarpTgt05 |

The native layout path at `0x4962F7` checks controller +0x18, searches its
child table for type `0x51870001`, and calls the original world-position getter
`0x542C40`. It selects object **WarpGate**, terrain kind **7**, with the child
world position in the creation parameters at +0x34. WarpGate.Sco selects
**WarpA.Gob**; both exported files match the original archive hashes. Unlike
the provisional turret model choice, this model assignment comes from the
native layout path and original configuration.

Offline execution against reconstructed parent/child structures verified all
nine destinations (maximum difference from Python matrix composition: 0.054
game units). Four negative probes confirmed that a disabled controller, missing
child, wrong child type or null child skips creation. The probes stop before
allocation; this does not prove that rendered gates have spawned.

The original LoadObject sender writes kind 7 and destination float3 at packet
+0x9E (`0x48A6C5..0x48A718`). The receiver's kind-7 dispatch copies those fields
to object +0x70/+0x74/+0x78 (`0x4A6A6D`). All nine destinations passed these
native sender/receiver field probes. Packet opcode is 0x25, body length 191.

Kind 7 is collidable and dispatches to `CollideWithNodeWarp` at `0x4B5060`.
The caller only enters this path for the local player while the collision
handler's busy flag is clear. Three branch probes verified those conditions.
The transit routine sets both current and target positions to:

```text
destination + velocity / max(speed, 100) * 1000
```

Velocity is preserved. At speed 100 or above the exit offset is 1,000 units
along travel; below that it is shorter, and a stationary ship lands exactly
at the destination. Six native probes cover zero, axial, diagonal and slow
velocity. They stop before sound and network calls. Trigger geometry, rendered
orientation and re-entry behavior still need live testing.

The current relay accepts finite absolute position changes without a gate-aware
distance check. Nine synthetic tests passed each recovered destination through
the movement filter, state update and observer snapshot codecs. This supports
an isolated trial, but does not establish host-authorized transit or real
two-client synchronization.

The investigation itself enables no gates. The opt-in trial below implements
`Rail_Hy1 HyBase1_Rail` → `WarpTgt01`, using the native model and destination
fields. Verify its placement/orientation, collision entry, exit, observer view,
late join and cleanup before enabling all nine. The flag and turret work remain
independent.

Reproduce with:

```powershell
.venv/Scripts/python.exe -I tools/audit_warp_gates.py --local-report work/warp-research/routes.json
```

The audit pins the original client and map hashes. Full coordinates remain in
the ignored local report; names, checks and limitations are recorded in
[warp evidence](../evidence/2.9.2/warp_gates_20261026.json).

## Single-gate local trial

`--warp-trial EXPORT_DIR` restores only **HyBase1_Rail → WarpTgt01**. It
validates the original exported asset inventory and map, emits one native
kind-7 LoadObject with the recovered destination, and reserves dynamic slot 85
(tag `0x40010055`). The native model assignment is WarpGate / WarpA. The display
label uses the layout's second token, as the original layout path does.

The option requires a local relay/guest profile, Arena1a terrain and sustained
ordered delivery. It rejects target-ship counts above 83, so passive targets
cannot occupy the gate slot. The gate loads after buoys and optional turrets,
for each first or late joiner. Host-control does not enable it automatically.

Four focused tests pass: configuration/packet fields, original-client kind-7
destination receipt, first/late socket joins with ten buoys and five disabled
turrets (including a lost gate ACK and observed retransmission), and live
verifier rejection cases. The four navigation tests and seven runtime tests
also passed; the POSIX-specific runtime shutdown test is skipped on Windows.
The standard-library-only host configuration entry point still works.

**Live acceptance is pending.** The isolated host was started at 127.0.0.2
and the existing prepared client opened. The UI tool cannot capture the pilot
dialog (`window capture timed out`) and its editable-field action fails
(`Cannot set a value for an element that is not settable`). Manual flight
entry was requested for this technical limitation. No live gate spawn or
transit is claimed yet.

Editor orientation is not restored by this LoadObject trial. The original
client performs local collision transit; the rebuilt host does not authorize
gate crossings. Visual geometry/orientation, actual collision entry/exit,
observer synchronization and map cleanup require live checks.

```powershell
.venv/Scripts/python.exe -I tools/station_stub.py game/2.9.2/SCRTY.BIN work/warp-research/host.jsonl --profile local-relay --bind-address 127.0.0.2 --advertised-address 127.0.0.2 --map Arena1a --experimental-terrain --sustained-delivery --navigation-buoys work/2.9.2/export/AOAOBJECTS --warp-trial work/2.9.2/export/AOAOBJECTS --target-ships 0 --spawn-at 19018.6543 0 -3742.1543 --status-file work/warp-research/status.json --seconds 1800
```

Connect the prepared client to Station IP 127.0.0.2, select Local Relay and
press Play. The spawn is 6,000 units behind the gate along +Z. Once flying:

```powershell
.venv/Scripts/python.exe -I tools/verify_warp_trial.py <PID> work/2.9.2/export/AOAOBJECTS work/warp-research/live-verification.json
```

The verifier checks one matching gate, kind, name, position, destination,
graphics/visibility/collision flags and the unchanged 239-object terrain
baseline. It rejects a lobby snapshot or non-finite coordinates. Passing it
is memory acceptance, not proof of rendered appearance or successful travel.

## Headless warp validation

The user deferred manual playtesting. The trial can now be checked without
opening the game UI:

```powershell
.venv/Scripts/python.exe -I tools/test_warp_headless.py --report evidence/2.9.2/warp_headless_20261026.json
```

All three tests passed. `emulate_warp_trial.py` executes the complete original
LoadObject receiver (`0x4A66A0`) through its return, including the native name,
position, kind, relation and destination handling. Three duplicate loads take
the original already-present-object path: one allocation and one model request.
Allocation, model loading, scene registration, AI cleanup, team services, event
queue availability and two CRT calls are explicit fixture substitutes. This
does not claim that the real renderer loaded the model.

The original overlap/dispatch path (`0x4B3013` onward) and transit routine run
against supplied render positions and sphere radii. Eight cases check outside,
exact boundary, inside, center, nonlocal player, busy handler, hidden gate and
disabled collision. Six velocities check stationary, axial, diagonal and slow
transit. Velocity remains unchanged; checking overlap again at the remote exit
does not retrigger the same gate. These fixtures use radii 10 and 100, not
recovered ship/gate model bounds. Sound and outgoing game calls are not run.

The socket test starts the actual host on temporary loopback ports. Its gate
packet is consumed by the original receiver in the emulator. A synthetic pilot
then enters the emulated overlap path, and the test uploads the resulting
native-computed position and preserved velocity through the existing movement
format. The host's output movement prefix is decoded with the original
`0x495330` routine. Four synthetic peer connections verify:

- A connected observer receives the warped position and preserved velocity.
- Dropping the first post-warp update recovers on the host's periodic refresh,
  without requiring a second pilot upload.
- A late join receives the post-warp position in LoadPlayer and the movement
  seed, plus the same gate.
- A reconnecting observer receives one gate and the current pilot state.

The tests clean up their temporary hosts and sockets. They do not change the
regular host or require a running client. Results and fixture boundaries are
recorded in [headless evidence](../evidence/2.9.2/warp_headless_20261026.json).

Remaining acceptance is specifically the real model's orientation/bounds,
full game-loop collision entry, actual clients on two PCs and map-change
cleanup. The rebuilt host still trusts client movement rather than authorizing
gate transit. Manual testing is deferred, not needed to run these checks.

## Live baseline

The user entered Arena1a through the local host. Read-only process inspection
found 239 terrain objects: **235 static placements matched by name and position**
(within two game units) and four kind-2 safe-zone placeholders. The safe-zone
handler independently contained four zones. All 235 static objects have their
collidable byte set; this does not prove every collision shape is correct.

The dynamic world list contained Mentor, host practice targets, and subsequently
missiles, not the map's turrets or flags. Those practice objects are not evidence
that the map's original gameplay nodes were restored.

## What is missing

| Records | Count | Cause / remaining work |
|---|---:|---|
| Turrets | 80 | Layout category 1 is skipped outright. Models/configurations exist, but per-marker turret type, mounting/hierarchy, ownership, target selection, firing and synchronized destruction need recovery. |
| Flags / control-point markers | 18 | Category 5 is skipped. Flag assets exist; exact mode semantics, teams, ownership, capture logic and turret-group links remain unresolved. These are not automatically 18 CTF flags. |
| Navigation markers | 10 | Layout requests Buoy, but kind-3 creation is gated off. Native NavC model exists. This is the smallest useful first restoration experiment. |
| Warp rails / gates | 9 | Destination children, world transforms, native model and transit math recovered offline. Controller +0x18 is zero; rendering, collision entry and multiplayer transit still need an isolated live trial. |
| Service markers | 19 | Names suggest six repair, six shield and seven missile stations/zones. Eighteen are unresolved category-9 names; the nested base has one category-8 ZAMissile1, which is skipped. Original volumes, rates, types and ownership rules are not established. |
| Cube Home | 1 | Named category-9 node is absent from both terrain and dynamic lists. Its intended role needs confirmation; it must not be silently replaced with a decorative cube. |

There are also **17 group/link helper records** and **one nested-layout reference**.
These are structural records, not 18 missing visible objects. The accounting is
exact: 235 static + 4 zones + 136 gameplay markers + Cube Home + 17 helpers +
1 layout reference = **394 expanded records** (383 in the root map).

## Why a single switch is insufficient

The live terrain controller bytes +4, +5 and +0x18 were all zero. Original-code
emulation independently confirmed 21 cases:

- AddTerrainObject's turret, buoy, warp and flag branches reject creation with
  both controller flags clear and no explicit override; each of the three
  enabling inputs reaches world-object allocation.
- The layout warp gate requires +0x18 before even looking for its child link.
- Layout categories 1, 5 and 8 go straight to the skip branch regardless of
  those creation gates.

The probes stop before allocation. They prove control flow, not functioning AI,
rendering, damage or replication. Broadly enabling server/controller flags in
every client could create duplicate or independently simulated world objects.

## Rebuild order

1. Restore the ten navigation markers in an isolated client/server experiment.
   Verify positions, labels, lifecycle and a second client's view.
2. Decode turret/flag parent and attachment links. Restore one linked group,
   prove mounting and ownership, then expand to all 80 turrets / 18 flags.
3. Decode and verify one warp connection before enabling all nine.
4. Define and test the service zones, preserving the distinction between
   recovered fields and reconstruction choices.
5. Verify safe-zone rules, collision, late joins, destruction/respawn and map
   changes with two clients before applying the approach to other maps.

## Reproduction and evidence

`tools/audit_arena1a_rebuild.py` executes the pinned original-code probes.
Pass `--pid <PID>` while a client is flying Arena1a to capture and reconcile its
live inventory, or `--snapshot <file>` to check a previously captured snapshot.
Full local coordinates are in ignored `work/arena1a-game-trial/live-snapshot.json`.
Committed [evidence](../evidence/2.9.2/arena1a_rebuild_20261026.json) contains counts,
gate results and the reconciliation. The test client was a copy prepared at
patch version 19; the original client and deployed Linux host were not modified.

During setup, a duplicate local host caused error 10048; the investigation host
was stopped. The UI launcher then used the Codex app directory as the client's
working directory, causing connection timeouts. Relaunching with the game
directory explicitly set resolved the timeout and the user entered flight.
