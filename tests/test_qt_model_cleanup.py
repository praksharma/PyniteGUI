"""Reviewable findings and atomic equal subdivision of physical frame members."""
import contextlib
import io
import math
import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYNITEGUI_NO_WEBENGINE", "1")
import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QInputDialog, QMessageBox
from pynitegui.qt.analysis import analyze, rigid_body_issue
from pynitegui.qt.app import MainWindow
from pynitegui.qt.examples import example_project
from pynitegui.qt.model import Load, Project
from pynitegui.qt.model_findings import finding_entities
from pynitegui.qt.spatial_analysis import rigid_body_issue as spatial_rigid_body_issue


def solve(project):
    with contextlib.redirect_stdout(io.StringIO()):
        return analyze(project)


class SubdivisionTests(unittest.TestCase):
    def test_equal_lengths_assignments_releases_and_existing_joint(self):
        project = example_project("shear_release")
        joint = project.node_at(30, 0)
        project.nodes[joint].support = "roller"
        original = project.members["M1"]
        names = project.subdivide_members(["M1", "M1"], 4)["M1"]
        self.assertEqual(len(names), 4)
        self.assertEqual(project.members[names[0]].end, joint)
        for index, name in enumerate(names):
            member = project.members[name]
            a, b = project.nodes[member.start], project.nodes[member.end]
            self.assertAlmostEqual(math.hypot(b.x-a.x, b.y-a.y), 30)
            self.assertEqual((member.material, member.section), (original.material, original.section))
            self.assertEqual(member.release_end_y, index == 3)
            self.assertFalse(member.release_start_y)

    def test_frame_solutions_preserved_partial_loads_roll_selfweight_combinations(self):
        for key in ("cantilever", "pitched", "self_weight", "shear_release", "3d_cantilever", "3d_space_frame"):
            with self.subTest(key=key):
                project = example_project(key)
                if key == "3d_cantilever":
                    project.members["M1"].roll = 31
                    project.loads["L4"].position = .13
                    project.loads["L4"].end_position = .87
                original = project.clone()
                before = solve(project)
                segments = project.subdivide_members(list(project.members), 3)
                self.assertEqual(len(project.members), 3 * len(original.members))
                self.assertFalse(project.analysis_topology_issues())
                after = solve(project)
                for combo in original.combinations:
                    left, right = before.for_combination(combo), after.for_combination(combo)
                    for node in original.nodes:
                        np.testing.assert_allclose(right.reactions[node], left.reactions[node], rtol=1e-7, atol=1e-7)
                        np.testing.assert_allclose(right.displacements[node], left.displacements[node], rtol=1e-7, atol=1e-7)
                if key.startswith("3d"):
                    for original_name, names in segments.items():
                        for name in names:
                            self.assertEqual(project.members[name].roll, original.members[original_name].roll)

    def test_invalid_batch_is_atomic_and_trusses_are_explicitly_rejected(self):
        for count, names in ((True, ["M1"]), (1, ["M1"]), (101, ["M1"]), (2.5, ["M1"]), (2, []), (2, ["M1", "missing"])):
            project = example_project("cantilever")
            before = project.to_dict()
            with self.assertRaises(ValueError):
                project.subdivide_members(names, count)
            self.assertEqual(project.to_dict(), before)
        project = example_project("portal")
        project.members["M2"].kind = "truss"
        project.loads.clear()
        before = project.to_dict()
        with self.assertRaisesRegex(ValueError, "unbraced joints"):
            project.subdivide_members(["M1", "M2"], 2)
        self.assertEqual(project.to_dict(), before)


class FindingTests(unittest.TestCase):
    def test_known_topology_and_dof_references_are_exact(self):
        project = Project()
        project.add_member((0, 0), (120, 0))
        project.add_member((30, 0), (60, 0))
        self.assertEqual(finding_entities(project, "Members M1 and M2 overlap. Remove it."), [("members", "M1"), ("members", "M2")])
        self.assertEqual(finding_entities(project, "N3 lies inside M1. Use Connect."), [("nodes", "N3"), ("members", "M1")])
        self.assertEqual(finding_entities(project, "Node N1: bad restraint."), [("nodes", "N1")])
        self.assertEqual(finding_entities(project, "Unexpected error mentioning N1 and M1"), [])
        self.assertEqual(finding_entities(project, "Affected global degrees of freedom: N1 DX, N2 DY, and 9 more."), [("nodes", "N1"), ("nodes", "N2")])
        self.assertEqual(finding_entities(project, "No effective joint stiffness at: N10 DX."), [])

    def test_actual_rigid_body_findings_and_names_with_punctuation(self):
        for key in ("portal", "3d_cantilever"):
            project = example_project(key)
            for node in project.nodes.values():
                node.support = "free"
            issue = spatial_rigid_body_issue(project) if key.startswith("3d") else rigid_body_issue(project)
            self.assertTrue(finding_entities(project, issue))
        project = Project()
        project.add_member((0, 0), (100, 0))
        node = project.nodes.pop("N1")
        node.name = "Joint [A], one"
        project.nodes[node.name] = node
        self.assertEqual(finding_entities(project, "Possible mechanism or very weak stiffness involves: Joint [A], one DY, N2 RZ."), [("nodes", node.name), ("nodes", "N2")])


class CleanupWindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = MainWindow()
        self.window.load_project(example_project("portal"))

    def tearDown(self):
        self.window.saved = self.window.project.to_dict()
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()

    def test_multi_subdivision_one_undo_selection_and_cancel(self):
        window = self.window
        window.select_many([("members", "M1"), ("members", "M2")])
        before = window.project.to_dict()
        with patch.object(QInputDialog, "getInt", return_value=(3, False)):
            window.subdivide_selected_members()
        self.assertEqual(window.project.to_dict(), before)
        count = window.undo.count()
        with patch.object(QInputDialog, "getInt", return_value=(3, True)):
            window.subdivide_selected_members()
        after = window.project.to_dict()
        self.assertEqual(window.undo.count(), count+1)
        self.assertEqual(len(window.selections), 6)
        self.assertEqual(len(window.project.members), 7)
        window.undo.undo()
        self.assertEqual(window.project.to_dict(), before)
        window.undo.redo()
        self.assertEqual(window.project.to_dict(), after)

    def test_model_findings_select_and_invalidate_on_edit_but_not_units(self):
        window = self.window
        project = window.project.clone()
        project.node_at(0, 72)
        window.load_project(project)
        window.check_model()
        self.assertTrue(window.model_findings.list.count())
        window.model_findings.activate()
        self.assertEqual(window.selections, [("nodes", "N5"), ("members", "M1")])
        self.assertEqual({tuple(item.data(0, Qt.ItemDataRole.UserRole)) for item in window.tree.selectedItems()},
                         {("nodes", "N5"), ("members", "M1")})
        before = window.project.to_dict()
        revision = window.revision
        window.model_findings.activate()
        self.assertEqual(window.project.to_dict(), before)
        self.assertEqual(window.revision, revision)
        window.set_units("si")
        self.assertTrue(window.model_findings.list.count())
        window.edit("Move", lambda project: setattr(project.nodes["N5"], "x", 10))
        self.assertEqual(window.model_findings.list.count(), 0)
        self.assertFalse(window.model_findings.select_button.isEnabled())

    def test_failed_analysis_references_and_stale_reply(self):
        window = self.window
        window.analysis_revision = window.revision
        with patch.object(QMessageBox, "warning"):
            window.analysis_finished(None, "Structure is unstable.\nNo effective joint stiffness at: N2 RZ, N3 DY.")
        window.model_findings.activate()
        self.assertEqual(window.selections, [("nodes", "N2"), ("nodes", "N3")])
        window.analysis_revision = window.revision-1
        with patch.object(window, "show_model_findings") as show:
            window.analysis_finished(None, "Node N1: invalid")
        show.assert_not_called()
        window.show_model_findings(["Unknown solver failure"], "Failed")
        self.assertFalse(window.model_findings.select_button.isEnabled())

    def test_spatial_subdivision_and_failure_navigation(self):
        window = self.window
        window.load_project(example_project("3d_cantilever"))
        window.select(("members", "M1"))
        with patch.object(QInputDialog, "getInt", return_value=(4, True)):
            window.subdivide_selected_members()
        self.assertEqual(len(window.selections), 4)
        self.assertEqual(len(window.project.members), 4)
        window.show_model_findings(["No effective joint stiffness at: N2 DZ, N3 RX."], "Analysis failed")
        window.model_findings.activate()
        self.assertEqual(window.selections, [("nodes", "N2"), ("nodes", "N3")])
        window.load_project(example_project("portal"))
        self.assertEqual(window.model_findings.list.count(), 0)


if __name__ == "__main__":
    unittest.main()
