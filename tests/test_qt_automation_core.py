"""GUI-thread automation, atomic edits and revision/permission boundaries."""
import contextlib
import io
import os
from threading import Thread
import time
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYNITEGUI_NO_WEBENGINE", "1")
from PySide6.QtCore import QThread
from PySide6.QtWidgets import QApplication, QMessageBox
from pynitegui.qt.analysis import analyze
from pynitegui.qt.app import MainWindow
from pynitegui.qt.automation_core import Permissions, QtCommandBridge, TOOLS
from pynitegui.qt.examples import example_project


class AutomationCoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = MainWindow()
        self.window.load_project(example_project("simple_beam"))
        self.permissions = Permissions()
        self.bridge = QtCommandBridge(self.window, self.permissions)
        self.bridge.set_active(True)
        self.logs = []
        self.bridge.logged.connect(self.logs.append)

    def wait_until(self, predicate, seconds=15):
        deadline = time.monotonic()+seconds
        while not predicate() and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(.005)
        self.assertTrue(predicate(), "Automation command timed out")

    def tearDown(self):
        self.bridge.set_active(False)
        if self.window.thread is not None:
            self.window.cancel_analysis()
            self.wait_until(lambda: self.window.thread is None)
        self.window.saved = self.window.project.to_dict()
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()

    def identity(self):
        return {"session_id": self.window.project_session, "expected_revision": self.window.automation_revision}

    def invoke(self, name, **arguments):
        future = self.bridge.submit(name, arguments)
        self.wait_until(future.done)
        return future.result()

    def edits(self, operations, **guard):
        self.permissions.set_group("Model edits", True)
        return self.invoke("apply_batch", **{**self.identity(), **guard}, operations=operations)

    def test_new_project_session_rejects_old_job_even_with_identical_geometry(self):
        self.window.analysis_revision = self.window.revision
        self.window.analysis_job_session = self.window.project_session
        result = analyze(self.window.project)
        self.window.project_session = "replacement-session"
        self.window.analysis_finished(result, "")
        self.assertIsNone(self.window.result)
        self.assertEqual(self.window.results_panel.analysis_state, "Outdated")

    def test_empty_model_reference_examples_validate_in_both_dimensions(self):
        from dataclasses import fields
        from pynitegui.qt.model import Project, Node
        from pynitegui.qt.spatial_model import SpatialProject, SpatialNode
        from pynitegui.qt.automation_core import batch_candidate
        for project, node_type in ((Project(), Node), (SpatialProject(), SpatialNode)):
            with self.subTest(dimension=getattr(project, "dimension", "2D")):
                self.window.load_project(project)
                docs = self.invoke("read_schema", session_id=self.window.project_session)
                self.assertTrue(docs["ok"], docs)
                schema = docs["data"]["schema"]
                self.assertEqual(set(schema["entities"]["nodes"]["properties"]), {field.name for field in fields(node_type)})
                example = batch_candidate(project, docs["data"]["examples"]["create_cantilever"])
                self.assertTrue(all(example.nodes["ExampleA"].restraints))
                self.assertEqual(example.members["ExampleBeam"].start, "ExampleA")
                self.assertEqual(example.loads["ExampleForce"].target, "ExampleB")
                self.assertFalse(self.window.project.nodes)
                invalid = self.invoke("read_schema", session_id="old-project")
                self.assertEqual(invalid["error"]["code"], "stale_session")

    def test_editor_busy_names_drawing_mode_and_preserves_batch(self):
        before = self.window.project.to_dict()
        self.window.set_mode("draw")
        response = self.edits([{"op":"put", "collection":"nodes", "key":"N3", "value":{"x": 200, "y": 100}}])
        self.assertEqual(response["error"]["code"], "editor_busy")
        self.assertIn("Select mode", response["error"]["message"])
        self.assertEqual(self.window.project.to_dict(), before)
        self.window.set_mode("select")
        response = self.edits([{"op":"put", "collection":"nodes", "key":"N3", "value":{"x": 200, "y": 100}}])
        self.assertTrue(response["ok"], response)

    def test_automation_controls_and_readonly_focus_do_not_block_edits(self):
        from PySide6.QtWidgets import QLineEdit
        self.window.show_automation_server()
        panel = self.window.automation_panel
        panel.port.findChild(QLineEdit).setModified(True)
        with patch.object(QApplication, "focusWidget", return_value=panel.port):
            self.assertFalse(self.window.live_analysis.is_editing())
            response = self.edits([{"op":"set", "collection":"settings", "value":{"grid":24}}])
            self.assertTrue(response["ok"], response)
        readonly = QLineEdit(self.window)
        readonly.setReadOnly(True)
        readonly.setModified(True)
        with patch.object(QApplication, "focusWidget", return_value=readonly):
            self.assertFalse(self.window.live_analysis.is_editing())
        readonly.deleteLater()

    def test_own_modal_dialog_and_gesture_block_even_when_panel_has_focus(self):
        from PySide6.QtWidgets import QDialog
        own, other = QDialog(self.window), QDialog()
        with patch.object(QApplication, "activeModalWidget", return_value=own):
            self.assertIn("editing dialog", self.window.live_analysis.editing_blocker())
        with patch.object(QApplication, "activeModalWidget", return_value=other), patch.object(QApplication, "focusWidget", return_value=None):
            self.assertFalse(self.window.live_analysis.is_editing())
        self.window.show_automation_server()
        self.window.planar_view.drag_node = "N2"
        with patch.object(QApplication, "focusWidget", return_value=self.window.automation_panel.port):
            self.assertIn("node drag", self.window.live_analysis.editing_blocker())
        self.window.planar_view.drag_node = None
        own.deleteLater()
        other.deleteLater()

    def test_modified_model_input_blocks_but_other_window_does_not(self):
        from PySide6.QtWidgets import QDoubleSpinBox, QLineEdit
        self.window.select(("nodes", "N2"))
        field = self.window.inspector.findChild(QDoubleSpinBox)
        field.findChild(QLineEdit).setModified(True)
        with patch.object(QApplication, "focusWidget", return_value=field):
            response = self.edits([{"op":"set", "collection":"settings", "value":{"grid":24}}])
            self.assertEqual(response["error"]["code"], "editor_busy")
            self.assertIn("Apply or discard", response["error"]["message"])
        other = QLineEdit()
        other.setModified(True)
        with patch.object(QApplication, "focusWidget", return_value=other):
            self.assertFalse(self.window.live_analysis.is_editing())
        other.deleteLater()

    def test_read_units_and_canonical_model_without_server_dependencies(self):
        response = self.invoke("read_model")
        self.assertTrue(response["ok"])
        self.assertEqual(response["data"]["model"], self.window.project.to_dict())
        units = self.invoke("read_units", session_id=self.window.project_session)
        self.assertEqual(units["data"]["canonical"], "in-kip")
        self.assertEqual(units["data"]["units"]["length"], "in")

    def test_atomic_geometry_load_support_material_section_and_case_transaction(self):
        before = self.window.project.to_dict()
        count = self.window.undo.count()
        operations = [
            {"op":"put", "collection":"materials", "key":"New steel", "value":{"E":30000}},
            {"op":"put", "collection":"sections", "key":"New section", "value":{"A":12,"Iy":20,"Iz":600,"J":1}},
            {"op":"put", "collection":"nodes", "key":"N3", "value":{"x":500,"y":30,"support":"fixed"}},
            {"op":"put", "collection":"members", "key":"M2", "value":{"start":"N2","end":"N3","material":"New steel","section":"New section"}},
            {"op":"put", "collection":"load_cases", "key":"Wind"},
            {"op":"put", "collection":"loads", "key":"L2", "value":{"target":"N3","direction":"FX","magnitude":2,"case":"Wind"}},
            {"op":"put", "collection":"combinations", "key":"Combined", "value":{"Case 1":1,"Wind":1.5}},
            {"op":"put", "collection":"nodes", "key":"N2", "value":{"support":"pin"}},
        ]
        response = self.edits(operations)
        self.assertTrue(response["ok"], response)
        self.assertEqual(self.window.undo.count(), count+1)
        self.assertEqual(self.window.project.nodes["N3"].support, "fixed")
        self.assertEqual(self.window.project.loads["L2"].case, "Wind")
        self.assertEqual(self.window.project.members["M2"].section, "New section")
        self.window.undo.undo()
        self.assertEqual(self.window.project.to_dict(), before)
        self.window.undo.redo()
        self.assertEqual(len(self.window.project.members), 2)

    def test_invalid_batch_unknown_fields_and_dependent_deletes_leave_model_and_undo_unchanged(self):
        before, count = self.window.project.to_dict(), self.window.undo.count()
        batches = [
            [{"op":"put","collection":"nodes","key":"N2","value":{"x":450}}, {"op":"put","collection":"members","key":"M2","value":{"start":"missing","end":"N2"}}],
            [{"op":"delete","collection":"nodes","key":"N1"}],
            [{"op":"put","collection":"nodes","key":"N1","value":{"unknown":True}}],
            [{"op":"set","collection":"settings","value":{"dimension":"3D"}}],
            [{"op":"put","collection":"files","key":"foo","value":{}}],
            [{"op":"put","collection":"nodes","key":"N2","value":{"x":float("nan")}}],
        ]
        with patch.object(QMessageBox, "warning") as warning:
            for operations in batches:
                self.assertFalse(self.edits(operations)["ok"])
                self.assertEqual(self.window.project.to_dict(), before)
                self.assertEqual(self.window.undo.count(), count)
            warning.assert_not_called()

    def test_session_revision_unit_edits_and_undo_reject_stale_requests(self):
        old = self.identity()
        physical = self.window.revision
        self.window.set_units("si")
        self.assertEqual(self.window.revision, physical)
        response = self.edits([{"op":"set","collection":"settings","value":{"grid":24}}], **old)
        self.assertEqual(response["error"]["code"], "stale_revision")
        old = self.identity()
        self.window.undo.undo()
        self.assertNotEqual(old["expected_revision"], self.window.automation_revision)
        self.window.load_project(example_project("simple_beam"))
        response = self.edits([{"op":"set","collection":"settings","value":{"grid":24}}], **old)
        self.assertEqual(response["error"]["code"], "stale_session")

    def test_permissions_are_rechecked_after_queuing_and_shutdown_invalidates_old_requests(self):
        self.permissions.set_group("Model edits", True)
        arguments = {**self.identity(), "operations":[{"op":"set","collection":"settings","value":{"grid":24}}]}
        future = self.bridge.submit("apply_batch", arguments)
        self.permissions.set_tool("apply_batch", False)
        self.wait_until(future.done)
        self.assertEqual(future.result()["error"]["code"], "permission_denied")
        future = self.bridge.submit("read_model", {})
        self.bridge.set_active(False)
        self.bridge.set_active(True)
        self.wait_until(future.done)
        self.assertEqual(future.result()["error"]["code"], "server_stopped")

    def test_cancelled_queued_mutation_never_applies_and_noop_adds_no_undo(self):
        self.permissions.set_group("Model edits", True)
        before = self.window.project.to_dict()
        future = self.bridge.submit("apply_batch", {**self.identity(), "operations":[{"op":"set","collection":"settings","value":{"grid":24}}]})
        future.cancel()
        self.app.processEvents()
        self.assertEqual(self.window.project.to_dict(), before)
        count = self.window.undo.count()
        response = self.edits([{"op":"set","collection":"settings","value":{"grid":self.window.project.grid}}])
        self.assertTrue(response["ok"])
        self.assertFalse(response["data"]["changed"])
        self.assertEqual(self.window.undo.count(), count)

    def test_foreign_thread_dispatch_executes_only_on_gui_thread(self):
        threads, responses = [], []
        original = self.bridge.commands.execute
        def execute(*arguments):
            threads.append(QThread.currentThread())
            return original(*arguments)
        with patch.object(self.bridge.commands, "execute", execute):
            thread = Thread(target=lambda: responses.append(self.bridge.submit("read_model", {}).result(3)))
            thread.start()
            self.wait_until(lambda: bool(responses))
            thread.join()
        self.assertEqual(threads, [self.app.thread()])
        self.assertTrue(responses[0]["ok"])

    def test_logs_omit_arguments_names_and_validation_messages(self):
        secret = "private-value-do-not-log"
        self.edits([{"op":"put","collection":"loads","key":secret,"value":{"target":"missing","magnitude":2}}])
        self.assertTrue(self.logs)
        self.assertNotIn(secret, "\n".join(self.logs))
        self.assertTrue(all(line.startswith("apply_batch | ") for line in self.logs))

    def test_spatial_edits_and_result_pages_have_snapshot_identity_and_units(self):
        self.window.load_project(example_project("3d_cantilever"))
        response = self.edits([{"op":"put","collection":"nodes","key":"N2","value":{"z":30}},
                               {"op":"put","collection":"members","key":"M1","value":{"roll":25}}])
        self.assertTrue(response["ok"], response)
        with contextlib.redirect_stdout(io.StringIO()):
            result = analyze(self.window.project)
        self.window.analysis_revision = self.window.revision
        self.window.analysis_finished(result, "")
        response = self.invoke("read_results", session_id=self.window.project_session, kind="members", limit=2)
        self.assertTrue(response["ok"], response)
        self.assertEqual(len(response["data"]["rows"]), 2)
        self.assertEqual(response["data"]["snapshot_id"], result.snapshot_id)
        self.assertIn("Vz (kip)", response["data"]["headers"])
        stale = self.invoke("read_results", session_id=self.window.project_session, snapshot_id="old")
        self.assertEqual(stale["error"]["code"], "stale_snapshot")

    def test_automation_analysis_runs_existing_job_and_failure_is_nonmodal(self):
        self.permissions.set_group("Analysis", True)
        self.window.edit("Supports", lambda project: [setattr(node, "support", "free") for node in project.nodes.values()])
        with patch.object(QMessageBox, "warning") as warning:
            response = self.invoke("run_analysis", **self.identity())
            self.assertTrue(response["ok"], response)
            job = response["data"]["job_id"]
            self.wait_until(lambda: self.window.thread is None)
            warning.assert_not_called()
        status = self.invoke("analysis_status", session_id=self.window.project_session, job_id=job)
        self.assertEqual(status["data"]["state"], "Failed")
        self.assertTrue(status["data"]["error"])
        self.assertTrue(self.window.model_findings.list.count())


if __name__ == "__main__":
    unittest.main()
