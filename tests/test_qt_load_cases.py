"""Load-case lifecycle, superposition, and combination-aware Qt results."""
import contextlib
import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import numpy as np
from PySide6.QtWidgets import QApplication, QComboBox, QDialog, QMessageBox, QPushButton
from pynitegui.qt.analysis import analyze
from pynitegui.qt.app import EngineeringSymbol, MainWindow
from pynitegui.qt.diagrams import DiagramDialog, sample_member
from pynitegui.qt.load_cases import CombinationEditor, LoadCasesDialog
from pynitegui.qt.model import Load, Project


def beam():
    project = Project()
    project.add_member((0, 0), (120, 0))
    project.nodes["N1"].support = "pin"
    project.nodes["N2"].support = "roller"
    project.set_load_case("Dead", "Case 1")
    project.set_load_case("Live")
    project.loads["L1"] = Load("L1", "M1", "FY", -0.1, 0, "distributed", -0.1, 1, "Dead")
    project.loads["L2"] = Load("L2", "M1", "FY", -10, 0.5, case="Live")
    project.set_combination("Dead only", {"Dead": 1}, "Service")
    project.set_combination("Live only", {"Live": 1})
    project.set_combination("Factored", {"Dead": 1.2, "Live": 1.6})
    project.set_combination("Uplift", {"Dead": -1, "Live": 0})
    return project


def solve(project):
    with contextlib.redirect_stdout(io.StringIO()):
        return analyze(project)


class LoadCaseTests(unittest.TestCase):
    def test_independent_and_factored_beam_results(self):
        result = solve(beam())
        self.assertEqual(result.combination, "Dead only")
        for name, reaction, moment in (("Dead only", 6, -180), ("Live only", 5, -300),
                                       ("Factored", 15.2, -696), ("Uplift", -6, 180)):
            with self.subTest(name=name):
                view = result.for_combination(name)
                self.assertIs(view.solver, result.solver)
                self.assertAlmostEqual(view.reactions["N1"][1], reaction)
                self.assertAlmostEqual(view.reactions["N2"][1], reaction)
                values = sample_member(beam(), view, "M1")
                self.assertAlmostEqual(values["moment"][np.argmin(abs(values["x"] - 60))], moment, places=4)
        self.assertEqual(result.combination, "Dead only")

    def test_displacement_superposition(self):
        result = solve(beam())
        member = result.solver.members["M1"]
        dead = member.deflection("dy", 60, "Dead only")
        live = member.deflection("dy", 60, "Live only")
        self.assertAlmostEqual(member.deflection("dy", 60, "Factored"), 1.2 * dead + 1.6 * live)

    def test_nodal_force_and_moment_case_assignment(self):
        project = Project()
        project.add_member((0, 0), (120, 0))
        project.nodes["N1"].support = "fixed"
        project.set_load_case("Moment")
        project.loads["L1"] = Load("L1", "N2", "FY", -2)
        project.loads["L2"] = Load("L2", "N2", "MZ", 7, case="Moment")
        project.set_combination("Both", {"Case 1": 2, "Moment": -3})
        result = solve(project).for_combination("Both")
        self.assertAlmostEqual(result.reactions["N1"][1], 4)
        self.assertAlmostEqual(result.reactions["N1"][2], 501)

    def test_rename_case_reassigns_all_references(self):
        project = beam()
        project.set_load_case("Permanent", "Dead")
        project.validate()
        self.assertEqual(project.default_load_case, "Permanent")
        self.assertEqual(project.loads["L1"].case, "Permanent")
        self.assertEqual(project.combinations["Factored"], {"Permanent": 1.2, "Live": 1.6})

    def test_deletion_guards_and_unused_case(self):
        project = beam()
        with self.assertRaises(ValueError):
            project.delete_load_case("Dead")
        with self.assertRaises(ValueError):
            project.delete_load_case("Live")
        project.set_load_case("Unused")
        project.delete_load_case("Unused")
        self.assertNotIn("Unused", project.load_cases)
        for name in list(project.combinations)[1:]:
            project.delete_combination(name)
        with self.assertRaises(ValueError):
            project.delete_combination("Dead only")

    def test_validation(self):
        project = beam()
        for name, factors in (("", {"Dead": 1}), (" Factored", {"Dead": 1}),
                              ("Invalid", {}), ("Invalid", {"Missing": 1}),
                              ("Invalid", {"Dead": float("nan")}), ("Invalid", {"Dead": "1.2"})):
            with self.subTest(name=name, factors=factors), self.assertRaises(ValueError):
                project.set_combination(name, factors)
        with self.assertRaises(ValueError):
            project.set_load_case("Live")
        with self.assertRaises(ValueError):
            project.set_load_case(" ")
        project.loads["L1"].case = "Missing"
        with self.assertRaises(ValueError):
            project.validate()

    def test_serialization_and_version_four_migration(self):
        project = beam()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cases.pynite.json"
            project.save(path)
            self.assertEqual(Project.open(path).to_dict(), project.to_dict())
        legacy = Project()
        legacy.add_member((0, 0), (120, 0))
        legacy.loads["L1"] = Load("L1", "M1")
        data = legacy.to_dict()
        data["version"] = 4
        for key in ("load_cases", "default_load_case", "combinations"):
            del data[key]
        del data["loads"]["L1"]["case"]
        restored = Project.from_dict(data)
        self.assertEqual(restored.loads["L1"].case, "Case 1")
        self.assertEqual(restored.combinations, {"Service": {"Case 1": 1}})

    def test_split_preserves_case(self):
        project = beam()
        project.split_member("M1", 0.5)
        self.assertEqual([load.case for load in project.loads.values() if load.kind == "distributed"], ["Dead", "Dead"])
        self.assertEqual(project.loads["L2"].case, "Live")
        result = solve(project).for_combination("Factored")
        self.assertAlmostEqual(result.reactions["N1"][1], 15.2)

    def test_empty_case_and_zero_factor(self):
        project = beam()
        project.set_load_case("Empty")
        project.set_combination("Empty only", {"Empty": 1})
        project.set_combination("Zero", {"Dead": 0})
        result = solve(project)
        for name in ("Empty only", "Zero"):
            for values in result.for_combination(name).reactions.values():
                np.testing.assert_allclose(values, 0, atol=1e-10)
        with self.assertRaises(ValueError):
            result.for_combination("Missing")

    def test_analyzed_factors_do_not_alias_project(self):
        project = beam()
        result = solve(project)
        project.combinations["Factored"]["Dead"] = 20
        self.assertEqual(result.solver.load_combos["Factored"].factors["Dead"], 1.2)


class LoadCaseEditorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = MainWindow()
        self.window.load_project(beam())

    def tearDown(self):
        self.window.saved = self.window.project.to_dict()
        self.window.close()
        self.window.deleteLater()
        self.application.processEvents()

    def finish_analysis(self):
        self.window.analysis_revision = self.window.revision
        self.window.analysis_finished(solve(self.window.project), "")

    def test_result_switch_updates_table_title_and_load_glyphs(self):
        self.finish_analysis()
        self.window.result_combination.setCurrentText("Factored")
        self.assertEqual(self.window.result.combination, "Factored")
        self.assertEqual(self.window.results_dock.windowTitle(), "Results - Factored")
        self.assertAlmostEqual(float(self.window.results_table.item(0, 5).text()), 15.2)
        self.window.result_combination.setCurrentText("Live only")
        glyphs = [item for item in self.window.view.scene().items() if isinstance(item, EngineeringSymbol) and item.kind == "load"]
        self.assertEqual(len(glyphs), 1)
        self.assertEqual(glyphs[0].value, ("FY", -10))
        self.window.result_combination.setCurrentText("Uplift")
        glyphs = [item for item in self.window.view.scene().items() if isinstance(item, EngineeringSymbol) and item.kind == "load"]
        self.assertEqual(len(glyphs), 9)
        self.assertTrue(all(item.value[1] == 0.1 for item in glyphs))

    def test_deformed_shape_tracks_combination(self):
        self.finish_analysis()
        self.window.deformation_mode.setCurrentText("Custom")
        self.window.deformed_action.trigger()
        from PySide6.QtWidgets import QGraphicsLineItem
        def peak():
            return max(item.line().y2() for item in self.window.view.scene().items()
                       if isinstance(item, QGraphicsLineItem) and item.pen().color().name() == "#bd3549")
        self.window.result_combination.setCurrentText("Dead only")
        dead = peak()
        self.window.edit("Add double dead", lambda p: p.set_combination("Double", {"Dead": 2}))
        self.assertFalse(self.window.result_combination.isEnabled())
        self.assertEqual(self.window.result_combination.count(), 0)
        self.finish_analysis()
        self.window.deformed_action.trigger()
        self.window.result_combination.setCurrentText("Double")
        self.assertAlmostEqual(peak(), 2 * dead)

    def test_coincident_case_load_labels_do_not_overlap(self):
        from PySide6.QtWidgets import QGraphicsSimpleTextItem
        self.finish_analysis()
        self.window.result_combination.setCurrentText("Factored")
        labels = [item for item in self.window.view.scene().items()
                  if isinstance(item, QGraphicsSimpleTextItem) and item.text().startswith("L")]
        self.assertEqual(len(labels), 2)
        rects = [item.deviceTransform(self.window.view.viewportTransform()).mapRect(item.boundingRect()) for item in labels]
        self.assertFalse(rects[0].intersects(rects[1]))

    def test_diagram_switch_and_snapshot(self):
        self.finish_analysis()
        dialog = DiagramDialog(self.window, self.window.project, self.window.result)
        dialog.combination.setCurrentText("Factored")
        self.assertEqual(dialog.result.combination, "Factored")
        self.assertEqual(self.window.result.combination, "Dead only")
        self.assertEqual(dialog.windowTitle(), "Force Diagrams | Factored")
        old = sample_member(dialog.project, dialog.result, "M1")["moment"].copy()
        self.window.edit("Change factor", lambda p: p.set_combination("Factored", {"Dead": 1}, "Factored"))
        np.testing.assert_allclose(sample_member(dialog.project, dialog.result, "M1")["moment"], old)
        dialog.close()

    def test_case_assignment_in_inspector_and_undo(self):
        self.window.select(("loads", "L2"))
        self.window.inspector.findChild(QComboBox, "load_case").setCurrentText("Dead")
        next(b for b in self.window.inspector.findChildren(QPushButton) if b.text() == "Apply").click()
        self.assertEqual(self.window.project.loads["L2"].case, "Dead")
        self.window.undo.undo()
        self.assertEqual(self.window.project.loads["L2"].case, "Live")

    def test_default_case_for_new_load(self):
        self.window.edit("Default Live", lambda p: setattr(p, "default_load_case", "Live"))
        self.window.selected = ("nodes", "N2")
        with patch.object(QDialog, "exec", return_value=QDialog.DialogCode.Accepted):
            self.window.add_load()
        self.assertEqual(self.window.project.loads["L3"].case, "Live")
        self.assertEqual(self.window.project.loads["L1"].case, "Dead")

    def test_manager_rename_default_and_undo(self):
        dialog = LoadCasesDialog(self.window)
        with patch("pynitegui.qt.load_cases.QInputDialog.getText", return_value=("Permanent", True)):
            dialog.perform("cases", "edit")
        self.assertEqual(self.window.project.default_load_case, "Permanent")
        self.assertEqual(self.window.project.loads["L1"].case, "Permanent")
        self.assertFalse(dialog.buttons["cases", "delete"].isEnabled())
        self.window.undo.undo()
        dialog.refresh()
        self.assertEqual(self.window.project.loads["L1"].case, "Dead")
        dialog.tables["cases"].selectRow(1)
        dialog.set_default()
        self.assertEqual(self.window.project.default_load_case, "Live")
        dialog.close()

    def test_combination_editor_validation_and_negative_factors(self):
        dialog = CombinationEditor(self.window, self.window.project, "Custom", {"Dead": 1})
        for include, factor in dialog.fields.values():
            include.setChecked(False)
        with patch.object(QMessageBox, "warning") as warning:
            dialog.accept()
            self.assertTrue(warning.called)
        self.assertIsNone(dialog.definition)
        include, factor = dialog.fields["Live"]
        include.setChecked(True)
        factor.setValue(-1.5)
        dialog.accept()
        self.assertEqual(dialog.definition, ("Custom", {"Live": -1.5}))
        self.window.edit("Add Custom", lambda p: p.set_combination(*dialog.definition))
        self.assertIn("Custom", self.window.project.combinations)
        self.window.undo.undo()
        self.assertNotIn("Custom", self.window.project.combinations)

    def test_manager_combination_add_rename_delete(self):
        dialog = LoadCasesDialog(self.window)
        def accept(editor):
            editor.name.setText("Custom" if editor.previous is None else "Renamed")
            editor.accept()
            return QDialog.DialogCode.Accepted
        with patch.object(CombinationEditor, "exec", accept):
            dialog.perform("combinations", "add")
            self.assertIn("Custom", self.window.project.combinations)
            dialog.perform("combinations", "edit")
        self.assertNotIn("Custom", self.window.project.combinations)
        self.assertIn("Renamed", self.window.project.combinations)
        dialog.perform("combinations", "delete")
        self.assertNotIn("Renamed", self.window.project.combinations)
        self.window.undo.undo()
        self.assertIn("Renamed", self.window.project.combinations)
        dialog.close()
