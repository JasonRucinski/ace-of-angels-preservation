# Phase 0c: host fixes (no files move)

Fix the host-side problems that break or mislead hosts. Findings are in
`docs/restructure/audits/host.md` (H-numbers) and `audits/launchers.md`
(F-numbers). `tools/test_host_argv.py` snapshots the effective server config
for each launcher: update the snapshot only for changes this brief asks for,
and list each such change in your report.

Files you may edit: `tools/host_control.py`, `tools/host_control.cmd`,
`tools/dedicated_host.py`, `tools/station_stub.py`, `tools/station_runtime.py`,
`tools/host_ops.py`, `tools/start_lan_dogfight.ps1`, `tools/map_viewer.py`,
`tools/make_vessel_combat.py`, `tools/turret_groups.py`, `deploy/linux/*`, and
the tests of those modules. Not docs (list doc changes in your report).

1. **F-03 (high):** `host_control` saved settings are validated on load;
   `mode` is stored as the profile id, with the old display labels accepted
   and migrated; an invalid value falls back to the default with a visible
   notice. Wrap start-up so any exception shows a message box and is written
   to `work/logs/host.log`. Add argparse (H18): `--help` must not open a
   window. `host_control.cmd` uses `-I` (F-19).
2. **F-04:** "Load map (restart)" validates the new settings before it stops
   the running server. Test with a fake `HostProcess`.
3. **H1 / F-07, F-08:** `dedicated_host` no longer has mutually invalid
   defaults: `--bind-address` is required for the LAN and VPN profiles, with
   a one-line error. Argparse errors from the server config are shown as one
   line under the right program name. The rotation-config error names the
   unknown keys.
4. **H2, H3:** everything `run()` can reject at start is rejected by config
   validation: `--start-vessel` uses `choices`; navigation-buoy placement
   inputs (JRMAP.TRN, asset inventory) are checked during validation and a
   missing file is reported by name, never as a port or address problem.
   The host window checks the same before Start.
5. **H25:** the ban check runs before the version-rejection reply.
6. **H6:** the host window's "This PC only" mode uses the same admission and
   delivery path that LAN and VPN players get (`local-guests` with sustained
   delivery), so a local test exercises it. Keep `local-relay` selectable
   from the command line.
7. **H7 / F-06 (defaults):** one defaults table in `station_runtime`
   (20 kills, 600 seconds, 8 players) imported by `host_control` and
   `dedicated_host`. The Linux rotation example keeps its explicit 10 kills /
   900 seconds, with a comment that it overrides the default.
   `start_lan_dogfight.ps1` prints the limits and map it was actually given
   (H4, F-16), accepts every map the server accepts (H5), and its help lists
   every console command from `host_ops.HELP` (H19).
8. **H8 / F-15:** one `status_path(profile)` and one `read_status(path, pid)`
   in `host_ops`, used by the host window and the headless host.
9. **H9:** remove `--advertised-address` from the launchers' command lines;
   keep the flag accepted but hidden, with a deprecation line.
10. **H13 (dead code)** and **H24 (stale docstring):** delete what the audit
    verified dead; move emulator-only helpers only if no test breaks.
11. **H16:** `make_vessel_combat.py` gets argparse and a `--check` mode that
    regenerates in memory and diffs against `vessel_combat.py`; add that
    check as a game-free test if its inputs are committed, else skip with a
    reason.

Done when the host suites and the argv snapshot pass, and your report lists
each snapshot change and every doc line that now needs changing.
