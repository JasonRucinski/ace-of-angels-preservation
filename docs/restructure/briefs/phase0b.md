# Phase 0b: client fixes (no files move)

Fix the client-side problems that break or mislead players. Findings are in
`docs/restructure/audits/client.md` (C-numbers) and `audits/launchers.md`
(F-numbers). Patch bytes must not change: `tools/test_patch_layout.py` must
stay green without `--update`.

Files you may edit: `tools/prepare_client.py`, `tools/client_launcher.py`,
`tools/client_launcher.cmd`, `tools/patch_client.py`, `tools/local_station.py`,
`tools/physics_timestep.py`, `tools/third_person.py`, `tools/own_ship_menu.py`,
`tools/asteroid_render.py`, `tools/solid_world_render.py`,
`tools/station_detail.py`, `tools/world_detail.py`, `tools/texture32.py`,
`tools/object_persistence.py`, `tools/install_wrapper.py`,
`tools/make_install.py`, `tools/setup_game.ps1`, and the tests of those
modules. Not docs (list doc changes in your report).

1. **C1 / F-01 (high): an unnamed option keeps its installed state.**
   `prepare()` and `configure()` take every option as `None` = preserve.
   Defaults apply only when the input is pristine or has no recorded options.
   Replace the 14 positional arguments in the `configure()` call with keywords
   (C6). The command-line flags all default to `None`. Add a game-free test
   on a synthetic image (`audits/scripts/client_sim.py` shows how): turn the
   chase camera off, run a prepare that names only the station, and assert
   the camera is still off. Cover all five previously forced options.
2. **C2, C3 (high): the per-tool installers.** `asteroid_render`,
   `object_persistence`, `texture32`, `station_detail`, `world_detail` and
   `solid_world_render` must no longer reset other options, and must never
   report failure after writing. Make each `install()`/`main()` a thin call
   into `prepare()` naming only its own option (C1 then preserves the rest).
   Keep their command lines working for now (phase 2 removes them); keep
   `--undo` meaning "turn this option off". Stop writing the extra
   `.before-*` backups and `_*.json` side records (C12) if, and only if,
   `prepare`'s own backup and record fully cover undo; say which you kept.
3. **C13:** `solid_world_render.configure` and `world_detail.configure` must
   not silently strip their sibling. One rule, enforced in `prepare`:
   requesting both of a conflicting pair is an error naming both.
4. **C8 (medium):** `third_person.state()` and `own_ship_menu.state()` report
   the installed variant, so `inspect()` names the real one and `check()`
   fails on an old variant with "re-run prepare". Follow
   `online_terrain.installed_name` as the model.
5. **C9 / F-22:** the launcher passes `experimental_protection=False` when
   the station is not loopback, with a visible note in its status line.
6. **C11:** command-line flags that only make sense with `prepare` are
   rejected with other actions, not ignored. `RuntimeError` from write
   verification is caught and printed as one line.
7. **C16:** remove the standalone `main()` of `patch_client.py`,
   `local_station.py` and `physics_timestep.py` (they write the executable
   with no setup record and break a prepared client). They stay importable.
   Convert `tools/test_physics_timestep.py` to unittest that skips without
   the game.
8. **C17, C18, F-17, F-18, F-19:** `setup_game.ps1` throws when an explicit
   `-Wrapper` path is missing, uses one Python rule (`.venv`, with a clear
   message if absent) and fixes its synopsis; `client_launcher.cmd` shows
   start-up errors (run `python.exe` and `pause` on a non-zero exit, or catch
   in `main` and show a message box and write `work/logs/launcher.log`);
   `install_wrapper.py` and `make_install.py` get argparse, and
   `install_wrapper` writes atomically and keeps existing `[DirectX]` keys.

Done when the listed tests pass, the patch layout snapshot is unchanged, and
your report lists every doc line that now needs changing.
