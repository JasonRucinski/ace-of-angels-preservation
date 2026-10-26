# Level, scenario and mission data in the recovered clients

Checked 22 October 2026 across the five complete installers (2.0.0, 2.7.1,
2.8.0, 2.8.2, 2.9.2) and the 2.3.1 replacement client. Static inspection
only: no client was run for this audit, and nothing below has been loaded
in-game yet.

```powershell
.venv/Scripts/python.exe -I tools/audit_level_data.py
```

That writes full decodes (with coordinates) to the ignored
`work/asset-review/level-data/` and a coordinate-free summary to
`evidence/asset-review/level-data.json`. The decoders are
`tools/decode_trn.py`, `tools/decode_scenario.py` and
`tools/decode_legacy_layout.py`.

## Result

Three pieces of level data were in the downloads but not yet read:

| Data | Where | What it is | State |
|---|---|---|---|
| `JRMAP.TRN` | Loose file in all five installers, byte-identical (SHA-256 `e3da8fbb…c5c4`) | A world map saved by the in-game editor: 74 placed objects and 13 turret→flag links | **New.** Fully decoded; not yet loaded in a client |
| `Curt3` | `SCENARIOS.AOA`, 2.8.0–2.9.2, identical | The offline "ZCVS carrier group" mission: 2 teams, 5 AI groups, orders and 13 waypoints | **Structure decoded** (was "not decoded"); some fields still unnamed |
| `TestScene.Gob` | 2.0.0 `AOAOBJECTS.ODB` only | An early arena layout: 178 nodes | **Node list decoded** (was "format not reconstructed"); hierarchy not decoded |

No other scenario, mission or map was found. The places checked and ruled
out are listed at the end.

## 1. `JRMAP.TRN`: an editor-built world map

`JRMAP.TRN` is not encrypted or compressed, and `tools/inventory.py` listed it
without reading it. Its format matches the 2.0.0 client's
`CTerrainObjectHandler::ReadInTerrain` (`0x46F600`):

- a u32 count, then that many 512-byte records, each checked for the
  sentinel `0xFADE1234` at +0x1FC;
- then 48-byte (turret name, flag name) pairs until end of file.

4 + 74 × 512 + 13 × 48 = 38,516 bytes, the exact file size. Each record
holds the database name (`AoAObjects.odb`), the ODB object, an instance
name, a 3×3 rotation, a position and a kind field. The records are raw
struct dumps: stale pointers and MSVC debug fill (`0xCDCDCDCD`) survive in
unused fields.

What the map contains:

- **Three flag stations** (`flag1`, `flag2`, `flag3`) and **13 turrets**
  linked to them: `Perimeter 1–4` and `Close 1–3` guard `flag3`;
  `Turret 1A–1C` guard `flag1`; `Turret 2A–2C` guard `flag2`.
- A **station** built from `Wall` and `Dish` segments (`Station1Seg1–5`,
  `Internal 3`, a `flagcage`), with the `flag3` station inside it.
- **Six warp gates**: `Station Warp`, `Warp Far`, `Far1`, `Warp0`, `Warp1`
  and one named `Curt`.
- **Docks and capital ships**: three `IBCH` at `Dock1Ship1–3`, an `MBB`
  `DryDockShip1` beside four `ss5` segments, and a second group of
  `Dish`/`Wall`/`MBB`/`MCVA`.
- **Markers**: buoys `Dock 1`, `bryan1` and `Valinor` (the last at
  x = 5,000,000), cubes `AoA Safe` and `Flag 2 Safe`, five kind-2 safe
  zones (half-size 2,000–5,000 at `+0x104`) and 11 kind-6 power-up zones
  (type at `+0x194`; [findings 9.44](findings.md)).

Kind values seen: 0 static model, 1 turret, 2 safe zone (from 2.9.2's
`AddTerrainObject`, [findings 9.42](findings.md)), 6 power-up zone (same
function, [9.44](findings.md)), 3 cube/buoy, 7 warp gate, 8 flag station;
labels other than 2 and 6 are inferred.
The turret records carry a second value of 3, 4 or 5, which may be the
gun/turn setting in the 2.0.0 log line `Loading turret [%s] gun[%d] turn[%d]`.

**Object availability.** `Wall`, `MBB`, `MCVA`, `IBCH`, `Cube`, `Buoy`,
`Station`, `TurretA` and `WarpGate` have `.Sco` configs in every version,
including 2.9.2. `ss1`, `ss4`, `ss5` and `Dish` (16 records) exist in no
surviving object database; 2.0.0's `Section1`, `Section4` and `Dish1` Gobs
are the nearest candidates, unconfirmed.

**How the client loads it.** In 2.0.0 the reader is reached from a chat
command handler that also holds `you are in edit mode`,
`edit mode not allowed -management`, `Loading terrain object [%s]`,
`Reading terrain map from file [%s]` and `Terrain written to [%s]`; the
terrain handler also names `temp.trn`. Edit mode is refused unless a
world flag is set or a player-record value at +0x97 is above 1
(`0x47D3C5`–`0x47D3DC`), which the message calls management. 2.9.2 keeps the same machinery: the read-map handler is case 6 of
the 94-case command switch at `0x4A9A47`, which calls the reader at
`0x4967E0`. The typed command names were not found as plain strings, so
how to issue the command is still unknown.

## 2. `Curt3`: the offline prototype mission

The file is a stream of integers and tagged strings (u32 `0x05765768`,
u32 length, bytes, NUL). `tools/decode_scenario.py` applies one fixed
grammar and must end on the last byte, which it does for the 2.8.0, 2.8.2
and 2.9.2 copies. Field names come from the contents; the client's loader
(`AoA_MissionData.cpp`, `CScenarioHdlr`) has not been traced, so numeric
fields without an obvious meaning are kept raw.

- **Teams:** `Defense` and `Offense`, each with one relation to the other.
- **Groups** (all role `Air Superiority`):

| Group | Team | Ships | Orders | Waypoints |
|---|---|---|---|---|
| Attackers | Offense | 1 `ZCVS` "Zethi Enforcer" | Attack `EDefenders` (100) | Idle At, Patrol To, Patrol To |
| Defenders | Defense | 1 `ZCVS` "Zethi Defector" | none | Idle At, Escort To |
| EDefenders | Defense | none listed | Defend `Defenders` (50) | Idle At, Patrol To, Patrol To |
| EAttackers | Offense | none listed | none | Idle At, Patrol To, Patrol To |
| Attack Escort | (blank) | 6 `Zkole`, `Zkole1–6` | none | Idle At, Patrol To, Patrol To |

Each waypoint holds an action, a target name (always blank here), integer
x/y/z, a radius-like value (20–10,000) and a 0/1 flag; the flag is 1 on every
group's last waypoint (and on both of Defenders'). Several groups end at the same point (y 83465,
z 50440), the likely rendezvous.

This matches the briefing compiled into 2.8.2 and 2.9.2, under
`Loading offline prototype mission (work in progress)...`: the ZCVS carrier
group is leaving with a seized prototype fighter; the player meets an escort
wing at `NavMarkerBlue`, then intercepts the carrier group and destroys its
escort fighters. The six-Zkole escort is
the "waves of 6 enemies" in CONTEXT.md. The objective texts are
placeholders ("Test Killing", "this is a test of Killing …"). No trigger or
win-condition records exist in the file; those must live in client code.
`ZCVS.Sco`/`Zcvs.Gob` exist from 2.8.0 on and `Zkole` from 2.0.0, so every
client that ships Curt3 also has its ships.

## 3. `TestScene.Gob` (2.0.0): an early arena layout

2.0.0 layouts use the same tagged strings, and each node's position sits
0x4D bytes after its name's NUL, followed by a (1, 1, 1) scale.
`tools/decode_legacy_layout.py` accepts a node only when that scale check
passes, and it also reads the hardpoint nodes of the 2.0.0 ship models,
which supports the offset. TestScene yields 178 nodes; only the root name
fails the check:

- 13 `DockSeg`, 8 `IBCH`, 1 `MBB`, 10 `DishWall`
- 9 flags (`Flag F1`, `F2`, `D1-3`, `D1-6`, `D2-1` … `D2-5`) and 22
  turrets named after them (`Turret F1-`, `Turret D2-` …)
- docking and nav buoys, safe zones `SafeZone Z` and `SafeZone 0`, cubes
  `Home` and `Seenar`
- a ring of 104 `RingPan` panels plus two animated ring nodes

The 2.0.0 format truncates names to 10 characters. Positions are **local
to each node's parent**: turret coordinates are small offsets from their
flag. Parent links are not decoded, so these are not world coordinates yet.
The `DishWall` names repeat in later Arena1a, but the positions differ, so
this is an earlier, distinct arena.

## Checked and ruled out

- **Deleted or orphaned archive entries.** All 41 `.AOA`/`.ODB` archives
  across the five installers are packed end to end: zero bytes are
  outside a directory entry.
- **Installer slack.** No gap over 64 bytes between Wise members; each
  installer ends in a 1.1–2.4 KB Wise script tail.
- **The 2.8.0 RAR** holds only the installer and an `old-games.nfo`.
- **Later layouts.** The 2.7.1, 2.8.x and 2.9.2 layouts carry the same node
  names; 2.8.0 and 2.9.2 positions agree for all 16 shared layouts. The
  only difference remains the 80 older Arena1a turret records. 2.7.1
  positions were not compared numerically (its scene format is not decoded).
- **Scripts.** The eight `.scr` files are AI parameter sets and test
  chatter (`jrscen` and `MCVA_Scenario1` only print text). 2.0.0 differs
  only in an extra `Type` parameter.
- **Missing scenario sources.** 2.0.0 asks for `scenario.scr` and
  `terrain.aoa`; neither scenario file shipped, and its `TERRAIN.AOA` holds
  only `begin.tga`. 2.7.1 receives scenarios from the server
  (`SPacketLoadScenario`) and ships no `SCENARIOS.AOA`. 2.9.2's
  "Select the scenario you wish for offline play" screen has only Curt3.
  Any other missions were server-side and are not in any client.
- **2.3.1's type-240 resource** is 11 bytes of MFC UI data.
- **The tutorial** ("I am Mentor", seven lessons) is compiled into the
  client and present in every version. It is not lost data.

The 2.9.2 client also holds a list of AI callsigns that includes team and
tester handles (`Bryan Stephens`, `ahmed Supreme`, `ahmed minor`,
`ZeroSephiroth`, `Kibbysaur` …), which may help match credits to in-game names.

## Next steps

1. Recover the edit-command names: find the parser that fills the
   command index used at `0x4A9A47` in 2.9.2. Then load `JRMAP.TRN`
   in a real client. The local Station stub controls the player record,
   so it may be able to grant the management value the edit-mode check needs.
2. Trace the 2.9.2 scenario loader to name Curt3's raw fields and find
   its trigger and win logic.
3. Decode TestScene's parent links to get world positions, then render it
   next to Arena1a.
