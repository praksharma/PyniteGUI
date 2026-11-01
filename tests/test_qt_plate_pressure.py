"""Editable pressure profiles, snapshot probes, native examples and units."""
import csv
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
from PySide6.QtWidgets import QApplication,QFileDialog,QDialog
from pynitegui.qt.app import MainWindow
from pynitegui.qt.plate_workspace import PlateWorkspace
from pynitegui.qt.plate_loads import PlateLoadsDialog
from pynitegui.qt.official_plate import example_definition
from pynitegui.qt.plate_model import PlateDefinition


class PlatePressureEditorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])

    def wait(self,predicate):
        end=time.monotonic()+30
        while not predicate() and time.monotonic()<end:self.app.processEvents();time.sleep(.005)
        self.assertTrue(predicate(),'Plate worker timed out')

    def close(self,w):
        if w.thread is not None:w.worker.cancel();self.wait(lambda:w.thread is None)
        w.pending=False;w.saved=w.definition.to_dict();w.reject();w.deleteLater();self.app.processEvents()

    def test_staged_profile_units_rename_delete_cancel_and_one_step_undo(self):
        for units in ('imperial','imperial_ft','si','si_mm','custom_cm_kN'):
            d=PlateDefinition(unit_system=units,pressure=-1e-5,additional_pressures={'Other':2e-5},mesh_size=60.)
            w=PlateWorkspace(definition=d)
            try:
                before=w.definition.to_dict();dialog=PlateLoadsDialog(w,w.definition)
                axis,end=dialog.cases.cellWidget(0,3),dialog.cases.cellWidget(0,4)
                axis.setCurrentIndex(axis.findData('y'));end.setValue(d.units.to_display(1e-5,'pressure'))
                dialog.cases.selectRow(0)
                with patch('pynitegui.qt.plate_loads.QInputDialog.getText',return_value=('Water',True)):dialog.perform('cases','edit')
                self.assertEqual(dialog.definition.pressure_profiles['Water']['axis'],'y')
                self.assertAlmostEqual(dialog.definition.pressure_profiles['Water']['end_pressure'],1e-5)
                self.assertEqual(w.definition.to_dict(),before)
                with patch('pynitegui.qt.plate_loads.PlateLoadsDialog',return_value=dialog),patch.object(dialog,'exec',return_value=QDialog.DialogCode.Rejected):w.configure_loading()
                self.assertEqual(w.definition.to_dict(),before)
                dialog.accept()
                with patch('pynitegui.qt.plate_loads.PlateLoadsDialog',return_value=dialog),patch.object(dialog,'exec',return_value=QDialog.DialogCode.Accepted):w.configure_loading()
                self.assertEqual(w.undo.count(),1);self.assertIn('Water',w.definition.pressure_profiles)
                w.undo.undo();self.assertEqual(w.definition.to_dict(),before);w.undo.redo()
                noop=PlateLoadsDialog(w,w.definition);noop.accept()
                self.assertEqual(noop.definition.to_dict(),w.definition.to_dict());noop.deleteLater()
                dialog.deleteLater()
            finally:self.close(w)

    def test_native_wall_entry_worker_pressure_plot_probes_export_save_and_unit_identity(self):
        host=MainWindow();d=example_definition('official_wall_hydrostatic');before=host.project.to_dict()
        captured=[]
        def execute(panel):captured.append(panel.definition.to_dict());return QDialog.DialogCode.Rejected
        with patch.object(PlateWorkspace,'exec',execute):host.example('official_wall_hydrostatic')
        self.assertEqual(captured,[d.to_dict()]);self.assertEqual(host.project.to_dict(),before)
        w=PlateWorkspace(definition=d)
        try:
            w.component.setCurrentIndex(7);self.assertIn('preview',w.ax.get_title())
            w.run_analysis();self.wait(lambda:w.thread is None)
            self.assertIsNotNone(w.result,w.status.text());snapshot=w.result['snapshot_id']
            self.assertAlmostEqual(w.result['reactions'].sum(),-245.7,places=8)
            w.component.setCurrentIndex(7);w.canvas.draw();self.assertEqual(w.component.currentIndex(),7)
            self.assertIn('centroid',w.ax.get_title().lower())
            w.inspect_results();inspector=w.inspector;inspector.select_probe(w.result['element_names'][0],-1.,-1.)
            self.assertIn('Applied element pressure',inspector.probe.text());self.assertIn('Target profile pressure',inspector.probe.text())
            target=inspector.probe_data['target_pressure'];applied=inspector.probe_data['applied_pressure']
            self.assertNotEqual(target,applied)
            w.units_box.setCurrentIndex(w.units_box.findData('si_mm'))
            self.assertEqual(w.result['snapshot_id'],snapshot);self.assertEqual(w.component.currentIndex(),7)
            self.assertAlmostEqual(inspector.probe_data['applied_pressure'],applied)
            self.assertIn('N/mm2',inspector.probe.text())
            with tempfile.TemporaryDirectory() as directory:
                csv_path=Path(directory)/'wall.csv';project=Path(directory)/'wall.pyniteplate';probe=Path(directory)/'probe.csv'
                with patch.object(QFileDialog,'getSaveFileName',return_value=(str(csv_path),'CSV')):w.export_csv()
                with csv_path.open() as stream:rows=list(csv.DictReader(stream))
                self.assertEqual(rows[0]['Snapshot'],snapshot)
                self.assertEqual(json.loads(rows[0]['Pressure profiles (canonical kip/in2)']),d.pressure_profiles)
                self.assertAlmostEqual(float(rows[0]['Combined pressure at zero (kip/in2)']),.0091)
                self.assertAlmostEqual(float(rows[0]['dq/dlocal y (kip/in3)']),-.0091/180)
                with patch('pynitegui.qt.plate_inspection_dialog.QFileDialog.getSaveFileName',return_value=(str(probe),'CSV')):inspector.export_csv(True)
                with probe.open() as stream:row=next(csv.DictReader(stream))
                self.assertIn('Target profile pressure (N/mm2)',row)
                with patch.object(QFileDialog,'getSaveFileName',return_value=(str(project),'Plate')):w.save_file()
                saved=PlateDefinition.open(project);self.assertEqual(saved.pressure_profiles,d.pressure_profiles);self.assertEqual(saved.to_dict()['version'],4)
            w.fields['height'].setValue(5000.);self.assertIsNone(w.result);self.assertFalse(inspector.export_probe.isEnabled())
        finally:
            self.close(w);host.saved=host.project.to_dict();host.close();host.deleteLater();self.app.processEvents()

    def test_case_delete_removes_owned_profile_and_uniform_toggle_is_explicit(self):
        d=PlateDefinition(additional_pressures={'Unused':1e-5},pressure_profiles={'Unused':{'axis':'x','end_pressure':-1e-5}})
        uniform=PlateLoadsDialog(None,d);uniform.cases.cellWidget(1,3).setCurrentIndex(0);uniform.accept()
        self.assertNotIn('Unused',uniform.definition.pressure_profiles);self.assertIn('Unused',d.pressure_profiles);uniform.deleteLater()
        dialog=PlateLoadsDialog(None,d)
        dialog.cases.selectRow(1);dialog.perform('cases','delete');dialog.accept()
        self.assertNotIn('Unused',dialog.definition.pressure_profiles);self.assertIn('Unused',d.pressure_profiles)
        dialog.deleteLater()
