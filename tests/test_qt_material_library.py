"""Reference presets, weight-density conversion, and safe library imports."""
import copy
import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication, QDialogButtonBox
from pynitegui.qt.app import MainWindow
from pynitegui.qt.material_library import PRESETS, BY_KEY
from pynitegui.qt.materials import MaterialDialog, MaterialEditor, MaterialLibraryDialog
from pynitegui.qt.model import Material, Project


def preset_material(key="aluminum", name="Aluminum"):
    return Material(name, **BY_KEY[key].properties(), preset=key)


class MaterialLibraryTests(unittest.TestCase):
    def test_all_presets_validate_and_metric_weight_is_not_mass(self):
        self.assertEqual(len(BY_KEY), len(PRESETS))
        units = Project(unit_system="si").units
        for item in PRESETS:
            material = preset_material(item.key)
            material.validate()
            self.assertAlmostEqual(material.G, material.E / (2 * (1 + material.nu)))
        self.assertAlmostEqual(units.to_display(BY_KEY["aluminum"].rho, "density"), 26.477955)
        self.assertAlmostEqual(units.to_display(BY_KEY["aluminum"].E, "stress"), 70000)
        self.assertAlmostEqual(units.to_display(BY_KEY["concrete_rc"].rho, "density"), 25)

    def test_roundtrip_and_legacy_preservation(self):
        project = Project()
        project.set_material(preset_material())
        self.assertEqual(project.clone().to_dict(), project.to_dict())
        data = Project().to_dict()
        data["version"] = 12
        data["materials"]["Steel_A992"].pop("preset")
        data["materials"]["Steel_A992"]["E"] = 12345
        before = copy.deepcopy(data)
        restored = Project.from_dict(data)
        self.assertEqual(restored.E, 12345)
        self.assertEqual(restored.materials["Steel_A992"].source_label, "Custom")
        self.assertEqual(data, before)

    def test_invalid_provenance_rejected(self):
        for preset in ([], True, "missing"):
            material = preset_material()
            material.preset = preset
            with self.assertRaises(ValueError):
                material.validate()
        project = Project()
        project.set_material(preset_material())
        data = project.to_dict()
        data["materials"]["Aluminum"]["E"] = 1
        with self.assertRaisesRegex(ValueError, "library properties differ"):
            Project.from_dict(data)


class MaterialLibraryUITests(unittest.TestCase):
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
        dialog = MaterialLibraryDialog(self.window, self.window.project)
        self.dialogs.append(dialog)
        return dialog

    def test_search_empty_and_cancel(self):
        dialog = self.chooser()
        before = self.window.project.to_dict()
        dialog.search.setText("ALUMINUM")
        self.assertEqual(len(dialog.rows), 1)
        dialog.search.setText("missing")
        self.assertEqual(dialog.table.rowCount(), 0)
        self.assertFalse(dialog.buttons.button(QDialogButtonBox.StandardButton.Ok).isEnabled())
        dialog.accept()
        self.assertIsNone(dialog.definition)
        dialog.reject()
        self.assertEqual(self.window.project.to_dict(), before)

    def test_all_units_import_exact_values_and_editor_preserves_source(self):
        for units in ("imperial", "si", "si_mm", "imperial_ft"):
            self.window.project.unit_system = units
            dialog = self.chooser()
            dialog.search.setText("Aluminum")
            shown = float(dialog.table.item(0, 1).text())
            expected = self.window.project.units.to_display(BY_KEY["aluminum"].E, "stress")
            self.assertAlmostEqual(shown, expected, delta=expected * 1e-9)
            dialog.accept()
            self.assertEqual(dialog.definition.E, BY_KEY["aluminum"].E)
            editor = MaterialEditor(self.window, self.window.project, dialog.definition)
            self.dialogs.append(editor)
            editor.name.setText("Renamed")
            editor.accept()
            self.assertEqual(editor.definition.preset, "aluminum")
            self.assertEqual(editor.definition.rho, dialog.definition.rho)

    def test_property_changes_are_custom(self):
        editor = MaterialEditor(self.window, self.window.project, preset_material())
        self.dialogs.append(editor)
        editor.rho.setValue(editor.rho.value() * 2)
        self.assertEqual(editor.source.text(), "Custom")
        editor.accept()
        self.assertIsNone(editor.definition.preset)

    def test_conflicts_and_import_undo(self):
        self.window.project.set_material(preset_material(name=BY_KEY["aluminum"].name))
        dialog = self.chooser()
        dialog.search.setText("Aluminum")
        self.assertTrue(dialog.name.text().endswith("(2)"))
        dialog.name.setText(BY_KEY["aluminum"].name)
        with patch("pynitegui.qt.materials.QMessageBox.warning") as warning:
            dialog.accept()
        warning.assert_called_once()
        self.assertIsNone(dialog.definition)
        manager = MaterialDialog(self.window)
        self.dialogs.append(manager)
        before = self.window.project.to_dict()
        def choose(dialog):
            dialog.search.setText("Concrete C30/37 - plain")
            dialog.accept()
            return 1
        with patch.object(MaterialLibraryDialog, "exec", choose):
            manager.add_library_material()
        self.assertEqual(self.window.undo.count(), 1)
        self.assertEqual(self.window.project.default_material, before["default_material"])
        self.window.undo.undo()
        self.assertEqual(self.window.project.to_dict(), before)
        self.window.undo.redo()
        self.assertEqual(self.window.project.materials[BY_KEY["concrete_plain"].name].preset, "concrete_plain")
