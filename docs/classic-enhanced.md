# Classic Enhanced visual experiment

An opt-in color filter for Ace of Angels 2.9.2: slightly richer muted colors,
gentle contrast, bounded sharpening, and a faint glow around bright pixels.
The original palette stays neutral. This is an SDR experiment; it does not
add HDR lighting or new texture detail.

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
- Adjust Color vibrance, Gentle contrast, Detail sharpening, or Highlight glow
  in that overlay. These changes belong to the experiment's local preset.

Start by comparing a shadowed hull, a bright weapon/engine effect, and the
smallest HUD text. Check distant targets remain visible, dark space stays
dark, highlights retain their color, and turning/firing remains smooth.

The defaults are vibrance **0.14**, contrast **0.08**, sharpening **0.12**,
glow **0.06**, and glow threshold **0.78**. The glow uses two quarter-resolution
targets; sharpening is capped at 0.015 per channel to limit halos. These are
conservative starting values, not visually approved settings.

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

- Separate local game copy prepared; source hashes and copied executable matched.
- ReShade FX compiled successfully in a 32-bit D3D11 GPU smoke harness at
  1280 × 720 / feature level 11.0; 240 frames presented and runtime shut down.
- The experiment client opened to its startup dialog. Its renderer had not
  started, so this does **not** establish dgVoodoo/ReShade injection in flight.
- In-game color/HUD acceptance, toggle behavior, and frame-time impact remain
  pending. The startup dialog could be read through accessibility, but screenshot
  capture timed out. No live visual approval is claimed.

References: [ReShade FX language](https://github.com/crosire/reshade-shaders/blob/slim/REFERENCE.md),
[official setup implementation](https://github.com/crosire/reshade/blob/v6.8.0/setup/MainWindow.xaml.cs).
