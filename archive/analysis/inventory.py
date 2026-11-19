"""Inventory a Wise/ZIP self-extracting installer without executing it.

Usage:
    python -I tools/run.py archive.analysis.inventory <installer.exe> <version> [handoff.txt] <out_dir>

* Lists every ZIP member (name, sizes, CRC, method, DOS timestamp), runs
  ZipFile.testzip(), hashes every member, flags MZ/PE signatures regardless
  of extension, and compares against the handoff's Appendix C inventory
  when a handoff is given and has one for <version> (only
  docs/history/2026-10-20-research-handoff.txt does); otherwise the
  appendix_c fields are null.
* Extracts a fixed set of members of interest to <out_dir>/members/ using
  "<index>_<basename>" names (member paths are never trusted).
* Writes <out_dir>/inventory.json.
"""
import hashlib
import json
import re
import sys
import zipfile
from pathlib import Path

from aoa import cli  # noqa: E402
from aoa.formats.installer import members as installer_members

EXTRACT = {
    "AOACLIENT.EXE", "AOADEFAULTS.PRF", "SCRTY.BIN", "SCENARIOS.AOA", "SCRIPTS.AOA",
    "SCHK.DAT", "AS_CHK.BIN", "AOAOBJECTS.ODB", "JRMAP.TRN", "RENEXE.EXE",
    "AOANOTES.TXT", "AOATUTORIAL.TXT", "AOACONTACT.TXT", "FX.AOA",
    "FILE0001.DAT", "FILE0002.DAT", "FILE0003.DAT", "FILE0004.DAT", "FILE0005.DAT",
    "FILE0006.DAT", "FILE0007.DAT", "FILE0008.DAT", "FILE0009.DAT", "FILE0010.DAT",
    "DATA.AOA", "HUD.AOA", "SOUNDS.AOA", "TEXTURES.AOA", "IMAGES.AOA", "KEYMAP.PDF",
}


def appendix_c(handoff: str, version: str):
    """(member count, rows) from the handoff's Appendix C, or None if it has none for version."""
    text = Path(handoff).read_text(encoding="utf-8")
    m = re.search(rf"CLIENT VERSION {re.escape(version)}: (\d+) members\n.*?\n(.*?)\n\n", text, re.S)
    if m is None:
        return None
    rows = []
    for line in m.group(2).splitlines():
        name, size, crc = [p.strip() for p in line.split("|")]
        rows.append((name, int(size), crc.lower()))
    return int(m.group(1)), rows


def main(argv=None) -> int:
    ap = cli.parser(__doc__)
    ap.add_argument("installer", help="Wise/ZIP self-extracting installer")
    ap.add_argument("version", help="client version, e.g. 2.9.2")
    ap.add_argument("handoff", nargs="?", help="handoff text with an Appendix C inventory to compare against")
    ap.add_argument("out_dir", help="folder for inventory.json and members/")
    a = ap.parse_args(argv)
    installer, version, handoff, out_dir = a.installer, a.version, a.handoff, a.out_dir
    expected = appendix_c(handoff, version) if handoff else None
    out = Path(out_dir)
    (out / "members").mkdir(parents=True, exist_ok=True)
    data = Path(installer).read_bytes()
    with zipfile.ZipFile(installer) as zf:
        bad = zf.testzip()
    members = []
    for i, zi, base, blob in installer_members(installer):
        is_mz = blob[:2] == b"MZ"
        is_pe = False
        if is_mz and len(blob) >= 0x40:
            e = int.from_bytes(blob[0x3C:0x40], "little")
            is_pe = blob[e:e + 4] == b"PE\0\0"
        rec = {
            "index": i, "name": zi.filename, "file_size": zi.file_size,
            "compress_size": zi.compress_size, "crc32": f"{zi.CRC:08x}",
            "method": zi.compress_type, "dos_datetime": "%04d-%02d-%02dT%02d:%02d:%02d" % zi.date_time,
            "header_offset": zi.header_offset, "sha256": hashlib.sha256(blob).hexdigest(),
            "mz": is_mz, "pe": is_pe,
        }
        if base.upper() in EXTRACT:
            dest = out / "members" / f"{i:02d}_{base.upper()}"
            dest.write_bytes(blob)
            rec["extracted_to"] = dest.as_posix()
        members.append(rec)

    got_rows = [(m["name"], m["file_size"], m["crc32"]) for m in members]
    if expected is None:
        want_count = exact = diffs = None
    else:
        want_count, want_rows = expected
        exact = got_rows == want_rows
        diffs = [
            {"got": g, "want": w} for g, w in zip(got_rows, want_rows) if g != w
        ] + ([{"length_mismatch": [len(got_rows), len(want_rows)]}] if len(got_rows) != len(want_rows) else [])
    result = {
        "installer": Path(installer).as_posix(),
        "installer_bytes": len(data),
        "installer_sha256": hashlib.sha256(data).hexdigest(),
        "zip_testzip_first_bad_member": bad,
        "member_count": len(members),
        "appendix_c_member_count": want_count,
        "appendix_c_exact_match_in_order": exact,
        "appendix_c_diffs": diffs,
        "pe_members": [m["name"] for m in members if m["pe"]],
        "mz_members": [m["name"] for m in members if m["mz"]],
        "members": members,
    }
    (out / "inventory.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "members"}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(cli.run(main))
