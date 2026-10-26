# Viewing every recovered map in the client

Added 23 October 2026. This loads any original 2.9.2 layout, or the converted
2.0.0 editor map `JRMAP`, as native terrain in a prepared 2.9.2 client
connected to the loopback relay. It is a way to look at maps. It does not
make them playable: no collision, turret, warp-gate, flag or mission
behaviour is claimed.

## Setup (once)

Close the client, then prepare it (patch version 11 added
`online-terrain-v2`; version 12 adds the panel-drag fix; version 18's
`online-terrain-v3` draws safe zones) and convert the shipped `JRMAP.TRN`:

```powershell
.venv/Scripts/python.exe -I tools/prepare_client.py prepare game/2.9.2/AOACLIENT.EXE --station localhost
.venv/Scripts/python.exe -I tools/map_viewer.py install game/2.9.2
```

`install` checks that `JRMAP.TRN` is the shipped file (SHA-256 `e3da8fbb…c5c4`)
and writes `jrmap292.trn` beside the client. Nothing is downloaded.

## Viewing a map

The [host control window](host-control.md) does all of this from one window
(pick a map, Start, Load map to switch). From the command line:

```powershell
.venv/Scripts/python.exe -I tools/map_viewer.py list
.venv/Scripts/python.exe -I tools/map_viewer.py serve CTF_arena
```

Launch the prepared client from its folder, log in to `127.0.0.1` with any
test handle, and press Play. The map is built when you enter flight.

**To switch maps, quit the client completely.** The hook loads terrain only
when the terrain list is empty, so a second map in the same session is
skipped. Press Alt+Q, close the copy the client relaunches (`autologin`),
stop the server with Ctrl+C, then `serve` the next map.

`--spawn-at X Y Z` overrides the starting point. Ships face +z at spawn.

## Maps

"Loaded" is the native terrain-object count read from a real client's memory
after flight entry (23 Oct, scratch copy of the prepared client; evidence:
[map_viewer_tour_20261023.json](../evidence/2.9.2/map_viewer_tour_20261023.json)).
Every loaded object had graphics and every list was complete. Nobody has
looked at these maps on screen yet: an in-flight screenshot comes back black,
so visual checking is up to you.

| # | Map | Kind | Spawn | Loaded | Notes |
|---:|---|---|---|---:|---|
| 0 | Arena1a | layout | origin | 239 | main arena |
| 1 | CTF_arena | layout | origin | 55 | nearest object 42 km away |
| 2 | CTF_arena_b | layout | (45396, 4633, 80000) | 60 | origin is 97 km from anything |
| 3 | newterrain | layout | origin | 234 | |
| 4 | outerchange | layout | origin | 616 | huge (millions of units); the export resolved only 7 nodes |
| 5–8 | ast_fld_a … ast_fld_d | layout | origin | 27 / 49 / 15 / 10 | asteroid fields, 15–25 km out |
| 9 | CTF_base | component | (0, 0, -12000) | 1 | |
| 10–11 | hu_base_a, hu_base_b | component | origin | 4 / 2 | |
| 12 | hy_base_test | component | origin | 2 | |
| 13 | hy_winga | component | (0, 0, -6000) | **0** | builds no terrain alone |
| 14 | HyBase2Lay | component | origin | 10 | |
| 15 | irrosa01 | component | origin | 457 | the export resolved only 2 nodes |
| 16–17 | ze_winga, ze_wingb | component | (0, 0, -3000) | **0** | build no terrain alone |
| 18 | Hittest | test layout | (0, 0, -4000) | **0** | builds no terrain alone |
| 19 | JRMAP | 2.0.0 `.TRN` | (-6000, -6000, -112000) | 23 | station segments, docked ships, wall, markers, 5 safe zones |

The native loader expands nested layouts, so outerchange, irrosa01 and
newterrain are much richer in the client than in the OBJ exports. newterrain,
outerchange, irrosa01 and hy_base_test each have an unnamed object at exactly
(0, 0, 0). If a view starts inside something, restart with `--spawn-at`.
Spawns are viewing positions, not original spawn points. Components are
pieces that bigger maps reuse, shown alone.

**JRMAP limits.** The 2.9.2 reader skips the 16 records whose object types
(`ss1`, `ss4`, `ss5`, `Dish`) no longer exist. Turrets, buoys/cubes, warp
gates and flag stations (kinds 1, 3, 7, 8) are behind controller flags in the
2.9.2 creation code and are not expected to appear. Expect walls, the
capital ships and five safe zones (kind 2; before 25 Oct 2026 `install`
left their names empty and the client dropped them, so re-run it).

**Safe zones** (since patch version 18): Arena1a, newterrain, outerchange,
irrosa01, hy_base_test, CTF_arena_b and JRMAP have them. They draw as
translucent blue wave cubes; on all but CTF_arena_b and JRMAP you spawn
inside one, so the whole view is tinted blue until you fly out. See
[findings 9.42](findings.md) for the list and sizes.

**TestScene** (2.0.0) cannot be loaded this way: the 2.9.2 object database
does not contain it, and its format differs.

## How it works

### Unfilled-node investigation (26 October 2026)

The export resolver now follows the original graphics lookup's first,
case-insensitive prefix match, preserving archive order from `_export.json`.
`HyBase2La0` resolves to `HyBase2Lay`; `outerchange`'s five `ast_fld_10`
through `ast_fld_14` references resolve to `ast_fld_d`, the first matching
layout in the archive. Without archive provenance, ambiguous prefixes are
left unresolved. Object lookup takes precedence over layout lookup.

This restores **60 geometry instances in outerchange and 10 in irrosa01**
to expanded exports. The former now has 615 resolved object records plus
one safe zone; the latter has 456 plus one safe zone. These agree with the
previous live counts of 616 and 457. The original client already resolves
these references; this change fixes the analysis/export tools, not gameplay.

`tools/audit_map_nodes.py` inventories all 17 node-layout Gobs and writes
[counts and remaining node classes](../evidence/2.9.2/map_nodes_20261026.json).
Full records and regenerated OBJ files are local under `work/map-node-review/`.
Object assets being available does not mean they spawn: ship-only components
still depend on native controller flags. Turret/flag gameplay, service-marker
definitions, warp links and helper semantics remain unimplemented or unverified.
Helper classifications are based on names, not proof of their original behavior.

Verification: all 337 archive entries passed CRC checks; six node tests pass,
including executing the original prefix-comparison routine in x86 emulation
with CRT string/uppercase calls stubbed. No live-client changes were made.

### Loader

- Client: `online-terrain-v3` (`tools/online_terrain.py`) hooks the
  flight-entry handler at `0x4306AF`. The server's four-byte 0x2C body
  selects the map: `AR1A` means Arena1a, kept for v1-prepared clients;
  `MAP` plus an index byte selects any entry of the 20-entry table in the
  cave (`0x58B8C0`; `0x58B8A0` before v3). Layouts go through the native lookup `0x4CDD30` and
  loader `0x495DF0`. `JRMAP` goes through the native `.TRN` reader
  `ReadInTerrain` (`0x4967E0`). Unknown markers, out-of-range indexes,
  missing world state and an existing terrain list all leave the client
  unchanged. After a load, v3 hands each safe zone to the flight view's
  zone-visual list (`0x43E030`), which `SetupFlightMode` had already
  walked while the map was still empty.
- File map: 2.9.2 reads 540-byte records; the 2.0.0 file has 512-byte
  records. `decode_trn.convert_292` inserts the two gaps that move position,
  scale, kind and the sentinel to their 2.9.2 offsets (see
  [level-data.md](level-data.md) and the `decode_trn.py` notes).
- Server: `--map` accepts every table name; with `--experimental-terrain` it
  sends that map's marker and moves relay spawns to the map's viewing spawn.
- Tests: `test_online_terrain.py` executes the hook in x86 emulation for all
  20 entries and for rejected markers, and checks the v1 → v2 upgrade. The
  native lookup, loader and reader are stubbed in emulation.
