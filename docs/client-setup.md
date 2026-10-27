# Supported local client preparation

Use your own 2.9.2 installation or installer. These tools distribute no game
assets and never execute the installer. Windows 11 is the locally exercised
platform; a clean Windows 10/11 installation still needs validation. This
prepares the local diagnostic client, not a released internet game.

## Prepare an existing working folder

Close the game first. Run from the repository root:

```powershell
.venv\Scripts\python.exe -I tools/prepare_client.py prepare game/2.9.2/AOACLIENT.EXE --station localhost
.venv\Scripts\python.exe -I tools/prepare_client.py check game/2.9.2/AOACLIENT.EXE
.venv\Scripts\python.exe -I tools/prepare_client.py launch game/2.9.2/AOACLIENT.EXE
```

`prepare` accepts the exact original 2.9.2 executable, or the recognized
stability/localhost/physics variants. It composes the logger allocation fix,
recursive logger lock, zero-time physics guard, background-network fix,
archive terminator, ship-menu aspect fix, cursor-warp fix and Station lookup in memory. The background-network fix (`0x446EAF`, two bytes)
lets an inactive flying client keep servicing the network. It is verified
with the dgVoodoo windowed wrapper only, not native exclusive fullscreen
([findings 9.24](findings.md#924-background-client-network-stall-and-fix-21-october-2026)).
The archive terminator (`0x52A6E3` plus a 24-byte cave at `0x58B440`) makes
the decompressor allocate one extra byte and NUL-terminate its output. This
fixes the intermittent crash on arena entry
([findings 9.29](findings.md#929-arena-join-crash-unterminated-archive-text-21-october-2026)).
It verifies the whole image after normalizing only those known patch sites.
Unrecognized binaries, altered code/caves, and conflicting DirectX wrappers
fail before the executable changes. Native DirectX is allowed; installed
wrappers must match the verified dgVoodoo2 2.87.5 DLLs.

The source executable SHA-256 is
`4b6c35e2b3ab473bd98c0afa6538079ee78678d85c28406c07bc27a08cc78c7e`.
Patch version 12 is recorded in `_client_setup.json`, with input/output and
undo-backup hashes, hostname, patch IDs, wrapper and transaction status.
`check` requires the physics guard, background-network fix, archive
terminator, ship-menu aspect fix, cursor-warp fix and online terrain hook, so an older setup must be prepared again. That upgrade happens in place and
keeps the original undo backup. The prepared localhost executable is
`78c5bd395c436776742e632d0cde8404aec8c38a37aeafcb55be481ad284680f` (patch version 12,
no optional rendering patches).
The existing `.orig` and `_patches.json` research artifacts are left intact.

The online terrain hook activates only on an explicit flight-entry marker sent
by the `--experimental-terrain` server option: `AR1A` for Arena1a, or `MAP`
plus an index for any other recovered map. Since patch version 11 it is
`online-terrain-v2`. A v1 (`online-arena1a-v1`) client fails `check` until it is
prepared again. Patch version 18 makes it `online-terrain-v3`, which also
draws the map's safe zones as the original translucent blue cubes; they were
never built because the client sets them up before the hook loads the map
([findings 9.42](findings.md)). A v2 client likewise fails `check` until
prepared again. Ordinary servers keep the normal flight-entry behavior. See
[the online probe](arena1a.md#online-terrain-probe-22-october-2026) and
[viewing every map](map-viewer.md) for verification limits.

The ship menu uses matching aspect-aware layout and projection hooks at
`0x463D06` and `0x4652A1`. Its authored 4:3 layout now fits widescreen viewports.
Clipping and first-entry selection were verified at 1920x1080, 125% Windows
scale. Emulator checks cover five viewport sizes. A separate panel-redraw
issue remains under investigation; this patch does not change flight rendering.
Smoother motion (`frame-clock-v1`, patch version 13, on by default; opt out with
`--no-frame-clock`) replaces the ~15.6 ms `GetTickCount` game clock with a
millisecond QPC clock. It also stops the background wakeup timer from drawing
extra frames between main-loop frames. At 60 Hz, game-time steps went from 15/16
ms with periodic 31 ms jumps to an even 16/17 ms, and background windows still
render from the timer ([findings 9.35](findings.md)). The older offline-only
QPC experiment tool remains for the isolated baseline.

Bounded visibility math (`visibility-math-v1`, patch version 14, on by default;
opt out with `--no-visibility-math`) keeps out-of-range values out of the
`acos`/`asin` calls that decide whether an object is on screen. Objects
directly behind the camera are no longer counted as visible, and a camera
inside an object's bounds gets finite values. Your own ship stays hidden as
before ([findings 9.36](findings.md)).

Third-person view (`third-person-camera-v1`, patch version 15, on by default;
opt out with `--no-third-person`): **press F2 in flight** to switch between
the cockpit and a chase camera 420 units behind and 100 above your ship.
Press F2 again to return. This turns on a chase camera that is already in
the 2.9.2 renderer but never enabled. The patch also culls the scene from
the chase eye so your own hull is drawn ([findings 9.37](findings.md)).
Patch version 16 adds `own-ship-model-v1`, which gives your own ship its 3D
model and keeps it visible with F2 on; without it the camera moved but
nothing was drawn ([findings 9.39](findings.md)). Patch version 17 adds
`own-ship-menu-model-v1`: after switching ships through the in-flight fighter
menu, the menu's preview had hidden that model's parts, so the new hull did
not show ([findings 9.41](findings.md)). F2 has no default binding. Confirmed
on screen for the Ym Khtat and for a Zkole picked from the fighter menu.

Power-up pickups (`powerup-pickup-v1`, patch version 19, on by default; opt
out with `--no-powerup-pickup`) let you pick up the power-ups a host places
with `--powerup-zones` (JRMAP's zones; [findings 9.44](findings.md)). 2.9.2
made power-ups non-collidable, and a taken one never turned its model back
on. The patch marks power-ups from the server's spawn message collidable
(22-byte cave at `0x58B2C0`). It also makes the 5 s reappear timer show the
model again, in place at `0x49ACC2`. Older clients still see power-ups but
cannot take them.

The cursor-warp fix (`cursor-warp-origin-v1`, patch version 12) stops dragged
in-game panels from jumping to the lower-right corner. The client caches its
window origin from `WM_MOVE` as unsigned 16-bit values; live clients cached
65535,65535 for a window at 0,0, so each `SetCursorPos` warp landed in the
corner. The hook at `0x4EAD16` (60-byte cave at `0x58B300`) asks Windows for
the current origin with `ScreenToClient`, and keeps the old arithmetic only if
that call fails. The other warps through the same function (for example
flight-mode mouse centering) use the same origin. See [findings 9.34](findings.md#934-dragged-panels-stick-to-the-lower-right-corner-23-october-2026).

An optional `--experimental-protection` preparation flag adds the localhost
explicit-state prototype. It is off for ordinary inputs and preserved when
already installed; `--no-experimental-protection` removes only this patch.
It changes `0x81` wire semantics and has not passed the manual client gate.
See [client-extension-gate.md](client-extension-gate.md) before using it.

Optional distant objects (`distant-world-objects-v1`, patch version 20) extend
the world-model horizon to 4,500,000 units and lower the projected-size cutoff
from 5 to 0.5. Enable with `prepare --distant-objects`; disable with
`prepare --no-distant-objects`. Ordinary preparation preserves the installed
choice. The original authored distant LOD remains available below its usual
minimum, so groups have a mesh to draw. More distant draws can cost frame
time; in-flight acceptance and GPU performance are still pending. See
[the rendering notes](asteroid-rendering.md#distant-object-persistence-27-october-2026)
for the exact-undo tool, scope and original-code verification.

`check` verifies the executable, setup record, backup, wrapper and ten static
dependencies against [the pinned manifest](../config/client-2.9.2.json).
That manifest was checked against the hash-pinned original installer.
`SOUNDS.AOA` is separately checked for presence and a 32 MiB size bound: the
client appends decoded WAVs on first run, so its runtime contents are **not
hash verified**. The check reports that exception. This is not the full
required/optional map manifest or a download/install protocol.

`launch` performs the same checks, then starts the executable with the game
folder as its working directory. It does not register ActiveSkin or change
Windows compatibility settings. Missing OCX registration still requires the
current-user registration step in [the Windows runbook](running-on-windows-11.md).

## Change the Station host without removing physics fixes

For the private LAN dogfight, use the short `aoalan` alias and hosts-file mapping
in [the LAN runbook](lan-dogfight.md). It preserves this field's size limit and
requires disabling the optional localhost protection probe.

```powershell
.venv\Scripts\python.exe -I tools/prepare_client.py prepare game/2.9.2/AOACLIENT.EXE --station 127.0.0.1
```

The recovered hostname field supports at most **11 ASCII characters** plus
NUL. Longer hostnames/IPv4 strings and IPv6 are rejected; there is no silent
truncation or unverified relocation patch. This modifies startup discovery
only. It does not add non-loopback server binding or secure internet transport.
The current server remains local. Reapplying preparation is idempotent, and
changing the host preserves both stability fixes and the physics guard.

## Exact undo and interrupted operations

```powershell
.venv\Scripts\python.exe -I tools/prepare_client.py undo game/2.9.2/AOACLIENT.EXE
```

The first preparation saves exact input bytes in
`AOACLIENT.EXE.setup-original`; later changes never replace that backup. Undo
restores those bytes, including any recognized patches present before first
preparation. It does not uninstall wrappers or unregister ActiveSkin. The
launcher refuses an undone client until it is prepared again.

Writes use same-directory temporary files, flush/fsync and atomic replacement.
A pending record contains both allowed hashes before executable replacement.
If the process is interrupted or Windows refuses replacement because the game
is running, the old executable remains intact. Close the game and repeat
`prepare` to finish, or `undo` to restore. An invalid backup or unrecorded
executable change is rejected; do not delete the record to bypass that check.

## Optional asteroid rendering comparison

For the Arena1a distance-dependent shape popping investigation, close the
client and run:

```powershell
.venv\Scripts\python.exe -I tools/asteroid_render.py game/2.9.2/AOACLIENT.EXE
# Exact reversal of only this change:
.venv\Scripts\python.exe -I tools/asteroid_render.py game/2.9.2/AOACLIENT.EXE --undo
```

This opt-in patch keeps `Astr-*` / `Astr_*` models on their original mesh path
out to 900,000 surface-distance units instead of switching to cached billboards
at 61,000. Other model names, asteroid texture LOD, transforms, and assets are
unchanged. Preparation recognizes and preserves the selection; it does not
enable this experiment by default. The adjacent `.EXE.before-asteroid-render`
backup and `_asteroid_render.json` record rollback and installed hashes.

Live read-only snapshots found identical draw buffers across asteroid detail
variants and active asteroid billboards. Original-code tests verify the new
distance gate, unchanged non-asteroid behavior, and exact rollback. This is a
workaround for the cached-image path, not a proven repair of its image-generation
math. The user confirmed the asteroid popping was fixed on 2026-10-22;
performance has not been benchmarked. See `docs/asteroid-rendering.md`.

## Optional solid world model rendering

To extend the accepted asteroid workaround to all world model groups while
retaining the sprite/particle/effect renderer, close the client and run:

```powershell
.venv\Scripts\python.exe -I tools/solid_world_render.py game/2.9.2/AOACLIENT.EXE
# Restore the exact previous client (including asteroid-only mode):
.venv\Scripts\python.exe -I tools/solid_world_render.py game/2.9.2/AOACLIENT.EXE --undo
```

This replaces the asteroid name filter with the same 900,000-unit mesh cutoff
for world models. Texture LOD and other culling gates remain active. The
`.EXE.before-solid-world-render` backup and `_solid_world_render.json` record
rollback and installed hashes. Preparation preserves the chosen mode.
Undo this mode before running the older asteroid-only tool. The user confirmed
stable ships/stations and normal effects in flight; performance is unbenchmarked.

## Optional station full detail

To keep the `Hy_base1` station on its closest mesh and texture detail, close
the client and run:

```powershell
.venv\Scripts\python.exe -I tools/station_detail.py game/2.9.2/AOACLIENT.EXE
# Restore the exact previous client:
.venv\Scripts\python.exe -I tools/station_detail.py game/2.9.2/AOACLIENT.EXE --undo
```

This selects the station's high-detail mesh set at all visible distances.
Other model LODs and effect rendering are unchanged. The backup is
`.EXE.before-station-detail`; hashes are in `_station_detail.json`.
Undo station detail before undoing the underlying solid-world patch.
The reported brightness jump persisted: live inspection identified the
affected sections as `newdock`, not `Hy_base1`. Prefer full world detail below.

## Optional full world mesh and texture detail

With the client closed:

```powershell
.venv\Scripts\python.exe -I tools/world_detail.py game/2.9.2/AOACLIENT.EXE
# Restore the exact previous client:
.venv\Scripts\python.exe -I tools/world_detail.py game/2.9.2/AOACLIENT.EXE --undo
```

This replaces station-only selection with close-up authored mesh/texture
variants for solid world model groups. It also removes child-derived root LOD
cutoffs that still sent distant dock sections to cached images. The original
5-unit small-object threshold, far horizon, texture filtering, and independent
sprite/particle/effect renderer remain active. It is not a global mip-filter
override. All 154 parsed mesh models retain a valid close-up selection.
The exact backup is `.EXE.before-world-detail`; hashes are in
`_world_detail.json`. Undo this layer before the older rendering patches.
Real-flight brightness confirmation remains pending.

## Optional wrapper image quality (23 October 2026)

`game/2.9.2/dgVoodoo.conf` now overrides five `[DirectX]` settings that were
`appdriven`/`false`. No executable bytes change:

| Key | Value | Purpose |
|---|---|---|
| `Antialiasing` | `8x` | MSAA on geometry edges |
| `Filtering` | `16` | 16x anisotropic texture filtering |
| `KeepFilterIfPointSampled` | `true` | Leave intentionally point-sampled textures alone |
| `Mipmapping` | `autogen_bilinear` | The client creates no mip chains (`Logs/DxGfx*.log`), so distant textures shimmer |
| `PhongShadingWhenPossible` | `true` | Per-pixel instead of per-vertex fixed-function lighting |

The exact prior file is `dgVoodoo.conf.before-quality`. Restore it with the
client closed:

```powershell
Copy-Item game/2.9.2/dgVoodoo.conf.before-quality game/2.9.2/dgVoodoo.conf
```

Fresh wrapper installs still use the plain defaults. Flight acceptance and
performance are pending. Phong can change the brightness of some objects.
Autogenerated mipmaps may bleed between images packed into the same texture
atlas. Neither has been observed yet.

## Optional 32-bit textures

The texture loader at `0x562A30` fixes TGA texture views at 16 bits: 24-bit
sources load as RGB565 and 32-bit sources as ARGB4444 (`Logs/DxGfx1.log`).
That covers ship skins, the space background, asteroids, docks, the station
and some HUD/effect images. `tools/texture32.py` rewrites 18 bytes in place
(no code cave). 24-bit sources get depth 32 with alpha 0, and 32-bit sources
get depth 32 with alpha 8. 16-bit sources are unchanged because a 32-bit
surface has no 16-bit converter (`0x411510` is a bare `ret`).

Why 24-bit skins stay opaque: AllocTexture `0x563650` promotes depth 32 with
alpha 0 to alpha 8, so it creates ARGB8888 (`0x554970`). The 32-bit surface's
24-bit converter `0x558B80` ORs `0xFF000000` into every pixel.

```powershell
# Close the client first:
.venv\Scripts\python.exe -I tools/texture32.py game/2.9.2/AOACLIENT.EXE
.venv\Scripts\python.exe -I tools/texture32.py game/2.9.2/AOACLIENT.EXE --undo
.venv\Scripts\python.exe -I tools/test_texture32.py
```

The six tests run the original and patched loader for source depths
0..64, the existing-view bypass and AllocTexture's format dispatch in
emulation. They also check the converter table and installation, idempotence,
exact undo, byte scope and corruption rejection. Normal preparation preserves
the patch (`texture-argb8888-v1`). The exact backup is
`.EXE.before-texture32`, with hashes in `_texture32.json`.
Installed 23 October 2026. In the first live session, all 17 TGA views
loaded as `Format(8888)` with no graphics-log warnings. That covers 24-bit
world/ship skins and the 32-bit HUD/effect images that were ARGB4444.
The user reported that everything checks out
([evidence](../evidence/2.9.2/texture_pack_20261023.json)).

## Optional replacement texture pack

`tools/texture_pack.py` rebuilds `TEXTURES.AOA` and/or `DATA.AOA` from the
pinned originals with named entries replaced by uncompressed 24/32-bit TGAs
(up to 2048²). Some skins live in `DATA.AOA` (for example `natak-t1.tga`,
`salamtex.tga`, `obdgr_t1.tga`). Names are matched case-insensitively in both
archives; prefix `DATA.AOA:` or `TEXTURES.AOA:` to choose. Originals are kept
as `<ARCHIVE>.before-texture-pack`. `_texture_pack.json` (schema 2) records
the installed hashes, and `prepare_client check` accepts exactly those
archives. Install the 32-bit texture patch as well, or the larger skins still
load at 16 bits.

The writer `aoapack.rebuild` keeps the key, header and every other entry's
stored bytes. Replacements use the same codec and cipher as the shipped
entries, which `aoapack.compress` reproduces byte for byte. Each replaced
entry is decoded back with the client's overflow limit before writing.
`tools/test_aoapack_write.py` covers:
- byte-exact identity rebuilds of all eight pinned archives;
- codec reproduction of shipped entries;
- a replacement round trip with untouched neighbours;
- a two-archive pack's install, reinstall, narrowing, tamper detection and exact undo.

```powershell
# Close the client first:
.venv\Scripts\python.exe -I tools/build_texture_pack.py game/2.9.2
.venv\Scripts\python.exe -I tools/texture_pack.py game/2.9.2 --from-dir work/texture-pack/build
.venv\Scripts\python.exe -I tools/texture_pack.py game/2.9.2 --undo
```

Player instructions are in [texture-pack.md](texture-pack.md). No upscaled
image is committed, because they derive from FRE art (see
[NOTICE.md](../NOTICE.md)). Instead, `tools/build_texture_pack.py` makes the
pack on each player's PC:
- It reads the skins named in
  [`config/texture-pack.json`](../config/texture-pack.json) from that
  player's pinned original archives. The archive key comes from their own
  2.9.2 client, at VA `0x5DE678`, accepted only if it matches the pinned
  SHA-256.
- It runs the hash-checked Real-ESRGAN release, extracting only the program
  and the one model it needs.
- It uses one method for all 104 skins: 16 px wrap padding, separate RGB and
  alpha passes, and Pillow Lanczos to 2x.
- Colour and alpha are resized separately. An RGBA resize premultiplies, which
  blackened the colour under transparent pixels and would fringe cutout edges.

`tools/test_build_texture_pack.py` is game-free and runs in CI. It checks:
- header, ID field, footer and row order for both TGA origins;
- alpha kept, including the colour under transparent pixels;
- wrap padding;
- rejection of compressed and truncated sources;
- the zip hash check.

End-to-end (26 October 2026): a clean build of all 104 skins took 23 minutes
on this PC (AMD integrated graphics). Deleting the 30 32-bit outputs and
rerunning rebuilt only those, in 7 minutes. Compared with the hand-built
sets below, the new outputs give PSNR 55 dB (`dock1a`) and 55 dB (`zcs_c`).
`ymkhtat` gives 42 dB, the difference being the added padding.

Installed pack (23 October 2026): the close-up skins of all 31 armed fighter
objects in `.Sco` (faction, engine, guns, hull ≤ 200), 26 skins in total:
23 in `TEXTURES.AOA` and 3 in `DATA.AOA`. Each is 2x: 256² to 512², and
`vagym.tga` 512² to 1024². AlphaFighter (also used by Saksatar and Tholfus)
has no texture. The lower-detail `_b/_c` variants are unchanged.

Every skin was upscaled 4x with Real-ESRGAN (`realesrgan-x4plus`,
ncnn-vulkan 20220424, zip SHA-256 `abc02804…802d`, under ignored `builds/`).
It was then Lanczos downscaled to 2x with ffmpeg and written with the
original 18-byte header fields and TGA footer. A contact sheet and lettering
crops (Eagle `HCS-216`) were checked against the originals.

The generated images and `_entries.json` stay under ignored
`work/texture-pack/fighters/` (FRE copyright). Live check (23 October
2026): the client logged `YmKhtat.tga (512 512 24) Format(8888)` on a 512²
32-bit surface with `Rect(0 0 511 511)`, and the user reported everything
checks out. Only the player's ship was in that session. The other 25 skins
are confirmed only once their log lines appear, and the 1024² Vagym is the
largest untested size. Performance is not benchmarked.

Second pack (25 October 2026): 78 more close-up model skins. These cover
capital ships, docks, stations, asteroids, turrets, tugs, flags, launch bays,
window strips and faction logos (55 24-bit, 23 32-bit with alpha); 70 are in
`TEXTURES.AOA` and 8 in `DATA.AOA`. The installed pack now replaces 104
skins: 96 in `TEXTURES.AOA` (54.6 MB) and 8 in `DATA.AOA`. These hand-built
sets were later replaced by the `build_texture_pack.py` output above.

The second set wraps 16 source pixels of padding around each image before
upscaling and crops it afterwards, so repeating textures keep seamless edges.
Alpha is upscaled as its own grayscale pass with the same model, then
recombined. Left at their originals:
- the 9 space background images (`spc02/03/05_a/b`, `planet02/03`,
  `space4`), where the model invented sharp strands in soft nebulae;
- `galogo.tga` (test cube), which hung the upscaler;
- 5 textures that models reference but no archive contains.

Checked: a contact sheet of all 78, plus crops of the wall grid (no moiré),
an asteroid surface, a dock repeated 2x2 (no seams) and a window strip's
alpha over magenta. None of the second set has been seen in the client yet.

## Fresh extraction

```powershell
powershell -ExecutionPolicy Bypass -File tools/setup_game.ps1 -Dest game/clean-2.9.2 -Station localhost
```

The destination must not already exist. This uses the existing extraction,
current-user OCX registration and pinned wrapper installation, then records
and checks the consolidated configuration. Byte-level preparation, exact
undo, interruption recovery, asset checks and conflict rejection are tested
on temporary copies. A clean-machine installation and actual launcher/UI run
have not been completed for this workflow.
