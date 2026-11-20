# The November 2026 restructure

From 13 to 20 November 2026 the repository was restructured on the
`architecture-cleanup` branch: one flat folder of 166 Python files became
the `aoa` package with the tests in `tests/`, the command shims in `tools/`
and the frozen one-off scripts in `archive/`; the client patches became
data in one registry; the host got one configuration and one supervisor;
both launcher windows were rebuilt; and the docs were sorted by reader. Patch
bytes were not changed: golden snapshots prove every patch writes the same
bytes to the same addresses. The files here are the record of that work and
are not kept current.

| File | What it is |
|---|---|
| [PLAN.md](PLAN.md) | The plan: what was wrong (section 1), the design rules (section 2, now in [CONTRIBUTING.md](../../CONTRIBUTING.md#design-rules)), each phase with what was done and when (section 3), what cannot be verified in the cloud (section 4), the decisions (section 5) |
| [briefs/](briefs/) | The task brief of each phase, and [RULES.md](briefs/RULES.md) that every implementation agent followed |
| [audits/](audits/README.md) | Six read-only audits of `main` at `f659000` (13 November 2026), with the scripts they used; frozen, so their links and paths are those of that day |
| [baseline-tests.md](baseline-tests.md), [phase1-tests.md](phase1-tests.md), [phase2pre-tests.md](phase2pre-tests.md) | The outcome of every test suite before the work, after the phase 1 move and after phase 2-pre |
| [file-map.tsv](file-map.tsv), [make_file_map.py](make_file_map.py), [move.py](move.py) | The phase 1 move: where every file went, and the script that moved them |
| [screens/](screens/) | Both windows in each state, captured on Linux under a virtual screen on 16 November 2026 |

## What still needs Windows and the game

Everything below was done in a Linux session with no game files and no
Windows ([PLAN.md section 4](PLAN.md#4-what-cannot-be-verified-in-the-cloud)).
Before relying on the branch, run on Windows with the game:

- `.venv\Scripts\python.exe -I tools\verify_local.py`: the local gate. The
  snapshot tests prove the refactor writes the same patch bytes; they do not
  prove the patched game still runs.
- Both windows (`Play.cmd`, `Host.cmd`) on Windows 10 and 11: their logic is
  tested, their layout and behaviour need a person to open them, and their
  Windows-only steps (archive.org download, skin registration, wrapper
  install, hosts file, the running-game check, Play) have not run at all.
- The elevation, registry and firewall steps of the launchers, and the
  PowerShell scripts (`start_lan_dogfight.ps1`, `setup_game.ps1`).
- The Windows job of CI, and the Linux job with the research packages
  installed (`--strict`).

What is verified and what is untested today: [STATUS.md](../STATUS.md).
