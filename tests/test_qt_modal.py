"""Native modal jobs, snapshots, unit-labelled exports and cancellation."""
import contextlib
import io
import json
from pathlib import Path
import tempfile
from threading import Event
import time
import unittest
from unittest.mock import patch

from PySide6.QtWidgets import QApplication,QFileDialog
from pynitegui.qt.app import MainWindow
from pynitegui.qt.analysis import analyze
from pynitegui.qt.automation_core import AutomationCommands,AutomationError
from pynitegui.qt.examples import example_project
from pynitegui.qt.modal import ModalSettings
from pynitegui.qt.modal_jobs import controller
from pynitegui.qt.spatial_conversion import to_spatial


def slow_modal_child(connection,request):
    connection.send(('progress','Modal cancellation test'))
    Event().wait(60)


class ModalEditorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])

    def setUp(self):
        self.window=MainWindow();self.window.load_project(example_project('official_modal'))
        self.modal=controller(self.window)

    def wait(self,predicate,seconds=20):
        deadline=time.monotonic()+seconds
        while not predicate() and time.monotonic()<deadline:self.app.processEvents();time.sleep(.005)
        self.assertTrue(predicate(),'Modal job timed out')

    def tearDown(self):
        w=self.window
        if w.thread is not None:w.cancel_analysis();self.wait(lambda:w.thread is None)
        if self.modal.panel is not None:self.modal.panel.close()
        w.saved=w.project.to_dict();w.close();w.deleteLater();self.app.processEvents()

    def test_official_native_route_worker_static_snapshot_preservation_and_exports(self):
        w=self.window;before=w.project.to_dict()
        with contextlib.redirect_stdout(io.StringIO()):static=analyze(w.project)
        w.analysis_revision=w.revision;w.analysis_finished(static,'')
        with patch.object(w,'confirm_discard',return_value=True):w.example('official_modal')
        panel=self.modal.panel
        self.assertIsNotNone(panel);self.assertAlmostEqual(panel.gravity.value(),386.4)
        self.assertIsNone(w.result)
        panel.solve.click();self.wait(lambda:w.thread is None)
        self.assertEqual(self.modal.status()['state'],'Current',self.modal.error)
        self.assertEqual(w.project.to_dict(),before);self.assertIsNone(w.result)
        self.assertEqual(panel.tables['frequencies'].rowCount(),3)
        self.assertEqual(panel.tables['shapes'].rowCount(),4)
        panel.mode.setCurrentIndex(2);panel.canvas.draw();self.assertIn('Mode 3',panel.figure.axes[0].get_title())
        r=self.modal.result
        with tempfile.TemporaryDirectory() as directory:
            csv=Path(directory)/'modes.csv';snapshot=Path(directory)/'modes.json';plot=Path(directory)/'mode.svg'
            with patch.object(QFileDialog,'getSaveFileName',return_value=(str(csv),'CSV')):panel.export_csv()
            self.assertIn(r.snapshot_id,csv.read_text());self.assertIn('Frequency (Hz)',csv.read_text())
            with patch.object(QFileDialog,'getSaveFileName',return_value=(str(snapshot),'JSON')):panel.export_json()
            data=json.loads(snapshot.read_text());self.assertEqual(data['settings']['gravity'],386.4)
            self.assertEqual(data['project'],before)
            with patch('pynitegui.qt.plot_export.QFileDialog.getSaveFileName',return_value=(str(plot),'SVG vector image (*.svg)')):panel.toolbar.save_figure()
            self.assertIn(r.configuration_signature,plot.read_text());self.assertIn(r.snapshot_id,plot.read_text())
        # A later static solve has its own identity and never replaces modes.
        w.run_analysis();self.wait(lambda:w.thread is None)
        self.assertEqual(w.analysis_kind,'static');self.assertIsNotNone(w.result);self.assertIs(self.modal.result,r)

    def test_mcp_result_units_pagination_and_stale_model_rejection(self):
        w=self.window;commands=AutomationCommands(w)
        self.modal.start(ModalSettings('Mass',3,gravity=386.4));self.wait(lambda:w.thread is None)
        snapshot=self.modal.result.snapshot_id
        args=dict(session_id=w.project_session,snapshot_id=snapshot,offset=1,limit=1)
        frequencies=commands.execute('read_modal_results',args)
        self.assertEqual(frequencies['total_rows'],3);self.assertEqual(frequencies['rows'][0][0],2)
        shapes=commands.execute('read_modal_results',{**args,'kind':'shapes','mode':2})
        rz=shapes['rows'][0][-1]
        w.set_units('si_mm');self.assertEqual(self.modal.status()['state'],'Current')
        converted=commands.execute('read_modal_results',{**args,'kind':'shapes','mode':2})
        self.assertEqual(converted['snapshot_id'],snapshot)
        self.assertIn('RZ (rad/mm)',converted['headers']);self.assertAlmostEqual(converted['rows'][0][-1],rz/25.4)
        before=w.project.to_dict();w.edit('Change stiffness',lambda p:setattr(p.materials['Steel'],'E',20000.))
        self.assertEqual(self.modal.status()['state'],'Outdated')
        with self.assertRaisesRegex(AutomationError,'current model'):commands.execute('read_modal_results',args)
        self.assertEqual(self.modal.result.project.materials['Steel'].E,29000.)

    def test_worker_edit_during_solve_cannot_accept_outdated_modes_and_cancel_is_shared(self):
        w=self.window
        with patch('pynitegui.qt.modal_jobs.modal_child',slow_modal_child):
            self.modal.start(ModalSettings('Mass',3));self.wait(lambda:'cancellation test' in self.modal.phase)
            with self.assertRaisesRegex(ValueError,'already running'):self.modal.start(ModalSettings('Mass',3))
            w.edit('Change model',lambda p:setattr(p.materials['Steel'],'E',20000.))
            w.cancel_analysis();self.wait(lambda:w.thread is None)
        self.assertEqual(self.modal.state,'Cancelled');self.assertIsNone(self.modal.result)
        self.assertTrue(w.analyze_action.isEnabled())
        self.modal.start(ModalSettings('Mass',3))
        w.edit('Change model during solve',lambda p:setattr(p.materials['Steel'],'E',21000.))
        self.wait(lambda:w.thread is None)
        self.assertEqual(self.modal.state,'Outdated');self.assertIsNone(self.modal.result)
        # The native renderer must handle actual spatial modes as well.
        w.load_project(to_spatial(example_project('official_modal')))
        self.modal.show();self.modal.start(ModalSettings('Mass',3));self.wait(lambda:w.thread is None)
        self.assertEqual(self.modal.state,'Current',self.modal.error)
        self.modal.panel.canvas.draw();self.assertEqual(self.modal.panel.figure.axes[0].name,'3d')

    def test_live_edits_do_not_misclassify_a_modal_job_as_previous_automatic_solve(self):
        w=self.window
        w.analysis_automatic=True  # Previous automatic solve's bookkeeping.
        w.live_analysis.enabled=True
        with patch('pynitegui.qt.modal_jobs.modal_child',slow_modal_child):
            self.modal.start(ModalSettings('Mass',3));self.wait(lambda:'cancellation test' in self.modal.phase)
            self.assertFalse(w.analysis_automatic)
            w.edit('Edit during manual modal job',lambda p:setattr(p.materials['Steel'],'E',21000.))
            self.assertTrue(w.live_analysis.pending)
            self.assertFalse(w.worker.cancelled.is_set())
            w.cancel_analysis();self.wait(lambda:w.thread is None)
        self.assertFalse(w.live_analysis.pending)
        w.live_analysis.enabled=False
