# Phase 1: one package, every file moved, behaviour unchanged

Turn the flat `tools/` folder into the `aoa/` package described in
`docs/restructure/PLAN.md` section 2, moving every file exactly as
`docs/restructure/file-map.tsv` says. This phase changes where code lives and
how it is imported. It must not change what any code does. Splitting,
merging and redesign belong to phase 2: if a module is ugly, move it ugly.

You may edit anything in the repo except `evidence/`, `data/`, `manifest/`,
`config/` and the audit reports. Work in stages and commit after each one,
so an interruption never leaves a half-applied move uncommitted.

## Method: script the move

Write `docs/restructure/move.py` (commit it first). It reads `file-map.tsv`
and does the whole move deterministically, so it can be re-run from a clean
tree and reviewed as code:

1. `git mv` every file to its new path; create each package's `__init__.py`
   with a one-line docstring saying what the package holds.
2. Rewrite imports with the `ast` module, not regular expressions on source
   text: for each moved module, map old top-level module names to new dotted
   paths. `import patch_client` becomes `from aoa.client import base`, and
   every reference `patch_client.X` in that file becomes `base.X`.
   `from station_stub import a, b` becomes `from aoa.host.server import a, b`.
   Where the new short name collides with another name bound in that file
   (`server`, `runtime`, `base`, `scene`, `version`, `motion`, `codec`,
   `arena` are likely), import under a role-qualified alias instead
   (`from aoa.host import server as host_server`) and say so in your report.
   No import may keep an old module name as its alias.
3. Remove every `sys.path.insert(...)` line and the imports that existed only
   for it.
4. Replace per-file repo-root computations (`Path(__file__).resolve().parents[N]`,
   `os.path.dirname(__file__)` chains, working-directory-relative repo paths)
   with `aoa.paths.ROOT`. Check every `__file__` use by hand: data files that
   moved with their module (`reel/shots.json`, snapshots) must still resolve.
5. Rewrite strings that name a moved script for a subprocess
   (`"tools/station_stub.py"`, `ROOT / "tools" / name`) to go through
   `aoa.paths.entry("station_stub")`, which returns the `tools/` shim path.

New files:

- `aoa/paths.py`: `ROOT`, `WORK`, `entry(name)`. Standard library only.
- `tools/<name>.py` shims for every row marked `yes` in `file-map.tsv`, plus
  `tools/verify_local.py` and `tools/test.py`. A shim is: docstring naming the
  real module, insert the repo root in `sys.path`, import `main`, exit with
  its result. Nothing else.
- `tools/run.py`: `python -I tools/run.py aoa.analysis.explore ARGS` runs any
  module's `main()`; `--list` prints every runnable module with the first
  line of its docstring.
- `tests/` (a package): every `test_*.py` per the map, `tools/snapshots/`
  moved to `tests/snapshots/`. Helpers that other suites import from
  `test_station_stub`, `test_station_runtime` and `test_object_persistence`
  move to `tests/support.py`; no test module imports another test module.
- `tests/tiers.py`: the `ci` list (today's CI list), the `local` list
  (today's `verify_local.py` list plus the orphan suites that need the
  game), and the emulation checks.
- `tools/test.py`: `--tier ci|local|all` or suite names. Runs each suite in
  its own `python -I` process (as today), prints one line per suite and a
  summary, exits non-zero on any failure. CI and `verify_local.py` call it.
- `tests/test_imports.py` (ci tier): imports every module under `aoa/`.
  A module that needs an optional package or Windows is skipped with the
  reason; anything else failing to import is a failure.
- `tests/test_layering.py` (ci tier): builds the import graph of `aoa/` with
  `ast` and enforces PLAN.md rule 1. Violations that exist today go in an
  explicit `KNOWN` list, each with its audit finding ID (H12, R4, R5 …), and
  the test fails if a listed violation disappears without being removed from
  the list, or a new one appears.
- `archive/README.md`: what the folder is, that nothing imports it, and for
  each script the evidence file that holds its frozen output
  (`audits/research.md` section 3 has these).

Also in this phase, mechanically:

- Docs: rewrite paths of moved scripts in `*.md` files (not in `evidence/`,
  not in `docs/restructure/audits/`). Shimmed commands keep their text.
  Others become `tools/run.py aoa.<package>.<module>`. Do not reword prose.
- `.github/workflows/tests.yml`: one step, `python -I tools/test.py --tier ci`.
- `docs/linux-host.md` and `deploy/`: the host needs `aoa/` as well as
  `tools/` and `deploy/`; the service keeps calling the `tools/` shim.
- `tools/README.md`: replace with a short pointer (phase 4 generates the
  index).

## Gate (all must hold before you report done)

1. `python3 -I tools/test.py --tier ci` passes.
2. `tests/snapshots/patch_regions.json` and `host_configs.json` are
   byte-identical to before the move (the tests pass without `--update`).
3. Every suite's outcome (exit code, ran, skipped, result) with only the
   standard library, and again with `requirements.txt` in a scratch venv,
   matches `docs/restructure/baseline-tests.md` as it stands when you start,
   except suites that now skip cleanly instead of erroring. Commit the new
   table as `docs/restructure/phase1-tests.md` with a diff summary on top.
4. `python -m pyflakes aoa tests tools archive` (pyflakes installed in a
   scratch venv) reports no undefined names and no import errors.
5. `python3 -I tools/<shim>.py --help` exits 0 for every shim (sandboxed:
   temp working directory, network blocked), and `tools/run.py --list` lists
   every module that has a `main`.
6. `git grep -n "sys.path.insert" -- aoa tests archive` is empty;
   `git ls-files tools` shows only shims, `run.py`, `test.py`,
   `verify_local.py`, the PowerShell and `.cmd` files, and `README.md`.
7. `git log --follow` on a moved file shows its history (moves were
   `git mv`, with content edits kept small enough for rename detection).

Cannot be verified here, so say so in the report: anything that needs the
game or Windows, including `verify_local.py` end to end, both windows, the
reel tools and the live verifiers.
