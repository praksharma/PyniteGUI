"""Opt-in checks executed by the frozen app itself, with disposable preferences."""
import asyncio
from concurrent.futures import Future
import contextlib
import io
import json
import math
from pathlib import Path
import platform
import sys
import tempfile
from threading import Thread
import time
import traceback


def run(output):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    record = {'frozen': bool(getattr(sys, 'frozen', False)), 'executable': sys.executable,
              'platform': platform.platform(), 'checks': []}
    def write():
        (output/'desktop-check.json').write_text(json.dumps(record, indent=2)+'\n')
    def passed(message):
        record['checks'].append(message)
        write()
    window = plate = None
    try:
        assert record['frozen'], 'Run this check from the built executable.'
        import pynitegui
        from PySide6.QtCore import QSettings
        from PySide6.QtWidgets import QApplication, QMessageBox
        from pynitegui.qt.app import MainWindow
        from pynitegui.qt.examples import EXAMPLES, example_project
        from pynitegui.qt.graphics import configure_graphics
        from pynitegui.qt.model import Project
        from pynitegui.qt.analysis import analyze
        from pynitegui.qt.reports import export_csv, report_html
        from pynitegui.qt.theme import configure_theme
        record.update(version=pynitegui.__version__, bundled_import=pynitegui.__file__)
        bundle = Path(sys.executable).parents[2] if sys.platform == 'darwin' else Path(sys.executable).parent
        assert Path(pynitegui.__file__).resolve().is_relative_to(bundle.resolve()), 'Application code is outside the app bundle'
        configure_graphics('auto')
        app = QApplication.instance() or QApplication(['Brecon desktop check'])
        app.setApplicationName('Brecon Desktop Check')
        app.setApplicationVersion(pynitegui.__version__)
        configure_theme(app, 'light')
        def wait(predicate, seconds=90):
            end = time.monotonic()+seconds
            while time.monotonic()<end and not predicate():
                app.processEvents()
                # Fail with a record instead of hanging in an unexpected dialog.
                modal = app.activeModalWidget()
                if isinstance(modal, QMessageBox):
                    text = modal.text()
                    modal.reject()
                    raise AssertionError(text)
                time.sleep(.01)
            assert predicate(), 'Desktop operation timed out.'
        with tempfile.TemporaryDirectory(prefix='brecon-frozen-check-') as directory:
            root = Path(directory)
            window = MainWindow(root/'recovery', QSettings(str(root/'settings.ini'), QSettings.Format.IniFormat))
            window.resize(1500, 1000)
            window.show()
            for key in EXAMPLES:
                project = example_project(key)
                path = root/(key+'.json')
                project.save(path)
                restored = Project.open(path)
                assert project.to_dict()==restored.to_dict()
                with contextlib.redirect_stdout(io.StringIO()):
                    result = analyze(restored)
                export_csv(root/(key+'.csv'), restored, result, 'nodes')
                assert '<html' in report_html(restored, result).lower()
            passed(f'{len(EXAMPLES)} examples save/open/analyze/export with bundled dependencies')
            window.load_project(example_project('3d_sliding_beam'))
            window.run_analysis()
            wait(lambda: window.thread is None)
            assert window.result is not None
            from pynitegui.qt.spatial_results import member_end_translations
            member = window.result.solver.members['M1']
            end = member_end_translations(window.result,'M1')[1]
            expected = -.001*member.L()**4/(24*member.material.E*member.section.Iz)
            assert math.isclose(float(end[1]),expected,rel_tol=1e-8)
            assert window.result.displacements['N2'][:3]==(0.,0.,0.)
            window.select(('members','M1'))
            wait(lambda: window.view.ready)
            window.view.diagram.setCurrentIndex(window.view.diagram.findData('moment_z'))
            window.deformed_action.setChecked(True)
            window.view.fit()
            preview = Future()
            window.view.web.page().runJavaScript('JSON.stringify(window.pyniteViewer.state())',preview.set_result)
            wait(preview.done)
            assert json.loads(preview.result())['objects']>5
            app.processEvents()
            scroll = window.inspector_scroll.verticalScrollBar()
            scroll.setValue(scroll.maximum())
            app.processEvents()
            assert window.grab().save(str(output/'sliding.png'))
            record['released_end_translations'] = [float(value) for value in end]
            passed('Frozen translational release worker, member-side motion, controls and diagram')
            window.load_project(example_project('3d_released_beam'))
            window.results_dock.hide()
            window.run_analysis()
            wait(lambda: window.thread is None)
            assert window.result is not None
            assert window.result.displacements['N2'][3:] == (None, None, None)
            assert not window.results_dock.isVisible()
            passed('Frozen background worker, released-member result transport and hidden All tools Results')
            wait(lambda: window.view.ready)
            window.select(('members', 'M1'))
            window.view.diagram.setCurrentIndex(window.view.diagram.findData('moment_z'))
            window.view.orientation.setCurrentIndex(1)
            window.deformed_action.setChecked(True)
            window.view.fit()
            state = Future()
            window.view.web.page().runJavaScript('JSON.stringify(window.pyniteViewer.state())', state.set_result)
            wait(state.done)
            geometry = json.loads(state.result())
            assert geometry['objects']>5
            record['viewport'] = geometry
            image = Future()
            window.view.web.page().runJavaScript('window.pyniteViewer.exportImage()', image.set_result)
            wait(image.done)
            assert image.result().startswith('data:image/png;base64,')
            import base64
            (output/'viewport.png').write_bytes(base64.b64decode(image.result().split(',',1)[1]))
            app.processEvents()
            assert window.grab().save(str(output/'app.png'))
            passed('Bundled Qt WebEngine helper, offline assets, released-beam diagram and PNG export')
            from PySide6.QtGui import QTextDocument
            from PySide6.QtPrintSupport import QPrinter
            printer = QPrinter(QPrinter.PrinterMode.HighResolution)
            printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
            printer.setOutputFileName(str(output/'results.pdf'))
            document = QTextDocument()
            document.setHtml(report_html(window.project, window.result))
            document.print_(printer)
            assert (output/'results.pdf').read_bytes().startswith(b'%PDF')
            passed('Bundled Qt print support and result PDF')
            from pynitegui.qt.plate_model import PlateDefinition
            from pynitegui.qt.plate_workspace import PlateWorkspace
            plate = PlateWorkspace(window)
            plate.install(PlateDefinition(width=60., height=60., mesh_size=20., thickness=1., pressure=1e-5).to_dict())
            plate.show()
            plate.run_analysis()
            wait(lambda: plate.thread is None)
            assert plate.result is not None
            plate.inspect_results()
            assert plate.inspector.table.rowCount()>0
            plate.canvas.draw()
            plate.figure.savefig(output/'plate.png')
            passed('Frozen plate worker, local recovery, Matplotlib Qt canvas and PNG export')
            plate.saved = plate.definition.to_dict()
            plate.close()
            plate = None
            check_mcp(window, wait)
            passed('Bundled authenticated MCP discovery, schema, atomic edit, background solve and result read')
            window.saved = window.project.to_dict()
            window.close()
            window = None
        record['ok'] = True
        write()
    except BaseException:
        record.update(ok=False, error=traceback.format_exc())
        write()
        if plate is not None:
            if plate.thread is not None:
                plate.worker.cancel()
                wait(lambda: plate.thread is None)
            plate.saved = plate.definition.to_dict()
            plate.close()
        if window is not None:
            if window.thread is not None:
                window.cancel_analysis()
                wait(lambda: window.thread is None)
            window.saved = window.project.to_dict()
            window.close()
        raise


def check_mcp(window, wait):
    from pynitegui.qt.automation_server import AutomationServer
    server = AutomationServer(window)
    window.automation_server = server
    server.permissions.set_group('Model edits', True)
    server.permissions.set_group('Analysis', True)
    try:
        assert server.start(0), server.detail
        wait(lambda: server.state!='Starting')
        assert server.state=='Running', server.detail
        window.automation_mode.set_enabled(True)
        future = Future()
        async def check():
            import httpx2
            from mcp import ClientSession
            from mcp.client.streamable_http import streamable_http_client
            async with httpx2.AsyncClient(headers={'Authorization':'Bearer '+server.token}, trust_env=False) as http:
                async with streamable_http_client(server.endpoint, http_client=http) as (read, write):
                    async with ClientSession(read, write, read_timeout_seconds=30) as client:
                        await client.initialize()
                        model = (await client.call_tool('read_model', {})).structured_content['data']
                        assert model['schema']['entities']['members']
                        identity = {'session_id':model['session_id']}
                        edited = await client.call_tool('apply_batch', {**identity, 'expected_revision':model['revision'],
                            'operations':[{'op':'set', 'collection':'settings', 'value':{'grid':6.}}]})
                        assert not edited.is_error, edited
                        revision = edited.structured_content['data']['revision']
                        started = await client.call_tool('run_analysis', {**identity,'expected_revision':revision})
                        assert not started.is_error, started
                        end = time.monotonic()+60
                        while time.monotonic()<end:
                            status = (await client.call_tool('analysis_status', identity)).structured_content['data']
                            if not status['running']:
                                break
                            await asyncio.sleep(.05)
                        assert status['state']=='Current', status
                        result = await client.call_tool('read_results', {**identity,'kind':'nodes'})
                        assert not result.is_error, result
                        assert result.structured_content['data']['inactive_rotation_directions']['N2']
        def background():
            try:
                future.set_result(asyncio.run(check()))
            except BaseException as error:
                future.set_exception(error)
        thread = Thread(target=background, daemon=True)
        thread.start()
        wait(future.done)
        thread.join(timeout=3)
        future.result()
    finally:
        server.stop()
        wait(lambda: server.thread is None)
