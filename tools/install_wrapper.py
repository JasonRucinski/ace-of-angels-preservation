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

Delete DDraw.dll, D3DImm.dll and dgVoodoo.conf to go back to native DirectX.
"""
import re
import hashlib
import sys
import zipfile
from pathlib import Path

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
            line = re.sub(r"=.*", "= " + value, line, count=1)
            done = True
        out.append(line)
    if not done:
        raise KeyError(f"{section} {key} not found in dgVoodoo.conf")
    return "".join(out)


def main():
    zip_path, game_dir = Path(sys.argv[1]), Path(sys.argv[2])
    if hashlib.sha256(zip_path.read_bytes()).hexdigest() != "5ffde6927f7355ca3fdd5d785b581256a8e6539fa13e395a891ade6ba1040850":
        sys.exit("requires the verified dgVoodoo2 2.87.5 archive; no files changed")
    if not (game_dir / "AOACLIENT.EXE").exists():
        sys.exit(f"{game_dir} has no AOACLIENT.EXE")
    with zipfile.ZipFile(zip_path) as z:
        for member, name in (("MS/x86/DDraw.dll", "DDraw.dll"), ("MS/x86/D3DImm.dll", "D3DImm.dll")):
            (game_dir / name).write_bytes(z.read(member))
        conf = z.read("dgVoodoo.conf").decode("latin1")
    for section, key, value in CONF_CHANGES:
        conf = set_key(conf, section, key, value)
    (game_dir / "dgVoodoo.conf").write_text(conf, encoding="latin1")
    (game_dir / "AOACLIENT.EXE.manifest").write_text(MANIFEST, encoding="utf-8")
    print(f"installed {zip_path.name} wrapper and DPI manifest into {game_dir}")


if __name__ == "__main__":
    main()
