"""Envelope reports and screen-space label placement preserve analytical values."""
import contextlib
import io
import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import numpy as np
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
from matplotlib.text import Text
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from pynitegui.qt.analysis import analyze
from pynitegui.qt.diagram_labels import DiagramLabel, add_diagram_label
from pynitegui.qt.diagrams import DiagramDialog, draw_structure
from pynitegui.qt.examples import example_project
from pynitegui.qt.reports import ReportOptions, ReportOptionsDialog, report_document, report_html
from pynitegui.qt.theme import LIGHT


class ResultPolishTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.project = example_project("simple_beam")
        cls.project.set_combination("Double", {"Case 1": 2})
        cls.project.set_combination('Reverse <&"case">', {"Case 1": -1})
        with contextlib.redirect_stdout(io.StringIO()):
            cls.result = analyze(cls.project)

    def assert_label_layout(self, figure):
        renderer = figure.canvas.get_renderer()
        boxes = []
        for ax in figure.axes:
            for label in ax.texts:
                if isinstance(label, DiagramLabel) and label.placed:
                    box = Text.get_window_extent(label, renderer)
                    self.assertTrue(ax.bbox.contains(box.x0, box.y0))
                    self.assertTrue(ax.bbox.contains(box.x1, box.y1))
                    self.assertFalse(any(box.overlaps(previous) for previous in boxes))
                    boxes.append(box)
        self.assertTrue(boxes)

    def test_dense_labels_do_not_overlap_and_reappear_after_resize(self):
        figure = Figure(figsize=(1.8, 1.4))
        canvas = FigureCanvasAgg(figure)
        ax = figure.add_subplot()
        ax.set(xlim=(-1, 1), ylim=(-1, 1))
        labels = [add_diagram_label(ax, f"Value {index}", (0, 0), LIGHT["moment"], LIGHT["canvas"]) for index in range(30)]
        canvas.draw()
        self.assert_label_layout(figure)
        small = sum(label.placed for label in labels)
        self.assertLess(small, len(labels))
        figure.set_size_inches(8, 5)
        canvas.draw()
        self.assert_label_layout(figure)
        self.assertGreater(sum(label.placed for label in labels), small)
        before = [(label.placed, label.get_position()) for label in labels]
        canvas.draw()
        self.assertEqual(before, [(label.placed, label.get_position()) for label in labels])
        for dpi in (72, 160, 300):
            figure.set_dpi(dpi)
            canvas.draw()
            self.assert_label_layout(figure)
        figure.clear()

    def test_member_ids_get_first_placement_and_offscreen_labels_are_skipped(self):
        figure = Figure(figsize=(4, 3))
        canvas = FigureCanvasAgg(figure)
        ax = figure.add_subplot()
        ax.set(xlim=(-1, 1), ylim=(-1, 1))
        value = add_diagram_label(ax, "1050", (0, 0), LIGHT["moment"], LIGHT["canvas"])
        member = add_diagram_label(ax, "M1", (0, 0), LIGHT["member"], LIGHT["canvas"], member=True)
        outside = add_diagram_label(ax, "Outside", (20, 0), LIGHT["moment"], LIGHT["canvas"])
        canvas.draw()
        self.assertTrue(member.placed)
        self.assertTrue(value.placed)
        self.assertFalse(outside.placed)
        self.assert_label_layout(figure)
        figure.clear()

    def test_real_diagram_geometry_is_unchanged_across_redraws(self):
        project = example_project("multistorey")
        with contextlib.redirect_stdout(io.StringIO()):
            result = analyze(project)
        before = project.to_dict()
        figure = Figure(figsize=(6, 4), layout="constrained")
        canvas = FigureCanvasAgg(figure)
        ax = figure.add_subplot()
        data = draw_structure(ax, project, result, "moment")
        lines = [line.get_xydata().copy() for line in ax.lines]
        canvas.draw()
        self.assert_label_layout(figure)
        figure.set_size_inches(9, 6)
        canvas.draw()
        self.assert_label_layout(figure)
        for line, expected in zip(ax.lines, lines):
            np.testing.assert_array_equal(line.get_xydata(), expected)
        self.assertEqual(project.to_dict(), before)
        self.assertTrue(all(len(row["values"]) >= 81 for row in data.values()))
        figure.clear()

    def test_envelope_only_report_has_exact_values_factors_and_escaping(self):
        options = ReportOptions(False, False, False, envelope_combinations=("Double", 'Reverse <&"case">'))
        project = self.project.clone()
        project.unit_system = "si"
        html = report_html(project, self.result, '<source & "file">', options)
        self.assertIn("Selected-Combination Envelopes", html)
        self.assertIn("Node Envelopes", html)
        self.assertIn("Member Envelopes", html)
        self.assertIn("Mz (kN-m)", html)
        self.assertIn("Minimum combination", html)
        self.assertIn("Reverse &lt;&amp;&quot;case&quot;&gt;", html)
        self.assertIn("Case 1: -1", html)
        self.assertNotIn("Model Definitions", html)
        self.assertNotIn("Member End Values", html)
        self.assertIn(f"{project.units.to_display(-2100, 'moment'):.6g}", html)
        text = report_document(project, self.result, options=options).toPlainText()
        truss_document = report_document(example_project("truss"), self.truss_result(),
                                        options=ReportOptions(False, False, False, envelope_combinations=("Service",)))
        self.assertIn("n/a", truss_document.toPlainText())
        self.assertIn("independently of the single-combination", text)

    def truss_result(self):
        with contextlib.redirect_stdout(io.StringIO()):
            return analyze(example_project("truss"))

    def test_envelope_subset_and_display_sign_do_not_change_bounds(self):
        options = ReportOptions(False, False, False, envelope_combinations=("Double",))
        normal = report_html(self.project, self.result, options=options)
        reversed_options = ReportOptions(False, False, False, side=-1, sign=-1, envelope_combinations=("Double",))
        self.assertEqual(normal, report_html(self.project, self.result, options=reversed_options))
        self.assertNotIn("Reverse", normal)
        self.assertNotIn("Service", normal)
        self.assertIn("Envelope combinations:", normal)
        self.assertIn(self.result.snapshot_id, normal)

    def test_invalid_unknown_and_stale_envelope_reports_are_rejected(self):
        for names in (["Service"], ("",), ("Service", "Service"), (None,)):
            with self.assertRaises(ValueError):
                ReportOptions(envelope_combinations=names).validate()
        options = ReportOptions(False, False, False, envelope_combinations=("unknown",))
        with self.assertRaises(ValueError):
            report_html(self.project, self.result, options=options)
        project = self.project.clone()
        project.nodes["N2"].x += 1
        with self.assertRaisesRegex(ValueError, "does not match"):
            report_document(project, self.result, options=ReportOptions(False, False, False, envelope_combinations=("Double",)))

    def test_envelope_print_defaults_inherit_selection_not_main_combination(self):
        parent = DiagramDialog(None, self.project, self.result)
        parent.envelopes.combinations.item(0).setCheckState(Qt.CheckState.Unchecked)
        parent.envelopes.combinations.item(2).setCheckState(Qt.CheckState.Unchecked)
        dialog = ReportOptionsDialog(parent.envelopes)
        dialog.accept()
        options = dialog.definition
        self.assertEqual(options.envelope_combinations, ("Double",))
        self.assertEqual((options.model, options.nodes, options.members, options.diagrams), (False, False, False, ()))
        dialog.close()
        parent.tabs.setCurrentWidget(parent.envelopes)
        dialog = ReportOptionsDialog(parent)
        self.assertTrue(dialog.include_envelopes.isChecked())
        dialog.accept()
        self.assertEqual(dialog.definition.envelope_combinations, ("Double",))
        dialog.close()
        parent.close()
        self.app.processEvents()

    def test_empty_checked_envelope_selection_does_not_open_preview(self):
        parent = DiagramDialog(None, self.project, self.result)
        dialog = ReportOptionsDialog(parent.envelopes)
        for index in range(dialog.envelope_combinations.count()):
            dialog.envelope_combinations.item(index).setCheckState(Qt.CheckState.Unchecked)
        with patch("pynitegui.qt.reports.QMessageBox.warning") as warning:
            dialog.accept()
        warning.assert_called_once()
        self.assertIsNone(dialog.definition)
        dialog.reject()
        parent.close()
        self.app.processEvents()

    def test_envelope_print_action_uses_snapshot_menu_and_cancel_is_safe(self):
        parent = DiagramDialog(None, self.project, self.result)
        widget = parent.envelopes
        self.assertTrue(any("Print envelopes" in action.text() for action in widget.export_button.menu().actions()))
        with patch("pynitegui.qt.reports.ReportOptionsDialog") as choices, \
                patch("pynitegui.qt.reports.QPrintPreviewDialog") as preview:
            choices.return_value.exec.return_value = 0
            widget.print_report()
            preview.assert_not_called()
            choices.assert_called_once_with(widget)
        parent.close()
        self.app.processEvents()
