# Offline rendering baseline

Status: ship-selection clipping fixed; flight rendering investigation ongoing.

## Automated observation proved (21 October 2026)

The Computer Use `@oai/sky` API successfully selected Play Offline, entered
flight, opened ship selection with Escape, and hid the briefing with F1.
Windows Graphics Capture returned actual textured DirectX frames. Startup
dialogs are secondary screenshots of a 2x2 parent window: target the screenshot
ID of the visible dialog, not the parent or accessibility button coordinates.
Refresh state after every action and select the window by the exact baseline
executable path; other diagnostic clients may be running.

Launch with the existing debugger to guarantee the game working directory and
collect failures (the generic app launcher exited during the first attempt):

```powershell
.venv\Scripts\python.exe -I tools/crashdbg.py --timeout 240 game/offline-baseline-2.9.2
```

This bounded debugger run terminates its own client after four minutes. It is
for diagnosis, not a timing benchmark. Do not enable physics breakpoints when
measuring smoothness. The loaded ActiveSkin module was the already registered
copy in `game/2.9.2`, so this is not a completely isolated COM installation.

The ship-selection list and information panel extended above the viewport.
Matching layout and projection hooks in `menu_aspect.py` now preserve the
authored 4:3 framing on widescreen. Before/after evidence: ignored
`work/offline-rendering/ship-selection-reference.png` and
`work/offline-rendering/ship-selection-fixed.png`. The first Dafusha entry was
clicked successfully after the fix. A separate intermittent panel-redraw
problem was observed both before and after this patch and remains unresolved.

`sample_rendering.py` records bounded read-only traces, including player and
mission-object transforms, names, focus and input axes. Reads are non-atomic;
frame-tick brackets identify some overlapping updates, but do not guarantee
atomicity within a frame. Terrain asteroids are not yet included. The stored
D3D view can belong to a HUD subview; use `main_camera_matrix` for the camera
input copied by 0x553810. Neither field measures GPU presentation timing.

Two initial tutorial idle traces each had 494 samples with stationary player
transforms. This does not validate moving-flight behavior. The user's reported
fault occurs while moving near ships, asteroids, capital ships and bases.

The game clock uses GetTickCount at 0x5296C4 and 0x529700. An isolated QPC
experiment replaces both sources before launch. Its first conversion failed
under the game's reduced x87 precision, producing 64 ms steps in live testing.
The corrected helper saves/restores the control word and calculates with
extended precision; emulator tests cover three precision modes, two frequencies
and 32-bit rollover. It remains excluded from supported preparation pending
moving-flight comparison. Clock epoch differs, so never apply it to a live
process or treat it as validated multiplayer behavior.

The existing `inspect_arena.snapshot(pid, True)` also collected 20 read-only
samples over approximately two seconds: 10 active player slots, 8 object slots,
and finite object positions throughout. Raw local evidence is in
`work/offline-rendering/idle-state.json`. Finite positions do not prove smooth
motion; this sample does not validate focus, frame pacing, or camera transforms.
The automation path is now demonstrated; a full unattended regression runner
and high-rate video capture have not yet been implemented.

Build a fresh, isolated copy from the hash-pinned installer and wrapper:

```powershell
.venv\Scripts\python.exe -I tools/prepare_offline_baseline.py game/offline-baseline-2.9.2
```

The tool refuses an existing destination, verifies static dependencies and
records initial file hashes in `_offline_baseline.json`. It does not launch the
client, register ActiveSkin, change the working client, or start a host.
The baseline includes logger size/lock fixes, the zero-time physics guard and
archive termination. Station discovery is redirected to localhost. Background
network and experimental protection patches are excluded. This is a usable
reference candidate, not an untouched historical reference.

Add `--menu-fix` to create a fresh baseline including the verified clipping fix.
Creation manifests describe initial hashes only; the current diagnostic folder
has subsequently received experimental patches and must not be represented as
still matching its creation manifest.

## First capture: reference configuration

Launch manually with the correct working directory:

```powershell
Start-Process -FilePath "$PWD\game\offline-baseline-2.9.2\AOACLIENT.EXE" -WorkingDirectory "$PWD\game\offline-baseline-2.9.2"
```

Choose **Play Offline**. If the login dialog does not appear, use the existing
ActiveSkin registration runbook; do not treat that failure as a rendering bug.
Do not run `prepare_client.py prepare` on this folder: it adds the full patch set.

Record desktop resolution, Windows scale, selected ship/mission, camera mode,
input devices, and game graphics settings. Keep the game focused. Record video
using an ordinary screen recorder; PrintWindow has previously returned a black
DirectX surface. Do not infer visual correctness from logs or memory alone.

1. Capture the complete ship-selection screen. Cycle the same ships in the
   same order and pause on each. Note missing previews, stale frames, clipping,
   text corruption, or distortion separately.
2. Enter the same offline mission. Record 20 seconds without intentional input,
   then a slow turn, forward flight toward a fixed landmark, and a stop.
3. Record whether the HUD, entire world, player-relative view, or individual
   objects move unexpectedly. Note input/camera settings before attributing
   camera movement to a defect. Moving enemies are not stationary references.
4. Repeat once after a clean restart. Mark inconsistent reproduction explicitly.

## Second capture: frame-rate comparison

Close the client before copying a profile. Change only the cap:

```powershell
Copy-Item game/offline-baseline-2.9.2/dgVoodoo.60fps.conf game/offline-baseline-2.9.2/dgVoodoo.conf
```

Repeat the same scene and input sequence. The reference uses wrapper defaults
with windowed output, unforced resolution, app-driven filtering/AA, VSync off
and no cap. The second profile changes only `GeneralExt.FPSLimit` to 60.
This tests a timing hypothesis; it is not a confirmed fix. The creation manifest
records initial hashes and is not updated to imply the active profile is unchanged.
Restore the reference with:

```powershell
Copy-Item game/offline-baseline-2.9.2/dgVoodoo.reference.conf game/offline-baseline-2.9.2/dgVoodoo.conf
```

## Acceptance and next steps

### Automated clock and camera comparison (no Computer Use)

```powershell
.venv\Scripts\python.exe -I tools/compare_render_clocks.py work/offline-rendering/clock-comparison.json
.venv\Scripts\python.exe -I tools/test_render_motion.py
.venv\Scripts\python.exe -I tools/test_render_clock_experiment.py
```

The comparison samples both Windows clocks at 60 and 144 Hz, executes the
actual patched x86 counter conversion, then replays translation, turning and
combined paths through the original camera builder at `0x569880`. These are
synthetic trajectories, not full game physics or GPU frame captures.

In the measured combined-motion replay, RMS frame-step projection error fell
from 1.297 to 0.145 pixels at 60 Hz, and from 2.547 to 0.113 pixels at 144 Hz.
At 144 Hz the old clock repeated 160 of 288 samples; the corrected clock
repeated none. This demonstrates clock-induced shared-scene jitter. The
original timer setter `0x40E000` also leaves its previous delta unchanged
when a timestamp repeats; its consumers have not all been audited.

Deterministic tests verify a camera-relative landmark remains within 0.03
pixels of its expected projection while translating and rotating at world
offsets up to 100,000 units. The mathematical camera transform did not
reproduce a large jump in those cases. This does not validate scene traversal,
asteroid LOD, per-object draw transforms, or final presentation.

An earlier debugger-free synthetic coast traveled approximately 4,890 units
in ten seconds. Camera and player translations matched in 488/494 non-atomic
samples; the other differences were approximately one frame of travel.
In the earlier stationary trace, named stationary mission objects remained
fixed, while Deep Explor had nonzero velocity and moved. This is not proof
that all reported drifting is intentional. Tutorial mode still runs combat;
deaths, respawns and debugger exception logging contaminate long live runs.

The isolated baseline currently includes the corrected clock. Close it before
changing the clock. These commands are restricted to that folder, verify the
whole normalized executable, retain a byte-exact backup and write a separate
`_render_clock.json` record:

The baseline also now includes the [culling correction](render-pipeline-audit.md).
Undo that patch first before using the clock commands below; their image checks
reject the additional culling edits.

```powershell
.venv\Scripts\python.exe -I tools/render_clock_experiment.py --undo
.venv\Scripts\python.exe -I tools/render_clock_experiment.py
```

`seed_offline_velocity.py PID` provides a one-shot synthetic coast fixture for
an already loaded anonymous offline player. It does not launch or navigate the
client, and is not yet an unattended full-scene runner. Normal keyboard input,
combat and networking are outside that fixture's validation scope.

| Check | Required evidence | Current result |
|---|---|---|
| Ship selection | All tested previews/text render correctly across repeated selection | Clipping fixed; panel redraw remains open |
| Idle camera | Repeatable behavior with known camera/input settings; no unexplained jumps | Stationary player verified in bounded traces |
| Flight scenery | No unexplained discontinuities during repeatable landmark passes | Pending |
| Enemy movement | Continuous movement except documented spawn/teleport behavior | Pending |
| Timing | Repeatable clock comparison and full-scene presentation validation | Clock quantization reproduced and corrected; presentation pending |

If both profiles fail, isolate resolution/DPI, preview surface updates, camera
transforms, and physics timing one variable at a time. Do not change multiple
wrapper options as a speculative fix. Use original-code traces to distinguish
world-state jumps from view/render jumps once the failing scene is known.

### Asteroid and object LOD audit

For the subsequent CPU culling, transform, draw-dispatch and device-error
investigation, see [rendering pipeline audit](render-pipeline-audit.md).

Run without launching or controlling the game:

```powershell
.venv\Scripts\python.exe -I tools/audit_object_lod.py work/offline-rendering/object-lod-audit.json
.venv\Scripts\python.exe -I tools/test_object_lod.py
```

The audit reads 154 mesh models (18 other files are layouts or unparsed).
It applies serialized mesh-node transforms before comparing bounds, and unions
multipart meshes sharing named LOD labels. Raw coordinates alone are misleading:
Vermok's lower-detail meshes are stored about 76 and 151 units away in X, but
their node transforms cancel those offsets. Vermok and Vasa Chovo's transformed
LOD centers agree within 0.001 units.

All ten parsed asteroid models have identical vertex/triangle geometry and node
transforms **within each model's variants**. This does not assert that separate
base and `_mip` files have identical geometry. Original x86 selector `0x542920`
uses an inclusive lower and exclusive upper projected-size bound. Automated
tests check both explicit and cached size selection around every asteroid
threshold: exactly one mesh is selected throughout the tested visible range.
Sizes below 5 select no asteroid mesh, matching the assets' small-object cutoff.

The original arithmetic at `0x54310D..0x54315E` clamps projected size to 4000.
The close-distance regression executes that code and verifies valid selection;
the assets' 4096 upper bound is therefore not evidence of close-range popping.
Four test methods pass. Compact evidence is in
`evidence/2.9.2/object_lod_audit.json`; the detailed generated asset report stays
under `work/`. No executable or asset LOD changes were justified by these tests.

These checks exclude scene-parent transform propagation, frustum culling,
texture selection, draw submission and GPU output. Those remain possible causes
of object popping; passing this audit does not establish full-scene correctness.

After offline passes, compare the full patch set offline using identical assets
and settings, then the localhost host. Keep host state and packet timing analysis
separate from presentation. Historical fidelity still needs independent footage,
documentation, or a known-good installation; internal consistency is not proof.
