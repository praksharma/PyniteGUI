"""Topology edits preserve engineering loads and produce explicit solver graphs."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtWidgets import QApplication, QInputDialog

from pynitegui.qt.analysis import analyze
from pynitegui.qt.app import MainWindow
from pynitegui.qt.model import Load, Project


def beam():
    project = Project()
    project.add_member((0, 0), (120, 0))
    project.nodes["N1"].support = "pin"
    project.nodes["N2"].support = "roller"
    return project


def crossing():
    project = Project()
    project.add_member((0, 60), (120, 60))
    project.add_member((60, 0), (60, 120))
    return project


def load_xy(project, load):
    if load.target in project.nodes:
        node = project.nodes[load.target]
        return node.x, node.y
    member = project.members[load.target]
    a, b = project.nodes[member.start], project.nodes[member.end]
    return a.x + load.position * (b.x - a.x), a.y + load.position * (b.y - a.y)


class TopologyTests(unittest.TestCase):
    def test_split_preserves_loads_and_reuses_node(self):
        project = beam()
        junction = project.node_at(30, 0)
        project.nodes[junction].support = "fixed"
        for index, fraction in enumerate((0, 0.1, 0.25, 0.8, 1)):
            name = f"L{index}"
            project.loads[name] = Load(name, "M1", "FY", -index - 1, fraction)
        before = {name: load_xy(project, load) for name, load in project.loads.items()}
        segments = project.split_member("M1", 0.25)
        self.assertEqual(segments, ["M1", "M2"])
        self.assertEqual(len(project.nodes), 3)
        self.assertEqual(project.nodes[junction].support, "fixed")
        self.assertEqual(project.loads["L2"].target, junction)
        self.assertAlmostEqual(project.loads["L3"].position, (0.8 - 0.25) / 0.75)
        for name, load in project.loads.items():
            self.assertEqual(load_xy(project, load), before[name])
        project.validate()
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "split.pynite.json"
            project.save(path)
            self.assertEqual(project.to_dict(), Project.open(path).to_dict())

    def test_split_preserves_solver_reactions_and_displacements(self):
        project = beam()
        project.loads["L1"] = Load("L1", "M1", "FY", -10, 0.37)
        project.loads["L2"] = Load("L2", "M1", "MZ", 12, 0.37)
        original = analyze(project)
        midpoint_displacement = original.solver.members["M1"].deflection("dy", 44.4, "Service")
        project.split_member("M1", 0.37)
        result = analyze(project)
        for name in ("N1", "N2"):
            for old, new in zip(original.reactions[name], result.reactions[name]):
                self.assertAlmostEqual(old, new, places=6)
        self.assertAlmostEqual(result.displacements["N3"][1], midpoint_displacement, places=6)
        self.assertEqual(project.loads["L1"].target, "N3")
        self.assertEqual(project.loads["L2"].target, "N3")

    def test_crossing_has_one_shared_junction_and_is_idempotent(self):
        project = crossing()
        project.connect_intersections()
        self.assertEqual(len(project.nodes), 5)
        self.assertEqual(len(project.members), 4)
        junction = project.node_at(60, 60)
        self.assertEqual(sum(junction in (m.start, m.end) for m in project.members.values()), 4)
        self.assertEqual(project.analysis_topology_issues(), [])
        before = project.to_dict()
        project.connect_intersections()
        self.assertEqual(project.to_dict(), before)

    def test_t_joint_reuses_endpoint(self):
        project = Project()
        project.add_member((0, 0), (120, 0))
        project.add_member((60, 0), (60, 60))
        self.assertTrue(project.analysis_topology_issues())
        project.connect_intersections()
        self.assertEqual(len(project.nodes), 4)
        self.assertEqual(len(project.members), 3)
        self.assertEqual(project.analysis_topology_issues(), [])

    def test_multiple_splits_preserve_all_load_positions(self):
        project = Project()
        project.add_member((0, 0), (120, 0))
        for x in (30, 60, 90):
            project.add_member((x, -30), (x, 30))
        for index, fraction in enumerate((0.1, 0.25, 0.5, 0.6, 0.9)):
            name = f"L{index}"
            project.loads[name] = Load(name, "M1", "MZ", 5, fraction)
        before = {name: load_xy(project, load) for name, load in project.loads.items()}
        project.connect_intersections()
        self.assertEqual(len(project.members), 10)
        self.assertEqual(project.analysis_topology_issues(), [])
        for name, load in project.loads.items():
            for old, new in zip(before[name], load_xy(project, load)):
                self.assertAlmostEqual(old, new)

    def test_overlaps_are_rejected_before_any_connection_changes(self):
        project = crossing()
        project.add_member((30, 60), (90, 60))
        before = project.to_dict()
        with self.assertRaisesRegex(ValueError, "overlap"):
            project.connect_intersections()
        self.assertEqual(project.to_dict(), before)
        self.assertTrue(any("overlap" in issue for issue in project.analysis_topology_issues()))

    def test_disconnected_supported_parts_rejected(self):
        project = beam()
        project.add_member((240, 0), (360, 0))
        project.nodes["N3"].support = "fixed"
        with self.assertRaisesRegex(ValueError, "Disconnected node groups"):
            analyze(project)

    def test_implicit_intermediate_connection_rejected(self):
        project = beam()
        project.node_at(60, 0)
        with self.assertRaisesRegex(ValueError, "N3 lies inside M1"):
            analyze(project)
        project.connect_intersections()
        self.assertEqual(project.analysis_topology_issues(), [])

    def test_reversed_inclined_member_preserves_load_position(self):
        project = Project()
        project.add_member((120, 120), (0, 0))
        project.loads["L1"] = Load("L1", "M1", "FX", 5, 0.8)
        before = load_xy(project, project.loads["L1"])
        project.split_member("M1", 0.25)
        self.assertEqual(load_xy(project, project.loads["L1"]), before)
        self.assertEqual(project.nodes["N3"].x, 90)
        self.assertEqual(project.nodes["N3"].y, 90)

    def test_large_coordinates_do_not_merge_distinct_nodes(self):
        project = Project()
        first = project.node_at(1e9, 0)
        second = project.node_at(1e9 + 0.1, 0)
        self.assertNotEqual(first, second)

    def test_invalid_split_does_not_mutate(self):
        project = beam()
        before = project.to_dict()
        for fraction in (0, 1, -0.5, float("nan"), 1e-12):
            with self.assertRaises(ValueError):
                project.split_member("M1", fraction)
            self.assertEqual(project.to_dict(), before)


class TopologyEditorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = MainWindow()

    def tearDown(self):
        self.window.saved = self.window.project.to_dict()
        self.window.close()
        self.window.deleteLater()
        self.application.processEvents()

    def test_connect_is_one_undoable_operation(self):
        self.window.load_project(crossing())
        original = self.window.project.to_dict()
        self.window.connect_intersections()
        self.assertEqual(self.window.undo.count(), 1)
        self.assertEqual(len(self.window.project.members), 4)
        self.window.undo.undo()
        self.assertEqual(self.window.project.to_dict(), original)
        self.window.undo.redo()
        self.assertEqual(len(self.window.project.members), 4)

    def test_split_dialog_preserves_load_and_invalidates_results(self):
        project = beam()
        project.loads["L1"] = Load("L1", "M1", "FY", -10, 0.5)
        self.window.load_project(project)
        self.window.select(("members", "M1"))
        self.window.result = analyze(project)
        self.window.deformed_action.setEnabled(True)
        with patch.object(QInputDialog, "getDouble", return_value=(0.5, True)):
            self.window.split_selected_member()
        self.assertEqual(len(self.window.project.members), 2)
        self.assertEqual(self.window.project.loads["L1"].target, "N3")
        self.assertIsNone(self.window.result)
        self.assertFalse(self.window.deformed_action.isEnabled())
        self.window.undo.undo()
        self.assertEqual(self.window.project.to_dict(), project.to_dict())
        self.window.undo.redo()
        self.assertEqual(len(self.window.project.members), 2)


if __name__ == "__main__":
    unittest.main()
