"""Build a playable game folder from a Wise/ZIP installer without running it.

Usage:
    python -I tools/make_install.py <installer.exe> <out_dir>

The AoA client loads every data file from its working directory (flat layout;
it creates Logs\\, images\\ and per-player folders itself at runtime). This
extracts the game payload members into <out_dir> under their basenames and
skips the Wise installer's own machinery (script dialogs, uninstaller, the
bundled 1990s REGSVR32/OCXREG32). ACTIVESKIN.OCX is extracted but NOT
registered; see tools/register_activeskin.ps1.

Member paths are never trusted: only the basename is used, and it must match
[A-Za-z0-9_.-]+. Refuses to overwrite an existing <out_dir>.
"""
import hashlib
import json
import re
import sys
import zipfile
from pathlib import Path

INSTALLER_ONLY = {
    "PROGRESS.DLL", "WISE0001.DLL", "W32INST.DLL", "UNWISE32.EXE",
    "OCXREG32.EXE", "REGSVR32.EXE",
}
INSTALLER_ONLY_RE = re.compile(r"^FILE\d{4}\.DAT$")
SAFE_NAME = re.compile(r"^[A-Za-z0-9_.-]+$")


def main() -> int:
    installer, out_dir = sys.argv[1:3]
    out = Path(out_dir)
    if out.exists():
        print(f"refusing to overwrite existing {out}", file=sys.stderr)
        return 1
    out.mkdir(parents=True)
    written, skipped = [], []
    with zipfile.ZipFile(installer) as zf:
        for zi in zf.infolist():
            base = zi.filename.replace("\\", "/").split("/")[-1]
            upper = base.upper()
            if upper in INSTALLER_ONLY or INSTALLER_ONLY_RE.match(upper):
                skipped.append(zi.filename)
                continue
            if not SAFE_NAME.match(base):
                raise ValueError(f"unexpected member name {zi.filename!r}")
            blob = zf.read(zi)
            dest = out / upper
            if dest.exists():
                # 2.7.1+ installers carry AOANOTES.TXT twice; only accept true duplicates.
                if dest.read_bytes() != blob:
                    raise ValueError(f"conflicting duplicate member {zi.filename!r}")
                continue
            dest.write_bytes(blob)
            written.append({"name": upper, "bytes": len(blob),
                            "sha256": hashlib.sha256(blob).hexdigest()})
    record = {"installer": Path(installer).as_posix(), "out_dir": out.as_posix(),
              "written": written, "skipped_installer_members": skipped}
    (out / "_install_manifest.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
    print(f"wrote {len(written)} files to {out}; skipped {len(skipped)} installer members")
    return 0


if __name__ == "__main__":
    sys.exit(main())
