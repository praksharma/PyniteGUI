"""Test a real installed wheel outside the source checkout, with optional MCP."""
import argparse
import asyncio
from concurrent.futures import Future
import contextlib
import importlib.metadata
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from threading import Thread
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYNITEGUI_NO_WEBENGINE", "1")
os.environ.setdefault("MPLCONFIGDIR", str(Path(tempfile.gettempdir()) / "pynite-release-mpl"))


def wait(app, predicate, seconds=20):
    deadline = time.monotonic() + seconds
    while not predicate() and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(.005)
    assert predicate(), "Installed smoke operation timed out"


def mcp_smoke(app, window, version):
    from pynitegui.qt.automation_core import TOOLS
    from pynitegui.qt.automation_server import AutomationServer
    server = AutomationServer(window)
    window.automation_server = server
    server.permissions.set_group(TOOLS["apply_batch"][0], True)
    before = window.project.to_dict()
    try:
        assert server.start(0), server.detail
        wait(app, lambda: server.state != "Starting")
        assert server.state == "Running", server.detail
        future = Future()
        async def client_check():
            import httpx2
            from mcp import ClientSession
            from mcp.client.streamable_http import streamable_http_client
            async with httpx2.AsyncClient(headers={"Authorization": "Bearer " + server.token}, trust_env=False) as http:
                async with streamable_http_client(server.endpoint, http_client=http) as (read, write):
                    async with ClientSession(read, write, read_timeout_seconds=10) as client:
                        initialized = await client.initialize()
                        assert initialized.server_info.version == version
                        response = await client.call_tool("read_model", {})
                        assert not response.is_error
                        model = response.structured_content["data"]
                        assert model["model"] == before and model["schema"]
                        edited = await client.call_tool("apply_batch", {"session_id": model["session_id"],
                            "expected_revision": model["revision"], "operations": [
                                {"op": "set", "collection": "settings", "value": {"grid": before["grid"] * 2}}]})
                        assert not edited.is_error, edited
                        assert edited.structured_content["data"]["changed"]
        def run():
            try:
                future.set_result(asyncio.run(client_check()))
            except BaseException as error:
                future.set_exception(error)
        worker = Thread(target=run, daemon=True)
        worker.start()
        wait(app, future.done, 30)
        worker.join(timeout=5)
        future.result()
        assert window.project.grid == before["grid"] * 2
        window.undo.undo()
        assert window.project.to_dict() == before
        print("PASS: installed MCP version, authenticated discovery, atomic edit and undo")
    finally:
        server.stop()
        wait(app, lambda: server.thread is None)


def main(version, mcp):
    import pynitegui
    from PySide6.QtWidgets import QApplication
    from pynitegui.qt.analysis import analyze
    from pynitegui.qt.app import MainWindow
    from pynitegui.qt.automation_server import dependencies_available
    from pynitegui.qt.examples import EXAMPLES, example_project
    from pynitegui.qt.model import Project
    from pynitegui.qt.reports import export_csv, report_html
    installed = Path(pynitegui.__file__).resolve()
    assert installed.is_relative_to(Path(sys.prefix).resolve()), f"Not an installed wheel: {installed}"
    assert pynitegui.__version__ == importlib.metadata.version("pynitegui") == version
    entry = Path(sys.executable).parent / ("pynitegui.exe" if os.name == "nt" else "pynitegui")
    assert subprocess.check_output([str(entry), "--version"], text=True, timeout=20).strip() == f"PyniteGUI {version}"
    assert dependencies_available() == mcp, "Wrong optional-dependency profile"
    assets = installed.parent / "qt/viewport3d"
    for name in ("index.html", "viewer.js", "frame_meshes.js", "node_drag.js", "vendor/three.module.js",
                 "vendor/three.core.js", "vendor/OrbitControls.js", "vendor/LICENSE"):
        assert (assets / name).is_file(), f"Missing installed viewport asset: {name}"
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    try:
        with tempfile.TemporaryDirectory(prefix="pynite-installed-smoke-") as directory:
            for key in EXAMPLES:
                project = example_project(key)
                path = Path(directory) / f"{key}.json"
                project.save(path)
                restored = Project.open(path)
                assert restored.to_dict() == project.to_dict()
                with contextlib.redirect_stdout(io.StringIO()):
                    result = analyze(restored)
                assert result.model_signature and result.solver.load_combos
                export_csv(Path(directory) / f"{key}.csv", restored, result, "nodes")
                assert "<html" in report_html(restored, result).lower()
                window.load_project(restored)
                window.analysis_revision = window.revision
                window.analysis_finished(result, None)
                assert window.result is not None
            if mcp:
                mcp_smoke(app, window, version)
        print(f"PASS: {version}, installed at {installed}; {len(EXAMPLES)} examples save/open/analyze/export and native windows")
    finally:
        window.saved = window.project.to_dict()
        window.close()
        window.deleteLater()
        app.processEvents()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True)
    parser.add_argument("--mcp", action="store_true")
    arguments = parser.parse_args()
    main(arguments.version, arguments.mcp)
