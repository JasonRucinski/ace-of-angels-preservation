# Arena1a asteroid rendering investigation

The user reports asteroid silhouettes changing size while approaching, then
stabilizing close up. Forcing the wrapper's minimum depth buffer to 24 bits
resolved the base issue but did not resolve this symptom.

## Evidence collected on 2026-10-22

- A read-only retreat recording saved 96 samples over 24.013 seconds, covering
  about 79,100 world units of player displacement. Nine visible asteroid texture
  LOD transitions occurred. Local matrices remained constant. All 773 sampled
  selected meshes with valid cached world matrices matched parent/local matrix
  composition within 0.006 world units. Reads are non-atomic; invalid cache flags
  sampled during frame updates are not themselves defects.
- A stationary read-only draw-buffer snapshot found 63 asteroid instances,
  sharing nine mesh resources (three models, three texture variants each).
  Vertex and index buffers within each model were identical across variants.
  The three asteroid texture resolutions were fully opaque, eliminating alpha
  silhouettes as an explanation for changing geometry.
- The same snapshot found 235 cached-image billboard objects. All 63 asteroids
  had billboard records; 18 asteroid billboards were active. Unlike texture LOD,
  this path can change the displayed silhouette without altering mesh buffers.
- Original visibility code at `0x54321E..0x543238` gates the mesh on surface
  distance below 61,000. `0x4ED2C6..0x4ED2CF` excludes normally visible meshes
  from billboarding. Billboard refresh code at `0x4ED484..0x4ED4A8` compares
  cached versus current projected size against a four-unit threshold. These are
  candidate mechanisms for the reported popping, not a GPU reproduction.

Raw captures and disassembly are retained under ignored
`work/render-clip-review/`. The retreat ended on a process-memory read failure;
all complete JSONL samples preceding the failure were retained.

## Reversible workaround

`tools/asteroid_render.py` replaces the single floating-point comparison at
`0x543222` with guarded code in unused padding at `0x58BA00`. For model names
beginning `Astr-` or `Astr_`, it uses the existing 900,000-unit billboard horizon
constant. All other names use the original 61,000 comparison. The hook preserves
integer registers and flags and consumes exactly the original x87 operand.
Short strings and null name pointers take the original path.

This makes the existing meshes available throughout the usual Arena1a flight
area, bypassing cached-image rendering for those asteroids. It does not alter
their triangle counts, texture LOD, authored transforms, networking, collision,
or the base depth-buffer setting. It does not repair billboard generation.
More distant mesh draws may cost performance, which must be checked in flight.

The patch remains opt-in. `prepare_client.py` recognizes it, preserves it across
normal preparation, and includes it in exact-undo handling. Whole-image
normalization rejects unrelated executable edits. It has separate padding from
the online terrain hook and the existing offline clock/culling experiments.

## Verification

```powershell
.venv\Scripts\python.exe -I tools/test_asteroid_render.py
.venv\Scripts\python.exe -I tools/test_object_lod.py
.venv\Scripts\python.exe -I tools/verify_local.py --report work/asteroid-render-verification/gate.json
```

The new tests execute the original and patched x86 distance gate at three x87
precision settings around both cutoffs, check unrelated and short model names,
integer-state preservation, idempotence, exact undo, partial/corrupt patch
rejection, unchanged bytes outside the patch, and setup transaction/check/undo.
The original mesh/texture LOD tests remain applicable and pass unchanged.

On 2026-10-22 the user reported "that did it" after the asteroid-only flight
test. This establishes user-observed acceptance of the asteroid popping fix;
it is not a measured frame-rate benchmark or validation of every scene.

## Extension to all solid world models

At the user's request, `tools/solid_world_render.py` replaces the same six-byte
comparison at `0x543222` directly with `fcomp [0x59D9C0]`, using 900,000 instead
of 61,000 surface-distance units for world model groups. It replaces the
asteroid-only selection and clears that patch's code cave. No name list or new
rendering system is introduced.

Static control-flow inspection of the pinned original finds one code caller
of visibility `0x543000`, at `0x546BCE` in model-group update `0x546B20`.
That update has two callers: world-object visibility at `0x49BCC2` (using the
object's model pointer at +0x19C), and the model update at `0x4A4E36`.
The patch changes this model visibility gate, not a global billboard switch.
Intentional sprites, particles, and their effect submission code are unchanged.
The cached-image manager still uses its original visibility test at
`0x4ED2C8`; it skips a cached image when the real model is visible.

Texture/mesh LOD selection, projected-size culling, transforms, depth settings,
assets, and networking remain unchanged. This is not unlimited draw distance:
the existing 900,000-unit horizon and other visibility gates still apply.

With the client closed:

```powershell
.venv\Scripts\python.exe -I tools/solid_world_render.py game/2.9.2/AOACLIENT.EXE
# Restore exactly the prior client, including asteroid-only mode if installed:
.venv\Scripts\python.exe -I tools/solid_world_render.py game/2.9.2/AOACLIENT.EXE --undo
.venv\Scripts\python.exe -I tools/test_solid_world_render.py
```

The `.EXE.before-solid-world-render` backup preserves the working asteroid-only
client. `_solid_world_render.json` records hashes and pending visual acceptance.
Normal preparation preserves the installed mode; a fresh preparation does not
enable it. Undo broad mode before using the older asteroid-only patch tool.

Five new regression methods cover the original/patched x86 gate at three FPU
precisions, register/flag preservation, caller and byte-change scope, migration,
idempotence, exact rollback, corruption, and backup mismatch rejection.
These are CPU and installation checks. On 2026-10-22 the user confirmed stable
ships/stations and normal-looking effects in flight. Performance is not
benchmarked. A separate station brightness transition remained at close LOD.

## Station full detail

`Hy_base1.Gob` contains six meshes. Its interior changes from 117 triangles
at projected sizes 200..750 to 2,933 triangles at 750..4096. The two meshes
share texture `hy_bs1_b.tga`, the `SimpleTextured` shader name, material name,
and white vertex colors. Geometry and normals differ. This makes their lighting
a candidate for the user-reported brightness jump, not a proven GPU diagnosis.

At the user's request, `tools/station_detail.py` pins this station to its
closest mesh selection. It replaces the size load at `0x546BE4` with a guarded
hook at `0x58BB00`: exact model name `Hy_base1` receives the original maximum
projected size of 4000 for child LOD selection. Other names receive their actual
size. The station's stored projected size, visibility, distance, transforms,
materials, lighting, and effects remain unchanged. It does not enable all LOD
meshes together: the original selector chooses the three high-detail meshes
and excludes the three alternatives. This also selects `astr4_a.tga` rather
than the station's lower-resolution rock textures.

```powershell
# Close the client first:
.venv\Scripts\python.exe -I tools/station_detail.py game/2.9.2/AOACLIENT.EXE
.venv\Scripts\python.exe -I tools/station_detail.py game/2.9.2/AOACLIENT.EXE --undo
.venv\Scripts\python.exe -I tools/test_station_detail.py
```

The exact prior client is saved as `.EXE.before-station-detail`. Preparation
preserves this optional selection and recognizes `station-full-detail-v1`.
Undo station detail before undoing the underlying solid-world patch.

Five tests execute original child traversal/selection with the six extracted
station thresholds around 200, 750 and 1024 at three FPU precision settings;
verify the finest mesh set, unchanged root state and other model names;
and check register/flag preservation, installation, exact undo, byte scope,
idempotence, occupied/partial patch rejection, and backup mismatch rejection.
The user reported the brightness jump persisted. Subsequent live inspection
identified the visible dock sections as `newdock`, not `Hy_base1`; the
station-only patch targeted a different model. It is superseded below.

## Full authored detail for solid world objects

The next read-only snapshot found four visible `newdock` sections straddling
an additional authored visibility threshold. The user described the nearest
two as bright and the farther two as dark. `NewDock09` and `NewDock08` had
projected sizes 213.98 and 223.16, visible meshes, and inactive cached images.
`NewDock10` and `NewDock07` measured 190.88 and 197.34, had hidden meshes, and
active cached images. All five authored `newdock` meshes have a minimum
projected size of 200. Model-group update copied that minimum into the root's
visibility range, permitting cached-image fallback even after the earlier
distance cutoff was extended. This is stronger evidence for the brightness
handoff than the earlier unverified `Hy_base1` assumption. The nearby
`RingPanel` structure has a single mesh and is distinct from these dock sections.

`tools/world_detail.py` supersedes station-only detail with two changes:

- `0x546BE4`: select child meshes/textures using the original close-up size of
  4000, instead of the real projected size. The root's stored size is untouched.
- `0x546B46`: use the existing default root range of 5..4096 instead of deriving
  it from the child LOD ranges. This removes the dock's 200-unit cached-image
  fallback while preserving ordinary small-object culling and the far horizon.

The previous station-only code cave is cleared. This does not draw multiple
alternative LODs together: the original selector picks exactly the close-up
mesh set. All 154 parsed mesh models have a valid selection at size 4000.
This keeps the highest authored texture variants on asteroids and station
rock, plus the close-up ship/dock meshes. Texture filtering and the independent
sprite/particle/effect renderer are unchanged; this is not a global sampler
or mip-filter override.

```powershell
# Close the client first:
.venv\Scripts\python.exe -I tools/world_detail.py game/2.9.2/AOACLIENT.EXE
.venv\Scripts\python.exe -I tools/world_detail.py game/2.9.2/AOACLIENT.EXE --undo
.venv\Scripts\python.exe -I tools/test_world_detail.py
```

Exact rollback is `.EXE.before-world-detail`; `_world_detail.json` records
the installed hash. Undo this layer before undoing station detail or the
solid-world distance patch. Normal preparation preserves the selected mode.

Five tests cover the complete 154-model close-up selection across authored
boundaries, the measured four-dock threshold split, retained small-object
culling, FPU/integer state, migration from station-only mode, idempotence,
exact rollback, byte scope, partial/corrupt edits, and backup rejection.
Flight confirmation of brightness consistency remains pending.

## Distant object persistence (27 October 2026)

`tools/object_persistence.py` adds a separate optional visibility patch,
`distant-world-objects-v1`. It extends the mesh surface-distance cutoff from
61,000 to **4,500,000 world units**, and the cached-world-image horizon from
900,000 to the same limit. The shared model visibility check now accepts
projected sizes above **0.5**, instead of above 5. For an object limited by
screen size, that permits visibility ten times farther away at the same
viewport and object radius. Actual distance still depends on object size,
camera direction and the renderer's other clipping rules.

Simply lowering the screen-size check would leave many models without a
selected mesh. The group update also lowers its root visibility minimum to
0.5 and saves the original authored minimum in an unused stack local. Child
selection uses the greater of actual projected size and that saved minimum.
This keeps the lowest authored LOD available beyond its original range,
including models such as `newdock` whose authored minimum is 200. The real
projected size stays unchanged. Existing near LOD transitions and textures
remain in use; this patch does not force the most detailed meshes at distance.

The hook sites are `0x546BB3` (root range) and `0x546BEA` (child selection),
with 128 bytes of padding at `0x58BB80..0x58BBFF`. This is separate from the
station-detail and third-person caves. The distance constants have one code
reference each in the original image: `0x543222` and `0x4ED36A`. The size
comparison at `0x54326A` uses the existing 0.5 constant; the shared 5.0 constant
is unchanged. No changes are made to the server, physics, authored transforms
or intentional sprites/particles.

Close the client first, then run from the repository root:

```powershell
.venv\Scripts\python.exe -I tools/object_persistence.py game/2.9.2/AOACLIENT.EXE
# Exact rollback of this layer:
.venv\Scripts\python.exe -I tools/object_persistence.py game/2.9.2/AOACLIENT.EXE --undo
.venv\Scripts\python.exe -I tools/test_object_persistence.py
```

The input must already have a recorded client preparation. The exact prior
executable is retained as `.EXE.before-object-persistence`. The new mode
composes with the older asteroid-only, solid-world, station-detail and
world-detail modes. Normal preparation preserves it. Patch version 22 also
accepts `prepare --distant-objects` and `prepare --no-distant-objects`; it
remains off for fresh preparations unless explicitly selected.

Seven regression tests execute the original model-group range setup,
visibility calculation and child selection together. They cover the old
and new distance boundaries at three FPU precisions, the tenfold screen-size
range, all 154 parsed models' distant and near mesh selections, hidden and
behind-camera objects, hook ABI, optional-mode composition, exact rollback,
installation preferences, byte scope and rejection of partial/corrupt edits.
These are CPU and installation checks. In-flight visual acceptance and GPU
performance remain unmeasured; additional distant draws can cost frame time.

Installed on 27 October in both the normal `game/2.9.2` folder and the active
`work/arena1a-game-trial` copy after the user closed the client. Both pass the
asset/setup check, with exact prior-image backups verified. Nine focused
suites pass (58 tests), plus CLI enable/preserve/disable checks. See the
[verification record](../evidence/2.9.2/object_persistence_20261027.json).

Independent review on the same date reran the seven new tests and added two
pipeline tests in `test_object_persistence_pipeline.py`. Those execute the
whole model-group function through its return, including the relative-motion
calculations after the original tests' stop point. Reused trees exercise
recursive child visibility and the renderer's drawable predicate through
near/far, hidden and reappearance transitions at three FPU precisions. Saved
registers, stack cleanup, x87 stack depth and relative-motion outputs pass.
The original terrain clip-range accumulator and projection setter also accept
the new horizon: the initial 65,000-unit projection is replaced by the dynamic
mesh-pass range, not a fixed cap. No executable correction was needed.
These checks still do not exercise a real Direct3D device or establish frame
rate, image quality or absence of visible pop-in.
