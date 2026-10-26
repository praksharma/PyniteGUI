"""Explicit camera navigation and recent-history cleanup preserve project work."""
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYNITEGUI_NO_WEBENGINE", "1")
from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QAction
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDoubleSpinBox

from pynitegui.qt.app import MainWindow
from pynitegui.qt.examples import example_project
from pynitegui.qt.model import Load, Project
from pynitegui.qt.recent_projects import recent_paths
from pynitegui.qt.view_focus import selection_bounds


def state(window):
    return (window.project.to_dict(), window.saved, window.path, window.revision, window.undo.count(), window.result)


class NavigationQualityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = MainWindow()
        self.window.load_project(example_project("continuous"))
        self.window.show()
        self.app.processEvents()
        self.window.view.fit()

    def tearDown(self):
        self.window.saved = self.window.project.to_dict()
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()

    def test_fit_selection_changes_only_camera_and_preserves_property_draft(self):
        self.window.select(("nodes", "N1"))
        field = self.window.inspector.findChild(QDoubleSpinBox)
        field.setValue(17.)
        before = state(self.window)
        previous = self.window.view.transform().m11()
        self.window.activateWindow()
        self.window.view.setFocus()
        self.app.processEvents()
        QTest.keyClick(self.window.view, Qt.Key.Key_F, Qt.KeyboardModifier.ShiftModifier)
        self.assertGreater(self.window.view.transform().m11(), previous)
        centre = self.window.view.mapToScene(self.window.view.viewport().rect().center())
        self.assertLess(abs(centre.x()), 1.)
        self.assertLess(abs(centre.y()), 1.)
        self.assertEqual(self.window.selections, [("nodes", "N1")])
        self.assertEqual(state(self.window), before)
        self.assertIs(self.window.inspector.findChild(QDoubleSpinBox), field)
        self.assertEqual(field.value(), 17.)
        self.window.select(None)
        self.assertFalse(self.window.fit_selection_action.isEnabled())
        self.assertFalse(self.window.fit_selection())

    def test_load_station_and_loaded_span_bounds_use_canonical_geometry(self):
        project = Project()
        project.add_member((0., 0.), (240., 0.))
        project.loads["Point"] = Load("Point", "M1", "FY", -1., .5)
        project.loads["Span"] = Load("Span", "M1", "FY", -.1, .25, "distributed", -.1, .75)
        self.assertEqual(selection_bounds(project, [("loads", "Point")]), [[96., -24., -24.], [144., 24., 24.]])
        expected = [[36., -24., -24.], [204., 24., 24.]]
        self.assertEqual(selection_bounds(project, [("loads", "Span")]), expected)
        project.unit_system = "si"
        self.assertEqual(selection_bounds(project, [("loads", "Span")]), expected)
        self.assertIsNone(selection_bounds(project, [("nodes", "Missing")]))

    def test_finding_double_click_focuses_and_unknown_references_stay_disabled(self):
        self.window.show_model_findings(["Node N1: review support."], "Model Check")
        before = state(self.window)
        previous = self.window.view.transform().m11()
        findings = self.window.model_findings
        findings.list.itemDoubleClicked.emit(findings.list.currentItem())
        self.assertEqual(self.window.selections, [("nodes", "N1")])
        self.assertGreater(self.window.view.transform().m11(), previous)
        self.assertEqual(state(self.window), before)
        self.window.show_model_findings(["Unknown solver diagnostic"], "Model Check")
        self.assertFalse(findings.focus_button.isEnabled())
        self.assertFalse(findings.select_button.isEnabled())
        findings.clear()
        self.assertFalse(findings.focus_button.isEnabled())

    def test_spatial_surface_focus_reveals_geometry_and_preserves_orientation_choice(self):
        project = example_project("3d_multistorey_slabs")
        self.window.load_project(project)
        view = self.window.view
        view.ready = True
        view.pending_fit = False
        self.window.surface_visibility_action.setChecked(False)
        self.window.select(("surfaces", "Floor2"))
        before = state(self.window)
        orientation = view.orientation.currentIndex()
        expected = selection_bounds(project, self.window.selections)
        with patch.object(view, "call") as call:
            self.assertTrue(self.window.fit_selection())
        self.assertTrue(self.window.surface_visibility_action.isChecked())
        self.assertIn(unittest.mock.call("focus", expected), call.call_args_list)
        self.assertNotIn(unittest.mock.call("fit"), call.call_args_list)
        self.assertEqual(view.orientation.currentIndex(), orientation)
        self.assertAlmostEqual((expected[0][1]+expected[1][1])/2., 288.)
        self.assertEqual(state(self.window), before)

    def test_pending_spatial_focus_is_replaced_by_fit_or_rejected_after_model_change(self):
        self.window.load_project(example_project("3d_space_frame"))
        view = self.window.view
        bounds = selection_bounds(self.window.project, [("nodes", "N1")])
        view.ready = False
        view.focus_bounds(bounds)
        self.assertIsNotNone(view.pending_focus)
        view.ready = True
        with patch.object(view, "call") as call:
            view.redraw()
        self.assertIn(unittest.mock.call("focus", bounds), call.call_args_list)
        self.assertIsNone(view.pending_focus)
        view.ready = False
        view.focus_bounds(bounds)
        self.window.revision += 1
        view.ready = True
        with patch.object(view, "call") as call:
            view.redraw()
        self.assertIn(unittest.mock.call("fit"), call.call_args_list)
        self.assertFalse(any(entry.args[0] == "focus" for entry in call.call_args_list))
        view.ready = False
        view.focus_bounds(bounds)
        view.fit()
        self.assertIsNone(view.pending_focus)

    def test_findings_reveal_filtered_loads_before_focusing(self):
        self.window.load_filter.setCurrentText("Hide loads")
        before = state(self.window)
        self.window.focus_finding_entities([("loads", "L1")])
        self.assertIsNone(self.window.load_filter.currentData())
        self.assertEqual(self.window.selections, [("loads", "L1")])
        self.assertEqual(state(self.window), before)


class RecentProjectQualityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.root = Path(self.folder.name)
        self.settings = QSettings(str(self.root/"settings.ini"), QSettings.Format.IniFormat)
        self.window = MainWindow(self.root/"recovery", self.settings)
        self.project_path = self.root/"R&D.pynite.json"
        Project().save(self.project_path)
        self.missing = self.root/"offline.pynite.json"
        self.settings.setValue("recent_projects", [str(self.project_path), str(self.missing)])
        self.window.update_recent_menu()

    def tearDown(self):
        self.window.saved = self.window.project.to_dict()
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()
        self.folder.cleanup()

    def actions(self):
        return {action.text(): action for action in self.window.recent_menu.actions() if action.text()}

    def test_unavailable_paths_are_marked_and_menu_actions_do_not_accumulate(self):
        entries = [action for action in self.window.recent_menu.actions() if action.data()]
        self.assertIn("R&&D", entries[0].text())
        self.assertTrue(entries[0].isEnabled())
        self.assertEqual(entries[0].toolTip(), str(self.project_path))
        self.assertFalse(entries[1].isEnabled())
        self.assertIn("unavailable", entries[1].text())
        count = len(self.window.recent_menu.findChildren(QAction))
        for _ in range(25):
            self.window.update_recent_menu()
        self.assertEqual(len(self.window.recent_menu.findChildren(QAction)), count)

    def test_cleanup_changes_only_history_and_retains_files_model_and_recovery(self):
        self.window.edit("Grid", lambda project: setattr(project, "grid", 24.))
        self.window.autosave_now()
        snapshot = self.window.recovery.path
        before, data, recovery = state(self.window), self.project_path.read_bytes(), snapshot.read_bytes()
        self.actions()["Remove Unavailable Entries"].trigger()
        self.assertEqual(self.settings.value("recent_projects", [], type=list), [str(self.project_path)])
        self.actions()["Clear Recent Projects"].trigger()
        self.assertEqual(self.settings.value("recent_projects", [], type=list), [])
        self.assertFalse(self.window.recent_menu.isEnabled())
        self.assertEqual(state(self.window), before)
        self.assertEqual(self.project_path.read_bytes(), data)
        self.assertEqual(snapshot.read_bytes(), recovery)

    def test_history_refreshes_when_file_menu_opens(self):
        self.settings.setValue("recent_projects", [])
        self.window.update_recent_menu()
        self.assertFalse(self.window.recent_menu.isEnabled())
        self.settings.setValue("recent_projects", [str(self.project_path)])
        self.window.menuBar().actions()[0].menu().aboutToShow.emit()
        self.assertTrue(self.window.recent_menu.isEnabled())

    def test_invalid_history_values_are_ignored_and_capped(self):
        stored = [None, {}, "relative.json", "bad\0path", str(self.project_path), str(self.project_path)]
        stored += [str(self.root/f"project-{i}.json") for i in range(20)]
        settings = SimpleNamespace(value=lambda *args, **kwargs: stored)
        paths = recent_paths(settings)
        self.assertEqual(paths[0], self.project_path)
        self.assertEqual(len(paths), 10)
        self.assertEqual(len(set(paths)), 10)
        for malformed in (None, "wrong", 123):
            settings.value = lambda *args, **kwargs: malformed
            self.assertEqual(recent_paths(settings), [])
        with patch.object(self.settings, "value", side_effect=TypeError("Invalid settings")):
            self.window.update_recent_menu()
        self.assertFalse(self.window.recent_menu.isEnabled())

    def test_file_removed_after_menu_open_does_not_prompt_to_discard_current_work(self):
        self.project_path.unlink()
        before = state(self.window)
        with patch.object(self.window, "confirm_discard") as discard, patch("pynitegui.qt.app.QMessageBox.warning") as warning:
            self.window.open_recent(self.project_path)
        discard.assert_not_called()
        warning.assert_called_once()
        self.assertEqual(state(self.window), before)

    def test_cancelled_recent_open_preserves_unsaved_work(self):
        self.window.edit("Grid", lambda project: setattr(project, "grid", 24.))
        before = state(self.window)
        entry = next(action for action in self.window.recent_menu.actions() if action.data() == str(self.project_path))
        with patch.object(self.window, "confirm_discard", return_value=False):
            entry.trigger()
            self.window.open_recent(str(self.project_path))
        self.assertEqual(state(self.window), before)
