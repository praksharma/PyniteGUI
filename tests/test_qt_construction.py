"""Explicit connections preview exact candidates and preserve engineering data."""
import contextlib
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
from PySide6.QtCore import QPointF
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox
from pynitegui.qt.analysis import analyze
from pynitegui.qt.app import MainWindow
from pynitegui.qt.construction import ConnectionPreview, coordinates, plan_connection
from pynitegui.qt.equilibrium import check_equilibrium
from pynitegui.qt.model import Load, Project
from pynitegui.qt.spatial_model import SpatialLoad, SpatialProject
from pynitegui.qt.spatial_results import member_axes


def perpendicular(spatial=False):
    project = SpatialProject() if spatial else Project()
    if spatial:
        project.add_member((20, 30, 40), (140, 150, 160))
        project.add_member((20, 30, 40), (110, 60, 100))
        project.members["M1"].roll = 37
    else:
        project.add_member((0, 0), (120, 0))
        project.add_member((0, 0), (60, 60))
    project.nodes["N1"].support = "fixed"
    return project


def midpoint_project(spatial=False):
    project = SpatialProject() if spatial else Project()
    points = ((0, 0, 0), (120, 0, 60), (0, 60, 60), (120, 60, 120)) if spatial else ((0, 0), (120, 0), (0, 60), (120, 60))
    project.add_member(points[0], points[1])
    project.add_member(points[2], points[3])
    project.add_member(points[0], points[2])
    project.nodes["N1"].support = "fixed"
    project.nodes["N3"].support = "fixed"
    cls = SpatialLoad if spatial else Load
    project.loads["L1"] = cls("L1", "N4", "FY", -2)
    return project


def solve(project):
    with contextlib.redirect_stdout(io.StringIO()):
        return analyze(project)


class ConstructionPlanTests(unittest.TestCase):
    def test_full_xyz_perpendicular_and_planar_projection_are_orthogonal(self):
        for spatial in (False, True):
            with self.subTest(spatial=spatial):
                project = perpendicular(spatial)
                before = project.to_dict()
                plan = plan_connection(project, "perpendicular", [("nodes", "N3"), ("members", "M1")])
                a, b = np.array(coordinates(project, "N1")), np.array(coordinates(project, "N2"))
                start, foot = map(np.array, plan.endpoints)
                self.assertAlmostEqual(float((foot-start) @ (b-a)), 0., places=9)
                self.assertAlmostEqual(math.dist(foot, (a+b)/2), 0., places=9)
                self.assertEqual(len(plan.definition.members), 4)
                self.assertEqual(project.to_dict(), before)
                self.assertFalse(plan.definition.analysis_topology_issues())
                self.assertEqual(plan.splits, {"M1": ["M1", "M3"]})
                self.assertEqual(plan.connector, "M4")

    def test_load_resultants_partial_profiles_point_stations_and_cases(self):
        project = perpendicular()
        project.set_load_case("Gravity", "Case 1")
        project.loads["L1"] = Load("L1", "M1", "FY", -.02, .2, "distributed", -.04, .8, case="Gravity")
        project.loads["L2"] = Load("L2", "N3", "FY", -2, case="Gravity")
        project.loads["L3"] = Load("L3", "M1", "MZ", 5, .5, case="Gravity")
        project.loads["L4"] = Load("L4", "M1", "Local y", -1, .5, case="Gravity")
        project.set_combination("Double", {"Gravity": 2})
        plan = plan_connection(project, "perpendicular", [("nodes", "N3"), ("members", "M1")])
        candidate = plan.definition
        foot = candidate.members[plan.connector].end
        self.assertEqual(candidate.loads["L3"].target, foot)
        self.assertEqual(candidate.loads["L4"].target, foot)
        pieces = [load for load in candidate.loads.values() if load.kind == "distributed"]
        self.assertEqual(len(pieces), 2)
        self.assertAlmostEqual(pieces[0].end_magnitude, -.03)
        self.assertAlmostEqual(pieces[1].magnitude, -.03)
        self.assertTrue(all(load.case == "Gravity" for load in candidate.loads.values()))
        result = solve(candidate)
        for combo, factor in (("Service", 1), ("Double", 2)):
            rows = check_equilibrium(candidate, result.for_combination(combo)).rows
            self.assertAlmostEqual(rows[1].applied, -5.16*factor)
            self.assertAlmostEqual(rows[2].applied, -313.24*factor)
            self.assertTrue(all(row.passed for row in rows))

    def test_midpoint_connection_stiffens_loaded_frame_and_uses_shared_joints(self):
        for spatial in (False, True):
            with self.subTest(spatial=spatial):
                project = midpoint_project(spatial)
                original = solve(project)
                plan = plan_connection(project, "midpoints", [("members", "M1"), ("members", "M2")])
                result = solve(plan.definition)
                self.assertLess(abs(result.displacements["N4"][1]), abs(original.displacements["N4"][1]))
                self.assertTrue(check_equilibrium(plan.definition, result).passed)
                self.assertFalse(plan.definition.analysis_topology_issues())
                self.assertEqual(len(plan.definition.members), 6)
                connection = plan.definition.members[plan.connector]
                for original_name, endpoint in zip(("M1", "M2"), (connection.start, connection.end)):
                    names = plan.splits[original_name]
                    self.assertEqual(plan.definition.members[names[0]].end, endpoint)
                    self.assertEqual(plan.definition.members[names[1]].start, endpoint)

    def test_existing_joint_support_springs_assignments_roll_and_outer_releases(self):
        project = perpendicular()
        joint = project.node_at(60, 0)
        project.nodes[joint].spring_y = 100
        project.loads["L1"] = Load("L1", joint, "FY", -3)
        project.members["M1"].release_end = True
        original_joint = project.nodes[joint]
        plan = plan_connection(project, "perpendicular", [("nodes", "N3"), ("members", "M1")])
        self.assertEqual(plan.definition.nodes[joint], original_joint)
        self.assertEqual(len(plan.definition.nodes), len(project.nodes))
        left, right = (plan.definition.members[name] for name in plan.splits["M1"])
        self.assertFalse(left.release_end)
        self.assertTrue(right.release_end)
        spatial = perpendicular(True)
        axes = member_axes(spatial, "M1")
        spatial.loads["L1"] = SpatialLoad("L1", "M1", "Fy", -2, .5)
        spatial.loads["L2"] = SpatialLoad("L2", "M1", "Mz", 3, .5)
        plan = plan_connection(spatial, "perpendicular", [("nodes", "N3"), ("members", "M1")])
        for name in plan.splits["M1"]:
            self.assertEqual(plan.definition.members[name].roll, 37)
            np.testing.assert_allclose(member_axes(plan.definition, name), axes, atol=1e-12)
        for name in ("L1", "L2"):
            self.assertEqual((plan.definition.loads[name].target, plan.definition.loads[name].position), ("M1", 1))
        self.assertEqual(plan.definition.members[plan.connector].roll, 0)

    def test_endpoint_foot_skips_split_and_selfweight_accounts_for_new_length(self):
        project = Project()
        project.add_member((0, 0), (120, 0))
        node = project.node_at(0, 60)
        project.self_weight_case = "Case 1"
        before_weight = project.self_weight_total()
        plan = plan_connection(project, "perpendicular", [("nodes", node), ("members", "M1")])
        self.assertEqual(plan.splits["M1"], ["M1"])
        self.assertEqual(len(plan.definition.nodes), 3)
        member = plan.definition.members[plan.connector]
        added = project.materials[member.material].rho*project.sections[member.section].A*60
        self.assertAlmostEqual(plan.definition.self_weight_total(), before_weight+added)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/"connection.json"
            plan.definition.save(path)
            self.assertEqual(Project.open(path).to_dict(), plan.definition.to_dict())

    def test_outside_coincident_wrong_selection_duplicate_and_overlapping_are_atomic(self):
        project = perpendicular()
        original = project.to_dict()
        for operation, selections in (("perpendicular", []), ("midpoints", [("members", "M1")]),
                                      ("perpendicular", [("nodes", "N1"), ("members", "M1")]),
                                      ("midpoints", [("members", "M1"), ("loads", "missing")])):
            with self.assertRaises(ValueError):
                plan_connection(project, operation, selections)
            self.assertEqual(project.to_dict(), original)
        outside = project.node_at(180, 60)
        with self.assertRaisesRegex(ValueError, "outside"):
            plan_connection(project, "perpendicular", [("nodes", outside), ("members", "M1")])
        project.add_member((60, 60), (60, 0))
        original = project.to_dict()
        with self.assertRaisesRegex(ValueError, "already connects"):
            plan_connection(project, "perpendicular", [("nodes", "N3"), ("members", "M1")])
        self.assertEqual(project.to_dict(), original)

    def test_unrelated_crossings_and_interior_nodes_require_explicit_connection(self):
        project = perpendicular()
        project.add_member((30, 30), (90, 30))
        original = project.to_dict()
        with self.assertRaisesRegex(ValueError, "crosses or meets"):
            plan_connection(project, "perpendicular", [("nodes", "N3"), ("members", "M1")])
        self.assertEqual(project.to_dict(), original)
        project = perpendicular()
        project.node_at(60, 30)
        with self.assertRaisesRegex(ValueError, "lies inside"):
            plan_connection(project, "perpendicular", [("nodes", "N3"), ("members", "M1")])
        project = Project()
        project.add_member((0, 0), (120, 0))
        project.add_member((120, 0), (240, 0))
        with self.assertRaisesRegex(ValueError, "overlap"):
            plan_connection(project, "midpoints", [("members", "M1"), ("members", "M2")])


class ConstructionWindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = MainWindow()
        self.window.load_project(perpendicular())
        self.window.select_many([("nodes", "N3"), ("members", "M1")])

    def tearDown(self):
        self.window.saved = self.window.project.to_dict()
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()

    def test_preview_cancel_and_apply_are_one_undoable_edit(self):
        window = self.window
        result = solve(window.project)
        window.analysis_revision = window.revision
        window.analysis_finished(result, "")
        snapshot = window.result
        original = window.project.to_dict()
        revision, count = window.revision, window.undo.count()
        with patch.object(ConnectionPreview, "exec", return_value=QDialog.DialogCode.Rejected):
            window.construct_connection("perpendicular")
        self.assertEqual(window.project.to_dict(), original)
        self.assertEqual(window.revision, revision)
        self.assertIs(window.result, snapshot)
        with patch.object(ConnectionPreview, "exec", return_value=QDialog.DialogCode.Accepted):
            window.construct_connection("perpendicular")
        candidate = window.project.to_dict()
        self.assertEqual(window.undo.count(), count+1)
        self.assertEqual(window.selected, ("members", "M4"))
        self.assertIsNone(window.result)
        self.assertFalse(window.diagrams_action.isEnabled())
        window.undo.undo()
        self.assertEqual(window.project.to_dict(), original)
        window.undo.redo()
        self.assertEqual(window.project.to_dict(), candidate)

    def test_stale_preview_never_overwrites_intervening_edit(self):
        window = self.window
        def accept(dialog):
            window.edit("Intervening edit", lambda project: setattr(project.nodes["N2"], "x", 140))
            return QDialog.DialogCode.Accepted
        with patch.object(ConnectionPreview, "exec", accept), patch.object(QMessageBox, "warning") as warning:
            window.construct_connection("perpendicular")
        self.assertIn("model changed", warning.call_args.args[2])
        self.assertEqual(window.project.nodes["N2"].x, 140)
        self.assertEqual(len(window.project.members), 2)

    def test_spatial_preview_projections_and_midpoint_application(self):
        window = self.window
        project = midpoint_project(True)
        plan = plan_connection(project, "midpoints", [("members", "M1"), ("members", "M2")])
        dialog = ConnectionPreview(window, project, plan, "Midpoint preview")
        dialog.show()
        self.app.processEvents()
        self.app.processEvents()
        self.assertEqual(dialog.projection.count(), 4)
        for index in range(4):
            dialog.projection.setCurrentIndex(index)
            dialog.resize(480, 430)
            self.app.processEvents()
            self.app.processEvents()
            self.assertTrue(dialog.scene.items())
            for name in project.nodes:
                position = QPointF(*dialog.projected(coordinates(project, name)))
                self.assertTrue(dialog.view.viewport().rect().contains(dialog.view.mapFromScene(position)),
                                f"{name} clipped in projection {index}")
        dialog.reject()
        window.load_project(project)
        window.select_many([("members", "M1"), ("members", "M2")])
        with patch.object(ConnectionPreview, "exec", return_value=QDialog.DialogCode.Accepted):
            window.construct_connection("midpoints")
        self.assertEqual(len(window.project.members), 6)
        self.assertEqual(window.selected, ("members", "M6"))


if __name__ == "__main__":
    unittest.main()
