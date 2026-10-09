"""Native pilot editing, identity, persistence and cancellable process checks."""
import os
import csv
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYNITEGUI_NO_WEBENGINE", "1")
from PySide6.QtWidgets import QApplication
from pynitegui.qt.plate_model import PlateDefinition, analyze_plate
from pynitegui.qt.plate_workspace import PlateWorkspace


class PlateWorkspaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = PlateWorkspace()

    def tearDown(self):
        if self.window.thread is not None:
            self.window.worker.cancel()
            self.wait_until(lambda: self.window.thread is None)
        self.window.pending = False
        self.window.saved = self.window.definition.to_dict()
        self.window.reject()
        self.window.deleteLater()
        self.app.processEvents()

    def wait_until(self, predicate):
        deadline = time.monotonic() + 25
        while not predicate() and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(.005)
        self.assertTrue(predicate())

    def test_edit_preview_undo_redo(self):
        before = self.window.definition.to_dict()
        self.window.fields["mesh_size"].setValue(30)
        self.assertTrue(self.window.pending)
        self.assertTrue(self.window.apply())
        self.assertEqual(self.window.definition.mesh_size, 30)
        self.assertEqual(self.window.undo.count(), 1)
        self.window.undo.undo()
        self.assertEqual(self.window.definition.to_dict(), before)
        self.window.undo.redo()
        self.assertEqual(self.window.definition.mesh_size, 30)

    def test_invalid_edit_atomic(self):
        before = self.window.definition.to_dict()
        self.window.fields["thickness"].setValue(-1)
        with patch("pynitegui.qt.plate_workspace.QMessageBox.warning"):
            self.assertFalse(self.window.apply())
        self.assertEqual(self.window.definition.to_dict(), before)
        self.assertEqual(self.window.undo.count(), 0)

    def test_units_preserve_geometry_and_pressure(self):
        before = self.window.definition.to_dict()
        for key in ("si", "si_mm", "imperial_ft", "imperial"):
            self.window.units_box.setCurrentIndex(self.window.units_box.findData(key))
            self.assertEqual(self.window.definition.to_dict(), {**before, "unit_system": key})
            self.assertTrue(self.window.apply())
            self.assertEqual(self.window.definition.pressure, before["pressure"])

    def test_file_save_open_and_unknown_format(self):
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory)/"surface.pyniteplate")
            with patch("pynitegui.qt.plate_workspace.QFileDialog.getSaveFileName", return_value=(path, "")):
                self.window.save_file()
            saved = PlateDefinition.open(path).to_dict()
            self.window.fields["width"].setValue(180)
            self.window.apply()
            with patch.object(self.window, "confirm_discard", return_value=True), patch(
                    "pynitegui.qt.plate_workspace.QFileDialog.getOpenFileName", return_value=(path, "")):
                self.window.open_file()
            self.assertEqual(self.window.definition.to_dict(), saved)
            self.assertEqual(self.window.undo.count(), 0)
            Path(path).write_text('{"version":18,"dimension":"3D"}')
            with patch("pynitegui.qt.plate_workspace.QFileDialog.getOpenFileName", return_value=(path, "")), patch(
                    "pynitegui.qt.plate_workspace.QMessageBox.warning"):
                self.window.open_file()
            self.assertEqual(self.window.definition.to_dict(), saved)

    def test_background_analysis_and_stale_results(self):
        self.window.fields["mesh_size"].setValue(30)
        self.window.run_analysis()
        self.assertFalse(self.window.toolbar.isEnabled())
        self.assertTrue(self.window.cancel_button.isEnabled())
        self.wait_until(lambda: self.window.thread is None)
        self.assertIsNotNone(self.window.result)
        self.assertTrue(self.window.toolbar.isEnabled())
        self.assertTrue(self.window.export_action.isEnabled())
        self.assertEqual(self.window.component.currentIndex(), 1)
        previous = self.window.result
        self.assertTrue(self.window.apply())
        self.assertIs(self.window.result, previous)
        self.window.fields["pressure"].setValue(-.002)
        self.assertIsNone(self.window.result)
        self.assertFalse(self.window.export_action.isEnabled())
        self.assertEqual(self.window.component.currentIndex(), 0)

    def test_background_cancel(self):
        self.window.run_analysis()
        self.window.cancel_button.click()
        self.wait_until(lambda: self.window.thread is None)
        self.assertIsNone(self.window.result)
        self.assertIn("cancelled", self.window.status.text())

    def test_components_and_unit_aware_csv(self):
        definition = PlateDefinition(unit_system="si", mesh_size=30)
        self.window.install(definition.to_dict())
        self.window.result = analyze_plate(definition)
        for index in range(1, self.window.component.count()):
            self.window.component.setCurrentIndex(index)
            self.window.canvas.draw()
            self.assertEqual(len(self.window.figure.axes), 2)
            self.assertTrue(self.window.figure.axes[0].collections)
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory)/"nodes.csv")
            with patch("pynitegui.qt.plate_workspace.QFileDialog.getSaveFileName", return_value=(path, "")):
                self.window.export_csv()
            with open(path, newline="") as stream:
                rows = list(csv.reader(stream))
            self.assertIn("Normal reaction (kN)", rows[0])
            self.assertEqual(len(rows)-1, len(self.window.result["names"]))
            self.assertAlmostEqual(sum(float(row[4]) for row in rows[1:]),
                                   -self.window.result["applied"]*definition.units.force_factor)


if __name__ == "__main__":
    unittest.main()
