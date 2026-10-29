"""Snapshot local probes, independent Rect polynomials and real element contracts."""
import contextlib
import csv
import io
import pickle
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

import numpy as np

from pynitegui.qt.plate_model import PlateDefinition, analyze_plate, build_plate, select_plate_combination
from pynitegui.qt.plate_inspection import inspect_plate, plate_probe_table, write_plate_probes
from pynitegui.qt.plate_recovery import rectangular_coefficients, polynomial_resultants
from pynitegui.qt.units import UNIT_SYSTEMS


def solve(definition):
    with contextlib.redirect_stdout(io.StringIO()):
        return analyze_plate(definition)


class PlateInspectionTests(unittest.TestCase):
    def test_rect_polynomial_probes_reproduce_independent_derivatives_off_centre(self):
        a, b, E, nu, t = 7., 11., 3200., .3, .8
        D = E*t**3/(12*(1-nu**2))
        nodal = np.zeros((4, 6))
        # w=x³y+xy³+x²+2y²: deliberately not bilinear Mxy.
        for row, (x, y) in enumerate(((0, 0), (a, 0), (a, b), (0, b))):
            nodal[row, [2, 3, 4]] = [x**3*y+x*y**3+x*x+2*y*y,
                x**3+3*x*y*y+4*y, -(3*x*x*y+y**3+2*x)]
        element = SimpleNamespace(width=lambda: a, height=lambda: b, d=lambda combo: nodal.reshape(24, 1))
        coefficients = rectangular_coefficients(element)
        for xi, eta in ((-.7, .3), (.2, -.4), (-1., 1.), (1., -1.), (0., 0.)):
            x, y = (xi+1)*a/2, (eta+1)*b/2
            xx, yy, xy = 6*x*y+2, 6*x*y+4, 3*x*x+3*y*y
            moments, shears = polynomial_resultants(coefficients, a, b, E, nu, t, xi, eta)
            np.testing.assert_allclose(moments, -D*np.array((xx+nu*yy, yy+nu*xx, (1-nu)*xy)), rtol=1e-12)
            np.testing.assert_allclose(shears, -D*np.array((12*y, 12*x)), rtol=1e-12, atol=1e-10)

    def test_cached_probes_match_solved_elements_in_every_plane_with_holes_and_factors(self):
        for family in ("Rect", "Quad"):
            for plane in ("XY", "XZ", "YZ"):
                d = PlateDefinition(element_type=family, plane=plane, width=120., height=80., mesh_size=20.,
                    origin=[17., -31., 49.], pressure=-1e-7, thickness=.6, node_start=25, element_start=50,
                    openings=[dict(name="Hole", x_left=40., y_bott=20., width=20., height=20.)],
                    combinations={"Reversed": {"Case 1": -2.}, "Zero": {"Case 1": 0.}})
                result = pickle.loads(pickle.dumps(solve(d)))
                model = build_plate(d)
                with contextlib.redirect_stdout(io.StringIO()):
                    model.analyze_linear()
                baseline = None
                for combination in d.load_combinations:
                    selected = select_plate_combination(result, combination)
                    name = result["element_names"][3]
                    element = (model.plates if family == "Rect" else model.quads)[name]
                    for xi, eta in ((0., 0.), (.63, -.27), (-1., 1.), (1., -1.)):
                        with self.subTest(family=family, plane=plane, combination=combination, xi=xi, eta=eta):
                            row = inspect_plate(selected, name, xi, eta)
                            if family == "Quad":
                                expected = element.moment(xi, eta, combo_name=combination).ravel()
                                self.assertNotIn("Qx", row)
                                self.assertNotIn("Qy", row)
                                self.assertIsNone(selected["shears"])
                            else:
                                expected, shear = polynomial_resultants(rectangular_coefficients(element, combination),
                                    element.width(), element.height(), d.material.E, d.material.nu, d.thickness, xi, eta)
                                np.testing.assert_allclose([row["Qx"], row["Qy"]], shear, rtol=1e-10, atol=1e-11)
                            np.testing.assert_allclose([row[k] for k in ("Mx", "My", "Mxy")], expected, rtol=1e-10, atol=1e-11)
                            np.testing.assert_allclose(np.cross(*np.asarray(row["axes"])[:2]), d.normal)
                            reconstructed = np.array(d.origin)+np.asarray(row["axes"])[:2].T @ row["position"]
                            np.testing.assert_allclose(row["global_position"], reconstructed)
                    centres = np.array([[inspect_plate(selected, n)[k] for k in ("Mx", "My", "Mxy")] for n in result["element_names"]])
                    np.testing.assert_allclose(centres, selected["moments"], rtol=1e-10, atol=1e-11)
                    if baseline is None:
                        baseline = centres
                    else:
                        factor = -2 if combination == "Reversed" else 0
                        np.testing.assert_allclose(centres, factor*baseline, atol=1e-10)
                self.assertTrue(result["element_names"][0].endswith("50"))

    def test_invalid_selection_coordinates_and_nonfinite_recovery_fail_closed(self):
        result = solve(PlateDefinition(mesh_size=60.))
        name = result["element_names"][0]
        for value in (True, None, "0", complex(0), float("nan"), float("inf"), -1.001, 1.001):
            for xi, eta in ((value, 0), (0, value)):
                with self.assertRaises(ValueError):
                    inspect_plate(result, name, xi, eta)
        with self.assertRaisesRegex(ValueError, "belonging"):
            inspect_plate(result, "Missing")
        result["inspection"][0, 0, 0] = np.nan
        with self.assertRaisesRegex(ValueError, "nonfinite"):
            inspect_plate(result, name)

    def test_centre_and_probe_csv_keep_units_axes_and_selected_snapshot_identity(self):
        for family in ("Rect", "Quad"):
            result = solve(PlateDefinition(element_type=family, plane="YZ", origin=[17., -31., 49.],
                mesh_size=60., combinations={"Reversed": {"Case 1": -2.}}))
            result = select_plate_combination(result, "Reversed")
            probe = inspect_plate(result, result["element_names"][0], .6, -.4)
            for unit_name in ("imperial", "si", "si_mm", "imperial_ft"):
                units = UNIT_SYSTEMS[unit_name]
                headers, rows = plate_probe_table(result, units, [probe])
                self.assertAlmostEqual(rows[0][8], probe["Mx"]*units.force_factor)
                self.assertIn(f"Mx ({units.moment}/{units.length})", headers)
                self.assertEqual(any(h.startswith("Qx (") for h in headers), family == "Rect")
                with TemporaryDirectory() as directory:
                    for single in (False, True):
                        path = Path(directory)/"results.csv"
                        write_plate_probes(path, result, units, [probe] if single else None)
                        with path.open(newline="") as stream:
                            data = list(csv.DictReader(stream))
                        self.assertEqual(len(data), 1 if single else len(result["element_names"]))
                        self.assertEqual(data[0]["Combination"], "Reversed")
                        self.assertEqual(data[0]["Snapshot"], result["snapshot_id"])
                        self.assertEqual(data[0]["Model signature"], result["model_signature"])
                        # Vector sign spelling is immaterial; its values are not.
                        import ast
                        np.testing.assert_allclose(ast.literal_eval(data[0]["Local z global vector"]), [-1, 0, 0])
                        if single:
                            self.assertEqual(float(data[0]["xi"]), .6)
                            self.assertEqual(float(data[0]["eta"]), -.4)


if __name__ == "__main__":
    unittest.main()
