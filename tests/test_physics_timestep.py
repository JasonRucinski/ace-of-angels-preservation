"""Byte-level guard checks on the user's original 2.9.2 client.

Reads game/2.9.2/AOACLIENT.EXE.orig without modifying it and skips without
it. Instruction-level checks are in aoa.emulation.check_movement; these
verify supported inputs and reversible edits.
"""
import unittest

from aoa.client import prepare
from aoa.client.patches import base as patching
from aoa.client.patches import logger
from aoa.client.patches.physics_timestep import CAVE, PATCH, SITE, guard_code
from aoa.client.patches.station_host import LOCAL, OFFSET, ORIGINAL
from tests.support_patches import ORIGINAL as SOURCE, needs_game


@needs_game
class PhysicsTimestepTests(unittest.TestCase):
    def test_hostname_variants_undo_idempotence_bounds_and_corruption(self):
        baseline = logger.stabilize(SOURCE.read_bytes())
        allowed = set(range(SITE - 0x400000, SITE - 0x400000 + 6))
        allowed.update(range(CAVE - 0x400000, CAVE - 0x400000 + len(guard_code())))
        for hostname in (ORIGINAL, LOCAL):
            with self.subTest(hostname=hostname):
                original = baseline[:OFFSET] + hostname + baseline[OFFSET + len(hostname):]
                patched = patching.apply(PATCH, original, True)
                self.assertEqual(patching.apply(PATCH, patched, True), patched)
                self.assertEqual(patching.apply(PATCH, patched, False), original)
                self.assertEqual(patching.apply(PATCH, original, False), original)
                self.assertEqual(patched[OFFSET:OFFSET + len(hostname)], hostname)
                self.assertIn(PATCH.id, prepare.inspect(patched)["patches"])
                for offset in (SITE - 0x400000, CAVE - 0x400000, 0x1000):
                    altered = bytearray(patched)
                    altered[offset] ^= 1
                    # The engine rejects its own sites; prepare's whole-image check the rest.
                    with self.assertRaises(ValueError, msg=f"accepted modified input at {offset:#x}"):
                        prepare.inspect(bytes(altered))
                self.assertEqual(len(original), len(patched))
                self.assertTrue(all(i in allowed for i, (a, b) in enumerate(zip(original, patched)) if a != b))


if __name__ == "__main__":
    unittest.main()
