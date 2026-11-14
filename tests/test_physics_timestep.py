"""Byte-level guard checks on the user's original 2.9.2 client.

Reads game/2.9.2/AOACLIENT.EXE.orig without modifying it and skips without
it. Instruction-level checks are in emulate_movement.py; these verify
supported inputs and reversible edits.
"""
import unittest

from aoa.client import base  # noqa: E402
from aoa.client.patches.physics_timestep import configure, SITE_OFFSET, CAVE_OFFSET, guard_code  # noqa: E402
from aoa.client.patches.station_host import OFFSET, ORIGINAL, LOCAL  # noqa: E402
from aoa.paths import ROOT

SOURCE = ROOT / "game/2.9.2/AOACLIENT.EXE.orig"


@unittest.skipUnless(SOURCE.is_file(), "requires user's original 2.9.2 executable")
class PhysicsTimestepTests(unittest.TestCase):
    def test_hostname_variants_undo_idempotence_bounds_and_corruption(self):
        baseline = configure(base.configure(SOURCE.read_bytes())[0], undo=True)
        allowed = set(range(SITE_OFFSET, SITE_OFFSET + 6))
        allowed.update(range(CAVE_OFFSET, CAVE_OFFSET + len(guard_code())))
        for hostname in (ORIGINAL, LOCAL):
            with self.subTest(hostname=hostname):
                original = baseline[:OFFSET] + hostname + baseline[OFFSET + len(hostname):]
                patched = configure(original)
                self.assertEqual(configure(patched), patched)
                self.assertEqual(configure(patched, undo=True), original)
                self.assertEqual(configure(original, undo=True), original)
                self.assertEqual(patched[OFFSET:OFFSET + len(hostname)], hostname)
                for offset in (SITE_OFFSET, CAVE_OFFSET, 0x1000):
                    altered = bytearray(patched)
                    altered[offset] ^= 1
                    with self.assertRaises(ValueError, msg=f"accepted modified input at {offset:#x}"):
                        configure(bytes(altered))
                self.assertEqual(len(original), len(patched))
                self.assertTrue(all(i in allowed for i, (a, b) in enumerate(zip(original, patched)) if a != b))


if __name__ == "__main__":
    unittest.main()
