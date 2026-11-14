"""Every tool answers --help with usage and nothing else.

For each script under tools/ (and tools/reel/) that has a __main__ block, this
runs `python -I -B <script> --help` against a throw-away copy of the
repository, from an empty working directory, with sockets and child processes
blocked inside the interpreter. It asserts exit code 0, argparse usage on
stdout, no network or process attempt, and no file created or changed in the
copy or the working directory. No script is ever run against this checkout.

A script whose import needs an optional package that is not installed (for
example Pillow, or a Windows-only module on Linux) is skipped with the
package's name. Scripts owned by other restructure tasks that still act on
--help are listed in KNOWN_UNSAFE with their finding ID and are not run.

    python -I tools/test_cli_help.py
    python -I tools/test_cli_help.py -k fetch_known_builds
"""
import importlib.util
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
ROOT = TOOLS.parent
# What the copy holds: everything tracked that a tool might read, never the
# ignored game/, builds/, work/, wb/ or originals/ folders.
COPY_DIRS = ["tools", "config", "data", "evidence", "manifest", "docs", "deploy"]
COPY_FILES = ["CONTEXT.md", "README.md", "CLAUDE.md", "CONTRIBUTING.md", "requirements.txt"]
TIMEOUT = 60

# Scripts outside this task's files that still act on --help, by finding ID
# (docs/restructure/audits/). Remove an entry when its script is fixed.
KNOWN_UNSAFE = {}

MAIN = re.compile(r"""^if __name__ == ['"]__main__['"]""", re.M)
MISSING = re.compile(r"ModuleNotFoundError: No module named '([\w.]+)'")
ATTEMPT = "CLI-HELP-SANDBOX-ATTEMPT"

# Runs inside the child interpreter before the script: any socket connect,
# bind, name lookup or child process prints a marker and raises.
GUARD = r'''
import os, runpy, socket, subprocess, sys
def _blocked(what):
    def refuse(*args, **kwargs):
        sys.stderr.write("%s %s\n" % (MARKER, what))
        sys.stderr.flush()
        raise PermissionError("blocked during --help: " + what)
    return refuse
for name in ("connect", "connect_ex", "bind", "sendto", "sendmsg"):
    setattr(socket.socket, name, _blocked("socket." + name))
for name in ("create_connection", "getaddrinfo", "gethostbyname", "gethostbyname_ex"):
    setattr(socket, name, _blocked("socket." + name))
subprocess.Popen._execute_child = _blocked("subprocess")
for name in ("system", "startfile", "posix_spawn", "posix_spawnp", "spawnv", "spawnve",
             "spawnl", "spawnle", "execv", "execve", "execl", "execle", "execvp", "execlp"):
    if hasattr(os, name):
        setattr(os, name, _blocked("os." + name))
script = sys.argv[1]
sys.argv = [script] + sys.argv[2:]
runpy.run_path(script, run_name="__main__")
'''.replace("MARKER", repr(ATTEMPT))


def entry_points():
    """Paths, relative to the repo, of the scripts that have a __main__ block."""
    found = []
    for path in sorted(TOOLS.glob("*.py")) + sorted((TOOLS / "reel").glob("*.py")):
        if path.name.startswith("test_"):
            continue
        if MAIN.search(path.read_text(encoding="utf-8", errors="replace")):
            found.append(path.relative_to(ROOT).as_posix())
    return found


def snapshot(*folders):
    """Every file under the folders, with its size and modification time."""
    seen = {}
    for folder in folders:
        for base, dirs, files in os.walk(folder):
            for name in dirs + files:
                path = os.path.join(base, name)
                info = os.lstat(path)
                seen[path] = (info.st_size, info.st_mtime_ns)
    return seen


def missing_optional(stderr):
    """The optional package a failed import needed, if it is simply not installed."""
    m = MISSING.search(stderr)
    if not m:
        return None
    top = m[1].split(".")[0]
    if (TOOLS / f"{top}.py").exists() or (TOOLS / "reel" / f"{top}.py").exists():
        return None
    return top if importlib.util.find_spec(top) is None else None


class CliHelp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix="aoa-cli-help-")
        base = Path(cls.tmp.name)
        cls.repo = base / "repo"
        cls.cwd = base / "cwd"
        cls.cwd.mkdir()
        ignore = shutil.ignore_patterns("__pycache__", "*.pyc")
        for name in COPY_DIRS:
            if (ROOT / name).is_dir():
                shutil.copytree(ROOT / name, cls.repo / name, ignore=ignore)
        for name in COPY_FILES:
            if (ROOT / name).is_file():
                shutil.copy2(ROOT / name, cls.repo / name)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def sandboxed(self, rel, *args):
        """Run a copy of tools/<rel> with args in the sandbox; assert it stayed inside."""
        script = self.repo / rel
        # The interpreter's own environment only; no proxy, so even an
        # unguarded connection attempt would go nowhere useful.
        env = {k: v for k, v in os.environ.items()
               if not k.lower().endswith("_proxy") and not k.startswith("PYTHON")}
        before = snapshot(self.repo, self.cwd)
        try:
            proc = subprocess.run(
                [sys.executable, "-I", "-B", "-c", GUARD, str(script), *args],
                cwd=self.cwd, env=env, stdin=subprocess.DEVNULL,
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                timeout=TIMEOUT)
        except subprocess.TimeoutExpired:
            self.fail(f"{rel} {' '.join(args)} did not finish within {TIMEOUT} s")
        after = snapshot(self.repo, self.cwd)
        changed = sorted(os.path.relpath(p, self.tmp.name)
                         for p in set(before) | set(after) if before.get(p) != after.get(p))
        self.assertNotIn(ATTEMPT, proc.stderr, f"{rel} {args} tried the network or a process:\n{proc.stderr}")
        self.assertEqual(changed, [], f"{rel} {args} created or changed files")
        return proc

    def check(self, rel):
        if rel in KNOWN_UNSAFE:
            self.skipTest(f"known unsafe on --help ({KNOWN_UNSAFE[rel]}); not run")
        proc = self.sandboxed(rel, "--help")
        if proc.returncode != 0:
            package = missing_optional(proc.stderr)
            if package:
                self.skipTest(f"needs {package}, not installed")
        self.assertEqual(proc.returncode, 0, f"{rel} --help exited {proc.returncode}:\n{proc.stderr[-2000:]}")
        self.assertIn("usage:", proc.stdout.lower(), f"{rel} --help printed no usage:\n{proc.stdout[:500]}")

    def one_line_failure(self, proc, what):
        self.assertNotEqual(proc.returncode, 0, f"{what} exited 0")
        self.assertNotIn("Traceback", proc.stderr, f"{what} ended in a traceback:\n{proc.stderr}")
        self.assertEqual(len(proc.stderr.strip().splitlines()), 1, f"{what}:\n{proc.stderr}")

    def test_output_folder_named_like_an_option_is_refused(self):
        # R1/R2: these used to download or query archive.org into "./--help".
        for rel in ("tools/fetch_known_builds.py", "tools/ia_fulltext_search.py"):
            proc = self.sandboxed(rel, "--", "-x")
            self.assertEqual(proc.returncode, 2, f"{rel}:\n{proc.stderr}")
            self.assertIn("refusing output folder", proc.stderr)

    def test_missing_output_folder_stops_before_querying(self):
        proc = self.sandboxed("tools/ia_fulltext_search.py", "no-such-folder")
        self.one_line_failure(proc, "ia_fulltext_search with a missing folder")

    def test_missing_input_is_one_line(self):
        for rel, args in (("tools/decode_trn.py", ["missing.trn"]),
                          ("tools/wise_extract.py", ["missing.exe"]),
                          ("tools/aoa_version.py", ["missing.exe"]),
                          ("tools/export_assets.py", ["missing", "out"])):
            self.one_line_failure(self.sandboxed(rel, *args), f"{rel} {args}")

    def test_lod_audit_fails_without_export(self):
        # R3: it wrote {"mesh_models": 0} and exited 0.
        proc = self.sandboxed("tools/audit_object_lod.py", "report.json")
        self.one_line_failure(proc, "audit_object_lod without an export folder")

    def test_known_unsafe_entries_exist(self):
        scripts = set(entry_points())
        for rel in KNOWN_UNSAFE:
            self.assertIn(rel, scripts, f"KNOWN_UNSAFE names {rel}, which is not an entry point")


class ToolBehaviour(unittest.TestCase):
    """In-process checks of the command-line fixes (no network, temp files only)."""

    def setUp(self):
        sys.path.insert(0, str(TOOLS))
        self.addCleanup(sys.path.remove, str(TOOLS))
        tmp = tempfile.TemporaryDirectory(prefix="aoa-cli-behaviour-")
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)

    def fake_installer(self, data, crc):
        """A Wise-style blob: junk, then one PK local header with a raw-deflate member."""
        import struct
        import zlib
        packer = zlib.compressobj(9, zlib.DEFLATED, -15)
        packed = packer.compress(data) + packer.flush()
        name = b"GAME\\AOANOTES.TXT"
        header = b"PK\x03\x04" + struct.pack("<HHHHHIIIHH", 20, 0, 8, 0, 0, crc, len(packed),
                                             len(data), len(name), 0)
        path = self.tmp / "installer.exe"
        path.write_bytes(b"MZ" + bytes(64) + header + name + packed + bytes(16))
        return path

    def test_wise_extract_refuses_bad_crc(self):
        # R19: a mismatch used to print a warning and write the file anyway.
        import contextlib
        import io
        import wise_extract
        import zlib
        data = b"Ace of Angels notes\r\n" * 20
        installer = self.fake_installer(data, zlib.crc32(data) ^ 1)
        out = self.tmp / "out"
        with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(SystemExit) as caught:
            wise_extract.main([str(installer), str(out)])
        self.assertIn("CRC", str(caught.exception.code))
        self.assertEqual(list(out.iterdir()), [])
        with contextlib.redirect_stdout(io.StringIO()):
            wise_extract.main([str(installer), str(out), "--force"])
        self.assertEqual((out / "AOANOTES.TXT").read_bytes(), data)

    def test_wise_extract_good_crc(self):
        import contextlib
        import io
        import wise_extract
        import zlib
        data = b"intact member" * 10
        out = self.tmp / "out"
        with contextlib.redirect_stdout(io.StringIO()):
            wise_extract.main([str(self.fake_installer(data, zlib.crc32(data))), str(out)])
        self.assertEqual((out / "AOANOTES.TXT").read_bytes(), data)

    def test_inventory_without_appendix_c(self):
        # R20: any version without an Appendix C crashed with AttributeError.
        import contextlib
        import io
        import json
        import zipfile
        import inventory
        installer = self.tmp / "setup.exe"
        with zipfile.ZipFile(installer, "w") as zf:
            zf.writestr("AOANOTES.TXT", b"notes")
        handoff = self.tmp / "handoff.txt"
        handoff.write_text("no appendix here\n", encoding="utf-8")
        for args in ([str(installer), "2.8.0", str(self.tmp / "a")],
                     [str(installer), "2.8.0", str(handoff), str(self.tmp / "b")]):
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(inventory.main(args), 0)
            result = json.loads((Path(args[-1]) / "inventory.json").read_text(encoding="utf-8"))
            self.assertEqual(result["member_count"], 1)
            self.assertIsNone(result["appendix_c_member_count"])
            self.assertIsNone(result["appendix_c_exact_match_in_order"])

    def test_audits_default_to_work(self):
        # R8: audits wrote committed evidence/ on every run.
        import cli_util
        committed = "evidence/2.9.2/example.json"
        self.assertEqual(cli_util.evidence_target(self.tmp / "x" / "e.json", committed), self.tmp / "x" / "e.json")
        default = cli_util.WORK / committed
        self.assertEqual(default.relative_to(cli_util.ROOT).parts[0], "work")


def _add_tests():
    for rel in entry_points():
        name = "test_" + re.sub(r"\W", "_", rel.removeprefix("tools/").removesuffix(".py"))
        setattr(CliHelp, name, lambda self, rel=rel: self.check(rel))


_add_tests()

if __name__ == "__main__":
    unittest.main()
