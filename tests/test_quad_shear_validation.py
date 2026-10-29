"""Independent shear references and deliberately bounded research recovery."""
import unittest

import numpy as np

from quad_shear_validation import CASES, FACTORS, METHODS, SIZES, metrics, patch_divergence, solve_case
from plate_reference import navier
from pynitegui.qt.plate_model import PlateDefinition, analyze_plate
from pynitegui.qt.plate_inspection import inspect_plate, plate_probe_table
from pynitegui.qt.surface_results import FIELDS
from pynitegui.qt.units import UNIT_SYSTEMS


class QuadShearValidationTests(unittest.TestCase):
    def test_quadratic_moment_patch_differentiation_and_coordinate_scaling(self):
        for spacing, origin in (((7., 11.), (0., 0.)), ((.07, 110.), (17., -31.))):
            x, y = np.meshgrid(np.arange(5)*spacing[0], np.arange(5)*spacing[1])
            points = np.column_stack((x.ravel(), y.ravel()))
            x, y = points.T
            # Independently differentiated manufactured moment tensors.
            moments = np.column_stack((2*x*x+3*x*y-y, -x*y+4*y*y+x, x*x-y*y+2*x*y))
            expected = np.column_stack((6*x+y, x+10*y))
            for factor in (1., -2., 0.):
                shear, valid = patch_divergence(points+origin, factor*moments)
                self.assertEqual(valid.sum(), 9)
                np.testing.assert_allclose(shear[valid], factor*expected[valid], rtol=1e-10, atol=1e-8)
                self.assertTrue(np.isnan(shear[~valid]).all())

    def test_incomplete_patches_never_bridge_a_hole_or_extrapolate_to_an_edge(self):
        x, y = np.meshgrid(np.arange(7.), np.arange(7.))
        points = np.column_stack((x.ravel(), y.ravel()))
        points = points[np.any(points != [3., 3.], axis=1)]
        shear, valid = patch_divergence(points, np.column_stack((points, points[:, 0])))
        expected = np.all((points > 0) & (points < 6), axis=1) & np.any(abs(points-[3, 3]) > 1, axis=1)
        np.testing.assert_array_equal(valid, expected)
        self.assertEqual(valid.sum(), 16)
        self.assertTrue(np.isnan(shear[~valid]).all())

    def test_research_patch_rejects_invalid_or_nonuniform_inputs(self):
        x, y = np.meshgrid(np.arange(3.), np.arange(3.))
        points = np.column_stack((x.ravel(), y.ravel()))
        moments = np.zeros((9, 3))
        for p, m in ((points, np.zeros((9, 2))), (points, np.full((9, 3), np.nan)),
                     (np.vstack((points, points[:1])), np.zeros((10, 3))),
                     (points*np.array([1, 0]), moments),
                     (points+np.column_stack((points[:, 0] == 2, np.zeros(9))), moments)):
            with self.subTest(points=p), self.assertRaises(ValueError):
                patch_divergence(p, m)

    def test_navier_shear_reference_truncation_is_checked_independently(self):
        x, y = np.meshgrid(np.arange(26.25, 100., 7.5), np.arange(26.25, 160., 7.5))
        points = np.column_stack((x.ravel(), y.ravel()))
        a = navier(points, 120., 180., .2, -1e-7, 1., terms=160)[2]
        b = navier(points, 120., 180., .2, -1e-7, 1., terms=320)[2]
        self.assertLess(np.linalg.norm(a-b)/np.linalg.norm(b), .0002)
        self.assertTrue(np.all(np.linalg.norm(a-b, axis=0)/np.linalg.norm(b, axis=0) < .0002))

    def test_solved_navier_and_strip_fields_in_all_planes_with_signed_and_zero_cases(self):
        for case in CASES:
            baseline = None
            for plane in ("XY", "XZ", "YZ"):
                history = []
                for size in SIZES:
                    samples = solve_case(case, size, plane)
                    service = samples["Service"]
                    for name, factor in FACTORS.items():
                        sample = samples[name]
                        for key in (*METHODS, "moments", "reference"):
                            np.testing.assert_allclose(sample[key], factor*service[key],
                                                       rtol=1e-7, atol=1e-11, equal_nan=True)
                        row = metrics(sample)
                        if name == "Zero":
                            for method in METHODS:
                                self.assertIsNone(row[method]["relative_l2"])
                                self.assertLess(row[method]["max_absolute_error_kip_per_in"], 1e-12)
                    row = metrics(service)
                    history.append(row)
                    self.assertTrue(np.isnan(service["patch_divergence"][~service["valid"]]).all())
                    if case.startswith("strip"):
                        for method in METHODS:
                            self.assertLess(row[method]["relative_l2"], 1e-6)
                if case.endswith("navier"):
                    errors = [row["patch_divergence"]["relative_l2"] for row in history]
                    self.assertTrue(all(b < a for a, b in zip(errors, errors[1:])), errors)
                    self.assertLess(errors[-1], .003)
                    self.assertTrue(all(v < .003 for v in history[-1]["patch_divergence"]["component_relative_l2"]))
                if baseline is not None:
                    for a, b in zip(baseline, history):
                        for method in METHODS:
                            self.assertAlmostEqual(a[method]["relative_l2"], b[method]["relative_l2"], delta=1e-7)
                baseline = history

    def test_research_candidate_does_not_enter_accepted_snapshots_or_exports(self):
        definition = PlateDefinition(mesh_size=30.)
        result = analyze_plate(definition)
        self.assertIsNone(result["shears"])
        row = inspect_plate(result, result["element_names"][0])
        headers, _ = plate_probe_table(result, UNIT_SYSTEMS["imperial"], [row])
        self.assertFalse({"Qx", "Qy"} & row.keys())
        self.assertFalse({"Qx", "Qy"} & FIELDS.keys())
        self.assertFalse(any(header.startswith(("Qx ", "Qy ")) for header in headers))


if __name__ == "__main__":
    unittest.main()
