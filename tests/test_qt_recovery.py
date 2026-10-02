"""Recovery files are separate, atomic, and owned by an individual window."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication, QMessageBox
from pynitegui.qt.app import MainWindow
from pynitegui.qt.model import Project
from pynitegui.qt.recovery import RecoveryStore


class RecoveryTests(unittest.TestCase):
    def test_atomic_snapshots_and_live_process_filter(self):
        with tempfile.TemporaryDirectory() as directory:
            store = RecoveryStore(directory)
            project = Project()
            saved = project.to_dict()
            project.add_member((0, 0), (240, 0))
            store.write(project, saved, Path(directory) / "original.json")
            self.assertEqual(len(store.snapshots(include_active=True)), 1)
            self.assertFalse(store.snapshots())
            restored, original, baseline = store.read(store.path)
            self.assertEqual(restored.to_dict(), project.to_dict())
            self.assertEqual(baseline, saved)
            self.assertEqual(original.name, "original.json")
            self.assertFalse(store.path.with_suffix(".tmp").exists())

    def test_failed_replace_preserves_previous_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            store = RecoveryStore(directory)
            project = Project()
            store.write(project, project.to_dict())
            original = store.path.read_bytes()
            project.grid = 24
            with patch.object(Path, "replace", side_effect=OSError("disk failure")):
                with self.assertRaises(OSError):
                    store.write(project, project.to_dict())
            self.assertEqual(store.path.read_bytes(), original)
            self.assertFalse(store.path.with_suffix(".tmp").exists())

    def test_multiple_windows_and_corrupt_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            one, two = RecoveryStore(directory), RecoveryStore(directory)
            self.assertNotEqual(one.path, two.path)
            one.write(Project(), Project().to_dict())
            two.write(Project(), Project().to_dict())
            (Path(directory) / "broken.json").write_text("[]", encoding="utf-8")
            self.assertEqual(len(one.snapshots(include_active=True)), 2)
            self.assertEqual(len(one.errors), 1)
            one.clear()
            self.assertTrue(two.path.exists())
            self.assertTrue((Path(directory) / "broken.json").exists())


class RecoveryEditorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.settings = QSettings(str(Path(self.directory.name) / "settings.ini"), QSettings.Format.IniFormat)
        self.window = MainWindow(self.directory.name, self.settings)

    def tearDown(self):
        self.window.saved = self.window.project.to_dict()
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()
        self.directory.cleanup()

    def test_autosave_never_overwrites_original_and_recovery_is_dirty(self):
        original = Path(self.directory.name) / "model.json"
        Project().save(original)
        before = original.read_bytes()
        self.window.load_project(Project(), original)
        self.window.edit("Draw", lambda p: p.add_member((0, 0), (240, 0)))
        self.assertTrue(self.window.autosave_now())
        self.assertEqual(original.read_bytes(), before)
        snapshot = self.window.recovery.path
        other = MainWindow(self.directory.name)
        try:
            self.assertTrue(other.recover_snapshot(snapshot))
            self.assertEqual(len(other.project.members), 1)
            self.assertNotEqual(other.project.to_dict(), other.saved)
            self.assertTrue(other.recovery.path.exists())
            self.assertFalse(snapshot.exists())
            self.assertEqual(original.read_bytes(), before)
        finally:
            other.saved = other.project.to_dict()
            other.close()
            other.deleteLater()
            self.app.processEvents()

    def test_save_clears_snapshot_and_records_recent(self):
        filename = Path(self.directory.name) / "model.json"
        self.window.path = filename
        self.window.edit("Grid", lambda p: setattr(p, "grid", 24))
        self.window.autosave_now()
        self.assertTrue(self.window.recovery.path.exists())
        self.assertTrue(self.window.save_project())
        self.assertFalse(self.window.recovery.path.exists())
        self.assertEqual(self.settings.value("recent_projects", [], type=list), [str(filename)])
        self.window.record_recent(filename)
        self.assertEqual(len(self.window.recent_menu.actions()), 1)

    def test_cancelled_close_keeps_recovery(self):
        self.window.edit("Grid", lambda p: setattr(p, "grid", 24))
        self.window.autosave_now()
        with patch.object(self.window, "confirm_discard", return_value=False):
            self.window.close()
        self.assertTrue(self.window.recovery.path.exists())
        self.assertTrue(self.window.autosave_timer.isActive())

    def test_autosave_failure_leaves_model_and_dirty_state_unchanged(self):
        self.window.edit("Grid", lambda p: setattr(p, "grid", 24))
        before = self.window.project.to_dict()
        with patch.object(self.window.recovery, "write", side_effect=OSError("disk full")):
            self.assertFalse(self.window.autosave_now())
        self.assertEqual(self.window.project.to_dict(), before)
        self.assertNotEqual(self.window.project.to_dict(), self.window.saved)
        self.assertIn("Autosave failed", self.window.statusBar().currentMessage())

    def test_unavailable_recovery_directory_does_not_stop_editor(self):
        with patch("pynitegui.qt.recovery.RecoveryStore", side_effect=PermissionError("read only")), patch.object(QMessageBox, "warning") as warning:
            window = MainWindow(self.directory.name)
            self.assertIsNone(window.recovery)
            self.assertFalse(window.autosave_timer.isActive())
            warning.assert_called_once()
            window.close()
            window.deleteLater()
        self.app.processEvents()

    def test_corrupt_nested_project_is_preserved_not_offered(self):
        self.window.edit("Grid", lambda p: setattr(p, "grid", 24))
        self.window.autosave_now()
        snapshot = self.window.recovery.path
        payload = json.loads(snapshot.read_text())
        payload["project"]["nodes"] = []
        snapshot.write_text(json.dumps(payload))
        self.assertFalse(self.window.recovery.snapshots(include_active=True))
        self.assertEqual(len(self.window.recovery.errors), 1)
        self.assertTrue(snapshot.exists())


if __name__ == "__main__":
    unittest.main()
