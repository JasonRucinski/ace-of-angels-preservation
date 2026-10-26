# Arena1a recovery

Arena1a is selectable for inspection. **All nodes are not yet working in online
play.** Selecting its name in Station proves neither terrain collision nor
creation of its gameplay objects. No original game files were changed by this
recovery work.

## Recovered inventory

The original layout contains **383 node records**, not the previously reported
303. The old parser omitted 80 turret records because their exporter metadata
was nonempty. `scene2obj.read_nodes` now retains those records, categories,
matrices and source offsets. These are records in the root file, not proof that
every record has a top-level world transform.

| Group | Records | Current evidence / remaining work |
|---|---:|---|
| Named objects | 226 | Exact object lookup candidates have local assets; online collision unverified |
| Turret markers | 80 | Recovered records; attachment transforms, ownership, spawn and AI unresolved |
| Flag markers | 18 | Native terrain dispatch skips these; preview meshes do not implement flag rules |
| Repair/shield/missile markers | 18 | No matching local object/layout for recovered lookup candidates; definitions and behavior unresolved |
| Navigation | 10 | Native dispatch selects Buoy; online creation unverified |
| Warp rails | 9 | Native WarpGate path requires an enable flag and linked child; destinations unresolved |
| Warp targets/dummies | 9 | Link semantics unresolved |
| Groups | 8 | Hierarchy/helper semantics unresolved |
| Safe zones | 4 | Created online and drawn as blue wave cubes since patch version 18 ([findings 9.42](findings.md)); zone rules unverified |
| Nested layout | 1 | HyBase2Lay expands to 11 records: 10 meshes and one unresolved category-8 marker |

The expanded preview has 394 records and 254 placed meshes (previously 244),
68,897 vertices and 62,272 triangles, with no degenerate triangles. Existing
heuristic mesh matching remains a visualization aid, not a collision contract.
OBJ previews negate game Z. Turret coordinates must not be used for spawning
until their attachment hierarchy is recovered.

Local previews, generated from the original assets:

- [Full expanded map](../work/arena1a-review/Arena1a-expanded.png)
- [Recovered nested base](../work/arena1a-review/Arena1a-nested-base.png)
- [Per-node manifest](../work/arena1a-review/manifest.json)

## Reproduce and inspect

### Online terrain probe (22 October 2026)

The map field alone does not create online terrain. The explicit loopback
probe now sends `AR1A` in the otherwise-unused four-byte flight-entry body.
Client preparation version 6 installs `online-arena1a-v1`: after the normal
flight setup it resolves the original `Arena1a` graphics info and calls the
native terrain loader at `0x495DF0`, with the original null-parent convention.
It skips ordinary flight packets, null world/controller/assets, and an already
populated terrain list. No replacement map assets are generated.

Close the client, prepare it, and start the probe:

```powershell
.venv/Scripts/python.exe -I tools/prepare_client.py prepare game/2.9.2/AOACLIENT.EXE --station localhost
.venv/Scripts/python.exe -I tools/station_stub.py game/2.9.2/SCRTY.BIN work/arena1a-online.jsonl --profile local-relay --map Arena1a --experimental-terrain
```

Since 23 October, client patch version 11 replaces this hook with
`online-terrain-v2`, which loads any recovered map. `AR1A` still selects
Arena1a; see [viewing every map](map-viewer.md).

Launch the prepared client from its own folder and connect to `127.0.0.1`.
The LAN/VPN launcher accepts `-Map Arena1a -Terrain` for the same marker
(`--experimental-terrain` with the `lan-dogfight`/`vpn-dogfight` profiles);
every client must be prepared at version 6 or later.
`inspect_arena.py PID --objects` reports the native terrain list separately
from dynamic objects. `test_online_terrain.py` emulates the hook and checks
arguments, register/stack preservation, duplicate suppression and missing
state. Its native lookup/loader calls are stubbed: it does not prove geometry
rendering or collision. Manual visual, flight and lifecycle acceptance remains
required. Turrets, services and warp gameplay remain outside this probe.

The first manual online join with the patched client produced **239 native
terrain objects, all 239 with non-null graphics objects**, and a complete
linked list. The user confirmed that arena geometry is visible. Flight,
collision and interactive-node acceptance remain open. See
[the sanitized snapshot summary](../evidence/2.9.2/online_terrain_20261022.json).

```powershell
.venv/Scripts/python.exe -I tools/audit_arena1a.py
powershell -NoProfile -ExecutionPolicy Bypass -File tools/start_lan_dogfight.ps1 -HostAddress 192.168.0.61 -Map Arena1a -PrintConfig
```

Replace the example address with the host's assigned LAN address. Remove
`-PrintConfig` to run the host and follow [LAN client setup](lan-dogfight.md).
The Python launcher also accepts `--map Arena1a`. Default backdrop remains
`spacebkgd3`; map-specific spawn positions have not been accepted. Existing
spawn placement is unchanged. Manually inspect loading, position, surfaces
and return to Station before treating this as a playable arena.

## Evidence and blockers

- [Full regression gate](../evidence/2.9.2/local_gate_20261021_arena1a.json):
  69 tests and nine original-code emulators passed. All 17 layouts also
  exported successfully with the corrected parser. These are offline and
  synthetic checks, not real-client gameplay acceptance.
- [Pinned inventory and geometry audit](../evidence/2.9.2/arena1a_audit_20261021.json)
  records source hashes, all category counts and remaining blockers.
- [Original-code emulation](../evidence/2.9.2/arena1a_native_nodes_20261021.json)
  checks category dispatch and 32 parent-position transform cases. It does not
  execute complete object allocation, rendering, collision or online loading.
- Parser tests cover the omitted records, malformed category boundaries,
  nested expansion and transforms. Synthetic Station clients verify Arena1a
  and the selected backdrop survive admission and server-list refresh.

`CreateTerrainFromGfxInfo` at `0x495DF0` dispatches category 4 to Buoy, 7 to
Cube, 6 to WarpGate and 9 to named object/layout lookup. Categories 1, 5 and
8 skip terrain creation. Category-9 fallback recursion at `0x496279` supplies
the parent transform. Emulated row-vector position arithmetic supports the
preview's child-times-parent transform.

The external direct caller found at `0x4564FB` belongs to an offline/team setup
and hardcodes CTF_arena. The scene-switch path at `0x43C820` replaces graphics;
this is not evidence that online scene switching creates all terrain objects.
The next implementation gate is recovering the online terrain creation path
and linked-node hierarchy. Then recover warp destinations and service-zone
definitions, and turret placement/activation. Missing original definitions
remain blockers; guessed assets or rules are not substituted.

Acceptance remains pending for original-client loading, collision, all spawn
locations, navigation/safe zones, warp travel, repair/shield/rearming, turret
behavior, late join and round restart. Manual visual acceptance alone cannot
close those gameplay items.
