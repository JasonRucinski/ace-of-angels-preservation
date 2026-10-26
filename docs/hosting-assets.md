# Local maps and scenarios

Inventory of the extracted 2.9.2 bundle, checked 20 October 2026. These are
available assets, not a claim that the replacement server can host their
original game modes. Reproduce with:

```powershell
.venv/Scripts/python.exe -I tools/arena_inventory.py work/2.9.2/export work/2.9.2/scenes evidence/2.9.2/arena_inventory.json
```

The scene JSON is produced by `tools/scene2obj.py` (see `assets.md`). Its
name-to-object matching is heuristic; unrendered nodes may be markers or
unresolved geometry. All model references that it resolved exist locally.
Hashes and counts are in `evidence/2.9.2/arena_inventory.json`.

Arena1a's count was corrected on 21 October: the old inventory omitted 80
turret records. Its current audit and remaining gameplay blockers are in
[Arena1a recovery](arena1a.md); the older inventory JSON retains the historical
303 count. Nested expansion adds 11 records, including 10 placed meshes.

| Arena/layout candidate | Nodes | Nodes resolved to geometry |
|---|---:|---:|
| Arena1a | 383 | 244 (254 with nested layout expansion) |
| CTF_arena | 119 | 113 |
| CTF_arena_b | 64 | 59 |
| newterrain | 368 | 248 |
| outerchange | 89 | 7 |

There are also four asteroid-field layouts (`ast_fld_a` through `ast_fld_d`)
and eight base/component layouts: `CTF_base`, `hu_base_a`, `hu_base_b`,
`hy_base_test`, `hy_winga`, `HyBase2Lay`, `irrosa01`, and `ze_winga`.
These total 17 exported layouts; component layouts need not be standalone maps.

Five backdrops exist: `spacebkgd`, `spacebkgd2`, `spacebkgd3`, `spacebkgd5`,
and `spacebkgd6`. The server-list backdrop must name an existing object:
the original `field40` placeholder caused an intentional client shutdown.

`SCENARIOS.AOA` exports only **Curt3**, a 2,282-byte binary scenario. Tagged
strings include Defense, Offense, Attackers, Defenders, and Air Superiority.
Those are labels inside one file, not five recovered scenarios. Its structure
(teams, groups, ships, orders, waypoints) is now decoded by
`tools/decode_scenario.py`; trigger and win rules are not in the file. The
loose `JRMAP.TRN` is a further editor-saved map. See [level-data.md](level-data.md).
This inventory does not cover missing server-delivered resources.

The experimental server now creates players and one opt-in passive mission
ship (`--experimental-object`), verified in the real client on 21 Oct.
Movement synchronization still has timing/recovery limits, and the relevant
scoring/team/mission rules are missing. Advertising a terrain name in Station
alone does not provide those. No original multiplayer scenario is yet
verified hostable. See findings 9.11 for the object-spawn evidence.

Static `CTF_arena` continuation (21 October 2026):
`python -I tools/check_arena_geometry.py` checks the existing heuristic export
and writes `work/ctf-arena-validation.json`. It found 37,449 finite vertices,
35,134 triangles with valid indices, 113 exported objects and no degenerate
triangles. All resolved model files exist. Six nodes remain unresolved:
`NavFar2`, `ZAMissile`, `ZAMissile0`, `ZARepair0`, `CTF_base01`, `CTF_base02`.
In particular, the bases are not represented in the checked mesh; treating
this export as complete server collision would omit them. The static check
does not verify node semantics, heuristic matching, original-client loading,
collision or spawn safety. `CTF_arena` remains a validation candidate.
