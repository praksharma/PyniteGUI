"""Workspace layout switches preserve the current editing/result session."""
import contextlib
import io
import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYNITEGUI_NO_WEBENGINE", "1")
from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QApplication, QDoubleSpinBox, QToolBar
from pynitegui.qt.analysis import analyze
from pynitegui.qt.app import MainWindow
from pynitegui.qt.examples import example_project
from pynitegui.qt.theme import configure_theme
from pynitegui.qt.workspaces import TOOLBARS


class WorkspaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = MainWindow()
        self.window.load_project(example_project("portal"))
        self.window.show()
        self.app.processEvents()
        self.window.view.fit()

    def tearDown(self):
        self.window.saved = self.window.project.to_dict()
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()
        configure_theme(self.app, "light")

    def state(self):
        w = self.window
        return w.project.to_dict(), w.saved, w.path, w.revision, w.undo.count(), list(w.selections), w.result, w.mode

    def test_model_results_all_and_collapsed_commands(self):
        w, c = self.window, self.window.workspaces
        before = self.state()
        for name in TOOLBARS:
            self.assertEqual(len(w.findChildren(QToolBar, name)), 1)
        for key in ("model", "results", "all"):
            c.actions[key].trigger()
            self.assertEqual(c.selector.currentData(), key)
            for name, role in TOOLBARS.items():
                toolbar = w.findChild(QToolBar, name)
                self.assertEqual(not toolbar.isHidden(), key == "all" or role in ("shared", key))
            c.commands.trigger()
            self.assertTrue(all(w.findChild(QToolBar, name).isHidden() for name in TOOLBARS))
            self.assertFalse(c.toolbar.isHidden())
            c.commands.trigger()
            self.assertEqual(self.state(), before)
        c.choose("results")
        self.assertFalse(w.results_dock.isHidden())
        self.assertTrue(w.structure_dock.isHidden())
        self.assertTrue(w.properties_dock.isHidden())
        self.assertFalse(w.results_panel.tabs.isEnabled())
        c.choose("model")
        self.assertTrue(w.results_dock.isHidden())
        self.assertFalse(w.properties_dock.isHidden())

    def test_switch_preserves_draft_selection_transform_and_retained_result_window(self):
        w, c = self.window, self.window.workspaces
        with contextlib.redirect_stdout(io.StringIO()):
            result = analyze(w.project)
        w.analysis_revision = w.revision
        w.analysis_finished(result, "")
        w.select(("nodes", "N2"))
        field = w.inspector.findChild(QDoubleSpinBox)
        field.setValue(17.)
        dialog = w.diagrams()
        before = self.state()
        transform = w.view.transform()
        self.app.processEvents()
        center = w.view.mapToScene(w.view.viewport().width()//2, w.view.viewport().height()//2)
        try:
            with patch.object(w, "refresh", side_effect=AssertionError("No rebuilding drafts")), \
                 patch.object(w, "update_inspector", side_effect=AssertionError("No inspector rebuild")), \
                 patch.object(w.view, "redraw", side_effect=AssertionError("No redraw")), \
                 patch.object(w.view, "fit", side_effect=AssertionError("No fit")):
                for key in ("results", "model", "all"):
                    c.choose(key)
                    self.app.processEvents()
                    self.assertEqual(w.view.transform(), transform)
                    projected = w.view.mapFromScene(center)
                    actual = QPoint(w.view.viewport().width()//2, w.view.viewport().height()//2)
                    self.assertLessEqual((projected-actual).manhattanLength(), 4)
            self.assertEqual(self.state(), before)
            self.assertIs(w.inspector.findChild(QDoubleSpinBox), field)
            self.assertEqual(field.value(), 17.)
            self.assertEqual(dialog.result.snapshot_id, result.snapshot_id)
        finally:
            dialog.close()

    def test_restore_layout_resets_controls_and_recovers_workspaces(self):
        w, c = self.window, self.window.workspaces
        w.select(("nodes", "N2"))
        field = w.inspector.findChild(QDoubleSpinBox)
        field.setValue(19.)
        before = self.state()
        c.choose("results")
        c.commands.trigger()
        c.toolbar.hide()
        w.restore_default_layout()
        self.assertEqual(c.current, "all")
        self.assertEqual(c.selector.currentData(), "all")
        self.assertTrue(c.commands.isChecked())
        self.assertFalse(c.toolbar.isHidden())
        self.assertTrue(all(not w.findChild(QToolBar, name).isHidden() for name in TOOLBARS))
        self.assertEqual(self.state(), before)
        self.assertIs(w.inspector.findChild(QDoubleSpinBox), field)
        self.assertEqual(field.value(), 19.)

    def test_spatial_switch_never_calls_renderer_or_changes_view_controls(self):
        w, c = self.window, self.window.workspaces
        w.load_project(example_project("3d_space_frame"))
        w.view.orientation.setCurrentIndex(2)
        w.view.plane.setCurrentText("XZ")
        w.view.offset.setValue(24.)
        w.select(("members", "M1"))
        before = self.state()
        controls = w.view.orientation.currentIndex(), w.view.plane.currentText(), w.view.offset.value()
        with patch.object(w.view, "call", side_effect=AssertionError("No camera/scene requests")), \
             patch.object(w.view, "redraw", side_effect=AssertionError("No scene rebuild")):
            c.choose("results")
            c.commands.trigger()
            c.choose("model")
            self.app.processEvents()
        self.assertEqual(self.state(), before)
        self.assertEqual((w.view.orientation.currentIndex(), w.view.plane.currentText(), w.view.offset.value()), controls)

    def test_minimum_size_themes_and_mcp_guard(self):
        w, c = self.window, self.window.workspaces
        w.resize(820, 560)
        for theme in ("light", "dark"):
            configure_theme(self.app, theme)
            for key in ("model", "results", "all"):
                c.choose(key)
                self.app.processEvents()
                self.assertFalse(c.selector.isHidden())
                self.assertFalse(w.grab().isNull())
                self.assertLessEqual(c.toolbar.sizeHint().width(), 200)
        w.mcp_mode = True
        before = self.state()
        c.selector.setCurrentIndex(c.selector.findData("results"))
        self.assertEqual(c.current, "all")
        self.assertEqual(c.selector.currentData(), "all")
        c.commands.trigger()
        self.assertTrue(c.commands.isChecked())
        self.assertEqual(self.state(), before)
        w.mcp_mode = False
