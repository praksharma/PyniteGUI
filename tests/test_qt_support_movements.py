"""Staged support motion editing, unit conversion and real worker snapshots."""
from threading import Event
import unittest
from unittest.mock import patch

import numpy as np
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication, QCheckBox, QComboBox, QDoubleSpinBox, QPushButton, QMessageBox
from pynitegui.qt.app import MainWindow
from pynitegui.qt.analysis_jobs import execute_analysis
from pynitegui.qt.automation_core import AutomationCommands
from pynitegui.qt.automation_schema import model_reference, batch_examples
from pynitegui.qt.examples import example_project
from pynitegui.qt.model_tables import ModelTablesDialog
from pynitegui.qt.reports import model_definition_tables
from pynitegui.qt.spatial_conversion import to_spatial
from pynitegui.qt.spatial_view import viewport_payload
from pynitegui.qt.annotations import support_label
from pynitegui.qt.geometry_tools import plan_transform, support_state


class SupportMovementEditorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])

    def setUp(self):
        self.window=MainWindow();self.window.load_project(example_project('support_settlement'))

    def tearDown(self):
        self.window.saved=self.window.project.to_dict();self.window.close();self.window.deleteLater();self.app.processEvents()

    def apply_button(self):
        return next(b for b in self.window.inspector.findChildren(QPushButton) if b.text()=='Apply')

    def test_staged_precision_undo_and_presets_clear_inapplicable_motion(self):
        w=self.window
        for spatial in (False,True):
            p=example_project('support_settlement');p.nodes['N2'].settlement_y=-.123456789123
            if spatial:p=to_spatial(p)
            w.load_project(p);w.set_units('si_mm');before=w.project.to_dict();w.select(('nodes','N2'))
            self.apply_button().click();self.assertEqual(w.project.to_dict(),before)
            w.inspector.findChild(QDoubleSpinBox,'settlement_y').setValue(-5.08)
            w.inspector.findChild(QDoubleSpinBox,'settlement_rz').setValue(.002)
            self.assertEqual(w.project.to_dict(),before)
            self.apply_button().click()
            self.assertAlmostEqual(w.project.nodes['N2'].settlement_y,-.2)
            self.assertEqual(w.project.nodes['N2'].settlement_rz,.002)
            w.undo.undo();self.assertEqual(w.project.to_dict(),before)
            w.select(('nodes','N2'))
            support=(w.inspector.findChild(QComboBox,'spatial_support') if spatial else next(c for c in w.inspector.findChildren(QComboBox) if c.findText('fixed')>=0))
            support.setCurrentText('free');self.apply_button().click()
            self.assertEqual(w.project.nodes['N2'].settlement_y,0.)
            self.assertEqual(w.project.nodes['N2'].settlement_rz,0.)
            w.undo.undo();self.assertEqual(w.project.to_dict(),before)

    def test_tables_bulk_atomic_invalid_edit_and_one_undo(self):
        w=self.window
        for spatial in (False,True):
            p=example_project('support_settlement')
            if spatial:p=to_spatial(p)
            w.load_project(p)
            dialog=ModelTablesDialog(w,p);self.addCleanup(dialog.deleteLater)
            table=dialog.tables['nodes'];fields=dialog.fields['nodes']
            table.item(1,fields.index('settlement_y')).setText('-.2')
            self.assertEqual(dialog.preview().nodes['N2'].settlement_y,-.2)
            self.assertEqual(w.project.nodes['N2'].settlement_y,-.1)
            table.cellWidget(1,fields.index('support')).setCurrentText('free')
            self.assertEqual(dialog.preview().nodes['N2'].settlement_y,0.)
            # New rows must not run support updates against half-built cells.
            dialog.add_row('nodes');self.assertEqual(table.rowCount(),3)
            w.select_many([('nodes','N1'),('nodes','N2')])
            w.inspector.findChild(QCheckBox,'bulk_change_settlement_y').setChecked(True)
            w.inspector.findChild(QDoubleSpinBox,'bulk_settlement_y').setValue(-.3)
            w.inspector.findChild(QPushButton,'bulk_apply').click()
            self.assertTrue(all(n.settlement_y==-.3 for n in w.project.nodes.values()))
            self.assertEqual(w.undo.count(),1);w.undo.undo()
            self.assertEqual(w.project.nodes['N1'].settlement_y,0.)
            w.select_many([('nodes','N1'),('nodes','N2')])
            w.inspector.findChild(QCheckBox,'bulk_change_settlement_normal').setChecked(True)
            w.inspector.findChild(QDoubleSpinBox,'bulk_settlement_normal').setValue(-.1)
            before=w.project.to_dict()
            with patch.object(QMessageBox,'warning') as warning:w.inspector.findChild(QPushButton,'bulk_apply').click()
            warning.assert_called_once();self.assertEqual(w.project.to_dict(),before)

    def test_actual_worker_example_reactions_units_metadata_reports_and_invalidation(self):
        w=self.window;r=execute_analysis(w.project,lambda phase:None,Event());w.analysis_revision=w.revision;w.analysis_finished(r,'')
        settled=r.for_combination('Settlement only')
        np.testing.assert_allclose(settled.reactions['N1'],(0.,16.4333333333333,862.75),atol=1e-8)
        np.testing.assert_allclose(settled.reactions['N2'],(0.,-16.4333333333333,1109.25),atol=1e-8)
        self.assertIn('Imposed motion (all combinations)',str(model_definition_tables(w.project)))
        self.assertIn('all combinations',support_label(w.project,w.project.nodes['N2']))
        snapshot=w.result.snapshot_id;w.set_units('si');self.assertEqual(w.result.snapshot_id,snapshot)
        response=AutomationCommands(w).execute('read_results',dict(session_id=w.project_session,kind='nodes',offset=1,limit=1,combination='Settlement only'))
        self.assertEqual(set(response['imposed_support_movements']),{'N2'})
        row=response['imposed_support_movements']['N2'];self.assertAlmostEqual(row['settlement_y']['value'],-.00254)
        self.assertEqual(row['settlement_y']['unit'],'m');self.assertEqual(row['settlement_rz'],{'value':.001,'unit':'rad'})
        w.edit('Change settlement',lambda p:setattr(p.nodes['N2'],'settlement_y',-.2));self.assertIsNone(w.result)

    def test_spatial_preview_support_copy_and_discoverable_schema(self):
        w=self.window;p=to_spatial(w.project);w.load_project(p);payload=viewport_payload(w)
        node=next(n for n in payload['nodes'] if n['name']=='N2')
        self.assertIn('imposed -0.1 in in every combination',node['supportDetails'][1]['state'])
        self.assertIn('imposed 0.001 rad',node['supportDetails'][5]['state'])
        for dimension in ('2D','3D'):
            fields=model_reference(dimension)['entities']['nodes']['properties']
            self.assertIn('every combination',fields['settlement_y']['description'])
            self.assertEqual(fields['settlement_y']['default'],0.)
        copy=plan_transform(p,[('members','M1')],'repeat',offset=(0.,240.,0.),copy_supports=True).definition
        self.assertEqual(sum(n.settlement_y==-.1 and n.settlement_rz==.001 for n in copy.nodes.values()),2)
        original=support_state(p.nodes['N2']);p.nodes['N2'].settlement_y=-.2
        self.assertNotEqual(support_state(p.nodes['N2']),original)

    def test_pdelta_method_native_edit_worker_units_and_result_invalidation(self):
        w = self.window
        p = example_project('p_delta_support_motion')
        p.analysis_method = 'linear'
        w.load_project(p)
        before = w.project.to_dict()
        def choose():
            dialog = self.app.activeModalWidget()
            dialog.method.setCurrentIndex(dialog.method.findData('p_delta'))
            dialog.accept()
        QTimer.singleShot(0, choose)
        w.manage_analysis_method()
        self.assertEqual(w.project.analysis_method, 'p_delta')
        w.undo.undo()
        self.assertEqual(w.project.to_dict(), before)
        w.undo.redo()
        result = execute_analysis(w.project, lambda phase: None, Event())
        w.analysis_revision = w.revision
        w.analysis_finished(result, '')
        self.assertEqual(w.result.analysis_method, 'p_delta')
        tip = w.project.node_at(0., 480.)
        self.assertAlmostEqual(result.for_combination('Base motion only').displacements[tip][0], .03-.0007*480., places=10)
        snapshot = w.result.snapshot_id
        w.set_units('si_mm')
        self.assertEqual(w.result.snapshot_id, snapshot)
        response = AutomationCommands(w).execute('read_results', dict(session_id=w.project_session,
            kind='nodes', offset=0, limit=1, combination='Base motion only'))
        self.assertEqual(response['analysis_method'], 'p_delta')
        self.assertEqual(response['imposed_support_movements']['N1']['settlement_rz'], {'value': .0007, 'unit': 'rad'})
        self.assertAlmostEqual(response['imposed_support_movements']['N1']['settlement_x']['value'], .762)
        self.assertIn('force balance only', w.results_panel.equilibrium_summary.text())
        w.select(('nodes', 'N1'))
        w.inspector.findChild(QDoubleSpinBox, 'settlement_x').setValue(1.27)
        self.apply_button().click()
        self.assertAlmostEqual(w.project.nodes['N1'].settlement_x, .05)
        self.assertIsNone(w.result)
        w.undo.undo()
        self.assertAlmostEqual(w.project.nodes['N1'].settlement_x, .03)
