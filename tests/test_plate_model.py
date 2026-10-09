"""Independent transverse plate checks and bounded mesh/persistence contracts."""
from dataclasses import replace
import math
import unittest

import numpy as np

from pynitegui.qt.plate_model import PlateDefinition, PLANES, build_plate, plate_geometry, analyze_plate
from pynitegui.qt.model import Material


class PlateModelTests(unittest.TestCase):
    def test_roundtrip_and_regeneration(self):
        definition = PlateDefinition()
        self.assertEqual(PlateDefinition.from_dict(definition.to_dict()), definition)
        coarse = build_plate(definition)
        fine = build_plate(replace(definition, mesh_size=7.5))
        self.assertEqual(len(coarse.quads), 64)
        self.assertEqual(len(fine.quads), 256)
        self.assertEqual(definition.edges, dict.fromkeys(definition.edges, "Simply supported"))
        self.assertEqual(definition.to_dict(), PlateDefinition().to_dict())
        for model in (coarse, fine):
            self.assertTrue(all(node.support_DZ for node in model.nodes.values() if node.X == 0))

    def test_mesh_planes_and_local_winding(self):
        for plane in PLANES:
            definition = PlateDefinition(plane=plane, width=60, height=90, mesh_size=30)
            model = build_plate(definition)
            _, points, cells = plate_geometry(model, definition)
            self.assertEqual(len(cells), 6)
            np.testing.assert_allclose(points.max(axis=0), [60, 90])
            for quad in model.quads.values():
                np.testing.assert_allclose(quad.T()[2, :3], definition.normal)

    def test_invalid_inputs(self):
        for changes in ({"mesh_size": 0}, {"mesh_size": .001}, {"pressure": math.nan},
                        {"thickness": -1}, {"width": True}, {"plane": "ZX"},
                        {"unit_system": "invalid"}, {"load_factor": math.inf},
                        {"edges": {}}, {"load_case": ""}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                replace(PlateDefinition(), **changes).validate()
        for changes in ({"version": 2}, {"version": True}, {"nodes": {}}, {"units": "m-N"}):
            with self.assertRaises(ValueError):
                PlateDefinition.from_dict({**PlateDefinition().to_dict(), **changes})

    def test_unstable_supports_rejected(self):
        for edges in (dict.fromkeys(PlateDefinition().edges, "Free"),
                      {**dict.fromkeys(PlateDefinition().edges, "Free"), "Left": "Simply supported"}):
            with self.assertRaisesRegex(ValueError, "Unstable"):
                analyze_plate(PlateDefinition(edges=edges, mesh_size=30))

    def test_navier_square_plate_convergence_and_equilibrium(self):
        definition = PlateDefinition(mesh_size=30)
        coarse = analyze_plate(definition)
        fine = analyze_plate(replace(definition, mesh_size=15))
        # Navier sine-series solution for a uniformly loaded simply supported
        # square: w_center = 16*q*a^4/(pi^6*D) * alternating odd-term sum.
        series = sum(math.sin(m*math.pi/2)*math.sin(n*math.pi/2) /
                     (m*n*(m*m+n*n)**2) for m in range(1, 80, 2) for n in range(1, 80, 2))
        rigidity = definition.material.E*definition.thickness**3/(12*(1-definition.material.nu**2))
        expected = 16*definition.pressure*definition.width**4*series/(math.pi**6*rigidity)
        coarse_peak, fine_peak = min(coarse["displacement"]), min(fine["displacement"])
        self.assertLess(abs(fine_peak-expected), abs(coarse_peak-expected))
        self.assertAlmostEqual(fine_peak/expected, 1, delta=.025)
        self.assertAlmostEqual(fine["reactions"].sum(), -fine["applied"], places=7)
        self.assertTrue(np.isfinite(fine["moments"]).all())

    def test_plane_invariance_pressure_sign_and_load_factor(self):
        baseline = analyze_plate(PlateDefinition(mesh_size=30))
        for plane in PLANES:
            result = analyze_plate(PlateDefinition(mesh_size=30, plane=plane, load_factor=-2))
            np.testing.assert_allclose(result["displacement"], -2*baseline["displacement"], atol=1e-9)
            np.testing.assert_allclose(result["reactions"], -2*baseline["reactions"], atol=1e-9)

    def test_clamped_edge_stable_and_stiffer(self):
        simple = analyze_plate(PlateDefinition(mesh_size=30))
        clamped = analyze_plate(PlateDefinition(mesh_size=30, edges=dict.fromkeys(PlateDefinition().edges, "Clamped")))
        self.assertLess(max(abs(clamped["displacement"])), max(abs(simple["displacement"])))
        cantilever = analyze_plate(PlateDefinition(mesh_size=30,
            edges={**dict.fromkeys(PlateDefinition().edges, "Free"), "Left": "Clamped"}))
        self.assertAlmostEqual(cantilever["reactions"].sum(), -cantilever["applied"], places=6)

    def test_cantilever_strip_closed_form(self):
        definition = PlateDefinition(width=120, height=60, mesh_size=15,
            material=Material("Benchmark", E=3600, nu=0, rho=0),
            edges={"Left": "Clamped", "Right": "Free", "Bottom": "Free", "Top": "Free"})
        result = analyze_plate(definition)
        rigidity = definition.material.E*definition.thickness**3/12
        expected_tip = definition.pressure*definition.width**4/(8*rigidity)
        self.assertAlmostEqual(min(result["displacement"])/expected_tip, 1, delta=.01)
        centres = result["points"][result["cells"]].mean(axis=1)
        expected_moment = -definition.pressure*(definition.width-centres[:, 0])**2/2
        np.testing.assert_allclose(result["moments"][:, 0], expected_moment, rtol=.01, atol=.0003)
        np.testing.assert_allclose(result["moments"][:, 1:], 0, atol=1e-10)


if __name__ == "__main__":
    unittest.main()
