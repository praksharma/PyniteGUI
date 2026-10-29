"""Native spatial rotational releases, atomic edits and recovered result context."""
import os
from tempfile import TemporaryDirectory
import time
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYNITEGUI_NO_WEBENGINE", "1")
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QCheckBox, QPushButton, QMessageBox, QLabel
from pynitegui.qt.app import MainWindow
from pynitegui.qt.examples import example_project
from pynitegui.qt.model_tables import ModelTablesDialog
from pynitegui.qt.spatial_view import viewport_payload
from pynitegui.qt.reports import report_html


class SpatialReleaseEditorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.directory = TemporaryDirectory()
        self.window = MainWindow(self.directory.name)
        self.window.load_project(example_project("3d_released_beam"))
        self.window.select(("members", "M1"))

    def wait_finished(self):
        end = time.monotonic()+25
        while self.window.thread is not None and time.monotonic() < end:
            self.app.processEvents()
            time.sleep(.005)
        self.assertIsNone(self.window.thread)

    def tearDown(self):
        if self.window.thread is not None:
            self.window.cancel_analysis()
            self.wait_finished()
        self.window.saved = self.window.project.to_dict()
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()
        self.directory.cleanup()

    def test_staged_rotational_checkboxes_tables_bulk_and_invalid_undo_rollback(self):
        w = self.window
        original = w.project.to_dict()
        w.findChild(QCheckBox, "spatial_release_start").setChecked(False)
        self.assertEqual(w.project.to_dict(), original)
        w.findChild(QPushButton, "spatial_apply").click()
        self.assertFalse(w.project.members["M1"].release_start)
        self.assertEqual(w.undo.count(), 1)
        w.undo.undo()
        self.assertEqual(w.project.to_dict(), original)
        w.findChild(QCheckBox, "spatial_release_start_rx").setChecked(True)
        w.findChild(QCheckBox, "spatial_release_end_rx").setChecked(True)
        with patch.object(QMessageBox, "warning") as warning:
            w.findChild(QPushButton, "spatial_apply").click()
        warning.assert_called_once()
        self.assertEqual(w.project.to_dict(), original)
        tables = ModelTablesDialog(w, w.project)
        table = tables.tables["members"]
        column = tables.fields["members"].index("release_start_rx")
        table.item(0, column).setCheckState(Qt.CheckState.Checked)
        tables.accept()
        self.assertTrue(tables.definition.members["M1"].release_start_rx)
        self.assertEqual(w.project.to_dict(), original)
        tables.deleteLater()
        w.select_many([("nodes", "N1"), ("members", "M1")])
        w.findChild(QCheckBox, "bulk_release_start").setCheckState(Qt.CheckState.Unchecked)
        w.findChild(QPushButton, "bulk_apply").click()
        self.assertFalse(w.project.members["M1"].release_start)
        w.undo.undo()
        self.assertEqual(w.project.to_dict(), original)

    def test_actual_worker_recovers_end_slopes_viewport_labels_reports_and_units(self):
        w = self.window
        w.run_analysis()
        self.wait_finished()
        self.assertIsNotNone(w.result)
        self.assertEqual(w.result.displacements["N2"][3:], (None, None, None))
        w.select(("members", "M1"))
        text = "\n".join(w.form.itemAt(i).widget().text() for i in range(w.form.count())
                          if w.form.itemAt(i).widget() and hasattr(w.form.itemAt(i).widget(), "text"))
        self.assertIn("Member-end bending rotations", text)
        self.assertIn("rad", text)
        payload = viewport_payload(w)
        self.assertEqual(payload["members"][0]["releaseLabels"], ["RY, RZ", "RY, RZ"])
        html = report_html(w.project, w.result)
        self.assertIn("Start releases (local)", html)
        self.assertIn("RY, RZ", html)
        self.assertIn("unused", html.lower())
        snapshot = w.result.snapshot_id
        w.set_units("si")
        self.assertEqual(w.result.snapshot_id, snapshot)
        w.select(("members", "M1"))
        self.assertTrue(w.findChild(QCheckBox, "spatial_release_start_ry").isChecked())

    def test_translational_controls_tables_bulk_rollback_worker_and_recovered_motion(self):
        w = self.window
        w.load_project(example_project('3d_sliding_beam'))
        w.select(('members','M1'))
        original = w.project.to_dict()
        w.findChild(QCheckBox,'spatial_release_end_z').setChecked(False)
        self.assertEqual(w.project.to_dict(),original)
        w.findChild(QPushButton,'spatial_apply').click()
        self.assertFalse(w.project.members['M1'].release_end_z)
        w.undo.undo()
        self.assertEqual(w.project.to_dict(),original)
        w.findChild(QCheckBox,'spatial_release_start_y').setChecked(True)
        with patch.object(QMessageBox,'warning') as warning:
            w.findChild(QPushButton,'spatial_apply').click()
        warning.assert_called_once()
        self.assertEqual(w.project.to_dict(),original)
        tables = ModelTablesDialog(w,w.project)
        column = tables.fields['members'].index('release_end_z')
        tables.tables['members'].item(0,column).setCheckState(Qt.CheckState.Unchecked)
        tables.accept()
        self.assertFalse(tables.definition.members['M1'].release_end_z)
        self.assertEqual(w.project.to_dict(),original)
        tables.deleteLater()
        w.select_many([('nodes','N1'),('members','M1')])
        w.findChild(QCheckBox,'bulk_release_end_z').setCheckState(Qt.CheckState.Unchecked)
        w.findChild(QPushButton,'bulk_apply').click()
        self.assertFalse(w.project.members['M1'].release_end_z)
        w.undo.undo()
        self.assertEqual(w.project.to_dict(),original)
        w.run_analysis()
        self.wait_finished()
        self.assertIsNotNone(w.result)
        w.select(('members','M1'))
        labels = '\n'.join(item.text() for item in w.inspector.findChildren(QLabel))
        self.assertIn('Member-end translations (local)',labels)
        self.assertIn('can differ from the joint',labels)
        self.assertEqual(viewport_payload(w)['members'][0]['releaseLabels'],['None','DX, DY, DZ'])
        self.assertIn('Released Member-End Translations',report_html(w.project,w.result))
        identity = w.result.snapshot_id
        w.set_units('si')
        self.assertEqual(w.result.snapshot_id,identity)
        w.select(('members','M1'))
        labels = '\n'.join(item.text() for item in w.inspector.findChildren(QLabel))
        self.assertIn(f" {w.project.units.length}\nMember-side",labels)


if __name__ == "__main__":
    unittest.main()
