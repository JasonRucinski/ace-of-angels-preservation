# Phase 4: the docs, sorted by reader

Reorganise the documentation so each reader finds one place for their task,
and add the guards that keep it correct. This is the last phase. Phases 0e
and 3 already made the guides true and wrote the new player and host
guides; this phase moves, merges and indexes. It does not reword prose that
is still true, and it never removes a dated research record.

Read `docs/restructure/audits/docs.md` sections 3 and 4 first: the file
classification and the target tree there are the plan, with the decisions
below where they differ.

Files: everything under `docs/` except `docs/restructure/audits/` (frozen
records of the audit) and `docs/images/`; `README.md`, `CONTEXT.md`,
`CONTRIBUTING.md`, `CLAUDE.md`; `.github/ISSUE_TEMPLATE/*`; `data/` only for
the handoff move in item 5; code only where a docstring, usage line, error
message or test names a doc path that moves; new tests under `tests/`.

Notes from phases 2c and 3 for this phase:

- `tools/README.md` is generated (`tools/run.py aoa.tools_index`, checked by
  `tests/test_tools_index.py`); item 4's tools index builds on it.
- Docs still name the shim module names that 2c kept for compatibility
  (`CONTEXT.md` tool table, `data/magazine-mentions.md`, `findings.md`
  around the `inventory` and full-text tools): switch them to the current
  commands. `docs/private-web-archive.md` should describe the new `cdx`
  subcommand; `CLAUDE.md` the `--log` option of `ia_disc_find`.
- 2.8.2 is now fetched from discmaster first with archive.org as the mirror:
  `play/README.md` and `reference/tools.md` should say so where they name
  the source.
- `docs/restructure/file-map.tsv` is a record of phase 1; do not update it.

## Target tree

```
docs/
  README.md        index grouped by reader; each entry tagged guide / reference / log / roadmap
  STATUS.md        unchanged role: the only place for verified / untested
  play/            README.md (install and first flight: today's play.md), launcher.md,
                   texture-pack.md, map-viewer.md, troubleshooting.md
  host/            README.md (choose: this PC / home network / VPN / Linux; the steps they
                   share: firewall, hosts name, ports; the defaults table), host-window.md,
                   lan.md, vpn.md, linux.md, console.md, server-reference.md
  create/          custom-maps.md, custom-objects.md, hype-reel.md
  reference/       client-patches.md, protocol.md, message-types.md, asset-formats.md,
                   maps.md, versions.md, tools.md
  research/        README.md (how the logs work), findings.md, log.md, arena1a.md,
                   arena1a-trials.md, level-data.md, code-clues.md, windows-11.md,
                   rendering/asteroids.md, rendering/pipeline-audit.md,
                   rendering/offline-baseline.md
  archive/         web-archive.md
  roadmap/         internet-server.md, modernization.md, authoritative-server.md
  restructure/     unchanged (this programme's plan, briefs, audits, test tables)
```

## Items

1. **Move with stubs.** Use `git mv` so history follows. At every old path
   that anything outside the repo may link to (all of `docs/*.md` today),
   leave a three-line stub: a title and "Moved to [new path](new path)."
   Rewrite every link inside the repo to the new path, so no in-repo link
   lands on a stub. The issue templates' links too.
2. **Splits and merges** (follow the audit's table; where a doc mixes a
   guide with a dated record, the guide part goes to its reader's folder and
   the dated part to `research/`):
   - `client-setup.md`: the launcher part to `play/launcher.md`, the patch
     reference to `reference/client-patches.md` (its patch-level table is
     checked against the registry by a test: keep that test passing).
   - `map-viewer.md`: viewing to `play/map-viewer.md`; the map table into
     `reference/maps.md` together with `hosting-assets.md`, generated from
     `aoa/maps/registry.py` (item 4).
   - `running-on-windows-11.md`: the dated diagnosis to
     `research/windows-11.md`; its setup steps are covered by
     `play/README.md`, so they go (link instead).
   - `lan-dogfight.md`, `vpn-dogfight.md`, `linux-host.md`,
     `host-control.md`, `local-server.md`: what all of them repeat (firewall,
     hosts name and the 11-character limit, ports, defaults, console
     commands, status file, crash restarts) moves once to `host/README.md`
     and `host/console.md`; each page keeps only what differs. Dated
     verification prose moves to `research/log.md` with a link back.
   - `first-playable-release.md` and `client-extension-gate.md` merge into
     `roadmap/authoritative-server.md`, each keeping its own section and
     dates.
   - `arena1a.md` and `arena1a-rebuild.md` become `research/arena1a.md` and
     `research/arena1a-trials.md`.
3. **`findings.md`** moves whole to `research/findings.md` (do not split it
   into many files). Give every `##`/`###` section an explicit stable anchor
   (`<a id="s9-47"></a>` before the heading, ids from the section numbers),
   point every link at those ids, and add a short table of contents at the
   top. Corrections already link forward; keep that.
4. **Generated reference tables**, each with a generator command and a CI
   test that fails when the committed table is stale (follow the pattern of
   `aoa/host/flagdoc.py` and its test):
   - `reference/maps.md`: the map table from `aoa/maps/registry.py`
     (name, kind, content, objects where known, note);
   - `host/README.md`: the defaults table from `aoa/host/defaults.py`
     (profiles, ports, limits, who can join);
   - `reference/client-patches.md`: the patch table from the client
     `REGISTRY` (id, option, group, default, patch level, requires,
     conflicts);
   - `reference/tools.md`: the tools index (phase 2c generates
     `tools/README.md`; make `tools/README.md` a short pointer to it, or the
     other way round, but have one generated copy, not two).
   - `server-reference.md` keeps the generated flag table from
     `aoa/host/flagdoc.py` (update its target path).
5. **`CONTEXT.md` back to archive research.** Its section 2 (the dated
   development changelog) moves to `research/log.md` unchanged, newest
   first, with a link from CONTEXT. Its tool table that duplicates the
   tools index becomes a link. The rule in `CLAUDE.md` ("keep CONTEXT
   current") then applies to the archive work it is about. The handoff
   text that tools read (`docs/history/2026-10-20-research-handoff.txt`)
   moves to `data/research-handoff-2026-10-20.txt`; update the tools that
   read it and their tests.
6. **Who owns what.** `README.md` is the front door: what it is, the
   screenshots, at most five status bullets that link `docs/STATUS.md`, a
   "Start here" table by reader, the layout (`aoa/`, `tests/`, `tools/`,
   `archive/`, `docs/`), licence. No counts or verification claims that are
   not also in STATUS. `CONTRIBUTING.md` holds the house rules and the
   design rules of PLAN.md section 2 (layering, one entry convention, one
   source per fact, patches as data, one host configuration, output to
   `work/`, polite network, tests), how to run the tests, and where each
   kind of doc goes. `CLAUDE.md` stays short: what the repo is, where to
   read, the agent-only rules, the test command; it links CONTRIBUTING
   instead of copying it. `docs/README.md` lists every doc once.
7. **CI guards** (game-free, in the CI tier):
   - `tests/test_doc_links.py`: every relative link and anchor in every
     tracked `.md` resolves; no link points into `builds/`, `game/`,
     `originals/`, `wb/` or `work/`; no in-repo link points at a stub.
     Start from `docs/restructure/audits/scripts/docs_linkcheck.py`.
     `docs/restructure/audits/` is exempt (frozen record).
   - `tests/test_doc_commands.py`: every `tools/<name>.py` and
     `tools/run.py aoa.<module>` named in a doc exists and has a `main`;
     for each documented command line, every `--flag` it uses appears in
     that command's `--help` output, obtained only through the sandbox that
     `tests/test_cli_help.py` uses (never run a tool any other way).
8. **Restructure record.** Tick phase 4 in `docs/restructure/PLAN.md` with
   what was done and what was not, and add a short
   `docs/restructure/README.md`: what the programme was, where the plan,
   briefs, audits, test tables and screenshots are, and the checks that
   still need Windows and the game.

## Gate

- `python3 -I tools/test.py --tier ci` passes, including the two new guard
  suites and every generated-table test.
- `git log --follow` on a moved doc reaches its old history.
- No doc lost content: for each doc you split or merged, list in your
  report where each of its sections went. Dated research text is moved, not
  rewritten.
- The link checker reports zero broken links outside
  `docs/restructure/audits/`.
