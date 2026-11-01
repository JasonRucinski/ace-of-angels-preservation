# Adding new objects

Added 27 October 2026. `tools/make_object.py` turns a 3D model in glTF
(`.glb`) format into a new object for the 2.9.2 client: a model file
(`.Gob`) and an object config (`.Sco`), added to a play copy's
`AOAOBJECTS.ODB`. A [map spec](custom-maps.md) can then place the object by
name like any original one.

The first new object is **Bennu**, the asteroid 101955 Bennu, from
[NASA's 3D Resources](https://github.com/nasa/NASA-3D-Resources). It is
scaled up to a mining world 120 km across and sits 776 km out in Crucible.
The real client loaded it, drew it and lit it
([evidence](../evidence/2.9.2/custom_object_bennu_20261027.json)).

## Bennu

- **Source:** `1999 RQ36 asteroid.glb` from NASA's repository: 329,596
  bytes, SHA-256 `644af156…7958`. The repository describes its assets as
  free to use without copyright. NASA's media guidelines ask for NASA to be
  credited and for no implied endorsement. The file is not stored here.
  [`config/objects/bennu.json`](../config/objects/bennu.json) records its URL
  and hash, and `install` refuses any other file.
- **Model:** 9,122 vertices and 18,240 triangles. It has no texture, so it
  takes the game's own tiling rock texture `astr4_a.tga`, at one repeat per
  18 km. No new texture is added.
- **In Crucible:** about 776 km out, ahead, down and to port. A **Bennu**
  waypoint sits 45 km above the side that faces you on arrival. That side holds:
  - the mining settlement: `hy_base` "Bennu Works" lying on the surface in a
    safe zone, with two NewDocks
  - an excavation pit of four Wall segments, and a DishWall ore screen
  - four tugs, two IBCH ore haulers and an MBB command ship
  - four ore chunks in orbit
  - repair and +20 shield power-ups

  Each structure stands on the real surface: its position comes from a ray
  cast against the converted mesh, tilted to the surface normal.

## Using it

Download the model into its own new folder, then add the object before
installing the map. The map's `install` checks every object name against
the play copy's database.

```bash
mkdir builds/bennu-nasa
```

```bash
curl -L -o builds/bennu-nasa/bennu.glb "https://raw.githubusercontent.com/nasa/NASA-3D-Resources/master/3D%20Models/1999%20RQ36%20asteroid/1999%20RQ36%20asteroid.glb"
```

```bash
.venv/Scripts/python.exe -I tools/make_object.py install config/objects/bennu.json builds/bennu-nasa/bennu.glb work/custom-map/client
```

```bash
.venv/Scripts/python.exe -I tools/make_map.py install config/maps/crucible.json work/custom-map/client
```

Then `make_map.py serve` as usual. In flight, press T until the target
windows show **Bennu**, and follow the marker.

`install` needs `requirements.txt` for the archive key. The first time, it
keeps the database as `AOAOBJECTS.ODB.before-custom-objects`. Later installs
keep objects added from other specs and replace the spec's own entries, so
it can be repeated after changing the spec. `undo` puts the backup back,
removing every added object. `game\2.9.2` is refused. `preview SPEC MODEL OUT_DIR`
writes the `.Gob` and `.Sco` without installing them. Render a preview with
`tools/gob2obj.py`, then `tools/render_obj.py`.

## Object spec

```json
{"object": "Bennu", "model": "Bennu1", "radius": 60000, "tile": 18000, "texture": "astr4_a.tga",
 "source": {"url": "…", "sha256": "644af156…"}}
```

- `object` is the name maps use, and `model` names the `.Gob`, as `Cube`
  uses `Cube1`. Both must be new names in the database.
- `radius` is the distance from the box centre to the farthest vertex, in
  world units. For scale: Astr-C is 16 km, `hy_base` 16 km and fighters
  about 0.1 km.
- `texture` must already be in `TEXTURES.AOA`.

## How it works

**Model.** The `.Gob` is written from the original `Astr-C.Gob` template: a
single textured mesh with asteroid settings. `make_object` replaces:

- the model name, and the header length field at `+0x0C` (162 plus the name
  length)
- the model and node bounding boxes
- the node's translation (Astr-C's is a small offset; Bennu's is zero)
- the mesh block
- both copies of the texture name

Everything else is kept byte for byte. The field meanings come from the
original files:

- **Vertices:** position, UV, normal at `+44`, colour `0xFFFFFFFF` and 2.
- **Faces:** three indices, edge flags `0x57`, 2 at `+20`, then the three
  edge lengths |ab|, |bc| and |ca|. That order matches every face of Astr-C
  and almost every face of the CCVB carrier; the others are triangles with
  equal edges.
- **Winding:** the outward side is cross(b − a, c − a) in the game's
  left-handed coordinates, so glTF's z is negated. The winding is chosen by
  the closed mesh's signed volume. NASA's Bennu normals point inward, so
  normals are rebuilt from the faces.
- **Texture coordinates:** triplanar. Each triangle is mapped from the plane
  of its main normal axis.

**Config.** The `.Sco` is `Astr-C.Sco` with the object and model names
swapped. Its header does not depend on name lengths, and its systems
(power plant, hull) are the asteroid's.

**Database.** `aoapack.rebuild` can now append entries. They get the same
mode as every shipped entry: compressed with CRC and encrypted with the
archive key. The directory count, offsets and the encrypted directory are
rewritten, and the 4-byte `DataBaseHeader` (`Odb\0`) needs no change.
Entries are not sorted, and lookups take the first match, so new names go
at the end without shadowing any original object.

## Not verified

- collision with Bennu
- the frame-rate cost of an 18,240-triangle model
- how Bennu looks from beyond the 61,000-unit mesh distance in normal flight
  (from the spawn it is 776 km away, inside the 900 km cached-image horizon)
- flying the route from the spawn
- a second player
