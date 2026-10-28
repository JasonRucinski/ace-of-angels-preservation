"""Build, install, restore, or capture the optional Classic Enhanced UI mode."""
import argparse
import configparser
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
from classic_enhanced import ROOT, CONFIG, RECORD, check, digest, require_x86

SETUP_SHA = "afe4c8f13048306307983b8b3d41d5bf00a86820440b0e57dea10950e1176445"
SDK_SHA = "936d3e9cc0506f16e635266299f43a6b9db49023af1573fae572195506e5b764"
ADDON = "ClassicUI.addon32"
BACKUP = "_classic_ui_backup"
SOURCE = ROOT / "tools/classic_ui_addon.cpp"


def build(sdk, output):
    if digest(sdk) != SDK_SHA:
        raise ValueError("requires the official ReShade v6.8.0 source.zip (see docs/classic-enhanced.md)")
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        include = Path(tmp)
        with zipfile.ZipFile(sdk) as archive:
            for name in archive.namelist():
                if "/include/" in name and name.endswith(".hpp"):
                    (include / Path(name).name).write_bytes(archive.read(name))
        subprocess.run([sys.executable, "-m", "ziglang", "c++", "-target", "x86-windows-gnu",
                        "-std=c++20", "-O2", "-shared", "-s", "-Wno-ignored-attributes",
                        "-Wno-unknown-attributes", "-I", str(include), str(SOURCE), "-o", str(output),
                        "-luser32", "-ld3d11", "-ldxguid"], check=True)
    output.with_suffix(".json").write_text(json.dumps({"source_sha256": digest(SOURCE),
        "addon_sha256": digest(output), "sdk_sha256": SDK_SHA}, indent=2), encoding="utf-8")
    return {"addon": str(output)}


def install(folder, setup, addon):
    folder = folder.resolve()
    state = check(folder)
    if state["runtime"] != "enabled" or (folder / BACKUP).exists():
        raise ValueError("requires an enabled standard experiment; restore existing UI mode first")
    if digest(setup) != SETUP_SHA:
        raise ValueError("requires official ReShade_Setup_6.8.0_Addon.exe with the pinned hash")
    manifest = json.loads(addon.with_suffix(".json").read_text(encoding="utf-8"))
    if (manifest["source_sha256"] != digest(SOURCE) or manifest["addon_sha256"] != digest(addon)
            or manifest["sdk_sha256"] != SDK_SHA):
        raise ValueError("add-on build is stale or changed; rebuild from project source")
    # The client is never modified on disk. Validate the exact instruction that
    # the add-on will replace in process memory, without depending on pefile.
    import struct
    data = (folder / "AOACLIENT.EXE").read_bytes()
    pe = struct.unpack_from("<I", data, 60)[0]
    sections, optional = struct.unpack_from("<H", data, pe + 6)[0], struct.unpack_from("<H", data, pe + 20)[0]
    offset = None
    for i in range(sections):
        pos = pe + 24 + optional + 40 * i
        size, rva, raw_size, raw = struct.unpack_from("<IIII", data, pos + 8)
        if rva <= 0x4B3C7 < rva + min(size, raw_size):
            offset = raw + 0x4B3C7 - rva
    if offset is None or data[offset:offset + 6] != bytes.fromhex("8b8e98010000"):
        raise ValueError("unsupported client HUD boundary")
    if (folder / ADDON).exists():
        raise ValueError("add-on already exists")
    with zipfile.ZipFile(setup) as archive:
        runtime = archive.read("ReShade32.dll")
    require_x86(runtime)
    require_x86(addon.read_bytes())
    record = json.loads((folder / RECORD).read_text(encoding="utf-8"))
    settings = configparser.ConfigParser(interpolation=None)
    settings.optionxform = str
    settings.read(folder / "ReShade.ini", encoding="utf-8-sig")
    for section in ("OVERLAY", "SCREENSHOT"):
        if not settings.has_section(section):
            settings.add_section(section)
    settings["OVERLAY"]["ShowScreenshotMessage"] = "0"
    settings["SCREENSHOT"].update({"SaveBeforeShot": "0", "PostSaveCommand": "",
        "SavePresetFile": "1", "SavePath": ".\\comparison-captures", "FileFormat": "1",
        "FileNaming": "AOA_%Date%_%Time%_%Count%_%BeforeAfter%"})
    # Request a writable handle before creating the backup (Windows image locks).
    with (folder / "dxgi.dll").open("r+b"):
        pass
    backup = folder / BACKUP
    backup.mkdir()
    for name in ("dxgi.dll", RECORD, "ReShade.ini", "classic-enhanced-shaders/AOAClassic.fx"):
        target = backup / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(folder / name, target)
    try:
        (folder / "dxgi.dll").write_bytes(runtime)
        shutil.copyfile(addon, folder / ADDON)
        shutil.copyfile(CONFIG / "AOAClassic.fx", folder / "classic-enhanced-shaders/AOAClassic.fx")
        with (folder / "ReShade.ini").open("w", encoding="utf-8") as stream:
            settings.write(stream, space_around_delimiters=False)
        import hashlib
        record.update({"runtime_sha256": hashlib.sha256(runtime).hexdigest(),
            "setup_sha256": SETUP_SHA, "setup_url": "https://reshade.me/downloads/ReShade_Setup_6.8.0_Addon.exe",
            "ui_addon_sha256": digest(addon), "note": "World effect before HUD drawing; source client unchanged."})
        (folder / RECORD).write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    except Exception:
        restore(folder)
        raise
    return check(folder)


def restore(folder):
    folder = folder.resolve()
    backup = folder / BACKUP
    if not backup.is_dir():
        raise ValueError("no UI mode backup")
    if (folder / "dxgi.dll.classic-disabled").exists():
        raise ValueError("enable the experiment with classic_enhanced.py on before restoring UI mode")
    # Keep the backup for inspection; don't delete user files recursively.
    for name in ("dxgi.dll", RECORD, "ReShade.ini", "classic-enhanced-shaders/AOAClassic.fx"):
        shutil.copyfile(backup / name, folder / name)
    if (folder / ADDON).exists():
        (folder / ADDON).rename(folder / (ADDON + ".disabled"))
    backup.rename(folder / (BACKUP + "_restored_" + str(time.time_ns())))
    return check(folder)


def capture(folder, output, engines=False):
    from compare_classic_capture import build as report
    folder = folder.resolve()
    if not (folder / ADDON).is_file():
        raise ValueError("UI add-on is not installed")
    captures = folder / "comparison-captures"
    existing = set(captures.glob("*.png"))
    (folder / ("classic-engine-capture.flag" if engines else "classic-ui-capture.flag")).touch()
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        before = sorted(p for p in captures.glob("*_EngineBefore.png" if engines else "*_UIOriginal.png") if p not in existing)
        after = sorted(p for p in captures.glob("*_EngineAfter.png" if engines else "*_UIProtected.png") if p not in existing)
        if before and after:
            try:
                return report(before[-1], after[-1], output, sequential_ui=True, engines=engines)
            except (OSError, ValueError):
                if output.exists():
                    raise
        time.sleep(0.2)
    raise ValueError("no complete capture; enter offline flight with the effect enabled")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("action", choices=("build", "install", "restore", "capture"))
    p.add_argument("folder", type=Path)
    p.add_argument("--sdk", type=Path)
    p.add_argument("--setup", type=Path)
    p.add_argument("--addon", type=Path)
    p.add_argument("--output", type=Path)
    p.add_argument("--engines", action="store_true", help="capture exhaust off/on, keeping other effects enabled")
    a = p.parse_args()
    try:
        if a.action == "build":
            if not a.sdk:
                p.error("build requires --sdk")
            result = build(a.sdk, a.folder)
        elif a.action == "install":
            if not a.setup or not a.addon:
                p.error("install requires --setup and --addon; close the game first")
            result = install(a.folder, a.setup, a.addon)
        elif a.action == "restore":
            result = restore(a.folder)
        else:
            result = capture(a.folder, a.output or ROOT / "work/classic-enhanced" / ("ui-" + str(time.time_ns())), engines=a.engines)
        print(json.dumps(result, indent=2))
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as error:
        p.exit(1, f"Classic UI: {error}\n")


if __name__ == "__main__":
    main()
