"""Download a recovered build listed in manifest/downloads.json and verify it.

    python -I tools/fetch.py VERSION [--out DIR] [--client]
    python -I tools/fetch.py 2.9.2 --out builds/2.9.2-fetch

The older form `tools/fetch.py manifest/downloads.json VERSION OUT_DIR
[--client]` still works.

The file is saved in DIR (default builds/<VERSION>/; CLAUDE.md asks for a new,
empty folder per download) under the manifest's `suggested_local_filename`,
or aoaclient_<VERSION>_direct.exe with --client, which fetches
`direct_client_url` (only 2.7.1 has one). It counts as verified only with the
manifest's size, the SHA-256 that aoa/builds.py holds for that version, and
the manifest's MD5 where it gives one; only then is the .part file renamed
and made read-only. A failed check leaves the .part file for inspection. A
file already in place is checked, never overwritten. When the manifest's URL
fails or gives other bytes, the archive.org mirrors in MIRRORS are tried.

Nothing downloaded is executed. Every download appends a JSON provenance
record to evidence/download_log.jsonl (--log names another file). Requests go
through aoa/research/http.py (paced, backs off on HTTP 429/5xx).

tools/fetch_known_builds.py runs `known_builds` below: the 2.8.2 and 2.9.2
installers under the folder names docs/play.md and tools/setup_game.ps1 use.
"""
import datetime
import hashlib
import json
import os
import stat
import sys
from pathlib import Path

from aoa import builds, cli
from aoa.research.http import polite_open

MANIFEST = cli.ROOT / "manifest" / "downloads.json"
LOG = cli.ROOT / "evidence" / "download_log.jsonl"
# Other uploads of the same bytes, tried after the manifest's direct URL.
MIRRORS = {
    "2.8.2": ["https://archive.org/download/cda_20260908/CDA%2006-2002.iso/"
              "%23dema%2Face%20of%20angels%2Faoa-current.exe"],
    "2.9.2": ["https://archive.org/download/family_game_pack32004/family_game_pack3%282004%29.iso/"
              "Games%2FAce%20of%20Angels%2Faoa-current.exe"],
}
# tools/fetch_known_builds.py: version -> folder, each holding aoa-current.exe.
KNOWN_BUILDS = {
    "2.8.2": "v2.8.2_2002-03_CD-Action-06-2002",
    "2.9.2": "v2.9.2_2004_FamilyGamePack3",
}
KNOWN_NAME = "aoa-current.exe"


class FetchError(Exception):
    """A problem with the request itself (unknown version, no URL); one line."""


def entry_for(version, manifest=MANIFEST):
    data = json.loads(Path(manifest).read_text(encoding="utf-8"))
    entry = next((d for d in data["downloads"] if d["runtime_version"] == version), None)
    if entry is None:
        raise FetchError(f"no manifest entry for runtime_version {version}")
    return entry


def expected(entry, client=False):
    """{"bytes", "sha256", "md5"} the download must have; the SHA-256 must agree with aoa/builds.py."""
    version = entry["runtime_version"]
    if client:
        want = {"bytes": entry["client_bytes"], "sha256": entry["client_sha256"], "md5": None}
        known = builds.CLIENT_SHA256.get(version)
    else:
        want = {"bytes": entry["bytes"], "sha256": entry["sha256"], "md5": entry.get("md5")}
        known = builds.INSTALLER_SHA256.get(version)
        if entry["kind"] == "replacement_client_only":
            known = builds.CLIENT_SHA256.get(version)
    if known != want["sha256"]:
        raise FetchError(f"the manifest's {version} SHA-256 is not the one aoa/builds.py holds")
    return want


def urls(entry, client=False):
    field = "direct_client_url" if client else "direct_url"
    if field not in entry:
        raise FetchError(f"the {entry['runtime_version']} entry has no {field}")
    return [entry[field]] + ([] if client else MIRRORS.get(entry["runtime_version"], []))


def digests(path):
    """(bytes, sha256, md5) of a file."""
    sha, md5, n = hashlib.sha256(), hashlib.md5(), 0
    with open(path, "rb") as f:
        while chunk := f.read(1 << 20):
            sha.update(chunk)
            md5.update(chunk)
            n += len(chunk)
    return n, sha.hexdigest(), md5.hexdigest()


def matches(got, want):
    n, sha, md5 = got
    return n == want["bytes"] and sha == want["sha256"] and (want["md5"] is None or md5 == want["md5"])


def download(url, part, open_url):
    """Stream url into part; returns (status, final URL, chosen headers)."""
    with open_url(url, timeout=600) as resp, open(part, "wb") as f:
        status, final_url = resp.status, resp.geturl()
        headers = {k: v for k, v in resp.headers.items()
                   if k.lower() in ("content-length", "content-type", "last-modified", "date", "etag")}
        while chunk := resp.read(1 << 20):
            f.write(chunk)
    return status, final_url, headers


def fetch(version, out_dir, *, client=False, name=None, manifest=MANIFEST, log=LOG,
          open_url=polite_open, say=print):
    """Download and verify one manifest entry into out_dir; returns the final path or None."""
    entry = entry_for(version, manifest)
    want = expected(entry, client)
    candidates = urls(entry, client)
    if name is None:
        name = f"aoaclient_{version}_direct.exe" if client else entry["suggested_local_filename"]
    out = Path(out_dir)
    final = out / name
    if final.exists():
        if matches(digests(final), want):
            say(f"OK {final} already there and verified")
            return final
        say(f"{final} exists but does not verify; not overwriting it")
        return None
    out.mkdir(parents=True, exist_ok=True)
    part = out / (name + ".part")
    for url in candidates:
        started = datetime.datetime.now(datetime.timezone.utc).isoformat()
        try:
            status, final_url, headers = download(url, part, open_url)
        except Exception as error:
            say(f"   {version}: {error}" + ("; trying a mirror" if url != candidates[-1] else ""))
            continue
        got = digests(part)
        ok = matches(got, want)
        record = {
            "runtime_version": version, "what": "client" if client else "installer",
            "url": url, "final_url": final_url, "http_status": status, "headers": headers,
            "started_utc": started, "bytes": got[0], "sha256": got[1],
            "expected_bytes": want["bytes"], "expected_sha256": want["sha256"], "verified": ok,
            "local_path": str(final.as_posix()),
        }
        if want["md5"]:
            record.update(md5=got[2], expected_md5=want["md5"])
        with open(log, "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
        if ok:
            os.replace(part, final)
            os.chmod(final, stat.S_IREAD | stat.S_IRGRP | stat.S_IROTH)
            say(f"OK {final} {got[0]} bytes sha256={got[1]}")
            return final
        say(json.dumps(record, indent=2))
        say(f"VERIFICATION FAILED for {url}; the .part file is left for inspection")
    return None


def legacy_argv(argv):
    """Turn `MANIFEST.json VERSION OUT_DIR [--client]` into `VERSION --out OUT_DIR --manifest MANIFEST.json`."""
    words = [a for a in argv if not a.startswith("-")]
    if len(words) == 3 and words[0].endswith(".json"):
        flags = [a for a in argv if a.startswith("-")]
        return [words[1], "--out", words[2], "--manifest", words[0], *flags]
    return argv


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else list(argv)
    ap = cli.parser(__doc__)
    ap.add_argument("version", help="runtime_version of the manifest entry, e.g. 2.9.2")
    ap.add_argument("--out", type=cli.output_dir, metavar="DIR",
                    help="folder to save the file in (default: builds/VERSION)")
    ap.add_argument("--client", action="store_true", help="fetch the direct client instead of the installer")
    ap.add_argument("--manifest", default=str(MANIFEST), help="download manifest (default: manifest/downloads.json)")
    ap.add_argument("--log", default=str(LOG), help="provenance log to append to (default: evidence/download_log.jsonl)")
    a = ap.parse_args(legacy_argv(argv))
    out = a.out or cli.ROOT / "builds" / a.version
    try:
        final = fetch(a.version, out, client=a.client, manifest=a.manifest, log=a.log)
    except FetchError as error:
        sys.exit(f"fetch: {error}")
    return 0 if final else 1


def known_builds(argv=None) -> int:
    """Download the verified 2.8.2 and 2.9.2 installers into the folders docs/play.md names.

    The command line of tools/fetch_known_builds.py.
    """
    ap = cli.parser("""Download the verified 2.8.2 and 2.9.2 installers and check them.

    python3 -I tools/fetch_known_builds.py builds/

Each goes to builds/<folder>/aoa-current.exe (the 2.9.2 one to
builds/v2.9.2_2004_FamilyGamePack3/, where tools/setup_game.ps1 looks for it)
through aoa/research/fetch.py: size, SHA-256 and provenance log as for
`tools/fetch.py VERSION`. Nothing is executed. A file already there is checked
and kept. The output folder must be given explicitly; a name starting with
"-" is refused.
""")
    ap.add_argument("out_dir", type=cli.output_dir, help="folder to save the builds in, e.g. builds/")
    ap.add_argument("--log", default=str(LOG), help="provenance log to append to (default: evidence/download_log.jsonl)")
    a = ap.parse_args(argv)
    ok = True
    for version, folder in KNOWN_BUILDS.items():
        final = fetch(version, Path(a.out_dir) / folder, name=KNOWN_NAME, log=a.log)
        ok &= final is not None
        print(f"{'OK' if final else 'FAILED':8}  {folder}  {Path(a.out_dir) / folder / KNOWN_NAME}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(cli.run(main))
