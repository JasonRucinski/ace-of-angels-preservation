"""install_wrapper and make_install on small stand-in archives; game-free."""
import contextlib
import hashlib
import io
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import install_wrapper  # noqa: E402
import make_install  # noqa: E402

CONF = ("Version = 0x287\r\n\r\n[General]\r\nFullScreenMode = true\r\nCenterAppWindow = false\r\n\r\n"
        "[DirectX]\r\nAntialiasing = appdriven\r\nFiltering = appdriven\r\ndgVoodooWatermark = true\r\n"
        "DisableAltEnterToToggleScreenMode = true\r\n")


class InstallWrapperTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.zip = self.root / "dgVoodoo2_87_5.zip"
        with zipfile.ZipFile(self.zip, "w") as z:
            z.writestr("MS/x86/DDraw.dll", b"ddraw")
            z.writestr("MS/x86/D3DImm.dll", b"d3dimm")
            z.writestr("dgVoodoo.conf", CONF)
        self.game = self.root / "game"
        self.game.mkdir()
        (self.game / "AOACLIENT.EXE").write_bytes(b"client")
        digest = hashlib.sha256(self.zip.read_bytes()).hexdigest()
        mocked = patch.object(install_wrapper, "ZIP_SHA256", digest)
        mocked.start()
        self.addCleanup(mocked.stop)

    def run_main(self, *argv):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            install_wrapper.main([str(a) for a in argv])

    def test_fresh_install_and_kept_directx_choices(self):
        self.run_main(self.zip, self.game)
        conf = (self.game / "dgVoodoo.conf").read_bytes().decode("latin1")
        self.assertIn("FullScreenMode = false\r\n", conf)
        self.assertIn("dgVoodooWatermark = false\r\n", conf)
        self.assertEqual((self.game / "DDraw.dll").read_bytes(), b"ddraw")
        self.assertIn(b"dpiAware", (self.game / "AOACLIENT.EXE.manifest").read_bytes())
        # The launcher's quality choices survive a reinstall; the tool's own keys are reapplied.
        chosen = install_wrapper.set_key(conf, "[DirectX]", "Antialiasing", "8x")
        chosen = install_wrapper.set_key(chosen, "[DirectX]", "dgVoodooWatermark", "true")
        (self.game / "dgVoodoo.conf").write_bytes(chosen.encode("latin1"))
        self.run_main(self.zip, self.game)
        conf = (self.game / "dgVoodoo.conf").read_bytes().decode("latin1")
        self.assertIn("Antialiasing = 8x\r\n", conf)
        self.assertIn("Filtering = appdriven\r\n", conf)
        self.assertIn("dgVoodooWatermark = false\r\n", conf)
        self.assertEqual(sorted(p.name for p in self.game.iterdir()),
                         ["AOACLIENT.EXE", "AOACLIENT.EXE.manifest", "D3DImm.dll", "DDraw.dll", "dgVoodoo.conf"])

    def test_refusals_change_nothing(self):
        with patch.object(install_wrapper, "ZIP_SHA256", "0" * 64), self.assertRaises(SystemExit) as stopped:
            self.run_main(self.zip, self.game)
        self.assertIn("no files changed", str(stopped.exception.code))
        (self.game / "AOACLIENT.EXE").unlink()
        with self.assertRaises(SystemExit) as stopped:
            self.run_main(self.zip, self.game)
        self.assertIn("has no AOACLIENT.EXE", str(stopped.exception.code))
        self.assertEqual(list(self.game.iterdir()), [])
        with self.assertRaises(SystemExit) as stopped:
            self.run_main()
        self.assertEqual(stopped.exception.code, 2)


class MakeInstallTests(unittest.TestCase):
    def test_extracts_payload_and_parses_arguments(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            installer = root / "setup.exe"
            with zipfile.ZipFile(installer, "w") as z:
                z.writestr("MAINDIR/aoaclient.exe", b"client")
                z.writestr("WISE0001.DLL", b"installer")
            out = root / "game"
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(make_install.main([str(installer), str(out)]), 0)
                self.assertEqual(make_install.main([str(installer), str(out)]), 1)
                self.assertEqual(make_install.main([str(root / "missing.exe"), str(root / "other")]), 1)
                with self.assertRaises(SystemExit) as stopped:
                    make_install.main([])
            self.assertEqual(stopped.exception.code, 2)
            self.assertEqual((out / "AOACLIENT.EXE").read_bytes(), b"client")
            record = json.loads((out / "_install_manifest.json").read_text())
            self.assertEqual(record["skipped_installer_members"], ["WISE0001.DLL"])
            self.assertFalse((root / "other").exists())


if __name__ == "__main__":
    unittest.main()
