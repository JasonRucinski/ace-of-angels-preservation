# Asset extraction (2.9.2)

Extracted assets are FRE's copyrighted game data: they are written under the
gitignored `work\` and are never committed. Only the tools and these notes are.

## Pipeline

```powershell
# 1. unpack every archive (decrypt + decompress, CRC-checked per entry)
#    the built-in key is read from the 2.7.1 client; 2.9.2 uses the same key
foreach ($a in "AOAOBJECTS.ODB","DATA.AOA","HUD.AOA","SCRIPTS.AOA","SOUNDS.AOA","TEXTURES.AOA","IMAGES.AOA","FX.AOA","SCENARIOS.AOA") {
  .venv\Scripts\python.exe -I tools\aoapack.py extract work\2.7.1\members\15_AOACLIENT.EXE game\2.9.2\$a work\2.9.2\assets\$($a.Split('.')[0])
}
# 2. browsable tree: TGA -> PNG, everything else copied with its real name
.venv\Scripts\python.exe -I tools\export_assets.py work\2.9.2\assets work\2.9.2\export
# 3. 3D models -> Wavefront OBJ/MTL (textures referenced from ..\TEXTURES)
.venv\Scripts\python.exe -I tools\gob2obj.py work\2.9.2\export\AOAOBJECTS work\2.9.2\models ..\TEXTURES
# 4. optional preview render of one model
.venv\Scripts\python.exe -I tools\render_obj.py work\2.9.2\models\Vermok_LOD1.obj vermok.png 512
```

For step 3's texture paths to resolve, copy `export\TEXTURES` to
`work\2.9.2\TEXTURES` (or pass a different texture directory).

Archives can also be written back: `aoapack.py replace` rebuilds an archive
with named entries swapped (see [replacement texture pack](client-setup.md#optional-replacement-texture-pack)).

## What comes out (2.9.2, 748 archive entries, all CRC-valid)

| Archive | Contents | Output |
|---|---|---|
| TEXTURES.AOA | 214 ship/station/effect skins, uncompressed TGA (24/32-bit, up to 1024²) | PNG |
| HUD.AOA | 56 HUD/cockpit images + `.cfg` | PNG |
| DATA.AOA | 13 TGA + 10 data blobs | PNG / raw |
| IMAGES.AOA | 39 BMP (UI) | BMP |
| SOUNDS.AOA | 55 MP3 + the 55 WAVs the client decodes into it on first run | MP3 / WAV |
| SCRIPTS.AOA | 8 readable `.scr` scripts | text |
| FX.AOA | 14 `.sfx` effect definitions | raw (not decoded) |
| SCENARIOS.AOA | the offline scenario (Curt3) | structure decoded: `tools/decode_scenario.py`, see `level-data.md` |
| AOAOBJECTS.ODB | 172 `.Gob` (3D), 123 `.Sco` (ship configs), 39 `.Shs`, index | see below |

## `.Gob` 3D model format

Recovered from the data and validated mesh by mesh (every index in range,
≥95 % unit normals, blocks end exactly where the next field starts):

* Strings: `68 57 76 05` tag, u32 length, bytes, NUL.
* Header: `Gob\0`, ids, model name, bounding box, material table
  (letter → texture filename, e.g. `A` → `Vermok.tga`).
* Mesh block (one per LOD, named `*LOD: 1..3` when named at all): material
  letter, `u32 vertex_count`, `u32 face_count`, then
  * 64-byte vertex: `f32 x,y,z`, `f32 u,v`, 8 zero bytes, u32, 12 bytes of
    uninitialised exporter memory (2000-era stack/kernel32 addresses),
    `f32 nx,ny,nz` (unit), `u32` ARGB colour, u32;
  * 36-byte face: `u16 i0,i1,i2`, u16 flags, 16 zero bytes, u32 group,
    3 floats of per-face data;
  * then a shader name (`SimpleTextured`) and the mesh's texture filename.
* After the meshes: named attachment points (`Dummy01..`, each with a
  `Category`) — weapon mounts and similar.

Result: 154 of 172 `.Gob` files → 289 meshes (LODs included), e.g. Vermok
712/374/202 vertices. Verified visually by rendering (correct textures,
Kafic purple as in the in-game target window).

The other 18 `.Gob` files are **scene layouts**, not meshes: arenas
(`Arena1a`, `CTF_arena`, `newterrain`, `outerchange`), bases and asteroid
fields. They are lists of ~0x1DF-byte node records: name (`Astr-C07`,
`RingPan12`, `DishWall03`, `SafeZone Z`, turret/flag/nav markers), bounding
box, then position (f32×3), scale (f32×3) and a unit quaternion, plus a
`Category`. The node also stores its full Direct3D world matrix at +0xF8
from the end of its name (orthonormal rotation rows, translation == the
stored position for every node checked).

Nodes name objects, not models: `Astr-C07` → object `Astr-C` (a `.Sco`) →
that object's model (`Astr-C_mip.Gob`). `tools/scene2obj.py` resolves this
chain (longest `.Sco` name prefix) and writes each scene as one OBJ plus a
`_nodes.json` of every node and its position. All 17 scenes export; e.g.
Arena1a initially placed 244 of 303 detected nodes as geometry (152 ring panels, 54 asteroids,
flags, dish walls, docks, the base). Its ring panels close into two clean
hoops, which checks the matrices. The other nodes are markers with no model
(safe zones, nav/warp points, turret and flag mounts, power-up spawns).
The 21 October correction recovers 80 omitted turret records, bringing the
root-file count to 383. Optional `--expand-layouts` adds the nested HyBase2Lay
records and 10 meshes: 394 records and 254 meshes total. These counts do not
establish working gameplay nodes; see [Arena1a recovery](arena1a.md).

```powershell
.venv\Scripts\python.exe -I tools\scene2obj.py work\2.9.2\export\AOAOBJECTS all work\2.9.2\scenes ..\TEXTURES
```

## `.Sco` object configs (ships, stations, turrets, pods)

```powershell
.venv\Scripts\python.exe -I tools\sco_dump.py work\2.9.2\export\AOAOBJECTS work\2.9.2\sco.json work\2.9.2\ships.md
```

Header strings: name, class code (`S621`), faction, (empty), `.Gob` model.
Then one record per ship system: a name string and a 284-byte block starting
`u32 type, f32 hit points, f32 × n parameters`. Guns and missile racks are
followed by their mount point (a hardpoint in the model, named `Dummy05`,
`Dmy-G04`, `RACK_I_02`…), then weapon id + firing sound or slot + missile
type. Verified against the running game: the Ym Khtat (S707, Sho'Tahl
Republic) decodes to Power Plant 30, Gun310 ×4 and Gun-360 ×2 at 2 each,
ECM 5, Scanner 5, Engine 30, Hull 40, Internal Hull 12, exactly the in-game
Damage panel. 124 objects decode, across 11 factions that match the official
site's nation list. The parameters after hit points are kept raw; their
meaning (power draw, recharge, etc.) is not established.

## Map preview gallery

`tools/render_map_previews.py` renders all 17 recovered scene exports to a
local HTML gallery with 29 PNG views. Arena candidates include full-layout
oblique/top views and labeled close-ups; component layouts are listed separately.
The images use original exported textures with simplified preview lighting.
Unresolved nodes are listed rather than replaced with invented geometry.

After the extraction/export steps above, one scene texture comes from DATA
rather than TEXTURES. Stage that original image alongside the other preview
textures, then render:

```powershell
Copy-Item work/2.9.2/export/DATA/salamtex.png work/2.9.2/TEXTURES/SALAMTEX.png
.venv/Scripts/python.exe -I tools/render_map_previews.py
```

Open `work/map-previews/index.html` in a browser. Images and extracted assets
remain under ignored `work/`; nothing is uploaded. The gallery manifest records
scene hashes, view angles, framing and unresolved node names. Different views
are fitted independently and are not to a shared scale. A close-up may crop
surrounding geometry; full views retain exported spacing. These previews do not
establish original-client loading, complete collision or working scenarios.

For one close-up, the existing renderer now supports an object-name prefix:

```powershell
.venv/Scripts/python.exe -I tools/render_obj.py work/2.9.2/scenes/outerchange.obj work/map-previews/outerchange-base.png 1000 35 25 --focus Hy_Base
```

## Not yet decoded

* the meaning of each system's further parameters;
* `.Shs` (gun/rack definitions such as `Gun-410`, `Rack IIA`), `.sfx`, the
  scenario file, and the extra fields in `DataBaseIndex` (68-byte records:
  name, then a numeric object id, 16385 upward).
