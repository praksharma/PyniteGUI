"""Native coupled-slab controls, result publishing and isolated worker payloads."""
import contextlib
import io
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from threading import Event
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYNITEGUI_NO_WEBENGINE", "1")
from PySide6.QtWidgets import QApplication, QCheckBox, QComboBox, QDoubleSpinBox, QPushButton
from pynitegui.qt.analysis import analyze
from pynitegui.qt.analysis_jobs import execute_analysis
from pynitegui.qt.app import MainWindow, unit_value
from pynitegui.qt.equilibrium import check_equilibrium
from pynitegui.qt.examples import example_project
from pynitegui.qt.spatial_surfaces import put_surface
from pynitegui.qt.spatial_view import viewport_payload
from pynitegui.qt.surface_results import centre_results, FIELDS
import numpy as np


class CoupledEditorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = MainWindow()
        self.window.load_project(example_project("3d_slab_frame"))
        self.window.select(("surfaces", "Floor"))

    def tearDown(self):
        self.window.live_analysis.set_enabled(False)
        self.window.saved = self.window.project.to_dict()
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()

    def test_pressure_case_units_and_opt_in_are_atomic_undoable_edits(self):
        window = self.window
        window.set_units("si")
        field = window.findChild(QDoubleSpinBox, "surface_pressure")
        self.assertAlmostEqual(unit_value(field, window.project.units, "pressure"), .001)
        case = window.findChild(QComboBox, "surface_pressure_case")
        case.setCurrentText("Uplift")
        self.assertAlmostEqual(unit_value(field, window.project.units, "pressure"), -.0003)
        field.setValue(0.)
        window.findChild(QPushButton, "surface_pressure_apply").click()
        case = window.findChild(QComboBox, "surface_pressure_case")
        field = window.findChild(QDoubleSpinBox, "surface_pressure")
        case.setCurrentText("Uplift")
        self.assertEqual(field.value(), 0.)
        field.setValue(window.project.units.to_display(.002, "pressure"))
        window.findChild(QPushButton, "surface_pressure_apply").click()
        self.assertAlmostEqual(window.project.surface_pressures["Floor"]["Uplift"], .002, places=9)
        window.undo.undo()
        self.assertNotIn("Uplift", window.project.surface_pressures["Floor"])
        window.findChild(QCheckBox, "surface_analysis_enabled").setChecked(False)
        self.assertFalse(window.project.surface_analysis_enabled)
        with patch("pynitegui.qt.app.QMessageBox.information") as info:
            window.run_analysis()
        info.assert_called_once()
        self.assertIsNone(window.thread)
        window.undo.undo()
        self.assertTrue(window.project.surface_analysis_enabled)

    def test_results_deformation_pressure_filter_and_rename(self):
        window = self.window
        with contextlib.redirect_stdout(io.StringIO()):
            result = analyze(window.project)
        window.analysis_revision = window.revision
        window.analysis_finished(result, "")
        self.assertEqual(window.result.snapshot_id, result.snapshot_id)
        self.assertTrue(window.results_panel.equilibrium.passed)
        self.assertTrue(window.export_menu.isEnabled())
        from pynitegui.qt.reports import ReportOptions, report_html, report_images
        html = report_html(window.project, window.result)
        self.assertIn("Surface Geometry and Material", html)
        self.assertIn("Experimental coupled rectangular Quad slabs", html)
        images = report_images(window.project, window.result, ReportOptions(diagrams=("moment_z",), views=("isometric",)))
        self.assertTrue(next(iter(images.values())).startswith(b"\x89PNG"))
        window.deformed_action.setChecked(True)
        payload = viewport_payload(window)
        mesh = payload["surfaceMeshes"][0]
        self.assertTrue(any(abs(n["displacement"][1]) > 0 for n in mesh["nodes"]))
        self.assertEqual(mesh["pressures"][0]["value"], .001)
        self.assertTrue(payload["deformed"])
        window.load_filter.setCurrentIndex(window.load_filter.findData(False))
        self.assertFalse(viewport_payload(window)["surfaceMeshes"][0]["pressures"])
        definition = window.project.surfaces["Floor"]
        definition = type(definition).from_dict(definition.to_dict())
        definition.name = "Roof"
        window.edit("Rename surface", lambda p: put_surface(p, definition, "Floor"))
        self.assertEqual(window.project.surface_pressures, {"Roof": {"Gravity": .001, "Uplift": -.0003}})
        self.assertIsNone(window.result)

    def test_isolated_analysis_roundtrip_retains_generated_node_mapping(self):
        project = self.window.project
        phases = []
        result = execute_analysis(project, phases.append, Event())
        self.assertIn("Floor", result.solver._pynitegui_surfaces)
        self.assertTrue(check_equilibrium(project, result).passed)
        self.assertTrue(any("Connecting" in phase for phase in phases))
        self.window.live_analysis.set_enabled(True)
        self.assertTrue(self.window.live_analysis.pending)
        self.window.live_analysis.set_enabled(False)
        from pynitegui.qt.automation_core import AutomationCommands
        with patch.object(self.window, "run_analysis") as run:
            AutomationCommands(self.window).execute("run_analysis", {"session_id": self.window.project_session,
                "expected_revision": self.window.automation_revision})
        run.assert_called_once_with(automation=True)

    def test_edge_support_dialog_preview_cancel_commit_and_undo(self):
        from pynitegui.qt.surface_support_dialog import SurfaceSupportDialog, edit_surface_supports
        window = self.window
        before = window.project.to_dict()
        dialog = SurfaceSupportDialog(window, window.project, "Floor")
        dialog.choices["left"].setCurrentText("Normal roller")
        dialog.choices["bottom"].setCurrentText("Bending clamp")
        self.assertEqual(dialog.values()["left"], ["DY"])
        self.assertEqual(set(dialog.values()["bottom"]), {"DY", "RX", "RZ"})
        self.assertEqual(window.project.to_dict(), before)
        with patch("pynitegui.qt.surface_support_dialog.SurfaceSupportDialog", return_value=dialog), patch.object(dialog, "exec", return_value=dialog.DialogCode.Rejected):
            edit_surface_supports(window, "Floor")
        self.assertEqual(window.project.to_dict(), before)
        dialog.accept()
        with patch("pynitegui.qt.surface_support_dialog.SurfaceSupportDialog", return_value=dialog), patch.object(dialog, "exec", return_value=dialog.DialogCode.Accepted):
            edit_surface_supports(window, "Floor")
        self.assertEqual(window.project.surface_supports["Floor"]["left"], ["DY"])
        mesh = viewport_payload(window)["surfaceMeshes"][0]
        self.assertEqual(mesh["supportEdges"][0]["edge"], "left")
        self.assertEqual(len(mesh["supportEdges"][0]["segments"]), 6)
        # Asymmetric frame/slab clamps can still trigger the upstream drilling
        # imbalance. Adding this editor must not bypass the equilibrium gate.
        with contextlib.redirect_stdout(io.StringIO()), self.assertRaisesRegex(ValueError, "equilibrium failed"):
            analyze(window.project)
        report_project = window.project.clone()
        report_project.surface_supports = {"Floor": {edge: ["DX", "DY", "DZ", "RX", "RY", "RZ"]
                                                   for edge in ("left", "right", "bottom", "top")}}
        with contextlib.redirect_stdout(io.StringIO()):
            result = analyze(report_project)
        from pynitegui.qt.reports import report_html, report_images, ReportOptions
        html = report_html(report_project, result)
        self.assertIn("Surface Edge Supports (Global DOFs)", html)
        self.assertIn("RX, RY, RZ", html)
        images = report_images(report_project, result, ReportOptions(diagrams=("moment_z",), views=("isometric",)))
        self.assertTrue(next(iter(images.values())).startswith(b"\x89PNG"))
        window.undo.undo()
        self.assertEqual(window.project.to_dict(), before)
        dialog.deleteLater()

    def test_slab_contour_probe_combination_units_csv_and_invalidation(self):
        window = self.window
        window.project.set_combination("Double", {"Gravity": 2.})
        with contextlib.redirect_stdout(io.StringIO()):
            result = analyze(window.project)
        window.analysis_revision = window.revision
        window.analysis_finished(result, "")
        panel = window.results_panel.surfaces
        window.select(("surfaces", "Floor"))
        self.assertIs(window.results_panel.tabs.currentWidget(), panel)
        self.assertEqual(panel.table.rowCount(), 48)
        self.assertEqual(panel.field.count(), 6)
        expected = np.array([row["Mx"] for row in centre_results(window.result, "Floor")])
        np.testing.assert_allclose(panel.artist.get_array(), expected)
        window.result_combination.setCurrentText("Double")
        panel.ensure_loaded()
        np.testing.assert_allclose(panel.artist.get_array(), 2*expected)
        window.set_units("si")
        panel.ensure_loaded()
        np.testing.assert_allclose(panel.artist.get_array(), 2*expected*window.project.units.force_factor)
        centre = panel.polygons[2].mean(axis=0)
        panel.click_plot(SimpleNamespace(inaxes=panel.ax, button=1, xdata=centre[0], ydata=centre[1]))
        self.assertEqual(panel.element.currentText(), panel.rows[2]["element"])
        self.assertAlmostEqual(panel.xi.value(), 0.)
        self.assertAlmostEqual(panel.eta.value(), 0.)
        self.assertIn("Local unit axes", panel.probe.text())
        with TemporaryDirectory() as directory:
            path = Path(directory)/"slab.csv"
            panel.write_csv(path)
            text = path.read_text()
            self.assertIn(result.snapshot_id, text)
            self.assertIn("Double", text)
            self.assertIn("Mx (kN-m/m)", text)
            self.assertIn("Sx (MPa)", text)
            self.assertIn("local z global Z", text)
            self.assertNotIn("Qx (", text)
            image = Path(directory)/"contour.png"
            panel.figure.savefig(image)
            self.assertTrue(image.read_bytes().startswith(b"\x89PNG"))
        with patch("pynitegui.qt.surface_results_panel.centre_results", side_effect=ValueError("Recovery contract changed")):
            panel.choose_surface()
        self.assertEqual(panel.rows, ())
        self.assertEqual(panel.table.rowCount(), 0)
        self.assertFalse(panel.export.isEnabled())
        self.assertIn("Recovery contract changed", panel.probe.text())
        panel.choose_surface()
        self.assertEqual(panel.table.rowCount(), 48)
        self.assertTrue(panel.export.isEnabled())
        window.edit("Change pressure", lambda p: p.surface_pressures["Floor"].update(Gravity=.002))
        self.assertIsNone(window.result)
        self.assertIsNone(panel.result)
        self.assertEqual(panel.table.rowCount(), 0)
        self.assertFalse(window.results_panel.tabs.isTabVisible(window.results_panel.surface_tab))


if __name__ == "__main__":
    unittest.main()
