"""Deterministic original-x86 camera and timer regressions; no UI or client launch."""
import math
import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from compare_render_clocks import view, project
from emulate_codec import Emu, SCRATCH
from pe_util import PE
from unicorn.x86_const import UC_X86_REG_FPCW


class RenderMotionTests(unittest.TestCase):
    def setUp(self):
        path = Path(__file__).resolve().parents[1] / 'game/2.9.2/AOACLIENT.EXE.orig'
        self.emu = Emu(PE(path))
        self.emu.uc.reg_write(UC_X86_REG_FPCW, 0x7F)

    def test_original_camera_translation_and_turns(self):
        # For a point fixed relative to the moving camera, its projected
        # location should stay fixed while the camera translates and turns.
        for offset in (0, 10000, 100000):
            for frame in range(120):
                yaw = frame / 120
                eye = (offset + frame * 3, offset / 2, offset)
                right = (math.cos(yaw), 0, -math.sin(yaw))
                forward = (math.sin(yaw), 0, math.cos(yaw))
                target = tuple(eye[i] + 100*right[i] + 1000*forward[i] for i in range(3))
                actual = project(view(self.emu, eye, yaw), target)
                self.assertLess(math.dist(actual, (96, 0)), 0.03)

    def test_quantized_clock_repeats_and_projection_jitter(self):
        trajectories = {}
        repeated = {}
        for name, quantum in (('original', 15.625), ('qpc', 1), ('ideal', 0)):
            positions, ticks = [], []
            for frame in range(288):
                ms = frame * 1000 / 144
                tick = math.floor(ms / quantum) * quantum if quantum else ms
                ticks.append(tick)
                t = tick / 1000
                positions.append(project(view(self.emu, (500*t, 0, 0), 0.2*t), (0, 0, 5000))[0])
            trajectories[name] = positions
            repeated[name] = sum(a == b for a,b in zip(ticks,ticks[1:]))
        self.assertGreater(repeated['original'], 140)
        self.assertEqual(repeated['qpc'], 0)
        def error(name):
            errors = [(b-a)-(d-c) for a,b,c,d in zip(trajectories[name],trajectories[name][1:],trajectories['ideal'],trajectories['ideal'][1:])]
            return math.sqrt(sum(x*x for x in errors)/len(errors))
        self.assertLess(error('qpc'), error('original') / 10)

    def test_original_timer_keeps_previous_delta_on_repeated_tick(self):
        # Important limitation: this tests the timer, not every consumer.
        timer = SCRATCH + 0x1000
        self.emu.write(timer, bytes(32))
        for tick in (1000, 1016, 1016):
            self.emu.thiscall(0x40E000, timer, tick)
        self.assertEqual(struct.unpack('<II', self.emu.read(timer, 8)), (1016, 16))
        self.emu.thiscall(0x40E000, timer, 1023)
        self.assertEqual(struct.unpack('<II', self.emu.read(timer, 8)), (1023, 7))


if __name__ == '__main__':
    unittest.main()
