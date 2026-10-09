"""Native meshing controls, table edits, persistence, transfer and units."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYNITEGUI_NO_WEBENGINE", "1")
from PySide6.QtWidgets import QApplication
from pynitegui.qt.mesh_model import GENERATORS, MeshDefinition, mesh_geometry
from pynitegui.qt.mesh_workspace import MeshWorkspace, transfer_rectangle
from pynitegui.qt.plate_model import PlateDefinition


class MeshWorkspaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = MeshWorkspace()

    def tearDown(self):
        self.window.pending = False
        self.window.saved = self.window.definition.to_dict()
        self.window.reject()
        self.window.deleteLater()
        self.app.processEvents()

    def test_all_generators_dynamic_options_and_undo(self):
        before = self.window.definition.to_dict()
        for generator in GENERATORS:
            self.window.generator.setCurrentIndex(self.window.generator.findData(generator))
            self.assertEqual(self.window.definition.generator, generator)
            self.assertEqual(set(self.window.parameter_fields), set(GENERATORS[generator][1]))
            self.assertTrue(self.window.apply())
            self.assertEqual(self.window.tabs.isTabEnabled(3), generator == "rectangle")
            self.assertEqual(len(self.window.preview.payload["surfaces"]), len(self.window.model.meshes["Surface"].elements))
        while self.window.undo.canUndo():
            self.window.undo.undo()
        self.assertEqual(self.window.definition.to_dict(), before)

    def test_units_roundtrip_preserves_dimensions_and_modifiers(self):
        before = self.window.definition.to_dict()
        for key in ("si", "si_mm", "imperial_ft", "imperial"):
            self.window.units.setCurrentIndex(self.window.units.findData(key))
            self.assertEqual(self.window.definition.to_dict(), {**before, "unit_system": key})
            self.assertTrue(self.window.apply())

    def test_control_and_opening_tables_and_rect_transfer(self):
        self.window.add_control(axis="x", coordinate=20)
        self.window.add_opening()
        self.assertTrue(self.window.apply())
        self.assertEqual(self.window.definition.x_control, [20])
        self.assertEqual(len(self.window.definition.openings), 1)
        self.window.element_type.setCurrentText("Rect")
        self.assertTrue(self.window.apply())
        plate = PlateDefinition(pressure=-.0002)
        transfer_rectangle(self.window.definition, plate)
        self.assertEqual(plate.element_type, "Rect")
        self.assertEqual(plate.pressure, -.0002)
        self.assertEqual(plate.openings, self.window.definition.openings)
        self.assertEqual(plate.mesh_definition(), self.window.definition)

    def test_invalid_change_keeps_valid_model(self):
        before = self.window.definition.to_dict()
        self.window.parameter_fields["width"].setValue(-1)
        with patch("pynitegui.qt.mesh_workspace.QMessageBox.warning"):
            self.assertFalse(self.window.apply())
        self.assertEqual(self.window.definition.to_dict(), before)
        self.assertEqual(self.window.undo.count(), 0)

    def test_recipe_save_open_and_generated_export(self):
        with tempfile.TemporaryDirectory() as directory:
            recipe, export = (str(Path(directory)/name) for name in ("mesh.pynitemesh", "mesh.json"))
            with patch("pynitegui.qt.mesh_workspace.QFileDialog.getSaveFileName", return_value=(recipe, "")):
                self.window.save_file()
            self.assertEqual(MeshDefinition.open(recipe), self.window.definition)
            with patch("pynitegui.qt.mesh_workspace.QFileDialog.getSaveFileName", return_value=(export, "")):
                self.window.export_mesh()
            data = json.loads(Path(export).read_text())
            self.assertEqual(len(data["nodes"]), len(self.window.model.nodes))
            self.assertTrue(all(set(element["nodes"]) <= data["nodes"].keys() for element in data["elements"].values()))
            self.window.parameter_fields["width"].setValue(150)
            self.window.apply()
            with patch.object(self.window, "confirm_discard", return_value=True), patch(
                    "pynitegui.qt.mesh_workspace.QFileDialog.getOpenFileName", return_value=(recipe, "")):
                self.window.open_file()
            self.assertEqual(self.window.definition.parameters["width"], 120)

    def test_selection_only_rejects_nonrectangle_file(self):
        dialog = MeshWorkspace(selection_only=True)
        try:
            self.assertEqual(dialog.generator.count(), 1)
            with tempfile.TemporaryDirectory() as directory:
                path = str(Path(directory)/"annulus.pynitemesh")
                data = MeshDefinition(generator="annulus", parameters=dict(GENERATORS["annulus"][1])).to_dict()
                Path(path).write_text(json.dumps(data))
                with patch("pynitegui.qt.mesh_workspace.QFileDialog.getOpenFileName", return_value=(path, "")), patch(
                        "pynitegui.qt.mesh_workspace.QMessageBox.warning"):
                    dialog.open_file()
                self.assertEqual(dialog.definition.generator, "rectangle")
        finally:
            dialog.reject()
            dialog.deleteLater()


if __name__ == "__main__":
    unittest.main()
