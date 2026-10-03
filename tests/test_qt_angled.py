"""Angled point forces remain single editable loads and resolve at the solver boundary."""
import contextlib
import io
import math
import os
import unittest
from dataclasses import replace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QTimer, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QComboBox, QDialog, QDoubleSpinBox, QLabel, QPushButton
from pynitegui.qt.analysis import analyze
from pynitegui.qt.app import MainWindow, EngineeringSymbol
from pynitegui.qt.model import Load, Project


def beam(target="M1", angle=-30):
    project = Project()
    project.add_member((0, 0), (240, 0))
    project.nodes["N1"].support = "pin"
    project.nodes["N2"].support = "roller"
    project.loads["L1"] = Load("L1", target, "Angle", 10, angle=angle)
    return project


def solve(project):
    with contextlib.redirect_stdout(io.StringIO()):
        return analyze(project)


class AngledModelTests(unittest.TestCase):
    def test_cardinal_and_oblique_components(self):
        for angle, expected in ((0, (10, 0)), (90, (0, 10)), (-90, (0, -10)), (180, (-10, 0)),
                                (-30, (5 * math.sqrt(3), -5))):
            values = Load("L1", "M1", "Angle", 10, angle=angle).components()
            self.assertEqual([item[0] for item in values], ["FX", "FY"])
            for (_, actual), value in zip(values, expected):
                self.assertAlmostEqual(actual, value)

    def test_member_and_nodal_forces_match_resolved_loads(self):
        for target in ("M1", "N2"):
            project = beam(target)
            angled = solve(project)
            resolved = project.clone()
            load = resolved.loads.pop("L1")
            for index, (direction, magnitude) in enumerate(load.components()):
                name = f"L{index + 1}"
                resolved.loads[name] = replace(load, name=name, direction=direction, magnitude=magnitude)
            manual = solve(resolved)
            for name in project.nodes:
                for actual, expected in zip(angled.displacements[name] + angled.reactions[name],
                                            manual.displacements[name] + manual.reactions[name]):
                    self.assertAlmostEqual(actual, expected)
            self.assertAlmostEqual(angled.reactions["N1"][0], -5 * math.sqrt(3))
            self.assertAlmostEqual(sum(values[1] for values in angled.reactions.values()), 5)

    def test_save_roundtrip_and_legacy_defaults(self):
        project = beam()
        self.assertEqual(project.to_dict()["version"], 12)
        self.assertEqual(Project.from_dict(project.to_dict()).to_dict(), project.to_dict())
        data = project.to_dict()
        data["version"] = 7
        data["loads"]["L1"]["direction"] = "FY"
        del data["loads"]["L1"]["angle"]
        restored = Project.from_dict(data)
        self.assertEqual(restored.loads["L1"].direction, "FY")
        self.assertEqual(restored.loads["L1"].magnitude, 10)

    def test_split_at_load_preserves_vector_and_solution(self):
        project = beam()
        before = solve(project)
        project.split_member("M1", 0.5)
        self.assertIn(project.loads["L1"].target, project.nodes)
        self.assertEqual(project.loads["L1"].components(), beam().loads["L1"].components())
        after = solve(project)
        for name in ("N1", "N2"):
            for actual, expected in zip(after.reactions[name], before.reactions[name]):
                self.assertAlmostEqual(actual, expected)

    def test_negative_combination_factor_reverses_components(self):
        project = beam()
        project.set_combination("Reverse", {"Case 1": -2})
        result = solve(project)
        reverse = result.for_combination("Reverse")
        for name in project.nodes:
            for actual, original in zip(reverse.reactions[name], result.reactions[name]):
                self.assertAlmostEqual(actual, -2 * original)

    def test_signed_force_reverses_solution_and_roundtrips(self):
        project = beam()
        positive = solve(project)
        project.loads["L1"].magnitude = -10
        restored = Project.from_dict(project.to_dict())
        self.assertEqual(restored.loads["L1"].magnitude, -10)
        negative = solve(restored)
        for name in project.nodes:
            for actual, original in zip(negative.reactions[name], positive.reactions[name]):
                self.assertAlmostEqual(actual, -original)

    def test_invalid_angles_magnitudes_and_distributed_direction(self):
        for changes in ({"angle": float("nan")}, {"angle": float("inf")}, {"angle": 361},
                        {"magnitude": float("inf")}, {"kind": "distributed", "direction": "MZ"}):
            project = beam()
            project.loads["L1"] = replace(project.loads["L1"], **changes)
            with self.assertRaises(ValueError):
                project.validate()


class AngledEditorTests(unittest.TestCase):
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

    def test_inspector_edit_and_undo(self):
        self.window.select(("loads", "L1"))
        angle = self.window.inspector.findChild(QDoubleSpinBox, "load_angle")
        angle.setValue(45)
        next(button for button in self.window.inspector.findChildren(QPushButton) if button.text() == "Apply").click()
        self.assertEqual(self.window.project.loads["L1"].angle, 45)
        self.window.undo.undo()
        self.assertEqual(self.window.project.loads["L1"].angle, -30)
        self.window.undo.redo()
        self.assertEqual(self.window.project.loads["L1"].angle, 45)

    def test_creation_uses_current_force_units_on_node_and_member(self):
        self.window.set_units("si")
        for selection in (("nodes", "N2"), ("members", "M1")):
            self.window.select(selection)
            def accept():
                dialog = self.application.activeModalWidget()
                combos = dialog.findChildren(QComboBox)
                combos[1].setCurrentText("Angle")
                dialog.findChildren(QDoubleSpinBox)[0].setValue(20)
                dialog.findChild(QDoubleSpinBox, "load_angle").setValue(-45)
                self.assertTrue(any("FX 14.1421" in label.text() for label in dialog.findChildren(QLabel)))
                dialog.accept()
            QTimer.singleShot(0, accept)
            self.window.add_load()
            load = list(self.window.project.loads.values())[-1]
            self.assertEqual(load.target, selection[1])
            self.assertEqual(load.direction, "Angle")
            self.assertEqual(load.angle, -45)
            self.assertAlmostEqual(self.window.project.units.to_display(load.magnitude, "force"), 20)

    def test_canvas_retains_single_angled_arrow_and_label(self):
        glyphs = [item for item in self.window.view.scene().items()
                  if isinstance(item, EngineeringSymbol) and item.kind == "load"]
        self.assertEqual(len(glyphs), 1)
        self.assertEqual(glyphs[0].value, ("Angle", 10, -30))
        self.window.set_units("si")
        self.assertEqual(self.window.project.loads["L1"].angle, -30)
        self.window.select(("loads", "L1"))
        self.assertTrue(any("kN" in label.text() and "FX" in label.text()
                            for label in self.window.inspector.findChildren(QLabel)))

    def test_inspector_switch_from_signed_force_to_angle(self):
        self.window.project.loads["L1"].direction = "FY"
        self.window.project.loads["L1"].magnitude = -10
        self.window.select(("loads", "L1"))
        self.window.inspector.findChild(QComboBox, "load_direction").setCurrentText("Angle")
        next(button for button in self.window.inspector.findChildren(QPushButton) if button.text() == "Apply").click()
        self.assertEqual(self.window.project.loads["L1"].magnitude, -10)
        self.window.project.validate()

    def test_typing_signed_and_large_magnitudes_in_inspector(self):
        for units in ("imperial", "si"):
            self.window.set_units(units)
            self.window.select(("loads", "L1"))
            field = self.window.inspector.findChild(QDoubleSpinBox, "load_magnitude")
            for text in ("-10", "-12345.125", "123456789.125", "0", "-10"):
                field.lineEdit().selectAll()
                QTest.keyClicks(field.lineEdit(), text)
                QTest.keyClick(field.lineEdit(), Qt.Key.Key_Return)
                self.assertEqual(field.value(), float(text))
            next(button for button in self.window.inspector.findChildren(QPushButton) if button.text() == "Apply").click()
            self.assertAlmostEqual(self.window.project.units.to_display(self.window.project.loads["L1"].magnitude, "force"), -10)
            self.window.project.validate()

    def test_typing_negative_force_in_creation_dialog(self):
        self.window.select(("nodes", "N2"))
        def accept():
            dialog = self.application.activeModalWidget()
            dialog.findChildren(QComboBox)[1].setCurrentText("Angle")
            field = dialog.findChild(QDoubleSpinBox, "load_magnitude")
            field.lineEdit().selectAll()
            QTest.keyClicks(field.lineEdit(), "-10")
            QTest.keyClick(field.lineEdit(), Qt.Key.Key_Return)
            self.assertEqual(field.value(), -10)
            self.assertTrue(any("FY 10 kip" in label.text() for label in dialog.findChildren(QLabel)))
            dialog.accept()
        QTimer.singleShot(0, accept)
        self.window.add_load()
        self.assertEqual(self.window.project.loads["L2"].magnitude, -10)
        self.assertEqual(self.window.project.loads["L2"].components(), [("FX", 0), ("FY", 10)])

    def test_factored_arrow_reverses_without_splitting_load(self):
        self.window.project.set_combination("Reverse", {"Case 1": -2})
        self.window.analysis_revision = self.window.revision
        self.window.analysis_finished(solve(self.window.project), "")
        self.window.select_result_combination("Reverse")
        glyphs = [item for item in self.window.view.scene().items()
                  if isinstance(item, EngineeringSymbol) and item.kind == "load"]
        self.assertEqual(len(glyphs), 1)
        self.assertEqual(glyphs[0].value, ("Angle", -20, -30))

    def test_dialog_component_preview_has_room_for_two_lines(self):
        self.window.select(("nodes", "N2"))
        def accept():
            dialog = self.application.activeModalWidget()
            dialog.findChildren(QComboBox)[1].setCurrentText("Angle")
            dialog.findChild(QDoubleSpinBox, "load_angle").setValue(45)
            self.application.processEvents()
            preview = next(label for label in dialog.findChildren(QLabel) if label.text().startswith("FX "))
            self.assertEqual(len(preview.text().splitlines()), 2)
            self.assertFalse(preview.wordWrap())
            self.assertGreaterEqual(preview.height(), 2 * preview.fontMetrics().lineSpacing())
            for line in preview.text().splitlines():
                self.assertGreaterEqual(preview.width(), preview.fontMetrics().horizontalAdvance(line))
            self.assertGreaterEqual(dialog.width(), 360)
            dialog.reject()
        QTimer.singleShot(0, accept)
        self.window.add_load()


if __name__ == "__main__":
    unittest.main()
