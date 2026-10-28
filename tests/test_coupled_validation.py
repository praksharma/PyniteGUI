"""Solved membrane, shared-centreline strip and weak-drilling benchmarks."""
import unittest

import numpy as np

from coupled_validation import (AXES, STRAIN, FACTORS, membrane_patch, membrane_metrics,
    beam_strip, strip_metrics, drilling_project, drilling_metrics, quiet_solve)
from coupled_reference import membrane_stress
from pynitegui.qt.surface_results import centre_results, inspect_surface


class CoupledValidationTests(unittest.TestCase):
    def test_applied_traction_solves_affine_membrane_in_all_planes_under_refinement(self):
        for plane in AXES:
            for size in (40., 20., 10.):
                p = membrane_patch(size, plane)
                before = p.to_dict()
                r = quiet_solve(p)
                self.assertEqual(p.to_dict(), before)
                for combination in p.combinations:
                    with self.subTest(plane=plane, size=size, combination=combination):
                        selected = r.for_combination(combination)
                        metrics = membrane_metrics(p, selected)
                        self.assertLess(metrics["max_displacement_error_in"], 1e-10)
                        self.assertLess(metrics["max_stress_error_ksi"], 1e-9)
                        self.assertLess(metrics["max_normal_displacement_in"], 1e-12)
                        self.assertLess(metrics["max_drilling_rotation_rad"], 1e-12)
                        self.assertTrue(metrics["equilibrium_passed"])
                        # Edge/centre probes must agree with the solved stress,
                        # including after all three axes have been permuted.
                        expected = membrane_stress(3600., .2, STRAIN)*FACTORS[combination]
                        for row in centre_results(selected, "Patch")[::max(1, metrics["elements"]//4)]:
                            for xi, eta in ((0., 0.), (.63, -.27), (-1., 1.)):
                                probe = inspect_surface(selected, "Patch", row["element"], xi, eta)
                                np.testing.assert_allclose([probe[k] for k in ("Sx", "Sy", "Txy")], expected,
                                                           rtol=1e-8, atol=1e-10)
                                np.testing.assert_allclose([probe[k] for k in ("Mx", "My", "Mxy")], 0., atol=1e-12)

    def test_uniaxial_poisson_contraction_and_pure_shear_solve_without_rotation_penalty(self):
        for strain, nu in (((3e-5, -.3*3e-5, 0.), .3), ((0., 0., -4e-5), .2)):
            p = membrane_patch(20., "YZ", strain, nu)
            r = quiet_solve(p)
            metrics = membrane_metrics(p, r, strain)
            self.assertLess(metrics["max_displacement_error_in"], 1e-10)
            self.assertLess(metrics["max_stress_error_ksi"], 1e-9)
            self.assertTrue(metrics["equilibrium_passed"])
            # The off-plane frame anchor is not secretly carrying the tractions.
            member = r.solver.members["Anchor"]
            np.testing.assert_allclose(member.f("Service"), 0., atol=1e-9)

    def test_pressure_and_member_line_load_transfer_to_beam_and_slab_with_ei_sharing(self):
        for ratio in (.25, 1., 4.):
            records = {case: [] for case in ("Pressure", "Beam", "Reverse")}
            for size in (30., 15., 7.5):
                p = beam_strip(size, ratio)
                r = quiet_solve(p)
                for case, history in records.items():
                    metrics = strip_metrics(p, r.for_combination(case))
                    history.append(metrics)
                    self.assertTrue(metrics["equilibrium_passed"])
                    self.assertEqual(metrics["beam_segments"], int(240/size))
                    self.assertAlmostEqual(metrics["stiffness_ratio"], ratio)
            for case, history in records.items():
                with self.subTest(ratio=ratio, case=case):
                    fine = history[-1]
                    self.assertLess(fine["peak_relative_error"], .002)
                    self.assertLess(fine["field_error_relative_to_peak"], .002)
                    self.assertLess(fine["beam_moment_relative_error"], .005)
                    self.assertLess(fine["slab_moment_relative_l2"], .003)
                    self.assertLess(history[2]["slab_moment_relative_l2"], history[1]["slab_moment_relative_l2"])
                    self.assertLess(history[1]["slab_moment_relative_l2"], history[0]["slab_moment_relative_l2"])
                    key = "beam_moment_relative_error" if case == "Beam" else "peak_relative_error"
                    self.assertLess(history[2][key], history[1][key])
                    self.assertLess(history[1][key], history[0][key])
            self.assertAlmostEqual(records["Reverse"][-1]["peak_in"], -2*records["Pressure"][-1]["peak_in"], places=10)

    def test_interface_load_transfer_is_invariant_under_global_translation(self):
        baseline = None
        for origin in ((0., 0., 0.), (-137., 211., 43.)):
            p = beam_strip(15., origin=origin)
            r = quiet_solve(p)
            metrics = {case: strip_metrics(p, r.for_combination(case)) for case in p.combinations}
            for row in metrics.values():
                self.assertTrue(row.pop("equilibrium_passed"))
            if baseline is not None:
                for case in metrics:
                    np.testing.assert_allclose(list(metrics[case].values()), list(baseline[case].values()), rtol=1e-6, atol=1e-8)
            baseline = metrics

    def test_weak_drilling_moment_residual_is_measured_and_rejected_at_each_refinement(self):
        for size in (60., 30., 15.):
            with self.subTest(size=size):
                row = drilling_metrics(drilling_project(size))
                self.assertFalse(row["raw_equilibrium_passed"])
                self.assertTrue(row["production_rejected"])
                self.assertGreater(abs(row["residuals"]["MY"]), 100*row["limits"]["MY"])
                # Summed local weak-spring torques independently explain the
                # external global moment residual, not a reference-point error.
                np.testing.assert_allclose(row["summed_drilling_torque_kip_in"],
                    [row["residuals"][key] for key in ("MX", "MY", "MZ")], rtol=1e-6, atol=1e-7)


if __name__ == "__main__":
    unittest.main()
