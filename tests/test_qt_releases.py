"""Moment-release mechanics, topology preservation, and editor regressions."""
import contextlib
import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import numpy as np
from PySide6.QtWidgets import QApplication, QCheckBox, QMessageBox, QPushButton
from pynitegui.qt.analysis import analyze
from pynitegui.qt.app import EngineeringSymbol, MainWindow
from pynitegui.qt.diagrams import sample_member, structure_data
from pynitegui.qt.model import Load, Project


def solve(project):
    with contextlib.redirect_stdout(io.StringIO()):
        return analyze(project)


def beam(start=True, end=True, support="fixed"):
    project = Project()
    project.add_member((0, 0), (120, 0))
    project.nodes["N1"].support = support
    project.nodes["N2"].support = "roller" if support == "pin" else support
    project.members["M1"].release_start = start
    project.members["M1"].release_end = end
    project.loads["L1"] = Load("L1", "M1", "FY", -0.1, 0, "distributed", -0.1, 1)
    return project


class ReleaseTests(unittest.TestCase):
    def test_two_hinges_at_fixed_nodes_match_simply_supported_beam(self):
        project = beam()
        result = solve(project)
        self.assertAlmostEqual(result.reactions["N1"][1], 6)
        self.assertAlmostEqual(result.reactions["N2"][1], 6)
        self.assertAlmostEqual(result.reactions["N1"][2], 0)
        self.assertAlmostEqual(result.reactions["N2"][2], 0)
        member = result.solver.members["M1"]
        self.assertAlmostEqual(member.moment("Mz", 60, "Service"), -180)
        self.assertAlmostEqual(member.deflection("dy", 60, "Service"), -5 * 0.1 * 120**4 / (384 * project.E * project.Iz))
        self.assertEqual(result.inactive_rotations, frozenset())

    def test_single_hinge_propped_cantilever_formulas(self):
        result = solve(beam(False, True))
        self.assertAlmostEqual(result.reactions["N1"][1], 7.5)
        self.assertAlmostEqual(result.reactions["N2"][1], 4.5)
        self.assertAlmostEqual(result.reactions["N1"][2], 180)
        self.assertAlmostEqual(result.reactions["N2"][2], 0)
        self.assertAlmostEqual(result.solver.members["M1"].moment("Mz", 120, "Service"), 0)

    def test_unreleased_fixed_beam_baseline(self):
        result = solve(beam(False, False))
        self.assertAlmostEqual(result.reactions["N1"][2], 120)
        self.assertAlmostEqual(result.reactions["N2"][2], -120)

    def test_unused_joint_rotations_are_not_physical_restraints(self):
        project = beam(support="pin")
        result = solve(project)
        self.assertEqual(result.inactive_rotations, {"N1", "N2"})
        self.assertIsNone(result.displacements["N1"][2])
        self.assertIsNone(result.displacements["N2"][2])
        self.assertAlmostEqual(result.reactions["N1"][1], 6)
        self.assertAlmostEqual(result.reactions["N1"][2], 0)
        self.assertAlmostEqual(result.reactions["N2"][2], 0)
        self.assertAlmostEqual(sample_member(project, result, "M1")["moment"].min(), -180)

    def test_unrestrained_nodal_moment_rejected_per_combination(self):
        project = beam(support="pin")
        project.loads["L2"] = Load("L2", "N1", "MZ", 7)
        with self.assertRaisesRegex(ValueError, "Node N1.*Service.*rotational restraint"):
            solve(project)
        project.combinations["Service"] = {"Case 1": 0}
        self.assertEqual(project.analysis_release_issues(), [])
        result = solve(project)
        self.assertAlmostEqual(result.reactions["N1"][2], 0)

    def test_balanced_and_tiny_nodal_moments(self):
        project = beam(support="pin")
        project.loads["L2"] = Load("L2", "N1", "MZ", 7)
        project.loads["L3"] = Load("L3", "N1", "MZ", -7)
        self.assertEqual(project.analysis_release_issues(), [])
        solve(project)
        project.loads["L2"].magnitude = 1e-15
        del project.loads["L3"]
        self.assertTrue(project.analysis_release_issues())

    def test_fixed_node_can_resist_external_nodal_moment(self):
        project = beam()
        project.loads["L2"] = Load("L2", "N1", "MZ", 7)
        result = solve(project)
        self.assertAlmostEqual(result.reactions["N1"][2], -7)
        self.assertAlmostEqual(result.solver.members["M1"].moment("Mz", 0, "Service"), 0)

    def test_split_preserves_outer_releases_only_and_response(self):
        project = beam(support="pin")
        before = solve(project)
        segments = project._split_member("M1", [0.25, 0.75])
        self.assertEqual([(project.members[name].release_start, project.members[name].release_end) for name in segments],
                         [(True, False), (False, False), (False, True)])
        self.assertEqual(project.inactive_rotations(), {"N1", "N2"})
        result = solve(project)
        for node in ("N1", "N2"):
            np.testing.assert_allclose(result.reactions[node], before.reactions[node], atol=1e-8)
        self.assertAlmostEqual(result.solver.members["M2"].deflection("dy", 30, "Service"),
                               before.solver.members["M1"].deflection("dy", 60, "Service"))

    def test_connect_intersections_keeps_new_joints_rigid(self):
        project = beam()
        project.add_member((60, 0), (60, 60))
        project.members["M2"].release_end = True
        project.connect_intersections()
        project.validate()
        self.assertTrue(project.members["M1"].release_start)
        self.assertFalse(project.members["M1"].release_end)
        self.assertFalse(project.members["M3"].release_start)
        self.assertTrue(project.members["M3"].release_end)
        self.assertTrue(project.members["M2"].release_end)

    def test_reversed_hinge_response_and_diagram(self):
        project = beam(False, True)
        original = structure_data(project, solve(project), "moment")["M1"]
        member = project.members["M1"]
        member.start, member.end = member.end, member.start
        member.release_start, member.release_end = member.release_end, member.release_start
        result = solve(project)
        reverse = structure_data(project, result, "moment")["M1"]
        np.testing.assert_allclose(original["values"], reverse["values"][::-1], atol=1e-8)
        self.assertAlmostEqual(result.reactions["N1"][2], 180)

    def test_pin_jointed_triangle(self):
        project = Project()
        for start, end in (((0, 0), (120, 0)), ((0, 0), (60, 80)), ((120, 0), (60, 80))):
            project.add_member(start, end)
        project.nodes["N1"].support = "pin"
        project.nodes["N2"].support = "roller"
        for member in project.members.values():
            member.release_start = member.release_end = True
        project.loads["L1"] = Load("L1", "N3", "FY", -10)
        result = solve(project)
        self.assertAlmostEqual(result.reactions["N1"][1], 5)
        self.assertAlmostEqual(result.reactions["N2"][1], 5)
        self.assertLess(result.displacements["N3"][1], 0)
        for member in result.solver.members.values():
            self.assertAlmostEqual(member.moment("Mz", member.L() / 2, "Service"), 0)
            self.assertAlmostEqual(member.shear("Fy", member.L() / 2, "Service"), 0)
        self.assertAlmostEqual(abs(result.solver.members["M1"].axial(60, "Service")), 3.75)

    def test_real_translational_mechanism_is_not_hidden(self):
        project = beam()
        project.nodes["N2"].support = "free"
        with self.assertRaises(Exception):
            solve(project)

    def test_shared_joint_rotation_active_if_any_connection_is_rigid(self):
        project = Project()
        project.add_member((0, 0), (0, 120))
        project.add_member((0, 120), (120, 120))
        project.add_member((120, 120), (120, 0))
        project.nodes["N1"].support = project.nodes["N4"].support = "fixed"
        project.members["M2"].release_start = True
        project.loads["L1"] = Load("L1", "N2", "MZ", 7)
        self.assertNotIn("N2", project.inactive_rotations())
        result = solve(project)
        self.assertIsNotNone(result.displacements["N2"][2])
        self.assertAlmostEqual(result.solver.members["M2"].moment("Mz", 0, "Service"), 0)

    def test_combinations_preserve_inactive_rotation_metadata(self):
        project = beam(support="pin")
        project.set_combination("Double", {"Case 1": 2})
        result = solve(project).for_combination("Double")
        self.assertIsNone(result.displacements["N1"][2])
        self.assertAlmostEqual(result.reactions["N1"][1], 12)
        self.assertEqual(result.inactive_rotations, {"N1", "N2"})

    def test_persistence_and_version_five_migration(self):
        project = beam()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "hinges.pynite.json"
            project.save(path)
            self.assertEqual(Project.open(path).to_dict(), project.to_dict())
        data = project.to_dict()
        data["version"] = 5
        del data["members"]["M1"]["release_start"]
        del data["members"]["M1"]["release_end"]
        restored = Project.from_dict(data)
        self.assertFalse(restored.members["M1"].release_start)
        self.assertFalse(restored.members["M1"].release_end)

    def test_release_validation(self):
        for value in (1, "true", None):
            project = beam()
            project.members["M1"].release_start = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                project.validate()

    def test_whole_structure_diagram_marks_released_member_ends(self):
        from matplotlib.figure import Figure
        from matplotlib.offsetbox import AnnotationBbox
        from pynitegui.qt.diagrams import draw_structure
        project = beam()
        ax = Figure().add_subplot(111)
        draw_structure(ax, project, solve(project), "moment")
        self.assertEqual(sum(isinstance(item, AnnotationBbox) and item.get_gid() is None for item in ax.artists), 2)


class ReleaseEditorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = MainWindow()
        self.window.load_project(beam(False, False, "pin"))

    def tearDown(self):
        self.window.saved = self.window.project.to_dict()
        self.window.close()
        self.window.deleteLater()
        self.application.processEvents()

    def test_inspector_apply_undo_and_glyphs(self):
        self.window.result = solve(self.window.project)
        self.window.select(("members", "M1"))
        for key in ("release_start", "release_end"):
            self.window.inspector.findChild(QCheckBox, key).setChecked(True)
        next(b for b in self.window.inspector.findChildren(QPushButton) if b.text() == "Apply").click()
        self.assertIsNone(self.window.result)
        self.assertTrue(self.window.project.members["M1"].release_start)
        glyphs = [item for item in self.window.view.scene().items() if isinstance(item, EngineeringSymbol) and item.kind == "hinge"]
        self.assertEqual(len(glyphs), 2)
        self.window.undo.undo()
        self.assertFalse(self.window.project.members["M1"].release_start)
        self.window.undo.redo()
        self.assertTrue(self.window.project.members["M1"].release_end)

    def test_inactive_rotation_table_and_deformed_shape(self):
        self.window.load_project(beam(support="pin"))
        self.window.analysis_revision = self.window.revision
        self.window.analysis_finished(solve(self.window.project), "")
        self.assertEqual(self.window.results_table.item(0, 3).text(), "n/a")
        self.assertEqual(self.window.results_table.item(0, 6).text(), "0")
        self.window.deformed_action.trigger()
        from PySide6.QtWidgets import QGraphicsLineItem
        lines = [item for item in self.window.view.scene().items() if isinstance(item, QGraphicsLineItem) and item.pen().color().name() == "#bd3549"]
        self.assertEqual(len(lines), 40)
        self.assertGreater(max(item.line().y2() for item in lines), 0)

    def test_check_model_reports_unrestrained_nodal_moment(self):
        project = beam(support="pin")
        project.loads["L2"] = Load("L2", "N1", "MZ", 7)
        self.window.load_project(project)
        with patch.object(QMessageBox, "warning") as warning:
            self.window.check_model()
        self.assertIn("all connected member ends are hinged", warning.call_args.args[2])
