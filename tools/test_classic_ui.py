"""Installer rejection and exact restore checks, without launching game code."""
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import classic_ui as ui


def pe_image():
    data = bytearray(1024)
    data[:2] = b"MZ"
    struct.pack_into("<I", data, 60, 128)
    data[128:132] = b"PE\0\0"
    struct.pack_into("<HH", data, 132, 0x14C, 1)
    struct.pack_into("<H", data, 148, 224)
    struct.pack_into("<H", data, 152, 0x10B)
    struct.pack_into("<IIII", data, 384, 512, 0x4B300, 512, 512)
    data[711:717] = bytes.fromhex("8b8e98010000")
    return data


class InstallTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.folder = self.root / "game"
        self.folder.mkdir()
        (self.folder / "classic-enhanced-shaders").mkdir()
        for name, data in {"AOACLIENT.EXE": pe_image(), "dxgi.dll": b"original runtime",
                           ui.RECORD: b'{"runtime_sha256":"old"}',
                           "ReShade.ini": b"[GENERAL]\nPresetPath=ClassicEnhanced.ini\n",
                           "classic-enhanced-shaders/AOAClassic.fx": b"original shader"}.items():
            (self.folder / name).write_bytes(data)
        self.original = {str(p.relative_to(self.folder)): p.read_bytes()
                         for p in self.folder.rglob("*") if p.is_file()}
        self.setup = self.root / "setup.exe"
        with zipfile.ZipFile(self.setup, "w") as archive:
            archive.writestr("ReShade32.dll", pe_image())
        self.addon = self.root / ui.ADDON
        self.addon.write_bytes(pe_image())
        self.addon.with_suffix(".json").write_text(json.dumps({
            "source_sha256": ui.digest(ui.SOURCE), "addon_sha256": ui.digest(self.addon),
            "haze_profiles_sha256": ui.digest(ui.HAZE_HEADER),
            "sdk_sha256": ui.SDK_SHA}))
        self.check_patch = patch.object(ui, "check", return_value={"runtime": "enabled"})
        self.check_patch.start()
        self.addCleanup(self.check_patch.stop)

    def install(self):
        with patch.object(ui, "SETUP_SHA", ui.digest(self.setup)):
            ui.install(self.folder, self.setup, self.addon)

    def test_install_restore_exact_bytes(self):
        self.install()
        self.assertTrue((self.folder / ui.ADDON).exists())
        self.assertEqual((self.folder / "AOACLIENT.EXE").read_bytes(), self.original["AOACLIENT.EXE"])
        ui.restore(self.folder)
        for name, expected in self.original.items():
            self.assertEqual((self.folder / name).read_bytes(), expected, name)
        self.assertFalse((self.folder / ui.ADDON).exists())

    def test_unrecognized_runtime_rejected_before_backup(self):
        with self.assertRaisesRegex(ValueError, "pinned hash"):
            ui.install(self.folder, self.setup, self.addon)
        self.assertFalse((self.folder / ui.BACKUP).exists())

    def test_unknown_native_hook_rejected_before_backup(self):
        data = bytearray((self.folder / "AOACLIENT.EXE").read_bytes())
        data[711] = 0xE9
        (self.folder / "AOACLIENT.EXE").write_bytes(data)
        with self.assertRaisesRegex(ValueError, "HUD boundary"):
            self.install()
        self.assertFalse((self.folder / ui.BACKUP).exists())

    def test_changed_addon_rejected(self):
        self.addon.write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "stale or changed"):
            self.install()
        self.assertFalse((self.folder / ui.BACKUP).exists())

    def test_stale_haze_table_rejected(self):
        path = self.addon.with_suffix(".json")
        manifest = json.loads(path.read_text())
        manifest["haze_profiles_sha256"] = "old table"
        path.write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ValueError, "stale or changed"):
            self.install()
        self.assertFalse((self.folder / ui.BACKUP).exists())


if __name__ == "__main__":
    unittest.main()
