"""Optional SDK wire tests plus dependency-free native lifecycle checks."""
import asyncio
from concurrent.futures import Future
import importlib.util
import os
import socket
import subprocess
from threading import Thread
import time
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYNITEGUI_NO_WEBENGINE", "1")
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
from pynitegui.qt.app import MainWindow
from pynitegui.qt.automation_server import AutomationPanel, AutomationServer, dependencies_available
from pynitegui.qt.examples import example_project


def slow_automation_child(connection, project):
    connection.send(("progress", "Slow automation test solve"))
    time.sleep(60)


class ServerWindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = MainWindow()
        self.window.load_project(example_project("simple_beam"))
        self.server = AutomationServer(self.window)
        self.panel = AutomationPanel(self.window, self.server)
        self.window.automation_server = self.server

    def wait_until(self, predicate, seconds=15):
        deadline = time.monotonic()+seconds
        while not predicate() and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(.005)
        self.assertTrue(predicate(), "Server lifecycle timed out")

    def tearDown(self):
        self.server.stop()
        self.wait_until(lambda: self.server.thread is None)
        if self.window.thread is not None:
            self.window.cancel_analysis()
            self.wait_until(lambda: self.window.thread is None)
        self.window.saved = self.window.project.to_dict()
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()

    def test_missing_extra_is_explained_without_installing(self):
        with patch("pynitegui.qt.automation_server.dependencies_available", return_value=False):
            self.assertFalse(self.server.start())
        self.assertEqual(self.server.state, "Unavailable")
        self.assertIn("uv sync --extra mcp", self.panel.status.text())
        self.assertIsNone(self.server.thread)
        self.assertFalse(self.panel.copy_token.isEnabled())

    def test_desktop_import_and_panel_work_when_all_optional_packages_are_blocked(self):
        import sys
        source = '''
import importlib.abc, sys
class BlockOptional(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'mcp','mcp_types','uvicorn','starlette','pydantic'}:
            raise ModuleNotFoundError(fullname)
sys.meta_path.insert(0, BlockOptional())
from PySide6.QtWidgets import QApplication
from pynitegui.qt.app import MainWindow
app = QApplication([])
window = MainWindow()
window.show_automation_server()
assert window.automation_server.state == 'Stopped'
window.close()
'''
        result = subprocess.run([sys.executable, "-B", "-c", source], capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_group_and_tool_switches_default_to_read_access(self):
        self.assertTrue(self.server.permissions.allows("read_model"))
        self.assertFalse(self.server.permissions.allows("apply_batch"))
        tree = self.panel.permissions
        group = next(tree.topLevelItem(index) for index in range(tree.topLevelItemCount())
                     if tree.topLevelItem(index).text(0) == "Model edits")
        group.setCheckState(0, Qt.CheckState.Checked)
        self.assertTrue(self.server.permissions.allows("apply_batch"))
        group.child(0).setCheckState(0, Qt.CheckState.Unchecked)
        self.assertFalse(self.server.permissions.allows("apply_batch"))

    def test_auth_checkbox_defaults_on_and_omits_token_free_config_headers(self):
        self.assertTrue(self.server.require_token)
        self.assertTrue(self.panel.require_token.isChecked())
        self.panel.require_token.setChecked(False)
        self.assertFalse(self.server.require_token)
        self.assertFalse(self.panel.token.isEnabled())
        self.assertFalse(self.panel.copy_token.isEnabled())
        self.assertNotIn("headers", self.server.configuration()["mcpServers"]["PyniteGUI"])
        self.panel.require_token.setChecked(True)
        self.assertTrue(self.server.require_token)

    def test_auth_preference_is_remembered_without_persisting_tokens(self):
        import tempfile
        from PySide6.QtCore import QSettings
        with tempfile.TemporaryDirectory() as directory:
            settings = QSettings(directory+"/preferences.ini", QSettings.Format.IniFormat)
            first = MainWindow(settings=settings)
            first.show_automation_server()
            first.automation_panel.require_token.setChecked(False)
            settings.sync()
            first.close()
            first.deleteLater()
            restored = MainWindow(settings=QSettings(directory+"/preferences.ini", QSettings.Format.IniFormat))
            restored.show_automation_server()
            self.assertFalse(restored.automation_server.require_token)
            self.assertFalse(restored.automation_panel.require_token.isChecked())
            self.assertEqual(settings.allKeys(), ["automation_require_token"])
            restored.close()
            restored.deleteLater()
            self.app.processEvents()


@unittest.skipUnless(dependencies_available(), "Install the optional mcp extra for wire tests")
class ServerWireTests(ServerWindowTests):
    # Keep the base window helpers but avoid duplicating its standalone tests.
    test_missing_extra_is_explained_without_installing = None
    test_desktop_import_and_panel_work_when_all_optional_packages_are_blocked = None
    test_group_and_tool_switches_default_to_read_access = None
    test_auth_checkbox_defaults_on_and_omits_token_free_config_headers = None
    test_auth_preference_is_remembered_without_persisting_tokens = None

    def setUp(self):
        super().setUp()
        self.assertTrue(self.server.start(0), self.server.detail)
        self.wait_until(lambda: self.server.state != "Starting")
        self.assertEqual(self.server.state, "Running", self.server.detail)

    def run_async(self, operation):
        future = Future()
        def run():
            try:
                future.set_result(asyncio.run(operation()))
            except BaseException as error:
                future.set_exception(error)
        thread = Thread(target=run, daemon=True)
        thread.start()
        self.wait_until(future.done)
        thread.join()
        return future.result()

    def with_client(self, callback):
        async def run():
            import httpx2
            from mcp import ClientSession
            from mcp.client.streamable_http import streamable_http_client
            headers = {"Authorization":"Bearer "+self.server.token} if self.server.require_token else {}
            async with httpx2.AsyncClient(headers=headers, trust_env=False) as http:
                async with streamable_http_client(self.server.endpoint, http_client=http) as (read, write):
                    async with ClientSession(read, write, read_timeout_seconds=5) as client:
                        await client.initialize()
                        return await callback(client)
        return self.run_async(run)

    def test_official_client_discovers_reads_model_units_and_snapshot_results(self):
        async def callback(client):
            listed = await client.list_tools()
            self.assertEqual({tool.name for tool in listed.tools}, {"read_model","read_schema","read_units","read_results"})
            response = await client.call_tool("read_model", {})
            self.assertFalse(response.is_error, response)
            model = response.structured_content["data"]
            units = await client.call_tool("read_units", {"session_id":model["session_id"]})
            self.assertEqual(units.structured_content["data"]["canonical"], "in-kip")
            missing = await client.call_tool("read_results", {"session_id":model["session_id"]})
            self.assertTrue(missing.is_error)
            self.assertEqual(missing.structured_content["error"]["code"], "no_results")
            return model
        model = self.with_client(callback)
        self.assertEqual(model["model"], self.window.project.to_dict())
        self.assertGreater(self.server.requests, 0)

    def test_cached_tool_calls_cannot_bypass_revocation_and_real_wire_edits_undo(self):
        self.server.permissions.set_group("Model edits", True)
        original = self.window.project.to_dict()
        async def callback(client):
            model = (await client.call_tool("read_model", {})).structured_content["data"]
            arguments = {"session_id":model["session_id"], "expected_revision":model["revision"],
                         "operations":[{"op":"put","collection":"nodes","key":"N2","value":{"x":480}}]}
            response = await client.call_tool("apply_batch", arguments)
            self.assertFalse(response.is_error, response)
            self.server.permissions.set_group("Model edits", False)
            denied = await client.call_tool("apply_batch", arguments)
            self.assertTrue(denied.is_error)
            self.assertEqual(denied.structured_content["error"]["code"], "permission_denied")
            tools = await client.list_tools()
            self.assertNotIn("apply_batch", {tool.name for tool in tools.tools})
        self.with_client(callback)
        self.assertEqual(self.window.project.nodes["N2"].x, 480)
        self.window.undo.undo()
        self.assertEqual(self.window.project.to_dict(), original)

    def test_token_free_client_reads_edits_and_restarts_without_config_changes(self):
        port = int(self.server.endpoint.split(":")[2].split("/")[0])
        self.server.stop()
        self.wait_until(lambda: self.server.thread is None)
        self.panel.require_token.setChecked(False)
        self.assertTrue(self.server.start(port))
        self.wait_until(lambda: self.server.state == "Running")
        self.assertFalse(self.panel.require_token.isEnabled())
        self.assertFalse(self.server.set_require_token(True))
        self.assertFalse(self.server.require_token)
        self.assertEqual(self.server.token, "")
        self.assertFalse(self.panel.copy_token.isEnabled())
        config = self.server.configuration()
        self.assertEqual(config["mcpServers"]["PyniteGUI"], {"url": self.server.endpoint})
        self.window.automation_mode.set_enabled(True)
        self.assertTrue(self.window.mcp_mode)
        async def callback(client):
            model = (await client.call_tool("read_model", {})).structured_content["data"]
            self.assertTrue(model["mcp_mode"])
            args = {"session_id":model["session_id"], "expected_revision":model["revision"],
                    "operations":[{"op":"put", "collection":"nodes", "key":"N2", "value":{"x":480}}]}
            denied = await client.call_tool("apply_batch", args)
            self.assertTrue(denied.is_error)
            self.server.permissions.set_group("Model edits", True)
            changed = await client.call_tool("apply_batch", args)
            self.assertFalse(changed.is_error, changed)
        self.with_client(callback)
        self.assertEqual(self.window.project.nodes["N2"].x, 480)
        self.assertGreater(self.server.requests, 0)
        self.assertIn("Last accepted request", self.panel.status.text())
        self.server.stop()
        self.wait_until(lambda: self.server.thread is None)
        self.assertTrue(self.server.start(port))
        self.wait_until(lambda: self.server.state == "Running")
        self.assertEqual(self.server.configuration(), config)
        async def read_again(client):
            response = await client.call_tool("read_model", {})
            self.assertFalse(response.is_error)
        self.with_client(read_again)

    def test_token_free_mode_still_rejects_invalid_host_origin_and_can_restore_auth(self):
        self.server.stop()
        self.wait_until(lambda: self.server.thread is None)
        self.server.set_require_token(False)
        self.assertTrue(self.server.start(0))
        self.wait_until(lambda: self.server.state == "Running")
        async def requests():
            import httpx2
            from pynitegui.qt.automation_transport import build_application
            application = build_application(self.server.bridge, self.server.permissions, "",
                int(self.server.endpoint.split(":")[2].split("/")[0]), self.server.network_event, require_token=False)
            sent = []
            async def send(message):
                sent.append(message)
            async def receive():
                return {"type":"http.request", "body":b"{}", "more_body":False}
            await application({"type":"http", "client":("203.0.113.1", 1234),
                "headers":[(b"host", self.server.endpoint.split("//")[1].split("/")[0].encode())]}, receive, send)
            self.assertEqual(sent[0]["status"], 403)
            self.assertIn(b"invalid_host", sent[1]["body"])
            async with httpx2.AsyncClient(trust_env=False) as client:
                for headers in ({"Host":"evil.example"}, {"Origin":"http://evil.example"}, {"Origin":"null"}):
                    response = await client.post(self.server.endpoint, headers=headers, json={})
                    self.assertEqual(response.status_code, 403)
                # A leftover client token is irrelevant when token authentication is disabled.
                response = await client.post(self.server.endpoint, headers={"Authorization":"Bearer obsolete"}, json={})
                self.assertNotEqual(response.status_code, 401)
        self.run_async(requests)
        self.server.stop()
        self.wait_until(lambda: self.server.thread is None)
        self.server.set_require_token(True)
        self.assertTrue(self.server.start(0))
        self.wait_until(lambda: self.server.state == "Running")
        self.assertTrue(self.server.token)
        async def unauthorized():
            import httpx2
            async with httpx2.AsyncClient(trust_env=False) as client:
                return (await client.post(self.server.endpoint, json={})).status_code
        self.assertEqual(self.run_async(unauthorized), 401)

    def test_auth_host_origin_duplicate_headers_and_secret_free_logs(self):
        token = self.server.token
        async def callback():
            import httpx2
            async with httpx2.AsyncClient(trust_env=False) as client:
                for headers, status in (({},401), ({"Authorization":"Bearer wrong"},401),
                    ({"Authorization":"Bearer "+token, "Host":"evil.example"},403),
                    ({"Authorization":"Bearer "+token, "Origin":"http://evil.example"},403),
                    ({"Authorization":"Bearer "+token, "Origin":"null"},403)):
                    response = await client.post(self.server.endpoint, headers=headers, json={})
                    self.assertEqual(response.status_code, status)
                response = await client.post(self.server.endpoint,
                    headers=[("Authorization","Bearer "+token),("Authorization","Bearer "+token)], json={})
                self.assertEqual(response.status_code, 401)
        self.run_async(callback)
        self.app.processEvents()
        self.assertNotIn(token, self.panel.log.toPlainText())
        self.assertNotIn("evil.example", self.panel.log.toPlainText())
        self.assertIn("unauthorized", self.panel.log.toPlainText())

    def test_start_stop_restart_rotates_token_and_port_conflicts_are_actionable(self):
        endpoint, token = self.server.endpoint, self.server.token
        port = int(endpoint.split(":")[2].split("/")[0])
        second = AutomationServer(self.window)
        self.assertFalse(second.start(port))
        self.assertIn("bind localhost port", second.detail)
        self.window.automation_mode.set_enabled(True)
        self.assertTrue(self.window.mcp_mode)
        self.server.stop()
        self.assertFalse(self.window.mcp_mode)
        self.assertTrue(self.window.centralWidget().isEnabled())
        self.wait_until(lambda: self.server.thread is None)
        self.assertTrue(self.server.start(port), self.server.detail)
        self.wait_until(lambda: self.server.state == "Running")
        self.assertNotEqual(token, self.server.token)
        async def old_token():
            import httpx2
            async with httpx2.AsyncClient(trust_env=False) as client:
                return (await client.post(endpoint, headers={"Authorization":"Bearer "+token}, json={})).status_code
        self.assertEqual(self.run_async(old_token), 401)

    def test_wire_schema_and_reference_resource_document_empty_models(self):
        from pynitegui.qt.model import Project
        self.window.load_project(Project())
        async def callback(client):
            model = (await client.call_tool("read_model", {})).structured_content["data"]
            self.assertEqual(model["model"]["nodes"], {})
            self.assertIn("support", model["schema"]["entities"]["nodes"]["properties"])
            reference = (await client.call_tool("read_schema", {"session_id": model["session_id"]})).structured_content["data"]
            self.assertEqual(reference["schema"]["dimension"], "2D")
            self.assertEqual(reference["examples"]["create_cantilever"][0]["value"]["support"], "fixed")
            resources = await client.list_resources()
            self.assertIn("pynitegui://automation/reference", {str(resource.uri) for resource in resources.resources})
            import json
            resource = await client.read_resource("pynitegui://automation/reference")
            docs = json.loads(resource.contents[0].text)
            self.assertIn("restraint_z", docs["3D"]["entities"]["nodes"]["properties"])
            self.server.permissions.set_tool("read_schema", False)
            denied = await client.call_tool("read_schema", {"session_id": model["session_id"]})
            self.assertTrue(denied.is_error)
        self.with_client(callback)

    def test_wire_successful_analysis_and_paginated_snapshot_results(self):
        self.window.automation_mode.set_enabled(True)
        self.assertTrue(self.window.mcp_mode)
        self.assertFalse(self.window.centralWidget().isEnabled())
        self.server.permissions.set_group("Analysis", True)
        async def callback(client):
            model = (await client.call_tool("read_model", {})).structured_content["data"]
            args = {"session_id": model["session_id"], "expected_revision": model["revision"]}
            started = await client.call_tool("run_analysis", args)
            self.assertFalse(started.is_error, started)
            for _ in range(300):
                status = (await client.call_tool("analysis_status", {"session_id": model["session_id"]})).structured_content["data"]
                if not status["running"]:
                    break
                await asyncio.sleep(.02)
            self.assertEqual(status["state"], "Current", status)
            result = await client.call_tool("read_results", {"session_id": model["session_id"],
                "snapshot_id": status["snapshot"]["snapshot_id"], "limit": 1})
            self.assertFalse(result.is_error, result)
            data = result.structured_content["data"]
            self.assertEqual(len(data["rows"]), 1)
            self.assertEqual(data["total_rows"], len(model["model"]["nodes"]))
            self.assertEqual(data["snapshot_id"], status["snapshot"]["snapshot_id"])
            stale = await client.call_tool("run_analysis", {**args, "expected_revision": -1})
            self.assertTrue(stale.is_error)
            self.assertEqual(stale.structured_content["error"]["code"], "stale_revision")
        self.with_client(callback)

    def test_listener_exit_automatically_releases_mcp_mode(self):
        self.window.automation_mode.set_enabled(True)
        self.assertTrue(self.window.mcp_mode)
        self.server.server.should_exit = True  # Listener exits without the user clicking Stop.
        self.wait_until(lambda: self.server.thread is None)
        self.assertFalse(self.window.mcp_mode)
        self.assertTrue(self.window.centralWidget().isEnabled())
        self.assertFalse(self.window.mcp_mode_button.isEnabled())

    def test_wire_analysis_progress_cancellation_and_no_modal_errors(self):
        self.server.permissions.set_group("Analysis", True)
        async def callback(client):
            model = (await client.call_tool("read_model", {})).structured_content["data"]
            run = await client.call_tool("run_analysis", {"session_id":model["session_id"], "expected_revision":model["revision"]})
            self.assertFalse(run.is_error, run)
            job = run.structured_content["data"]["job_id"]
            for _ in range(100):
                status = await client.call_tool("analysis_status", {"session_id":model["session_id"], "job_id":job})
                if "Slow automation" in status.structured_content["data"]["phase"]:
                    break
                await asyncio.sleep(.02)
            else:
                self.fail("No analysis phase received")
            cancelled = await client.call_tool("cancel_analysis", {"session_id":model["session_id"], "job_id":job})
            self.assertFalse(cancelled.is_error, cancelled)
            return job
        with patch("pynitegui.qt.analysis_jobs.analysis_child", slow_automation_child):
            self.with_client(callback)
            self.wait_until(lambda: self.window.thread is None)
        self.assertEqual(self.window.results_panel.analysis_state, "Cancelled")

    def test_strict_revision_types_request_limits_and_window_close_stop_server(self):
        self.server.permissions.set_group("Model edits", True)
        async def callback(client):
            model = (await client.call_tool("read_model", {})).structured_content["data"]
            result = await client.call_tool("apply_batch", {"session_id":model["session_id"], "expected_revision":True,
                "operations":[{"op":"set","collection":"settings","value":{"grid":24}}]})
            self.assertTrue(result.is_error)
        self.with_client(callback)
        async def oversized():
            import httpx2
            async with httpx2.AsyncClient(trust_env=False) as client:
                return (await client.post(self.server.endpoint, headers={"Authorization":"Bearer "+self.server.token},
                    content=b"x"*(1024*1024+1))).status_code
        self.assertEqual(self.run_async(oversized), 413)
        self.window.saved = self.window.project.to_dict()
        self.window.close()
        self.wait_until(lambda: self.server.thread is None)
        self.assertEqual(self.server.state, "Stopped")


if __name__ == "__main__":
    unittest.main()
