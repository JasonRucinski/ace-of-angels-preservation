# Rules for every implementation agent

You are implementing one task from `docs/restructure/PLAN.md` in
`/home/user/ace-of-angels-preservation` (or the git worktree you were started
in). Read PLAN.md sections 2 to 4 and your task brief before touching code.
The audit reports in `docs/restructure/audits/` give file and line for every
finding your brief cites by ID.

## Safety

- **Never run a script you have not read.** Many scripts act on `--help` or
  on no arguments (they download, query archive.org, or overwrite tracked
  files). Read first; run only what is argparse-based or proven harmless.
- **No network to archive.org, the Wayback Machine or any game host.** Package
  installs from PyPI into a venv under your scratch directory are fine.
- **No game files exist here** (`game/`, `builds/`, `work/`, `originals/`
  are absent). Do not create them inside the repo. Use temp directories.
- Linux, Python 3.13 (CI uses 3.12). Windows-only code (tkinter windows,
  ctypes process access, PowerShell, `.cmd`) cannot be run: change it
  carefully and say in your report that it was not executed.
- Stay inside your brief's file list. If a fix needs a file outside it, stop
  and report instead of editing it.
- Do not push, do not open pull requests, do not rewrite history. Commit on
  the branch you are on, one commit per logical change, message in the
  imperative, ending with these two lines:
  `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`
  `Claude-Session: https://claude.ai/code/session_0164BRCWQ7ryQSoA4xsR4iz8`
- Do not name any AI model in code, comments or docs.

## Quality bar

- **Client patch bytes must not change** unless your brief says so. A patch's
  addresses, original bytes and new bytes are evidence-backed; refactor
  around them.
- Match the surrounding code: its naming, comment density and idiom. No
  drive-by reformatting. Keep diffs minimal for the task.
- Every behaviour change gets a test that fails before and passes after, and
  that needs no game files wherever that is possible.
- House rules (CONTRIBUTING.md): evidence over claims; anything untested
  stays visibly marked untested; patches reversible and hash-checked; no game
  files in commits.
- Before each commit run the game-free suites that cover what you touched,
  with `python3 -I tools/<suite>.py`. Before you finish run all of:
  test_network_bounds test_relay_motion test_relay_recovery
  test_station_runtime test_station_sessions test_station_stub
  test_guest_admission test_combat_delivery test_client_extensions
  test_lan_dogfight test_internet_play test_powerups test_target_ships
  test_host_control test_prepare_client test_dedicated_host
  test_client_launcher test_make_map test_make_object
  test_patch_layout test_host_argv test_reel
  test_cli_help test_polite_http test_install_wrapper test_make_vessel_combat
  plus any test you added. All must pass.

## Report back (under 400 words)

1. What you changed, by finding ID, with the commit hashes.
2. Test results: exact commands and outcomes. Say plainly what failed.
3. What you did not do or could not verify, and why.
4. Doc changes now needed (file, line, what to change) if docs were outside
   your file list.
5. Anything you found that the plan gets wrong.
