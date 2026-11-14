"""Safe movement baselines and downstream absolute-refresh regressions."""
import math
import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import relay_motion as motion


def packet(mask, body):
    return struct.pack("<HHI", 0x8000, 1, mask) + body


class RelayMotionTests(unittest.TestCase):
    def test_all_fields_round_trip_and_control_not_refreshed(self):
        state = {flag: ((123,) if fmt == "i" else tuple(float(i + 1) for i in range(3 if fmt == "3f" else 1)))
                 for flag, _, fmt, _ in motion.FIELDS}
        wire = motion.snapshot(1, state, include_control=True)
        actual, present, missing = motion.update(wire, {})
        self.assertEqual(actual, state)
        self.assertEqual(present, set(state))
        self.assertEqual(missing, set())
        refreshed, present, _ = motion.update(motion.snapshot(1, state), {})
        self.assertNotIn(0x400, present)
        self.assertEqual(refreshed, {flag: value for flag, value in state.items() if flag != 0x400})

    def test_delta_scales_and_absolute_precedence(self):
        for flag, _, _, scale in motion.FIELDS:
            if scale is None:
                continue
            for shift, fmt, values in ((1, "3h", (32767, -32768, 5)), (2, "3b", (127, -128, 3))):
                original = {flag: (1.5, 2.5, 3.5)}
                actual, _, _ = motion.update(packet(flag << shift, struct.pack("<" + fmt, *values)), original)
                expected = struct.unpack("<3f", struct.pack("<3f", *(a + b * scale for a, b in zip(original[flag], values))))
                self.assertEqual(actual[flag], expected)
                self.assertEqual(original, {flag: (1.5, 2.5, 3.5)})
            actual, _, _ = motion.update(packet(flag * 7, struct.pack("<3f", 1, 2, 3)), {})
            self.assertEqual(actual[flag], (1, 2, 3))

    def test_unobserved_bases_are_not_invented(self):
        before = motion.initial((0, 0, 0))
        state, present, missing = motion.update(packet(0x10, struct.pack("<3h", 1, 2, 3)), before)
        self.assertEqual(state, before)
        self.assertEqual(missing, {8})
        state, _, _ = motion.update(packet(8, struct.pack("<3f", 1, 2, 3)), state)
        state, _, missing = motion.update(packet(0x20, struct.pack("<3b", 1, 2, 3)), state)
        self.assertEqual(state[8], (2, 4, 6))
        self.assertEqual(missing, set())

    def test_nonfinite_truncated_and_unknown_fields_do_not_poison_state(self):
        before = motion.initial((1, 2, 3))
        for flag, _, fmt, _ in motion.FIELDS:
            if fmt == "i":
                continue
            for invalid in (math.nan, math.inf, -math.inf):
                values = (invalid, 0, 0) if fmt == "3f" else (invalid,)
                with self.assertRaises(ValueError):
                    motion.update(packet(flag, struct.pack("<" + fmt, *values)), before)
        for malformed in (b"", packet(1, bytes(11)), packet(0, b"x"), packet(0x80000000, bytes(4))):
            with self.assertRaises(ValueError):
                motion.update(malformed, before)
        self.assertEqual(before, motion.initial((1, 2, 3)))

    def test_gun_state_round_trip_and_bounds(self):
        state = motion.initial((1, 2, 3))
        firing = bytes([0x82]) + struct.pack("<HBHB", 2, 15, 7, 15)
        state, present, _ = motion.update(packet(motion.GUN_STATE, firing), state)
        self.assertIn(motion.GUN_STATE, present)
        self.assertEqual(state[motion.GUN_STATE], (0x82, ((2, 15), (7, 15))))
        # Repeated in every snapshot (absolute), unlike the 0x400 status flags.
        snap = motion.snapshot(1, state)
        self.assertEqual(struct.unpack_from("<I", snap, 4)[0] & motion.GUN_STATE, motion.GUN_STATE)
        self.assertTrue(snap.endswith(firing))
        self.assertEqual(motion.update(snap, motion.initial((0, 0, 0)))[0][motion.GUN_STATE], state[motion.GUN_STATE])
        stopped, _, _ = motion.update(packet(motion.GUN_STATE, b"\x80" ), state)
        self.assertEqual(stopped[motion.GUN_STATE], (0x80, ()))
        for bad in (b"", b"\x01", bytes([1]) + struct.pack("<HB", motion.MAX_SYSTEM_INDEX, 1),
                    firing + b"x"):
            with self.assertRaises(ValueError):
                motion.update(packet(motion.GUN_STATE, bad), state)

    def test_client_stats_and_server_stats_block(self):
        stats = struct.pack("<hhhHi", 9, 9, 5, 0, 4321)
        # Submask parts before 0x100, in decoder order: 1 (15), 2 (1+6n),
        # 0x20, 4, 8 (1 each), 0x10, 0x40 (2 each); then the stats.
        submask = 0x100 | 1 | 2 | 0x20 | 4 | 8 | 0x10 | 0x40
        before = bytes(15) + bytes([2]) + bytes(12) + bytes(3) + bytes(4)
        tail = struct.pack("<I", submask) + before + stats
        payload = bytes(8) + bytes(12) + bytes(2) + tail  # prefix stand-in, 0x40000000 u16
        mask = motion.STATS | 0x40000000
        self.assertEqual(motion.client_stats(payload, 20, mask), (5, 4321))
        self.assertIsNone(motion.client_stats(payload, 8, 0x40))
        full = bytes(4) + struct.pack("<h", 6) + bytes(20) + struct.pack("<i", 77)  # 30 bytes
        real = bytes(8) + struct.pack("<I", 0x200 | 0x41) + bytes(15) + bytes(2) + full
        self.assertEqual(motion.client_stats(real, 8, motion.STATS), (6, 77))
        with self.assertRaises(ValueError):
            motion.client_stats(real[:-1], 8, motion.STATS)
        no_stats = bytes(8) + struct.pack("<I", 0x20) + b"\x01"
        self.assertIsNone(motion.client_stats(no_stats, 8, motion.STATS))
        for truncated in (payload[:-1], bytes(8) + b"\x00\x01"):
            with self.assertRaises(ValueError):
                motion.client_stats(truncated, 20, mask)
        snap = motion.snapshot(1, motion.initial((1, 2, 3)), stats=(3, 2, 7, -5))
        self.assertEqual(struct.unpack_from("<I", snap, 4)[0], 0x40 | 1 | motion.STATS)
        self.assertTrue(snap.endswith(struct.pack("<IhhhHi", 0x100, 3, 2, 7, 0, -5)))

    def test_next_absolute_snapshot_recovers_observer_after_dropped_delta(self):
        server = motion.initial((100, 200, 300))
        observer = dict(server)
        server, _, _ = motion.update(packet(4, struct.pack("<3b", 1, 2, 3)), server)
        # This update never arrives at the observer.
        server, _, _ = motion.update(packet(4, struct.pack("<3b", 4, 5, 6)), server)
        observer, _, _ = motion.update(motion.snapshot(1, server), observer)
        self.assertEqual(server, observer)
        # A duplicate absolute delivery cannot apply the delta twice.
        self.assertEqual(motion.update(motion.snapshot(1, server), observer)[0], observer)


if __name__ == "__main__":
    unittest.main(verbosity=2)
