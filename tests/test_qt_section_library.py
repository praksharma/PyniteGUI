"""Catalog axis mapping, provenance, persistence, and import workflow."""
import copy
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication, QDialogButtonBox

from pynitegui.qt.app import MainWindow
from pynitegui.qt.model import Load, Project, Section
from pynitegui.qt.section_library import BY_DESIGNATION, CATALOG, SOURCE
from pynitegui.qt.sections import SectionDialog, SectionEditor, SectionLibraryDialog
from pynitegui.qt.analysis import analyze


def named_section(name="Beam", designation="W18X35", weak=False):
    return Section(name, **BY_DESIGNATION[designation].properties(weak),
                   catalog=SOURCE, designation=designation, weak_axis=weak)


class CatalogTests(unittest.TestCase):
    def test_catalog_properties_and_unique_designations(self):
        self.assertEqual(len(CATALOG), 15)
        self.assertEqual(len(BY_DESIGNATION), len(CATALOG))
        for item in CATALOG:
            for weak in (False, True):
                section = named_section(designation=item.designation, weak=weak)
                section.validate()
                self.assertEqual(section.Iz, item.Iy if weak else item.Ix)
                self.assertEqual(section.Iy, item.Ix if weak else item.Iy)
                self.assertEqual(section.J, item.J)
        self.assertEqual(BY_DESIGNATION["W18X35"].properties(),
                         {"A": 10.3, "Iy": 15.3, "Iz": 510, "J": 0.506})
        self.assertEqual(BY_DESIGNATION["HSS8X4X1/4"].properties(),
                         {"A": 5.24, "Iy": 14.4, "Iz": 42.5, "J": 35.3})

    def test_roundtrip_and_clone_keep_provenance(self):
        project = Project()
        project.set_section(named_section(weak=True))
        project.default_section = "Beam"
        project.add_member((0, 0), (120, 0))
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "library.json"
            project.save(path)
            restored = Project.open(path)
        self.assertEqual(restored.to_dict(), project.to_dict())
        self.assertEqual(restored.sections["Beam"].designation, "W18X35")
        cloned = restored.clone()
        cloned.sections["Beam"].name = "Other"
        self.assertEqual(restored.sections["Beam"].name, "Beam")

    def test_legacy_names_do_not_imply_catalog_membership(self):
        data = Project().to_dict()
        data["version"] = 11
        section = data["sections"]["W18x35"]
        for key in ("catalog", "designation", "weak_axis"):
            section.pop(key)
        section["Iz"] = 123
        before = copy.deepcopy(data)
        migrated = Project.from_dict(data)
        self.assertEqual(migrated.sections["W18x35"].source_label, "Custom")
        self.assertEqual(migrated.Iz, 123)
        self.assertEqual(data, before)

    def test_bad_metadata_and_changed_catalog_values_rejected(self):
        for changes in ({"catalog": "unknown"}, {"designation": []},
                        {"designation": "missing"}, {"weak_axis": 1},
                        {"Iz": 511}, {"catalog": None}):
            section = named_section()
            for key, value in changes.items():
                setattr(section, key, value)
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                section.validate()
        with self.assertRaises(ValueError):
            Section("Custom", weak_axis=True).validate()

    def test_axis_choice_changes_cantilever_stiffness(self):
        displacements = []
        for weak in (False, True):
            project = Project()
            project.set_section(named_section(weak=weak))
            project.default_section = "Beam"
            project.add_member((0, 0), (120, 0))
            project.nodes["N1"].support = "fixed"
            project.loads["L1"] = Load("L1", "N2", magnitude=-1)
            result = analyze(project)
            displacements.append(result.displacements["N2"][1])
        self.assertAlmostEqual(displacements[1] / displacements[0], 510 / 15.3)

    def test_invalid_catalog_document_is_rejected(self):
        project = Project()
        project.set_section(named_section())
        data = project.to_dict()
        data["sections"]["Beam"]["Iz"] = 999
        with self.assertRaisesRegex(ValueError, "catalog properties differ"):
            Project.from_dict(data)


class LibraryUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = MainWindow()
        self.dialogs = []

    def tearDown(self):
        for dialog in self.dialogs:
            dialog.close()
            dialog.deleteLater()
        self.window.saved = self.window.project.to_dict()
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()

    def chooser(self):
        dialog = SectionLibraryDialog(self.window, self.window.project)
        self.dialogs.append(dialog)
        return dialog

    def test_search_family_and_empty_results(self):
        dialog = self.chooser()
        dialog.search.setText("w18 x35")
        self.assertEqual([item.designation for item in dialog.rows], ["W18X35"])
        dialog.family.setCurrentText("Square HSS")
        self.assertEqual(dialog.table.rowCount(), 0)
        self.assertFalse(dialog.buttons.button(QDialogButtonBox.StandardButton.Ok).isEnabled())
        dialog.accept()
        self.assertIsNone(dialog.definition)
        dialog.search.clear()
        self.assertEqual(dialog.table.rowCount(), 3)
        dialog.family.setCurrentIndex(0)
        self.assertEqual(dialog.table.rowCount(), 15)

    def test_orientation_preview_and_import(self):
        dialog = self.chooser()
        dialog.search.setText("W18X35")
        dialog.axis.setCurrentIndex(1)
        self.assertEqual(float(dialog.table.item(0, 4).text()), 15.3)
        self.assertIn("weak", dialog.name.text())
        dialog.accept()
        self.assertTrue(dialog.definition.weak_axis)
        self.assertEqual(dialog.definition.Iz, 15.3)
        self.assertEqual(dialog.definition.A, 10.3)

    def test_preview_converts_all_unit_presets(self):
        for preset in ("imperial", "si", "si_mm", "imperial_ft"):
            self.window.project.unit_system = preset
            dialog = self.chooser()
            dialog.search.setText("W18X35")
            units = self.window.project.units
            self.assertAlmostEqual(float(dialog.table.item(0, 2).text()), units.to_display(10.3, "area"), places=4)
            self.assertAlmostEqual(float(dialog.table.item(0, 4).text()), units.to_display(510, "inertia"), delta=1)
            dialog.accept()
            self.assertEqual(dialog.definition.Iz, 510)

    def test_duplicate_names_get_suffix_and_cannot_overwrite(self):
        self.window.project.set_section(named_section("W18X35"))
        dialog = self.chooser()
        dialog.search.setText("W18X35")
        self.assertEqual(dialog.name.text(), "W18X35 (2)")
        dialog.name.setText("W18X35")
        with patch("pynitegui.qt.sections.QMessageBox.warning") as warning:
            dialog.accept()
        warning.assert_called_once()
        self.assertIsNone(dialog.definition)
        dialog.name.setText(" ")
        with patch("pynitegui.qt.sections.QMessageBox.warning") as warning:
            dialog.accept()
        warning.assert_called_once()

    def test_manager_import_is_one_undo_and_cancel_is_noop(self):
        manager = SectionDialog(self.window)
        self.dialogs.append(manager)
        before = self.window.project.to_dict()
        with patch.object(SectionLibraryDialog, "exec", return_value=0):
            manager.add_library_section()
        self.assertEqual(self.window.project.to_dict(), before)
        def choose(dialog):
            dialog.search.setText("W18X35")
            dialog.accept()
            return 1
        with patch.object(SectionLibraryDialog, "exec", choose):
            manager.add_library_section()
        self.assertEqual(self.window.undo.count(), 1)
        self.assertIn("W18X35", self.window.project.sections)
        self.assertIn(SOURCE, manager.table.item(manager.table.currentRow(), 7).text())
        self.window.undo.undo()
        self.assertEqual(self.window.project.to_dict(), before)
        self.window.undo.redo()
        self.assertEqual(self.window.project.sections["W18X35"].catalog, SOURCE)

    def test_editor_rename_preserves_source_but_property_edit_is_custom(self):
        project = self.window.project
        original = named_section()
        project.set_section(original)
        for preset in ("imperial", "si"):
            project.unit_system = preset
            dialog = SectionEditor(self.window, project, original, "Beam")
            self.dialogs.append(dialog)
            dialog.name.setText("Renamed")
            dialog.accept()
            self.assertEqual(dialog.definition.catalog, SOURCE)
            self.assertEqual(dialog.definition.Iz, original.Iz)
        modified = SectionEditor(self.window, project, original, "Beam")
        self.dialogs.append(modified)
        modified.fields["Iz"].setValue(modified.fields["Iz"].value() * 2)
        self.assertEqual(modified.source.text(), "Custom")
        modified.accept()
        self.assertIsNone(modified.definition.catalog)
        self.assertIsNone(modified.definition.designation)
        self.assertFalse(modified.definition.weak_axis)


if __name__ == "__main__":
    unittest.main()
