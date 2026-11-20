"""prepare's composition, options, transaction and command line.

SyntheticClientTests run on the synthetic client of tests/support_patches.py
(game-free, in CI); ClientPreparationTests run on temporary copies of the
user's original client and skip without it.
"""
import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from aoa.client import prepare as setup
from aoa.client.patches import archive_terminator
from aoa.client.patches import background_network
from aoa.client.patches import base as patching
from aoa.client.patches import explicit_protection
from aoa.client.patches import logger
from aoa.client.patches import physics_timestep
from tests import support_patches
from tests.support_patches import ORIGINAL as SOURCE, needs_game


@needs_game
class ClientPreparationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original = SOURCE.read_bytes()
        assert hashlib.sha256(cls.original).hexdigest() == logger.PRISTINE_292
        cls.stable = logger.stabilize(cls.original)

    def test_composed_patches_and_host_changes(self):
        self.assertEqual(setup.sha(self.stable), logger.STABLE_SHA256)
        for source in (self.original, self.stable, patching.apply(physics_timestep.PATCH, self.stable, True)):
            prepared = setup.configure(source)
            self.assertEqual(setup.configure(prepared), prepared)
            changed = setup.configure(prepared, "10.0.0.1")
            self.assertEqual(setup.inspect(changed)["host"], "10.0.0.1")
            self.assertIn("zero-time-physics-v1", setup.inspect(changed)["patches"])
            self.assertIn("background-network-v1", setup.inspect(changed)["patches"])
            self.assertIn("archive-terminator-v1", setup.inspect(changed)["patches"])
            self.assertIn("ship-menu-aspect-v1", setup.inspect(changed)["patches"])
            self.assertEqual(patching.state(background_network.PATCH, prepared), background_network.NAME)
            self.assertEqual(setup.configure(changed), prepared)
        # A version-1 setup (no background patch) upgrades in place.
        version1 = patching.apply(archive_terminator.PATCH, patching.apply(
            background_network.PATCH, setup.configure(self.stable, "127.0.0.1"), False), False)
        self.assertNotIn("background-network-v1", setup.inspect(version1)["patches"])
        self.assertEqual(setup.configure(version1, "127.0.0.1"), setup.configure(self.stable, "127.0.0.1"))

    def test_explicit_protection_opt_in_and_exact_undo(self):
        normal = setup.configure(self.original)
        self.assertFalse(patching.state(explicit_protection.PATCH, normal))
        experimental = setup.configure(normal, experimental_protection=True)
        self.assertIn(explicit_protection.NAME, setup.inspect(experimental)["patches"])
        self.assertEqual(setup.configure(experimental), experimental)
        self.assertTrue(patching.state(explicit_protection.PATCH, setup.configure(experimental, "127.0.0.1")))
        self.assertEqual(setup.configure(experimental, experimental_protection=False), normal)
        with self.assertRaisesRegex(ValueError, "loopback"):
            setup.configure(experimental, "10.0.0.1")
        for offset in (explicit_protection.SITE - 0x400000, explicit_protection.CAVE - 0x400000):
            corrupt = bytearray(experimental)
            corrupt[offset] ^= 1
            with self.assertRaises(ValueError):
                setup.configure(corrupt)
        with tempfile.TemporaryDirectory() as tmp:
            exe = Path(tmp) / "AOACLIENT.EXE"
            exe.write_bytes(self.original)
            record = setup.prepare(exe, {"experimental_protection": True})
            self.assertEqual(record["patch_version"], 22)
            self.assertIn(explicit_protection.NAME, setup.check(exe, require_assets=False)["patches"])
            setup.prepare(exe, {"experimental_protection": False})
            self.assertEqual(exe.read_bytes(), normal)
            setup.undo(exe)
            self.assertEqual(exe.read_bytes(), self.original)

    def test_pinned_original_assets_and_corruption(self):
        self.assertEqual(setup.check_assets(SOURCE.parent), 11)
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / "ACTIVESKIN.OCX").write_bytes(b"changed")
            with self.assertRaisesRegex(ValueError, "modified or incompatible"):
                setup.check_assets(folder)

    def test_exact_undo_and_recorded_launch_check(self):
        for source in (self.original, self.stable, setup.configure(self.stable, "127.0.0.1")):
            with tempfile.TemporaryDirectory() as tmp:
                exe = Path(tmp) / "AOACLIENT.EXE"
                exe.write_bytes(source)
                first = setup.prepare(exe)
                self.assertEqual(first["status"], "ready")
                setup.check(exe, require_assets=False)
                setup.prepare(exe, station="10.0.0.1")
                self.assertEqual(setup.check(exe, require_assets=False)["host"], "10.0.0.1")
                setup.undo(exe)
                self.assertEqual(exe.read_bytes(), source)
                with self.assertRaises(ValueError):
                    setup.check(exe, require_assets=False)
                setup.prepare(exe)
                setup.undo(exe)
                self.assertEqual(exe.read_bytes(), source)

    def test_unknown_inputs_and_wrapper_conflicts_fail_before_mutation(self):
        for offset in (0, 0x1000, 0x8AE71, 0x18B400, 0x46EAF, 0x12A6E3, 0x18B448):
            corrupt = bytearray(setup.configure(self.stable))
            corrupt[offset] ^= 1
            with self.assertRaises(ValueError):
                setup.configure(corrupt)
        for host in ("", "a" * 12, "https://x", "x/y", "x..y", "-x", "x-", "☃", "999.1.1.1"):
            with self.assertRaises(ValueError):
                setup.configure(self.original, host)
        with tempfile.TemporaryDirectory() as tmp:
            exe = Path(tmp) / "AOACLIENT.EXE"
            exe.write_bytes(self.original)
            (exe.parent / "DDraw.dll").write_bytes(b"unknown wrapper")
            with self.assertRaises(ValueError):
                setup.prepare(exe)
            self.assertEqual(exe.read_bytes(), self.original)
            self.assertFalse((exe.parent / "_client_setup.json").exists())

    def test_drift_backup_corruption_and_missing_assets(self):
        with tempfile.TemporaryDirectory() as tmp:
            exe = Path(tmp) / "AOACLIENT.EXE"
            exe.write_bytes(self.original)
            setup.prepare(exe)
            with self.assertRaisesRegex(ValueError, "missing game dependency"):
                setup.check(exe)
            ready = exe.read_bytes()
            exe.write_bytes(setup.configure(ready, "10.0.0.1"))
            with self.assertRaisesRegex(ValueError, "outside the recorded setup"):
                setup.prepare(exe)
            exe.write_bytes(ready)
            backup = exe.with_name(exe.name + ".setup-original")
            backup.write_bytes(b"corrupt backup")
            with self.assertRaisesRegex(ValueError, "backup is invalid"):
                setup.undo(exe)
            self.assertEqual(exe.read_bytes(), ready)

    def test_interrupted_replace_is_recoverable(self):
        with tempfile.TemporaryDirectory() as tmp:
            exe = Path(tmp) / "AOACLIENT.EXE"
            exe.write_bytes(self.original)
            replace = setup.os.replace

            def fail_executable(source, target):
                if Path(target) == exe:
                    raise PermissionError("simulated running executable")
                replace(source, target)

            with patch.object(setup.os, "replace", fail_executable), self.assertRaises(PermissionError):
                setup.prepare(exe)
            self.assertEqual(exe.read_bytes(), self.original)
            self.assertEqual(json.loads((exe.parent / "_client_setup.json").read_text())["status"], "pending")
            self.assertEqual(list(exe.parent.glob("*.tmp")), [])
            setup.prepare(exe)
            self.assertEqual(setup.check(exe, require_assets=False)["status"], "ready")
            setup.undo(exe)
            self.assertEqual(exe.read_bytes(), self.original)

    def test_undo_does_not_require_a_working_wrapper(self):
        with tempfile.TemporaryDirectory() as tmp:
            exe = Path(tmp) / "AOACLIENT.EXE"
            exe.write_bytes(self.original)
            setup.prepare(exe)
            (exe.parent / "DDraw.dll").write_bytes(b"unrecognized wrapper added later")
            with self.assertRaises(ValueError):
                setup.check(exe, require_assets=False)
            setup.undo(exe)
            self.assertEqual(exe.read_bytes(), self.original)


class SyntheticClientTests(unittest.TestCase):
    """Option handling on the synthetic client of tests/support_patches.py; game-free."""
    FORCED = {"smooth_frame_clock": "frame-clock-v1", "bounded_visibility": "visibility-math-v1",
              "chase_camera": "third-person-camera-v3", "powerup_pickups": "powerup-pickup-v1",
              "menu_framing": "ship-menu-aspect-v1"}

    @classmethod
    def setUpClass(cls):
        cls.pristine = support_patches.synthetic_pristine()

    def setUp(self):
        self.enterContext(support_patches.synthetic_client(self.pristine))
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.exe = Path(temp.name) / "AOACLIENT.EXE"
        self.exe.write_bytes(self.pristine)

    def installed(self):
        return setup.check(self.exe, require_assets=False)

    def test_unnamed_options_keep_their_installed_state(self):
        fresh = setup.prepare(self.exe)
        self.assertEqual(fresh["host"], "localhost")
        self.assertLessEqual(set(self.FORCED.values()), set(fresh["patches"]))
        for key, name in self.FORCED.items():
            with self.subTest(option=key):
                setup.prepare(self.exe, {key: False})
                # What play.md tells LAN players to run: only the Station is named.
                state = setup.prepare(self.exe, {"experimental_protection": False}, station="aoalan")
                self.assertEqual(state["host"], "aoalan")
                self.assertNotIn(name, state["patches"])
                setup.prepare(self.exe, {key: True})
                self.assertIn(name, setup.prepare(self.exe, station="localhost")["patches"])
        setup.prepare(self.exe, {"distant_objects": True, "experimental_texture32": True,
                                 **dict.fromkeys(self.FORCED, False)})
        before = self.exe.read_bytes()
        setup.prepare(self.exe)
        self.assertEqual(self.exe.read_bytes(), before)
        self.assertEqual(self.installed()["host"], "localhost")
        state = setup.prepare(self.exe, station="10.0.0.1")
        self.assertFalse(set(self.FORCED.values()) & set(state["patches"]))
        self.assertIn("distant-world-objects-v1", state["patches"])
        self.assertIn("texture-argb8888-v1", state["patches"])
        setup.undo(self.exe)
        self.assertEqual(self.exe.read_bytes(), self.pristine)
        self.assertLessEqual(set(self.FORCED.values()), set(setup.prepare(self.exe)["patches"]))

    def test_conflicting_pairs(self):
        pairs = (("experimental_asteroids", "asteroid-mesh-distance-v1",
                  "experimental_solids", "solid-world-mesh-distance-v1"),
                 ("experimental_station_detail", "station-full-detail-v1",
                  "experimental_world_detail", "world-full-detail-v1"))
        for first, first_name, second, second_name in pairs:
            with self.subTest(pair=(first, second)):
                prepared = setup.configure(self.pristine)
                with self.assertRaisesRegex(ValueError, f"{first_name} and {second_name}"):
                    setup.configure(prepared, **{first: True, second: True})
                # An explicit request replaces the installed alternative, either way round.
                one = setup.configure(prepared, **{first: True})
                other = setup.configure(one, **{second: True})
                self.assertNotIn(first_name, setup.inspect(other)["patches"])
                self.assertIn(second_name, setup.inspect(other)["patches"])
                self.assertEqual(setup.configure(other, **{first: True}), one)
                self.assertEqual(setup.configure(one, **{first: False}), prepared)

    def test_engine_does_not_strip_a_conflicting_patch(self):
        # The engine applies one patch at a time; only prepare resolves conflicts (C13).
        from aoa.client.patches import BY_ID
        for name, sibling in (("solid-world-mesh-distance-v1", "asteroid-mesh-distance-v1"),
                              ("world-full-detail-v1", "station-full-detail-v1")):
            with self.subTest(patch=name):
                with_sibling = patching.apply(BY_ID[sibling], self.pristine, True)
                for on in (True, False):
                    with self.assertRaises(ValueError):
                        patching.apply(BY_ID[name], with_sibling, on)
                alone = patching.apply(BY_ID[name], self.pristine, True)
                self.assertEqual(patching.apply(BY_ID[name], alone, False), self.pristine)

    def test_one_option_changes_only_that_option(self):
        # What the removed per-tool installers did, through prepare (C2, C3).
        setup.prepare(self.exe, {"chase_camera": False, "menu_framing": False}, station="aoalan")
        kept = set(setup.prepare(self.exe)["patches"])
        for option in ("experimental_asteroids", "experimental_solids", "experimental_station_detail",
                       "experimental_world_detail", "experimental_texture32", "distant_objects"):
            name = setup.OPTIONS[option].id
            with self.subTest(option=option):
                record = setup.prepare(self.exe, {option: True})
                self.assertEqual(record["status"], "ready")
                self.assertEqual(set(self.installed()["patches"]), kept | {name})
                setup.prepare(self.exe, {option: False})
                self.assertEqual(set(self.installed()["patches"]), kept)
                self.assertEqual(self.installed()["host"], "aoalan")
                self.assertEqual(sorted(p.name for p in self.exe.parent.iterdir()),
                                 ["AOACLIENT.EXE", "AOACLIENT.EXE.setup-original", "_client_setup.json"])

    def test_options_and_requirements_come_from_the_registry(self):
        with self.assertRaisesRegex(ValueError, "unknown option: chase"):
            setup.configure(self.pristine, chase=True)
        record = setup.prepare(self.exe)
        self.assertEqual(record["patch_version"], 22)
        self.assertLessEqual(setup.REQUIRED, set(record["patches"]))
        # The chase-camera trio is one option.
        state = setup.prepare(self.exe, {"chase_camera": False})["patches"]
        self.assertFalse({"third-person-camera-v3", "own-ship-model-v1", "own-ship-menu-model-v1"} & set(state))
        # An old per-tool backup is reported by check, never used.
        (self.exe.parent / "AOACLIENT.EXE.before-texture32").write_bytes(b"old")
        self.assertEqual(self.installed()["unused_old_backups"], ["AOACLIENT.EXE.before-texture32"])

    def test_older_camera_variants_are_named_and_fail_check(self):
        from aoa.client.patches import own_ship_menu
        from aoa.client.patches import third_person
        setup.prepare(self.exe)
        on = self.exe.read_bytes()
        setup.prepare(self.exe, {"chase_camera": False})
        off = self.exe.read_bytes()
        for module, name in ((third_person, "third-person-camera-v1"), (third_person, "third-person-camera-v2"),
                             (own_ship_menu, "own-ship-menu-model-legacy")):
            with self.subTest(variant=name):
                # third_person's own cave is off here; own_ship_menu needs the camera on.
                old = bytearray(off if module is third_person else patching.apply(own_ship_menu.PATCH, on, False))
                for r in dict(module.PATCH.legacy)[name]:
                    old[r.va - 0x400000:r.end - 0x400000] = r.new
                old = bytes(old)
                self.assertIn(name, setup.inspect(old)["patches"])
                self.assertNotIn(module.NAME, setup.inspect(old)["patches"])
                # As an earlier prepare would have recorded it.
                record_path = self.exe.with_name("_client_setup.json")
                record = json.loads(record_path.read_text())
                self.exe.write_bytes(old)
                record_path.write_text(json.dumps({**record, "output_sha256": setup.sha(old)}))
                with self.assertRaisesRegex(ValueError, f"outdated client patches \\({name}\\); re-run prepare"):
                    self.installed()
                # An unnamed option keeps the old variant on, and prepare upgrades it.
                state = setup.prepare(self.exe)
                self.assertIn(module.NAME, state["patches"])
                self.assertNotIn(name, state["patches"])
                setup.prepare(self.exe, {"chase_camera": False})
                self.assertEqual(self.exe.read_bytes(), off)

    def test_command_line(self):
        for argv in (["check", str(self.exe), "--station", "aoalan"],
                     ["undo", str(self.exe), "--no-third-person"],
                     ["launch", str(self.exe), "--frame-clock"]):
            with self.subTest(argv=argv), patch("sys.stderr", io.StringIO()) as stderr, \
                    self.assertRaises(SystemExit) as stopped:
                setup.main(argv)
            self.assertEqual(stopped.exception.code, 2)
            self.assertIn("unrecognized arguments", stderr.getvalue())
        with patch("sys.stdout", io.StringIO()):
            setup.main(["prepare", str(self.exe), "--no-third-person"])
            setup.main(["prepare", str(self.exe), "--station", "aoalan"])
        self.assertNotIn("third-person-camera-v3", self.installed()["patches"])
        self.assertEqual(self.installed()["host"], "aoalan")
        # Generated flags and today's names select the same option.
        with patch("sys.stdout", io.StringIO()):
            setup.main(["prepare", str(self.exe), "--chase-camera", "--experimental-texture32"])
        self.assertIn("third-person-camera-v3", self.installed()["patches"])
        self.assertIn("texture-argb8888-v1", self.installed()["patches"])
        with patch("sys.stdout", io.StringIO()):
            setup.main(["prepare", str(self.exe), "--no-experimental-texture32", "--no-visibility-math"])
            setup.main(["undo", str(self.exe)])
        self.assertEqual(self.exe.read_bytes(), self.pristine)
        with patch.object(setup, "atomic_write", side_effect=RuntimeError("write verification failed")), \
                patch("sys.stderr", io.StringIO()) as stderr, self.assertRaises(SystemExit) as stopped:
            setup.main(["prepare", str(self.exe), "--third-person"])
        self.assertEqual(stopped.exception.code, 1)
        self.assertEqual(stderr.getvalue(), "Client setup failed: write verification failed\n")


if __name__ == "__main__":
    unittest.main(verbosity=2)
