"""Native help/navigation and layout recovery leave engineering work untouched."""
import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYNITEGUI_NO_WEBENGINE", "1")
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QKeySequence, QPalette
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialogButtonBox, QDoubleSpinBox, QPushButton, QToolBar

from pynitegui import __version__
from pynitegui.qt.app import MainWindow
from pynitegui.qt.help_menu import (AboutDialog, DOCS_URL, LINKS, ShortcutsDialog, copy_support_information,
                                    open_link, shortcut_rows, show_dialog, support_information)
from pynitegui.qt.theme import configure_theme


class HelpQualityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = MainWindow()
        self.window.show()
        self.app.processEvents()

    def tearDown(self):
        self.window.saved = self.window.project.to_dict()
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()
        configure_theme(self.app, "light")

    def snapshot(self):
        window = self.window
        return (window.project.to_dict(), window.saved, window.path, window.revision,
                window.undo.count(), window.selected, window.result)

    def test_menu_order_and_help_links_open_only_on_request(self):
        before = self.snapshot()
        self.assertEqual([action.text().replace("&", "") for action in self.window.menuBar().actions()],
                         ["File", "Edit", "View", "Tools", "Help"])
        actions = {action.text(): action for action in self.window.help_menu.actions()}
        with patch("pynitegui.qt.help_menu.QDesktopServices.openUrl", return_value=True) as browser:
            self.app.processEvents()
            browser.assert_not_called()
            for label, key in (("Documentation", "documentation"), ("Getting Started", "getting_started"),
                               ("Report an Issue", "issues")):
                actions[label].trigger()
                self.assertEqual(browser.call_args.args[0].toString(), LINKS[key])
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(actions["About PyniteGUI…"].menuRole(), QAction.MenuRole.AboutRole)

    def test_f1_uses_documentation_website(self):
        self.window.activateWindow()
        self.window.view.setFocus()
        self.app.processEvents()
        with patch("pynitegui.qt.help_menu.QDesktopServices.openUrl", return_value=True) as browser:
            QTest.keyClick(self.window.view, Qt.Key.Key_F1)
            self.app.processEvents()
        self.assertEqual(browser.call_count, 1)
        self.assertEqual(browser.call_args.args[0].toString(), DOCS_URL)

    def test_browser_failure_displays_a_copyable_address(self):
        with patch("pynitegui.qt.help_menu.QDesktopServices.openUrl", return_value=False), \
                patch("pynitegui.qt.help_menu.QMessageBox.warning") as warning:
            self.assertFalse(open_link(self.window, "documentation"))
        self.assertIn(DOCS_URL, warning.call_args.args[2])
        with patch("pynitegui.qt.help_menu.QDesktopServices.openUrl", side_effect=OSError("Unavailable")), \
                patch("pynitegui.qt.help_menu.QMessageBox.warning") as warning:
            self.assertFalse(open_link(self.window, "getting_started"))
        self.assertIn(LINKS["getting_started"], warning.call_args.args[2])

    def test_about_is_reused_and_preserves_unapplied_inspector_inputs(self):
        self.window.example()
        self.window.select(("nodes", "N1"))
        field = self.window.inspector.findChild(QDoubleSpinBox)
        field.setValue(17.)
        before = self.snapshot()
        first = show_dialog(self.window, "about_dialog", AboutDialog)
        self.assertIn(__version__, first.version_label.text())
        first.close()
        second = show_dialog(self.window, "about_dialog", AboutDialog)
        self.assertIs(first, second)
        self.assertFalse(second.isModal())
        buttons = {button.text(): button for button in second.findChildren(QPushButton)}
        with patch("pynitegui.qt.help_menu.QDesktopServices.openUrl", return_value=True) as browser:
            buttons["Source Code"].click()
        self.assertEqual(browser.call_args.args[0].toString(), LINKS["source"])
        buttons["Copy Version Details"].click()
        self.assertEqual(self.app.clipboard().text(), support_information())
        self.assertEqual(self.snapshot(), before)
        self.assertIs(self.window.inspector.findChild(QDoubleSpinBox), field)
        self.assertEqual(field.value(), 17.)
        second.close()

    def test_version_details_and_missing_optional_distribution(self):
        before = self.snapshot()
        copy_support_information(self.window)
        text = self.app.clipboard().text()
        for value in (f"PyniteGUI {__version__}", "Python:", "Qt:", "PyniteFEA:", "System:"):
            self.assertIn(value, text)
        self.assertEqual(self.snapshot(), before)
        from importlib.metadata import PackageNotFoundError
        with patch("pynitegui.qt.help_menu.version", side_effect=PackageNotFoundError()):
            self.assertIn("PyniteFEA: Unavailable", support_information())

    def test_shortcut_reference_tracks_actual_actions_and_filters(self):
        self.window.example()
        self.window.edit("Move node", lambda project: setattr(project.nodes["N1"], "x", 12.))
        before = self.snapshot()
        rows = dict(shortcut_rows(self.window))
        self.assertIn("Undo", rows)
        self.assertNotIn("Undo Move node", rows)
        self.assertEqual(rows["Analyze"], QKeySequence("F5").toString(QKeySequence.SequenceFormat.NativeText))
        dialog = show_dialog(self.window, "shortcuts_dialog", ShortcutsDialog)
        dialog.search.setText("analyze")
        visible = [dialog.table.item(row, 0).text() for row in range(dialog.table.rowCount()) if not dialog.table.isRowHidden(row)]
        self.assertEqual(visible, ["Analyze"])
        dialog.search.setText("missing-command")
        self.assertFalse(dialog.empty.isHidden())
        dialog.search.clear()
        self.assertTrue(dialog.empty.isHidden())
        dialog.close()
        self.window.action("Extra test command", lambda: None, "Ctrl+Alt+T")
        self.assertIs(show_dialog(self.window, "shortcuts_dialog", ShortcutsDialog), dialog)
        self.assertIn("Extra test command", dict(shortcut_rows(self.window)))
        self.assertEqual(self.snapshot(), before)
        dialog.close()

    def test_restore_layout_recovers_panels_and_toolbars_without_changing_drafts(self):
        self.window.example()
        self.window.select(("nodes", "N1"))
        field = self.window.inspector.findChild(QDoubleSpinBox)
        field.setValue(17.)
        before = self.snapshot()
        self.window.structure_dock.hide()
        self.window.properties_dock.setFloating(True)
        self.window.results_dock.show()
        toolbar = self.window.findChild(QToolBar, "toolbar_file")
        self.window.addToolBar(Qt.ToolBarArea.BottomToolBarArea, toolbar)
        toolbar.hide()
        self.window.restore_layout_action.trigger()
        self.app.processEvents()
        self.assertFalse(self.window.structure_dock.isHidden())
        self.assertFalse(self.window.properties_dock.isFloating())
        self.assertEqual(self.window.dockWidgetArea(self.window.properties_dock), Qt.DockWidgetArea.RightDockWidgetArea)
        self.assertTrue(self.window.results_dock.isHidden())
        self.assertEqual(self.window.toolBarArea(toolbar), Qt.ToolBarArea.TopToolBarArea)
        self.assertFalse(toolbar.isHidden())
        self.assertEqual(self.snapshot(), before)
        self.assertIs(self.window.inspector.findChild(QDoubleSpinBox), field)
        self.assertEqual(field.value(), 17.)

    def test_restore_layout_keeps_available_results_and_findings_accessible(self):
        # Layout recovery needs only the presence of a result; it never queries
        # or recomputes the solver payload.
        self.window.result = sentinel = object()
        self.window.model_findings.show_findings(self.window.project, ["Review supports"], "Model check")
        self.window.results_dock.hide()
        self.window.findings_dock.hide()
        self.window.restore_default_layout()
        self.assertFalse(self.window.results_dock.isHidden())
        self.assertFalse(self.window.findings_dock.isHidden())
        self.assertIs(self.window.result, sentinel)
        self.window.result = None

    def test_help_dialogs_follow_light_and_dark_themes_at_minimum_window_size(self):
        self.window.resize(820, 560)
        for theme in ("light", "dark"):
            configure_theme(self.app, theme)
            about = show_dialog(self.window, "about_dialog", AboutDialog)
            shortcuts = show_dialog(self.window, "shortcuts_dialog", ShortcutsDialog)
            for dialog in (about, shortcuts):
                self.assertLessEqual(dialog.minimumSizeHint().width(), 820)
                self.assertEqual(dialog.palette().color(QPalette.ColorRole.Window), self.app.palette().color(QPalette.ColorRole.Window))
                buttons = dialog.findChild(QDialogButtonBox)
                self.assertIsNotNone(buttons.button(QDialogButtonBox.StandardButton.Close))
                dialog.close()
