"""Custom support constraints must map exactly to PyNite degrees of freedom."""
import contextlib
import io
import os
import unittest
from dataclasses import replace
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication, QCheckBox, QComboBox, QPushButton
from pynitegui.qt.analysis import analyze
from pynitegui.qt.app import MainWindow
from pynitegui.qt.model import Node, Project, Load


def solve(project):
    with contextlib.redirect_stdout(io.StringIO()):
        return analyze(project)


class SupportTests(unittest.TestCase):
    def beam(self):
        project = Project()
        project.add_member((0, 0), (240, 0))
        project.nodes["N1"].support = "pin"
        project.nodes["N2"].support = "roller"
        project.loads["L1"] = Load("L1", "M1", "FY", -10)
        return project

    def test_presets_match_custom_constraints(self):
        project = self.beam()
        original = solve(project)
        for node in project.nodes.values():
            node.restraint_x, node.restraint_y, node.restraint_rz = node.restraints
            node.support = "custom"
        custom = solve(project)
        for name in project.nodes:
            for expected, actual in zip(original.reactions[name] + original.displacements[name], custom.reactions[name] + custom.displacements[name]):
                self.assertAlmostEqual(expected, actual)

    def test_horizontal_only_support_and_rotation_restraint(self):
        project = self.beam()
        project.nodes["N1"] = Node("N1", 0, 0, "custom", True, False, False)
        project.nodes["N2"].support = "fixed"
        result = solve(project)
        self.assertEqual(result.solver.nodes["N1"].support_DX, True)
        self.assertEqual(result.solver.nodes["N1"].support_DY, False)
        self.assertEqual(result.solver.nodes["N1"].support_RZ, False)
        self.assertAlmostEqual(result.reactions["N2"][1], 10)
        project.nodes["N1"] = Node("N1", 0, 0, "pin")
        project.nodes["N2"] = Node("N2", 240, 0, "custom", False, False, True)
        project.loads["L1"].target = "N2"
        result = solve(project)
        self.assertAlmostEqual(result.reactions["N2"][2], 2400)
        self.assertAlmostEqual(result.displacements["N2"][2], 0)

    def test_custom_empty_support_does_not_count_as_restraint(self):
        project = self.beam()
        for node in project.nodes.values():
            node.support = "custom"
        with self.assertRaisesRegex(ValueError, "Assign supports"):
            solve(project)

    def test_persistence_and_boolean_validation(self):
        project = self.beam()
        project.nodes["N1"] = Node("N1", 0, 0, "custom", True, True, False)
        restored = Project.from_dict(project.to_dict())
        self.assertEqual(restored.nodes["N1"].restraints, (True, True, False))
        project.nodes["N1"].restraint_x = 1
        with self.assertRaisesRegex(ValueError, "boolean"):
            project.validate()

    def test_restrained_hinge_joint_has_real_rotation_support(self):
        project = self.beam()
        project.members["M1"].release_start = True
        project.members["M1"].release_end = True
        project.nodes["N1"] = Node("N1", 0, 0, "custom", True, True, True)
        self.assertNotIn("N1", project.inactive_rotations())


class SupportEditorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_checkbox_edit_and_undo(self):
        window = MainWindow()
        window.example()
        window.select(("nodes", "N1"))
        combo = next(widget for widget in window.inspector.findChildren(QComboBox) if widget.findText("custom") >= 0)
        combo.setCurrentText("custom")
        window.inspector.findChild(QCheckBox, "restraint_rz").setChecked(True)
        next(button for button in window.inspector.findChildren(QPushButton) if button.text() == "Apply").click()
        self.assertEqual(window.project.nodes["N1"].restraints, (True, True, True))
        window.undo.undo()
        self.assertEqual(window.project.nodes["N1"].support, "pin")
        window.saved = window.project.to_dict()
        window.close()
        window.deleteLater()
        self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
