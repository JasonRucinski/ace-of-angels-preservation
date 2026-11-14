"""visibility-math-v1: original visibility code run with the patch in Unicorn."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from audit_render_pipeline import run  # noqa: E402
import prepare_client  # noqa: E402
import render_culling_experiment  # noqa: E402
import visibility_fix  # noqa: E402

ORIGINAL = Path(__file__).resolve().parents[1] / "game/2.9.2/AOACLIENT.EXE.orig"


class VisibilityFixTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.before = run(ORIGINAL)
        cls.after = run(ORIGINAL, corrected=True, patch=visibility_fix)

    def test_same_machine_code_as_verified_experiment(self):
        # Built where the offline experiment put it, the angle cave is identical.
        relocated = visibility_fix.code(render_culling_experiment.ANGLE)
        offset = render_culling_experiment.ANGLE - render_culling_experiment.CAVE
        self.assertEqual(render_culling_experiment.code()[offset:offset + len(relocated)], relocated)

    def test_trig_inputs_bounded_while_moving_and_turning(self):
        self.assertTrue(self.before["angular_domain_cases"])
        self.assertTrue(self.before["visibility_mismatches_with_nan_math_stub"])
        self.assertEqual(self.after["angular_domain_cases"], [])
        self.assertEqual(self.after["visibility_mismatches_with_nan_math_stub"], [])
        self.assertEqual(len(self.after["motion_samples"]), 480)
        for old, new in zip(self.before["motion_samples"], self.after["motion_samples"]):
            self.assertEqual(old[2], new[2])          # projected size never changes
            if old[1]:
                self.assertEqual(old, new)            # previously valid results unchanged

    def test_inside_sphere_visible_and_centre_unchanged(self):
        self.assertEqual(self.after["inside_sphere_cases"], 48)
        for distance in ("101", "100", "99", "1"):
            case = self.after["near_center_cases"][distance]
            self.assertTrue(case["visible"] and case["direction_finite"] and case["angular_bound_finite"])
            self.assertTrue(all(abs(c["input"]) <= 1 for c in case["math_calls"]))
        # Distance 0 (the player's own ship): hidden, no trig, as in the original.
        self.assertEqual(self.after["near_center_cases"]["0"], self.before["near_center_cases"]["0"])
        self.assertFalse(self.after["near_center_cases"]["0"]["visible"])
        self.assertEqual(self.before["small_object_cutoff_cases"], self.after["small_object_cutoff_cases"])

    def test_other_fpu_precisions(self):
        for control in (0x27F, 0x37F):
            result = run(ORIGINAL, corrected=True, fpcw=control, patch=visibility_fix)
            self.assertEqual(result["angular_domain_cases"], [])
            self.assertEqual(result["visibility_mismatches_with_nan_math_stub"], [])
            self.assertEqual(result["inside_sphere_cases"], 48)

    def test_preparation_applies_and_undoes_exactly(self):
        raw = ORIGINAL.read_bytes()
        on = prepare_client.configure(raw)
        off = prepare_client.configure(raw, bounded_visibility=False)
        self.assertIn(visibility_fix.NAME, prepare_client.inspect(on)["patches"])
        self.assertNotIn(visibility_fix.NAME, prepare_client.inspect(off)["patches"])
        self.assertEqual(visibility_fix.configure(on, False), off)
        self.assertEqual(prepare_client.configure(on), on)
        allowed = {i for o, old, new in visibility_fix.regions() for i in range(o, o + len(old))}
        self.assertTrue(all(i in allowed for i, (a, b) in enumerate(zip(on, off)) if a != b))
        for o, old, new in visibility_fix.regions():
            bad = bytearray(on)
            bad[o] ^= 0xFF
            with self.assertRaises(ValueError):
                visibility_fix.state(bytes(bad))
            partial = bytearray(on)
            partial[o:o + len(old)] = old
            with self.assertRaises(ValueError):
                visibility_fix.state(bytes(partial))
        # Coexists with the asteroid/solid-world hook in the same routine.
        both = prepare_client.configure(raw, experimental_asteroids=True)
        self.assertTrue({visibility_fix.NAME, "asteroid-mesh-distance-v1"} <= set(prepare_client.inspect(both)["patches"]))


if __name__ == "__main__":
    unittest.main()
