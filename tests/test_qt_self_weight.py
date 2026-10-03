"""Opt-in member weight, combinations, migration, display, and undo."""
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
from PySide6.QtWidgets import QApplication, QDialog, QGraphicsSimpleTextItem
from pynitegui.qt.analysis import analyze
from pynitegui.qt.app import MainWindow, EngineeringSymbol
from pynitegui.qt.diagrams import DiagramDialog
from pynitegui.qt.examples import example_project
from pynitegui.qt.load_cases import LoadCasesDialog
from pynitegui.qt.model import Project, Material, Section
from pynitegui.qt.reports import export_csv, report_html
from pynitegui.qt.self_weight import SelfWeightDialog
from pynitegui.qt.units import UNIT_SYSTEMS


def solve(project):
    with contextlib.redirect_stdout(io.StringIO()):
        return analyze(project)


def beam():
    return example_project("self_weight")


class SelfWeightTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_uniform_beam_analytical_response_and_no_manual_duplicates(self):
        project = beam()
        result = solve(project)
        w = project.rho * project.A
        length = 420
        self.assertEqual(project.loads, {})
        self.assertAlmostEqual(result.reactions["N1"][1], w * length / 2)
        self.assertAlmostEqual(result.reactions["N2"][1], w * length / 2)
        member = result.solver.members["M1"]
        self.assertAlmostEqual(member.moment("Mz", length / 2, "Service"), -w * length**2 / 8)
        self.assertAlmostEqual(member.deflection("dy", length / 2, "Service"), -5 * w * length**4 / (384 * project.E * project.Iz))
        self.assertAlmostEqual(project.self_weight_total(), w * length)

    def test_mixed_materials_sections_and_inclined_members(self):
        project = Project()
        project.set_material(Material("Heavy", 29000, 0.3, 0.0005))
        project.set_section(Section("Wide", 20, 15.3, 510, 0.506))
        project.add_member((0, 0), (120, 120))
        project.add_member((120, 120), (240, 120))
        project.members["M2"].material = "Heavy"
        project.members["M2"].section = "Wide"
        project.nodes["N1"].support = "fixed"
        project.self_weight_case = "Case 1"
        project.self_weight_factor = 1.2
        weight1 = project.rho * project.A * math.hypot(120, 120) * 1.2
        weight2 = 0.0005 * 20 * 120 * 1.2
        result = solve(project)
        self.assertAlmostEqual(result.reactions["N1"][0], 0)
        self.assertAlmostEqual(result.reactions["N1"][1], weight1 + weight2)
        self.assertAlmostEqual(result.reactions["N1"][2], weight1 * 60 + weight2 * 180)
        self.assertAlmostEqual(project.self_weight_total(), weight1 + weight2)
        for member in project.members.values():
            member.start, member.end = member.end, member.start
        reversed_result = solve(project)
        self.assertAlmostEqual(reversed_result.reactions["N1"][1], weight1 + weight2)

    def test_case_factors_omission_and_disable(self):
        project = beam()
        project.set_load_case("Empty")
        project.set_combination("No weight", {"Empty": 1})
        project.set_combination("Double", {"Self-weight": 2})
        result = solve(project)
        self.assertAlmostEqual(result.for_combination("No weight").reactions["N1"][1], 0)
        self.assertAlmostEqual(result.for_combination("Double").reactions["N1"][1], project.self_weight_total())
        project.self_weight_case = None
        self.assertEqual(project.self_weight_loads(), [])
        self.assertAlmostEqual(solve(project).reactions["N1"][1], 0)

    def test_zero_density_and_split_do_not_change_weight(self):
        project = beam()
        weight = project.self_weight_total()
        project.split_member("M1", 0.37)
        self.assertEqual(project.loads, {})
        self.assertAlmostEqual(project.self_weight_total(), weight)
        self.assertAlmostEqual(solve(project).reactions["N1"][1], weight / 2)
        project.materials[project.default_material].rho = 0
        self.assertEqual(project.self_weight_loads(), [])
        self.assertAlmostEqual(solve(project).reactions["N1"][1], 0)

    def test_case_rename_and_delete_guard(self):
        project = beam()
        project.set_load_case("Dead", "Self-weight")
        self.assertEqual(project.self_weight_case, "Dead")
        project.set_load_case("Other")
        project.default_load_case = "Other"
        project.combinations["Service"] = {"Other": 1}
        with self.assertRaisesRegex(ValueError, "self-weight"):
            project.delete_load_case("Dead")
        project.self_weight_case = None
        project.delete_load_case("Dead")

    def test_validation_persistence_and_old_projects_default_off(self):
        project = beam()
        self.assertEqual(project.clone().to_dict(), project.to_dict())
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "beam.json"
            project.save(path)
            self.assertEqual(Project.open(path).to_dict(), project.to_dict())
        data = project.to_dict()
        data["version"] = 10
        data.pop("self_weight_case")
        data.pop("self_weight_factor")
        self.assertIsNone(Project.from_dict(data).self_weight_case)
        for key, values in (("self_weight_case", (True, [], "Missing")),
                            ("self_weight_factor", (True, 0, -1, float("inf"), "1"))):
            for value in values:
                candidate = project.to_dict()
                candidate[key] = value
                with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                    Project.from_dict(candidate)

    def test_units_preview_and_dialog_factor_precision(self):
        project = beam()
        project.self_weight_factor = 1.123456789012345
        for key, units in UNIT_SYSTEMS.items():
            project.unit_system = key
            dialog = SelfWeightDialog(None, project)
            self.assertAlmostEqual(float(dialog.total.text()), units.to_display(project.self_weight_total(), "force"), delta=abs(float(dialog.total.text())) * 1e-5)
            dialog.accept()
            self.assertEqual(dialog.definition, ("Self-weight", project.self_weight_factor))
            dialog.close()

    def test_ui_commit_undo_filter_and_outdated_snapshot(self):
        window = MainWindow()
        project = beam()
        project.self_weight_case = None
        window.load_project(project)
        result = solve(project)
        window.analysis_revision = window.revision
        window.analysis_finished(result, "")
        snapshot = DiagramDialog(window, window.project, window.result)
        try:
            def accept(dialog):
                dialog.enabled.setChecked(True)
                dialog.accept()
                return QDialog.DialogCode.Accepted
            with patch.object(SelfWeightDialog, "exec", accept):
                window.manage_self_weight()
            self.assertEqual(window.project.self_weight_case, "Self-weight")
            self.assertIsNone(window.result)
            self.assertIn("Different from current", snapshot.snapshot_label.text())
            labels = [item.text() for item in window.view.scene().items() if isinstance(item, QGraphicsSimpleTextItem)]
            self.assertTrue(any(label.startswith("SW M1:") for label in labels))
            self.assertTrue(any(window.tree.topLevelItem(i).text(0) == "Self-weight (1)" for i in range(window.tree.topLevelItemCount())))
            case_dialog = LoadCasesDialog(window)
            self.assertEqual(case_dialog.tables["cases"].item(0, 2).text(), "1")
            case_dialog.close()
            window.load_filter.setCurrentIndex(window.load_filter.findData(False))
            self.assertFalse(any(isinstance(item, EngineeringSymbol) and item.kind == "load" for item in window.view.scene().items()))
            window.undo.undo()
            self.assertIsNone(window.project.self_weight_case)
            window.undo.redo()
            self.assertEqual(window.project.self_weight_case, "Self-weight")
        finally:
            snapshot.close()
            window.saved = window.project.to_dict()
            window.close()
            window.deleteLater()
            self.app.processEvents()

    def test_cancelled_dialog_and_export_provenance(self):
        window = MainWindow()
        window.load_project(beam())
        before = window.project.to_dict()
        with patch.object(SelfWeightDialog, "exec", return_value=QDialog.DialogCode.Rejected):
            window.manage_self_weight()
        self.assertEqual(window.project.to_dict(), before)
        result = solve(window.project)
        self.assertIn("Self-weight; factor 1", report_html(window.project, result))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "results.csv"
            export_csv(path, window.project, result, "nodes")
            with path.open(newline="") as stream:
                row = next(csv.DictReader(stream))
            self.assertEqual(row["Self-weight case"], "Self-weight")
            self.assertEqual(float(row["Self-weight factor"]), 1)
        window.close()
        window.deleteLater()
        self.app.processEvents()

    def test_combined_manual_and_generated_loads_are_added_once(self):
        from pynitegui.qt.model import Load
        project = beam()
        project.loads["L1"] = Load("L1", "M1", "FY", -10, case="Self-weight")
        result = solve(project)
        self.assertAlmostEqual(result.reactions["N1"][1], 5 + project.self_weight_total() / 2)
        solve(project)
        self.assertEqual(len(project.loads), 1)
        self.assertEqual(len(project.self_weight_loads()), 1)

    def test_intensity_overflow_and_missing_new_fields_rejected(self):
        data = beam().to_dict()
        for key in ("self_weight_case", "self_weight_factor"):
            missing = dict(data)
            missing.pop(key)
            with self.assertRaisesRegex(ValueError, key):
                Project.from_dict(missing)
        data["materials"]["Steel_A992"]["rho"] = 1e308
        with self.assertRaisesRegex(ValueError, "intensity"):
            Project.from_dict(data)
