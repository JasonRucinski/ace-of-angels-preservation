"""Prepare an isolated, opt-in ReShade experiment; never edit the source game."""
import argparse
import hashlib
import json
import shutil
import struct
import subprocess
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from install_wrapper import set_key
from prepare_client import wrapper_state

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config/classic-enhanced"
SETUP_SHA256 = "207aea16205fbf952bc8fe1879966672454cf04002e7ad34237c7990a5b3c0b4"
SETUP_URL = "https://reshade.me/downloads/ReShade_Setup_6.8.0.exe"
RECORD = "_classic_enhanced.json"
ACTIVE = "dxgi.dll"
DISABLED = "dxgi.dll.classic-disabled"


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def require_x86(data):
    if data[:2] != b"MZ" or len(data) < 64:
        raise ValueError("expected a Windows PE binary")
    offset = struct.unpack_from("<I", data, 60)[0]
    if (offset + 26 > len(data) or data[offset:offset + 4] != b"PE\0\0"
            or struct.unpack_from("<H", data, offset + 4)[0] != 0x14C
            or struct.unpack_from("<H", data, offset + 24)[0] != 0x10B):
        raise ValueError("requires the 32-bit x86 client/runtime")


def prepare(source, destination, setup):
    source, destination, setup = source.resolve(), destination.resolve(), setup.resolve()
    if not source.is_dir():
        raise ValueError("source game folder does not exist")
    if destination.exists() or destination == source or source in destination.parents:
        raise ValueError("destination must be a new folder outside the source game")
    # Fail before copying, including when the source contains other injectors.
    reserved = (ACTIVE, DISABLED, "d3d9.dll", "d3d10.dll", "d3d11.dll", "d3d12.dll",
                "ReShade.ini", "ReShade.log", "ClassicEnhanced.ini", RECORD,
                "classic-enhanced-shaders", "classic-enhanced-cache")
    if any((source / name).exists() for name in reserved):
        raise ValueError("source already contains a graphics injector/experiment; use a clean source")
    for path in source.rglob("*"):
        if path.is_symlink() or path.is_junction():
            raise ValueError(f"source contains a link: {path}")
    if wrapper_state(source) != "dgVoodoo2-2.87.5":
        raise ValueError("requires the project's dgVoodoo2 2.87.5 wrapper")
    require_x86((source / "AOACLIENT.EXE").read_bytes())
    if digest(setup) != SETUP_SHA256:
        raise ValueError(f"requires the pinned standard ReShade 6.8.0 download: {SETUP_URL}")
    with zipfile.ZipFile(setup) as archive:
        runtime = archive.read("ReShade32.dll")
    require_x86(runtime)
    # Explicit D3D11 output makes the injection path reproducible.
    wrapper_config = set_key((source / "dgVoodoo.conf").read_bytes().decode("latin1"),
                             "[General]", "OutputAPI", "d3d11_fl11_0").encode("latin1")
    assets = {name: (CONFIG / name).read_bytes()
              for name in ("AOAClassic.fx", "ClassicEnhanced.ini", "Subtle.ini", "ReShade.ini")}
    source_hashes = {str(p.relative_to(source)): digest(p)
                     for p in source.rglob("*") if p.is_file()}
    shutil.copytree(source, destination)
    for name, expected in source_hashes.items():
        if digest(destination / name) != expected or digest(source / name) != expected:
            raise ValueError("source changed during copy; close the game and use a fresh destination")
    (destination / "dgVoodoo.conf").write_bytes(wrapper_config)
    (destination / ACTIVE).write_bytes(runtime)
    (destination / "classic-enhanced-shaders").mkdir()
    (destination / "classic-enhanced-shaders/AOAClassic.fx").write_bytes(assets["AOAClassic.fx"])
    for name in ("ClassicEnhanced.ini", "Subtle.ini", "ReShade.ini"):
        (destination / name).write_bytes(assets[name])
    record = {
        "schema": 1, "source": str(source), "destination": str(destination),
        "reshade_version": "6.8.0", "setup_url": SETUP_URL, "setup_sha256": SETUP_SHA256,
        "runtime_sha256": hashlib.sha256(runtime).hexdigest(),
        "client_sha256": source_hashes["AOACLIENT.EXE"],
        "source_hashes": source_hashes,
        "note": "Copied client patches/settings preserved. Shader applies to HUD as well as world.",
    }
    (destination / RECORD).write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return check(destination)


def check(folder):
    folder = folder.resolve()
    record = json.loads((folder / RECORD).read_text(encoding="utf-8"))
    if record.get("schema") != 1 or Path(record["destination"]) != folder:
        raise ValueError("not the recorded experiment folder")
    if digest(folder / "AOACLIENT.EXE") != record["client_sha256"]:
        raise ValueError("experiment client changed since preparation")
    wrapper_state(folder)
    present = [name for name in (ACTIVE, DISABLED) if (folder / name).exists()]
    if len(present) != 1 or digest(folder / present[0]) != record["runtime_sha256"]:
        raise ValueError("runtime missing, ambiguous, or changed")
    if "ui_addon_sha256" in record:
        addon = folder / "ClassicUI.addon32"
        if not addon.is_file() or digest(addon) != record["ui_addon_sha256"]:
            raise ValueError("UI preservation add-on is missing or changed")
    for name in ("ReShade.ini", "ClassicEnhanced.ini", "classic-enhanced-shaders/AOAClassic.fx"):
        if not (folder / name).is_file():
            raise ValueError(f"missing experiment file: {name}")
    return {"folder": str(folder), "runtime": "enabled" if present[0] == ACTIVE else "disabled",
            "client": "unchanged copy", "toggle": "Scroll Lock", "settings": "Home"}


def switch(folder, enabled):
    state = check(folder)
    if (state["runtime"] == "enabled") != enabled:
        (folder / (DISABLED if enabled else ACTIVE)).rename(folder / (ACTIVE if enabled else DISABLED))
    return check(folder)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "check", "on", "off", "launch"))
    parser.add_argument("folder", type=Path, help="new experiment folder, or an existing experiment")
    parser.add_argument("--source", type=Path, default=ROOT / "game/2.9.2")
    parser.add_argument("--setup", type=Path, help="official standard ReShade 6.8.0 installer (extracted, never run)")
    args = parser.parse_args()
    try:
        if args.action == "prepare":
            if args.setup is None:
                parser.error("prepare requires --setup")
            result = prepare(args.source, args.folder, args.setup)
        elif args.action in ("on", "off"):
            result = switch(args.folder, args.action == "on")
        else:
            result = check(args.folder)
            if args.action == "launch":
                folder = args.folder.resolve()
                process = subprocess.Popen([str(folder / "AOACLIENT.EXE")], cwd=folder)
                result["pid"] = process.pid
        print(json.dumps(result, indent=2))
    except (OSError, ValueError, KeyError, zipfile.BadZipFile) as error:
        parser.exit(1, f"Classic Enhanced: {error}\n")


if __name__ == "__main__":
    main()
