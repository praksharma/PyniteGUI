"""Native staged links, workers, tables, geometry and unit-labelled exports."""
from dataclasses import replace
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
from PySide6.QtWidgets import QApplication,QDialog,QFileDialog
from pynitegui.qt.app import MainWindow
from pynitegui.qt.examples import example_project
from pynitegui.qt.joint_spring_editor import JointSpringEditor,JointSpringsDialog
from pynitegui.qt.reports import export_csv,report_html
from pynitegui.qt.spatial_view import viewport_payload


class JointSpringEditorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])

    def setUp(self):self.window=MainWindow()

    def wait(self,predicate):
        deadline=time.monotonic()+20
        while not predicate() and time.monotonic()<deadline:self.app.processEvents();time.sleep(.005)
        self.assertTrue(predicate(),'Joint spring worker timed out')

    def tearDown(self):
        w=self.window
        if w.thread is not None:w.cancel_analysis();self.wait(lambda:w.thread is None)
        w.saved=w.project.to_dict();w.close();w.deleteLater();self.app.processEvents()

    def test_staged_editor_exact_units_cancel_apply_undo_and_native_mode_guard(self):
        w=self.window
        for units in ('imperial','imperial_ft','si','si_mm','custom_cm_kN'):
            p=example_project('joint_spring_series',units);w.load_project(p);before=w.project.to_dict()
            editor=JointSpringEditor(w,p,p.joint_springs['S1'],'S1');editor.accept()
            self.assertEqual(editor.definition,p.joint_springs['S1']);editor.deleteLater()
            dialog=JointSpringsDialog(w,w.project);dialog.project.joint_springs['S1'].stiffness=150.
            with patch('pynitegui.qt.joint_spring_editor.JointSpringsDialog',return_value=dialog),patch.object(dialog,'exec',return_value=QDialog.DialogCode.Rejected):w.manage_joint_springs()
            self.assertEqual(w.project.to_dict(),before)
            dialog=JointSpringsDialog(w,w.project);dialog.project.joint_springs['S1'].stiffness=150.
            with patch('pynitegui.qt.joint_spring_editor.JointSpringsDialog',return_value=dialog),patch.object(dialog,'exec',return_value=QDialog.DialogCode.Accepted):w.manage_joint_springs()
            self.assertEqual(w.project.joint_springs['S1'].stiffness,150.);self.assertEqual(w.undo.count(),1)
            w.undo.undo();self.assertEqual(w.project.to_dict(),before)
            w.mcp_mode=True
            with patch('pynitegui.qt.joint_spring_editor.JointSpringsDialog') as opened:w.manage_joint_springs();opened.assert_not_called()
            w.mcp_mode=False

    def test_actual_workers_native_tables_csv_definitions_and_spatial_payload(self):
        w=self.window
        for key in ('joint_spring_series','joint_spring_one_way','3d_joint_spring_network'):
            w.load_project(example_project(key));self.assertTrue(w.analyze_action.isEnabled())
            w.run_analysis();self.wait(lambda:w.thread is None)
            self.assertIsNotNone(w.result,w.analysis_error)
            self.assertEqual(w.results_panel.joint_table.rowCount(),len(w.project.joint_springs))
            self.assertTrue(w.results_panel.tabs.isTabVisible(w.results_panel.joint_tab))
            if key=='joint_spring_one_way':
                w.result_combination.setCurrentText('Reverse')
                self.assertLess(w.result.displacements['B'][0],0.)
            if key.startswith('3d_'):
                payload=viewport_payload(w);self.assertEqual(len(payload['jointSprings']),3)
                self.assertTrue(all(len(s['points'])>10 for s in payload['jointSprings']))
            self.assertIn('Joint Springs',report_html(w.project,w.result))
            with tempfile.TemporaryDirectory() as directory:
                path=Path(directory)/'links.csv';export_csv(path,w.project,w.result,'joint_springs')
                self.assertIn('Axial force, tension +',path.read_text());self.assertIn(w.result.snapshot_id,path.read_text())
            snapshot=w.result.snapshot_id;w.set_units('si_mm');self.assertEqual(w.result.snapshot_id,snapshot)
            self.assertIn('Axial stiffness (N/mm)',[w.results_panel.joint_table.horizontalHeaderItem(i).text() for i in range(w.results_panel.joint_table.columnCount())])
            w.edit('Delete joint',lambda p:p.delete('nodes',next(iter(p.nodes))))
            self.assertIsNone(w.result);self.assertEqual(w.results_panel.joint_table.rowCount(),0)
            w.undo.undo();self.assertTrue(w.project.joint_springs)

    def test_invalid_self_link_does_not_change_model_and_mcp_merge_fields_are_typed(self):
        from pynitegui.qt.automation_core import batch_candidate,AutomationError
        w=self.window;w.load_project(example_project('joint_spring_series'));before=w.project.to_dict()
        editor=JointSpringEditor(w,w.project,w.project.joint_springs['S1'],'S1');editor.end.setCurrentText(editor.start.currentText())
        with patch('pynitegui.qt.joint_spring_editor.QMessageBox.warning') as warning:editor.accept()
        warning.assert_called_once();self.assertIsNone(editor.definition);self.assertEqual(w.project.to_dict(),before);editor.deleteLater()
        q=batch_candidate(w.project,[{'op':'put','collection':'joint_springs','key':'S1','value':{'stiffness':250.}}])
        self.assertEqual(q.joint_springs['S1'].stiffness,250.)
        with self.assertRaises(AutomationError):batch_candidate(w.project,[{'op':'put','collection':'joint_springs','key':'S1','value':{'stiffness':True}}])
