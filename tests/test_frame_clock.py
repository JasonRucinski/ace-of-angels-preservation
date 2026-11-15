"""frame-clock-v1: patch bytes, client preparation, and the emulated clock and timer gate.

The clock and gate caves run alone in Unicorn with stubbed Windows counters
(game-free); the preparation checks run on the user's original client and
skip without it.
"""
import struct
import unittest
from itertools import product

from unicorn import Uc, UC_ARCH_X86, UC_MODE_32, UC_HOOK_CODE
from unicorn.x86_const import UC_X86_REG_EAX, UC_X86_REG_ECX, UC_X86_REG_EDX, UC_X86_REG_ESP, UC_X86_REG_FPCW

from aoa.client import prepare
from aoa.client.patches import base as patching
from aoa.client.patches import frame_clock
from aoa.live import frame_pacing
from archive.offline_baseline import render_clock_experiment
from tests.support_patches import ORIGINAL, needs_game, triples

QPF_STUB, QPC_STUB, FRAME_STUB_EXIT, RETURN = 0x500000, 0x500010, 0x500020, 0x500100
APP = 0x600000


def run_gate(now_ms, last_frame_ms):
    """Run the gate cave as the timer callback would; return (frame ran, eax, ecx at frame)."""
    u = Uc(UC_ARCH_X86, UC_MODE_32)
    u.mem_map(0x400000, 0x300000)
    u.mem_map(0x700000, 0x20000)
    u.mem_write(frame_clock.CLOCK, frame_clock.clock_code())
    u.mem_write(frame_clock.GATE, frame_clock.gate_code())
    u.mem_write(frame_clock.QPF, struct.pack("<I", QPF_STUB))
    u.mem_write(frame_clock.QPC, struct.pack("<I", QPC_STUB))
    for stub in (QPF_STUB, QPC_STUB):
        u.mem_write(stub, bytes.fromhex("c20400"))         # ret 4
    u.mem_write(frame_clock.FRAME, bytes.fromhex("b801000000c3"))  # mov eax,1; ret
    u.mem_write(APP + 0x30, struct.pack("<I", last_frame_ms & 0xFFFFFFFF))
    seen = {}

    def hook(uc, address, size, data):
        if address in (QPF_STUB, QPC_STUB):
            ptr = struct.unpack("<I", uc.mem_read(uc.reg_read(UC_X86_REG_ESP) + 4, 4))[0]
            value = 10_000_000 if address == QPF_STUB else now_ms * 10_000
            uc.mem_write(ptr, struct.pack("<q", value))
            uc.reg_write(UC_X86_REG_EAX, 1)
        elif address == frame_clock.FRAME:
            seen["ecx"] = uc.reg_read(UC_X86_REG_ECX)
    u.hook_add(UC_HOOK_CODE, hook)
    u.mem_write(0x710000, struct.pack("<I", RETURN))
    u.reg_write(UC_X86_REG_ESP, 0x710000)
    u.reg_write(UC_X86_REG_ECX, APP)
    u.emu_start(frame_clock.GATE, RETURN, count=2000)
    assert u.reg_read(UC_X86_REG_ESP) == 0x710004, "gate must return to its caller with a balanced stack"
    return "ecx" in seen, u.reg_read(UC_X86_REG_EAX), seen.get("ecx")


class FrameClockTests(unittest.TestCase):
    def test_clock_matches_verified_experiment(self):
        self.assertEqual(frame_clock.clock_code(), render_clock_experiment.code())
        sites = {off: new for off, old, new in triples(frame_clock.PATCH)}
        for off, old, new in render_clock_experiment.regions():
            self.assertEqual(sites[off], new)

    def test_gate_runs_timer_frames_only_after_a_quiet_period(self):
        for now, last, expected in ((1000, 990, False), (1000, 951, False), (1000, 950, True),
                                    (1000, 900, True), (5, 2**32 - 100, True),   # clock wrap
                                    (2**32 + 10, 2**32 - 30, False)):
            with self.subTest(now=now, last=last):
                ran, eax, ecx = run_gate(now, last)
                self.assertEqual(ran, expected)
                if ran:
                    self.assertEqual((eax, ecx), (1, APP))  # frame result passes through, app intact
                else:
                    self.assertEqual(eax, 0)

    def test_counter_conversion_and_abi(self):
        # Moved from the archived clock experiment's suite: the same cave bytes.
        clock = frame_clock
        for frequency, cw in product((10_000_000, 3_579_545), (0x7F, 0x27F, 0x37F)):
            for ms in (0, 1, 17, 551433734, 2**32 - 1, 2**32 + 17):
                with self.subTest(frequency=frequency, ms=ms):
                    u = Uc(UC_ARCH_X86, UC_MODE_32)
                    u.reg_write(UC_X86_REG_FPCW, cw)
                    u.mem_map(0x400000, 0x200000)
                    u.mem_map(0x700000, 0x20000)
                    u.mem_write(clock.CLOCK, clock.clock_code())
                    u.mem_write(clock.QPF, struct.pack('<I', QPF_STUB))
                    u.mem_write(clock.QPC, struct.pack('<I', QPC_STUB))
                    u.mem_write(QPF_STUB, bytes.fromhex('c20400'))
                    u.mem_write(QPC_STUB, bytes.fromhex('c20400'))

                    def api(uc, address, size, data):
                        if address in (QPF_STUB, QPC_STUB):
                            sp = uc.reg_read(UC_X86_REG_ESP)
                            ptr = struct.unpack('<I', uc.mem_read(sp + 4, 4))[0]
                            value = frequency if address == QPF_STUB else round(ms * frequency / 1000)
                            uc.mem_write(ptr, struct.pack('<q', value))
                            uc.reg_write(UC_X86_REG_EAX, 1)
                    u.hook_add(UC_HOOK_CODE, api)
                    u.mem_write(0x710000, struct.pack('<I', RETURN))
                    for reg, value in [(UC_X86_REG_ESP, 0x710000), (UC_X86_REG_ECX, 1234), (UC_X86_REG_EDX, 5678)]:
                        u.reg_write(reg, value)
                    u.emu_start(clock.CLOCK, RETURN, count=1000)
                    self.assertEqual(u.reg_read(UC_X86_REG_EAX), ms & 0xFFFFFFFF)
                    self.assertEqual(u.reg_read(UC_X86_REG_ESP), 0x710004)
                    self.assertEqual(u.reg_read(UC_X86_REG_ECX), 1234)
                    self.assertEqual(u.reg_read(UC_X86_REG_EDX), 5678)
                    self.assertEqual(u.reg_read(UC_X86_REG_FPCW), cw)

    @needs_game
    def test_preparation_applies_and_undoes_exactly(self):
        raw = ORIGINAL.read_bytes()
        on = prepare.configure(raw)
        off = prepare.configure(raw, smooth_frame_clock=False)
        self.assertIn(frame_clock.NAME, prepare.inspect(on)["patches"])
        self.assertNotIn(frame_clock.NAME, prepare.inspect(off)["patches"])
        self.assertEqual(patching.apply(frame_clock.PATCH, on, False), off)
        self.assertEqual(prepare.configure(on), on)                       # idempotent
        self.assertEqual(prepare.configure(on, smooth_frame_clock=False), off)
        allowed = {i for o, old, new in triples(frame_clock.PATCH) for i in range(o, o + len(old))}
        self.assertTrue(all(i in allowed for i, (a, b) in enumerate(zip(on, off)) if a != b))
        for o, old, new in triples(frame_clock.PATCH):
            bad = bytearray(on)
            bad[o] ^= 0xFF
            with self.assertRaises(ValueError):
                patching.state(frame_clock.PATCH, bytes(bad))

    @needs_game
    def test_partial_patch_rejected(self):
        off = prepare.configure(ORIGINAL.read_bytes(), smooth_frame_clock=False)
        o, old, new = triples(frame_clock.PATCH)[-1]          # gate call only
        partial = off[:o] + new + off[o + len(old):]
        with self.assertRaises(ValueError):
            patching.state(frame_clock.PATCH, partial)

    def test_pacing_summary(self):
        frames = [{"t": n / 60, "counter": n, "clock": round(n * 1000 / 60), "camera": (0, 0, n * 8.0),
                   "active": 1} for n in range(120)]
        s = frame_pacing.summarize(frames, 1000, 2.0)
        self.assertEqual(s["missed_counter_steps"], 0)
        self.assertAlmostEqual(s["present_interval_ms"]["mean"], 16.667, places=2)
        self.assertEqual(set(s["game_ms_per_frame"]), {"16", "17"})
        self.assertLess(s["camera"]["step_error_rms_frames"], 1e-6)
        self.assertEqual(s["active_frames"], 120)
        jumpy = [dict(f, clock=(f["counter"] // 2) * 31) for f in frames]  # 0/31 ms steps
        self.assertGreater(frame_pacing.summarize(jumpy, 1000, 2.0)["game_vs_present_rms_ms"], 10)


if __name__ == "__main__":
    unittest.main()
