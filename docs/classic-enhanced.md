# Classic Enhanced visual experiment

An opt-in color filter for Ace of Angels 2.9.2. The default now targets a
dramatic cinematic look: lifted shadow detail, stronger color and contrast,
teal shadows / warm highlights, wider bloom, and a light edge vignette.
This is an SDR experiment; it does not add HDR lighting or new texture detail.

The experiment uses the standard 32-bit ReShade 6.8.0 runtime after dgVoodoo2.
Our self-contained shader needs no shader packs, depth access, or add-ons.
It affects the final image, **including the HUD**. It cannot distinguish a
bright HUD label from an engine light; lower Highlight glow if text looks hazy.

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
The glow uses two quarter-resolution targets; sharpening stays capped at
0.015 per channel to limit halos. Exact black stays black before bloom.

The original restrained look is preserved in `Subtle.ini`. Select that preset
in the ReShade overlay, or copy it over `ClassicEnhanced.ini` while the game
is closed. The new shadow, exposure, grade, and vignette controls are disabled
in that preset, and the original glow radius is restored.

## Capture an exact before/after comparison

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
