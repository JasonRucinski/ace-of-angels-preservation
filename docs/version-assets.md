# Cross-version asset inspection

Checked 20 October 2026. Scope: **all six recovered versions in
`manifest/downloads.json`**, not a claim to have located every historical
release. Five are complete installers; 2.3.1 is a replacement executable only.
No installer or client was executed for this review. The active `game/`
directory and multiplayer implementation were not changed.

All six package/client hashes match the manifest and all six compiled version
checks agree. All **2,609 packed entries** across the five installers passed
their decoded CRC checks; installer ZIP member CRCs also passed.

| Version | Installer files | Packed assets | Identical to 2.9.2 | Same name, changed bytes | Name and bytes absent |
|---|---:|---:|---:|---:|---:|
| 2.0.0 | 17 | 244 | 69* | 86 | 89 |
| 2.3.1 | client only | 0 | — | — | — |
| 2.7.1 | 38 | 430 | 282 | 147 | 1 |
| 2.8.0 | 40 | 592 | 507 | 84 | 1 |
| 2.8.2 | 40 | 595 | 482 | 112 | 1 |
| 2.9.2 | 41 | 748 | baseline | — | — |

*Includes three entries with matching content under a different name/archive.
The 89 early entries include WAV audio whose later counterparts use MP3;
this is a file-level comparison, **not 89 confirmed new gameplay assets**.

## Useful findings, in priority order

1. **80 older turret placement records in Arena1a.** The 2.8.0 and 2.8.2
   layouts export 383 nodes versus 303 in the existing 2.9.2 export. All 80
   names absent from the later layout start with `Turret `. Their positions
   are retained in ignored `work/asset-review/arena1a-old-only-nodes.json`.
   Both versions resolve 244 nodes to geometry. The extra turret nodes are
   markers/unresolved objects, not rendered working turrets. This is useful
   placement evidence for arena reconstruction, not proof of spawn rules,
   teams, weapon types, or server-side behavior. The layout reader validates
   matrix/position agreement; matching node names to models is heuristic.

2. **Early geometry absent by name from 2.9.2.** Version 2.0.0 contains
   `Harbinger.Gob`, `CapShip1.Gob`, `DockSeg.Gob`, `Dish1.Gob`, `Flag.Gob`,
   `Section1.Gob`, `Section4.Gob`, and `Turret.Gob`. It also contains
   `CapShip.Sco` and `DockSeg.Sco`. These files have distinct bytes and names;
   this does not prove every shape is conceptually unique to that release.
   Tagged strings in the two configs reference `CapShip1` and `DockSeg`.
   The capital-ship config also names the United Human Confederacy.

   The existing model reader could not read the 32-byte legacy vertices.
   `tools/export_legacy_models.py` recovers **44 meshes from 37 of 40**
   2.0.0 Gob files and **93 meshes from 59 of 78** 2.7.1 Gob files. Accepted
   meshes have finite values, at least 95% unit normals, in-range face indices,
   and an exact shader-record boundary. These are geometry-only OBJ/MTL
   exports; legacy shader/texture bindings remain unresolved. `Harbinger`,
   `CapShip1`, and `DockSeg` previews were rendered and visually inspected.
   `Section4` and `RingPanel` fail this conservative mesh reader; `TestScene`
   is a layout rather than a mesh. Rejected files remain preserved as raw data.

3. **An early TestScene layout and older equipment definitions.** The 2.0.0
   `TestScene.Gob` contains DockSeg, flag, turret, safe-zone, and buoy names.
   Its layout format has not been reconstructed. Fifteen old `.Shs` names
   are absent in 2.9.2: ten `DGun-*` definitions, `DRack-MQ4T1`, `Missle1`,
   `Missle2`, `Missle3`, and `TempRack`. Preserve these as references for
   equipment-format research; their fields and compatibility are unverified.

4. **Older art and audio.** The earliest bundle supplies older ship-art
   images such as `hvnswrd`, `bstrdtex`, and `*_t1`, plus bump-map variants and
   `begin.tga`. Its 82 supported TGA images were converted to PNG. Some are
   duplicates within that build. Its audio is WAV while later installers
   contain MP3; different hashes/extensions do not mean different sounds.
   `chime`, `primal1`, and `Tylenol` are early audio names absent from the
   later installed archive. No listening or acoustic equivalence test was
   performed, so these are candidates rather than verified new sound effects.

5. **An older base configuration.** `hy_base1.Sco` survives in 2.7.1, 2.8.0,
   and 2.8.2 but is absent from 2.9.2. It references `Hy_base1`, a model that
   still exists later. It may help explain the old base setup; copying the
   config into the newer client has not been tested.

## What this did not recover

The eight scripts and single `Curt3` scenario in 2.8.0 and 2.8.2 are
byte-identical to the later versions. The 2.0.0 scripts include simpler
predecessors, including placeholder capital-ship behavior. No additional
scenario or standalone server implementation was identified in these packages.
**Correction (22 Oct):** this review skipped the loose `JRMAP.TRN`, an
editor-saved world map present in every installer, and did not decode
`TestScene`. Both are now decoded; see [level-data.md](level-data.md).
No extra assets are supplied alongside the 2.3.1 replacement client; its
embedded PE resources are inventoried separately.
The 2.3.1 client contains 36 resource payloads, 18 of which have bytes absent
from 2.9.2 (17 dialog templates and one custom type-240 resource).
Raw resources are in `work/asset-review/2.3.1/client-resources/`;
their type/ID/language, hashes, and comparisons are recorded in
`evidence/asset-review/client-resources.json`. These were not rendered as UI.

The newer Gob exporter reads **149 meshes from 93 models** in each of
2.8.0 and 2.8.2. Seventeen other Gobs in each were inspected as layouts,
including the six-node `ze_wingb` component. Older layouts lack the
`Category` string used by `scene2obj.py all`; explicit names were required.
The 2.0.0/2.7.1 scene formats still need separate work.

Archive byte differences are not automatically visual or gameplay differences:
format changes and uninitialized exporter fields can change hashes. Nothing
here establishes that old data can be dropped into 2.9.2 unchanged.

## Files and reproduction

- Sources and expected installer/client hashes: `manifest/downloads.json`.
- Fresh downloads: `builds/asset-review/{2.0.0,2.3.1,2.8.0,2.8.2}/`.
  The retained 2.7.1/2.9.2 installers in `originals/` were reverified.
- Per-version installer inventories and decoded-file comparisons:
  `evidence/asset-review/<version>.json`; every decoded entry has a SHA-256.
- Compiled version checks: `evidence/asset-review/<version>-version.json`.
  These handle virtual zero-fill in 2.0.0 and 2.8.0, rather than trusting
  stale release notes or installer labels.
- Extracted data: `work/asset-review/<version>/assets/` and `export/`.
- Geometry: `legacy-models/` for 2.0.0/2.7.1, `models/` for newer versions;
  decoded 2.8 layouts are in `scenes/`.
- Geometry previews: `work/asset-review/2.0.0/harbinger.png`,
  `capital-ship.png`, and `docking-segment.png`.
- All downloaded game data, exported models, images, and coordinates remain
  gitignored. Evidence JSON contains inventories and validation metadata.

```powershell
.venv/Scripts/python.exe -I tools/compare_version_assets.py
.venv/Scripts/python.exe -I tools/compare_client_resources.py
# Replace VERSION with a complete-installer version:
.venv/Scripts/python.exe -I tools/export_assets.py work/asset-review/VERSION/assets work/asset-review/VERSION/export
.venv/Scripts/python.exe -I tools/export_legacy_models.py work/asset-review/2.0.0/export/AOAOBJECTS work/asset-review/2.0.0/legacy-models
.venv/Scripts/python.exe -I tools/scene2obj.py work/asset-review/2.8.0/export/AOAOBJECTS Arena1a work/asset-review/2.8.0/scenes ../export/TEXTURES
```

The comparison uses pristine installer archives. The existing runtime-derived
2.9.2 extraction includes 55 additional decoded WAVs; those are not extra
shipped assets. Filename matching is case-insensitive within each archive;
content matching also searches other archive names to catch renamed copies.

Final verification rehashed all 2,609 extracted files, checked all six runtime
version reports, validated exported OBJ indices, and reproduced both sets of
80 older turret nodes against the freshly extracted pristine 2.9.2 layout.
The three new Python tools compile successfully. No runtime compatibility,
audio equivalence, or working multiplayer behavior is claimed by this audit.
