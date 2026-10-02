"""Material persistence, mixed stiffness, inheritance, and UI assignments."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import tempfile
import unittest
from pathlib import Path

from PySide6.QtWidgets import QApplication, QComboBox, QPushButton
from pynitegui.qt.analysis import analyze
from pynitegui.qt.app import MainWindow
from pynitegui.qt.materials import MaterialDialog, MaterialEditor
from pynitegui.qt.model import Material, Project, Load


class MaterialTests(unittest.TestCase):
    def test_legacy_file_preserves_custom_properties(self):
        legacy = Project().to_dict()
        legacy["version"] = 1
        legacy.pop("materials")
        legacy.pop("default_material")
        legacy.pop("sections")
        legacy.pop("default_section")
        legacy.update(A=10.3, Iy=15.3, Iz=510.0, J=0.506)
        legacy.update(E=12345, nu=0.24, rho=0.0001)
        legacy["nodes"] = {"N1": {"name": "N1", "x": 0, "y": 0, "support": "fixed"}, "N2": {"name": "N2", "x": 120, "y": 0, "support": "free"}}
        legacy["members"] = {"M1": {"name": "M1", "start": "N1", "end": "N2"}}
        project = Project.from_dict(legacy)
        self.assertEqual((project.E, project.nu, project.rho), (12345, 0.24, 0.0001))
        self.assertEqual(project.members["M1"].material, "Project material")
        self.assertEqual(project.to_dict()["version"], 8)
        self.assertEqual(project.to_dict(), Project.from_dict(project.to_dict()).to_dict())

    def test_mixed_material_axial_stiffness(self):
        project = Project()
        project.set_material(Material("Soft", 10000, 0.3, 0))
        project.add_member((0, 0), (120, 0))
        project.add_member((120, 0), (240, 0))
        project.members["M2"].material = "Soft"
        project.nodes["N1"].support = "fixed"
        project.loads["L1"] = Load("L1", "N3", "FX", 5)
        result = analyze(project)
        expected = 5 / project.A * (120 / 29000 + 120 / 10000)
        self.assertAlmostEqual(result.displacements["N3"][0], expected, places=9)
        self.assertAlmostEqual(result.displacements["N2"][0], 5 * 120 / (29000 * project.A), places=9)
        self.assertEqual(result.solver.members["M2"].material.E, 10000)

    def test_new_default_does_not_reassign_existing_members(self):
        project = Project()
        project.add_member((0, 0), (120, 0))
        project.set_material(Material("Other", 20000, 0.2, 0))
        project.default_material = "Other"
        project.add_member((120, 0), (240, 0))
        self.assertEqual(project.members["M1"].material, "Steel_A992")
        self.assertEqual(project.members["M2"].material, "Other")

    def test_split_and_connect_inherit_material(self):
        project = Project()
        project.set_material(Material("Other", 20000, 0.2, 0))
        project.add_member((0, 0), (120, 0))
        project.members["M1"].material = "Other"
        project.add_member((60, -60), (60, 60))
        project.connect_intersections()
        for member in project.members.values():
            a, b = project.nodes[member.start], project.nodes[member.end]
            self.assertEqual(member.material, "Other" if a.y == b.y else "Steel_A992")
        segments = project.split_member("M1", 0.5)
        self.assertTrue(all(project.members[name].material == "Other" for name in segments))

    def test_rename_updates_default_and_assignments(self):
        project = Project()
        project.add_member((0, 0), (120, 0))
        project.set_material(Material("Steel", 30000, 0.3, 0.001), "Steel_A992")
        self.assertEqual(project.default_material, "Steel")
        self.assertEqual(project.members["M1"].material, "Steel")
        self.assertNotIn("Steel_A992", project.materials)
        project.validate()

    def test_delete_protects_used_and_default_materials(self):
        project = Project()
        with self.assertRaisesRegex(ValueError, "default"):
            project.delete_material("Steel_A992")
        project.set_material(Material("Other", 10000, 0.3, 0))
        project.add_member((0, 0), (120, 0))
        project.members["M1"].material = "Other"
        with self.assertRaisesRegex(ValueError, "M1"):
            project.delete_material("Other")
        project.members["M1"].material = "Steel_A992"
        project.delete_material("Other")
        self.assertNotIn("Other", project.materials)

    def test_round_trip_and_no_shared_definitions(self):
        project = Project()
        project.set_material(Material("Other", 10000, 0.2, 0.001))
        project.default_material = "Other"
        project.add_member((0, 0), (120, 0))
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "mixed.pynite.json"
            project.save(path)
            self.assertEqual(project.to_dict(), Project.open(path).to_dict())
        copied = project.clone()
        copied.materials["Other"].E = 20000
        self.assertEqual(project.materials["Other"].E, 10000)

    def test_invalid_materials_and_references(self):
        for definition in (Material(""), Material("bad", 0), Material("bad", float("nan")), Material("bad", nu=0.5), Material("bad", rho=-1)):
            with self.assertRaises(ValueError):
                definition.validate()
        project = Project()
        project.add_member((0, 0), (120, 0))
        project.members["M1"].material = "missing"
        with self.assertRaisesRegex(ValueError, "M1.*missing"):
            project.validate()
        with self.assertRaisesRegex(ValueError, "already exists"):
            Project().set_material(Material("Steel_A992"))


class MaterialEditorTests(unittest.TestCase):
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

    def test_assignment_is_undoable_and_invalidates_results(self):
        self.window.edit("Add material", lambda p: p.set_material(Material("Other", 10000, 0.3, 0)))
        self.window.edit("Add member", lambda p: p.add_member((0, 0), (120, 0)))
        self.window.select(("members", "M1"))
        selector = next(widget for widget in self.window.inspector.findChildren(QComboBox) if "Other" in [widget.itemText(i) for i in range(widget.count())])
        selector.setCurrentText("Other")
        self.window.result = object()
        self.window.deformed_action.setEnabled(True)
        button = next(button for button in self.window.inspector.findChildren(QPushButton) if button.text() == "Apply")
        button.click()
        self.assertEqual(self.window.project.members["M1"].material, "Other")
        self.assertIsNone(self.window.result)
        self.assertFalse(self.window.deformed_action.isEnabled())
        self.window.undo.undo()
        self.assertEqual(self.window.project.members["M1"].material, "Steel_A992")
        self.window.undo.redo()
        self.assertEqual(self.window.project.members["M1"].material, "Other")

    def test_manager_default_and_unused_delete(self):
        self.window.edit("Add material", lambda p: p.set_material(Material("Other", 10000, 0.3, 0)))
        dialog = MaterialDialog(self.window)
        dialog.refresh("Other")
        self.assertTrue(dialog.delete_button.isEnabled())
        dialog.set_default()
        self.assertEqual(self.window.project.default_material, "Other")
        self.assertFalse(dialog.delete_button.isEnabled())
        dialog.refresh("Steel_A992")
        dialog.set_default()
        dialog.refresh("Other")
        dialog.delete_material()
        self.assertNotIn("Other", self.window.project.materials)
        self.window.undo.undo()
        self.assertIn("Other", self.window.project.materials)
        dialog.close()

    def test_unchanged_definition_preserves_exact_density(self):
        project = self.window.project
        original = project.materials[project.default_material]
        dialog = MaterialEditor(self.window, project, original, original.name)
        dialog.accept()
        self.assertEqual(dialog.definition.rho, original.rho)
        self.assertEqual(dialog.definition.E, original.E)
        self.assertEqual(dialog.definition.nu, original.nu)
        dialog.close()


if __name__ == "__main__":
    unittest.main()
