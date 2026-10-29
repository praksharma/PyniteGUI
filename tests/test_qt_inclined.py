"""Native inclined-roller edits, snapshots, metadata and worker transport."""
from threading import Event
import unittest
from unittest.mock import patch

import numpy as np
from PySide6.QtWidgets import QApplication, QComboBox, QDoubleSpinBox, QCheckBox, QPushButton, QMessageBox, QLabel
from PySide6.QtCore import Qt

from pynitegui.qt.app import MainWindow, EngineeringSymbol
from pynitegui.qt.examples import example_project
from pynitegui.qt.model_tables import ModelTablesDialog
from pynitegui.qt.automation_core import AutomationCommands
from pynitegui.qt.automation_schema import model_reference
from pynitegui.qt.analysis_jobs import execute_analysis
from pynitegui.qt.annotations import support_geometry, support_label
from pynitegui.qt.reports import model_definition_tables
from test_inclined_supports import supported, solve


class InclinedSupportEditorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = MainWindow()
        self.window.load_project(supported())

    def tearDown(self):
        self.window.saved = self.window.project.to_dict()
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()

    def test_staged_inspector_undo_precision_and_rotated_native_symbol(self):
        w = self.window
        w.project.nodes['N2'].support_angle = 27.123456789123
        w.select(('nodes', 'N2'))
        angle = w.inspector.findChild(QDoubleSpinBox, 'support_angle')
        self.assertIsNotNone(angle)
        button = next(b for b in w.inspector.findChildren(QPushButton) if b.text() == 'Apply')
        button.click()
        self.assertEqual(w.project.nodes['N2'].support_angle, 27.123456789123)
        w.select(('nodes', 'N2'))
        w.inspector.findChild(QDoubleSpinBox, 'support_angle').setValue(-31.)
        self.assertNotEqual(w.project.nodes['N2'].support_angle, -31.)
        next(b for b in w.inspector.findChildren(QPushButton) if b.text() == 'Apply').click()
        self.assertEqual(w.project.nodes['N2'].support_angle, -31.)
        symbols = [item for item in w.view.scene().items() if isinstance(item, EngineeringSymbol) and item.value == ('inclined', -31.)]
        self.assertEqual(len(symbols), 1)
        self.assertIn('tangent -31', symbols[0].toolTip())
        w.undo.undo()
        self.assertEqual(w.project.nodes['N2'].support_angle, 27.123456789123)

    def test_tables_bulk_reset_and_atomic_invalid_angle(self):
        w = self.window
        dialog = ModelTablesDialog(w, w.project)
        self.addCleanup(dialog.deleteLater)
        table = dialog.tables['nodes']
        column = dialog.fields['nodes'].index('support_angle')
        table.item(1, column).setText('200')
        with self.assertRaisesRegex(ValueError, 'angle'):
            dialog.preview()
        self.assertEqual(w.project.nodes['N2'].support_angle, 27.)
        table.item(1, column).setText('-40')
        self.assertEqual(dialog.preview().nodes['N2'].support_angle, -40.)
        table.cellWidget(1, dialog.fields['nodes'].index('support')).setCurrentText('roller')
        self.assertEqual(dialog.preview().nodes['N2'].support_angle, 0.)
        w.select_many([('nodes', 'N1'), ('nodes', 'N2')])
        support = w.inspector.findChild(QComboBox, 'bulk_support')
        support.setCurrentIndex(support.findData('inclined'))
        w.inspector.findChild(QCheckBox, 'bulk_change_support_angle').setChecked(True)
        w.inspector.findChild(QDoubleSpinBox, 'bulk_support_angle').setValue(33.)
        w.inspector.findChild(QPushButton, 'bulk_apply').click()
        self.assertTrue(all(n.support == 'inclined' and n.support_angle == 33. for n in w.project.nodes.values()))
        w.undo.undo()
        self.assertEqual(w.project.nodes['N1'].support, 'fixed')

    def test_snapshot_unit_retention_result_metadata_pagination_and_invalidation(self):
        w = self.window
        r = solve(w.project)
        w.analysis_revision = w.revision
        w.select(('nodes', 'N2'))
        self.assertEqual(w.inspector.findChild(QLabel, 'inclined_normal_reaction').text(), 'Analyze to inspect')
        w.analysis_finished(r, '')
        self.assertIsNotNone(w.result)
        draft = w.inspector.findChild(QDoubleSpinBox, 'support_angle')
        draft.setValue(31.)
        w.select_result_combination('Reverse')
        self.assertIn('Reverse', w.inspector.findChild(QLabel, 'inclined_normal_reaction').toolTip())
        self.assertEqual(draft.value(), 31.)
        w.select_result_combination('Service')
        accepted = w.result
        w.set_units('si')
        self.assertEqual(w.result.snapshot_id, accepted.snapshot_id)
        self.assertIs(w.result.solver, accepted.solver)
        response = AutomationCommands(w).execute('read_results', dict(session_id=w.project_session, kind='nodes', offset=1, limit=1, combination='Reverse'))
        metadata = response['inclined_supports']
        self.assertEqual(set(metadata), {'N2'})
        expected = r.solver._pynitegui_support_reactions['Reverse']['N2']
        self.assertAlmostEqual(metadata['N2']['normal_reaction'], w.project.units.to_display(expected['normal_reaction_kip'], 'force'))
        self.assertEqual(response['support_reaction_units'], ['kN', 'kN', 'kN-m'])
        self.assertIn('inclined', model_reference()['entities']['nodes']['properties']['support']['enum'])
        self.assertIn('support_angle', model_reference('3D')['entities']['nodes']['properties'])
        w.edit('Change inclination', lambda p:setattr(p.nodes['N2'], 'support_angle', -22.))
        self.assertIsNone(w.result)

    def test_real_worker_example_reactions_reports_and_support_geometry(self):
        p = example_project('inclined_roller')
        phases = []
        result = execute_analysis(p, phases.append, Event())
        self.assertTrue(any('inclined' in phase for phase in phases))
        np.testing.assert_allclose(result.reactions['N2'], [-.6/np.sqrt(3), .6, 0.], atol=1e-9)
        tables = str(model_definition_tables(p))
        self.assertIn('tangent 30 deg', tables)
        self.assertIn('Coupled normal', tables)
        self.assertIn('normal translation restrained', support_label(p, p.nodes['N2']))
        paths, circles = support_geometry('inclined', (), 90.)
        self.assertTrue(paths and circles)
        self.assertAlmostEqual(circles[0][0], 19.5)


class SpatialInclinedEditorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window=MainWindow()
        self.window.load_project(example_project('3d_inclined_roller'))

    def tearDown(self):
        self.window.saved=self.window.project.to_dict()
        self.window.close();self.window.deleteLater();self.app.processEvents()

    def test_native_staging_precision_additional_restraints_and_undo(self):
        w=self.window;node=w.project.nodes['N2'];node.support_angle=60.123456789123
        before=w.project.to_dict();w.select(('nodes','N2'))
        w.inspector.findChild(QPushButton,'spatial_apply').click()
        self.assertEqual(w.project.to_dict(),before)
        angle=w.inspector.findChild(QDoubleSpinBox,'support_angle')
        elevation=w.inspector.findChild(QDoubleSpinBox,'support_elevation')
        angle.setValue(-31.);elevation.setValue(22.)
        w.inspector.findChild(QCheckBox,'restraint_y').setChecked(True)
        self.assertEqual(w.project.to_dict(),before)
        w.inspector.findChild(QPushButton,'spatial_apply').click()
        self.assertEqual(w.project.nodes['N2'].support_angle,-31.)
        self.assertEqual(w.project.nodes['N2'].support_elevation,22.)
        self.assertTrue(w.project.nodes['N2'].restraint_y)
        w.undo.undo();self.assertEqual(w.project.to_dict(),before)
        w.select(('nodes','N1'))
        w.inspector.findChild(QComboBox,'spatial_support').setCurrentText('inclined')
        self.assertFalse(any(w.inspector.findChild(QCheckBox,key).isChecked() for key in ('restraint_x','restraint_y','restraint_z','restraint_rx','restraint_ry','restraint_rz')))

    def test_tables_bulk_angles_persistence_and_reset(self):
        w=self.window;dialog=ModelTablesDialog(w,w.project);self.addCleanup(dialog.deleteLater)
        table=dialog.tables['nodes'];fields=dialog.fields['nodes']
        table.item(1,fields.index('support_elevation')).setText('91')
        with self.assertRaisesRegex(ValueError,'elevation'):dialog.preview()
        table.item(1,fields.index('support_elevation')).setText('-17')
        table.item(1,fields.index('restraint_y')).setCheckState(Qt.CheckState.Checked)
        self.assertTrue(dialog.preview().nodes['N2'].restraint_y)
        self.assertEqual(dialog.preview().nodes['N2'].support_elevation,-17.)
        w.select_many([('nodes','N1'),('nodes','N2')])
        support=w.inspector.findChild(QComboBox,'bulk_support');support.setCurrentIndex(support.findData('inclined'))
        for key,value in (('support_angle',44.),('support_elevation',-22.)):
            w.inspector.findChild(QCheckBox,'bulk_change_'+key).setChecked(True)
            w.inspector.findChild(QDoubleSpinBox,'bulk_'+key).setValue(value)
        w.inspector.findChild(QPushButton,'bulk_apply').click()
        self.assertTrue(all(n.support_angle==44. and n.support_elevation==-22. and not any(n.restraints) for n in w.project.nodes.values()))
        w.undo.undo();w.select(('nodes','N2'))
        w.inspector.findChild(QComboBox,'spatial_support').setCurrentText('roller')
        w.inspector.findChild(QPushButton,'spatial_apply').click()
        self.assertEqual((w.project.nodes['N2'].support_angle,w.project.nodes['N2'].support_elevation),(0.,0.))

    def test_real_worker_six_dof_metadata_viewport_reports_and_units(self):
        from pynitegui.qt.spatial_view import viewport_payload
        from pynitegui.qt.spatial_reports import report_images
        from pynitegui.qt.reports import ReportOptions
        w=self.window;result=execute_analysis(w.project,lambda text:None,Event())
        w.analysis_revision=w.revision;w.analysis_finished(result,'');w.select(('nodes','N2'))
        self.assertNotEqual(w.inspector.findChild(QLabel,'inclined_normal_reaction').text(),'Analyze to inspect')
        payload=viewport_payload(w);node=next(n for n in payload['nodes'] if n['name']=='N2')
        np.testing.assert_allclose(node['supportNormal'],[np.sqrt(3)/4,.5,.75],atol=1e-12)
        self.assertEqual(node['supportDetails'][-1]['dof'],'Normal')
        self.assertEqual(len(node['supportDetails']),7)
        self.assertIn('normal az',w.inspector.findChild(QLabel,'inclined_normal_reaction').toolTip())
        self.assertIn('Inclined normal (global XYZ)',str(model_definition_tables(w.project)))
        images=report_images(w.project,result,ReportOptions(diagrams=('axial',),views=('isometric','front','top','right')))
        self.assertEqual(len(images),4)
        self.assertTrue(all(data.startswith(b'\x89PNG') for data in images.values()))
        w.set_units('si')
        response=AutomationCommands(w).execute('read_results',dict(session_id=w.project_session,kind='nodes',offset=1,limit=1,combination='Reversed'))
        self.assertEqual(set(response['inclined_supports']),{'N2'})
        metadata=response['inclined_supports']['N2']
        self.assertEqual(len(metadata['rigid_reaction']),6)
        self.assertEqual(response['support_reaction_units'],['kN']*3+['kN-m']*3)
        np.testing.assert_allclose(metadata['normal_global_xyz'],node['supportNormal'])
        self.assertIn('support_elevation',model_reference('3D')['entities']['nodes']['properties'])
        w.edit('Change normal',lambda p:setattr(p.nodes['N2'],'support_elevation',-17.))
        self.assertIsNone(w.result)

    def test_released_rotation_and_support_metadata_coexist_and_invalid_batch_is_atomic(self):
        from pynitegui.qt.automation_core import batch_candidate, AutomationError
        w=self.window;p=example_project('3d_released_beam');n=p.nodes['N2']
        n.support='inclined';n.support_angle=30.;n.support_elevation=20.;n.restraint_y=True
        w.load_project(p);r=solve(p);w.analysis_revision=w.revision;w.analysis_finished(r,'')
        response=AutomationCommands(w).execute('read_results',dict(session_id=w.project_session,kind='nodes',offset=1,limit=1))
        self.assertEqual(set(response['inclined_supports']),{'N2'})
        self.assertIn('N2',response['inactive_rotation_directions'])
        before=w.project.to_dict()
        with self.assertRaises(AutomationError):
            batch_candidate(w.project,[{'op':'put','collection':'nodes','key':'N2','value':{'support_elevation':91.}}])
        self.assertEqual(w.project.to_dict(),before)
