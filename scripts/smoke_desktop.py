"""Visible installed-wheel checks through Qt controls and the real WebEngine.

Run with an installed MCP wheel in a desktop session, outside the checkout:
  python /path/to/scripts/smoke_desktop.py --output /tmp/pynite-desktop-qa

Disposable settings/projects; native QtTest clicks and application commands.
File chooser paths are supplied. This does not certify human keyboard/mouse use,
OS-native file choosers, physical printing or any other platform.
"""
import argparse
import base64
import faulthandler
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import sys
import time
from unittest.mock import patch


def main(output, hold=False):
    if os.environ.get("QT_QPA_PLATFORM") in ("offscreen", "minimal") or os.environ.get("PYNITEGUI_NO_WEBENGINE") == "1":
        raise RuntimeError("Use a visible native desktop with WebEngine enabled.")
    import pynitegui
    assert Path(pynitegui.__file__).resolve().is_relative_to(Path(sys.prefix).resolve()), "Install a wheel; do not use an editable checkout."
    from PySide6.QtCore import QSettings, Qt, QTimer
    from PySide6.QtPrintSupport import QPrintPreviewDialog, QPrinter
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QFileDialog
    from pynitegui.qt.graphics import configure_graphics
    configure_graphics("auto")
    from pynitegui.qt.app import MainWindow
    from pynitegui.qt.diagrams import DiagramDialog
    from pynitegui.qt.geometry_panel import open_geometry_tool
    from pynitegui.qt.reports import report_document, report_printer
    from pynitegui.qt.theme import configure_theme
    from pynitegui.qt.window_controls import install_window_controls
    output.mkdir(parents=True, exist_ok=True)
    app = QApplication.instance() or QApplication([])
    app.setApplicationName("PyniteGUI Desktop QA")
    app.setApplicationVersion(pynitegui.__version__)
    app.setProperty("pynitegui_graphics", "auto")
    configure_theme(app, "light")
    install_window_controls(app)
    window = MainWindow(output/"recovery", QSettings(str(output/"settings.ini"), QSettings.Format.IniFormat))
    window.resize(1400, 960)
    window.show()
    record = {"version": pynitegui.__version__, "platform": platform.platform(), "python": platform.python_version(),
              "qt_platform": app.platformName(), "installed": str(Path(pynitegui.__file__).resolve()),
              "dependencies": {name: importlib.metadata.version(name) for name in ("PySide6", "pynitefea", "matplotlib", "numpy", "scipy", "mcp")},
              "method": "Visible QtTest/application-command automation; supplied file paths; no human/native-file-chooser certification", "checks": []}
    def wait(predicate, seconds=60):
        deadline = time.monotonic()+seconds
        while not predicate() and time.monotonic() < deadline:
            app.processEvents()
            QTest.qWait(20)
        assert predicate(), "Native workflow timed out"
    def capture(name, widget=None):
        QTest.qWait(350)
        assert (widget or window).grab().save(str(output/name))
    def click(widget):
        QTest.mouseClick(widget, Qt.MouseButton.LeftButton)
        app.processEvents()
    def checked(text):
        record["checks"].append(text)
        (output/"record.json").write_text(json.dumps(record, indent=2)+"\n")
        print("PASS: "+text, flush=True)
    # Fail with evidence instead of hanging in an unexpected modal question.
    def unexpected_dialog():
        dialog = app.activeModalWidget()
        if dialog is not None:
            (output/"unexpected-dialog.json").write_text(json.dumps({"title": dialog.windowTitle(),
                "text": dialog.text() if hasattr(dialog, "text") else "", "dirty_fields": [k for k,v in window.project.to_dict().items() if window.saved.get(k)!=v]}, indent=2))
            dialog.grab().save(str(output/"unexpected-dialog.png"))
            dialog.reject()
    watchdog = QTimer()
    watchdog.timeout.connect(unexpected_dialog)
    watchdog.start(2000)
    trace = (output/"timeout-trace.txt").open("w")
    faulthandler.dump_traceback_later(180, repeat=True, file=trace)
    try:
        open_geometry_tool(window, 1)
        panel = window.geometry_panel
        click(panel.preview_button)
        assert not window.project.members and panel.plan is not None
        window.view.fit()
        capture("generator-preview.png")
        click(panel.apply_button)
        assert (len(window.project.nodes), len(window.project.members)) == (9, 10)
        window.undo.undo()
        assert not window.project.members
        panel.cancel()
        checked("Native generator preview/apply and one-step undo")
        window.example("simple_beam")
        window.select_many([("members", "M1")])
        open_geometry_tool(window, 0)
        panel = window.geometry_panel
        c = panel.controls
        c["operation"].setCurrentIndex(c["operation"].findData("repeat"))
        c["offset_X"].setValue(0.)
        c["offset_Y"].setValue(144.)
        c["copies"].setValue(1)
        c["copy_loads"].setChecked(True)
        c["copy_supports"].setChecked(True)
        click(panel.preview_button)
        assert panel.plan is not None, panel.summary.text()
        window.view.fit()
        capture("array-preview.png")
        click(panel.apply_button)
        assert (len(window.project.members), len(window.project.loads)) == (2, 2)
        window.undo.undo()
        assert (len(window.project.members), len(window.project.loads)) == (1, 1)
        window.undo.redo()
        assert len(window.project.members) == 2
        window.undo.undo()
        panel.cancel()
        checked("Native array, copied loads/supports, undo and redo")
        path = output/"beam.pynite.json"
        definition = window.project.to_dict()
        with patch.object(QFileDialog, "getSaveFileName", return_value=(str(path), "")):
            assert window.save_project()
        with patch.object(QFileDialog, "getOpenFileName", return_value=(str(path), "")):
            window.open_project()
        assert window.project.to_dict() == definition
        checked("Save/reopen commands and current schema using supplied file paths")
        window.analyze_action.trigger()
        wait(lambda: window.thread is None and window.result is not None)
        dialog = DiagramDialog(window, window.project, window.result)
        dialog.show()
        dialog.tabs.setCurrentWidget(dialog.envelopes)
        envelope = dialog.envelopes
        envelope.filters.component.setCurrentIndex(envelope.filters.component.findData("Member:Mz"))
        envelope.station_query.search()
        assert len(envelope.station_query.rows) == 3
        envelope.views.setCurrentWidget(envelope.station_query)
        capture("governing-stations.png", dialog)
        dialog.reject()
        with patch.object(QFileDialog, "getSaveFileName", return_value=(str(output/"nodes.csv"), "")):
            window.export_menu.save_csv("nodes")
        document = report_document(window.project, window.result, str(path))
        printer = report_printer()
        printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
        printer.setOutputFileName(str(output/"report.pdf"))
        preview = QPrintPreviewDialog(printer, window)
        preview.paintRequested.connect(document.print_)
        preview.resize(1050, 750)
        preview.show()
        capture("report-preview.png", preview)
        document.print_(printer)
        preview.close()
        assert (output/"report.pdf").stat().st_size > 1000 and (output/"nodes.csv").stat().st_size > 100
        checked("Background solve, station queries, native report preview and CSV/PDF")
        for number in (1, 2):
            print(f"Checking native official frame {number}", flush=True)
            window.example(f"3d_official_space_frame_{number}")
            assert window.project.nodes["N2"].x == (-100. if number == 1 else 120.), "Example did not load"
            wait(lambda: window.spatial_view is not None and window.spatial_view.ready, 120)
            window.analyze_action.trigger()
            wait(lambda: window.thread is None and window.result is not None)
            window.deformed_action.setChecked(True)
            window.view.diagram.setCurrentIndex(window.view.diagram.findData("torque"))
            window.view.fit()
            def javascript(source):
                values = []
                window.view.web.page().runJavaScript(source, values.append)
                wait(lambda: bool(values))
                return values[0]
            record["renderer"] = json.loads(javascript("JSON.stringify(window.pyniteViewer.diagnostics())"))
            assert record["renderer"] and not record["renderer"]["lost"]
            image = javascript("window.pyniteViewer.exportImage()")
            (output/f"official-{number}-viewport.png").write_bytes(base64.b64decode(image.split(",", 1)[1]))
            capture(f"official-{number}-desktop.png")
            with patch.object(QFileDialog, "getSaveFileName", return_value=(str(output/f"official-{number}.pynite.json"), "")):
                assert window.save_project()
            checked(f"Official space frame {number}: native WebEngine, solve, deformation, torsion and save")
        print("MCP: opening panel", flush=True)
        window.show_automation_server()
        # Ephemeral localhost binding avoids using or disrupting another app's port.
        print("MCP: starting server", flush=True)
        assert window.automation_server.start(0)
        wait(lambda: window.automation_server.state == "Running")
        print("MCP: entering mode", flush=True)
        click(window.automation_panel.mode_button)
        assert window.mcp_mode and not window.centralWidget().isEnabled()
        print("MCP: leaving mode", flush=True)
        click(window.automation_panel.mode_button)
        assert not window.mcp_mode and window.centralWidget().isEnabled()
        click(window.automation_panel.stop_button)
        wait(lambda: window.automation_server.thread is None)
        window.automation_panel.close()
        faulthandler.cancel_dump_traceback_later()
        checked("Native MCP lock/unlock handover and server shutdown on an ephemeral port")
        watchdog.stop()
        if hold:
            print("READY: native RC3 window left open for human checks; close it when finished.", flush=True)
            app.exec()
    finally:
        faulthandler.cancel_dump_traceback_later()
        trace.close()
        window.saved = window.project.to_dict()
        window.close()
        window.deleteLater()
        app.processEvents()
    print("Visible native checks complete; human/OS-dialog checks remain separate.", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--hold", action="store_true", help="Leave the verified native window open for human checks")
    args = parser.parse_args()
    main(args.output, args.hold)
