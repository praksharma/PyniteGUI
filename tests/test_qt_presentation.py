"""Display conventions and selected model/diagram reports preserve snapshots."""
import contextlib
from dataclasses import replace
import io
import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import numpy as np
from matplotlib.figure import Figure
from PySide6.QtCore import QUrl
from PySide6.QtGui import QTextDocument
from PySide6.QtWidgets import QApplication

from pynitegui.qt.analysis import analyze
from pynitegui.qt.app import MainWindow
from pynitegui.qt.diagrams import DiagramDialog, draw_structure, member_values
from pynitegui.qt.examples import example_project
from pynitegui.qt.reports import ReportOptions, ReportOptionsDialog, model_definition_tables, report_document, report_html
from pynitegui.qt.theme import configure_theme


class PresentationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.project = example_project("portal")
        with contextlib.redirect_stdout(io.StringIO()):
            self.result = analyze(self.project)

    def test_side_changes_placement_without_changing_values(self):
        first, second = Figure(), Figure()
        a, b = first.add_subplot(), second.add_subplot()
        left = draw_structure(a, self.project, self.result, "moment")
        right = draw_structure(b, self.project, self.result, "moment", side=-1)
        for name in left:
            np.testing.assert_array_equal(left[name]["values"], right[name]["values"])
        np.testing.assert_allclose(a.lines[1].get_xydata() + b.lines[1].get_xydata(), 2 * a.lines[0].get_xydata())
        self.assertFalse(np.array_equal(a.lines[1].get_xydata(), b.lines[1].get_xydata()))
        first.clear()
        second.clear()

    def test_reversed_sign_is_explicit_and_does_not_mutate_results(self):
        before = member_values(self.project, self.result, "M2", 100)
        first, second = Figure(), Figure()
        normal = draw_structure(first.add_subplot(), self.project, self.result, "axial")
        self.assertIn("+ compression", first.axes[0].get_title())
        reversed_values = draw_structure(second.add_subplot(), self.project, self.result, "axial", sign=-1)
        for name in normal:
            np.testing.assert_allclose(normal[name]["values"], -reversed_values[name]["values"])
        self.assertIn("+ tension", second.axes[0].get_title())
        self.assertEqual(before, member_values(self.project, self.result, "M2", 100))
        first.clear()
        second.clear()

    def test_dialog_controls_survive_combination_and_unit_changes(self):
        dialog = DiagramDialog(None, self.project, self.result)
        dialog.diagram_side.setCurrentIndex(1)
        dialog.reverse_sign.setChecked(True)
        dialog.set_unit_system("si")
        dialog.select_combination("Service")
        self.assertEqual(dialog.diagram_side.currentData(), -1)
        self.assertTrue(dialog.reverse_sign.isChecked())
        self.assertIn("reversed display sign", dialog.structure_figure.axes[0].get_title())
        self.assertEqual(dialog.inspection_values.item(0, 0).text(),
                         f"{dialog.project.units.to_display(member_values(self.project, self.result, 'M1', 0)[0], 'force'):.6g}")
        dialog.close()
        self.app.processEvents()

    def test_model_definitions_are_unit_aware_and_complete(self):
        self.project.unit_system = "si"
        tables = {title: (headers, rows) for title, headers, rows in model_definition_tables(self.project)}
        self.assertIn("Nodes and Supports", tables)
        self.assertIn("Members and Assignments", tables)
        self.assertIn("Materials", tables)
        self.assertIn("Sections", tables)
        self.assertIn("X (m)", tables["Nodes and Supports"][0])
        self.assertAlmostEqual(tables["Nodes and Supports"][1][1][2], 144 * 0.0254)
        self.assertIn("Weight (kN/m3)", tables["Materials"][0])
        loads = tables["Manual Loads (Unfactored)"][1]
        self.assertTrue(any(row[6] == "kN/m" for row in loads))
        self.assertTrue(any(row[6] == "kN" for row in loads))

    def test_custom_names_and_provenance_are_escaped(self):
        material = replace(self.project.materials["Steel_A992"], name='<Steel & "grade">')
        self.project.set_material(material, "Steel_A992")
        with contextlib.redirect_stdout(io.StringIO()):
            self.result = analyze(self.project)
        html = report_html(self.project, self.result, '<unsafe & "source">')
        self.assertIn("&lt;unsafe &amp; &quot;source&quot;&gt;", html)
        self.assertIn("&lt;Steel &amp; &quot;grade&quot;&gt;", html)
        self.assertIn("Model Definitions", html)
        self.assertIn("Generated Self-Weight (Unfactored)", html)
        self.assertNotIn("<img", html)

    def test_selected_sections_and_embedded_light_diagrams(self):
        before = self.project.to_dict()
        configure_theme(self.app, "dark")
        options = ReportOptions(model=False, nodes=False, members=False, diagrams=("moment",), side=-1, sign=-1)
        html = report_html(self.project, self.result, options=options)
        self.assertIn("data:image/png;base64,", html)
        self.assertNotIn("Model Definitions", html)
        self.assertNotIn("Node Displacements and Support Reactions", html)
        self.assertIn("opposite side", html)
        self.assertIn("reversed", html)
        doc = report_document(self.project, self.result, options=options)
        image = doc.resource(QTextDocument.ResourceType.ImageResource, QUrl("pynitegui-report:moment"))
        self.assertFalse(image.isNull())
        self.assertGreater(image.pixelColor(0, 0).lightness(), 200)
        self.assertEqual(self.project.to_dict(), before)
        configure_theme(self.app, "light")

    def test_stale_diagram_only_report_is_rejected(self):
        self.project.nodes["N2"].x += 1
        with self.assertRaisesRegex(ValueError, "does not match"):
            report_html(self.project, self.result, options=ReportOptions(model=False, nodes=False, members=False, diagrams=("axial",)))

    def test_report_options_reject_empty_invalid_and_duplicate_choices(self):
        for options in (ReportOptions(False, False, False), ReportOptions(diagrams=("unknown",)),
                        ReportOptions(diagrams=("moment", "moment")), ReportOptions(side=0),
                        ReportOptions(sign=True), ReportOptions(amplitude=float("nan"))):
            with self.assertRaises(ValueError):
                options.validate()
        dialog = ReportOptionsDialog(None)
        for widget in (*dialog.sections.values(), *dialog.diagrams.values()):
            widget.setChecked(False)
        with patch("pynitegui.qt.reports.QMessageBox.warning") as warning:
            dialog.accept()
        warning.assert_called_once()
        self.assertIsNone(dialog.definition)
        dialog.reject()
        dialog.deleteLater()

    def test_report_options_inherit_snapshot_display_controls(self):
        parent = DiagramDialog(None, self.project, self.result)
        parent.quantity.setCurrentIndex(2)
        parent.diagram_side.setCurrentIndex(1)
        parent.reverse_sign.setChecked(True)
        parent.amplitude.setValue(30)
        dialog = ReportOptionsDialog(parent)
        dialog.accept()
        self.assertEqual(dialog.definition.diagrams, ("axial",))
        self.assertEqual((dialog.definition.side, dialog.definition.sign, dialog.definition.amplitude), (-1, -1, 30))
        dialog.close()
        parent.close()
        self.app.processEvents()

    def test_cancel_report_options_never_opens_print_preview(self):
        window = MainWindow()
        window.load_project(self.project)
        window.analysis_revision = window.revision
        window.analysis_finished(self.result, None)
        with patch("pynitegui.qt.reports.ReportOptionsDialog") as options, \
                patch("pynitegui.qt.reports.QPrintPreviewDialog") as preview:
            options.return_value.exec.return_value = 0
            window.export_menu.print_report()
            preview.assert_not_called()
        window.saved = window.project.to_dict()
        window.close()
        window.deleteLater()
        self.app.processEvents()
