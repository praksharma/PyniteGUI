"""Native coupled-slab controls, result publishing and isolated worker payloads."""
import contextlib
import io
import os
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


if __name__ == "__main__":
    unittest.main()
