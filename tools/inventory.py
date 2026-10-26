"""Inventory a Wise/ZIP self-extracting installer without executing it.

Usage:
    python -I tools/inventory.py <installer.exe> <version> <handoff.txt> <out_dir>

* Lists every ZIP member (name, sizes, CRC, method, DOS timestamp), runs
  ZipFile.testzip(), hashes every member, flags MZ/PE signatures regardless
  of extension, and compares against the handoff's Appendix C inventory.
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

EXTRACT = {
    "AOACLIENT.EXE", "AOADEFAULTS.PRF", "SCRTY.BIN", "SCENARIOS.AOA", "SCRIPTS.AOA",
    "SCHK.DAT", "AS_CHK.BIN", "AOAOBJECTS.ODB", "JRMAP.TRN", "RENEXE.EXE",
    "AOANOTES.TXT", "AOATUTORIAL.TXT", "AOACONTACT.TXT", "FX.AOA",
    "FILE0001.DAT", "FILE0002.DAT", "FILE0003.DAT", "FILE0004.DAT", "FILE0005.DAT",
    "FILE0006.DAT", "FILE0007.DAT", "FILE0008.DAT", "FILE0009.DAT", "FILE0010.DAT",
    "DATA.AOA", "HUD.AOA", "SOUNDS.AOA", "TEXTURES.AOA", "IMAGES.AOA", "KEYMAP.PDF",
}


def appendix_c(handoff: str, version: str):
    text = Path(handoff).read_text(encoding="utf-8")
    m = re.search(rf"CLIENT VERSION {re.escape(version)}: (\d+) members\n.*?\n(.*?)\n\n", text, re.S)
    rows = []
    for line in m.group(2).splitlines():
        name, size, crc = [p.strip() for p in line.split("|")]
        rows.append((name, int(size), crc.lower()))
    return int(m.group(1)), rows


def main() -> int:
    installer, version, handoff, out_dir = sys.argv[1:5]
    out = Path(out_dir)
    (out / "members").mkdir(parents=True, exist_ok=True)
    data = Path(installer).read_bytes()
    zf = zipfile.ZipFile(installer)
    infos = zf.infolist()
    bad = zf.testzip()
    members = []
    for i, zi in enumerate(infos):
        blob = zf.read(zi)
        base = zi.filename.replace("\\", "/").split("/")[-1]
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

    want_count, want_rows = appendix_c(handoff, version)
    got_rows = [(m["name"], m["file_size"], m["crc32"]) for m in members]
    result = {
        "installer": Path(installer).as_posix(),
        "installer_bytes": len(data),
        "installer_sha256": hashlib.sha256(data).hexdigest(),
        "zip_testzip_first_bad_member": bad,
        "member_count": len(members),
        "appendix_c_member_count": want_count,
        "appendix_c_exact_match_in_order": got_rows == want_rows,
        "appendix_c_diffs": [
            {"got": g, "want": w} for g, w in zip(got_rows, want_rows) if g != w
        ] + ([{"length_mismatch": [len(got_rows), len(want_rows)]}] if len(got_rows) != len(want_rows) else []),
        "pe_members": [m["name"] for m in members if m["pe"]],
        "mz_members": [m["name"] for m in members if m["mz"]],
        "members": members,
    }
    (out / "inventory.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "members"}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
