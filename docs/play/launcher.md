# Player window and client options

How the player window chooses and applies the client options. Every patch
behind them, its addresses and its checks: [reference/client-patches.md](../reference/client-patches.md).

## Client launcher and visual options

Double-click `Play.cmd`, or run `python -I tools/client_launcher.py
[GAME_FOLDER]`. The player window (`aoa/launchers/play_app.py`, rebuilt 16
November 2026) opens on a setup checklist until the game is ready, then has
three tabs: **Play**, **Join a friend** and **Options**. The game folder is
remembered in `work/settings.json`, shared with the host window. The first-run
steps are in [play.md](README.md#3-double-click-playcmd-and-follow-the-checklist).

The **Options** tab reads the installed settings each time the game folder is
read. Its checkboxes come from the patch registry
(`aoa/client/patches/__init__.py`), in the registry's groups, with player
wording and a hover text from `aoa/launchers/catalog.py`:

- **Fixes (recommended):** widescreen ship-selection screen, smoother frame
  timing, the visibility fix, power-up pickups.
- **Visual extras:** distant objects, the F2 chase camera and F4 orbit view
  (with the player's own ship).
- **Experimental:** asteroid-only or solid-world meshes, station-only or
  full world detail, 32-bit textures.
- **Graphics quality (needs the wrapper):** anti-aliasing, anisotropic
  filtering, point-sample preservation, generated mipmaps, per-pixel
  lighting, and the replacement texture pack when one is installed or saved.

Ticking one side of a declared conflict turns the other off and says so in a
line under the boxes. Turning off the chase camera also removes its two
own-ship rendering patches. **Recommended** sets the registry defaults;
**Original visuals** keeps the fixes and turns every visual and experimental
option off (the original visual behavior with the compatibility layer, not
an unpatched executable). **Apply** saves and verifies; nothing changes until
then. **Restore the original game** runs `prepare undo`; **Install JRMAP
terrain** runs the `map_viewer.py install` conversion. Close the game first:
changes are blocked while AOACLIENT.EXE is running.

Unchecked wrapper effects use application-controlled values (or `false` for
the two boolean options). Existing custom enabled values, such as 4x AA, are
preserved until their checkbox changes. Missing wrapper or replacement pack
options are disabled.

Disabling an installed texture pack saves hash-checked copies as
`<ARCHIVE>.launcher-texture-pack` and `_launcher_texture_pack.json` in the game
folder, then restores the original archives. Re-enabling restores those saved
images, so the original upscale source folders are not needed. The existing
`<ARCHIVE>.before-texture-pack` backups are retained. Do not delete the launcher
cache if you want to re-enable the pack. No assets are downloaded.

If the client carries an older variant of a patch, the window shows that
option as on and **Apply** updates it; the checklist's fixes step offers the
update when the recorded patch level is older. The window has no control for
the `--experimental-protection` probe, which works only with a loopback
server: pointing the game at another PC (Play on a friend, or Join) switches
the probe off. **Play** and **Join** change only the server address; every
other option keeps its installed state.

Apply preflights the selected patches and rolls back changed files if it
fails (`aoa/launchers/client_launcher.py`). Covered without the game by
`tests/test_client_launcher.py` and `tests/test_launcher_logic.py` (the
synthetic client); the rest of that suite needs the game. The window itself
has been opened only on Linux under a virtual screen
([status](../STATUS.md#implemented-but-not-tested)). This does not replace
in-flight visual/performance acceptance for the individual effects.
