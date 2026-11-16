"""The player's first-run steps, in order. Each step has check() and run().

check(state) -> Status: "done", "todo", "optional" (may be skipped),
"skipped", "waiting" (an earlier step is not done) or "unavailable" (not on
this system), with one plain sentence. run(progress) does the work and
reports with progress(text); it raises StepError with a sentence that says
what happened and what to do.

The steps only call the engines: the project's fetcher (tools/fetch.py,
through download_installer(), the one place it is called), make_install,
prepare, tools/register_activeskin.ps1 and install_wrapper. Nothing here
asks for administrator rights. The window runs every run() off its thread.
"""
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from aoa import builds, paths
from aoa.client import install_wrapper, make_install, prepare
from aoa.launchers import game_folder
from aoa.launchers.catalog import PATCH_LEVEL, WRAPPER_LOSS, WRAPPER_PAGE, WRAPPER_ZIP
from aoa.paths import ROOT

MANIFEST = ROOT / "manifest/downloads.json"
VERSION = "2.9.2"
DOWNLOADS = ROOT / "builds"
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


class StepError(Exception):
    """A step failed; str() is the sentence to show. `details` holds tool output, if any."""

    def __init__(self, text, details=""):
        super().__init__(text)
        self.details = details


@dataclass(frozen=True)
class Status:
    state: str
    text: str

    @property
    def ok(self):
        return self.state in ("done", "skipped")


def installer_entry(manifest=MANIFEST):
    """The manifest entry of the 2.9.2 installer: url, bytes, sha256, file name."""
    import json
    data = json.loads(Path(manifest).read_text(encoding="utf-8"))
    return next(d for d in data["downloads"] if d["runtime_version"] == VERSION)


def size_text(count):
    return f"{count / 1e6:.0f} MB"


def find_installer(root=DOWNLOADS, entry=None):
    """A downloaded 2.9.2 installer with the right size (its hash is checked by the fetcher
    and again before use), or None."""
    entry = entry or installer_entry()
    if not Path(root).is_dir():
        return None
    for candidate in sorted(Path(root).glob(f"*/{entry['suggested_local_filename']}")) + \
            sorted(Path(root).glob("*/aoa-current.exe")):
        if candidate.is_file() and candidate.stat().st_size == entry["bytes"]:
            return candidate
    return None


def run_tool(argv, runner=subprocess.run):
    """Run a project tool as its own process; StepError with its output on failure."""
    result = runner(argv, capture_output=True, text=True, cwd=ROOT, creationflags=NO_WINDOW)
    if result.returncode != 0:
        output = (result.stdout or "") + (result.stderr or "")
        last = next((line for line in reversed(output.strip().splitlines()) if line.strip()), "")
        raise StepError(last or f"exit code {result.returncode}", output)
    return result.stdout


def download_installer(out_dir, runner=subprocess.run, python=None):
    """The one call of the project's fetcher: manifest entry 2.9.2 into a new, empty out_dir."""
    argv = [python or sys.executable, "-I", str(paths.entry("fetch")), str(MANIFEST), VERSION, str(out_dir)]
    return run_tool(argv, runner)


def new_download_dir(root=DOWNLOADS):
    """builds/<new empty folder> (the project rule: one new folder per download)."""
    stamp = time.strftime("%Y%m%d-%H%M%S")
    folder = Path(root) / f"v{VERSION}-installer-{stamp}"
    folder.mkdir(parents=True, exist_ok=False)
    return folder


# --- the steps ---------------------------------------------------------------------
class Step:
    key = ""
    title = ""

    def __init__(self, context):
        self.context = context

    def check(self, state):
        raise NotImplementedError

    def run(self, progress):
        raise NotImplementedError


class Context:
    """What the steps share: the settings, the folder state and the replaceable engine calls."""

    def __init__(self, settings, runner=subprocess.run, platform=sys.platform, downloads_root=DOWNLOADS,
                 wrapper_folders=None, python=None):
        self.settings, self.runner, self.platform = settings, runner, platform
        self.downloads_root, self.wrapper_folders, self.python = downloads_root, wrapper_folders, python
        self.state = None

    @property
    def folder(self):
        return self.settings.game_path()

    def refresh(self, skin_check=None):
        self.state = game_folder.examine(
            self.folder, skin_check or (lambda f: game_folder.skin_registered(f, self.platform)))
        return self.state


class GameFiles(Step):
    key, title = "files", "Game files"

    def check(self, state):
        entry = installer_entry()
        if state.exists:
            return Status("done", f"Found the game in {state.folder}.")
        installer = find_installer(self.context.downloads_root, entry)
        if installer:
            return Status("done", f"The 2.9.2 installer is downloaded ({installer.name}).")
        return Status("todo", "Choose the folder where your game is, or download the 2.9.2 installer "
                              f"({size_text(entry['bytes'])} from archive.org).")

    def run(self, progress):
        entry = installer_entry()
        progress(f"Downloading {size_text(entry['bytes'])} from archive.org…")
        out = new_download_dir(self.context.downloads_root)
        try:
            download_installer(out, self.context.runner, self.context.python)
        except StepError as error:
            raise StepError("The download did not finish. Check your internet connection and try again.",
                            error.details or str(error)) from None
        if find_installer(self.context.downloads_root, entry) is None:
            raise StepError("The downloaded file is not the expected installer. Try the download again.")
        progress("Downloaded and checked.")


class BuildFolder(Step):
    key, title = "folder", "Game folder"

    def check(self, state):
        if not state.exists:
            installer = find_installer(self.context.downloads_root)
            if installer is None:
                return Status("waiting", "Waiting for the game files.")
            return Status("todo", f"Unpack the game into {state.folder}.")
        if state.exe == "unknown":
            return Status("todo", "This game's program file is not the 2.9.2 version the project supports, or was "
                                  "changed by another tool. Choose another folder, or unpack a fresh copy.")
        if not state.assets_ok:
            return Status("todo", f"A game data file is missing or changed ({state.assets_problem}). "
                                  "Choose another folder, or unpack a fresh copy.")
        return Status("done", "Every game file is present and matches the 2.9.2 release.")

    def run(self, progress):
        folder = self.context.folder
        installer = find_installer(self.context.downloads_root)
        if installer is None:
            raise StepError("No downloaded installer was found. Do step 1 first.")
        if folder.exists():
            raise StepError(f"{folder} already exists, so it was not overwritten. Choose that folder in step 1, "
                            "or rename it and try again.")
        progress("Checking the installer…")
        if game_folder.sha_file(installer) != builds.INSTALLER_SHA256[VERSION]:
            raise StepError(f"{installer.name} is not the expected 2.9.2 installer. Delete it and download again.")
        progress(f"Unpacking into {folder}…")
        try:
            code = make_install.main([str(installer), str(folder)])
        except (OSError, ValueError) as error:
            raise StepError(f"Unpacking failed: {error}") from None
        if code:
            raise StepError("Unpacking failed. See the details.")
        shutil.copyfile(folder / game_folder.EXE, folder / (game_folder.EXE + ".orig"))
        progress("Checking the game files…")
        try:
            prepare.check_assets(folder)
        except (OSError, ValueError) as error:
            raise StepError(f"The unpacked files do not match the 2.9.2 release: {error}") from None


class Fixes(Step):
    key, title = "fixes", "Compatibility fixes"

    def check(self, state):
        if not state.exists or not state.assets_ok:
            return Status("waiting", "Waiting for the game folder.")
        if state.exe == "prepared":
            return Status("done", f"Applied: patch level {state.patch_level}.")
        if state.exe == "update":
            return Status("todo", f"Patch level {state.patch_level} is installed; update to {PATCH_LEVEL}. "
                                  "Your options are kept.")
        return Status("todo", f"Make the 2004 game run on Windows 10 and 11 (patch level {PATCH_LEVEL}). "
                              "Each change can be undone.")

    def run(self, progress):
        progress("Applying the fixes…")
        try:
            record = prepare.prepare(self.context.folder / game_folder.EXE)
        except (OSError, ValueError, RuntimeError) as error:
            raise StepError(f"The fixes could not be applied: {error}") from None
        progress(f"Applied: patch level {record['patch_version']}.")


class Skin(Step):
    key, title = "skin", "Login screen"
    SCRIPT = ROOT / "tools/register_activeskin.ps1"

    def check(self, state):
        if self.context.platform != "win32":
            return Status("unavailable", "Windows only: the login screen's skin is a Windows control.")
        if not state.exists:
            return Status("waiting", "Waiting for the game folder.")
        if state.skin:
            return Status("done", "The login screen's skin is registered for you.")
        return Status("todo", "Register the login screen's skin for your Windows user (no administrator "
                              "needed). Without it the login screen never opens.")

    def command(self):
        return ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(self.SCRIPT),
                str((self.context.folder / game_folder.OCX).resolve())]

    def run(self, progress):
        progress("Registering the login screen skin…")
        try:
            run_tool(self.command(), self.context.runner)
        except (OSError, StepError) as error:
            raise StepError("The skin could not be registered.", getattr(error, "details", "") or str(error)) \
                from None
        game_folder.record_skin(self.context.folder)


class Wrapper(Step):
    key, title = "wrapper", "Graphics wrapper (recommended)"

    def check(self, state):
        if not state.exists:
            return Status("waiting", "Waiting for the game folder.")
        if state.wrapper == "installed":
            return Status("done", "Installed: the game runs in a window and survives Alt+Tab.")
        if state.wrapper == "damaged":
            return Status("todo", f"The wrapper files do not match version 2.87.5 ({state.wrapper_problem}). "
                                  "Install it again.")
        if self.context.settings.skip_wrapper:
            return Status("skipped", "Skipped. " + WRAPPER_LOSS)
        return Status("optional", f"Download {WRAPPER_ZIP} from the dgVoodoo2 page, then choose "
                                  "\"I've downloaded it\". Leave the file as it is, unopened.")

    def page(self):
        return WRAPPER_PAGE

    def run(self, progress):
        progress("Looking in your Downloads folder…")
        found, wrong = game_folder.find_wrapper_zip(self.context.wrapper_folders)
        if found is None:
            if wrong:
                raise StepError(f"{wrong[0].name} is in Downloads but is not version 2.87.5. "
                                f"Download {WRAPPER_ZIP} from the page again.")
            folders = self.context.wrapper_folders or [game_folder.downloads_folder()]
            raise StepError(f"{WRAPPER_ZIP} is not in {folders[0]}. Download it from the page, then try again.")
        progress(f"Installing {found.name}…")
        try:
            install_wrapper.main([str(found), str(self.context.folder)])
        except SystemExit as stop:
            if stop.code:
                raise StepError(f"The wrapper could not be installed: {stop.code}") from None
        # Record the wrapper in the setup record; an option not named keeps its state.
        try:
            prepare.prepare(self.context.folder / game_folder.EXE)
        except (OSError, ValueError, RuntimeError) as error:
            raise StepError(f"The wrapper is installed, but the setup record was not updated: {error}") from None
        self.context.settings.skip_wrapper = False


STEPS = (GameFiles, BuildFolder, Fixes, Skin, Wrapper)


def checklist(context):
    """[(step, Status)] for the current folder state (call context.refresh() first)."""
    out = []
    for cls in STEPS:
        step = cls(context)
        out.append((step, step.check(context.state)))
    return out


def complete(rows):
    """Whether the checklist can be left: every step done, skipped, optional or unavailable."""
    return all(status.state in ("done", "skipped", "unavailable", "optional") for _, status in rows) and \
        rows[2][1].state == "done"


def open_page(url, opener=None):
    """Open a web page in the player's browser."""
    import webbrowser
    (opener or webbrowser.open)(url)
