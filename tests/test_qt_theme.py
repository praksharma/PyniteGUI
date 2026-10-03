"""Live and persistent themes leave project/result/inspection state unchanged."""
import contextlib
import io
import os
from pathlib import Path
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from matplotlib.colors import to_hex
from PySide6.QtCore import QSettings
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QApplication, QDoubleSpinBox, QGraphicsSimpleTextItem, QPushButton
from pynitegui.qt.analysis import analyze
from pynitegui.qt.app import MainWindow
from pynitegui.qt.diagrams import DiagramDialog
from pynitegui.qt.examples import example_project
from pynitegui.qt.reports import report_html
from pynitegui.qt.theme import colors, configure_theme, theme_name, THEMES


class ThemeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        configure_theme(self.app)
        self.window = MainWindow()
        self.window.load_project(example_project("portal"))

    def tearDown(self):
        self.window.saved = self.window.project.to_dict()
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()
        configure_theme(self.app)

    def test_live_canvas_palette_and_model_result_preservation(self):
        with contextlib.redirect_stdout(io.StringIO()):
            result = analyze(self.window.project)
        self.window.analysis_revision = self.window.revision
        self.window.analysis_finished(result, "")
        self.window.select(("nodes", "N1"))
        pending = self.window.inspector.findChild(QDoubleSpinBox)
        pending.setValue(17)
        before = (self.window.project.to_dict(), self.window.revision, self.window.undo.count(), self.window.view.transform())
        retained = self.window.result
        for name in ("dark", "light", "dark"):
            self.window.theme_actions[name].trigger()
            self.assertEqual(theme_name(), name)
            self.assertTrue(self.window.theme_actions[name].isChecked())
            self.assertEqual(self.window.view.backgroundBrush().color().name(), colors()["canvas"])
            self.assertEqual(self.app.palette().color(QPalette.ColorRole.Text).name(), colors()["text"])
            self.assertEqual((self.window.project.to_dict(), self.window.revision, self.window.undo.count(), self.window.view.transform()), before)
            self.assertIs(self.window.result, retained)
            self.assertIs(self.window.inspector.findChild(QDoubleSpinBox), pending)
            self.assertEqual(pending.value(), 17)
            self.assertTrue(self.window.export_menu.isEnabled())
            labels = [item for item in self.window.view.scene().items() if isinstance(item, QGraphicsSimpleTextItem)]
            self.assertTrue(any(item.brush().color().name() == colors()["load"] for item in labels))

    def test_open_diagrams_recolor_in_place_preserving_probes_zoom_and_report(self):
        with contextlib.redirect_stdout(io.StringIO()):
            result = analyze(self.window.project)
        dialog = DiagramDialog(self.window, self.window.project, result)
        dialog.distance.setValue(50)
        ax = dialog.member_figure.axes[1]
        ax.set_xlim(20, 80)
        probe = dialog.probes[1]
        snapshot = result.snapshot_id
        report = report_html(self.window.project, result)
        try:
            for name in ("dark", "light", "dark"):
                self.window.set_theme(name)
                self.assertIs(dialog.member_figure.axes[1], ax)
                self.assertIs(dialog.probes[1], probe)
                self.assertEqual(ax.get_xlim(), (20, 80))
                self.assertEqual(dialog.inspection_x, 50)
                self.assertEqual(dialog.result.snapshot_id, snapshot)
                self.assertEqual(to_hex(ax.get_facecolor()), colors()["canvas"])
                self.assertEqual(to_hex(ax.lines[0].get_color()), colors()["shear"])
                self.assertEqual(to_hex(dialog.structure_figure.axes[0].lines[0].get_color()), colors()["member"])
                self.assertEqual(report_html(self.window.project, result), report)
        finally:
            dialog.close()
            self.app.processEvents()

    def test_settings_restore_and_invalid_preference_falls_back(self):
        with tempfile.TemporaryDirectory() as directory:
            settings = QSettings(str(Path(directory) / "preferences.ini"), QSettings.Format.IniFormat)
            window = MainWindow(settings=settings)
            window.set_theme("dark")
            self.assertEqual(settings.value("theme"), "dark")
            window.close()
            window.deleteLater()
            self.app.processEvents()
            configure_theme(self.app, "light")
            restored = MainWindow(settings=settings)
            self.assertEqual(theme_name(), "dark")
            self.assertTrue(restored.theme_actions["dark"].isChecked())
            restored.close()
            restored.deleteLater()
            self.app.processEvents()
            settings.setValue("theme", "unsupported")
            restored = MainWindow(settings=settings)
            self.assertEqual(theme_name(), "light")
            restored.close()
            restored.deleteLater()
            self.app.processEvents()

    def test_multiple_editors_sync_theme_actions(self):
        other = MainWindow()
        try:
            self.window.set_theme("dark")
            self.assertTrue(other.theme_actions["dark"].isChecked())
            self.assertEqual(other.view.backgroundBrush().color().name(), colors()["canvas"])
        finally:
            other.close()
            other.deleteLater()
            self.app.processEvents()

    def test_dark_toolbar_icons_and_compact_inspector_scrolling(self):
        self.window.set_theme("dark")
        image = self.window.analyze_action.icon().pixmap(24, 24).toImage()
        visible = [image.pixelColor(x, y) for x in range(image.width()) for y in range(image.height())
                   if image.pixelColor(x, y).alpha() > 128]
        self.assertTrue(visible)
        self.assertGreater(min(color.lightness() for color in visible), 200)
        self.window.resize(820, 560)
        self.window.select(("loads", "L1"))
        self.window.results_dock.show()
        self.window.show()
        self.app.processEvents()
        scroll = self.window.inspector_scroll
        self.assertGreater(scroll.verticalScrollBar().maximum(), 0)
        apply = next(button for button in self.window.inspector.findChildren(QPushButton) if button.text() == "Apply")
        scroll.ensureWidgetVisible(apply)
        self.assertGreater(scroll.verticalScrollBar().value(), 0)

    def test_dark_text_and_engineering_colors_have_readable_contrast(self):
        def luminance(hex_color):
            rgb = [int(hex_color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
            values = [value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055)**2.4 for value in rgb]
            return sum(a * b for a, b in zip(values, (0.2126, 0.7152, 0.0722)))
        c = THEMES["dark"]
        for key in ("text", "label", "load", "support", "member", "axial", "shear", "moment"):
            contrast = (luminance(c[key]) + 0.05) / (luminance(c["canvas"]) + 0.05)
            self.assertGreater(contrast, 4.5, key)
