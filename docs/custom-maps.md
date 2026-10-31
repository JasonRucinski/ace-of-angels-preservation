# Making new maps

Added 27 October 2026. `tools/make_map.py` turns a JSON list of placed
objects into a native 2.9.2 terrain file (`.TRN`), the same format the
in-game editor saved `JRMAP.TRN` in. The client builds it with its own
reader (`ReadInTerrain`, `0x4967E0`), so a new map needs no new client code.

The first map made this way is **Crucible** (`config/maps/crucible.json`).
The real client loaded all 100 of its objects and three safe zones. Two
navigation waypoints, which T can target, lead to a shipyard 400 km away and to
Bennu, a [new object](custom-objects.md) 776 km away
([evidence](../evidence/2.9.2/custom_map_crucible_20261027.json),
[Bennu](../evidence/2.9.2/custom_object_bennu_20261027.json)).


Like the [map viewer](map-viewer.md), this is for flying around. Nothing
here adds collision or game rules.

## Crucible

Every object is original 2.9.2 art; the placement is new. It is built along
the +z axis, which is the way ships face at the spawn:

| Area | Distance from spawn | What is there |
|---|---|---|
| Launch | 0 | Spawn inside a safe zone, between two IBCH escort carriers, with a tug below |
| The Halo | 58 km | 14 asteroids in a ring 68 km across, standing across the flight line. A +20 shield power-up sits at its centre |
| The Graveyard | 98–141 km | Seven derelict capital ships (MCVA, ZCVS, RCVS, HCVL-H, ZDD, HDD, CCVB) at tumbling angles, six debris asteroids, a missile power-up and a repair power-up |
| The Citadel | 158–184 km | Two DishWalls forming a gate with a +10 shield power-up in the gap. Behind it are `hy_base` in a safe zone, two NewDocks and an MBB and an MCVA at anchor |
| Outpost 719 | about 180 km, off to port (−x) | `base_719` with two Wall segments and a repair power-up |
| The Drift | 55–115 km either side | 22 loose asteroids that frame the arena |
| Bennu | 776 km, ahead, down and to port | A new object: NASA's Bennu asteroid scaled to 120 km, with a mining settlement on its near face. A **Bennu** waypoint leads there ([custom-objects.md](custom-objects.md)) |
| Far Yards | 405 km, ahead, up and to starboard (+x) | A shipyard far past draw distance. A ZDD destroyer sits in a slipway of eight Wall segments, with three tugs, a NewDock and two IBCH carriers, three anchor asteroids and a missile resupply. The **Far Yards** waypoint is 16 km short of it on the approach |

From the spawn, the Citadel is in view through the Halo. To reach the Far
Yards, press T until the target windows show **Far Yards**. The HUD then
marks it on screen with its distance (389k from the spawn), so you can turn
toward it and fly. At the 3,250 units/s top speed the trip takes about two
minutes. The spec was
generated once by a seeded script and then written out in full, so every
placement is listed in the JSON and can be edited by hand.

## Playing it

The client has no free map slot. The terrain hook's table of 20 maps fills
its code cave, and its only `.TRN` entry is JRMAP's `jrmap292.trn`. A custom
map therefore goes into that slot in a **separate play copy** of the client,
and your `game\2.9.2` keeps the original JRMAP. `install` refuses to write
into `game\2.9.2`.

```powershell
.venv\Scripts\python.exe -I tools\make_map.py install config\maps\crucible.json work\custom-map\client --copy-from game\2.9.2
.venv\Scripts\python.exe -I tools\make_map.py serve config\maps\crucible.json work\custom-map\client
```

The first command copies the client once (about 550 MB, without `Logs` and
`Capture Images`) and writes the map. Crucible uses the new object Bennu, so
add it to the play copy first ([custom-objects.md](custom-objects.md#using-it)).
Otherwise `install` stops on the missing name. Run it again after editing the spec.
Then launch `work\custom-map\client\AOACLIENT.EXE`, log in to `127.0.0.1` and
press Play. `serve` starts the loopback relay as map JRMAP, at the spec's
spawn, with the spec's power-up zones and waypoints (`--powerup-zones`,
`--map-waypoints`, `--sustained-delivery`). Stop any other host first.

The host control window still serves the original JRMAP from `game\2.9.2`.
Do not point it at the play copy with navigation buoys on: those come from
the original `JRMAP.TRN`.

## Writing a spec

```json
{"name": "crucible", "spawn": [0, 0, -6000], "objects": [
  {"object": "Astr-C", "name": "Halo 04", "pos": [8623, 32594, 52869], "rot": [-163.5, 33.2, -109.8]},
  {"zone": "safe", "name": "Launch Safe", "pos": [0, 0, -6000], "half": 2500},
  {"zone": "powerup", "name": "Halo Heart", "pos": [0, 2000, 52000], "half": 3000, "type": 3},
  {"nav": "Far Yards", "object": "NavMarkerBlue", "pos": [220915, 67235, 307123]}
]}
```

- `object` is any `.Sco` name in `AOAOBJECTS.ODB`. With `requirements.txt`
  installed, `install` checks the names against your copy; without it, the
  client skips a missing object. Ships, stations, asteroids and walls all
  load. Names are at most 23 characters.
- `rot` is yaw, pitch and roll in degrees, using Direct3D's order and signs.
  Positive yaw turns the nose (+z) toward +x. The file has no scale field.
- `half` is a zone's half-size: zones are cubes. Power-up types are 0
  missile, 1/2/3 shield +5/+10/+20 and 4 repair ([findings 9.44](findings.md)).
- `nav` makes a navigation waypoint with that name, at most 23 characters
  (`object` defaults to `Buoy`). There can be at most ten. The client ignores
  waypoints in the file, so the server sends them as objects (LoadObject
  kind 3, slots 90–99, the same path as the original maps' buoys in
  `navigation_buoys.py`). They need sustained delivery, which `serve` turns on.
- Units: fighters are about 100–300 units long, capital ships 6–12 km,
  asteroids 10–33 km, bases about 30 km. A fighter's top speed was 3,250
  units/s in the test.

`build SPEC OUT.trn` writes the file only. `obj SPEC EXPORT\AOAOBJECTS OUT_DIR
[TEX_DIR]` writes a preview OBJ from an [asset export](assets.md) and
reports how far the spawn is from the nearest object. Render it with
`tools/render_obj.py`.

## Format notes

Each 540-byte record copies the layout of JRMAP's editor-saved records:

- the database, object and instance names
- the rotated x axis at `+0x98` and z axis at `+0xA4`. These are the two rows
  the reader takes, and the identity is (1,0,0),(0,0,1) as in JRMAP. A test
  reproduces JRMAP's `flag3` rows from a yaw.
- the position at `+0xC4`
- the half-size, or the position x, at `+0x104`
- the power-up type at `+0x194`
- the kind at `+0x200`, with 4 at `+0x204` for kinds 0 and 2
- the `0xFADE1234` sentinel

Safe zones get the `AoAObjects.odb` / `Cube` names, as `decode_trn.convert_292`
gives JRMAP's. Power-up zones stay unnamed, like all eleven of JRMAP's. The
client drops them and the relay uses them. Waypoints are kind 3 records
with their model and name and 0 at `+0x204`, as JRMAP's buoys are. The
2.9.2 client gates kind 3 off, so it skips them and the relay sends them.
Turrets, warp gates and flags (kinds 1, 7, 8) are not written.

## Not verified

- picking up power-ups on this map (all six appear as objects in the client)
- whether a waypoint can be collided with (kind 3 is the one collidable
  non-terrain kind, [findings 9.45](findings.md); the marker is 66 units across)
- collision with the new objects
- a second player
- pitch and roll on tumbled ships compared with editor data (yaw is checked)
