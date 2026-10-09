"""Opt-in scheduling never publishes stale solves or edits model definitions."""
import contextlib
import io
import os
import time
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYNITEGUI_NO_WEBENGINE", "1")
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDoubleSpinBox, QLineEdit, QToolBar, QToolButton
from pynitegui.qt.analysis import analyze
from pynitegui.qt.analysis_jobs import analysis_child
from pynitegui.qt.app import MainWindow
from pynitegui.qt.examples import example_project


def delayed_live_child(connection, project):
    connection.send(("progress", "Delayed live test solve"))
    time.sleep(.7)
    analysis_child(connection, project)


class LiveAnalysisTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = MainWindow()
        self.window.load_project(example_project("simple_beam"))
        with contextlib.redirect_stdout(io.StringIO()):
            result = analyze(self.window.project)
        self.window.analysis_revision = self.window.revision
        self.window.analysis_finished(result, "")

    def wait_until(self, predicate, seconds=15):
        deadline = time.monotonic()+seconds
        while not predicate() and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(.01)
        self.assertTrue(predicate(), "Live analysis lifecycle timed out")

    def tearDown(self):
        self.window.live_analysis.set_enabled(False)
        if self.window.thread is not None:
            self.window.cancel_analysis()
            self.wait_until(lambda: self.window.thread is None)
        self.window.saved = self.window.project.to_dict()
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()

    def edit_load(self, magnitude):
        self.window.edit("Load", lambda project: setattr(project.loads["L1"], "magnitude", magnitude))

    def enable(self):
        self.window.live_analysis_action.trigger()
        self.assertTrue(self.window.live_analysis.enabled)

    def test_manual_default_and_enable_does_not_repeat_valid_solve(self):
        window = self.window
        self.assertFalse(window.live_analysis_action.isChecked())
        self.assertEqual(window.live_analysis.timer.interval(), 750)
        with patch.object(window, "run_analysis") as run:
            self.enable()
            QTest.qWait(40)
            run.assert_not_called()
        window.live_analysis_action.trigger()
        self.edit_load(-7)
        self.assertFalse(window.live_analysis.timer.isActive())
        self.assertIsNone(window.result)

    def test_rapid_completed_edits_debounce_once_units_and_selection_do_not_restart(self):
        window = self.window
        self.enable()
        window.live_analysis.timer.setInterval(60)
        with patch.object(window, "run_analysis") as run:
            self.edit_load(-7)
            QTest.qWait(35)
            self.edit_load(-8)
            window.set_units("si")
            window.select(("nodes", "N1"))
            self.assertEqual(window.results_panel.analysis_state, "Pending")
            QTest.qWait(35)
            run.assert_not_called()
            QTest.qWait(50)
            run.assert_called_once_with(automatic=True)
        self.assertEqual(window.project.loads["L1"].magnitude, -8)

    def test_automatic_solve_uses_latest_model_and_preserves_units(self):
        window = self.window
        self.enable()
        window.live_analysis.timer.setInterval(20)
        self.edit_load(-8)
        window.set_units("si")
        project, revision = window.project.to_dict(), window.revision
        self.wait_until(lambda: window.result is not None and window.thread is None)
        self.assertAlmostEqual(window.result.reactions["N1"][1], 4)
        self.assertEqual(window.project.to_dict(), project)
        self.assertEqual(window.revision, revision)
        self.assertEqual(window.results_panel.analysis_state, "Current")
        self.assertTrue(window.diagrams_action.isEnabled())

    def test_edit_during_automatic_solve_cancels_and_restarts_latest_revision(self):
        window = self.window
        self.enable()
        window.live_analysis.timer.setInterval(20)
        with patch("pynitegui.qt.analysis_jobs.analysis_child", delayed_live_child):
            self.edit_load(-7)
            self.wait_until(lambda: "Delayed live" in window.analysis_phase.text())
            old_revision = window.analysis_revision
            self.edit_load(-12)
            self.assertTrue(window.analysis_cancel_requested)
            self.assertEqual(window.results_panel.analysis_state, "Pending")
            self.wait_until(lambda: window.result is not None and window.thread is None)
        self.assertGreater(window.analysis_revision, old_revision)
        self.assertAlmostEqual(window.result.reactions["N1"][1], 6)
        self.assertFalse(window.live_analysis.pending)

    def test_off_and_user_cancel_clear_pending_until_a_new_edit(self):
        window = self.window
        self.enable()
        self.edit_load(-7)
        self.assertTrue(window.cancel_analysis_action.isEnabled())
        window.cancel_analysis_action.trigger()
        self.assertFalse(window.live_analysis.pending)
        self.assertEqual(window.results_panel.analysis_state, "Cancelled")
        self.edit_load(-8)
        self.assertTrue(window.live_analysis.pending)
        window.live_analysis_action.trigger()
        self.assertFalse(window.live_analysis.timer.isActive())
        self.assertFalse(window.cancel_analysis_action.isEnabled())
        self.assertEqual(window.results_panel.analysis_state, "Outdated")

    def test_auto_failure_is_visible_without_modal_or_retry_loop(self):
        window = self.window
        self.enable()
        window.live_analysis.timer.setInterval(20)
        window.edit("Remove supports", lambda project: [setattr(node, "support", "free") for node in project.nodes.values()])
        with patch("pynitegui.qt.app.QMessageBox.warning") as warning:
            self.wait_until(lambda: window.results_panel.analysis_state == "Failed" and window.thread is None)
            QTest.qWait(80)
            warning.assert_not_called()
        self.assertTrue(window.model_findings.list.count())
        self.assertFalse(window.live_analysis.pending)
        self.assertIsNone(window.result)

    def test_manual_analyze_consumes_pending_timer_and_closing_discards_it(self):
        window = self.window
        self.enable()
        self.edit_load(-6)
        window.analyze_action.trigger()
        self.assertFalse(window.live_analysis.pending)
        self.assertFalse(window.analysis_automatic)
        self.wait_until(lambda: window.thread is None)
        self.assertAlmostEqual(window.result.reactions["N1"][1], 3)
        self.edit_load(-8)
        with patch.object(window, "confirm_discard", return_value=False):
            window.close()
        self.assertFalse(window.live_analysis.timer.isActive())

    def test_empty_model_and_invalid_edit_do_not_schedule(self):
        window = self.window
        self.enable()
        with patch("pynitegui.qt.app.QMessageBox.warning"):
            window.edit("Invalid", lambda project: setattr(project.nodes["N2"], "x", float("nan")))
        self.assertFalse(window.live_analysis.pending)
        from pynitegui.qt.model import Project
        window.load_project(Project())
        self.assertFalse(window.live_analysis.pending)


    def test_compact_groups_icons_active_modes_and_result_enablement(self):
        window = self.window
        groups = {bar.windowTitle(): bar for bar in window.findChildren(QToolBar)}
        self.assertTrue({"File", "View", "Edit", "Loads", "Analysis", "Results"} <= set(groups))
        for key in ("File", "View", "Edit", "Loads", "Analysis", "Results"):
            self.assertEqual(groups[key].toolButtonStyle(), Qt.ToolButtonStyle.ToolButtonIconOnly)
            for action in groups[key].actions():
                button = groups[key].widgetForAction(action)
                if isinstance(button, QToolButton):
                    self.assertFalse(button.icon().isNull())
                    self.assertTrue(button.toolTip())
        window.mode_actions["draw"].trigger()
        self.assertEqual(window.mode, "draw")
        self.assertTrue(window.mode_actions["draw"].isChecked())
        self.assertFalse(window.mode_actions["select"].isChecked())
        self.assertEqual(window.properties_button.menu().actions(), window.property_actions)
        self.assertTrue(window.diagrams_action.isEnabled())
        self.edit_load(-7)
        self.assertFalse(window.diagrams_action.isEnabled())
        self.assertFalse(window.deformed_action.isEnabled())

    def test_spatial_edit_and_undo_use_latest_definition(self):
        window = self.window
        self.enable()
        window.live_analysis.timer.setInterval(20)
        window.load_project(example_project("3d_cantilever"))
        window.edit("Spatial force", lambda project: setattr(project.loads["L1"], "magnitude", -4))
        window.undo.undo()
        project = window.project.to_dict()
        self.wait_until(lambda: window.result is not None and window.thread is None)
        self.assertTrue(window.result.spatial)
        self.assertEqual(window.project.to_dict(), project)
        self.assertAlmostEqual(window.result.reactions["N1"][1], 1.9)

    def test_disabling_live_cancels_automatic_job_without_restarting(self):
        window = self.window
        self.enable()
        window.live_analysis.timer.setInterval(20)
        with patch("pynitegui.qt.analysis_jobs.analysis_child", delayed_live_child):
            self.edit_load(-7)
            self.wait_until(lambda: "Delayed live" in window.analysis_phase.text())
            window.live_analysis_action.trigger()
            self.wait_until(lambda: window.thread is None)
            QTest.qWait(60)
        self.assertIsNone(window.result)
        self.assertFalse(window.live_analysis.pending)
        self.assertEqual(window.results_panel.analysis_state, "Cancelled")

    def test_manual_busy_solve_is_not_cancelled_but_latest_edit_is_queued(self):
        window = self.window
        self.enable()
        window.live_analysis.timer.setInterval(20)
        with patch("pynitegui.qt.analysis_jobs.analysis_child", delayed_live_child):
            window.analyze_action.trigger()
            self.wait_until(lambda: "Delayed live" in window.analysis_phase.text())
            self.edit_load(-14)
            self.assertFalse(window.analysis_cancel_requested)
            self.wait_until(lambda: window.result is not None and window.thread is None
                            and window.result.reactions["N1"][1] > 6)
        self.assertAlmostEqual(window.result.reactions["N1"][1], 7)
        self.assertTrue(window.analysis_automatic)

    def test_unfinished_drawing_defers_launch_until_select_mode(self):
        window = self.window
        self.enable()
        window.live_analysis.timer.setInterval(20)
        with patch.object(window, "run_analysis") as run:
            self.edit_load(-7)
            window.set_mode("draw")
            QTest.qWait(60)
            run.assert_not_called()
            window.set_mode("select")
            QTest.qWait(50)
            run.assert_called_once_with(automatic=True)

    def test_completed_snapshot_waits_for_unfinished_input_and_stale_deferred_is_dropped(self):
        window = self.window
        self.enable()
        window.live_analysis.timer.setInterval(20)
        with patch("pynitegui.qt.analysis_jobs.analysis_child", delayed_live_child):
            self.edit_load(-7)
            self.wait_until(lambda: "Delayed live" in window.analysis_phase.text())
            with patch.object(window.live_analysis, "is_editing", return_value=True):
                self.wait_until(lambda: window.thread is None)
                self.assertIsNone(window.result)
                self.assertIsNotNone(window.live_analysis.deferred)
                self.edit_load(-10)
                self.assertIsNone(window.live_analysis.deferred)
            self.wait_until(lambda: window.result is not None and window.thread is None)
        self.assertAlmostEqual(window.result.reactions["N1"][1], 5)

    def test_modified_numeric_input_defers_launch(self):
        window = self.window
        self.enable()
        window.live_analysis.timer.setInterval(20)
        self.edit_load(-7)
        window.select(("nodes", "N2"))
        field = window.inspector.findChild(QDoubleSpinBox)
        editor = field.findChild(QLineEdit)
        editor.setModified(True)
        with patch.object(QApplication, "focusWidget", return_value=field), patch.object(window, "run_analysis") as run:
            QTest.qWait(60)
            run.assert_not_called()
            editor.setModified(False)
            QTest.qWait(50)
            run.assert_called_once_with(automatic=True)

    def test_deferred_snapshot_publishes_after_input_finishes_without_another_solve(self):
        window = self.window
        self.enable()
        window.live_analysis.timer.setInterval(20)
        with patch("pynitegui.qt.analysis_jobs.analysis_child", delayed_live_child), \
                patch.object(window, "run_analysis", wraps=window.run_analysis) as run:
            self.edit_load(-9)
            self.wait_until(lambda: "Delayed live" in window.analysis_phase.text())
            with patch.object(window.live_analysis, "is_editing", return_value=True):
                self.wait_until(lambda: window.thread is None)
                self.assertIsNone(window.result)
                self.assertTrue(window.cancel_analysis_action.isEnabled())
            self.wait_until(lambda: window.result is not None)
            run.assert_called_once_with(automatic=True)
        self.assertAlmostEqual(window.result.reactions["N1"][1], 4.5)
        self.assertEqual(window.results_panel.analysis_state, "Current")
        self.assertFalse(window.cancel_analysis_action.isEnabled())


if __name__ == "__main__":
    unittest.main()
