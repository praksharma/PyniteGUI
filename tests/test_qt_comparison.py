"""Comparison curves share provenance, scale and exact one-sided probes."""
import contextlib
import io
import os
import json
from pathlib import Path
import tempfile
from xml.etree import ElementTree
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import numpy as np
from PySide6.QtWidgets import QApplication
from pynitegui.qt.analysis import analyze
from pynitegui.qt.comparison import ComparisonWidget
from pynitegui.qt.diagrams import DiagramDialog, member_values, sample_member
from pynitegui.qt.examples import example_project
from pynitegui.qt.theme import configure_theme


class ComparisonTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.project = example_project("simple_beam")
        cls.project.set_combination("Reverse double", {"Case 1": -2})
        with contextlib.redirect_stdout(io.StringIO()):
            cls.result = analyze(cls.project)

    def setUp(self):
        self.dialog = DiagramDialog(None, self.project, self.result)
        self.widget = self.dialog.comparison

    def tearDown(self):
        self.dialog.close()
        self.app.processEvents()

    def test_shared_axes_exact_probe_and_governing_signed_value(self):
        w = self.widget
        w.quantity.setCurrentIndex(w.quantity.findData("shear"))
        w.distance.setValue(210)
        for side in ("left", "right"):
            w.side.setCurrentIndex(w.side.findData(side))
            expected = [member_values(self.project, self.result.for_combination(n), "M1", 210, side)[1]
                        for n in ("Service", "Reverse double")]
            for col, value in enumerate(expected):
                self.assertAlmostEqual(float(w.inspection.item(0, col).text()), value, places=5)
            self.assertEqual(w.inspection.item(0, 2).text(), "B: Reverse double")
            self.assertAlmostEqual(float(w.inspection.item(0, 3).text()), expected[1], places=5)
        self.assertEqual(len(w.figure.axes), 1)
        curves = w.figure.axes[0].lines[:2]
        self.assertNotEqual(curves[0].get_linestyle(), curves[1].get_linestyle())
        for line, name in zip(curves, ("Service", "Reverse double")):
            np.testing.assert_allclose(line.get_ydata(), sample_member(self.project, self.result.for_combination(name), "M1")["shear"])

    def test_snapshot_independent_of_parent_selector_units_and_theme(self):
        w = self.widget
        w.distance.setValue(100)
        original = self.project.to_dict()
        self.dialog.combination.setCurrentText("Reverse double")
        self.assertEqual(w.first.currentText(), "Service")
        self.assertEqual(w.result.snapshot_id, self.result.snapshot_id)
        self.dialog.set_unit_system("si")
        self.assertAlmostEqual(w.inspection_x, 100)
        self.assertAlmostEqual(w.distance.value(), w.project.units.to_display(100, "length"))
        configure_theme(self.app, "dark")
        self.dialog.apply_theme()
        self.assertEqual(w.second.currentText(), "Reverse double")
        metadata = w.metadata()
        self.assertEqual(metadata["combinations"], ["Service", "Reverse double"])
        self.assertEqual(metadata["snapshot_id"], self.result.snapshot_id)
        self.assertEqual(self.project.to_dict(), original)
        configure_theme(self.app, "light")

    def test_same_combination_tie_and_model_mismatch_guard(self):
        w = self.widget
        w.second.setCurrentText("Service")
        self.assertEqual(w.inspection.item(0, 2).text(), "A: Service")
        w.project.nodes["N1"].x += 1
        try:
            with self.assertRaisesRegex(ValueError, "snapshot"):
                w.refresh()
        finally:
            w.project.nodes["N1"].x -= 1

    def test_image_export_identifies_both_curves_and_retains_live_limits(self):
        from pynitegui.qt.plot_export import export_plot
        w = self.widget
        w.distance.setValue(80)
        ax = w.figure.axes[0]
        ax.set_xlim(40, 120)
        before = ax.get_xlim()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "comparison.svg"
            export_plot(path, w.figure, w.metadata())
            root = ElementTree.parse(path).getroot()
            description = root.find(".//{http://purl.org/dc/elements/1.1/}description")
            metadata = json.loads(description.text)
            self.assertEqual(metadata["combinations"], ["Service", "Reverse double"])
            self.assertEqual(metadata["inspection_distance"], 80)
            self.assertEqual(metadata["snapshot_id"], self.result.snapshot_id)
        self.assertEqual(ax.get_xlim(), before)
        self.assertEqual(w.distance.value(), 80)

    def test_spatial_uses_same_component_and_exact_probe(self):
        from pynitegui.qt.spatial_results import inspect_member, sampled_member
        p = example_project("3d_cantilever")
        with contextlib.redirect_stdout(io.StringIO()):
            r = analyze(p)
        w = ComparisonWidget(None, p, r, "Untitled")
        try:
            w.quantity.setCurrentIndex(3)
            w.distance.setValue(w.distance.maximum() / 2)
            name = w.member.currentText()
            expected = inspect_member(p, r, name, w.inspection_x, "right")[3]
            self.assertAlmostEqual(float(w.inspection.item(0, 0).text()), expected, places=4)
            _, samples, _ = sampled_member(p, r, name)
            np.testing.assert_allclose(w.figure.axes[0].lines[0].get_ydata(), samples[:, 3])
        finally:
            w.close()
