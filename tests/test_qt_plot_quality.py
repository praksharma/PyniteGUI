"""Plot visibility and portable image export preserve analyzed snapshot data."""
import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYNITEGUI_NO_WEBENGINE", "1")
import numpy as np
from PIL import Image
from matplotlib.figure import Figure
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMessageBox

from pynitegui.qt.analysis import analyze
from pynitegui.qt.diagram_labels import DiagramLabel
from pynitegui.qt.diagrams import DiagramDialog, draw_structure
from pynitegui.qt.examples import example_project
from pynitegui.qt.plot_export import SnapshotPlotToolbar, export_plot
from pynitegui.qt.spatial_diagrams import SpatialDiagramDialog
from pynitegui.qt.theme import configure_theme


def solve(project):
    with contextlib.redirect_stdout(io.StringIO()):
        return analyze(project)


class PlotQualityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.project = example_project("simple_beam")
        self.result = solve(self.project)
        self.dialog = DiagramDialog(None, self.project, self.result)

    def tearDown(self):
        self.dialog.close()
        configure_theme(self.app, "light")
        self.app.processEvents()

    def test_ids_end_values_and_sampled_extrema_are_independent_and_keep_curves(self):
        figures, data = [], []
        for ids, ends, extrema in ((True, False, False), (False, True, False), (False, False, True), (False, False, False)):
            figure = Figure()
            ax = figure.add_subplot()
            data.append(draw_structure(ax, self.project, self.result, "moment", supports=False, loads=False,
                                       ids=ids, end_values=ends, extrema=extrema))
            labels = [a.get_text() for a in ax.get_children() if isinstance(a, DiagramLabel)]
            if ids:
                self.assertEqual(set(labels), {"N1", "N2", "M1"})
            elif ends:
                self.assertEqual(labels, ["0", "0"])
            elif extrema:
                self.assertIn("-1050", labels)
                self.assertIn("0", labels)
            else:
                self.assertEqual(labels, [])
            figures.append(figure)
        for changed in data[1:]:
            np.testing.assert_array_equal(changed["M1"]["values"], data[0]["M1"]["values"])
        for figure in figures:
            figure.clear()

    def test_controls_survive_units_combination_and_theme_without_editing_the_model(self):
        before = self.project.to_dict()
        inspection = self.dialog.inspection_values.item(0, 0).text()
        for control in (self.dialog.show_ids, self.dialog.show_end_values, self.dialog.show_extrema):
            control.setChecked(False)
        self.assertEqual(self.dialog.inspection_values.item(0, 0).text(), inspection)
        self.dialog.set_unit_system("si")
        self.dialog.select_combination("Service")
        configure_theme(self.app, "dark")
        self.dialog.apply_theme()
        self.assertTrue(all(not c.isChecked() for c in (self.dialog.show_ids, self.dialog.show_end_values, self.dialog.show_extrema)))
        self.assertEqual(self.project.to_dict(), before)
        self.assertEqual(self.dialog.result.snapshot_id, self.result.snapshot_id)
        self.assertIn("kN", self.dialog.structure_figure.axes[0].get_title())

    def test_png_and_svg_export_metadata_and_restore_zoom_probe_and_layout(self):
        self.dialog.source = "/private/project-folder/Frame.pynite.json"
        canvas = self.dialog.member_canvas
        canvas.draw()
        figure = canvas.figure
        ax = figure.axes[0]
        ax.set_xlim(40., 160.)
        ax.set_ylim(-3., 3.)
        before = (ax.get_xlim(), ax.get_ylim(), tuple(figure.texts), tuple(self.dialog.probes))
        layout = figure.get_layout_engine()
        metadata = canvas.toolbar.metadata()
        self.assertEqual(metadata["source"], "Frame.pynite.json")
        with tempfile.TemporaryDirectory() as directory:
            for suffix in ("png", "svg"):
                target = Path(directory)/f"plot.{suffix}"
                export_plot(target, figure, metadata)
                if suffix == "png":
                    with Image.open(target) as image:
                        self.assertGreater(image.width, 200)
                        saved = json.loads(image.info["Description"])
                else:
                    root = ET.parse(target).getroot()
                    saved = json.loads(root.find('.//{http://purl.org/dc/elements/1.1/}description').text)
                self.assertEqual(saved["snapshot_id"], self.result.snapshot_id)
                self.assertEqual(saved["combinations"], ["Service"])
                self.assertEqual(saved["model_signature"], self.result.model_signature)
                self.assertEqual(saved["analysis_method"], "Linear elastic")
                self.assertEqual(saved["member"], "M1")
                self.assertNotIn("/private/", json.dumps(saved))
                self.assertEqual((ax.get_xlim(), ax.get_ylim(), tuple(figure.texts), tuple(self.dialog.probes)), before)
                self.assertIs(figure.get_layout_engine(), layout)

    def test_failed_export_is_atomic_cleans_temporary_file_and_restores_figure(self):
        figure = self.dialog.structure_figure
        before = (tuple(figure.texts), figure.axes[0].get_xlim(), figure.axes[0].get_ylim())
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'keep.svg'
            path.write_text('previous image')
            with patch.object(figure, "savefig", side_effect=OSError("disk full")):
                with self.assertRaisesRegex(OSError, "disk full"):
                    export_plot(path, figure, self.dialog.structure_canvas.toolbar.metadata())
            self.assertEqual(path.read_text(), 'previous image')
            self.assertEqual(list(Path(directory).iterdir()), [path])
        self.assertEqual((tuple(figure.texts), figure.axes[0].get_xlim(), figure.axes[0].get_ylim()), before)

    def test_toolbar_cancel_suffix_choice_and_error_reporting(self):
        toolbar = self.dialog.structure_canvas.toolbar
        self.assertIsInstance(toolbar, SnapshotPlotToolbar)
        with patch("pynitegui.qt.plot_export.QFileDialog.getSaveFileName", return_value=("", "")), \
             patch("pynitegui.qt.plot_export.export_plot") as export:
            toolbar.save_figure()
        export.assert_not_called()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'snapshot'
            with patch("pynitegui.qt.plot_export.QFileDialog.getSaveFileName", return_value=(str(path), "SVG vector image (*.svg)")):
                toolbar.save_figure()
            self.assertTrue(path.with_suffix('.svg').is_file())
            original = path.with_suffix('.svg').read_bytes()
            with patch("pynitegui.qt.plot_export.QFileDialog.getSaveFileName", return_value=(str(path), "SVG vector image (*.svg)")), \
                 patch("pynitegui.qt.plot_export.QMessageBox.question", return_value=QMessageBox.StandardButton.No):
                toolbar.save_figure()
            self.assertEqual(path.with_suffix('.svg').read_bytes(), original)
            with patch("pynitegui.qt.plot_export.QFileDialog.getSaveFileName", return_value=(str(path.with_suffix('.jpg')), "")), \
                 patch("pynitegui.qt.plot_export.QMessageBox.warning") as warning:
                toolbar.save_figure()
            warning.assert_called_once()
            pdf = path.with_suffix('.pdf')
            with patch("pynitegui.qt.plot_export.QFileDialog.getSaveFileName", return_value=(str(pdf), "Other Matplotlib formats (*.*)")):
                toolbar.save_figure()
            self.assertTrue(pdf.read_bytes().startswith(b'%PDF'))

    def test_envelope_export_names_the_checked_combinations_not_the_single_selector(self):
        project = example_project("simple_beam")
        project.set_combination("Reverse", {"Case 1": -1.})
        dialog = DiagramDialog(None, project, solve(project))
        try:
            envelope = dialog.envelopes
            self.assertEqual(dialog.combination.currentText(), "Service")
            envelope.combinations.item(0).setCheckState(Qt.CheckState.Unchecked)
            metadata = envelope.canvas.toolbar.metadata()
            self.assertEqual(metadata["combinations"], ["Reverse"])
            self.assertEqual(dialog.combination.currentText(), "Service")
            self.assertEqual(metadata["snapshot_id"], dialog.result.snapshot_id)
        finally:
            dialog.close()

    def test_spatial_and_envelope_toolbars_use_their_own_current_context(self):
        project = example_project("3d_cantilever")
        spatial = SpatialDiagramDialog(None, project, solve(project))
        try:
            metadata = spatial.canvas.toolbar.metadata()
            self.assertEqual(metadata["plot"], "3D Member Detail")
            self.assertEqual(metadata["member"], "M1")
            envelope = self.dialog.envelopes
            self.assertEqual(envelope.canvas.toolbar.metadata()["combinations"], ["Service"])
            envelope.combinations.item(0).setCheckState(Qt.CheckState.Unchecked)
            with self.assertRaisesRegex(ValueError, "Select at least one"):
                envelope.canvas.toolbar.metadata()
        finally:
            spatial.close()
