"""Discovery and preview must preserve the active project until an approved open."""
import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYNITEGUI_NO_WEBENGINE", "1")
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QDialog, QDoubleSpinBox

from pynitegui.qt.app import MainWindow
from pynitegui.qt.example_browser import ExampleBrowser, NOTES
from pynitegui.qt.examples import EXAMPLES, EXAMPLE_GROUPS, example_project
from pynitegui.qt.theme import configure_theme


def state(window):
    return (window.project.to_dict(), window.saved, window.path, window.revision, window.undo.count(), window.result)


class ExampleBrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = MainWindow()
        self.window.load_project(example_project("portal", "si"))
        self.browser = ExampleBrowser(self.window)

    def tearDown(self):
        self.browser.reject()
        self.browser.deleteLater()
        self.window.saved = self.window.project.to_dict()
        self.window.close()
        self.window.deleteLater()
        configure_theme(self.app, "light")
        self.app.processEvents()

    def test_catalog_preview_loading_and_checks_cover_every_example_without_solving(self):
        self.assertEqual(set(NOTES), set(EXAMPLES))
        self.assertEqual(self.browser.list.count(), len(EXAMPLES))
        before = state(self.window)
        with patch("pynitegui.qt.analysis.analyze", side_effect=AssertionError("Preview must not solve")):
            for row in range(self.browser.list.count()):
                self.browser.list.setCurrentRow(row)
                key = self.browser.selected_key
                self.assertEqual(self.browser.preview.project.to_dict(), example_project(key, "si").to_dict())
                text = self.browser.details.toPlainText()
                self.assertIn(NOTES[key][0], text)
                self.assertIn(NOTES[key][1], text)
                self.assertIn("m, kN", text)
                self.assertIn("Combinations", text)
        self.assertEqual(state(self.window), before)

    def test_filters_preserve_selection_and_no_matches_clear_stale_preview(self):
        self.browser.search.setText("official truss")
        self.assertEqual(self.browser.list.count(), 1)
        self.assertEqual(self.browser.selected_key, "3d_official_truss")
        self.browser.category.setCurrentIndex(self.browser.category.findData("Trusses"))
        self.assertEqual(self.browser.selected_key, "3d_official_truss")
        self.browser.search.setText("nothing matches this")
        self.assertEqual(self.browser.list.count(), 0)
        self.assertIsNone(self.browser.selected_key)
        self.assertIsNone(self.browser.preview.project)
        self.assertEqual(self.browser.details.toPlainText(), "")
        self.assertFalse(self.browser.open_button.isEnabled())
        self.browser.accept()
        self.assertNotEqual(self.browser.result(), QDialog.DialogCode.Accepted)
        self.browser.search.clear()
        self.assertEqual(self.browser.list.count(), len(EXAMPLE_GROUPS["Trusses"]))

    def test_search_and_cancel_preserve_unapplied_inspector_input(self):
        self.window.select(("nodes", "N1"))
        field = self.window.inspector.findChild(QDoubleSpinBox)
        field.setValue(17.)
        before = state(self.window)
        self.browser.search.setText("hinge")
        self.browser.reject()
        self.assertEqual(state(self.window), before)
        self.assertIs(self.window.inspector.findChild(QDoubleSpinBox), field)
        self.assertEqual(field.value(), 17.)

    def test_reference_units_are_explicit_while_loading_summary_tracks_display_units(self):
        self.browser.search.setText("Gerber")
        text = self.browser.details.toPlainText()
        self.assertIn("0.15 kip", text)
        self.assertIn("kN/m", text)
        self.assertIn("0%–100% of span", text)
        self.assertIn("Service: 1 × Case 1", text)
        self.browser.search.setText("cantilever mixed")
        self.assertIn("-60°", self.browser.details.toPlainText())

    def test_open_routes_through_existing_unsaved_prompt_and_respects_cancellation(self):
        for approved in (False, True):
            before = state(self.window)
            with patch("pynitegui.qt.example_browser.ExampleBrowser.exec", return_value=QDialog.DialogCode.Accepted), \
                 patch.object(self.window, "confirm_discard", return_value=approved) as confirm:
                self.window.browse_examples_action.trigger()
            confirm.assert_called_once()
            if approved:
                self.assertEqual(self.window.project.to_dict(), example_project("simple_beam", "si").to_dict())
                self.assertIsNone(self.window.path)
                self.assertNotEqual(self.window.saved, self.window.project.to_dict())
            else:
                self.assertEqual(state(self.window), before)

    def test_cancel_and_mcp_mode_never_replace_the_model(self):
        before = state(self.window)
        with patch("pynitegui.qt.example_browser.ExampleBrowser.exec", return_value=QDialog.DialogCode.Rejected), \
             patch.object(self.window, "confirm_discard") as confirm:
            self.window.browse_examples()
        confirm.assert_not_called()
        self.assertEqual(state(self.window), before)
        self.window.mcp_mode = True
        with patch("pynitegui.qt.example_browser.ExampleBrowser.exec") as execute:
            self.window.browse_examples()
        execute.assert_not_called()
        self.window.mcp_mode = False

    def test_native_preview_renders_in_both_themes_including_slabs_and_hinges(self):
        self.browser.show()
        for theme in ("light", "dark"):
            configure_theme(self.app, theme)
            for query in ("Gerber", "three-storey", "space truss"):
                self.browser.search.setText(query)
                self.app.processEvents()
                self.assertIsNotNone(self.browser.preview.project)
                self.assertFalse(self.browser.preview.grab().isNull())
        self.assertEqual(self.browser.unit_system, "si")
