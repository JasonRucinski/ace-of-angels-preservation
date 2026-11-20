"""Look at a game folder and say what state it is in; changes nothing.

examine() reports the executable (missing, the original, prepared, needing
an update, or not one the project knows), the game data files against
config/client-2.9.2.json, the patch level, the graphics wrapper, whether
the login screen skin is registered for this Windows user, and JRMAP's
terrain file. Every check is the engines' own (aoa/client/prepare.py); this
module only turns their exceptions into states and plain sentences.
"""
import hashlib
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

from aoa.client import install_wrapper, prepare
from aoa.maps import registry
from aoa.paths import ROOT

EXE = "AOACLIENT.EXE"
OCX = "ACTIVESKIN.OCX"
SKIN_RECORD = "_activeskin_registered.json"
JRMAP_SOURCE = "JRMAP.TRN"
JRMAP_TERRAIN = registry.MAPS[registry.MAP_NAMES.index("JRMAP")][2]
EXPORT = ROOT / "work/2.9.2/export/AOAOBJECTS"


@dataclass
class FolderState:
    folder: Path
    exe: str = "missing"        # missing, original, prepared, update, unprepared, unknown
    exe_problem: str = ""
    assets_ok: bool = False
    assets_problem: str = ""
    patch_level: int = None
    patches: list = field(default_factory=list)
    server: str = None
    wrapper: str = "none"       # none, installed, damaged
    wrapper_problem: str = ""
    skin: bool = None           # None: not a Windows PC
    jrmap_source: bool = False
    jrmap_terrain: bool = False

    @property
    def exists(self):
        return self.exe != "missing"

    @property
    def prepared(self):
        return self.exe == "prepared"

    @property
    def ready(self):
        """Everything Play needs (the wrapper and skin are judged by their own steps)."""
        return self.prepared and self.assets_ok


def sha_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def examine(folder, skin_check=None):
    folder = Path(folder)
    state = FolderState(folder)
    exe = folder / EXE
    state.jrmap_source = (folder / JRMAP_SOURCE).is_file()
    state.jrmap_terrain = (folder / JRMAP_TERRAIN).is_file()
    if not exe.is_file():
        return state
    try:
        data = exe.read_bytes()
        info = prepare.inspect(data)
    except (OSError, ValueError) as error:
        state.exe, state.exe_problem = "unknown", str(error)
        return state
    state.patches, state.server = list(info["patches"]), info["host"]
    if info["source"] == "original-2.9.2":
        state.exe = "original"
    else:
        try:
            _, backup, record_path = prepare.paths(exe)
            record = prepare.load_record(record_path, backup, data)
        except (OSError, ValueError, KeyError) as error:
            state.exe, state.exe_problem = "unknown", str(error)
            record = None
        if state.exe != "unknown":
            if record is None or record.get("status") != "ready" or not prepare.REQUIRED <= set(info["patches"]):
                state.exe = "unprepared"
            elif prepare.OUTDATED & set(info["patches"]) or record.get("patch_version") != prepare.PATCH_VERSION:
                state.exe, state.patch_level = "update", record.get("patch_version")
            else:
                state.exe, state.patch_level = "prepared", record.get("patch_version")
    try:
        prepare.check_assets(folder)
        state.assets_ok = True
    except (OSError, ValueError, KeyError) as error:
        state.assets_problem = str(error)
    try:
        state.wrapper = "none" if prepare.wrapper_state(folder) == "native-directx7" else "installed"
    except (OSError, ValueError) as error:
        state.wrapper, state.wrapper_problem = "damaged", str(error)
    state.skin = (skin_check or skin_registered)(folder)
    return state


# --- login screen skin (ActiveSkin, registered per user by tools/register_activeskin.ps1) ---
def skin_registered(folder, platform=sys.platform, registry_scan=None):
    """True or False on Windows; None elsewhere (the skin is a Windows control).

    Registered means: this launcher recorded a successful registration of
    this very file, and (when the registry can be read) a per-user COM class
    still points at it, which also catches a moved game folder.
    """
    if platform != "win32":
        return None
    ocx = (Path(folder) / OCX).resolve()
    try:
        record = json.loads((Path(folder) / SKIN_RECORD).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        record = None
    recorded = isinstance(record, dict) and record.get("ocx") == str(ocx)
    scan = registry_scan or user_com_servers
    servers = scan()
    if servers is None:
        return recorded
    return os.path.normcase(str(ocx)) in {os.path.normcase(s) for s in servers}


def user_com_servers():
    """Every InprocServer32 path under HKCU\\Software\\Classes\\CLSID, or None when unreadable. Windows only."""
    try:
        import winreg
    except ImportError:
        return None
    found = set()
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Classes\CLSID") as classes:
            index = 0
            while True:
                try:
                    name = winreg.EnumKey(classes, index)
                except OSError:
                    break
                index += 1
                try:
                    with winreg.OpenKey(classes, name + r"\InprocServer32") as server:
                        found.add(winreg.QueryValueEx(server, "")[0])
                except OSError:
                    continue
    except OSError:
        return None
    return found


def record_skin(folder):
    """Remember that the skin of this folder was registered (after the script reported success)."""
    ocx = (Path(folder) / OCX).resolve()
    prepare.atomic_write(Path(folder) / SKIN_RECORD, (json.dumps({"ocx": str(ocx)}) + "\n").encode())


# --- the graphics wrapper download -------------------------------------------------
def downloads_folder():
    return Path.home() / "Downloads"


def find_wrapper_zip(folders=None):
    """(path of the verified dgVoodoo2 2.87.5 zip, []) or (None, [zips with the wrong contents])."""
    wrong = []
    for folder in folders or [downloads_folder()]:
        folder = Path(folder)
        if not folder.is_dir():
            continue
        for candidate in sorted(folder.glob("dgVoodoo2*.zip")):
            try:
                if sha_file(candidate) == install_wrapper.ZIP_SHA256:
                    return candidate, []
            except OSError:
                continue
            wrong.append(candidate)
    return None, wrong


def export_ready(export=EXPORT):
    """Whether the map objects exported from the game files are there (for buoys and trials)."""
    export = Path(export)
    return export.is_dir() and (export.parent / "_export.json").is_file()
