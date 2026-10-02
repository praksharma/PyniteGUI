"""SI/imperial conversions, precision-preserving input, and complete UI switching."""
import contextlib
import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import numpy as np
from matplotlib.figure import Figure
from PySide6.QtCore import QPointF, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QComboBox, QDialog, QDoubleSpinBox, QGraphicsSimpleTextItem, QLabel, QPushButton
from pynitegui.qt.analysis import analyze
from pynitegui.qt.app import MainWindow, unit_number, unit_value
from pynitegui.qt.diagrams import DiagramDialog, draw_structure, sample_member
from pynitegui.qt.materials import MaterialDialog, MaterialEditor
from pynitegui.qt.model import Load, Material, Project, Section
from pynitegui.qt.sections import SectionDialog, SectionEditor
from pynitegui.qt.units import INCH_TO_METRE, KIP_TO_KN, UNIT_SYSTEMS


def solve(project):
    with contextlib.redirect_stdout(io.StringIO()):
        return analyze(project)


def si_beam():
    project = Project(unit_system="si")
    units = project.units
    project.add_member((0, 0), (units.from_display(3, "length"), 0))
    project.nodes["N1"].support = "pin"
    project.nodes["N2"].support = "roller"
    project.materials[project.default_material] = Material(project.default_material, units.from_display(200000, "stress"), 0.3, units.from_display(78.5, "density"))
    project.sections[project.default_section] = Section(project.default_section, units.from_display(5000, "area"),
        units.from_display(8e6, "inertia"), units.from_display(8e6, "inertia"), units.from_display(1e6, "inertia"))
    intensity = units.from_display(-10, "intensity")
    project.loads["L1"] = Load("L1", "M1", "FY", intensity, 0, "distributed", intensity, 1)
    return project


class UnitTests(unittest.TestCase):
    def test_known_conversion_factors(self):
        units = UNIT_SYSTEMS["si"]
        self.assertEqual(units.to_display(1, "length"), 0.0254)
        self.assertAlmostEqual(units.to_display(1, "force"), 4.4482216152605)
        self.assertAlmostEqual(units.to_display(1, "moment"), 0.1129848290276167)
        self.assertAlmostEqual(units.to_display(1, "intensity"), 175.1268352464764)
        self.assertAlmostEqual(units.to_display(1, "stress"), 6.894757293168361)
        self.assertAlmostEqual(units.to_display(1, "area"), 645.16)
        self.assertAlmostEqual(units.to_display(1, "inertia"), 416231.4256)
        self.assertAlmostEqual(units.to_display(1, "density"), KIP_TO_KN / INCH_TO_METRE**3)
        self.assertEqual(units.to_display(0.3, "rotation"), 0.3)

    def test_round_trips_and_imperial_identity(self):
        for quantity in ("length", "force", "moment", "intensity", "stress", "density", "area", "inertia", "rotation"):
            for value in (0, -12.3456789, 1e-9, 1e8):
                for units in UNIT_SYSTEMS.values():
                    converted = units.from_display(units.to_display(value, quantity), quantity)
                    self.assertAlmostEqual(converted, value, delta=max(abs(value) * 1e-14, 1e-20))
                self.assertEqual(UNIT_SYSTEMS["imperial"].to_display(value, quantity), value)
        with self.assertRaises(ValueError):
            UNIT_SYSTEMS["si"].factor("temperature")

    def test_si_beam_analytical_response(self):
        project = si_beam()
        result = solve(project)
        for name in ("N1", "N2"):
            self.assertAlmostEqual(project.units.to_display(result.reactions[name][1], "force"), 15)
        member = result.solver.members["M1"]
        midpoint = project.units.from_display(1.5, "length")
        self.assertAlmostEqual(project.units.to_display(member.moment("Mz", midpoint, "Service"), "moment"), -11.25)
        self.assertAlmostEqual(project.units.to_display(member.deflection("dy", midpoint, "Service"), "length"), -5 * 10 * 3**4 / (384 * 1600))

    def test_changing_units_does_not_change_model_or_solver_response(self):
        project = si_beam()
        before = project.to_dict()
        result = solve(project)
        project.unit_system = "imperial"
        after = project.to_dict()
        before.pop("unit_system")
        after.pop("unit_system")
        self.assertEqual(before, after)
        repeated = solve(project)
        for name in result.reactions:
            np.testing.assert_allclose(result.reactions[name], repeated.reactions[name], atol=1e-10)

    def test_preference_persistence_and_legacy_migration(self):
        project = si_beam()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "si.pynite.json"
            project.save(path)
            restored = Project.open(path)
            self.assertEqual(restored.to_dict(), project.to_dict())
            self.assertEqual(restored.to_dict()["units"], "in-kip")
        data = project.to_dict()
        data["version"] = 6
        del data["unit_system"]
        restored = Project.from_dict(data)
        self.assertEqual(restored.unit_system, "imperial")
        self.assertEqual(restored.nodes["N2"].x, project.nodes["N2"].x)

    def test_invalid_unit_preferences(self):
        for key in ("unknown", None, []):
            project = si_beam()
            project.unit_system = key
            with self.subTest(key=key), self.assertRaises(ValueError):
                project.validate()
        data = si_beam().to_dict()
        data["units"] = "m-kN"
        with self.assertRaises(ValueError):
            Project.from_dict(data)

    def test_structure_plot_converts_geometry_and_moment_annotations(self):
        project = si_beam()
        ax = Figure().add_subplot(111)
        draw_structure(ax, project, solve(project), "moment")
        self.assertEqual(ax.get_xlabel(), "X (m)")
        self.assertEqual(ax.get_ylabel(), "Y (m)")
        self.assertIn("kN-m", ax.get_title())
        self.assertAlmostEqual(ax.lines[0].get_xdata()[-1], 3)
        labels = [text.get_text() for text in ax.texts]
        self.assertIn("-11.25", labels)


class UnitEditorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = MainWindow()
        self.window.load_project(si_beam())

    def tearDown(self):
        self.window.saved = self.window.project.to_dict()
        self.window.close()
        self.window.deleteLater()
        self.application.processEvents()

    def apply(self):
        next(b for b in self.window.inspector.findChildren(QPushButton) if b.text() == "Apply").click()

    def finish_analysis(self):
        self.window.analysis_revision = self.window.revision
        self.window.analysis_finished(solve(self.window.project), "")

    def test_selector_updates_units_and_is_undoable(self):
        self.window.unit_selector.setCurrentIndex(self.window.unit_selector.findData("imperial"))
        self.assertEqual(self.window.project.unit_system, "imperial")
        self.window.undo.undo()
        self.assertEqual(self.window.project.unit_system, "si")
        self.assertEqual(self.window.unit_selector.currentData(), "si")
        self.window.undo.redo()
        self.assertEqual(self.window.project.unit_system, "imperial")

    def test_existing_results_relabel_and_convert_without_reanalysis(self):
        self.finish_analysis()
        solver = self.window.result.solver
        revision = self.window.revision
        self.assertEqual(self.window.results_table.horizontalHeaderItem(5).text(), "FY (kN)")
        self.assertAlmostEqual(float(self.window.results_table.item(0, 5).text()), 15)
        self.window.set_units("imperial")
        self.assertIs(self.window.result.solver, solver)
        self.assertEqual(self.window.revision, revision)
        self.assertEqual(self.window.results_table.horizontalHeaderItem(5).text(), "FY (kip)")
        self.assertAlmostEqual(float(self.window.results_table.item(0, 5).text()), 15 / KIP_TO_KN, places=5)
        self.window.undo.undo()
        self.assertAlmostEqual(float(self.window.results_table.item(0, 5).text()), 15)

    def test_node_entry_uses_metres_and_preserves_untouched_values(self):
        self.window.select(("nodes", "N2"))
        fields = self.window.inspector.findChildren(QDoubleSpinBox)
        self.assertAlmostEqual(fields[0].value(), 3)
        original = self.window.project.nodes["N2"].x
        self.apply()
        self.assertEqual(self.window.project.nodes["N2"].x, original)
        fields = self.window.inspector.findChildren(QDoubleSpinBox)
        fields[0].setValue(4)
        self.apply()
        self.assertAlmostEqual(self.window.project.nodes["N2"].x, 4 / INCH_TO_METRE)
        self.window.undo.undo()
        self.assertEqual(self.window.project.nodes["N2"].x, original)

    def test_grid_entry_converts_and_canvas_snaps(self):
        self.window.select(None)
        field = self.window.inspector.findChild(QDoubleSpinBox)
        self.assertAlmostEqual(field.value(), 0.3048)
        field.setValue(0.25)
        self.apply()
        self.assertAlmostEqual(self.window.project.grid, 0.25 / INCH_TO_METRE)
        self.window.show()
        self.application.processEvents()
        self.window.view.fit()
        x, y = self.window.view.snapped(QPointF(20, -20))
        self.assertAlmostEqual(self.window.project.units.to_display(x, "length"), 0.5)
        self.assertAlmostEqual(self.window.project.units.to_display(y, "length"), 0.5)

    def test_distributed_inspector_uses_kn_per_metre(self):
        self.window.select(("loads", "L1"))
        fields = self.window.inspector.findChildren(QDoubleSpinBox)
        self.assertAlmostEqual(fields[0].value(), -10)
        self.assertAlmostEqual(fields[2].value(), -10)
        original = self.window.project.loads["L1"].magnitude
        self.apply()
        self.assertEqual(self.window.project.loads["L1"].magnitude, original)
        fields = self.window.inspector.findChildren(QDoubleSpinBox)
        fields[0].setValue(-20)
        self.apply()
        self.assertAlmostEqual(self.window.project.units.to_display(self.window.project.loads["L1"].magnitude, "intensity"), -20)

    def test_creation_dialog_converts_force_moment_and_distribution(self):
        for load_type, direction, value, quantity in (("Point", "FY", -12, "force"), ("Point", "MZ", 6, "moment"), ("Distributed", "FX", -2, "intensity")):
            self.window.selected = ("members", "M1")
            def accept(dialog):
                combos = dialog.findChildren(QComboBox)
                combos[0].setCurrentText(load_type)
                combos[1].setCurrentText(direction)
                dialog.findChildren(QDoubleSpinBox)[0].setValue(value)
                labels = [label.text() for label in dialog.findChildren(QLabel)]
                self.assertIn(self.window.project.units.moment if direction == "MZ" else f"Start ({self.window.project.units.intensity})" if load_type == "Distributed" else "kN", labels)
                return QDialog.DialogCode.Accepted
            count = len(self.window.project.loads)
            with patch.object(QDialog, "exec", accept):
                self.window.add_load()
            load = self.window.project.loads[f"L{count + 1}"]
            self.assertAlmostEqual(self.window.project.units.to_display(load.magnitude, quantity), value)

    def test_moment_inspector_and_direction_change_use_correct_dimensions(self):
        self.window.edit("Add moment", lambda p: p.loads.update({"L2": Load("L2", "N2", "MZ", p.units.from_display(5, "moment"))}))
        self.window.select(("loads", "L2"))
        spin = self.window.inspector.findChild(QDoubleSpinBox)
        self.assertAlmostEqual(spin.value(), 5)
        spin.setValue(7)
        self.apply()
        self.assertAlmostEqual(self.window.project.units.to_display(self.window.project.loads["L2"].magnitude, "moment"), 7)
        self.window.inspector.findChild(QComboBox, "load_direction").setCurrentText("FY")
        spin = self.window.inspector.findChild(QDoubleSpinBox)
        spin.setValue(8)
        self.apply()
        self.assertAlmostEqual(self.window.project.units.to_display(self.window.project.loads["L2"].magnitude, "force"), 8)

    def test_material_editor_units_conversion_and_noop_precision(self):
        project = self.window.project
        material = project.materials[project.default_material]
        editor = MaterialEditor(self.window, project, material, material.name)
        self.assertAlmostEqual(editor.E.value(), 200000)
        self.assertAlmostEqual(editor.rho.value(), 78.5)
        editor.accept()
        self.assertEqual(editor.definition, material)
        editor = MaterialEditor(self.window, project, material, material.name)
        editor.E.setValue(210000)
        editor.rho.setValue(77)
        editor.accept()
        self.assertAlmostEqual(project.units.to_display(editor.definition.E, "stress"), 210000)
        self.assertAlmostEqual(project.units.to_display(editor.definition.rho, "density"), 77)
        editor.close()

    def test_section_editor_units_conversion_and_noop_precision(self):
        project = self.window.project
        section = project.sections[project.default_section]
        editor = SectionEditor(self.window, project, section, section.name)
        self.assertAlmostEqual(editor.fields["A"].value(), 5000)
        self.assertAlmostEqual(editor.fields["Iz"].value(), 8e6)
        editor.accept()
        self.assertEqual(editor.definition, section)
        editor = SectionEditor(self.window, project, section, section.name)
        editor.fields["A"].setValue(6000)
        editor.fields["Iz"].setValue(9e6)
        editor.accept()
        self.assertAlmostEqual(project.units.to_display(editor.definition.A, "area"), 6000)
        self.assertAlmostEqual(project.units.to_display(editor.definition.Iz, "inertia"), 9e6)
        editor.close()

    def test_material_and_section_tables_show_si_values(self):
        material = MaterialDialog(self.window)
        self.assertEqual(material.table.horizontalHeaderItem(1).text(), "E (MPa)")
        self.assertAlmostEqual(float(material.table.item(0, 1).text()), 200000)
        self.assertIn("kN/m3", material.table.horizontalHeaderItem(3).text())
        section = SectionDialog(self.window)
        self.assertEqual(section.table.horizontalHeaderItem(1).text(), "Area (mm2)")
        self.assertEqual(section.table.horizontalHeaderItem(3).text(), "Iz (mm4)")
        self.assertAlmostEqual(float(section.table.item(0, 3).text()), 8e6)
        material.close()
        section.close()

    def test_open_diagrams_switch_all_axes_and_keep_analyzed_snapshot(self):
        result = solve(self.window.project)
        dialog = DiagramDialog(self.window, self.window.project, result)
        self.assertEqual(dialog.member_figure.axes[3].get_xlabel(), "Distance from start (m)")
        self.assertAlmostEqual(dialog.member_figure.axes[0].lines[0].get_xdata()[-1], 3)
        self.assertIn("kN-m", dialog.member_figure.axes[2].get_ylabel())
        raw = sample_member(dialog.project, dialog.result, "M1")["moment"].copy()
        self.window.set_units("imperial")
        self.assertEqual(dialog.member_figure.axes[3].get_xlabel(), "Distance from start (in)")
        self.assertIn("kip-in", dialog.quantity.itemText(1))
        self.window.undo.undo()
        self.assertEqual(dialog.structure_figure.axes[0].get_xlabel(), "X (m)")
        np.testing.assert_allclose(sample_member(dialog.project, dialog.result, "M1")["moment"], raw)
        dialog.close()

    def test_repeated_switches_have_no_model_drift(self):
        before = self.window.project.to_dict()
        for _ in range(20):
            self.window.set_units("imperial")
            self.window.set_units("si")
        self.assertEqual(self.window.project.to_dict(), before)

    def test_canvas_annotations_and_coordinates_use_si(self):
        labels = [item.text() for item in self.window.view.scene().items() if isinstance(item, QGraphicsSimpleTextItem)]
        self.assertTrue(any("-10 to -10 kN/m" in label for label in labels))
        self.window.show()
        self.application.processEvents()
        QTest.mouseMove(self.window.view.viewport(), self.window.view.mapFromScene(QPointF(0, 0)))
        self.assertIn(" m", self.window.coordinates.text())
        self.assertNotIn(" in", self.window.coordinates.text())

    def test_unit_input_widget_preserves_unrounded_canonical_value(self):
        value = 1.23456789012345
        widget = unit_number(value, UNIT_SYSTEMS["si"], "length")
        self.assertEqual(unit_value(widget, UNIT_SYSTEMS["si"]), value)
        widget.setValue(2)
        self.assertAlmostEqual(unit_value(widget, UNIT_SYSTEMS["si"]), 2 / INCH_TO_METRE)

    def test_units_switch_during_analysis_does_not_discard_result(self):
        revision = self.window.revision
        result = solve(self.window.project)
        self.window.analysis_revision = revision
        self.window.set_units("imperial")
        self.window.analysis_finished(result, "")
        self.assertIsNotNone(self.window.result)
        self.assertEqual(self.window.results_table.horizontalHeaderItem(5).text(), "FY (kip)")

    def test_new_project_keeps_selected_units(self):
        self.window.new_project()
        self.assertEqual(self.window.project.unit_system, "si")
        self.assertFalse(self.window.project.members)

    def test_cantilever_result_table_converts_all_dimensional_columns(self):
        project = si_beam()
        project.nodes["N1"].support = "fixed"
        project.nodes["N2"].support = "free"
        project.loads = {"L1": Load("L1", "N2", "FY", project.units.from_display(-30, "force")),
                         "L2": Load("L2", "N2", "MZ", project.units.from_display(6, "moment"))}
        self.window.load_project(project)
        self.finish_analysis()
        self.assertAlmostEqual(float(self.window.results_table.item(0, 5).text()), 30)
        self.assertAlmostEqual(float(self.window.results_table.item(0, 6).text()), 84)
        result = self.window.result
        tip = result.displacements["N2"]
        self.assertAlmostEqual(float(self.window.results_table.item(1, 2).text()), project.units.to_display(tip[1], "length"), places=6)
        self.assertAlmostEqual(float(self.window.results_table.item(1, 3).text()), tip[2], places=6)
        self.window.set_units("imperial")
        self.assertAlmostEqual(float(self.window.results_table.item(0, 6).text()), result.reactions["N1"][2], places=3)

    def test_units_switch_keeps_undefined_hinged_rotations(self):
        project = self.window.project.clone()
        project.members["M1"].release_start = project.members["M1"].release_end = True
        self.window.load_project(project)
        self.finish_analysis()
        self.window.set_units("imperial")
        self.assertEqual(self.window.results_table.item(0, 3).text(), "n/a")
        self.assertEqual(self.window.results_table.item(0, 6).text(), "0")

    def test_grid_dialog_uses_metres(self):
        def accept(dialog):
            labels = [label.text() for label in dialog.findChildren(QLabel)]
            self.assertIn("Grid (m)", labels)
            dialog.findChild(QDoubleSpinBox).setValue(0.5)
            return QDialog.DialogCode.Accepted
        with patch.object(QDialog, "exec", accept):
            self.window.settings()
        self.assertAlmostEqual(self.window.project.units.to_display(self.window.project.grid, "length"), 0.5)
