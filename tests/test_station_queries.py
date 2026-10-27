"""Independent governing-location benchmarks and retained query UI contracts."""
import contextlib
import csv
import io
import math
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYNITEGUI_NO_WEBENGINE", "1")
import numpy as np
from numpy.polynomial import Polynomial
from PySide6.QtWidgets import QApplication, QWidget
from pynitegui.qt.analysis import analyze
from pynitegui.qt.envelopes import EnvelopeWidget
from pynitegui.qt.geometry_tools import plan_generator
from pynitegui.qt.model import Project, Load
from pynitegui.qt.spatial_model import SpatialProject, SpatialLoad
from pynitegui.qt.station_queries import governing_stations, member_candidates, segment_candidates, export_station_csv


def solve(project):
    with contextlib.redirect_stdout(io.StringIO()):
        return analyze(project)


def triangle(spatial=False):
    p = SpatialProject() if spatial else Project()
    p.add_member((0, 0, 0) if spatial else (0, 0), (120, 0, 0) if spatial else (120, 0))
    if spatial:
        a, b = p.nodes.values()
        a.support = "custom"
        a.restraint_x = a.restraint_y = a.restraint_z = a.restraint_rx = True
        b.support = "custom"
        b.restraint_y = b.restraint_z = True
    else:
        p.nodes["N1"].support, p.nodes["N2"].support = "pin", "roller"
    cls = SpatialLoad if spatial else Load
    p.loads["L1"] = cls("L1", "M1", "FY", 0., 0., "distributed", -.01, 1.)
    return p


class StationQueryTests(unittest.TestCase):
    def test_non_grid_triangular_moment_and_deflection_locations_2d_and_3d(self):
        for spatial in (False, True):
            p = triangle(spatial)
            result = solve(p)
            rows = governing_stations(p, result, ("Service",), ("M1",), "Mz")
            extreme = rows[-1]
            self.assertAlmostEqual(extreme["station"], 120/math.sqrt(3), places=7)
            self.assertAlmostEqual(abs(extreme["value"]), .01*120**2/(9*math.sqrt(3)), places=8)
            self.assertEqual(extreme["side"], "interior")
            dy = governing_stations(p, result, ("Service",), ("M1",), "dy")[-1]
            t = math.sqrt(1-2*math.sqrt(30)/15)
            self.assertAlmostEqual(dy["station"], 120*t, places=6)
            material, section = p.materials[p.default_material], p.sections[p.default_section]
            x = 120*t
            expected = .01/(material.E*section.Iz)*(-x**5/(120*120)+120*x**3/36-7*120**3*x/360)
            self.assertAlmostEqual(dy["value"], expected, places=10)

    def test_spatial_transverse_z_and_torsion_components_have_correct_locations(self):
        p = triangle(True)
        p.loads["L1"].direction = "FZ"
        r = solve(p)
        moment = governing_stations(p, r, ("Service",), ("M1",), "My")[-1]
        self.assertAlmostEqual(moment["station"], 120/math.sqrt(3), places=7)
        self.assertAlmostEqual(abs(moment["value"]), .01*120**2/(9*math.sqrt(3)), places=8)
        deflection = governing_stations(p, r, ("Service",), ("M1",), "dz")[-1]
        self.assertAlmostEqual(deflection["station"], 120*math.sqrt(1-2*math.sqrt(30)/15), places=6)
        shear = governing_stations(p, r, ("Service",), ("M1",), "Vz")[-1]
        self.assertAlmostEqual(abs(shear["value"]), .01*120/3, places=9)
        p.loads["L2"] = SpatialLoad("L2", "M1", "Mx", 5., .31)
        r = solve(p)
        torsion = governing_stations(p, r, ("Service",), ("M1",), "T")[-1]
        self.assertAlmostEqual(abs(torsion["value"]), 5., places=9)
        points = member_candidates(p, r, "M1", "T", "Service")
        sides = {side: value for x, side, value in points if abs(x-37.2) < 1e-8}
        self.assertAlmostEqual(abs(sides["left"]-sides["right"]), 5., places=9)

    def test_both_jump_sides_exact_limits_and_governing_combination_scope(self):
        p = triangle()
        p.loads = {"L1": Load("L1", "M1", "FY", -5., .37), "L2": Load("L2", "M1", "MZ", 10., .37)}
        p.set_combination("Double", {"Case 1": 2.})
        result = solve(p)
        candidates = member_candidates(p, result, "M1", "Mz", "Service")
        at_jump = {side: value for station, side, value in candidates if abs(station-44.4) < 1e-8 and side in ("left", "right")}
        self.assertEqual(set(at_jump), {"left", "right"})
        self.assertAlmostEqual(abs(at_jump["left"]-at_jump["right"]), 10., places=8)
        rows = governing_stations(p, result, ("Service", "Double"), ("M1",), "Mz")
        self.assertEqual(rows[-1]["combination"], "Double")
        self.assertAlmostEqual(rows[-1]["station"], 44.4, places=8)
        self.assertEqual(rows[-1]["side"], "left")
        before = result.snapshot_id
        for members, component in (([], "Mz"), (["unknown"], "Mz"), (["M1"], "unknown")):
            with self.assertRaises(ValueError):
                governing_stations(p, result, ("Service",), members, component)
        p.nodes["N2"].x += 1.
        with self.assertRaisesRegex(ValueError, "snapshot"):
            governing_stations(p, result, ("Service",), ("M1",), "Mz")
        self.assertEqual(result.snapshot_id, before)

    def test_multiple_interior_roots_and_rational_pdelta_contract(self):
        polynomial = Polynomial.fromroots([.13, .44, .83]).integ()
        candidates = segment_candidates(lambda x: polynomial(x/120.), 120.)
        for location in (.13, .44, .83):
            self.assertTrue(any(abs(x-120*location) < 1e-7 for x, value in candidates))
        # Independent closed-form extremum of f(t)=t(1-t)/(1+t²).
        rational = segment_candidates(lambda x: (x/120)*(1-x/120)/(1+(x/120)**2), 120., Polynomial([1., 0., 1.]))
        self.assertTrue(any(abs(x-120*(math.sqrt(2)-1)) < 1e-7 for x, value in rational))
        with self.assertRaisesRegex(ValueError, "singularity"):
            segment_candidates(lambda x: x, 1., Polynomial([1., 0., -4.]))
        with self.assertRaisesRegex(ValueError, "singularity"):
            segment_candidates(lambda x: x, 1., Polynomial([1., 0., -1e14]))
        with self.assertRaisesRegex(ValueError, "contract"):
            segment_candidates(lambda x: math.sin(x*30), 1.)

    def test_pdelta_cantilever_queries_agree_with_independent_dense_point_evaluation(self):
        p = SpatialProject()
        p.add_member((0, 0, 0), (0, 120, 0))
        p.nodes["N1"].support = "fixed"
        p.loads["L1"] = SpatialLoad("L1", "N2", "FY", -20.)
        p.loads["L2"] = SpatialLoad("L2", "N2", "FX", 1.)
        p.analysis_method = "p_delta"
        r = solve(p)
        for component, direction, method in (("Mz", "Mz", "moment"), ("dy", "dy", "deflection")):
            rows = governing_stations(p, r, ("Service",), ("M1",), component)
            function = getattr(r.solver.members["M1"], method)
            values = [function(direction, x, "Service") for x in np.linspace(0, 120, 1001)]
            self.assertAlmostEqual(abs(rows[-1]["value"]), max(map(abs, values)), places=7)

    def test_submember_limits_and_truss_queries(self):
        p = plan_generator(Project(), "beam", [120., 120.]).definition
        # Replace two explicit spans by one physical member with an internal joint.
        p.members["M1"].end = "N3"
        del p.members["M2"]
        p.loads["L1"] = Load("L1", "M1", "FY", -.01, 0., "distributed", -.01, 1.)
        # Exercise the engine adapter's physical subdivision, normally rejected
        # by editor preflight in favour of explicit joints.
        with patch.object(p, "analysis_topology_issues", return_value=[]):
            r = solve(p)
        rows = governing_stations(p, r, ("Service",), ("M1",), "Mz")
        self.assertAlmostEqual(abs(rows[-1]["value"]), 18., places=8)
        self.assertAlmostEqual(rows[-1]["station"], 120., places=8)
        from pynitegui.qt.examples import example_project
        for key in ("truss", "3d_official_truss"):
            p = example_project(key)
            r = solve(p)
            rows = governing_stations(p, r, tuple(r.solver.load_combos), tuple(p.members), "N")
            self.assertEqual(len(rows), 3)
            self.assertTrue(all(math.isfinite(row["value"]) for row in rows))
            motion = governing_stations(p, r, tuple(r.solver.load_combos), tuple(p.members), "dy")
            self.assertTrue(all(math.isfinite(row["value"]) for row in motion))

    def test_csv_includes_units_snapshot_filters_method_and_formula_safe_names(self):
        p = triangle()
        r = solve(p)
        rows = governing_stations(p, r, ("Service",), ("M1",), "Mz")
        p.unit_system = "si"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/"stations.csv"
            export_station_csv(path, p, r, ("Service",), rows, {"scope": "all"}, "=source")
            with path.open(newline="") as stream:
                data = list(csv.DictReader(stream))
            self.assertEqual(data[0]["Analysis ID"], r.snapshot_id)
            self.assertEqual(data[0]["Source"], "'=source")
            self.assertEqual(data[0]["Station unit"], "m")
            self.assertIn("one-sided", data[0]["Query method"])
            self.assertAlmostEqual(float(data[-1]["Station from start"]), p.units.to_display(rows[-1]["station"], "length"))


class StationQueryUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_search_navigation_and_filter_changes_invalidate_export(self):
        p = triangle()
        r = solve(p)
        host = QWidget()
        w = EnvelopeWidget(host, p, r, "Test")
        query = w.station_query
        query.search()
        self.assertFalse(query.rows)
        w.filters.component.setCurrentIndex(w.filters.component.findData("Member:Mz"))
        query.search()
        self.assertEqual(len(query.rows), 3, query.message.text())
        query.navigate(2)
        self.assertEqual(w.member.currentText(), "M1")
        self.assertAlmostEqual(w.inspection_x, 120/math.sqrt(3), places=7)
        self.assertEqual(w.views.currentIndex(), 2)
        self.assertTrue(query.export_button.isEnabled())
        w.filters.scope.setCurrentIndex(w.filters.scope.findData("selection"))
        self.assertFalse(query.rows)
        self.assertFalse(query.export_button.isEnabled())
        query.search()
        self.assertFalse(query.rows)
        host.deleteLater()
        self.app.processEvents()
