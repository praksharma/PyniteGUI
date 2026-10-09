"""Explicit XYZ topology edits preserve loads, rolled axes and atomic undo."""
import contextlib
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYNITEGUI_NO_WEBENGINE", "1")
import numpy as np
from PySide6.QtWidgets import QApplication, QInputDialog, QMessageBox, QPushButton

from pynitegui.qt.analysis import analyze
from pynitegui.qt.app import MainWindow
from pynitegui.qt.model import Material, Project, Section
from pynitegui.qt.spatial_model import SpatialLoad, SpatialProject
from pynitegui.qt.spatial_results import member_axes


def beam():
    project = SpatialProject()
    project.set_material(Material("Custom", E=30000, nu=.25, rho=.0002))
    project.set_section(Section("Custom", A=8, Iy=20, Iz=80, J=5))
    project.default_material = project.default_section = "Custom"
    project.add_member((120, 180, 90), (-20, 30, -40))
    project.nodes["N1"].support = "fixed"
    project.members["M1"].roll = 37
    return project


def crossing():
    project = SpatialProject()
    project.add_member((-60, -60, -60), (60, 60, 60))
    project.add_member((-60, 60, 0), (60, -60, 0))
    return project


def position(project, load):
    if load.target in project.nodes:
        return project.nodes[load.target].coords
    member = project.members[load.target]
    a, b = project.nodes[member.start].coords, project.nodes[member.end].coords
    return tuple(start + load.position * (end - start) for start, end in zip(a, b))


def solve(project):
    with contextlib.redirect_stdout(io.StringIO()):
        return analyze(project)


class SpatialTopologyTests(unittest.TestCase):
    def test_split_preserves_xyz_assignments_local_point_loads_and_persistence(self):
        project = beam()
        for index, direction in enumerate(("FX", "FY", "FZ", "MX", "MY", "MZ", "Fx", "Fy", "Fz", "Mx", "My", "Mz", "Angle"), 1):
            project.loads[f"L{index}"] = SpatialLoad(f"L{index}", "M1", direction, index, .37, angle=33, elevation=-27)
        for index, fraction in enumerate((0, .1, .8, 1), 14):
            project.loads[f"L{index}"] = SpatialLoad(f"L{index}", "M1", "Fz", index, fraction)
        original = project.clone()
        axes = member_axes(project, "M1")
        names = project.split_member("M1", .37)
        self.assertEqual(names, ["M1", "M2"])
        self.assertEqual(project.members["M1"].end, project.members["M2"].start)
        for name in names:
            member = project.members[name]
            self.assertEqual((member.material, member.section, member.roll), ("Custom", "Custom", 37))
            np.testing.assert_allclose(member_axes(project, name), axes, atol=1e-12)
        for name, load in project.loads.items():
            before = original.loads[name]
            np.testing.assert_allclose(position(project, load), position(original, before), atol=1e-12)
            self.assertEqual((load.direction, load.magnitude, load.angle, load.elevation, load.case),
                             (before.direction, before.magnitude, before.angle, before.elevation, before.case))
            if before.position == .37:
                self.assertEqual((load.target, load.position), ("M1", 1.))
        project.validate()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "spatial-split.json"
            project.save(path)
            self.assertEqual(Project.open(path).to_dict(), project.to_dict())

    def test_split_preserves_solved_motion_reactions_and_partial_ramp_loads(self):
        project = beam()
        for index, direction in enumerate(("Fx", "Fy", "Fz", "Mx", "My", "Mz", "Angle"), 1):
            project.loads[f"L{index}"] = SpatialLoad(f"L{index}", "M1", direction, index * .1, .37, angle=33, elevation=-27)
        project.loads["L8"] = SpatialLoad("L8", "M1", "Fy", -.04, .1, "distributed", -.09, .9)
        project.loads["L9"] = SpatialLoad("L9", "M1", "Angle", -.03, 0, "distributed", .02, 1, angle=23, elevation=-17)
        project.self_weight_case, project.self_weight_factor = "Case 1", 1.2
        project.set_combination("Double", {"Case 1": 2})
        original = solve(project)
        weight = project.self_weight_total()
        length = original.solver.members["M1"].L()
        local_motion = np.array([original.solver.members["M1"].deflection(axis, length * .37, "Service") for axis in ("dx", "dy", "dz")])
        global_motion = local_motion @ original.solver.members["M1"].T()[:3, :3]
        project.split_member("M1", .37)
        result = solve(project)
        for combo in ("Service", "Double"):
            old, new = original.for_combination(combo), result.for_combination(combo)
            for node in ("N1", "N2"):
                np.testing.assert_allclose(new.reactions[node], old.reactions[node], atol=1e-7)
                np.testing.assert_allclose(new.displacements[node], old.displacements[node], atol=1e-9)
        np.testing.assert_allclose(result.displacements["N3"][:3], global_motion, atol=1e-9)
        self.assertAlmostEqual(weight, project.self_weight_total())
        for name, magnitude, end_magnitude in (("L8", -.04, -.09), ("L9", -.03, .02)):
            pieces = [load for load in project.loads.values() if load.kind == "distributed" and load.direction == project.loads[name].direction]
            self.assertEqual(len(pieces), 2)
            self.assertAlmostEqual(pieces[0].magnitude, magnitude)
            self.assertAlmostEqual(pieces[-1].end_magnitude, end_magnitude)
            self.assertAlmostEqual(pieces[0].end_magnitude, pieces[-1].magnitude)

    def test_reuse_existing_node_retains_restraints_springs_and_load(self):
        project = beam()
        target = tuple(start + .5 * (end - start) for start, end in zip(project.nodes["N1"].coords, project.nodes["N2"].coords))
        joint = project.node_at(*target)
        project.nodes[joint].spring_y = 10
        project.loads["L1"] = SpatialLoad("L1", joint, "FY", -3)
        before = project.nodes[joint]
        project.split_member("M1", .5)
        self.assertEqual(len(project.nodes), 3)
        self.assertEqual(project.nodes[joint], before)
        self.assertEqual(project.loads["L1"].target, joint)

    def test_crossing_and_t_junction_connect_once_without_projection(self):
        project = crossing()
        project.connect_intersections()
        self.assertEqual((len(project.nodes), len(project.members)), (5, 4))
        joint = project.node_at(0, 0, 0)
        self.assertEqual(sum(joint in (member.start, member.end) for member in project.members.values()), 4)
        self.assertEqual(project.analysis_topology_issues(), [])
        before = project.to_dict()
        project.connect_intersections()
        self.assertEqual(project.to_dict(), before)
        project = SpatialProject()
        project.add_member((0, 0, 0), (0, 0, 120))
        project.add_member((0, 0, 60), (60, 30, 60))
        self.assertEqual(project.member_intersection("M1", "M2"), (.5, 0))
        project.connect_intersections()
        self.assertEqual((len(project.nodes), len(project.members)), (4, 3))
        self.assertEqual(project.analysis_topology_issues(), [])

    def test_multiple_intersections_remap_original_load_stations(self):
        project = SpatialProject()
        project.add_member((0, 0, 0), (120, 120, 120))
        for t in (.25, .5, .75):
            point = np.array([120 * t] * 3)
            project.add_member(tuple(point + (20, -20, 0)), tuple(point + (-20, 20, 0)))
        for index, t in enumerate((.1, .25, .5, .6, .75, .9), 1):
            project.loads[f"L{index}"] = SpatialLoad(f"L{index}", "M1", "Mz", index, t)
        old = {name: position(project, load) for name, load in project.loads.items()}
        project.connect_intersections()
        self.assertEqual(len(project.members), 10)
        self.assertEqual(project.analysis_topology_issues(), [])
        for name, load in project.loads.items():
            np.testing.assert_allclose(position(project, load), old[name], atol=1e-12)

    def test_skew_and_endpoint_contacts_are_not_false_crossings(self):
        project = SpatialProject()
        project.add_member((-60, 0, 0), (60, 0, 0))
        project.add_member((0, -60, 1), (0, 60, 1))
        before = project.to_dict()
        project.connect_intersections()
        self.assertEqual(project.to_dict(), before)
        self.assertIsNone(project.member_intersection("M1", "M2"))
        project = SpatialProject()
        project.add_member((0, 0, 0), (0, 0, 120))
        project.add_member((0, 0, 120), (0, 60, 180))
        before = project.to_dict()
        project.connect_intersections()
        self.assertEqual(project.to_dict(), before)
        self.assertEqual(project.analysis_topology_issues(), [])

    def test_atomic_invalid_splits_overlaps_and_duplicate_segments(self):
        project = beam()
        before = project.to_dict()
        for fraction in (0, 1, -1, 1e-12, float("nan"), float("inf"), True, "bad"):
            with self.assertRaises(ValueError):
                project.split_member("M1", fraction)
            self.assertEqual(project.to_dict(), before)
        with self.assertRaisesRegex(ValueError, "Unknown"):
            project.split_member("missing", .5)
        project = crossing()
        project.add_member((-30, -30, -30), (30, 30, 30))
        before = project.to_dict()
        with self.assertRaisesRegex(ValueError, "overlap"):
            project.connect_intersections()
        self.assertEqual(project.to_dict(), before)
        project = SpatialProject()
        project.add_member((0, 0, 0), (120, 0, 0))
        project.add_member((0, 0, 0), (60, 0, 0))
        before = project.to_dict()
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            project.split_member("M1", .5)
        self.assertEqual(project.to_dict(), before)


class SpatialTopologyEditorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = MainWindow()

    def tearDown(self):
        self.window.saved = self.window.project.to_dict()
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()

    def test_inspector_split_is_one_undo_and_invalidates_results(self):
        project = beam()
        project.loads["L1"] = SpatialLoad("L1", "M1", "Fz", -3, .5)
        self.window.load_project(project)
        self.window.result = solve(project)
        self.window.select(("members", "M1"))
        button = self.window.findChild(QPushButton, "spatial_split")
        self.assertIsNotNone(button)
        with patch.object(QInputDialog, "getDouble", return_value=(.5, True)):
            button.click()
        self.assertEqual(len(self.window.project.members), 2)
        self.assertIsNone(self.window.result)
        self.assertEqual(self.window.undo.count(), 1)
        self.assertEqual(self.window.project.loads["L1"].target, "M1")
        self.assertEqual(self.window.project.loads["L1"].position, 1)
        self.window.undo.undo()
        self.assertEqual(self.window.project.to_dict(), project.to_dict())
        self.window.undo.redo()
        self.assertEqual(len(self.window.project.members), 2)

    def test_connect_one_undo_and_overlap_failure_leaves_model_unchanged(self):
        self.window.load_project(crossing())
        original = self.window.project.to_dict()
        self.window.connect_intersections()
        self.assertEqual(self.window.undo.count(), 1)
        self.assertEqual(len(self.window.project.members), 4)
        self.window.undo.undo()
        self.assertEqual(self.window.project.to_dict(), original)
        self.window.undo.redo()
        self.assertEqual(len(self.window.project.members), 4)
        project = crossing()
        project.add_member((-30, -30, -30), (30, 30, 30))
        self.window.load_project(project)
        with patch.object(QMessageBox, "warning") as warning:
            self.window.connect_intersections()
        warning.assert_called_once()
        self.assertEqual(self.window.undo.count(), 0)
        self.assertEqual(self.window.project.to_dict(), project.to_dict())


if __name__ == "__main__":
    unittest.main()
