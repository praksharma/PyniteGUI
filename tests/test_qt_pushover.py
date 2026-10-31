"""Native accepted histories, exports, model identity and shared cancellation."""
import json
from pathlib import Path
import tempfile
from threading import Event
import time
import unittest
from unittest.mock import patch
from PySide6.QtWidgets import QApplication,QFileDialog
from pynitegui.qt.app import MainWindow
from pynitegui.qt.automation_core import AutomationCommands,AutomationError
from pynitegui.qt.examples import example_project
from pynitegui.qt.pushover_jobs import controller
from pynitegui.qt.steel_examples import example_settings


def slow_pushover_child(connection,request):
    connection.send(('progress','Pushover cancellation test'));Event().wait(60)


class PushoverEditorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])

    def setUp(self):
        self.window=MainWindow();self.window.load_project(example_project('steel_redistribution'));self.job=controller(self.window)

    def wait(self,predicate,seconds=30):
        deadline=time.monotonic()+seconds
        while not predicate() and time.monotonic()<deadline:self.app.processEvents();time.sleep(.005)
        self.assertTrue(predicate(),'Pushover job timed out')

    def tearDown(self):
        w=self.window
        if w.thread is not None:w.cancel_analysis();self.wait(lambda:w.thread is None)
        if self.job.panel is not None:self.job.panel.close()
        w.saved=w.project.to_dict();w.close();w.deleteLater();self.app.processEvents()

    def test_native_example_worker_step_tables_and_exports_keep_static_snapshot(self):
        w=self.window
        with patch.object(w,'confirm_discard',return_value=True):w.example('steel_redistribution')
        panel=self.job.panel;before=w.project.to_dict()
        w.run_analysis();self.wait(lambda:w.thread is None);static=w.result
        panel.solve.click();self.wait(lambda:w.thread is None)
        self.assertEqual(self.job.status()['state'],'Current',self.job.error)
        self.assertIs(w.result,static);self.assertEqual(w.project.to_dict(),before)
        self.assertEqual(panel.tables['capacity'].rowCount(),501);self.assertEqual(panel.tables['member_ends'].rowCount(),4)
        self.assertLess(float(panel.tables['displacements'].item(1,2).text()),-1.14)
        panel.step.setCurrentIndex(0);self.assertEqual(float(panel.tables['displacements'].item(1,2).text()),0.)
        panel.step.setCurrentIndex(500);panel.magnitudes.setChecked(True);panel.canvas.draw()
        self.assertIn('magnitudes',panel.figure.axes[0].get_title())
        with tempfile.TemporaryDirectory() as directory:
            csv=Path(directory)/'steel.csv';snapshot=Path(directory)/'steel.json';plot=Path(directory)/'steel.svg'
            with patch.object(QFileDialog,'getSaveFileName',return_value=(str(csv),'CSV')):panel.export_csv()
            self.assertIn(self.job.result.snapshot_id,csv.read_text());self.assertIn('Push factor',csv.read_text())
            with patch.object(QFileDialog,'getSaveFileName',return_value=(str(snapshot),'JSON')):panel.export_json()
            data=json.loads(snapshot.read_text());self.assertEqual(data['project'],before);self.assertTrue(data['complete'])
            self.assertEqual(len(data['curve']),501);self.assertLess(data['curve'][-1][0],0.)
            with patch('pynitegui.qt.plot_export.QFileDialog.getSaveFileName',return_value=(str(plot),'SVG vector image (*.svg)')):panel.toolbar.save_figure()
            self.assertIn(self.job.result.configuration_signature,plot.read_text())

    def test_partial_prefix_mcp_units_pagination_and_revision_rejection(self):
        from dataclasses import replace
        w=self.window;commands=AutomationCommands(w)
        self.job.start(replace(example_settings('steel_redistribution'),steps=20));self.wait(lambda:w.thread is None)
        self.assertEqual(self.job.status()['state'],'Partial');self.assertEqual(self.job.result.termination,'yield_overshoot')
        args=dict(session_id=w.project_session,kind='capacity',offset=1,limit=1)
        data=commands.execute('read_pushover_results',args)
        self.assertFalse(data['complete']);self.assertEqual(data['rows'][0][0],1);self.assertLess(data['accepted_factor'],1.)
        displacement=data['rows'][0][2];w.set_units('si_mm')
        converted=commands.execute('read_pushover_results',args)
        self.assertIn('N2 DY (mm)',converted['headers']);self.assertAlmostEqual(converted['rows'][0][2],25.4*displacement)
        with self.assertRaisesRegex(AutomationError,'snapshot changed'):commands.execute('read_pushover_results',{**args,'snapshot_id':'old'})
        with self.assertRaisesRegex(ValueError,'recorded accepted step'):commands.execute('read_pushover_results',{**args,'step':999})
        w.edit('Change stiffness',lambda p:setattr(p.materials['Steel'],'E',21000.))
        self.assertEqual(self.job.status()['state'],'Outdated')
        with self.assertRaisesRegex(AutomationError,'current model'):commands.execute('read_pushover_results',args)
        self.assertEqual(self.job.result.project.materials['Steel'].E,29000.)

    def test_cancel_edit_during_job_and_live_bookkeeping(self):
        w=self.window;w.analysis_automatic=True;w.live_analysis.enabled=True
        with patch('pynitegui.qt.pushover_jobs.pushover_child',slow_pushover_child):
            self.job.start(example_settings('steel_redistribution'));self.wait(lambda:'cancellation test' in self.job.phase)
            self.assertFalse(w.analysis_automatic)
            with self.assertRaisesRegex(ValueError,'already running'):self.job.start(example_settings('steel_redistribution'))
            w.edit('Edit during pushover',lambda p:setattr(p.materials['Steel'],'E',21000.))
            self.assertFalse(w.worker.cancelled.is_set());self.assertTrue(w.live_analysis.pending)
            w.cancel_analysis();self.wait(lambda:w.thread is None)
        self.assertEqual(self.job.state,'Cancelled');self.assertIsNone(self.job.result);self.assertFalse(w.live_analysis.pending)
        w.live_analysis.enabled=False
        self.job.start(example_settings('steel_redistribution'));w.edit('Edit again',lambda p:setattr(p.materials['Steel'],'E',22000.))
        self.wait(lambda:w.thread is None);self.assertEqual(self.job.state,'Outdated');self.assertIsNone(self.job.result)

    def test_spatial_hinge_map_and_rotation_limit_units(self):
        w=self.window;w.load_project(example_project('3d_steel_weak_axis','si_mm'));self.job.show();panel=self.job.panel
        s=example_settings('3d_steel_weak_axis');panel.set_inputs(s);self.assertAlmostEqual(panel.limit.value(),76.2)
        self.job.start(s);self.wait(lambda:w.thread is None)
        self.assertEqual(self.job.state,'Current',self.job.error);panel.canvas.draw();self.assertEqual(panel.figure.axes[1].name,'3d')
        panel.direction.setCurrentText('RZ');self.assertIn('rad',panel.limit_label.text())
        panel.set_inputs(s);self.assertAlmostEqual(panel.limit.value(),76.2)
