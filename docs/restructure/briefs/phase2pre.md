# Phase 2-pre: make the layers real

Phase 1 moved every file but 17 imports still break the layering rule
(PLAN.md section 2, rule 1). They are listed in `tests/test_layering.py`
`KNOWN`. This task removes all of them by moving shared facts and library
code to the layer they belong in. When you finish, `KNOWN` is empty.

It runs before the three package rebuilds (client, host, research) so those
can work in parallel without touching the same files. Keep it to the list
below: no redesign of the patch engine, the server or the tools.

You may edit anything under `aoa/`, `tests/`, `archive/`, `tools/` (shims
only), and docs that name a moved module. Patch bytes and server command
lines must not change: `tests/snapshots/*.json` stay the same blobs.

1. **`aoa/builds.py` (new, standard library only).** The known client and
   installer hashes, keyed by version ("2.9.2", …), and
   `require_build(data_or_path, version)` that raises `ValueError` with a
   one-line message. A test checks them against `manifest/downloads.json`
   and `config/client-2.9.2.json` where those record the same file. Replace
   the literal copies of the 2.9.2 hash and every import of `PRISTINE_292`
   from `aoa.client.base` outside `aoa/client/` (audit R14 lists them).
   Replace the two `assert`-based hash checks with `require_build`.
2. **`aoa/formats/pe.py` (new, standard library only).** The PE section
   mapper (virtual address to file offset, read at address) that
   `aoa.analysis.pe_util` and `aoa.research.version` each implement.
   `aoa.formats.aoapack.builtin_key` uses it, so `aoapack`, `make_map`,
   `make_object` and `texture_pack` import without capstone or pefile.
   `pe_util` keeps the disassembly helpers and builds on the new mapper.
   Add a game-free test with a synthetic image.
3. **`aoa/maps/registry.py` (new, pure data).** The map table (`MAPS`,
   `MAP_NAMES`, `marker`, `spawn`) leaves
   `aoa/client/patches/online_terrain.py`, together with the per-map notes
   and a `playable` / `component` / `empty` kind from `map_viewer.NOTES` and
   `docs/STATUS.md`. `online_terrain` imports the table to build its cave;
   the cave bytes must be identical (the patch snapshot proves it). `host`,
   `maps` and `launchers` import the registry, never the patch.
4. **Audit code out of `aoa/maps`.** `turret_hierarchy.py`, `warp_routes.py`
   and `arena1a_audit.py` keep only what kept code imports (`hierarchy()`,
   `routes()`, and what `check_terrain_nodes` needs). Their audit command
   lines, with the emulator and disassembler imports, move to
   `archive/analysis/`. `movement_update` and the other motion codecs that
   `warp_routes` took from the server move to `aoa/protocol/motion.py`, which
   ends the cycle `host.server -> host.warp_trial -> maps.warp_routes ->
   host.server`. If `routes()` itself needs the emulator, it belongs in
   `aoa/emulation/` and the server must get its warp data another way
   (committed data under `aoa/maps/`): say which you chose and why.
5. **`aoa/emulation/emu.py` is a library.** Its 2.7.1-only command line
   moves to `archive/analysis/emulate_codec_271.py` (audit R5).
6. **No suite imports another suite.** The five that still do
   (`test_solid_world_render`, `test_world_detail`, `test_turret_trial`,
   `test_warp_trial`, `test_client_launcher`/`test_prepare_client`) get
   their shared classes and `synthetic_pristine` from `tests/support*.py`.
7. **Old names in text.** Docstrings, usage lines, error messages and
   comments that still say `tools/<old>.py` name the real command
   (`tools/<shim>.py` where a shim exists, else
   `tools/run.py aoa.<package>.<module>`). The `about` text inside the
   snapshot files may be regenerated only if nothing else in them changes.

Gate:
- `KNOWN` in `tests/test_layering.py` is empty and the test passes.
- `python3 -I tools/test.py --tier ci` passes; both snapshot blobs are
  unchanged apart from item 7's `about` text.
- Suite outcomes with and without `requirements.txt` match
  `docs/restructure/phase1-tests.md`, except suites that now import without
  optional packages; record the new table as `docs/restructure/phase2pre-tests.md`.
- `test_imports` shows `aoa.formats.*`, `aoa.protocol.*`, `aoa.maps.registry`,
  `aoa.maps.make_map`, `aoa.maps.make_object`, `aoa.client.texture_pack` and
  everything under `aoa/host/` importing with the standard library only.
- pyflakes reports no undefined names.
