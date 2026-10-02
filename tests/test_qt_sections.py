"""Section assignments, persistence, mixed stiffness, and editor lifecycle."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtWidgets import QApplication, QComboBox, QPushButton
from pynitegui.qt.analysis import analyze
from pynitegui.qt.app import MainWindow
from pynitegui.qt.model import Load, Material, Project, Section
from pynitegui.qt.sections import SectionDialog, SectionEditor


class SectionTests(unittest.TestCase):
    def test_mixed_inertia_cantilever_matches_integrated_deflection(self):
        project = Project()
        project.set_section(Section("Double inertia", project.A, project.Iy, 2 * project.Iz, project.J))
        project.add_member((0, 0), (120, 0))
        project.add_member((120, 0), (240, 0))
        project.members["M2"].section = "Double inertia"
        project.nodes["N1"].support = "fixed"
        project.loads["L1"] = Load("L1", "N3", "FY", -2)
        result = analyze(project)
        expected = -2 / project.E * ((240**3 - 120**3) / (3 * project.Iz) + 120**3 / (6 * project.Iz))
        self.assertAlmostEqual(result.displacements["N3"][1], expected, places=8)
        self.assertAlmostEqual(result.reactions["N1"][1], 2, places=8)
        self.assertAlmostEqual(result.reactions["N1"][2], 480, places=8)

    def test_mixed_area_axial_stiffness(self):
        project = Project()
        project.set_section(Section("Double area", 2 * project.A, project.Iy, project.Iz, project.J))
        project.add_member((0, 0), (120, 0))
        project.add_member((120, 0), (240, 0))
        project.members["M2"].section = "Double area"
        project.nodes["N1"].support = "fixed"
        project.loads["L1"] = Load("L1", "N3", "FX", 5)
        result = analyze(project)
        self.assertAlmostEqual(result.displacements["N3"][0], 5 * (120 + 60) / (project.E * project.A), places=9)

    def test_version_one_and_two_migrate_shared_section(self):
        for version in (1, 2):
            project = Project()
            project.set_material(Material("Custom", 10000, 0.2, 0.001))
            project.default_material = "Custom"
            project.add_member((0, 0), (120, 0))
            data = project.to_dict()
            data["version"] = version
            data.pop("sections")
            data.pop("default_section")
            data.update(A=2.5, Iy=12, Iz=345, J=0.15)
            data["members"]["M1"].pop("section")
            if version == 1:
                data.pop("materials")
                data.pop("default_material")
                data.update(E=10000, nu=0.2, rho=0.001)
                data["members"]["M1"].pop("material")
            restored = Project.from_dict(data)
            self.assertEqual((restored.A, restored.Iy, restored.Iz, restored.J), (2.5, 12, 345, 0.15))
            self.assertEqual(restored.members["M1"].section, "Project section")
            self.assertEqual(restored.materials[restored.members["M1"].material].E, 10000)
            self.assertEqual(restored.to_dict()["version"], 4)

    def test_new_default_only_affects_new_members(self):
        project = Project()
        project.add_member((0, 0), (120, 0))
        project.set_section(Section("Other", 5, 10, 100, 0.2))
        project.default_section = "Other"
        project.add_member((120, 0), (240, 0))
        self.assertEqual(project.members["M1"].section, "W18x35")
        self.assertEqual(project.members["M2"].section, "Other")

    def test_split_and_connect_keep_section(self):
        project = Project()
        project.set_section(Section("Other", 5, 10, 100, 0.2))
        project.add_member((0, 0), (120, 0))
        project.members["M1"].section = "Other"
        project.add_member((60, -60), (60, 60))
        project.connect_intersections()
        for member in project.members.values():
            a, b = project.nodes[member.start], project.nodes[member.end]
            self.assertEqual(member.section, "Other" if a.y == b.y else "W18x35")
        segments = project.split_member("M1", 0.5)
        self.assertTrue(all(project.members[name].section == "Other" for name in segments))

    def test_rename_updates_default_and_assignments(self):
        project = Project()
        project.add_member((0, 0), (120, 0))
        project.set_section(Section("Custom section", 5, 10, 100, 0.2), "W18x35")
        self.assertEqual(project.default_section, "Custom section")
        self.assertEqual(project.members["M1"].section, "Custom section")
        self.assertNotIn("W18x35", project.sections)
        project.validate()

    def test_delete_protects_assigned_and_default_sections(self):
        project = Project()
        with self.assertRaisesRegex(ValueError, "default"):
            project.delete_section("W18x35")
        project.set_section(Section("Other"))
        project.add_member((0, 0), (120, 0))
        project.members["M1"].section = "Other"
        with self.assertRaisesRegex(ValueError, "M1"):
            project.delete_section("Other")
        project.members["M1"].section = "W18x35"
        project.delete_section("Other")
        self.assertNotIn("Other", project.sections)

    def test_round_trip_and_independent_clones(self):
        project = Project()
        project.set_section(Section("Other", 5, 10, 100, 0.2))
        project.default_section = "Other"
        project.add_member((0, 0), (120, 0))
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "sections.pynite.json"
            project.save(path)
            self.assertEqual(project.to_dict(), Project.open(path).to_dict())
        copied = project.clone()
        copied.sections["Other"].Iz = 200
        self.assertEqual(project.sections["Other"].Iz, 100)

    def test_invalid_definitions_and_references(self):
        for section in (Section(""), Section("bad", A=0), Section("bad", Iy=-1), Section("bad", Iz=float("nan")), Section("bad", J=float("inf"))):
            with self.assertRaises(ValueError):
                section.validate()
        project = Project()
        project.add_member((0, 0), (120, 0))
        project.members["M1"].section = "missing"
        with self.assertRaisesRegex(ValueError, "M1.*missing"):
            project.validate()


class SectionEditorTests(unittest.TestCase):
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

    def test_assignment_undo_and_invalidation(self):
        self.window.edit("Add section", lambda p: p.set_section(Section("Other")))
        self.window.edit("Add member", lambda p: p.add_member((0, 0), (120, 0)))
        self.window.select(("members", "M1"))
        selector = next(widget for widget in self.window.inspector.findChildren(QComboBox) if "Other" in [widget.itemText(i) for i in range(widget.count())])
        selector.setCurrentText("Other")
        self.window.result = object()
        self.window.deformed_action.setEnabled(True)
        next(button for button in self.window.inspector.findChildren(QPushButton) if button.text() == "Apply").click()
        self.assertEqual(self.window.project.members["M1"].section, "Other")
        self.assertIsNone(self.window.result)
        self.assertFalse(self.window.deformed_action.isEnabled())
        self.window.undo.undo()
        self.assertEqual(self.window.project.members["M1"].section, "W18x35")
        self.window.undo.redo()
        self.assertEqual(self.window.project.members["M1"].section, "Other")

    def test_manager_default_and_delete(self):
        self.window.edit("Add section", lambda p: p.set_section(Section("Other")))
        dialog = SectionDialog(self.window)
        dialog.refresh("Other")
        self.assertTrue(dialog.delete_button.isEnabled())
        dialog.set_default()
        self.assertEqual(self.window.project.default_section, "Other")
        self.assertFalse(dialog.delete_button.isEnabled())
        dialog.refresh("W18x35")
        dialog.set_default()
        dialog.refresh("Other")
        dialog.delete_section()
        self.assertNotIn("Other", self.window.project.sections)
        self.window.undo.undo()
        self.assertIn("Other", self.window.project.sections)
        dialog.close()

    def test_editor_preserves_precision_and_rejects_zero(self):
        project = self.window.project
        original = Section("Fine", J=0.123456789012)
        project.set_section(original)
        dialog = SectionEditor(self.window, project, original, original.name)
        dialog.accept()
        self.assertEqual(dialog.definition.J, original.J)
        rejected = SectionEditor(self.window, project, original, original.name)
        rejected.fields["J"].setValue(0)
        with patch("pynitegui.qt.sections.QMessageBox.warning") as warning:
            rejected.accept()
        warning.assert_called_once()
        self.assertIsNone(rejected.definition)
        dialog.close()
        rejected.close()


if __name__ == "__main__":
    unittest.main()
