"""Snapshot-based 3D report diagrams, views, physical axes and native PDF output."""
import contextlib
import io
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYNITEGUI_NO_WEBENGINE", "1")
import numpy as np
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QImage, QTextDocument
from PySide6.QtPrintSupport import QPrinter
from PySide6.QtWidgets import QApplication, QMessageBox

from pynitegui.qt.analysis import analyze
from pynitegui.qt.app import MainWindow
from pynitegui.qt.examples import example_project
from pynitegui.qt.reports import ReportOptions, ReportOptionsDialog, diagram_pages, report_document, report_html, report_images, report_printer
from pynitegui.qt.spatial_model import SpatialLoad
from pynitegui.qt.spatial_reports import TITLES, VIEWS, diagram_geometry, draw_report, projection, ribbon_polygons, samples
from pynitegui.qt.theme import configure_theme


def solve(project):
    with contextlib.redirect_stdout(io.StringIO()):
        return analyze(project)


class SpatialReportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.project = example_project("3d_cantilever")
        self.project.nodes["N2"].y, self.project.nodes["N2"].z = 50, -40
        self.project.members["M1"].roll = 32
        self.project.set_combination("Double", {"Case 1": 2})
        self.result = solve(self.project)

    def test_projection_basis_and_shared_rolled_offsets(self):
        for view in VIEWS:
            basis = projection(view)
            np.testing.assert_allclose(basis @ basis.T, np.eye(2), atol=1e-12)
        rows = samples(self.project, self.result)
        self.assertEqual(len(rows), 1)
        for index, kind in enumerate(TITLES):
            geometry, bounds = diagram_geometry(rows, kind, 20, 120)
            _, baseline, curve, values = geometry[0]
            axis = rows[0][3][(1, 1, 2, 1, 2, 1)[index]]
            peak = max(abs(value) for value in bounds)
            factor = .2 * 120 / peak if peak else 0
            np.testing.assert_allclose(curve - baseline, values[:, None] * axis * factor, atol=1e-10)
            reversed_geometry, _ = diagram_geometry(rows, kind, 20, 120, side=-1)
            np.testing.assert_allclose(reversed_geometry[0][2] - baseline, -(curve - baseline), atol=1e-10)
            twice, _ = diagram_geometry(rows + rows, kind, 20, 120, side=-1, sign=-1)
            np.testing.assert_allclose(twice[0][2], curve, atol=1e-10)
            name, points, data, axes = rows[0]
            unequal = rows + [("Second", points + np.array([20, 0, 0]), data * 2, axes)]
            shared, _ = diagram_geometry(unequal, kind, 20, 120)
            np.testing.assert_allclose(shared[0][2] - baseline, (curve - baseline) / 2, atol=1e-10)

    def test_ribbons_split_at_zero_and_do_not_bridge_load_jumps(self):
        points = np.array([[0, 0, 0], [10, 0, 0]])
        offsets = points + np.array([[0, 2, 0], [0, -2, 0]])
        polygons = ribbon_polygons(points, offsets, np.array([2, -2]))
        self.assertEqual(len(polygons), 2)
        np.testing.assert_allclose(polygons[0][1], [5, 0, 0])
        np.testing.assert_allclose(polygons[1][0], [5, 0, 0])
        self.assertEqual(ribbon_polygons(points[[0, 0]], offsets, np.array([2, -2])), [])

    def test_each_component_view_generates_nonblank_print_friendly_images(self):
        before = self.project.to_dict()
        configure_theme(self.app, "dark")
        options = ReportOptions(False, False, False, tuple(TITLES), views=tuple(VIEWS))
        images = report_images(self.project, self.result, options)
        self.assertEqual(len(images), 24)
        for key, data in images.items():
            with self.subTest(page=key):
                image = QImage.fromData(data, "PNG")
                self.assertEqual((image.width(), image.height()), (1440, 768))
                self.assertGreater(image.pixelColor(0, 0).lightness(), 240)
                colored = sum(image.pixelColor(x, y).saturation() > 40
                              for x in range(0, image.width(), 8) for y in range(0, image.height(), 8))
                self.assertGreater(colored, 10)
        self.assertEqual(self.project.to_dict(), before)
        configure_theme(self.app, "light")

    def test_pdf_resources_metadata_views_and_retained_snapshot(self):
        self.project.unit_system = "si"
        result = self.result.for_combination("Double")
        options = ReportOptions(False, False, False, ("moment_y", "moment_z"), views=("isometric", "front"), sign=-1)
        doc = report_document(self.project, result, '<source & "model">', options)
        text = doc.toPlainText()
        for value in ("Bending My", "Bending Mz", "Front XY", "Isometric", "Double", "reversed", result.snapshot_id, "SI", '<source & "model">'):
            self.assertIn(value, text)
        for key, title in diagram_pages(self.project, options):
            image = doc.resource(QTextDocument.ResourceType.ImageResource, QUrl("pynitegui-report:" + key))
            self.assertFalse(image.isNull())
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "spatial.pdf"
            printer = report_printer()
            printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
            printer.setOutputFileName(str(path))
            doc.print_(printer)
            self.assertTrue(path.read_bytes().startswith(b"%PDF"))
            self.assertGreater(path.stat().st_size, 20000)
            if shutil.which("pdfinfo"):
                info = subprocess.check_output(["pdfinfo", str(path)], text=True, env={**os.environ, "LC_ALL": "C"})
                pages = next(int(line.split(":", 1)[1]) for line in info.splitlines() if line.startswith("Pages:"))
                self.assertEqual(pages, 5, "Each chart must share its page with its title and metadata")
        self.project.nodes["N2"].z += 1
        for render in (report_images, report_document):
            with self.assertRaisesRegex(ValueError, "snapshot"):
                render(self.project, result, options=options)

    def test_visibility_zero_forces_edge_on_loads_trusses_and_unit_labels(self):
        for key in ("3d_tripod", "3d_space_frame"):
            project = example_project(key, "si")
            result = solve(project)
            rows = samples(project, result)
            figure = Figure(figsize=(9, 4.8))
            FigureCanvasAgg(figure)
            ax = figure.add_subplot(111)
            options = ReportOptions(diagrams=("torque",), supports=False, loads=False)
            draw_report(ax, project, result, rows, "torque", "front", options)
            figure.canvas.draw()
            labels = [text.get_text() for text in ax.texts]
            self.assertFalse(any("fixed " in text or "spring " in text or "L1:" in text for text in labels))
            self.assertTrue(any("kN-m" in text for text in labels))
            self.assertTrue(all(np.isfinite(line.get_xydata()).all() for line in ax.lines))
            figure.clear()
        project = self.project.clone()
        project.loads["normal"] = SpatialLoad("normal", "N2", "FZ", 1)
        project.loads["varying"] = SpatialLoad("varying", "M1", "Fy", -.1, .2, "distributed", .1, .8)
        result = solve(project)
        figure = Figure()
        FigureCanvasAgg(figure)
        ax = figure.add_subplot(111)
        draw_report(ax, project, result, samples(project, result), "shear_y", "front", ReportOptions())
        figure.canvas.draw()
        labels = [text.get_text() for text in ax.texts]
        self.assertTrue(any("normal:" in text for text in labels))
        self.assertTrue(any("varying:" in text for text in labels))
        figure.clear()

    def test_invalid_views_components_and_dimension_choices(self):
        for views in ((), ("front", "front"), ("orbit",), ["front"], (None,)):
            with self.assertRaises(ValueError):
                ReportOptions(diagrams=("axial",), views=views).validate()
        with self.assertRaisesRegex(ValueError, "explicit 3D"):
            report_html(self.project, self.result, options=ReportOptions(diagrams=("moment",)))
        planar = example_project("cantilever")
        with self.assertRaisesRegex(ValueError, "3D project"):
            report_images(planar, solve(planar), ReportOptions(diagrams=("moment_z",)))

    def test_editor_options_and_cancelled_empty_view_selection(self):
        window = MainWindow()
        try:
            window.load_project(self.project)
            window.result = self.result
            window.view.diagram.setCurrentIndex(window.view.diagram.findData("moment_y"))
            choices = ReportOptionsDialog(window)
            self.assertEqual(set(choices.diagrams), set(TITLES))
            choices.views.item(1).setCheckState(Qt.CheckState.Checked)
            choices.accept()
            self.assertEqual(choices.definition.diagrams, ("moment_y",))
            self.assertEqual(choices.definition.views, ("isometric", "front"))
            choices.close()
            choices = ReportOptionsDialog(window)
            for index in range(choices.views.count()):
                choices.views.item(index).setCheckState(Qt.CheckState.Unchecked)
            with patch.object(QMessageBox, "warning") as warning:
                choices.accept()
            warning.assert_called_once()
            self.assertIsNone(choices.definition)
            choices.reject()
        finally:
            window.saved = window.project.to_dict()
            window.close()
            window.deleteLater()
            self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
