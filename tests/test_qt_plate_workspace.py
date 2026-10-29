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
from pynitegui.qt.model import Material


class PlateWorkspaceTests(unittest.TestCase):
    def test_local_inspection_clicks_holes_units_combinations_csv_and_stale_clear(self):
        import numpy as np
        from types import SimpleNamespace
        window = self.window
        for family in ("Rect", "Quad"):
            definition = PlateDefinition(element_type=family, plane="YZ", width=120., height=80., mesh_size=20.,
                origin=[17., -31., 49.], pressure=-1e-7, thickness=.6,
                openings=[dict(name="Hole", x_left=40., y_bott=20., width=20., height=20.)],
                combinations={"Reversed": {"Case 1": -2.}})
            window.install(definition.to_dict())
            self.assertFalse(window.inspect_action.isEnabled())
            window.run_analysis()
            self.wait_until(lambda: window.thread is None)
            self.assertTrue(window.inspect_action.isEnabled())
            window.component.setCurrentIndex(2)
            window.inspect_results()
            inspector = window.inspector
            self.app.processEvents()
            self.assertEqual(inspector.table.rowCount(), len(window.result["cells"]))
            self.assertEqual(any(inspector.table.horizontalHeaderItem(i).text().startswith("Qx (")
                for i in range(inspector.table.columnCount())), family == "Rect")
            polygon = window.result["points"][window.result["cells"][3]]
            point = polygon[0]+.7*(polygon[1]-polygon[0])+.2*(polygon[3]-polygon[0])
            event = SimpleNamespace(inaxes=window.ax, button=1, xdata=point[0], ydata=point[1])
            window.click_plot(event)
            self.assertEqual(inspector.element.currentText(), window.result["element_names"][3])
            self.assertAlmostEqual(inspector.xi.value(), .4)
            self.assertAlmostEqual(inspector.eta.value(), -.6)
            self.assertIn("Global XYZ", inspector.probe.text())
            self.assertIsNotNone(window.probe_marker)
            from PySide6.QtTest import QTest
            from PySide6.QtCore import Qt
            with patch("pynitegui.qt.plate_inspection_dialog.QFileDialog.getSaveFileName") as picker:
                inspector.xi.setFocus()
                QTest.keyClick(inspector.xi, Qt.Key.Key_Return)
            picker.assert_not_called()
            self.assertTrue(inspector.isVisible())
            previous = dict(inspector.probe_data)
            window.click_plot(SimpleNamespace(inaxes=window.ax, button=1, xdata=50., ydata=30.))
            self.assertEqual(inspector.probe_data, previous)  # The opening is blank.
            with patch.object(window.plot_toolbar, "mode", "pan/zoom"):
                window.click_plot(SimpleNamespace(inaxes=window.ax, button=1, xdata=10., ydata=10.))
            self.assertEqual(inspector.probe_data, previous)
            moment = inspector.probe_data["Mx"]
            snapshot = window.result["snapshot_id"]
            window.combination.setCurrentText("Reversed")
            self.assertAlmostEqual(inspector.probe_data["Mx"], -2*moment)
            self.assertAlmostEqual(inspector.xi.value(), .4)
            window.units_box.setCurrentIndex(window.units_box.findData("si"))
            self.assertEqual(window.result["snapshot_id"], snapshot)
            self.assertIn("kN-m/m", inspector.probe.text())
            self.assertAlmostEqual(inspector.probe_data["Mx"], -2*moment)
            np.testing.assert_allclose(window.probe_marker.get_xdata(), [point[0]*window.definition.units.length_factor])
            with tempfile.TemporaryDirectory() as directory:
                for single in (True, False):
                    path = str(Path(directory)/"inspection.csv")
                    with patch("pynitegui.qt.plate_inspection_dialog.QFileDialog.getSaveFileName", return_value=(path, "")):
                        inspector.export_csv(single)
                    with open(path, newline="") as stream:
                        rows = list(csv.DictReader(stream))
                    self.assertEqual(len(rows), 1 if single else len(window.result["cells"]))
                    self.assertEqual(rows[0]["Snapshot"], snapshot)
                    self.assertEqual(rows[0]["Combination"], "Reversed")
                    if single:
                        self.assertAlmostEqual(float(rows[0]["xi"]), .4)
                        self.assertAlmostEqual(float(rows[0]["eta"]), -.6)
            inspector.table.selectRow(0)
            self.assertEqual(inspector.xi.value(), 0.)
            self.assertEqual(inspector.eta.value(), 0.)
            inspector.reject()
            self.assertIsNone(window.probe_marker)
            window.inspect_results()
            self.assertIs(window.inspector, inspector)
            window.fields["thickness"].setValue(.9*window.definition.units.length_factor)
            self.assertIsNone(window.result)
            self.assertIsNone(inspector.result)
            self.assertIsNone(inspector.probe_data)
            self.assertEqual(inspector.table.rowCount(), 0)
            self.assertFalse(inspector.export_probe.isEnabled())
            self.assertFalse(inspector.export_centres.isEnabled())
            self.assertFalse(window.inspect_action.isEnabled())
            self.assertIsNone(window.probe_marker)

    def test_inspector_recovery_failure_clears_table_and_export_then_retries(self):
        window = self.window
        window.fields["mesh_size"].setValue(60.)
        window.run_analysis()
        self.wait_until(lambda: window.thread is None)
        window.inspect_results()
        inspector = window.inspector
        with patch("pynitegui.qt.plate_inspection_dialog.plate_probe_table", side_effect=ValueError("Nonfinite recovery")):
            inspector.key = object()
            window.draw()
        self.assertIsNone(inspector.result)
        self.assertIsNone(inspector.probe_data)
        self.assertEqual(inspector.table.rowCount(), 0)
        self.assertFalse(inspector.export_probe.isEnabled())
        self.assertFalse(inspector.export_centres.isEnabled())
        self.assertIn("Nonfinite recovery", inspector.probe.text())
        window.draw()
        self.assertEqual(inspector.table.rowCount(), 4)
        self.assertTrue(inspector.export_probe.isEnabled())

    def test_quad_shear_is_unavailable_and_rect_remains_enabled(self):
        from pynitegui.qt.surface_results import QUAD_SHEAR_LIMITATION
        for family in ("Quad", "Rect"):
            definition = PlateDefinition(element_type=family, mesh_size=60)
            self.window.install(definition.to_dict())
            result = analyze_plate(definition)
            self.assertEqual(result["shears"] is None, family == "Quad")
            self.window.result = result
            self.window.component.setCurrentIndex(5)
            self.assertEqual(self.window.component.currentIndex() == 5, family == "Rect")
            self.assertEqual(self.window.component.model().item(5).isEnabled(), family == "Rect")
            if family == "Quad":
                self.assertEqual(self.window.recovery_note.text(), QUAD_SHEAR_LIMITATION)

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

    def test_rect_worker_and_signed_unit_aware_contours(self):
        import numpy as np
        definition = PlateDefinition(element_type="Rect", unit_system="si", mesh_size=30,
                                     pressure=-1e-7, thickness=.6)
        self.window.install(definition.to_dict())
        self.window.run_analysis()
        self.wait_until(lambda: self.window.thread is None)
        result = self.window.result
        self.assertIsNotNone(result)
        self.assertTrue((result["moments"][:, :2] < 0).all())
        for index, key, column, factor in ((2, "moments", 0, definition.units.force_factor),
                                           (5, "shears", 0, definition.units.factor("intensity"))):
            self.window.component.setCurrentIndex(index)
            artist = self.window.figure.axes[0].collections[0]
            np.testing.assert_allclose(artist.get_array(), result[key][:, column]*factor)

    def test_loading_dialog_is_staged_and_commits_as_one_undoable_edit(self):
        from pynitegui.qt.plate_loads import PlateLoadsDialog
        from pynitegui.qt.load_cases import CombinationEditor
        definition = PlateDefinition(plane="XZ", unit_system="si", load_case="Dead", mesh_size=30.,
            material=Material("Concrete", E=3600., nu=.2, rho=.00009),
            additional_pressures={"Live": -.00002}, combinations={"Service": {"Dead": 1., "Live": .7}})
        window = self.window
        window.install(definition.to_dict())
        before = window.definition.to_dict()
        dialog = PlateLoadsDialog(window, window.definition)
        dialog.weight_case.setCurrentIndex(dialog.weight_case.findData("Dead"))
        dialog.weight_factor.setValue(1.3)
        dialog.cases.selectRow(0)
        with patch("pynitegui.qt.plate_loads.QInputDialog.getText", return_value=("Permanent", True)):
            dialog.perform("cases", "edit")
        self.assertEqual(dialog.definition.self_weight_case, "Permanent")
        self.assertEqual(dialog.definition.combinations["Service"], {"Permanent": 1., "Live": .7})
        self.assertEqual(dialog.definition.pressure, definition.pressure)
        dialog.cases.selectRow(1)
        with patch("pynitegui.qt.plate_loads.QMessageBox.warning") as warning:
            dialog.perform("cases", "delete")
        warning.assert_called_once()
        editor = CombinationEditor(dialog, dialog.definition, "Ultimate", {"Permanent": 1.2, "Live": 1.6})
        editor.accept()
        with patch("pynitegui.qt.load_cases.CombinationEditor", return_value=editor), patch.object(editor, "exec", return_value=editor.DialogCode.Accepted):
            dialog.perform("combinations", "add")
        self.assertEqual(window.definition.to_dict(), before)
        with patch("pynitegui.qt.plate_loads.PlateLoadsDialog", return_value=dialog), patch.object(dialog, "exec", return_value=dialog.DialogCode.Rejected):
            window.configure_loading()
        self.assertEqual(window.definition.to_dict(), before)
        self.assertEqual(window.undo.count(), 0)
        dialog.accept()
        with patch("pynitegui.qt.plate_loads.PlateLoadsDialog", return_value=dialog), patch.object(dialog, "exec", return_value=dialog.DialogCode.Accepted):
            window.configure_loading()
        self.assertEqual(window.undo.count(), 1)
        self.assertEqual(window.definition.self_weight_case, "Permanent")
        self.assertEqual(window.definition.combinations["Ultimate"], {"Permanent": 1.2, "Live": 1.6})
        self.assertEqual(window.definition.self_weight_factor, 1.3)
        window.undo.undo()
        self.assertEqual(window.definition.to_dict(), before)
        window.undo.redo()
        self.assertEqual(window.definition.load_case, "Permanent")
        from types import SimpleNamespace
        recipe = window.definition.mesh_definition()
        recipe.plane = "XY"
        mesh_dialog = SimpleNamespace(definition=recipe, exec=lambda: dialog.DialogCode.Accepted)
        before = window.definition.to_dict()
        count = window.undo.count()
        with patch("pynitegui.qt.mesh_workspace.MeshWorkspace", return_value=mesh_dialog), patch("pynitegui.qt.plate_workspace.QMessageBox.warning") as warning:
            window.configure_mesh()
        warning.assert_called_once()
        self.assertEqual(window.definition.to_dict(), before)
        self.assertEqual(window.undo.count(), count)
        editor.deleteLater()
        dialog.deleteLater()

    def test_multi_combination_worker_units_snapshot_csv_and_edit_invalidation(self):
        import numpy as np
        window = self.window
        definition = PlateDefinition(element_type="Rect", plane="XZ", mesh_size=30., thickness=.6,
            pressure=1e-7, load_case="Dead", material=Material("Concrete", E=3600., nu=.2, rho=1e-8),
            self_weight_case="Dead", additional_pressures={"Live": 2e-7},
            combinations={"Double": {"Dead": 2.}, "Service": {"Dead": 1.2, "Live": 1.6}})
        window.install(definition.to_dict())
        window.run_analysis()
        self.wait_until(lambda: window.thread is None)
        baseline = window.result
        self.assertEqual(window.combination.count(), 3)
        window.combination.setCurrentText("Double")
        np.testing.assert_allclose(window.result["displacement"], 2*baseline["displacement"], atol=1e-12)
        snapshot = window.result["snapshot_id"]
        window.component.setCurrentIndex(2)
        window.units_box.setCurrentIndex(window.units_box.findData("si"))
        self.assertEqual(window.result["snapshot_id"], snapshot)
        self.assertEqual(window.result["combination"], "Double")
        self.assertEqual(window.component.currentIndex(), 2)
        np.testing.assert_allclose(window.figure.axes[0].collections[0].get_array(),
                                   2*baseline["moments"][:, 0]*window.definition.units.force_factor)
        window.undo.undo()
        self.assertEqual(window.definition.unit_system, "imperial")
        self.assertEqual(window.result["snapshot_id"], snapshot)
        window.undo.redo()
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory)/"combined.csv")
            with patch("pynitegui.qt.plate_workspace.QFileDialog.getSaveFileName", return_value=(path, "")):
                window.export_csv()
            with open(path) as stream:
                rows = list(csv.reader(stream))
            self.assertIn("Combination", rows[0])
            self.assertIn("Snapshot", rows[0])
            self.assertIn("Double", rows[1])
            self.assertIn(snapshot, rows[1])
            self.assertIn("Dead: 2", rows[1])
            self.assertAlmostEqual(sum(float(row[4]) for row in rows[1:]),
                                   -window.result["applied"]*window.definition.units.force_factor)
        window.case.setText("Permanent")
        self.assertIsNone(window.result)
        self.assertFalse(window.combination.isEnabled())
        self.assertFalse(window.export_action.isEnabled())
        self.assertTrue(window.apply())
        self.assertEqual(window.definition.self_weight_case, "Permanent")
        self.assertEqual(window.definition.combinations["Service"], {"Permanent": 1.2, "Live": 1.6})


if __name__ == "__main__":
    unittest.main()
