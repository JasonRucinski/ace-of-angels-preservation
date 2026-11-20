# Phase 0d: command-line safety for research, analysis and asset tools

Make every script safe to ask for help, and make archive access polite.
Findings are in `docs/restructure/audits/research.md` (R-numbers).

Files you may edit: every `tools/*.py` and `tools/reel/*.py` that is NOT in
the client or host file lists below, plus new `tools/cli_util.py`,
`tools/polite_http.py`, `tools/test_cli_help.py`, `tools/test_polite_http.py`.
Do not touch (other agents own them): prepare_client, client_launcher,
patch_client, local_station, physics_timestep, third_person, own_ship_menu,
own_ship_model, asteroid_render, solid_world_render, station_detail,
world_detail, texture32, object_persistence, install_wrapper, make_install,
host_control, dedicated_host, station_stub, station_runtime, host_ops,
map_viewer, make_vessel_combat, turret_groups, and any `test_*.py` that
already exists. Not docs.

1. **R1, R2, R3 (high):** every script with a command line gets
   `main(argv=None)` and argparse, keeping its existing positional arguments
   in the same order so documented commands still work. No work at import
   time: module-level code moves into `main()` behind
   `if __name__ == "__main__":`. Missing or unreadable input exits non-zero
   with one line. `audit_object_lod.py` fails when its export folder is
   absent instead of writing an empty report. `fetch_known_builds.py` and
   `ia_fulltext_search.py` take an explicit output directory and refuse a
   name starting with `-`. Read each script fully before editing it.
2. **`tools/test_cli_help.py`** (game-free, for CI): for every script under
   `tools/` with a `__main__` block, run `python -I <script> --help` in a
   temp working directory with the network blocked (patch `socket` in a
   wrapper, or run under an environment that makes any connect raise) and
   assert exit code 0, usage text on stdout, and no file created. Scripts
   owned by other agents that still fail go in an explicit
   `KNOWN_UNSAFE` list with the finding ID, so the list shrinks visibly.
   The test must NEVER run a script outside that sandbox.
3. **R17, R18, U4:** one `tools/polite_http.py` with `polite_get(url, ...)`:
   one User-Agent naming the project (no personal data), a minimum pause
   between requests to the same host, exponential backoff with `Retry-After`
   on 429 and 5xx, a bounded retry count. All seven fetch helpers use it.
   `restore_web_archive.py` leaves throttled rows pending. Unit-test it with
   a fake opener (`tools/test_polite_http.py`): pacing, backoff, giving up.
   Never test against the real network.
4. **R7:** `ia_fulltext_search.py` and `ia_fulltext_context.py` default to the
   committed file names in `data/`.
5. **R9:** scripts that used working-directory-relative repo paths resolve
   them from the repo root.
6. **R8 (output):** audits that write committed `evidence/` files by default
   write to `work/` instead, with an explicit `--evidence PATH` to write the
   committed copy. Do not regenerate any evidence file.
7. **R19, R20:** `wise_extract.py` fails on a CRC mismatch unless `--force`;
   `inventory.py` treats the handoff comparison as optional.

Do not move or delete scripts (phase 1 does that) and do not change what any
analysis computes.

Done when `test_cli_help.py` and `test_polite_http.py` pass, the
`KNOWN_UNSAFE` list contains only other agents' files, and no tracked file
outside your list changed.
