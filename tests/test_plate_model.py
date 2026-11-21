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
        for changes in ({"version": 6}, {"version": True}, {"nodes": {}}, {"units": "m-N"}):
            with self.assertRaises(ValueError):
                PlateDefinition.from_dict({**PlateDefinition().to_dict(), **changes})
        # Control lines that subdivide a high-aspect rectangle into bounded cells are valid.
        controlled = PlateDefinition(width=100., height=4., mesh_size=100., x_control=[20., 40., 60., 80.])
        controlled.validate()
        with self.assertRaisesRegex(ValueError, "aspect ratio"):
            PlateDefinition(width=100., height=4., mesh_size=100.).validate()

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

    def test_winkler_subgrade_uniform_settlement_uplift_and_point_load_equilibrium(self):
        from pynitegui.qt.plate_model import select_plate_combination
        # A free-edged mat on Winkler subgrade ks under uniform downward pressure q
        # has exact tributary-weighted mean settlement w_mean = q / ks and mean bearing
        # pressure p_mean = q, with pointwise deviations from consistent boundary FER
        # moments within 3% and decreasing under mesh refinement.
        ks = .05
        q_down = .001
        expected_w = q_down / ks
        for family in ("Quad", "Rect"):
            for mode in ("compression_only", "bilateral"):
                definition = PlateDefinition(
                    width=120., height=80., thickness=6., mesh_size=20., plane="XZ",
                    element_type=family, pressure=q_down,
                    edges=dict.fromkeys(("Left", "Right", "Bottom", "Top"), "Free"),
                    subgrade_modulus=ks, subgrade_mode=mode,
                    openings=[dict(name="Hole", x_left=40., y_bott=20., width=20., height=20.)])
                result = analyze_plate(definition)
                fine = analyze_plate(replace(definition, mesh_size=10.))
                area = 120.*80. - 20.*20.
                self.assertAlmostEqual(float(result["tributary_areas"].sum()), area, places=8)
                self.assertAlmostEqual(float(result["tributary_areas"] @ result["displacement"]) / area, expected_w, places=11)
                self.assertAlmostEqual(float(result["tributary_areas"] @ result["nodal_bearing_pressure"]) / area, q_down, places=11)
                if family == "Quad":
                    np.testing.assert_allclose(result["displacement"], expected_w, rtol=1e-9, atol=1e-12)
                    np.testing.assert_allclose(result["nodal_bearing_pressure"], q_down, rtol=1e-9, atol=1e-12)
                    np.testing.assert_allclose(result["moments"], 0., atol=1e-9)
                else:
                    np.testing.assert_allclose(result["displacement"], expected_w, rtol=.03)
                    np.testing.assert_allclose(result["nodal_bearing_pressure"], q_down, rtol=.03)
                    self.assertLess(np.max(np.abs(fine["displacement"] - expected_w)),
                                    np.max(np.abs(result["displacement"] - expected_w)))
                self.assertEqual(result["active_soil_springs"], result["total_soil_springs"])
                self.assertEqual(result["uplift_nodes"], [])
        # Eccentric concentrated point force + moment triggers corner uplift under compression_only
        # while bilateral keeps all springs active.
        eccentric = PlateDefinition(
            width=120., height=120., thickness=6., mesh_size=30., plane="XZ",
            pressure=0., load_case="D",
            edges=dict.fromkeys(("Left", "Right", "Bottom", "Top"), "Free"),
            subgrade_modulus=.02, subgrade_mode="compression_only",
            point_loads=[
                dict(case="D", x=30., y=30., direction="FY", magnitude=-12.),
                dict(case="D", x=30., y=30., direction="MZ", magnitude=240.),
            ],
            combinations={"Zero": {"D": 0.}})
        comp = analyze_plate(eccentric)
        bilat = analyze_plate(replace(eccentric, subgrade_mode="bilateral"))
        self.assertLess(comp["active_soil_springs"], comp["total_soil_springs"])
        self.assertGreater(len(comp["uplift_nodes"]), 0)
        self.assertEqual(bilat["active_soil_springs"], bilat["total_soil_springs"])
        self.assertGreater(comp["nodal_bearing_pressure"].max(), bilat["nodal_bearing_pressure"].max())
        self.assertTrue((comp["nodal_bearing_pressure"] >= -1e-12).all())
        self.assertLess(bilat["nodal_bearing_pressure"].min(), 0.)
        zero = select_plate_combination(comp, "Zero")
        np.testing.assert_allclose(zero["displacement"], 0., atol=1e-12)
        np.testing.assert_allclose(zero["nodal_bearing_pressure"], 0., atol=1e-12)
        # Net upward load on a free-edged compression-only mat lifts off completely and fails closed.
        uplift = replace(eccentric, point_loads=[dict(case="D", x=60., y=60., direction="FY", magnitude=10.)])
        with self.assertRaisesRegex(ValueError, "Unstable plate/subgrade supports"):
            analyze_plate(uplift)

    def test_subgrade_and_point_loads_validation_and_v4_migration(self):
        base = PlateDefinition(
            plane="XZ", width=120., height=80., mesh_size=20.,
            openings=[dict(name="Hole", x_left=40., y_bott=20., width=20., height=20.)])
        for bad in (
            {"subgrade_modulus": -0.1},
            {"subgrade_modulus": True},
            {"subgrade_modulus": 1e7},
            {"subgrade_mode": "tension_only"},
            {"point_loads": "not_a_list"},
            {"point_loads": [dict(case="Missing", x=10., y=10., direction="FY", magnitude=-5.)]},
            {"point_loads": [dict(case="Case 1", x=10., y=10., direction="FZ", magnitude=-5.)]},
            {"point_loads": [dict(case="Case 1", x=10., y=10., direction="MY", magnitude=-5.)]},
            {"point_loads": [dict(case="Case 1", x=-1., y=10., direction="FY", magnitude=-5.)]},
            {"point_loads": [dict(case="Case 1", x=50., y=30., direction="FY", magnitude=-5.)]},
            {"point_loads": [dict(case="Case 1", x=10., y=10., direction="FY", magnitude=float("nan"))]},
            {"point_loads": [dict(case="Case 1", x=10., y=10., direction="FY")]},
        ):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                replace(base, **bad).validate()
        # Version 4 files migrate cleanly to version 5 defaults.
        v4 = base.to_dict()
        v4["version"] = 4
        for key in ("subgrade_modulus", "subgrade_mode", "point_loads"):
            v4.pop(key)
        self.assertEqual(PlateDefinition.from_dict(v4), base)
        # Renaming a load case updates point_loads case references.
        loaded = replace(base, point_loads=[dict(case="Case 1", x=17., y=23., direction="FY", magnitude=-5.)])
        loaded.rename_case("Case 1", "Permanent")
        self.assertEqual(loaded.point_loads[0]["case"], "Permanent")
        loaded.validate()


if __name__ == "__main__":
    unittest.main()
