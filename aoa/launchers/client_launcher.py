"""The client options behind the player window's Options tab: read, check, apply with rollback.

Selections are read from the installed EXE, wrapper and texture pack. Apply
uses the existing verified setup/undo path; no game assets are downloaded.
The window itself is aoa/launchers/play_app.py; main() opens it.
"""
import configparser
import csv
import io
import json
import os
import subprocess
from pathlib import Path

from aoa.client import install_wrapper
from aoa.client import patches
from aoa.client import prepare as setup
from aoa.client import texture_pack

from aoa.paths import ROOT
DEFAULT_GAME = ROOT / "game/2.9.2"
PACK_CACHE = "_launcher_texture_pack.json"
PACK_SUFFIX = ".launcher-texture-pack"
# The power-up checkbox sits with the Station, not with the visual additions.
GAMEPLAY = "powerup_pickups"
# key, visible label, Patch: every registry option with a checkbox label
# (aoa/client/patches/__init__.py supplies the checkbox, installed-state
# detection and the option prepare() takes).
PATCHES = tuple((p.option, p.label, p) for p in patches.OPTIONS.values() if p.label and p.option != GAMEPLAY)
# key, label, DirectX configuration key, enabled value, original value
QUALITY = (
    ("antialiasing", "Anti-aliasing (8x)", "Antialiasing", "8x", "appdriven"),
    ("filtering", "Anisotropic texture filtering (16x)", "Filtering", "16", "appdriven"),
    ("point_filter", "Preserve point-sampled textures", "KeepFilterIfPointSampled", "true", "false"),
    ("mipmaps", "Generated mipmaps — reduce texture shimmer", "Mipmapping", "autogen_bilinear", "appdriven"),
    ("phong", "Per-pixel lighting (Phong)", "PhongShadingWhenPossible", "true", "false"),
)
VISUAL_KEYS = tuple(p[0] for p in PATCHES) + tuple(q[0] for q in QUALITY) + ("texture_pack",)
EXCLUSIVE = tuple((b.option, a.option) for a, b in patches.CONFLICTS)


def wrapper_options(folder):
    if setup.wrapper_state(folder) == "native-directx7":
        return None
    conf = configparser.ConfigParser(interpolation=None, strict=True)
    # dgVoodoo starts with an unsectioned Version key.
    conf.read_string("[Header]\n" + (folder / "dgVoodoo.conf").read_bytes().decode("latin1"))
    # Fail on missing keys before any file changes, preserving unrelated keys.
    return {key: conf["DirectX"][key].strip().lower() for _, _, key, _, _ in QUALITY}


def cached_pack(folder):
    """Verify a cached pack independently of the currently installed archives."""
    path = folder / PACK_CACHE
    if not path.exists():
        return None
    record = json.loads(path.read_text(encoding="utf-8"))
    if record.get("schema") != 2 or not record.get("archives") or not set(record["archives"]) <= set(texture_pack.ARCHIVES):
        raise ValueError("invalid saved texture pack")
    for name, info in record["archives"].items():
        texture_pack.original(folder, name)
        if info["original_sha256"] != texture_pack.pinned(name):
            raise ValueError(f"{name}: saved pack original hash mismatch")
        if setup.sha((folder / (name + PACK_SUFFIX)).read_bytes()) != info["sha256"]:
            raise ValueError(f"{name}: saved texture pack was changed")
    return record


def read_settings(folder):
    folder = Path(folder).resolve()
    exe, backup, record = setup.paths(folder / "AOACLIENT.EXE")
    current = exe.read_bytes()
    state = setup.inspect(current)
    setup.load_record(record, backup, current)
    setup.check_assets(folder)
    # An older variant counts as on; Apply upgrades it.
    options = {key: any(variant in state["patches"] for variant, _ in patch.variants) for key, _, patch in PATCHES}
    quality = wrapper_options(folder)
    for key, _, conf_key, _, original in QUALITY:
        options[key] = quality is not None and quality[conf_key] != original
    active = texture_pack.verified(folder)
    cache = cached_pack(folder) if active is None else None
    options["texture_pack"] = bool(active and active["archives"])
    options[GAMEPLAY] = patches.OPTIONS[GAMEPLAY].id in state["patches"]
    options["station"] = state["host"] if state["host"] != "aoahost.com" else "localhost"
    return options, {"wrapper": quality is not None, "texture_pack": bool(active and active["archives"] or cache),
                     "outdated": sorted(setup.OUTDATED & set(state["patches"])),
                     "protection": setup.LOOPBACK_ONLY in state["patches"]}


def require_closed():
    """Do not change files underneath a client, including one launched elsewhere."""
    if os.name != "nt":
        return
    try:
        result = subprocess.run(["tasklist", "/FI", "IMAGENAME eq AOACLIENT.EXE", "/FO", "CSV", "/NH"],
                                capture_output=True, text=True, check=True, timeout=10,
                                creationflags=subprocess.CREATE_NO_WINDOW)
    except (OSError, subprocess.SubprocessError) as error:
        raise RuntimeError("Could not check whether the game is running. Reopen the launcher from Windows.") from error
    if any(row and row[0].lower() == "aoaclient.exe" for row in csv.reader(io.StringIO(result.stdout))):
        raise ValueError("Close Ace of Angels before applying settings or launching another copy.")


def validate_options(options, available):
    for key in (*VISUAL_KEYS, GAMEPLAY):
        if type(options.get(key)) is not bool:
            raise ValueError(f"{key}: expected an on/off selection")
    setup.host_field(options["station"])
    for a, b in EXCLUSIVE:
        if options[a] and options[b]:
            raise ValueError("Choose all-world or limited-only mode, not both.")
    if not available["wrapper"] and any(options[key] for key, *_ in QUALITY):
        raise ValueError("Install the supported dgVoodoo wrapper to use graphics quality options.")
    if options["texture_pack"] and not available["texture_pack"]:
        raise ValueError("No replacement texture pack is installed or saved in this game folder.")


def set_texture_pack(folder, enabled):
    active = texture_pack.verified(folder)
    if bool(active and active["archives"]) == enabled:
        return
    if not enabled:
        # Save the installed pack, not paths to source images that may move.
        for name in active["archives"]:
            setup.atomic_write(folder / (name + PACK_SUFFIX), (folder / name).read_bytes())
        setup.atomic_write(folder / PACK_CACHE, (json.dumps(active, indent=2) + "\n").encode())
        cached_pack(folder)
        texture_pack.undo(folder)
    else:
        record = cached_pack(folder)
        if record is None:
            raise ValueError("No saved replacement texture pack")
        setup.atomic_write(folder / texture_pack.RECORD, (json.dumps(record, indent=2) + "\n").encode())
        for name in record["archives"]:
            setup.atomic_write(folder / name, (folder / (name + PACK_SUFFIX)).read_bytes())
        texture_pack.verified(folder)


def apply_settings(folder, options):
    folder = Path(folder).resolve()
    require_closed()
    current, available = read_settings(folder)
    validate_options(options, available)
    exe = folder / "AOACLIENT.EXE"
    chosen = {key: options[key] for key, _, _ in PATCHES}
    chosen[GAMEPLAY] = options[GAMEPLAY]
    if options["station"] not in setup.LOOPBACK:
        # The launcher has no control for this probe, which needs a loopback Station.
        chosen[patches.BY_ID[setup.LOOPBACK_ONLY].option] = False
    # Preflight composition and wrapper edits before any writes.
    setup.configure(exe.read_bytes(), options["station"], chosen)
    conf_path = folder / "dgVoodoo.conf"
    conf = conf_path.read_bytes().decode("latin1") if available["wrapper"] else None
    if conf is not None:
        for key, _, conf_key, enhanced, original in QUALITY:
            # Keep any existing nonstandard enabled value until the box changes.
            if options[key] != current[key]:
                conf = install_wrapper.set_key(conf, "[DirectX]", conf_key, enhanced if options[key] else original)
    names = ["AOACLIENT.EXE", "AOACLIENT.EXE.setup-original", "_client_setup.json", "dgVoodoo.conf",
             texture_pack.RECORD, PACK_CACHE, *texture_pack.ARCHIVES,
             *(n + PACK_SUFFIX for n in texture_pack.ARCHIVES)]
    before = {folder / n: (folder / n).read_bytes() if (folder / n).exists() else None for n in names}
    try:
        setup.prepare(exe, chosen, station=options["station"])
        if conf is not None and conf.encode("latin1") != before[conf_path]:
            setup.atomic_write(conf_path, conf.encode("latin1"))
        set_texture_pack(folder, options["texture_pack"])
        result = setup.check(exe)
        installed, _ = read_settings(folder)
        if any(installed[key] != options[key] for key in (*VISUAL_KEYS, GAMEPLAY, "station")):
            raise ValueError("Installed settings did not match the selected options")
        return result
    except Exception as error:
        failures = []
        for path, data in before.items():
            try:
                if data is None:
                    path.unlink(missing_ok=True)
                elif not path.exists() or path.read_bytes() != data:
                    setup.atomic_write(path, data)
            except OSError as rollback_error:
                failures.append(f"{path.name}: {rollback_error}")
        if failures:
            raise RuntimeError(f"{error}; could not restore: {'; '.join(failures)}") from error
        raise


def launch(folder, options):
    apply_settings(folder, options)
    exe = Path(folder).resolve() / "AOACLIENT.EXE"
    return subprocess.Popen([str(exe)], cwd=exe.parent)


def main(argv=None):
    """The player window (aoa/launchers/play_app.py); this module keeps the options logic."""
    from aoa.launchers import play_app
    return play_app.main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
