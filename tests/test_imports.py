"""Every module under aoa/ imports on its own; game-free.

Each module is imported in a fresh `python -I` process with only the
repository on sys.path, so a cycle or a missing name shows up whatever order
other modules were loaded in. A module whose import needs an optional
package that is not installed (unicorn, capstone, pefile, Pillow), or
Windows, is skipped with the reason. Anything else that fails is a failure.

    python -I tools/test.py test_imports
"""
import importlib.util
import re
import subprocess
import sys
import unittest
from concurrent.futures import ThreadPoolExecutor

from aoa.paths import ROOT

MISSING = re.compile(r"ModuleNotFoundError: No module named '([\w.]+)'")
# What a Windows-only module raises when imported elsewhere.
WINDOWS = re.compile(r"windll|WinDLL|No module named '(winreg|msvcrt|_winapi|winsound)'")
LOCAL = ("aoa", "archive", "tests")


def modules():
    return [".".join(p.relative_to(ROOT).with_suffix("").parts).removesuffix(".__init__")
            for p in sorted((ROOT / "aoa").rglob("*.py"))]


def try_import(name):
    code = "import importlib, sys; sys.path[:0] = [sys.argv[1]]; importlib.import_module(sys.argv[2])"
    proc = subprocess.run([sys.executable, "-I", "-c", code, str(ROOT), name], cwd=ROOT,
                          capture_output=True, text=True, timeout=120, stdin=subprocess.DEVNULL)
    return proc.returncode, proc.stderr


def skip_reason(stderr):
    """Why a failed import is acceptable here, or None."""
    if sys.platform != "win32" and WINDOWS.search(stderr):
        return "Windows only"
    m = MISSING.search(stderr)
    if m:
        top = m[1].split(".")[0]
        if top not in LOCAL and importlib.util.find_spec(top) is None:
            return f"needs {top}, not installed"
    return None


class ImportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        names = modules()
        with ThreadPoolExecutor(8) as pool:
            cls.results = dict(zip(names, pool.map(try_import, names)))

    def check(self, name):
        code, stderr = self.results[name]
        if code == 0:
            return
        reason = skip_reason(stderr)
        if reason:
            self.skipTest(reason)
        self.fail(f"import {name} failed:\n{stderr[-2000:]}")

    def test_every_package_has_an_init(self):
        for folder in [ROOT / "aoa", *(p for p in (ROOT / "aoa").rglob("*") if p.is_dir()
                                       and p.name != "__pycache__")]:
            if any(folder.glob("*.py")):
                self.assertTrue((folder / "__init__.py").is_file(), f"{folder} has no __init__.py")


def _add_tests():
    for name in modules():
        setattr(ImportTests, "test_" + name.replace(".", "_"), lambda self, name=name: self.check(name))


_add_tests()

if __name__ == "__main__":
    unittest.main()
