"""Launch the client with individually selectable visual additions.

Selections are read from the installed EXE, wrapper and texture pack. Apply
uses the existing verified setup/undo path; no game assets are downloaded.
"""
import argparse
import configparser
import csv
import io
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import install_wrapper
import prepare_client as setup
import texture_pack

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_GAME = ROOT / "game/2.9.2"
PACK_CACHE = "_launcher_texture_pack.json"
PACK_SUFFIX = ".launcher-texture-pack"
# key, visible label, patch module. Adding a patch here supplies its checkbox,
# installed-state detection and explicit on/off argument to prepare().
PATCHES = (
    ("distant_objects", "Distant objects — extended visibility", setup.object_persistence),
    ("experimental_solids", "Solid world models — reduce distant shape popping", setup.solid_world_render),
    ("experimental_asteroids", "Asteroid models only — reduce shape popping", setup.asteroid_render),
    ("experimental_world_detail", "Full world mesh and texture detail", setup.world_detail),
    ("experimental_station_detail", "Full station detail only", setup.station_detail),
    ("experimental_texture32", "32-bit textures — richer color and alpha", setup.texture32),
    ("smooth_frame_clock", "Smoother frame timing", setup.frame_clock),
    ("bounded_visibility", "Corrected object visibility math", setup.visibility_fix),
    ("chase_camera", "Chase camera, orbit view and visible player ship (F2/F4)", setup.third_person),
    ("menu_framing", "Widescreen ship-selection framing", setup.menu_aspect),
)
# key, label, DirectX configuration key, enabled value, original value
QUALITY = (
    ("antialiasing", "Anti-aliasing (8x)", "Antialiasing", "8x", "appdriven"),
    ("filtering", "Anisotropic texture filtering (16x)", "Filtering", "16", "appdriven"),
    ("point_filter", "Preserve point-sampled textures", "KeepFilterIfPointSampled", "true", "false"),
    ("mipmaps", "Generated mipmaps — reduce texture shimmer", "Mipmapping", "autogen_bilinear", "appdriven"),
    ("phong", "Per-pixel lighting (Phong)", "PhongShadingWhenPossible", "true", "false"),
)
VISUAL_KEYS = tuple(p[0] for p in PATCHES) + tuple(q[0] for q in QUALITY) + ("texture_pack",)
EXCLUSIVE = (("experimental_solids", "experimental_asteroids"),
             ("experimental_world_detail", "experimental_station_detail"))


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
    options = {key: module.NAME in state["patches"] for key, _, module in PATCHES}
    quality = wrapper_options(folder)
    for key, _, conf_key, _, original in QUALITY:
        options[key] = quality is not None and quality[conf_key] != original
    active = texture_pack.verified(folder)
    cache = cached_pack(folder) if active is None else None
    options["texture_pack"] = bool(active and active["archives"])
    options["powerup_pickups"] = setup.powerup_pickup.NAME in state["patches"]
    options["station"] = state["host"] if state["host"] != "aoahost.com" else "localhost"
    return options, {"wrapper": quality is not None, "texture_pack": bool(active and active["archives"] or cache)}


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
    for key in (*VISUAL_KEYS, "powerup_pickups"):
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
    kwargs = {key: options[key] for key, _, _ in PATCHES}
    kwargs["powerup_pickups"] = options["powerup_pickups"]
    # Preflight composition and wrapper edits before any writes.
    setup.configure(exe.read_bytes(), host=options["station"], **kwargs)
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
        setup.prepare(exe, host=options["station"], **kwargs)
        if conf is not None and conf.encode("latin1") != before[conf_path]:
            setup.atomic_write(conf_path, conf.encode("latin1"))
        set_texture_pack(folder, options["texture_pack"])
        result = setup.check(exe)
        installed, _ = read_settings(folder)
        if any(installed[key] != options[key] for key in (*VISUAL_KEYS, "powerup_pickups", "station")):
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


def gui(folder=DEFAULT_GAME, run=True):
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk

    root = tk.Tk()
    root.title("Ace of Angels — Client launcher")
    root.minsize(760, 690)
    game = tk.StringVar(value=str(Path(folder).resolve()))
    station = tk.StringVar()
    status = tk.StringVar(value="Reading installed settings…")
    variables = {key: tk.BooleanVar(value=False) for key in (*VISUAL_KEYS, "powerup_pickups")}
    checks = {}
    loaded_folder = None
    top = ttk.Frame(root, padding=12)
    top.pack(fill="x")
    ttk.Label(top, text="Ace of Angels", font=("Segoe UI", 18, "bold")).grid(row=0, column=0, sticky="w")
    ttk.Label(top, text="Choose your visual additions. Settings take effect on the next launch.").grid(
        row=1, column=0, columnspan=3, sticky="w", pady=(4, 12))
    ttk.Entry(top, textvariable=game, state="readonly").grid(row=2, column=0, columnspan=2, sticky="ew")
    top.columnconfigure(0, weight=1)

    def load():
        nonlocal loaded_folder
        loaded_folder = None
        apply_button.state(["disabled"])
        launch_button.state(["disabled"])
        try:
            selected, available = read_settings(game.get())
            for key, var in variables.items():
                var.set(selected[key])
            station.set(selected["station"])
            for key, *_ in QUALITY:
                checks[key].state(["!disabled"] if available["wrapper"] else ["disabled"])
            checks["texture_pack"].state(["!disabled"] if available["texture_pack"] else ["disabled"])
            loaded_folder = game.get()
            apply_button.state(["!disabled"])
            launch_button.state(["!disabled"])
            notes = []
            if not available["texture_pack"]:
                notes.append("Replacement textures unavailable — install a pack to enable this option.")
            if not available["wrapper"]:
                notes.append("Graphics quality options require the dgVoodoo wrapper.")
            status.set("Loaded installed settings." + ("\n" + "\n".join(notes) if notes else ""))
        except (OSError, ValueError, KeyError, configparser.Error) as error:
            status.set(f"Cannot load this game folder: {error}")

    def browse():
        selected = filedialog.askdirectory(parent=root, initialdir=game.get(), title="Choose the game folder")
        if selected:
            game.set(selected)
            load()

    ttk.Button(top, text="Browse…", command=browse).grid(row=2, column=2, padx=(8, 0))

    def changed(key):
        if variables[key].get():
            for a, b in EXCLUSIVE:
                if key in (a, b):
                    variables[b if key == a else a].set(False)
        status.set("Unsaved selections. Choose Apply or Play to save them.")

    columns = ttk.Frame(root)
    columns.pack(fill="both", expand=True, padx=12)
    columns.columnconfigure(0, weight=1)
    columns.columnconfigure(1, weight=1)
    visuals = ttk.LabelFrame(columns, text="Visual additions", padding=10)
    visuals.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
    quality = ttk.LabelFrame(columns, text="Graphics quality", padding=10)
    quality.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
    for parent, entries in ((visuals, [(k, label) for k, label, _ in PATCHES]),
                            (quality, [(k, label) for k, label, *_ in QUALITY]
                             + [("texture_pack", "Replacement texture pack")])):
        for key, label in entries:
            check = ttk.Checkbutton(parent, text=label, variable=variables[key], command=lambda k=key: changed(k))
            check.pack(anchor="w", pady=5)
            checks[key] = check
    ttk.Label(quality, text="Unchecked graphics effects use the original\napplication-controlled settings.\n\nTexture packs can be switched off and back on\nwithout rebuilding the replacement images.",
              foreground="#555", justify="left").pack(anchor="w", pady=(14, 0))

    def original_visuals():
        for key in VISUAL_KEYS:
            variables[key].set(False)
        status.set("Original visuals selected. Choose Apply or Play to save.")

    presets = ttk.Frame(root, padding=(12, 10))
    presets.pack(fill="x")
    ttk.Button(presets, text="Original visuals (all off)", command=original_visuals).pack(side="left")
    ttk.Button(presets, text="Reload installed settings", command=load).pack(side="left", padx=8)
    other = ttk.LabelFrame(root, text="Connection and gameplay", padding=10)
    other.pack(fill="x", padx=12)
    ttk.Label(other, text="Station host").pack(side="left")
    ttk.Entry(other, textvariable=station, width=18).pack(side="left", padx=(8, 20))
    ttk.Checkbutton(other, text="Restored power-up pickups", variable=variables["powerup_pickups"],
                    command=lambda: changed("powerup_pickups")).pack(side="left")
    ttk.Label(root, text="Compatibility fixes and host-provided map content remain active.",
              foreground="#555").pack(anchor="w", padx=12, pady=(10, 0))
    ttk.Label(root, textvariable=status, wraplength=850, justify="left").pack(fill="x", padx=12, pady=10)
    bottom = ttk.Frame(root, padding=(12, 0, 12, 12))
    bottom.pack(fill="x", side="bottom")

    def apply(play=False):
        if loaded_folder != game.get():
            return
        options = {key: var.get() for key, var in variables.items()}
        options["station"] = station.get().strip()
        root.config(cursor="watch")
        root.update_idletasks()
        try:
            if play:
                launch(game.get(), options)
            else:
                apply_settings(game.get(), options)
            status.set("Game launched. Close it before changing settings." if play else "Settings saved and verified. Ready to play.")
        except (OSError, ValueError, KeyError, RuntimeError, subprocess.SubprocessError, configparser.Error) as error:
            status.set(f"Could not {'launch' if play else 'apply'}: {error}")
            messagebox.showerror("Client launcher", str(error), parent=root)
        finally:
            root.config(cursor="")

    launch_button = ttk.Button(bottom, text="Play", command=lambda: apply(True))
    launch_button.pack(side="right", padx=(8, 0))
    apply_button = ttk.Button(bottom, text="Apply", command=apply)
    apply_button.pack(side="right")
    load()
    if run:
        root.mainloop()
    return root, variables, checks


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("game", type=Path, nargs="?", default=DEFAULT_GAME)
    args = parser.parse_args()
    gui(args.game)
