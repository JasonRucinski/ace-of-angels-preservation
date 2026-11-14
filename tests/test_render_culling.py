"""Regression tests for the actual offline culling machine-code patch."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parent))
from audit_render_pipeline import run
import render_culling_experiment as patch
import render_clock_experiment as clock
import prepare_client
import online_terrain

ROOT = Path(__file__).resolve().parents[1]


class CullingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = ROOT/'game/2.9.2/AOACLIENT.EXE.orig'
        cls.before = run(cls.source)
        cls.after = run(cls.source,corrected=True)

    def test_turning_domains_and_visibility(self):
        self.assertGreater(len(self.before['angular_domain_cases']),0)
        self.assertGreater(len(self.before['visibility_mismatches_with_nan_math_stub']),0)
        self.assertEqual(self.after['angular_domain_cases'],[])
        self.assertEqual(self.after['visibility_mismatches_with_nan_math_stub'],[])
        self.assertEqual(len(self.after['motion_samples']),480)
        # Previously valid outside-sphere results and all projected sizes stay
        # unchanged, not merely within a broad error tolerance.
        for old,new in zip(self.before['motion_samples'],self.after['motion_samples']):
            self.assertEqual(old[2],new[2])
            if old[1]:
                self.assertEqual(old,new)

    def test_inside_and_center_are_finite_and_visible(self):
        self.assertEqual(self.after['inside_sphere_cases'],48)
        for distance in ('101','100','99','1','0'):
            case = self.after['near_center_cases'][distance]
            self.assertTrue(case['visible'])
            self.assertTrue(case['direction_finite'])
            self.assertTrue(case['angular_bound_finite'])
            self.assertTrue(all(abs(c['input'])<=1 for c in case['math_calls']))
        self.assertEqual(self.before['small_object_cutoff_cases'],self.after['small_object_cutoff_cases'])

    def test_other_fpu_precisions(self):
        for control in (0x27F,0x37F):
            result = run(self.source,corrected=True,fpcw=control)
            self.assertEqual(result['angular_domain_cases'],[])
            self.assertEqual(result['visibility_mismatches_with_nan_math_stub'],[])
            self.assertEqual(result['inside_sphere_cases'],48)

    def test_exact_undo_bounds_and_rejection(self):
        # The offline experiment predates online terrain (cave 0x58B800) and the
        # promoted patches it shares sites with; test it on that older layout.
        prepared = online_terrain.configure(prepare_client.configure(
            self.source.read_bytes(), smooth_frame_clock=False, bounded_visibility=False), False)
        for source in (prepared,clock.configure(prepared)):
            result = patch.configure(source)
            self.assertEqual(patch.configure(result),result)
            self.assertEqual(patch.configure(result,False),source)
            allowed = {i for off,old,new in patch.regions() for i in range(off,off+len(old))}
            self.assertEqual(len(result),len(source))
            self.assertTrue(all(i in allowed for i,(a,b) in enumerate(zip(source,result)) if a!=b))
            for off,old,new in patch.regions():
                bad = bytearray(result)
                bad[off] ^= 0xFF
                with self.assertRaises(ValueError):
                    patch.configure(bytes(bad))
                partial = bytearray(result)
                partial[off:off+len(old)] = old
                with self.assertRaises(ValueError):
                    patch.configure(bytes(partial))
            bad = bytearray(result)
            bad[0x10000] ^= 1
            with self.assertRaises(ValueError):
                patch.configure(bytes(bad))


if __name__ == '__main__':
    unittest.main()
