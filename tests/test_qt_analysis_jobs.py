"""Cancellation, process isolation, real progress, and sparse mechanisms."""
import contextlib
import io
import multiprocessing
import os
from threading import Event, Thread
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import numpy as np
from scipy.sparse import csr_matrix, eye
from scipy.sparse.linalg import ArpackNoConvergence
from PySide6.QtWidgets import QApplication

from pynitegui.qt.analysis import analyze, stiffness_issue
from pynitegui.qt.analysis_jobs import AnalysisCancelled, analysis_child, execute_analysis
from pynitegui.qt.app import MainWindow
from pynitegui.qt.examples import example_project
from pynitegui.qt.model import Load, Project


def slow_child(connection, project):
    connection.send(("progress", "Solving a busy test model"))
    time.sleep(30)
    connection.close()


def crashing_child(connection, project):
    os._exit(9)


def delayed_child(connection, project):
    connection.send(("progress", "Waiting before test solve"))
    time.sleep(0.5)
    analysis_child(connection, project)


def sparse_model():
    nodes = {f"N{i + 1}": SimpleNamespace(ID=i, name=f"N{i + 1}", support_DX=False,
                                         support_DY=False, support_RZ=False) for i in range(201)}
    matrix = eye(1206, format="lil")
    return SimpleNamespace(nodes=nodes, load_combos={"Service": None}, Ke=lambda *a, **k: matrix.tocsr()), matrix


class SparseStabilityTests(unittest.TestCase):
    def test_coupled_mechanism_has_positive_diagonals_and_is_localized(self):
        model, matrix = sparse_model()
        matrix[1201, 1205] = matrix[1205, 1201] = -1
        with patch.object(csr_matrix, "toarray", side_effect=AssertionError("Dense matrix conversion")):
            message = stiffness_issue(model)
        self.assertIn("N201 DY", message)
        self.assertIn("N201 RZ", message)
        self.assertNotIn("N1 DX", message)

    def test_zero_stiffness_is_localized_before_spectral_solve(self):
        model, matrix = sparse_model()
        matrix[1205, 1205] = 0
        with patch("pynitegui.qt.analysis.eigsh") as spectral:
            self.assertIn("N201 RZ", stiffness_issue(model))
            spectral.assert_not_called()

    def test_uniform_stiffness_scaling_does_not_create_mechanism(self):
        model, matrix = sparse_model()
        model.Ke = lambda *a, **k: (matrix * 1e-18).tocsr()
        self.assertIsNone(stiffness_issue(model))

    def test_nonfinite_stiffness_and_incomplete_check_fail_closed(self):
        model, matrix = sparse_model()
        matrix[0, 0] = np.nan
        with self.assertRaisesRegex(ValueError, "nonfinite"):
            stiffness_issue(model)
        matrix[0, 0] = 1
        failure = ArpackNoConvergence("test", np.array([]), np.empty((603, 0)))
        with patch("pynitegui.qt.analysis.eigsh", side_effect=failure):
            with self.assertRaisesRegex(ValueError, "did not converge"):
                stiffness_issue(model)

    def test_partial_convergence_can_still_report_a_found_mechanism(self):
        model, _ = sparse_model()
        mode = np.zeros((603, 1))
        mode[-1, 0] = 1
        failure = ArpackNoConvergence("test", np.array([0.0]), mode)
        with patch("pynitegui.qt.analysis.eigsh", side_effect=failure):
            self.assertIn("N201 RZ", stiffness_issue(model))

    def test_actual_frame_above_600_free_dofs_solves_and_balances(self):
        project = Project()
        for index in range(202):
            project.add_member((index * 24, 0), (index * 24, 120))
            project.nodes[project.node_at(index * 24, 0)].support = "fixed"
            if index:
                project.add_member(((index - 1) * 24, 120), (index * 24, 120))
        project.loads["L1"] = Load("L1", project.node_at(201 * 24, 120), "FY", -10)
        phases = []
        with contextlib.redirect_stdout(io.StringIO()):
            result = analyze(project, progress=phases.append)
        self.assertEqual(len(result.displacements), 404)
        self.assertAlmostEqual(sum(value[1] for value in result.reactions.values()), 10, places=7)
        self.assertIn("Checking results and stiffness", phases)
        self.assertEqual(phases[-1], "Collecting result snapshot")


class AnalysisJobTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.project = example_project("simple_beam")
        cls.project.set_combination("Double", {"Case 1": 2})
        with contextlib.redirect_stdout(io.StringIO()):
            cls.result = analyze(cls.project)

    def setUp(self):
        self.window = MainWindow()
        self.window.load_project(self.project)
        self.window.analysis_revision = self.window.revision
        self.window.analysis_finished(self.result, "")
        self.window.show()
        self.app.processEvents()

    def wait_until(self, predicate, timeout=15):
        deadline = time.monotonic() + timeout
        while not predicate() and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(0.01)
        self.assertTrue(predicate(), "Analysis lifecycle timed out")

    def tearDown(self):
        if self.window.thread is not None:
            self.window.cancel_analysis()
            self.wait_until(lambda: self.window.thread is None)
        self.window.saved = self.window.project.to_dict()
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()

    def test_isolated_result_roundtrip_keeps_all_combinations_and_member_methods(self):
        phases = []
        before = self.project.to_dict()
        result = execute_analysis(self.project, phases.append, Event())
        self.assertEqual(result.model_signature, self.result.model_signature)
        self.assertAlmostEqual(result.for_combination("Double").reactions["N1"][1], 10)
        self.assertAlmostEqual(result.solver.members["M1"].moment("Mz", 210, "Double"), -2100)
        self.assertEqual(phases[0], "Checking model and supports")
        self.assertEqual(phases[-1], "Collecting result snapshot")
        self.assertEqual(self.project.to_dict(), before)

    def test_cancel_before_launch_starts_no_process(self):
        event = Event()
        event.set()
        with patch("pynitegui.qt.analysis_jobs.multiprocessing.get_context") as context:
            with self.assertRaises(AnalysisCancelled):
                execute_analysis(self.project, lambda phase: None, event)
            context.assert_not_called()

    def test_cancel_busy_process_is_prompt_and_reaps_child(self):
        event, entered = Event(), Event()
        outcome = []
        children_before = {child.pid for child in multiprocessing.active_children()}
        def run():
            try:
                execute_analysis(self.project, lambda phase: entered.set(), event, target=slow_child)
            except AnalysisCancelled:
                outcome.append("cancelled")
        thread = Thread(target=run)
        thread.start()
        try:
            self.assertTrue(entered.wait(15))
            start = time.monotonic()
            event.set()
            thread.join(5)
            self.assertFalse(thread.is_alive())
            self.assertLess(time.monotonic() - start, 5)
            self.assertEqual(outcome, ["cancelled"])
            self.assertEqual({child.pid for child in multiprocessing.active_children()}, children_before)
        finally:
            event.set()
            thread.join(5)

    def test_child_crash_and_validation_error_are_reported(self):
        with self.assertRaisesRegex(RuntimeError, "exited|stopped unexpectedly"):
            execute_analysis(self.project, lambda phase: None, Event(), target=crashing_child)
        with self.assertRaisesRegex(ValueError, "at least one member"):
            execute_analysis(Project(), lambda phase: None, Event())

    def test_ui_cancel_retains_results_and_reenables_analysis(self):
        before = self.window.project.to_dict()
        snapshot = self.window.result.snapshot_id
        with patch("pynitegui.qt.analysis_jobs.analysis_child", slow_child), \
                patch("pynitegui.qt.app.QMessageBox.warning") as warning:
            self.window.run_analysis()
            self.assertFalse(self.window.analyze_action.isEnabled())
            self.assertTrue(self.window.analysis_progress.isVisible())
            self.assertTrue(self.window.cancel_analysis_action.isEnabled())
            self.wait_until(lambda: "busy test" in self.window.analysis_phase.text())
            self.window.cancel_analysis_action.trigger()
            self.wait_until(lambda: self.window.thread is None)
            warning.assert_not_called()
        self.assertEqual(self.window.result.snapshot_id, snapshot)
        self.assertEqual(self.window.project.to_dict(), before)
        self.assertTrue(self.window.export_menu.isEnabled())
        self.assertTrue(self.window.analyze_action.isEnabled())
        self.assertFalse(self.window.analysis_progress.isVisible())
        self.assertIn("cancelled", self.window.statusBar().currentMessage())
        self.window.run_analysis()
        self.wait_until(lambda: self.window.thread is None)
        self.assertNotEqual(self.window.result.snapshot_id, snapshot)

    def test_editor_change_invalidates_old_result_even_if_analysis_is_cancelled(self):
        with patch("pynitegui.qt.analysis_jobs.analysis_child", slow_child):
            self.window.run_analysis()
            self.wait_until(lambda: "busy test" in self.window.analysis_phase.text())
            self.window.edit("Move node", lambda project: setattr(project.nodes["N2"], "x", 432))
            self.window.cancel_analysis()
            self.wait_until(lambda: self.window.thread is None)
        self.assertIsNone(self.window.result)
        self.assertEqual(self.window.project.nodes["N2"].x, 432)
        self.assertFalse(self.window.export_menu.isEnabled())

    def test_cancel_request_wins_over_a_queued_success(self):
        self.window.analysis_cancel_requested = True
        self.window.analysis_finished(self.result.for_combination("Double"), "")
        self.assertEqual(self.window.result.combination, "Service")
        self.assertIn("cancelled", self.window.statusBar().currentMessage())

    def test_completed_result_from_edited_model_is_not_accepted(self):
        with patch("pynitegui.qt.analysis_jobs.analysis_child", delayed_child):
            self.window.run_analysis()
            self.wait_until(lambda: "Waiting before" in self.window.analysis_phase.text())
            self.window.edit("Move node", lambda project: setattr(project.nodes["N2"], "x", 432))
            self.wait_until(lambda: self.window.thread is None)
        self.assertIsNone(self.window.result)
        self.assertIn("Model changed during analysis", self.window.statusBar().currentMessage())

    def test_units_can_change_during_solve_without_discarding_physical_result(self):
        with patch("pynitegui.qt.analysis_jobs.analysis_child", delayed_child):
            self.window.run_analysis()
            self.wait_until(lambda: "Waiting before" in self.window.analysis_phase.text())
            self.window.set_units("si")
            self.wait_until(lambda: self.window.thread is None)
        self.assertIsNotNone(self.window.result)
        self.assertEqual(self.window.project.unit_system, "si")
        self.assertAlmostEqual(float(self.window.results_table.item(0, 5).text()), 5 * 4.4482216152605, places=4)

    def test_failed_reanalysis_retains_last_valid_snapshot(self):
        snapshot = self.window.result.snapshot_id
        with patch("pynitegui.qt.app.QMessageBox.warning") as warning:
            self.window.analysis_finished(None, "Unexpected worker failure")
            warning.assert_called_once()
        self.assertEqual(self.window.result.snapshot_id, snapshot)
        self.assertTrue(self.window.export_menu.isEnabled())
        self.assertIn("Previous results retained", self.window.statusBar().currentMessage())

    def test_close_cancels_and_keeps_unsaved_change_prompt(self):
        with patch("pynitegui.qt.analysis_jobs.analysis_child", slow_child):
            self.window.run_analysis()
            self.wait_until(lambda: "busy test" in self.window.analysis_phase.text())
            with patch.object(self.window, "confirm_discard", return_value=False) as confirm:
                self.window.close()
                self.wait_until(lambda: self.window.thread is None)
                self.wait_until(lambda: confirm.called)
            self.assertTrue(self.window.isVisible())
            self.assertFalse(self.window.close_after_analysis)
