"""Launcher persistence, reversible visuals, rollback and GUI wiring."""
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import client_launcher as launcher
import prepare_client as setup
import texture_pack

GAME = launcher.DEFAULT_GAME


class TextureToggleTests(unittest.TestCase):
    @unittest.skipUnless(sys.platform == "win32", "Windows process guard")
    def test_running_client_blocks_changes(self):
        from subprocess import CompletedProcess
        result = CompletedProcess([], 0, '"AOACLIENT.EXE","1234","Console","1","42 K"\n', "")
        with patch.object(launcher.subprocess, "run", return_value=result):
            with self.assertRaisesRegex(ValueError, "Close Ace of Angels"):
                launcher.require_closed()

    def test_pack_off_on_repeated_and_cache_tamper(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            originals = {name: (name + " original").encode() for name in texture_pack.ARCHIVES}
            digests = {name: setup.sha(data) for name, data in originals.items()}
            record = {"schema": 2, "archives": {}}
            for name, data in originals.items():
                packed = data + b" replacement skins"
                (folder / name).write_bytes(packed)
                (folder / (name + texture_pack.SUFFIX)).write_bytes(data)
                record["archives"][name] = {"original_sha256": digests[name], "sha256": setup.sha(packed)}
            (folder / texture_pack.RECORD).write_text(json.dumps(record))
            with patch.object(texture_pack, "pinned", side_effect=digests.__getitem__):
                for _ in range(2):
                    launcher.set_texture_pack(folder, False)
                    self.assertIsNone(texture_pack.verified(folder))
                    self.assertEqual(launcher.cached_pack(folder), record)
                    for name, data in originals.items():
                        self.assertEqual((folder / name).read_bytes(), data)
                    launcher.set_texture_pack(folder, True)
                    self.assertEqual(texture_pack.verified(folder), record)
                launcher.set_texture_pack(folder, False)
                (folder / ("DATA.AOA" + launcher.PACK_SUFFIX)).write_bytes(b"tampered")
                with self.assertRaisesRegex(ValueError, "was changed"):
                    launcher.set_texture_pack(folder, True)
                self.assertEqual((folder / "DATA.AOA").read_bytes(), originals["DATA.AOA"])


@unittest.skipUnless((GAME / "AOACLIENT.EXE.orig").exists(), "requires user's game files")
class LauncherTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        manifest = json.loads(setup.ASSET_MANIFEST.read_text())
        for name in (*manifest["required"], *manifest["mutable"], *setup.WRAPPERS, "dgVoodoo.conf"):
            shutil.copyfile(GAME / name, self.folder / name)
        shutil.copyfile(GAME / "AOACLIENT.EXE.orig", self.folder / "AOACLIENT.EXE")
        self.exe = self.folder / "AOACLIENT.EXE"
        self.closed = patch.object(launcher, "require_closed")
        self.closed.start()
        self.addCleanup(self.closed.stop)
        setup.prepare(self.exe, distant_objects=True)

    def test_visuals_on_off_individual_and_reopen(self):
        options, _ = launcher.read_settings(self.folder)
        for key in launcher.VISUAL_KEYS:
            options[key] = key not in ("texture_pack", "experimental_asteroids", "experimental_station_detail")
        options["station"] = "aoalan"
        launcher.apply_settings(self.folder, options)
        self.assertEqual(launcher.read_settings(self.folder)[0], options)
        enabled = self.exe.read_bytes()
        for key, _, module in launcher.PATCHES:
            if not options[key]:
                continue
            with self.subTest(key=key):
                toggled = {**options, key: False}
                launcher.apply_settings(self.folder, toggled)
                self.assertNotIn(module.NAME, setup.check(self.exe)["patches"])
                self.assertEqual(launcher.read_settings(self.folder)[0], toggled)
                launcher.apply_settings(self.folder, options)
                self.assertEqual(self.exe.read_bytes(), enabled)
        for key in launcher.VISUAL_KEYS:
            options[key] = False
        launcher.apply_settings(self.folder, options)
        self.assertEqual(launcher.read_settings(self.folder)[0], options)
        # The original visuals still pass the checked launch path, retaining
        # compatibility fixes and the independently chosen pickup behavior.
        state = setup.check(self.exe)
        self.assertIn("zero-time-physics-v1", state["patches"])
        self.assertIn(setup.powerup_pickup.NAME, state["patches"])
        self.assertNotIn(setup.own_ship_model.NAME, state["patches"])
        self.assertNotIn(setup.own_ship_menu.NAME, state["patches"])
        for key in ("experimental_asteroids", "experimental_station_detail"):
            options[key] = True
        launcher.apply_settings(self.folder, options)
        self.assertEqual(launcher.read_settings(self.folder)[0], options)
        with patch.object(launcher.subprocess, "Popen") as popen:
            launcher.launch(self.folder, options)
            popen.assert_called_once_with([str(self.exe)], cwd=self.folder)

    def test_invalid_choices_and_failed_write_preserve_files(self):
        options, _ = launcher.read_settings(self.folder)
        before = {p.name: p.read_bytes() for p in self.folder.iterdir() if p.is_file()}
        for changes in ({"experimental_solids": True, "experimental_asteroids": True},
                        {"experimental_world_detail": True, "experimental_station_detail": True},
                        {"texture_pack": True}, {"station": "host-name-too-long"}):
            with self.assertRaises(ValueError):
                launcher.apply_settings(self.folder, {**options, **changes})
        write = setup.atomic_write

        def fail_conf(path, data):
            if Path(path).name == "dgVoodoo.conf":
                raise PermissionError("simulated wrapper write failure")
            return write(path, data)

        options.update(chase_camera=False, antialiasing=not options["antialiasing"])
        with patch.object(setup, "atomic_write", side_effect=fail_conf), self.assertRaises(PermissionError):
            launcher.apply_settings(self.folder, options)
        self.assertEqual({p.name: p.read_bytes() for p in self.folder.iterdir() if p.is_file()}, before)

    def test_wrapper_unrelated_settings_and_custom_enabled_values_survive(self):
        path = self.folder / "dgVoodoo.conf"
        conf = path.read_bytes().decode("latin1")
        conf = launcher.install_wrapper.set_key(conf, "[DirectX]", "Antialiasing", "4x")
        path.write_bytes(conf.encode("latin1"))
        options, _ = launcher.read_settings(self.folder)
        self.assertTrue(options["antialiasing"])
        launcher.apply_settings(self.folder, options)
        self.assertEqual(path.read_bytes(), conf.encode("latin1"))
        options["antialiasing"] = False
        launcher.apply_settings(self.folder, options)
        expected = launcher.install_wrapper.set_key(conf, "[DirectX]", "Antialiasing", "appdriven")
        self.assertEqual(path.read_bytes(), expected.encode("latin1"))
        for name in setup.WRAPPERS:
            (self.folder / name).unlink()
        options, available = launcher.read_settings(self.folder)
        self.assertFalse(available["wrapper"])
        launcher.apply_settings(self.folder, options)

    @unittest.skipUnless(sys.platform == "win32", "Windows GUI smoke test")
    def test_gui_checkboxes_and_original_visuals_button(self):
        root, variables, checks = launcher.gui(self.folder, run=False)
        self.addCleanup(root.destroy)
        root.update_idletasks()
        for check in checks.values():
            self.assertLessEqual(check.winfo_rootx() + check.winfo_width(), root.winfo_rootx() + root.winfo_width())
            self.assertLessEqual(check.winfo_rooty() + check.winfo_height(), root.winfo_rooty() + root.winfo_height())
        root.withdraw()
        expected, _ = launcher.read_settings(self.folder)
        self.assertEqual({k: v.get() for k, v in variables.items()},
                         {k: expected[k] for k in variables})
        self.assertTrue(checks["texture_pack"].instate(["disabled"]))
        checks["experimental_solids"].invoke()
        checks["experimental_asteroids"].invoke()
        self.assertFalse(variables["experimental_solids"].get())
        self.assertTrue(variables["experimental_asteroids"].get())
        def widgets(parent):
            for child in parent.winfo_children():
                yield child
                yield from widgets(child)
        buttons = {w.cget("text"): w for w in widgets(root) if w.winfo_class() == "TButton"}
        buttons["Original visuals (all off)"].invoke()
        self.assertFalse(any(variables[k].get() for k in launcher.VISUAL_KEYS))
        self.assertTrue(variables["powerup_pickups"].get())
        self.assertFalse(buttons["Play"].instate(["disabled"]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
