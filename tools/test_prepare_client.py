"""Exercise preparation on temporary copies of the user's original client."""
import hashlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import archive_terminator
import explicit_protection
import patch_client
import physics_timestep
import prepare_client as setup
from local_station import STABLE_SHA256

SOURCE = Path(__file__).resolve().parents[1] / "game/2.9.2/AOACLIENT.EXE.orig"


@unittest.skipUnless(SOURCE.is_file(), "requires user's original 2.9.2 executable")
class ClientPreparationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original = SOURCE.read_bytes()
        assert hashlib.sha256(cls.original).hexdigest() == patch_client.PRISTINE_292
        cls.stable = patch_client.configure(cls.original)[0]

    def test_composed_patches_and_host_changes(self):
        self.assertEqual(setup.sha(self.stable), STABLE_SHA256)
        for source in (self.original, self.stable, physics_timestep.configure(self.stable)):
            prepared = setup.configure(source)
            self.assertEqual(setup.configure(prepared), prepared)
            changed = setup.configure(prepared, "10.0.0.1")
            self.assertEqual(setup.inspect(changed)["host"], "10.0.0.1")
            self.assertIn("zero-time-physics-v1", setup.inspect(changed)["patches"])
            self.assertIn("background-network-v1", setup.inspect(changed)["patches"])
            self.assertIn("archive-terminator-v1", setup.inspect(changed)["patches"])
            self.assertIn("ship-menu-aspect-v1", setup.inspect(changed)["patches"])
            self.assertEqual(prepared[setup.BACKGROUND_OFFSET:setup.BACKGROUND_OFFSET + 2], b"\x90\x90")
            self.assertEqual(setup.configure(changed), prepared)
        # A version-1 setup (no background patch) upgrades in place.
        version1 = archive_terminator.configure(
            setup.background_site(setup.configure(self.stable, "127.0.0.1"), False), False)
        self.assertNotIn("background-network-v1", setup.inspect(version1)["patches"])
        self.assertEqual(setup.configure(version1, "127.0.0.1"), setup.configure(self.stable, "127.0.0.1"))

    def test_explicit_protection_opt_in_and_exact_undo(self):
        normal = setup.configure(self.original)
        self.assertFalse(explicit_protection.state(normal))
        experimental = setup.configure(normal, experimental_protection=True)
        self.assertIn(explicit_protection.NAME, setup.inspect(experimental)["patches"])
        self.assertEqual(setup.configure(experimental), experimental)
        self.assertTrue(explicit_protection.state(setup.configure(experimental, "127.0.0.1")))
        self.assertEqual(setup.configure(experimental, experimental_protection=False), normal)
        with self.assertRaisesRegex(ValueError, "loopback"):
            setup.configure(experimental, "10.0.0.1")
        for offset in (explicit_protection.SITE_OFFSET, explicit_protection.CAVE_OFFSET):
            corrupt = bytearray(experimental)
            corrupt[offset] ^= 1
            with self.assertRaises(ValueError):
                setup.configure(corrupt)
        with tempfile.TemporaryDirectory() as tmp:
            exe = Path(tmp) / "AOACLIENT.EXE"
            exe.write_bytes(self.original)
            record = setup.prepare(exe, experimental_protection=True)
            self.assertEqual(record["patch_version"], 22)
            self.assertIn(explicit_protection.NAME, setup.check(exe, require_assets=False)["patches"])
            setup.prepare(exe, experimental_protection=False)
            self.assertEqual(exe.read_bytes(), normal)
            setup.prepare(exe, undo=True)
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
                setup.prepare(exe, "10.0.0.1")
                self.assertEqual(setup.check(exe, require_assets=False)["host"], "10.0.0.1")
                setup.prepare(exe, undo=True)
                self.assertEqual(exe.read_bytes(), source)
                with self.assertRaises(ValueError):
                    setup.check(exe, require_assets=False)
                setup.prepare(exe)
                setup.prepare(exe, undo=True)
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
                setup.prepare(exe, undo=True)
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
            setup.prepare(exe, undo=True)
            self.assertEqual(exe.read_bytes(), self.original)

    def test_undo_does_not_require_a_working_wrapper(self):
        with tempfile.TemporaryDirectory() as tmp:
            exe = Path(tmp) / "AOACLIENT.EXE"
            exe.write_bytes(self.original)
            setup.prepare(exe)
            (exe.parent / "DDraw.dll").write_bytes(b"unrecognized wrapper added later")
            with self.assertRaises(ValueError):
                setup.check(exe, require_assets=False)
            setup.prepare(exe, undo=True)
            self.assertEqual(exe.read_bytes(), self.original)


class SyntheticClientTests(unittest.TestCase):
    """Option handling on the synthetic client of test_patch_layout; game-free."""
    FORCED = {"smooth_frame_clock": "frame-clock-v1", "bounded_visibility": "visibility-math-v1",
              "chase_camera": "third-person-camera-v3", "powerup_pickups": "powerup-pickup-v1",
              "menu_framing": "ship-menu-aspect-v1"}

    @classmethod
    def setUpClass(cls):
        import test_patch_layout
        cls.pristine = test_patch_layout.synthetic_pristine()
        pristine_sha = hashlib.sha256(cls.pristine).hexdigest()
        with patch.object(patch_client, "PRISTINE_292", pristine_sha):
            stable_sha = hashlib.sha256(patch_client.configure(cls.pristine)[0]).hexdigest()
        cls.hashes = (patch.object(patch_client, "PRISTINE_292", pristine_sha),
                      patch.object(setup, "STABLE_SHA256", stable_sha),
                      patch.object(physics_timestep, "STABLE_SHA256", stable_sha))

    def setUp(self):
        for mocked in self.hashes:
            mocked.start()
            self.addCleanup(mocked.stop)
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
                setup.prepare(self.exe, **{key: False})
                # What play.md tells LAN players to run: only the Station is named.
                state = setup.prepare(self.exe, host="aoalan", experimental_protection=False)
                self.assertEqual(state["host"], "aoalan")
                self.assertNotIn(name, state["patches"])
                setup.prepare(self.exe, **{key: True})
                self.assertIn(name, setup.prepare(self.exe, host="localhost")["patches"])
        setup.prepare(self.exe, distant_objects=True, experimental_texture32=True,
                      **dict.fromkeys(self.FORCED, False))
        before = self.exe.read_bytes()
        setup.prepare(self.exe)
        self.assertEqual(self.exe.read_bytes(), before)
        self.assertEqual(self.installed()["host"], "localhost")
        state = setup.prepare(self.exe, host="10.0.0.1")
        self.assertFalse(set(self.FORCED.values()) & set(state["patches"]))
        self.assertIn("distant-world-objects-v1", state["patches"])
        self.assertIn("texture-argb8888-v1", state["patches"])
        setup.prepare(self.exe, undo=True)
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

    def test_command_line(self):
        for argv in (["check", str(self.exe), "--station", "aoalan"],
                     ["undo", str(self.exe), "--no-third-person"],
                     ["launch", str(self.exe), "--frame-clock"]):
            with self.subTest(argv=argv), patch("sys.stderr", io.StringIO()) as stderr, \
                    self.assertRaises(SystemExit) as stopped:
                setup.main(argv)
            self.assertEqual(stopped.exception.code, 2)
            self.assertIn("applies only to prepare", stderr.getvalue())
        with patch("sys.stdout", io.StringIO()):
            setup.main(["prepare", str(self.exe), "--no-third-person"])
            setup.main(["prepare", str(self.exe), "--station", "aoalan"])
        self.assertNotIn("third-person-camera-v3", self.installed()["patches"])
        self.assertEqual(self.installed()["host"], "aoalan")
        with patch.object(setup, "atomic_write", side_effect=RuntimeError("write verification failed")), \
                patch("sys.stderr", io.StringIO()) as stderr, self.assertRaises(SystemExit) as stopped:
            setup.main(["prepare", str(self.exe), "--third-person"])
        self.assertEqual(stopped.exception.code, 1)
        self.assertEqual(stderr.getvalue(), "Client setup failed: write verification failed\n")


if __name__ == "__main__":
    unittest.main(verbosity=2)
