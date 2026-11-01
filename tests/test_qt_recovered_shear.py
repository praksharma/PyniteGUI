"""Real plate workers, explicitly masked contours, provenance and stale clearing."""
import csv
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
import numpy as np

os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
os.environ.setdefault('PYNITEGUI_NO_WEBENGINE','1')
from PySide6.QtWidgets import QApplication
from matplotlib.collections import PolyCollection
from pynitegui.qt.official_plate import example_definition
from pynitegui.qt.plate_workspace import PlateWorkspace


class RecoveredShearUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])

    def setUp(self):
        self.window=PlateWorkspace()

    def tearDown(self):
        if self.window.thread is not None:
            self.window.worker.cancel();self.wait_finished()
        self.window.pending=False;self.window.saved=self.window.definition.to_dict()
        self.window.reject();self.window.deleteLater();self.app.processEvents()

    def wait_finished(self):
        deadline=time.monotonic()+40
        while self.window.thread is not None and time.monotonic()<deadline:
            self.app.processEvents();time.sleep(.005)
        self.assertIsNone(self.window.thread)
        self.assertIsNotNone(self.window.result)

    def test_worker_examples_masks_combinations_probe_csv_units_and_stale_clear(self):
        w=self.window
        for key in ('thin_plate_recovered_shear','opening_plate_recovered_shear'):
            w.install(example_definition(key).to_dict());w.run_analysis();self.wait_finished()
            meta=w.result['recovered_shear'];self.assertGreater(meta['available'],0)
            for index in (5,6):self.assertFalse(w.component.model().item(index).isEnabled())
            for index in (8,9):self.assertTrue(w.component.model().item(index).isEnabled())
            w.component.setCurrentIndex(8)
            artist=next(c for c in w.ax.collections if isinstance(c,PolyCollection))
            field=artist.get_array();mask=np.ma.getmaskarray(field)
            self.assertEqual(int(mask.sum()),meta['total']-meta['available'])
            if 'opening' in key:self.assertTrue(mask.any())
            original=field.copy();snapshot=w.result['snapshot_id']
            w.combination.setCurrentText('Reverse')
            current=next(c for c in w.ax.collections if isinstance(c,PolyCollection)).get_array()
            np.testing.assert_allclose(current.compressed(),-2*original.compressed())
            np.testing.assert_array_equal(np.ma.getmaskarray(current),mask)
            w.combination.setCurrentText('Zero')
            current=next(c for c in w.ax.collections if isinstance(c,PolyCollection)).get_array()
            np.testing.assert_allclose(current.compressed(),0.,atol=1e-12)
            np.testing.assert_array_equal(np.ma.getmaskarray(current),mask)
            w.combination.setCurrentText('Plate');w.inspect_results();inspector=w.inspector
            available=next(i for i,v in enumerate(meta['values']) if v is not None)
            inspector.element.setCurrentText(w.result['element_names'][available])
            self.assertIsNotNone(inspector.probe_data['recovered_Qx'])
            inspector.xi.setValue(.1)
            self.assertIsNone(inspector.probe_data['recovered_Qx'])
            self.assertEqual(inspector.probe_data['shear_status'],'centre_only')
            inspector.xi.setValue(0.)
            if mask.any():
                missing=int(np.where(mask)[0][0]);inspector.element.setCurrentText(w.result['element_names'][missing])
                self.assertIsNone(inspector.probe_data['recovered_Qx'])
                self.assertIn('corner',inspector.probe_data['shear_status'])
            w.units_box.setCurrentIndex(w.units_box.findData('si_mm'))
            self.assertEqual(w.result['snapshot_id'],snapshot)
            self.assertIn('N/mm',inspector.probe.text())
            with tempfile.TemporaryDirectory() as directory:
                path=Path(directory)/'centres.csv'
                with patch('pynitegui.qt.plate_inspection_dialog.QFileDialog.getSaveFileName',return_value=(str(path),'')):
                    inspector.export_csv(False)
                with path.open(newline='') as stream:rows=list(csv.DictReader(stream))
                self.assertEqual(len(rows),meta['total']);self.assertEqual(rows[0]['Snapshot'],snapshot)
                self.assertEqual(sum(row['Recovered Qx (N/mm)']=='' for row in rows),int(mask.sum()))
                self.assertIn(meta['method'],rows[0]['Recovery'])
            w.fields['thickness'].setValue(2*w.fields['thickness'].value())
            self.assertIsNone(w.result);self.assertIsNone(inspector.result)
            self.assertFalse(w.component.model().item(8).isEnabled())
            self.assertFalse(inspector.export_centres.isEnabled())

    def test_unsupported_scope_disables_recovery_with_reason(self):
        w=self.window;d=example_definition('thin_plate_recovered_shear');d.thickness=3.
        w.install(d.to_dict());w.run_analysis();self.wait_finished()
        self.assertIn('thickness',w.recovered_note.text())
        self.assertFalse(w.component.model().item(8).isEnabled())
        w.component.setCurrentIndex(8);self.assertNotEqual(w.component.currentIndex(),8)
        self.assertTrue(np.isfinite(w.result['moments']).all())
