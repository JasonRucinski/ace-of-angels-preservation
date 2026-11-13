# Phase 0a: safety net (golden snapshots and test baseline)

Goal: game-free tests that pin today's behaviour, so every later phase can
prove it changed nothing it should not have. No production code changes
except where a snapshot cannot be taken otherwise (say so if that happens).

Files you may create or edit: `tools/test_patch_layout.py`,
`tools/test_host_argv.py`, `tools/snapshots/` (new folder for committed
snapshot data), `.github/workflows/tests.yml`, `requirements.txt` only to
read. Seeds from the audit: `docs/restructure/audits/scripts/`.

1. **Patch layout snapshot** (`tools/test_patch_layout.py`, unittest):
   - Collect every region every client patch writes, for every variant:
     file offset, original bytes, new bytes, plus the runtime `.data`
     reservations. `audits/scripts/client_regions.py` and the inventory table
     in `audits/client.md` section 2a list the modules and their accessors
     (`regions()`, `regions(variant)`, `cave_code()`, `build_cave()`, …).
     Cover all 22 patch IDs and both experiments.
   - Write them to `tools/snapshots/patch_regions.json` (hex strings, sorted,
     stable) with a `--update` switch; the test compares against the file.
   - Assert: all code caves lie in the `.text` padding and all runtime data
     in the `.data` tail (bounds in `audits/client.md` finding C5); regions
     of different patches are disjoint except the declared pairs
     (asteroid/solid-world, station/world detail, experiments vs the patches
     that superseded them, third_person/own_ship_menu data as it is today,
     recorded as a known exception with a comment citing C5).
   - This must run with only the standard library if at all possible. If a
     module needs `capstone`/`unicorn`/`pefile` merely to be imported, note
     which and skip that module's rows with a reason instead of erroring.
2. **Host command-line snapshot** (`tools/test_host_argv.py`, unittest):
   - For `host_control.server_args` over a representative settings matrix,
     `dedicated_host`'s child arguments for `deploy/linux/*.example`,
     `map_viewer serve`, and the server command lines shown in the docs
     (`audits/scripts/host_doc_cmds.py` is a seed), assert each parses with
     `station_runtime.parse_args` and snapshot the resulting effective config
     to `tools/snapshots/host_configs.json`.
3. **CI**: add both tests and `test_reel` to the suite list. In the Linux job
   install the pinned `capstone`, `unicorn` and `pefile` only (not Pillow) so
   patch modules import; keep the comment about the host being
   standard-library-only accurate (reword it: the host needs none, the tests
   do).
4. **Baseline**: run every `tools/test_*.py` twice, once with only the
   standard library and once in a scratch venv with `requirements.txt`
   installed. Commit the table (suite, exit code, ran, skipped, result line)
   as `docs/restructure/baseline-tests.md`. Later phases diff against it.

Done when both new tests pass here, the snapshot files are committed, the CI
file lists them, and the baseline table is committed.
