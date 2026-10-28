# Classic Enhanced visual experiment

An opt-in color filter for Ace of Angels 2.9.2. The default now targets a
dramatic cinematic look: lifted shadow detail, stronger color and contrast,
teal shadows / warm highlights, wider bloom, and a light edge vignette.
The sky keeps its original colors by default; foreground lights can still
cast a soft halo across it.
This is an SDR experiment; it does not add HDR lighting or new texture detail.

The experiment uses the standard 32-bit ReShade 6.8.0 runtime after dgVoodoo2.
Our self-contained shader needs no shader packs or third-party add-ons.
Sky protection uses ReShade's built-in depth access with the pinned dgVoodoo2
2.87.5 D3D11 configuration.
The standard shader affects the final image, including HUD pixels over geometry.
The prepared local experiment now has the optional **UI preservation mode** below:
it applies the effect before the HUD is drawn, keeping panels, text, radar, and
target previews in their original colors.

## Engine exhaust experiment

The optional UI add-on now projects two blue-white engine plumes from the
player model's named `Trail` attachment points. In **F2 chase view**, the
plumes have a white core, blue flame and soft halo. **Engine exhaust** controls
strength (default 1.6; 0 disables it). This needs the updated add-on as well
as the shader; standard ReShade alone has no engine-position data.

The first version covers up to two engines on the player ship. Length ranges
from 40 to 105 world units with smoothed forward speed measured from rendered
positions. This is a motion response, not a direct throttle/afterburner read.
Models without named attachments get no invented engine placement. The
existing chase-camera patch must supply a current player node; cockpit,
spectator and unsupported camera paths fail closed. New cinematic-camera
patches have not been validated with this experiment.

The add-on reads model attachments and the native world/view/projection transforms;
it does not modify physics or assets. The shader tests against world depth
and runs before HUD rendering. Sky colors remain unchanged; exhaust light can
occupy a small area of sky immediately around an engine.

Capture only this effect while retaining all earlier lighting:

```powershell
python -I tools/classic_ui.py capture game/classic-capture --engines --output work/classic-enhanced/engine-review
```

Enter F2 chase view with effects enabled first. Captures are consecutive live
frames, so moving scenery may differ. The initial paused briefing comparison
isolates exhaust cleanly. Original PNG bytes are retained in the report. The verified local reports are
`work/classic-enhanced/engine-verified/index.html` (isolated idle comparison)
and `work/classic-enhanced/engine-motion-verified/index.html` (moving flight).
See [engine verification evidence](../evidence/2.9.2/classic_enhanced_engines_20261028.json).

## Try the prepared experiment

From the repository root:

```powershell
python -I tools\classic_enhanced.py launch game\classic-enhanced
```

Choose **Play Offline** and enter training for the first comparison.

- **Scroll Lock** toggles all effects instantly. It does not unload ReShade.
- **Home** opens the ReShade controls. Enable **Compare: original left /
  enhanced right** to inspect both versions of the same frame. Turn it off
  afterward, and close the overlay with Home before flying.
- Adjust Color vibrance, Shadow detail, Contrast, or Highlight glow
  in that overlay. These changes belong to the experiment's local preset.

Start by comparing a shadowed hull, a bright weapon/engine effect, and the
smallest HUD text. Check distant targets remain visible, dark space stays
dark, highlights retain their color, and turning/firing remains smooth.

The dramatic defaults are vibrance **0.95**, contrast **0.30**, shadow lift
**0.75**, exposure **+0.35 stops**, color grade **0.65**, vignette **0.18**,
sharpening **0.22**, glow **0.65**, threshold **0.40**, and glow spread **2.5**.
Radiant lights defaults to **2.2**, with light halo color **0.8**. This separate
half-resolution layer retains tiny bright source pixels and gives them a
tighter, more colorful halo over the existing wide bloom. Set Radiant lights
to **0** to restore the preceding dramatic look. It affects highlights on
reflective surfaces; it cannot identify actual lamps. The standard mode also
affects bright HUD text; UI preservation mode excludes the later HUD draw calls.
The glow uses two quarter-resolution and two half-resolution targets;
sharpening stays capped at
0.015 per channel to limit halos. Exact black stays black before bloom.

**Cinematic light streaks** adds thin horizontal flares to compact, bright
foreground highlights. Defaults are strength **2.2**, reach **64 pixels at
1920-wide resolution**, and highlight threshold **0.72**. Reach scales with
screen width. Set strength to **0** to restore the preceding glow treatment;
the Subtle preset keeps streaks off. Higher thresholds restrict them to brighter
sources. The source comes from the original light layer, before exposure or
bloom; a local-contrast gate suppresses broad bright hull surfaces. Sharp hull
glints and world labels can still qualify: this is a highlight effect, not an
engine/lamp detector. Two extra one-eighth-area targets form the tapered streaks.
Sky pixels never seed streaks with protection enabled, but nearby world lights
can cast them across the sky. UI preservation mode draws the HUD afterward.

The original restrained look is preserved in `Subtle.ini`. Select that preset
in the ReShade overlay, or copy it over `ClassicEnhanced.ini` while the game
is closed. The new shadow, exposure, grade, and vignette controls are disabled
in that preset, and the original glow radius is restored.

## Preserve the sky

**Preserve original sky colors** is enabled in the dramatic preset. The depth
mask excludes background pixels from exposure, shadow lift, vibrance, color
grading, sharpening, vignette, and bloom generation. Bloom from foreground
lights can still spread over the sky, preserving a natural halo at silhouettes.
Disabling the option restores full-frame grading. If depth is unavailable,
protection leaves the frame ungraded instead of recoloring the sky.

This is specific to the verified dgVoodoo2 2.87.5 / D3D11 path. Its sampled
depth values cannot be compared as ordinary floats: far-scene values appear
as NaNs. A live bit-pattern probe showed sky high bits `0xffffe0` and geometry
below that range. The shader compares the packed bits with point sampling.
ReShade `[DEPTH]` uses `DepthCopyBeforeClears=1` and the default
`DrawStatsHeuristic=0` to retain the scene depth. Numeric float comparisons
hid the far-scene geometry; bit-pattern inspection revealed it.
[ReShade depth texture semantics](https://github.com/crosire/reshade-shaders/blob/slim/REFERENCE.md)
and the pinned runtime's `examples/09-depth/generic_depth_addon.cpp` describe
the underlying texture binding and selection configuration.

In standard mode, depthless sprites and HUD drawn over the sky can bypass grading. HUD over
geometry can still receive the filter. A neutral-dark tone guard keeps flat
briefing-panel backgrounds from showing the underlying depth silhouette; it
also reduces lifting of similarly dark neutral object pixels. This is not a
complete HUD mask. Other scenes, distant billboards, camera motion, and wrapper
versions need further validation; performance has not been benchmarked.

## Preserve the UI

`game/classic-enhanced` now uses the optional `ClassicUI.addon32` built from
our original `tools/classic_ui_addon.cpp`. It requires the official full-add-on
ReShade 6.8.0 runtime. The source game and copied executable remain unchanged
on disk. A signature-checked, six-byte in-memory hook at `0044B3C7` applies
the effect after world rendering (`43CCF0`) and before HUD/target-preview drawing.
The hook preserves CPU registers, flags, x87/SSE state, and the D3D11 context.
Unknown signatures, missing depth, or unsupported targets skip the effect.
Menus also skip the effect. Exiting unloads the hook; unloading only restores
the instruction when the bytes still match our own patch.

Sky protection uses the native typed D16 view at this stage, through the
separate `AOA_WORLD_DEPTH` binding. This avoids dependence on ReShade's final
depth selection. No fixed screen rectangles or UI color heuristics are used.
Transparent UI areas naturally show the enhanced world behind them. Labels
rendered as part of the world (for example a station name) still receive the
world effect. Tested in the offline mission, not network play or every menu.

Build with Python containing `ziglang==0.16.0`, using the official
[v6.8.0 source archive](https://github.com/crosire/reshade/archive/refs/tags/v6.8.0.zip).
Download the [full-add-on installer](https://reshade.me/downloads/ReShade_Setup_6.8.0_Addon.exe)
without running it. Both archives are hash-pinned in `classic_ui.py`.

```powershell
.venv\Scripts\python.exe tools\classic_ui.py build builds\classic-ui\ClassicUI.addon32 --sdk builds\reshade-capture-sdk-6.8.0\source.zip
python -I tools\classic_ui.py install game\classic-enhanced --setup builds\reshade-6.8.0-capture-review\ReShade_Setup_6.8.0_Addon.exe --addon builds\classic-ui\ClassicUI.addon32
```

Close the game before installing/restoring. The install command saves the
previous runtime, shader, settings, and manifest under `_classic_ui_backup`.
To restore the previous standard mode, use `classic_ui.py restore
game\classic-enhanced`. The backup is retained under a timestamped name.
The usual `classic_enhanced.py off/on` still disables/enables the entire effect.

For an automatic **complete-UI comparison**, enter flight with effects enabled,
then run:

```powershell
python -I tools\classic_ui.py capture game\classic-enhanced
```

The add-on captures one live frame with effects off, restores the prior toggle,
and captures the following frame with effects on. The report explicitly labels
these as consecutive frames: animation and moving objects can differ. Original
PNG bytes are preserved. This replaces the final-screen Print Screen pair in
UI mode; that older method cannot show a pre-HUD effect correctly.

## Capture an exact before/after comparison

This section applies to **standard mode only**. Use the command above in UI mode.

The preset now configures **Print Screen** to save two PNGs from the **same
rendered frame**, before and after the filter, under the experiment's
`comparison-captures` folder. Effects must be enabled and Split preview off.
The ReShade overlay is excluded and a copy of the capture preset is saved.
This avoids camera or animation changes between separate screenshots.

To automatically build a comparison whenever a pair is captured, run this
before starting the experiment (requires Pillow from `requirements.txt`):

```powershell
python -I tools\compare_classic_capture.py game\classic-enhanced --configure
```

This sets a local ReShade screenshot callback to run the comparison script
with the current Python executable. The previous configuration is backed up as
`ReShade.ini.before-auto-comparison`. If the renderer is already running,
restart the experiment to load these settings. After entering flight, press
Print Screen. The resulting report is written to
`work/classic-enhanced/AOA_<capture timestamp and count>/index.html`.

The report includes side-by-side full-frame images and a movable comparison
divider. `original.png` and `enhanced.png` are byte-for-byte copies of the
captures; no image retouching or simulated filter is used. `comparison.json`
records image hashes, dimensions, pixel-change measurements, and preset values.
The helper rejects identical frames, mismatched dimensions, missing presets,
disabled Classic Enhanced, and captures with Split preview enabled.

To build a report from the latest existing pair manually:

```powershell
python -I tools\compare_classic_capture.py game\classic-enhanced\comparison-captures
```

Automatic report generation was checked with labeled synthetic fixtures and
then three actual offline-mission capture pairs (see verification below).
The game must have entered its 3D renderer before ReShade can capture a frame.

## Prepare on another machine

Close the source game before copying. Use a prepared 2.9.2 folder with the
project's dgVoodoo2 2.87.5 wrapper. Existing client patches, pilots, settings,
and textures are copied exactly; preparation does not update or certify them.

Download the **standard** [ReShade 6.8.0 installer](https://reshade.me/downloads/ReShade_Setup_6.8.0.exe)
from [the official ReShade site](https://reshade.me/) into a new, empty folder,
for example `builds\reshade-6.8.0-classic`. Do not run the installer.

```powershell
python -I tools\classic_enhanced.py prepare game\classic-enhanced --source game\2.9.2 --setup builds\reshade-6.8.0-classic\ReShade_Setup_6.8.0.exe
python -I tools\classic_enhanced.py check game\classic-enhanced
python -I tools\classic_enhanced.py launch game\classic-enhanced
```

Python 3.12+ is required. The tool refuses an existing destination, a destination
inside the source, linked source entries, existing injectors, and an unrecognized
installer. It copies into a new folder, verifies the copy and source hashes,
extracts only `ReShade32.dll` as `dxgi.dll`, and installs our shader and preset.
Only the copy's wrapper output API is changed to `d3d11_fl11_0`; its other
wrapper settings remain intact. An interrupted preparation may leave an
incomplete destination; use a new destination for the next attempt.

Pinned installer SHA-256:
`207aea16205fbf952bc8fe1879966672454cf04002e7ad34237c7990a5b3c0b4`.
The installer was downloaded from the official HTTPS endpoint. Windows reported
an untrusted certificate root on the validation machine, so this is a content
pin, not a claim that Authenticode chain validation passed.

`_classic_enhanced.json` records the source file hashes and runtime identity.
`check` verifies the copied executable identity, wrapper DLLs, runtime identity,
and presence of the preset/shader. It is not a flight or shader compilation test.
No game files or third-party runtime binaries are committed to the repository.

## Disable or return to the original

Close the experiment before changing runtime state:

```powershell
python -I tools\classic_enhanced.py off game\classic-enhanced
python -I tools\classic_enhanced.py launch game\classic-enhanced
```

`off` renames the verified injector so Windows will not load it on the next
launch. `on` restores it. The experiment retains its D3D11 wrapper setting in
either state, making comparisons use the same renderer. To return to your
previous setup, close the experiment and launch your original game folder.
Pilots/settings changed in the experiment are not synchronized back.

## Verification status — 28 October 2026

### Cinematic light streaks revision

The final shader and its pre-HUD permutation compiled in the live offline
renderer without warnings. The 11:14:10 capture shows thin horizontal flares
on bright ship highlights and selected station lights. Six sampled regions
(briefing interior, damage panel, systems panel, radar, and two open-sky regions)
have zero pixel/channel difference between effects off and on. This is not a
performance benchmark or verification of every combat scene.

`work/classic-enhanced/light-streaks/index.html` compares the previous glow
treatment with the new streaks, including a magnified ship detail. These are
separate live runs of the same view, so animation can differ. The page links
to the final consecutive off/on capture. All source PNG bytes are unchanged.
The main experiment and running capture copy both use the final settings.
See [streak evidence](../evidence/2.9.2/classic_enhanced_streaks_20261028.json).

### UI preservation revision

The full-add-on shader compiled and ran in the offline mission at 1920 × 1200.
A solid-red diagnostic established the world/HUD boundary, then was removed.
The final live captures at 10:05:20 and 10:07:31 include the original interface.
Damage, systems, radar, and two sky regions match exactly between the off/on
frames; the station and ship retain substantial color/light changes. The
briefing's opaque interior is unchanged. Transparent HUD backgrounds can show
changes in the world beneath them. Target models can animate between captures.
Four installer tests cover archive/add-on/signature rejection and byte-exact
restore. Runtime hooks and rendering were checked live rather than emulated.

Local report: `work/classic-enhanced/ui-preserved-verified/index.html`.
See [UI evidence](../evidence/2.9.2/classic_enhanced_ui_20261028.json).

### Sky preservation revision

Three new live same-frame pairs were captured at 09:15:06, 09:15:12, and
09:15:18 after the shader compiled without warnings. Two nebula regions were
checked against their same-frame originals while foreground ship/station
regions retained substantial changes. The final first pair was visually
inspected, including the briefing panel. Local incremental report:
`work/classic-enhanced/sky-preserved/index.html`; exact original/filtered report:
`work/classic-enhanced/AOA_2026-10-28_09-15-06_0/index.html`.
See [sky-preservation evidence](../evidence/2.9.2/classic_enhanced_sky_20261028.json).

### Radiant lights revision

The new light layer compiled without warnings in the live offline renderer.
Three new 1920 × 1200 same-frame pairs were captured at 08:42:45, 08:42:51,
and 08:42:57. Visual inspection shows brighter blue-white station lights and
halos on ship highlights. HUD text is readable in the inspected view but has
more glow. Two extra half-resolution passes have not been performance benchmarked.

`work/classic-enhanced/radiant-lights/index.html` compares the previous dramatic
capture with the radiant-light capture. These are separate runs of the same
camera view, so minor animation differences are possible. The page also links
to the new exact same-frame original/filtered comparison. Captures are unedited.
See [light-glow evidence](../evidence/2.9.2/classic_enhanced_lights_20261028.json).

### Dramatic revision

After feedback that the first pass was too subtle, the dramatic preset above
became the default. It compiled in the x86 D3D11 smoke harness and inside the
offline game, then produced three new 1920 × 1200 same-frame capture pairs.
The first pair visibly reveals the station hull and nebula, brightens asteroids,
and gives the ship a much stronger green/yellow finish. HUD text stays readable
in this view, though the filter also increases HUD brightness and reveals
banding in the original nebula texture. Performance is not benchmarked.

New local reports are under `work/classic-enhanced/`:
`AOA_2026-10-28_08-30-34_0/index.html`,
`AOA_2026-10-28_08-30-40_0/index.html`, and
`AOA_2026-10-28_08-30-46_0/index.html`.
See [dramatic capture evidence](../evidence/2.9.2/classic_enhanced_dramatic_20261028.json).

### Original subtle revision

- Separate local game copy prepared; source hashes and copied executable matched.
- ReShade FX compiled successfully in a 32-bit D3D11 GPU smoke harness at
  1280 × 720 / feature level 11.0; 240 frames presented and runtime shut down.
- Standard ReShade 6.8.0 loaded through dgVoodoo and compiled the shader inside
  the offline mission at 1920 × 1200.
- Three real before/after frame pairs were captured and automatic comparison
  reports generated. Each pair has identical scene geometry and timing.
  The first pair changes 46.673% of pixels, with mean absolute channel change
  0.621 on a 0–255 scale: this preset is deliberately subtle.
- Visual inspection of the first pair found richer green ship paint and blue
  HUD colors, with readable text. The station remains very dark. This is an
  initial review of one view, not full visual or performance acceptance.
- Live key toggles and frame-time impact remain unverified. Computer-use
  screenshot capture consistently timed out; automated screenshot key taps
  were not recognized by ReShade in this session.

### How the automated live capture was obtained

Only the temporary `game/classic-capture` copy was changed for capture.
Its login and station **dialog resources**, not executable code, expose native
Offline/Play controls with Alt+O / Alt+P accelerators and `WS_EX_APPWINDOW`.
Computer use then activated these controls to enter the offline mission.
The regular `game/classic-enhanced` executable was not changed.

For deterministic capture, the private copy used the official 6.8.0 full-add-on
runtime and [classic_capture_addon.cpp](../tools/classic_capture_addon.cpp).
The helper calls the runtime's screenshot API immediately before and after
effects at rendered frames 180, 540, and 900. It does not inject input or alter
game state. A synthetic D3D11 test confirmed the callback captures different
before/after pixels before it was used in the game.

The helper was built with Zig 0.16.0 C++ targeting `x86-windows-gnu`, using
the official ReShade v6.8.0 include headers, `-std=c++20 -O2 -shared -s` and
`-luser32`. Its DLL is installed as `AutoPair.addon32` **only in the diagnostic
copy**. No runtime/helper binaries or captured game images are committed.
The default experiment continues to use the standard runtime.

Capture runtime package:
[official ReShade 6.8.0 full-add-on download](https://reshade.me/downloads/ReShade_Setup_6.8.0_Addon.exe),
SHA-256 `afe4c8f13048306307983b8b3d41d5bf00a86820440b0e57dea10950e1176445`.
Runtime DLL SHA-256:
`da430e0a9c6eecefa0d1b27d05e16c426fb5d04e808b194d914eaac4b31bc0f8`.

Reports are saved locally as
`work/classic-enhanced/AOA_2026-10-28_08-20-01_0/index.html`,
`AOA_2026-10-28_08-20-07_0/index.html`, and
`AOA_2026-10-28_08-20-13_0/index.html` under the same parent.
See [capture evidence](../evidence/2.9.2/classic_enhanced_capture_20261028.json)
for hashes, measurements, and the exact scope of verification.

References: [ReShade FX language](https://github.com/crosire/reshade-shaders/blob/slim/REFERENCE.md),
[official setup implementation](https://github.com/crosire/reshade/blob/v6.8.0/setup/MainWindow.xaml.cs).
