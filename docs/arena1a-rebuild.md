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
| Warp rails / gates | 9 | Controller +0x18 is zero. Enabling it only reaches a child-link search for type 0x51870001; destinations and link transforms still need decoding, followed by network transit behavior. |
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
