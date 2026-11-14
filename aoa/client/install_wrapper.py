"""Install the dgVoodoo2 DirectX 7 wrapper and a DPI-aware manifest into a game folder.

Usage:
    python -I tools/install_wrapper.py <dgVoodoo2_x_y.zip> <game_dir>

* Copies MS/x86/DDraw.dll and MS/x86/D3DImm.dll (DirectDraw + D3D7) and a
  dgVoodoo.conf with: windowed (FullScreenMode=false), centred window, no
  watermark, Alt+Enter allowed to toggle fullscreen. The game sizes itself to
  the desktop, so "windowed" behaves like borderless fullscreen and the real
  display mode is never changed.
* Writes AOACLIENT.EXE.manifest declaring the process DPI-aware. Without it,
  at >100% display scaling Windows reports a shrunken desktop (e.g. 1536x864
  for 1920x1080 at 125%), the game renders at that size and it gets upscaled.
  The client has no embedded manifest, so the external one is honoured.
* An existing dgVoodoo.conf keeps its [DirectX] values (the client
  launcher's graphics quality choices); every file is replaced atomically.

Delete DDraw.dll, D3DImm.dll and dgVoodoo.conf to go back to native DirectX.
"""
import argparse
import re
import hashlib
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

ZIP_SHA256 = "5ffde6927f7355ca3fdd5d785b581256a8e6539fa13e395a891ade6ba1040850"  # dgVoodoo2 2.87.5
CONF_CHANGES = [
    ("[General]", "FullScreenMode", "false"),
    ("[General]", "CenterAppWindow", "true"),
    ("[DirectX]", "dgVoodooWatermark", "false"),
    ("[DirectX]", "DisableAltEnterToToggleScreenMode", "false"),
]

MANIFEST = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<assembly xmlns="urn:schemas-microsoft-com:asm.v1" manifestVersion="1.0">
  <application xmlns="urn:schemas-microsoft-com:asm.v3">
    <windowsSettings>
      <dpiAware xmlns="http://schemas.microsoft.com/SMI/2005/WindowsSettings">true</dpiAware>
    </windowsSettings>
  </application>
</assembly>
"""


def set_key(text, section, key, value):
    out, current, done = [], None, False
    for line in text.splitlines(keepends=True):
        stripped = line.strip()
        if stripped.startswith("["):
            current = stripped
        if current == section and not done and re.match(rf"{key}\s*=", stripped):
            # Keep the line's own ending: `.` would also replace a CR before the LF.
            line = re.sub(r"=[^\r\n]*", lambda _: "= " + value, line, count=1)
            done = True
        out.append(line)
    if not done:
        raise KeyError(f"{section} {key} not found in dgVoodoo.conf")
    return "".join(out)


def section_values(text, section):
    """{key: value} of the plain key = value lines in one section."""
    values, current = {}, None
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("["):
            current = stripped
        elif current == section:
            match = re.fullmatch(r"(\w+)\s*=\s*(.*?)", stripped)
            if match:
                values[match[1]] = match[2]
    return values


def keep_section(conf, previous, section):
    """Carry an earlier conf's values for the keys this conf also has."""
    for key, value in section_values(previous, section).items():
        if key in section_values(conf, section):
            conf = set_key(conf, section, key, value)
    return conf


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("zip", type=Path, help="dgVoodoo2 2.87.5 release zip")
    parser.add_argument("game_dir", type=Path, help="game folder holding AOACLIENT.EXE")
    args = parser.parse_args(argv)
    from prepare_client import atomic_write
    zip_path, game_dir = args.zip, args.game_dir
    try:
        if hashlib.sha256(zip_path.read_bytes()).hexdigest() != ZIP_SHA256:
            sys.exit("requires the verified dgVoodoo2 2.87.5 archive; no files changed")
        if not (game_dir / "AOACLIENT.EXE").exists():
            sys.exit(f"{game_dir} has no AOACLIENT.EXE")
        with zipfile.ZipFile(zip_path) as z:
            files = {name: z.read(member) for member, name in (("MS/x86/DDraw.dll", "DDraw.dll"),
                                                                ("MS/x86/D3DImm.dll", "D3DImm.dll"))}
            conf = z.read("dgVoodoo.conf").decode("latin1")
        previous = game_dir / "dgVoodoo.conf"
        if previous.exists():
            conf = keep_section(conf, previous.read_bytes().decode("latin1"), "[DirectX]")
        for section, key, value in CONF_CHANGES:
            conf = set_key(conf, section, key, value)
        # Build everything before the first write.
        files["dgVoodoo.conf"] = conf.encode("latin1")
        files["AOACLIENT.EXE.manifest"] = MANIFEST.encode("utf-8")
        for name, data in files.items():
            atomic_write(game_dir / name, data)
    except (OSError, KeyError, zipfile.BadZipFile) as error:
        sys.exit(f"Wrapper install failed: {error}")
    print(f"installed {zip_path.name} wrapper and DPI manifest into {game_dir}")


if __name__ == "__main__":
    main()
