"""Exclusive native MCP control, escape hatch, lifecycle and shortcut guards."""
import os
import time
import unittest
from unittest.mock import patch
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYNITEGUI_NO_WEBENGINE", "1")
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QDoubleSpinBox, QLineEdit
from pynitegui.qt.app import MainWindow
from pynitegui.qt.examples import example_project


class AutomationModeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = MainWindow()
        self.window.load_project(example_project("simple_beam"))
        self.window.show_automation_server()
        self.server = self.window.automation_server
        self.server.state = "Running"
        self.server.bridge.set_active(True)
        self.server.changed.emit()

    def tearDown(self):
        self.server.stop()
        if self.window.thread is not None:
            self.window.cancel_analysis()
            self.wait_until(lambda: self.window.thread is None)
        self.window.saved = self.window.project.to_dict()
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()

    def wait_until(self, predicate):
        deadline = time.monotonic()+15
        while not predicate() and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(.005)
        self.assertTrue(predicate())

    def invoke(self, name, **arguments):
        future = self.server.bridge.submit(name, arguments)
        self.wait_until(future.done)
        return future.result()

    def enable(self):
        self.window.automation_panel.mode_button.click()
        self.assertTrue(self.window.mcp_mode)

    def test_unavailable_without_running_server_and_defaults_off(self):
        self.assertFalse(self.window.mcp_mode)
        self.server.state = "Stopped"
        self.server.changed.emit()
        self.assertFalse(self.window.mcp_mode_button.isEnabled())
        self.assertFalse(self.window.automation_panel.mode_button.isEnabled())
        self.window.automation_mode.set_enabled(True)
        self.assertFalse(self.window.mcp_mode)

    def test_lock_disables_manual_controls_but_both_release_buttons_work(self):
        self.window.analysis_cancel_button.setEnabled(False)
        self.enable()
        self.assertFalse(self.window.centralWidget().isEnabled())
        self.assertFalse(self.window.menuBar().isEnabled())
        self.assertFalse(self.window.inspector.isEnabled())
        self.assertFalse(self.window.unit_selector.isEnabled())
        self.assertTrue(self.window.automation_panel.isEnabled())
        self.assertTrue(self.window.mcp_mode_button.isEnabled())
        self.window.mcp_mode_button.click()
        self.assertFalse(self.window.mcp_mode)
        self.assertTrue(self.window.centralWidget().isEnabled())
        self.assertTrue(self.window.inspector.isEnabled())
        self.assertFalse(self.window.analysis_cancel_button.isEnabled())
        self.enable()
        self.window.automation_panel.mode_button.click()
        self.assertFalse(self.window.mcp_mode)

    def test_handover_cancels_drawing_and_discards_only_unapplied_inputs(self):
        before = self.window.project.to_dict()
        self.window.select(("nodes", "N2"))
        field = self.window.inspector.findChild(QDoubleSpinBox)
        field.setValue(777)
        field.findChild(QLineEdit).setModified(True)
        self.window.mode = "draw"
        self.window.planar_view.start = (1, 2)
        self.enable()
        self.assertEqual(self.window.mode, "select")
        self.assertIsNone(self.window.planar_view.start)
        self.assertEqual(self.window.project.to_dict(), before)
        self.assertFalse(self.window.live_analysis.is_editing())

    def test_modal_editing_dialog_must_finish_before_handover(self):
        dialog = QDialog(self.window)
        with patch.object(QApplication, "activeModalWidget", return_value=dialog):
            self.window.automation_mode.set_enabled(True)
        self.assertFalse(self.window.mcp_mode)
        self.assertIn("Finish the open dialog", self.window.statusBar().currentMessage())
        dialog.deleteLater()

    def test_mcp_reads_atomic_edits_and_analysis_operate_while_ui_locked(self):
        self.enable()
        model = self.invoke("read_model")["data"]
        self.assertTrue(model["mcp_mode"])
        denied = self.invoke("apply_batch", session_id=model["session_id"], expected_revision=model["revision"],
            operations=[{"op":"set", "collection":"settings", "value":{"grid":24}}])
        self.assertEqual(denied["error"]["code"], "permission_denied")
        self.server.permissions.set_group("Model edits", True)
        edited = self.invoke("apply_batch", session_id=model["session_id"], expected_revision=model["revision"],
            operations=[{"op":"put", "collection":"nodes", "key":"N2", "value":{"x":480}}])
        self.assertTrue(edited["ok"], edited)
        self.assertEqual(self.window.project.nodes["N2"].x, 480)
        self.assertFalse(self.window.inspector.isEnabled())
        self.server.permissions.set_group("Analysis", True)
        started = self.invoke("run_analysis", session_id=model["session_id"], expected_revision=edited["data"]["revision"])
        self.assertTrue(started["ok"], started)
        self.wait_until(lambda: self.window.thread is None)
        self.assertEqual(self.window.results_panel.analysis_state, "Current")
        self.assertFalse(self.window.results_panel.isEnabled())
        self.window.mcp_mode_button.click()
        self.assertTrue(self.window.results_panel.isEnabled())
        self.assertTrue(self.window.diagrams_action.isEnabled())

    def test_spatial_view_is_locked_and_spatial_mcp_edits_still_refresh(self):
        from pynitegui.qt.spatial_model import SpatialProject
        self.window.load_project(SpatialProject())
        self.enable()
        self.assertFalse(self.window.spatial_view.isEnabled())
        model = self.invoke("read_model")["data"]
        self.server.permissions.set_group("Model edits", True)
        response = self.invoke("apply_batch", session_id=model["session_id"], expected_revision=model["revision"],
            operations=[{"op":"put", "collection":"nodes", "key":"N1", "value":{"x":0,"y":0,"z":100,"support":"fixed"}}])
        self.assertTrue(response["ok"], response)
        self.assertEqual(self.window.project.nodes["N1"].z, 100)
        self.assertFalse(self.window.spatial_view.isEnabled())
        self.window.mcp_mode_button.click()
        self.assertTrue(self.window.spatial_view.isEnabled())

    def test_window_close_releases_mode_before_unsaved_change_prompt(self):
        self.enable()
        self.window.saved = {}
        def confirm():
            self.assertFalse(self.window.mcp_mode)
            self.assertTrue(self.window.centralWidget().isEnabled())
            return False
        with patch.object(self.window, "confirm_discard", side_effect=confirm):
            self.window.close()
        self.assertFalse(self.window.mcp_mode)
        self.assertTrue(self.window.centralWidget().isEnabled())

    def test_stop_releases_mode_and_manual_edits_shortcuts_are_blocked(self):
        self.window.show()
        self.window.activateWindow()
        self.app.processEvents()
        before = self.window.project.to_dict()
        self.enable()
        self.window.edit("Manual edit", lambda project: setattr(project, "grid", 72))
        self.assertEqual(self.window.project.to_dict(), before)
        with patch.object(self.window, "run_analysis") as run:
            QTest.keyClick(self.window, Qt.Key.Key_F5)
            self.app.processEvents()
            run.assert_not_called()
            self.assertIsNone(self.window.thread)
        self.server.stop()
        self.assertFalse(self.window.mcp_mode)
        self.assertTrue(self.window.centralWidget().isEnabled())
        self.assertFalse(self.window.mcp_mode_button.isEnabled())
