"""Native unilateral editing, worker, snapshot result and MCP contracts."""
from threading import Event
import unittest
from unittest.mock import patch

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication,QCheckBox,QComboBox,QDoubleSpinBox,QPushButton,QMessageBox
from pynitegui.qt.app import MainWindow
from pynitegui.qt.analysis_jobs import execute_analysis
from pynitegui.qt.automation_core import AutomationCommands
from pynitegui.qt.automation_schema import model_reference
from pynitegui.qt.examples import example_project
from pynitegui.qt.model_tables import ModelTablesDialog
from pynitegui.qt.reports import model_definition_tables,result_table,report_html,ReportOptions
from pynitegui.qt.spatial_conversion import to_spatial
from pynitegui.qt.spatial_view import viewport_payload


class IterativeEditorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])

    def setUp(self):
        self.window=MainWindow();self.window.load_project(example_project('official_foundation'))

    def tearDown(self):
        w=self.window;w.saved=w.project.to_dict();w.close();w.deleteLater();self.app.processEvents()

    def apply(self):
        next(b for b in self.window.inspector.findChildren(QPushButton) if b.text()=='Apply').click()

    def test_staged_node_action_zero_stiffness_reset_and_undo_in_both_dimensions(self):
        w=self.window
        for spatial in (False,True):
            p=example_project('official_foundation')
            if spatial:p=to_spatial(p)
            w.load_project(p);w.set_units('si_mm');w.select(('nodes','N2'));before=w.project.to_dict()
            self.apply();self.assertEqual(w.project.to_dict(),before)
            box=w.inspector.findChild(QComboBox,'spring_y_mode')
            box.setCurrentIndex(box.findData('positive'))
            self.assertEqual(w.project.to_dict(),before)
            self.apply();self.assertEqual(w.project.nodes['N2'].spring_y_mode,'positive')
            w.undo.undo();self.assertEqual(w.project.to_dict(),before)
            w.select(('nodes','N2'));w.inspector.findChild(QDoubleSpinBox,'spring_y').setValue(0.)
            self.apply();self.assertEqual(w.project.nodes['N2'].spring_y_mode,'bilateral')
            w.undo.undo();self.assertEqual(w.project.to_dict(),before)

    def test_tables_bulk_behaviour_settings_and_reject_invalid_frame_flag(self):
        w=self.window;p=example_project('official_tension_braced');w.load_project(p)
        w.select(('members','Brace1'));before=w.project.to_dict();self.apply();self.assertEqual(w.project.to_dict(),before)
        box=w.inspector.findChild(QComboBox,'member_behavior');box.setCurrentIndex(box.findData('compression_only'))
        self.apply();self.assertEqual(w.project.members['Brace1'].behavior,'compression_only');w.undo.undo()
        dialog=ModelTablesDialog(w,w.project);self.addCleanup(dialog.deleteLater)
        table=dialog.tables['members'];fields=dialog.fields['members'];row=list(p.members).index('Brace1')
        table.cellWidget(row,fields.index('behavior')).setCurrentIndex(0)
        self.assertEqual(dialog.preview().members['Brace1'].behavior,'bilateral')
        self.assertEqual(w.project.members['Brace1'].behavior,'tension_only')
        w.select_many([('members','Brace1'),('members','Brace2')])
        choice=w.inspector.findChild(QComboBox,'bulk_behavior');choice.setCurrentIndex(choice.findData('compression_only'))
        w.inspector.findChild(QPushButton,'bulk_apply').click()
        self.assertTrue(all(w.project.members[key].behavior=='compression_only' for key in ('Brace1','Brace2')))
        w.undo.undo();self.assertEqual(w.project.to_dict(),before)
        def choose():
            d=self.app.activeModalWidget();d.iterative_fields['load_steps'].setValue(3);d.accept()
        QTimer.singleShot(0,choose);w.manage_analysis_method();self.assertEqual(w.project.load_steps,3)
        w.undo.undo();self.assertEqual(w.project.to_dict(),before)
        for dimension in ('2D','3D'):
            schema=model_reference(dimension)
            self.assertIn('negative',schema['entities']['nodes']['properties']['spring_y_mode']['enum'])
            self.assertIn('tension_only',schema['entities']['members']['properties']['behavior']['enum'])

    def test_worker_pagination_history_units_reports_and_spatial_hover(self):
        w=self.window;w.load_project(example_project('official_tension_braced'))
        r=execute_analysis(w.project,lambda phase:None,Event());w.analysis_revision=w.revision;w.analysis_finished(r,'')
        panel=w.results_panel
        self.assertEqual(panel.active_states.rowCount(),2)
        self.assertTrue(panel.tabs.isTabVisible(panel.iteration_tab))
        self.assertGreater(panel.iterations.rowCount(),1)
        self.assertIn('Tension only',str(model_definition_tables(w.project)))
        self.assertIn('Unilateral',report_html(w.project,r,options=ReportOptions()))
        command=AutomationCommands(w)
        arguments=dict(session_id=w.project_session,combination='1.2D+1.0W',offset=1,limit=1)
        data=command.execute('read_results',dict(arguments,kind='active_states'))
        self.assertEqual(data['total_rows'],2);self.assertEqual(data['rows'][0][4],'No')
        self.assertNotIn('history',data['iteration_summary'])
        history=command.execute('read_results',dict(arguments,kind='iterations'))
        self.assertEqual(len(history['rows']),1);self.assertGreater(history['total_rows'],1)
        snapshot=r.snapshot_id;w.set_units('si_mm');self.assertEqual(w.result.snapshot_id,snapshot)
        data=command.execute('read_results',dict(arguments,kind='active_states'))
        self.assertEqual(data['rows'][0][-1],'N')
        # A spatial foundation can retain the ground action in hover details.
        p=to_spatial(example_project('official_foundation'));w.load_project(p)
        r=execute_analysis(p,lambda phase:None,Event());w.analysis_revision=w.revision;w.analysis_finished(r,'')
        node=next(n for n in viewport_payload(w)['nodes'] if n['name']=='N2')
        self.assertIn('Negative displacement only',node['supportDetails'][1]['state'])
        self.assertIn('; active',node['supportDetails'][1]['state'])
