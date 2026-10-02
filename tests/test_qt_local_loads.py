"""Global and member-relative loading must agree with resolved physical vectors."""
import contextlib
import io
import math
import os
import unittest
from dataclasses import replace
from unittest.mock import patch
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication, QComboBox, QDialog, QDoubleSpinBox, QGraphicsSimpleTextItem, QLabel, QPushButton
from pynitegui.qt.analysis import analyze
from pynitegui.qt.app import MainWindow, EngineeringSymbol, load_directions
from pynitegui.qt.model import Project, Load


def cantilever(end=(120, 160)):
    project = Project()
    project.add_member((0, 0), end)
    project.nodes["N1"].support = "fixed"
    return project


def solve(project):
    with contextlib.redirect_stdout(io.StringIO()):
        return analyze(project)


class LocalLoadTests(unittest.TestCase):
    def test_local_axes_inclined_vertical_horizontal_and_reversed(self):
        for end in ((120, 160), (0, 200), (0, -200), (200, 0), (-120, -160)):
            project = cantilever(end)
            length = math.hypot(*end)
            tangent = end[0] / length, end[1] / length
            normal = -tangent[1], tangent[0]
            for direction, vector in (("Local x", tangent), ("Local y", normal)):
                load = Load("L1", "M1", direction, 10)
                for (_, actual), component in zip(load.components(project), vector):
                    self.assertAlmostEqual(actual, 10 * component)
            angled = Load("L1", "M1", "Local angle", 10, angle=90)
            self.assertAlmostEqual(angled.components(project)[0][1], 10 * normal[0])
            self.assertAlmostEqual(angled.components(project)[1][1], 10 * normal[1])

    def test_partial_triangular_global_angle_resultant_and_moment(self):
        project = cantilever()
        load = Load("L1", "M1", "Angle", 0, 0.15, "distributed", 0.5, 0.8, angle=-30)
        project.loads[load.name] = load
        result = solve(project)
        total = 0.5 * 0.5 * 130
        distance = 30 + 2 * 130 / 3
        base = math.atan2(160, 120)
        force_angle = math.radians(-30)
        self.assertAlmostEqual(result.reactions["N1"][0], -total * math.cos(force_angle))
        self.assertAlmostEqual(result.reactions["N1"][1], -total * math.sin(force_angle))
        self.assertAlmostEqual(result.reactions["N1"][2], -total * distance * math.sin(force_angle - base))

    def test_local_point_and_distributed_match_manual_components(self):
        for direction in ("Local x", "Local y", "Local angle", "Angle"):
            for kind in ("point", "distributed"):
                project = cantilever()
                load = Load("L1", "M1", direction, -0.2 if kind == "distributed" else -10,
                            0.2, kind, 0.4, 0.85, angle=30)
                project.loads[load.name] = load
                result = solve(project)
                manual = project.clone()
                manual.loads.clear()
                for index, ((axis, start), (_, end)) in enumerate(zip(load.components(project), load.components(project, load.end_magnitude))):
                    name = f"L{index + 1}"
                    manual.loads[name] = replace(load, name=name, direction=axis, magnitude=start, end_magnitude=end)
                expected = solve(manual)
                for name in project.nodes:
                    for actual, value in zip(result.reactions[name] + result.displacements[name], expected.reactions[name] + expected.displacements[name]):
                        self.assertAlmostEqual(actual, value)

    def test_local_distributed_split_preserves_loading_and_solution(self):
        project = cantilever()
        project.loads["L1"] = Load("L1", "M1", "Local angle", -0.2, 0.1, "distributed", 0.4, 0.9, angle=45)
        before = solve(project)
        project.split_member("M1", 0.5)
        self.assertEqual(len(project.loads), 2)
        self.assertTrue(all(load.direction == "Local angle" and load.angle == 45 for load in project.loads.values()))
        after = solve(project)
        for actual, expected in zip(after.reactions["N1"] + after.displacements["N2"], before.reactions["N1"] + before.displacements["N2"]):
            self.assertAlmostEqual(actual, expected)

    def test_local_point_at_split_becomes_equivalent_global_nodal_force(self):
        project = cantilever()
        project.loads["L1"] = Load("L1", "M1", "Local y", -10)
        vector = project.loads["L1"].components(project)
        before = solve(project)
        project.split_member("M1", 0.5)
        load = project.loads["L1"]
        self.assertEqual(load.direction, "Angle")
        self.assertIn(load.target, project.nodes)
        for (_, actual), (_, expected) in zip(load.components(), vector):
            self.assertAlmostEqual(actual, expected)
        after = solve(project)
        for actual, expected in zip(after.reactions["N1"], before.reactions["N1"]):
            self.assertAlmostEqual(actual, expected)

    def test_local_vector_follows_member_geometry(self):
        project = cantilever((200, 0))
        load = Load("L1", "M1", "Local y", 10)
        self.assertEqual(load.components(project), [("FX", 0), ("FY", 10)])
        project.nodes["N2"].x, project.nodes["N2"].y = 0, 200
        self.assertAlmostEqual(load.components(project)[0][1], -10)
        self.assertEqual(load.components(project)[1][1], 0)

    def test_persistence_legacy_and_invalid_nodal_local_force(self):
        project = cantilever()
        project.loads["L1"] = Load("L1", "M1", "Local angle", -0.2, 0, "distributed", -0.4, angle=-45)
        self.assertEqual(Project.from_dict(project.to_dict()).to_dict(), project.to_dict())
        legacy = project.to_dict()
        legacy["version"] = 9
        legacy["loads"]["L1"]["direction"] = "FY"
        restored = Project.from_dict(legacy)
        self.assertEqual(restored.loads["L1"].direction, "FY")
        project.loads["L1"] = Load("L1", "N2", "Local y", 10)
        with self.assertRaisesRegex(ValueError, "member target"):
            project.validate()


class LocalLoadEditorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = MainWindow()
        self.window.load_project(cantilever())
        self.window.set_units("si")

    def tearDown(self):
        self.window.saved = self.window.project.to_dict()
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()

    def test_creation_distributed_angle_and_local_intensity_units(self):
        for direction in ("Angle", "Local x", "Local y", "Local angle"):
            self.window.selected = ("members", "M1")
            def accept(dialog):
                combos = dialog.findChildren(QComboBox)
                combos[0].setCurrentText("Distributed")
                combos[1].setCurrentText(direction)
                dialog.findChild(QDoubleSpinBox, "load_magnitude").setValue(-10)
                dialog.findChild(QDoubleSpinBox, "load_angle").setValue(30)
                dialog.findChild(QDoubleSpinBox, "load_end_magnitude").setValue(-20)
                preview = next(label for label in dialog.findChildren(QLabel) if label.text().startswith("FX "))
                self.assertIn("to", preview.text())
                self.assertIn("kN/m", preview.text())
                return QDialog.DialogCode.Accepted
            with patch.object(QDialog, "exec", accept):
                self.window.add_load()
            load = list(self.window.project.loads.values())[-1]
            self.assertEqual(load.direction, direction)
            self.assertAlmostEqual(self.window.project.units.to_display(load.magnitude, "intensity"), -10)
            self.assertAlmostEqual(self.window.project.units.to_display(load.end_magnitude, "intensity"), -20)
            self.assertEqual(load.angle, 30)
        self.assertFalse(any(direction.startswith("Local") for direction in load_directions(False, "point")))

    def test_local_target_changed_to_node_keeps_global_vector(self):
        self.window.edit("Local force", lambda p: p.loads.update({"L1": Load("L1", "M1", "Local y", 10)}))
        self.window.select(("loads", "L1"))
        target = next(combo for combo in self.window.inspector.findChildren(QComboBox) if combo.findText("N2") >= 0)
        target.setCurrentText("N2")
        self.assertEqual(self.window.inspector.findChild(QComboBox, "load_direction").currentText(), "Angle")
        next(button for button in self.window.inspector.findChildren(QPushButton) if button.text() == "Apply").click()
        load = self.window.project.loads["L1"]
        self.assertEqual(load.target, "N2")
        self.assertAlmostEqual(load.components()[0][1], -8, places=12)
        self.assertAlmostEqual(load.components()[1][1], 6, places=12)

    def test_unedited_angle_and_intensity_retain_full_precision(self):
        self.window.edit("Local distribution", lambda p: p.loads.update({"L1": Load("L1", "M1", "Local angle", -0.123456789, 0, "distributed", -0.345678912, angle=13.123456789)}))
        before = self.window.project.to_dict()
        self.window.select(("loads", "L1"))
        next(button for button in self.window.inspector.findChildren(QPushButton) if button.text() == "Apply").click()
        self.assertEqual(self.window.project.to_dict(), before)

    def test_distributed_arrows_follow_local_orientation_and_signed_ramp(self):
        self.window.edit("Local distribution", lambda p: p.loads.update({"L1": Load("L1", "M1", "Local y", -0.2, 0, "distributed", 0.2)}))
        arrows = [item for item in self.window.view.scene().items() if isinstance(item, EngineeringSymbol) and item.kind == "load"]
        self.assertEqual(len(arrows), 8)
        self.assertTrue(all(item.value[0] == "Angle" for item in arrows))
        self.assertTrue(any(item.value[1] < 0 for item in arrows))
        self.assertTrue(any(item.value[1] > 0 for item in arrows))
        for arrow in arrows:
            self.assertAlmostEqual(arrow.value[2], math.degrees(math.atan2(160, 120)) + 90)

    def test_load_label_reflows_around_arrows_after_fit(self):
        self.window.edit("Local distribution", lambda p: p.loads.update({"L1": Load("L1", "M1", "Local y", -0.2, 0, "distributed", -0.4)}))
        self.window.show()
        self.app.processEvents()
        self.window.view.fit()
        transform = self.window.view.viewportTransform()
        label = next(item for item in self.window.view.scene().items()
                     if isinstance(item, QGraphicsSimpleTextItem) and item.text().startswith("L1:"))
        rect = label.deviceTransform(transform).mapRect(label.boundingRect())
        for item in self.window.view.scene().items():
            if isinstance(item, EngineeringSymbol) and item.kind == "load":
                self.assertFalse(rect.intersects(item.deviceTransform(transform).mapRect(item.boundingRect())))


if __name__ == "__main__":
    unittest.main()
