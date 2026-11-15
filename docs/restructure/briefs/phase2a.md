# Phase 2a: client patches as data, one engine, one undo

Rebuild the inside of `aoa/client/` so the 22 patches share one shape and
one engine (PLAN.md section 2, rule 4). The bytes every patch writes must
not change: `tests/snapshots/patch_regions.json` stays the same blob, and
`tests/test_patch_layout.py` passes without `--update` after every commit.

Files: everything under `aoa/client/`, `aoa/launchers/client_launcher.py`
(only where it reads the patch list or calls `prepare`), the client suites
in `tests/`, `tools/` shims for removed commands, `archive/`, and the docs
`docs/client-setup.md`, `docs/texture-pack.md`, `docs/asteroid-rendering.md`.
Not `aoa/host/`, `aoa/maps/`, `aoa/research/`, `aoa/analysis/` (other agents
are working there in parallel).

Design (audit `client.md` section 4 has the detail and each module's delta):

1. **`aoa/client/patches/base.py`**: `Region(va, old, new, kind)` and
   `Patch(id, since, policy, option, label, group, default, requires,
   conflicts, reads, data, regions, legacy)` as frozen dataclasses, plus
   generic `state(patch, image) -> installed variant id or None` (raises on
   a partial or unknown site), `apply(patch, image, on)` (strips any legacy
   variant first) and one `va_to_offset` checked once against the pristine
   section table (uses `aoa.formats.pe`). `policy` is `always` or `option`.
   `group` is one of fixes, visual, experimental (the launcher's sections).
2. **Every patch module exports `PATCH`** (or `PATCHES` for a module that
   owns several) and nothing else that callers need: the copy-pasted
   `state`/`configure` functions go. The five inline or unnamed patches get
   homes and ids (`logger-size-v1`, `logger-lock-v1`, `zero-time-physics-v1`,
   `background-network-v1`, `archive-terminator-v1`). `third_person` and
   `own_ship_menu` express older variants as `legacy`. The chase camera
   trio (`third_person`, `own_ship_model`, `own_ship_menu`) is one option
   through `requires`.
3. **`aoa/client/layout.py`**: every code-cave and runtime-data reservation
   in one table (start, size, owner). Modules take their addresses from it.
   A game-free test asserts reservations are disjoint and inside the padding
   bounds, replacing the by-comment arrangement between `third_person` and
   `own_ship_menu` (audit C5).
4. **`aoa/client/patches/__init__.py`: `REGISTRY`**, the ordered list. It is
   the only source for: `inspect`, `configure` (strip order and apply order
   derived from the list, with `requires` and `conflicts` enforced in one
   place), the `prepare` command-line flags (`--[no-]<option>` generated,
   under a `prepare` subcommand; keep today's flag names as aliases),
   the launcher's checkboxes and groups, `check`'s requirements, and a
   `patch level` table (`since`) that replaces the bare `PATCH_VERSION`
   constant's role in docs. `prepare(exe, options: dict, station=None)`
   keeps phase 0b's rule: an option not named keeps its installed state.
5. **Declared interactions** (audit C4): `distant-world-objects-v1` rewrites
   two constants that the asteroid and solid-world patches read. Declare it
   through `reads` and the `const` regions, and add a test that states the
   combined effect. Fix the doc sentence that claims otherwise.
6. **One undo.** The six per-tool installers and their command lines are
   removed (phase 0b already made them thin). Backups and records live in
   one place per game folder; keep reading the existing `.setup-original`
   and `_client_setup.json` so prepared clients keep working. Do not delete
   a user's old `.before-*` files; `check` may mention them.
7. **Experiments.** `render_clock_experiment` is byte-identical to
   `frame_clock` and `render_culling_experiment` is superseded by
   `visibility_fix`: repoint their importers (`aoa/emulation/render_pipeline`
   is not yours to edit: leave a compatible name it can import and report
   it), move the experiments and the offline-baseline-only tests to
   `archive/offline_baseline/`, and merge their game-free checks into
   `test_frame_clock` and `test_visibility_fix`.
8. **Tests.** Split each client suite into a game-free part (registry
   invariants, cave emulation on the synthetic image where possible) that
   joins the CI tier, and a needs-game part that skips with one shared
   helper. Add the suites that no gate ran (`test_menu_aspect`, and the
   converted `test_physics_timestep`) to the local tier.

Adding a patch after this task must mean: one new module exporting `PATCH`,
one line in `REGISTRY`, one reservation in `layout.py`. Say in your report
whether that is true and what else is still needed.

Gate: patch snapshot blob unchanged; `tools/test.py --tier ci` passes; a
game-free test shows `prepare` on the synthetic image produces byte-identical
output before and after this task for at least eight option sets (generate
the expected images at your starting commit and commit only their hashes);
layering test passes with `KNOWN` empty; pyflakes clean. Not verifiable
here: the patched game running, the launcher window. Say so.
