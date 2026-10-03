"""Axial-only members, nodal loading, mixed joints, and editing workflows."""
import copy
import math
import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication, QComboBox, QPushButton
from pynitegui.qt.analysis import analyze
from pynitegui.qt.app import MainWindow
from pynitegui.qt.examples import example_project
from pynitegui.qt.diagrams import member_values, member_result_rows, sample_member
from pynitegui.qt.model import Load, Project
from pynitegui.qt.model_tables import FIELDS, ModelTablesDialog


class TrussTests(unittest.TestCase):
    def test_triangle_matches_joint_equilibrium_and_virtual_work(self):
        project = example_project("truss")
        result = analyze(project)
        base, height, force = 240, 96, 10
        side = math.hypot(base / 2, height)
        self.assertAlmostEqual(result.reactions["N1"][1], force / 2)
        self.assertAlmostEqual(result.reactions["N2"][1], force / 2)
        expected = {"M1": -force * base / (4 * height),
                    "M2": force * side / (2 * height), "M3": force * side / (2 * height)}
        for name, member in result.solver.members.items():
            for fraction in (0, 0.3, 1):
                x = member.L() * fraction
                self.assertAlmostEqual(member.axial(x, "Service"), expected[name])
                self.assertAlmostEqual(member.shear("Fy", x, "Service"), 0)
                self.assertAlmostEqual(member.moment("Mz", x, "Service"), 0)
        displacement = -force * (side**3 / (2 * height**2) + base**3 / (16 * height**2)) / (project.E * project.A)
        self.assertAlmostEqual(result.displacements["N3"][1], displacement)
        self.assertTrue(all(values[2] is None for values in result.displacements.values()))
        for name in project.members:
            self.assertEqual(member_values(project, result, name, 0)[1:3], (0, 0))
            sample = sample_member(project, result, name)
            self.assertTrue(all(value == 0 for value in sample["moment"]))
            self.assertTrue(all(value == 0 for value in sample["shear"]))
        self.assertTrue(all(row[4] == row[5] == 0 for row in member_result_rows(project, result)))

    def test_response_independent_of_bending_inertia_and_endpoint_direction(self):
        project = example_project("truss")
        reference = analyze(project)
        for member in project.members.values():
            member.start, member.end = member.end, member.start
        section = project.sections[project.default_section]
        section.Iy *= 100
        section.Iz *= 0.01
        result = analyze(project)
        for name in project.nodes:
            for index in (0, 1):
                self.assertAlmostEqual(result.displacements[name][index], reference.displacements[name][index])

    def test_member_loads_are_rejected_not_silently_lumped(self):
        for direction, kind in (("FX", "point"), ("FY", "point"), ("MZ", "point"),
                                ("Angle", "point"), ("Local x", "distributed")):
            project = example_project("truss")
            project.loads["L2"] = Load("L2", "M1", direction, -1, kind=kind, position=0)
            with self.subTest(direction=direction), self.assertRaisesRegex(ValueError, "joint loads only"):
                project.validate()

    def test_truss_joint_moment_without_rotational_restraint_is_rejected(self):
        project = example_project("truss")
        project.loads["L2"] = Load("L2", "N3", "MZ", 2)
        with self.assertRaisesRegex(ValueError, "no rotational restraint"):
            analyze(project)

    def test_mixed_joint_retains_frame_rotation(self):
        project = example_project("truss")
        project.members["M2"].kind = "frame"
        project.nodes["N1"].support = "fixed"
        project.loads["L2"] = Load("L2", "N3", "MZ", 2)
        result = analyze(project)
        self.assertNotIn("N3", result.inactive_rotations)
        self.assertIsNotNone(result.displacements["N3"][2])
        self.assertAlmostEqual(result.solver.members["M3"].moment("Mz", 0, "Service"), 0)

    def test_self_weight_is_joint_lumped_with_correct_total_and_equilibrium(self):
        project = example_project("truss")
        project.loads.clear()
        project.self_weight_case = "Case 1"
        project.self_weight_factor = 1.5
        generated = project.self_weight_loads()
        self.assertEqual(len(generated), 6)
        self.assertTrue(all(load.kind == "point" and load.target in project.nodes for load in generated))
        lengths = 240 + 2 * math.hypot(120, 96)
        weight = project.rho * project.A * lengths * 1.5
        self.assertAlmostEqual(project.self_weight_total(), weight)
        self.assertAlmostEqual(-sum(load.magnitude for load in generated), weight)
        result = analyze(project)
        self.assertAlmostEqual(sum(values[1] for values in result.reactions.values()), weight)
        for member in result.solver.members.values():
            self.assertAlmostEqual(member.moment("Mz", member.L() / 2, "Service"), 0)

    def test_mixed_frame_and_truss_self_weight_and_combinations(self):
        project = example_project("truss")
        project.members["M1"].kind = "frame"
        project.self_weight_case = "Case 1"
        project.set_combination("Double", {"Case 1": 2})
        generated = project.self_weight_loads()
        self.assertEqual(sum(load.kind == "distributed" for load in generated), 1)
        self.assertEqual(sum(load.kind == "point" for load in generated), 4)
        result = analyze(project)
        self.assertAlmostEqual(sum(row[1] for row in result.reactions.values()), 10 + project.self_weight_total())
        doubled = result.for_combination("Double")
        self.assertAlmostEqual(doubled.displacements["N3"][1], 2 * result.displacements["N3"][1])

    def test_split_and_connect_keep_member_type(self):
        project = example_project("truss")
        pieces = project.split_member("M2", 0.5)
        self.assertTrue(all(project.members[name].kind == "truss" and project.members[name].moment_releases == (True, True) for name in pieces))
        project.validate()
        # Splitting a straight bar introduces a transverse mechanism unless braced.
        with self.assertRaisesRegex(ValueError, "unstable|singular"):
            analyze(project)

    def test_persistence_old_files_and_invalid_types(self):
        project = example_project("truss")
        self.assertEqual(project.clone().to_dict(), project.to_dict())
        data = project.to_dict()
        data["version"] = 13
        for member in data["members"].values():
            member.pop("kind")
        before = copy.deepcopy(data)
        restored = Project.from_dict(data)
        self.assertTrue(all(member.kind == "frame" for member in restored.members.values()))
        self.assertEqual(data, before)
        for kind in (None, [], True, "beam"):
            project.members["M1"].kind = kind
            with self.assertRaises(ValueError):
                project.validate()


class TrussUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = MainWindow()
        self.window.load_project(example_project("truss"))

    def tearDown(self):
        self.window.saved = self.window.project.to_dict()
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()

    def test_inspector_type_is_undoable_and_rejects_loaded_conversion(self):
        self.window.select(("members", "M1"))
        selector = self.window.inspector.findChild(QComboBox, "member_type")
        self.assertEqual(selector.currentText(), "truss")
        selector.setCurrentText("frame")
        next(button for button in self.window.inspector.findChildren(QPushButton) if button.text() == "Apply").click()
        self.assertEqual(self.window.project.members["M1"].kind, "frame")
        self.window.undo.undo()
        self.assertEqual(self.window.project.members["M1"].kind, "truss")
        self.window.undo.redo()
        self.window.edit("Add load", lambda p: p.loads.update(L2=Load("L2", "M1")))
        self.window.select(("members", "M1"))
        selector = self.window.inspector.findChild(QComboBox, "member_type")
        selector.setCurrentText("truss")
        before = self.window.project.to_dict()
        with patch("pynitegui.qt.app.QMessageBox.warning") as warning:
            next(button for button in self.window.inspector.findChildren(QPushButton) if button.text() == "Apply").click()
        warning.assert_called_once()
        self.assertEqual(self.window.project.to_dict(), before)

    def test_truss_load_dialog_guides_to_nodes(self):
        self.window.select(("members", "M1"))
        with patch("pynitegui.qt.app.QMessageBox.information") as message:
            self.window.add_load()
        self.assertIn("joint loads", message.call_args.args[2])

    def test_generated_tree_uses_force_units_for_truss_weight(self):
        self.window.edit("Self-weight", lambda p: setattr(p, "self_weight_case", "Case 1"))
        for index in range(self.window.tree.topLevelItemCount()):
            group = self.window.tree.topLevelItem(index)
            if group.text(0).startswith("Self-weight"):
                self.assertEqual(group.childCount(), 6)
                for row in range(group.childCount()):
                    self.assertTrue(group.child(row).text(1).endswith(" kip"))
                break
        else:
            self.fail("Generated self-weight group missing")

    def test_bulk_and_tables_type_editing(self):
        self.window.select_many([("members", "M1"), ("members", "M2")])
        selector = self.window.inspector.findChild(QComboBox, "bulk_kind")
        selector.setCurrentText("frame")
        self.window.inspector.findChild(QPushButton, "bulk_apply").click()
        self.assertEqual(self.window.project.members["M1"].kind, "frame")
        self.assertEqual(self.window.project.members["M2"].kind, "frame")
        self.window.undo.undo()
        self.assertEqual(self.window.project.members["M1"].kind, "truss")
        dialog = ModelTablesDialog(self.window, self.window.project)
        column = FIELDS["members"].index("kind")
        dialog.tables["members"].cellWidget(0, column).setCurrentText("frame")
        dialog.accept()
        self.assertEqual(dialog.definition.members["M1"].kind, "frame")
        self.assertEqual(dialog.definition.members["M2"].kind, "truss")
        dialog.close()
        dialog.deleteLater()
