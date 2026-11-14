"""Highlight-reel helpers: scripted pilot paths and packets, --start-vessel.

Game-free: checks bot.py's packets against the relay's own parsers.
"""
import contextlib
import io
import math
import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent / "reel"))
import bot  # noqa: E402
import edit  # noqa: E402
import relay_motion  # noqa: E402
import station_stub as stub  # noqa: E402
from station_runtime import parse_args  # noqa: E402


class ReelTests(unittest.TestCase):
    def test_paths(self):
        self.assertEqual(bot.path_state({"kind": "hold", "at": [1, 2, 3]}, 5), ((1, 2, 3), (0.0, 0.0, 0.0)))
        line = {"kind": "line", "start": [10, 0, -5], "velocity": [0, 2, 100]}
        self.assertEqual(bot.path_state(line, 2), ((10, 4, 195), (0, 2, 100)))
        circle = {"kind": "circle", "center": [0, 50, 0], "radius": 1000, "speed": 500, "phase": 90}
        for t in (0, 1.3, 7):
            (x, y, z), velocity = bot.path_state(circle, t)
            self.assertAlmostEqual(math.hypot(x, z), 1000, places=6)
            self.assertEqual(y, 50)
            self.assertAlmostEqual(math.hypot(*velocity), 500, places=6)
            self.assertAlmostEqual(x * velocity[0] + z * velocity[2], 0, places=4)  # tangent
        with self.assertRaises(ValueError):
            bot.path_state({"kind": "spiral"}, 0)

    def test_packets_pass_the_relay_parsers(self):
        payload = bot.movement(3, (1.5, -2, 3e4), (0, 0, 900))
        prefix = stub.movement_update(payload, 3)
        self.assertEqual(prefix, payload)
        self.assertIsNone(stub.movement_update(payload, 4))  # the header slot must be the sender's
        state, present, _ = relay_motion.update(prefix, {})
        self.assertEqual(state[0x40], (1.5, -2.0, 3e4))
        self.assertEqual(state[1], (0.0, 0.0, 900.0))
        for hull in stub.SELECTABLE_VESSELS:
            self.assertEqual(stub.ship_request(bot.hull_request(hull)), hull)
        login = bot.login_request("Wing2")
        self.assertEqual((len(login), login[31:36]), (381, b"Wing2"))
        self.assertEqual(struct.unpack_from("<I", bot.job_request(77), 60)[0], 77)

    def test_title_times_and_tracking(self):
        starts = [0.0, 1.57, 2.93]
        self.assertEqual(edit.resolve_time(4.5, starts), 4.5)
        self.assertEqual(edit.resolve_time("@2", starts), 2.93)
        self.assertEqual(edit.resolve_time("@1+0.4", starts), 1.97)
        for bad in ("2", "@x", "@1-2"):
            with self.assertRaises(ValueError):
                edit.resolve_time(bad, starts)
        self.assertEqual(edit.tracked("Go.", 1), "G O .")

    def test_start_vessel_option(self):
        self.assertEqual(parse_args(["key", "log"]).start_vessel, "Ym Khtat")
        self.assertEqual(parse_args(["key", "log", "--profile", "local-relay", "--start-vessel", "Naroch"]).start_vessel,
                         "Naroch")
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            parse_args(["key", "log", "--no-experimental-relay", "--start-vessel", "Naroch"])


if __name__ == "__main__":
    unittest.main()
