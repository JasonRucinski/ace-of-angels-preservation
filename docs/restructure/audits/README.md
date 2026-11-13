# Audit reports

Six read-only audits of `main` at `f659000`, made on 13 November 2026.
[`../PLAN.md`](../PLAN.md) is built from them. Each report lists findings
with file and line, how each was checked, and what was not checked.

| Report | Area |
|---|---|
| [host.md](host.md) | Stand-in server, host window, headless host |
| [client.md](client.md) | Client patches and client setup |
| [launchers.md](launchers.md) | Player and host experience, with a redesign |
| [docs.md](docs.md) | Documentation links, commands and contradictions |
| [research.md](research.md) | Archive research, analysis, asset and map tools, data folders |
| [tests.md](tests.md) | Test suites and CI |

`scripts/` holds the auditors' throwaway checkers, kept as starting points
for the phase 0 tests. They use absolute paths from the audit session and the
old flat `tools/` layout, so they are not runnable as they stand. Scratch
paths cited inside the reports no longer exist.

During the audit, running tools with `--help` contacted archive.org: the two
installers were downloaded twice and a full-text search was started twice
(PLAN.md, problem U3). Nothing in the repository was left changed.
