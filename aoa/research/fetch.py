"""Download one manifest entry, verify size + SHA-256, store it read-only.

Usage:
    python -I tools/fetch.py manifest/downloads.json <runtime_version> <out_dir> [--client]

--client fetches `direct_client_url` (only 2.7.1 has one) and verifies it
against `client_bytes` / `client_sha256` instead of the installer fields.

Nothing downloaded is executed. A JSON provenance record is appended to
evidence/download_log.jsonl (in the repository, whatever the working
directory). Requests go through tools/polite_http.py (paced, backs off on
HTTP 429/5xx).
"""
import datetime
import hashlib
import json
import os
import stat
import sys
from pathlib import Path

from aoa import cli  # noqa: E402
from aoa.research.http import polite_open  # noqa: E402

LOG = cli.ROOT / "evidence" / "download_log.jsonl"


def main(argv=None) -> int:
    ap = cli.parser(__doc__)
    ap.add_argument("manifest", help="manifest/downloads.json")
    ap.add_argument("version", help="runtime_version of the entry to fetch")
    ap.add_argument("out_dir", type=cli.output_dir, help="folder to save the file in")
    ap.add_argument("--client", action="store_true", help="fetch the direct client instead of the installer")
    a = ap.parse_args(argv)
    manifest_path, version, out_dir, want_client = a.manifest, a.version, a.out_dir, a.client
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    entry = next((d for d in manifest["downloads"] if d["runtime_version"] == version), None)
    if entry is None:
        sys.exit(f"fetch: no manifest entry for runtime_version {version}")

    field = "direct_client_url" if want_client else "direct_url"
    if field not in entry:
        sys.exit(f"fetch: the {version} entry has no {field}")
    if want_client:
        url = entry["direct_client_url"]
        want_bytes, want_sha = entry["client_bytes"], entry["client_sha256"]
        name = f"aoaclient_{version}_direct.exe"
    else:
        url = entry["direct_url"]
        want_bytes, want_sha = entry["bytes"], entry["sha256"]
        name = entry["suggested_local_filename"]

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    final = out / name
    if final.exists():
        print(f"exists, not overwriting: {final}")
        return 0
    part = out / (name + ".part")

    started = datetime.datetime.now(datetime.timezone.utc).isoformat()
    h = hashlib.sha256()
    n = 0
    with polite_open(url, timeout=120) as resp, open(part, "wb") as f:
        status, final_url = resp.status, resp.geturl()
        headers = {k: v for k, v in resp.headers.items()
                   if k.lower() in ("content-length", "content-type", "last-modified", "date", "etag")}
        while chunk := resp.read(1 << 20):
            f.write(chunk)
            h.update(chunk)
            n += len(chunk)
    sha = h.hexdigest()
    ok = (n == want_bytes and sha == want_sha)
    record = {
        "runtime_version": version, "what": "client" if want_client else "installer",
        "url": url, "final_url": final_url, "http_status": status, "headers": headers,
        "started_utc": started, "bytes": n, "sha256": sha,
        "expected_bytes": want_bytes, "expected_sha256": want_sha, "verified": ok,
        "local_path": str(final.as_posix()),
    }
    with open(LOG, "a", encoding="utf-8") as log:
        log.write(json.dumps(record) + "\n")
    if not ok:
        print(json.dumps(record, indent=2))
        print("VERIFICATION FAILED; leaving .part file for inspection", file=sys.stderr)
        return 1
    part.rename(final)
    os.chmod(final, stat.S_IREAD | stat.S_IRGRP | stat.S_IROTH)
    print(f"OK {final} {n} bytes sha256={sha}")
    return 0


if __name__ == "__main__":
    sys.exit(cli.run(main))
