"""The archived clock experiment's own configure(); needs the game.

Its counter-conversion test runs on the identical frame-clock-v1 cave in
tests/test_frame_clock.py.
"""
import unittest

from archive.offline_baseline import render_clock_experiment as clock
from aoa.client import prepare
from aoa.paths import ROOT
from tests.support_patches import needs_game


@needs_game
class ClockTests(unittest.TestCase):
    def test_reversible(self):
        p = ROOT / 'game/2.9.2/AOACLIENT.EXE.orig'
        # The experiment shares the clock sites with frame-clock-v1; test it alone.
        original = prepare.configure(p.read_bytes(), smooth_frame_clock=False)
        patched = clock.configure(original)
        self.assertEqual(clock.configure(patched), patched)
        self.assertEqual(clock.configure(patched, False), original)
        allowed = {i for off, old, new in clock.regions() for i in range(off, off + len(old))}
        self.assertEqual(len(original), len(patched))
        self.assertTrue(all(i in allowed for i,(a,b) in enumerate(zip(original, patched)) if a != b))
        for off, old, new in clock.regions():
            bad = bytearray(patched)
            bad[off] ^= 0xFF
            with self.assertRaises(ValueError):
                clock.configure(bytes(bad))


if __name__ == '__main__':
    unittest.main()
