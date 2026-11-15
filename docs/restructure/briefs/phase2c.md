# Phase 2c: research, analysis and evidence in order

Tidy the leaf packages (PLAN.md section 2, rules 2, 3, 6 and 7). Nothing
here changes what any analysis computes or what any committed evidence file
contains.

Files: everything under `aoa/research/`, `aoa/analysis/`, `aoa/emulation/`,
`aoa/live/`, `aoa/reel/`, `aoa/formats/` (only the items below), `archive/`,
`evidence/INDEX.tsv` (new), `data/`, their suites in `tests/`, `tools/`
shims for commands you merge, `requirements*.txt`, and `tools/README.md`.
Not `aoa/client/`, `aoa/host/`, `aoa/launchers/`, `aoa/protocol/`,
`aoa/maps/` (other agents are working there in parallel).

1. **One fetcher.** `aoa/research/fetch.py` is driven by
   `manifest/downloads.json` and replaces `fetch_known_builds.py`'s
   hard-coded list (audit R16): `fetch VERSION [--out DIR]`, sha256 checked
   against `aoa.builds`, MD5 where the manifest has it, provenance appended
   to the download log, one on-disk naming scheme. `tools/fetch_known_builds.py`
   stays as a shim that calls it for the two versions it used to fetch, so
   the player guide and `setup_game.ps1` keep working. Never contact the
   network in tests: use a fake opener.
2. **One version tool.** `version_probe` merges into
   `aoa/research/version.py` behind `--detail` (which may need capstone,
   imported only then).
3. **Wayback and archive.org.** `wayback` and `web_archive` share one CDX
   query helper, with a `cdx` subcommand that writes the index files
   `web_archive` reads (audit R17). `ia_disc_find` gets `--log
   data/disc_search.tsv` that appends the listed count and hit status, as
   `CLAUDE.md` requires for every search (audit R18). The two full-text
   scripts become one module with `search` and `context` subcommands.
   `iso_stream_extract` and `rar_img2iso` become `aoa/research/disc_image.py`.
   Everything still goes through `aoa/research/http.py`.
4. **Installer reading in one place.** `aoa/formats/installer.py`: one
   member iterator with one path sanitiser, used by `wise`, `make_install`
   (client, read-only here: only change its import if the function it calls
   keeps the same name and behaviour; otherwise report it), `inventory` and
   `version_assets` (audit research.md section 4).
5. **Disassembly cache keyed by the executable's hash** (audit R6):
   `work/cache/<sha256>.pkl`, no positional cache argument (keep accepting
   one, ignored with a note, so documented commands parse).
6. **Emulation helpers.** `Emu.for_build(path, "2.9.2")` (hash-checked
   through `aoa.builds`) and `emu.stop_at({...})` replace the pattern copied
   into about ten scripts (audit R22). The nine gate checks get a uniform
   `run(client_path) -> report` that `verify_local` calls in process.
7. **Windows process access in one module.** `aoa/live/procmem.py`
   (`Process.read/u32/write`, buffers sized to the request, a build check)
   and `aoa/live/addresses_292.py` replace the three copies (audit R21).
   Not runnable here: keep the change mechanical and say so.
8. **Evidence index.** `evidence/INDEX.tsv`: one row per committed evidence
   file with the generator command (or "no generator in the repository"),
   its date, and which docs cite it. A game-free CI test asserts every
   evidence file is listed and every named generator module exists. Move
   superseded `local_gate_*` snapshots and dated duplicates to
   `evidence/archive/` only when no doc links to them; record the two
   byte-identical layout files instead of deleting one.
9. **Requirements split** (audit F-10): `requirements.txt` holds only what a
   player or host needs (nothing today: keep the file with a comment so the
   documented `pip install -r requirements.txt` still succeeds),
   `requirements-research.txt` (capstone, unicorn, pefile, libarchive-c
   optional), `requirements-texture.txt` (Pillow). Update CI and the docs
   that name them.
    Also fix `docs/custom-maps.md` and `docs/custom-objects.md` where they
    say reading the archive key needs `requirements.txt`: since
    `aoa/formats/pe.py` it does not.
10. **Tools index.** `tools/README.md` is generated from module docstrings
    by `tools/run.py aoa.tools_index` (grouped by package, shims marked),
    with a CI test that the committed file is current.

Gate: `tools/test.py --tier ci` passes; no committed evidence file's content
changes (only moves under item 8); every documented command that named a
merged tool still parses; layering test passes with `KNOWN` empty; pyflakes
clean; the network is never contacted. Not verifiable here: the Windows
process tools, the reel, anything needing the game. Say so.
