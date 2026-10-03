"""Snapshot identity, safe CSV output, and native printable reports."""
import contextlib
import csv
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtPrintSupport import QPrinter
from PySide6.QtWidgets import QApplication
from pynitegui.qt.analysis import analyze, model_signature
from pynitegui.qt.app import MainWindow
from pynitegui.qt.diagrams import DiagramDialog
from pynitegui.qt.model import Load, Project
from pynitegui.qt.reports import ReportOptions, export_csv, report_document, report_html, report_printer, result_table


def beam(released=False):
    project = Project()
    project.add_member((0, 0), (120, 0))
    project.nodes["N1"].support = "pin"
    project.nodes["N2"].support = "roller"
    project.members["M1"].release_start = released
    project.members["M1"].release_end = released
    project.loads["L1"] = Load("L1", "M1", "FY", -10)
    project.set_combination("Double", {"Case 1": 2})
    return project


def solve(project):
    with contextlib.redirect_stdout(io.StringIO()):
        return analyze(project)


class ReportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.project = beam()
        self.result = solve(self.project)

    def close_window(self, window):
        window.saved = window.project.to_dict()
        window.close()
        window.deleteLater()
        self.app.processEvents()

    def test_snapshot_identity_and_unit_independent_signature(self):
        signature = model_signature(self.project)
        self.assertEqual(signature, self.result.model_signature)
        self.project.unit_system = "si"
        self.assertEqual(model_signature(self.project), signature)
        other = self.result.for_combination("Double")
        self.assertEqual((other.snapshot_id, other.analyzed_at, other.model_signature),
                         (self.result.snapshot_id, self.result.analyzed_at, signature))
        self.assertNotEqual(solve(self.project).snapshot_id, self.result.snapshot_id)
        self.project.nodes["N2"].x += 1
        self.assertNotEqual(model_signature(self.project), signature)

    def test_tables_units_combinations_and_independent_extrema(self):
        headers, rows = result_table(self.project, self.result, "nodes")
        self.assertEqual(headers[5], "FY (kip)")
        self.assertAlmostEqual(rows[0][5], 5)
        self.project.unit_system = "si"
        headers, rows = result_table(self.project, self.result.for_combination("Double"), "nodes")
        self.assertEqual(headers[5], "FY (kN)")
        self.assertAlmostEqual(rows[0][5], 10 * 4.4482216152605)
        headers, rows = result_table(self.project, self.result, "members")
        self.assertEqual(headers[5], "Mz (kN-m)")
        self.assertAlmostEqual(rows[1][2], 120 * 0.0254)
        self.assertEqual(rows[2][2], "")
        self.assertEqual(rows[3][2], "")
        self.assertAlmostEqual(rows[2][5], -300 * 4.4482216152605 * 0.0254)

    def test_released_rotation_export(self):
        project = beam(True)
        _, rows = result_table(project, solve(project), "nodes")
        self.assertEqual(rows[0][3], "n/a")
        self.assertEqual(rows[1][3], "n/a")

    def test_csv_roundtrip_metadata_and_formula_safety(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "results.csv"
            source = '=file,"quoted"\nsecond line'
            export_csv(path, self.project, self.result, "members", source)
            with path.open(newline="") as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual(len(rows), 4)
            self.assertEqual(rows[0]["Source"], "'" + source)
            self.assertEqual(rows[0]["Analysis ID"], self.result.snapshot_id)
            self.assertEqual(rows[0]["Model signature"], self.result.model_signature)
            self.assertEqual(rows[0]["Analyzed (UTC)"], self.result.analyzed_at)
            self.assertEqual(rows[0]["Combination"], "Service")
            self.assertAlmostEqual(float(rows[2]["Mz (kip-in)"]), -300)
            self.assertEqual(rows[2]["x (in)"], "")
            self.assertEqual(list(Path(directory).iterdir()), [path])

    def test_stale_export_never_overwrites_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "results.csv"
            path.write_text("previous", encoding="utf-8")
            self.project.loads["L1"].magnitude = -20
            with self.assertRaisesRegex(ValueError, "does not match"):
                export_csv(path, self.project, self.result, "nodes")
            self.assertEqual(path.read_text(), "previous")

    def test_failed_atomic_replace_preserves_previous_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "results.csv"
            path.write_text("previous", encoding="utf-8")
            with patch.object(Path, "replace", side_effect=OSError("Permission denied")):
                with self.assertRaises(OSError):
                    export_csv(path, self.project, self.result, "nodes")
            self.assertEqual(path.read_text(), "previous")
            self.assertEqual(list(Path(directory).iterdir()), [path])

    def test_report_escaping_and_native_pdf_printing(self):
        source = '<model & "source">'
        html = report_html(self.project, self.result, source)
        self.assertIn("&lt;model &amp; &quot;source&quot;&gt;", html)
        self.assertIn(self.result.snapshot_id, html)
        self.assertIn("FY (kip)", html)
        document = report_document(self.project, self.result, source)
        self.assertIn(source, document.toPlainText())
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "report.pdf"
            printer = report_printer()
            printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
            printer.setOutputFileName(str(path))
            document.print_(printer)
            self.assertTrue(path.read_bytes().startswith(b"%PDF"))
            self.assertGreater(path.stat().st_size, 1000)

    def test_editor_invalidation_and_retained_snapshot_export(self):
        window = MainWindow()
        self.addCleanup(self.close_window, window)
        window.load_project(self.project)
        self.assertFalse(window.export_menu.isEnabled())
        window.analysis_revision = window.revision
        window.analysis_finished(self.result, "")
        self.assertTrue(window.export_menu.isEnabled())
        dialog = DiagramDialog(window, window.project, window.result)
        self.addCleanup(dialog.close)
        self.assertIn("Matches current", dialog.snapshot_label.text())
        window.edit("Units", lambda p: setattr(p, "unit_system", "si"))
        self.assertTrue(window.export_menu.isEnabled())
        self.assertEqual(dialog.result.snapshot_id, self.result.snapshot_id)
        window.analysis_revision = window.revision
        window.analysis_finished(solve(window.project), "")
        self.assertIn("Earlier analysis", dialog.snapshot_label.text())
        window.edit("Change load", lambda p: setattr(p.loads["L1"], "magnitude", -20))
        self.assertFalse(window.export_menu.isEnabled())
        self.assertIn("Different from current", dialog.snapshot_label.text())
        with tempfile.TemporaryDirectory() as directory:
            export_csv(Path(directory) / "snapshot.csv", dialog.project, dialog.result, "nodes")
        self.assertAlmostEqual(dialog.result.reactions["N1"][1], 5)

    def test_cancelled_export_and_print_preview_connection(self):
        window = MainWindow()
        self.addCleanup(self.close_window, window)
        window.load_project(self.project)
        window.analysis_revision = window.revision
        window.analysis_finished(self.result, "")
        with patch("pynitegui.qt.reports.QFileDialog.getSaveFileName", return_value=("", "")), \
                patch("pynitegui.qt.reports.export_csv") as export:
            window.export_menu.save_csv("nodes")
            export.assert_not_called()
        with patch("pynitegui.qt.reports.ReportOptionsDialog") as choices, \
                patch("pynitegui.qt.reports.QPrintPreviewDialog") as preview:
            choices.return_value.exec.return_value = 1
            choices.return_value.definition = ReportOptions()
            window.export_menu.print_report()
            preview.return_value.paintRequested.connect.assert_called_once()
            preview.return_value.exec.assert_called_once()


if __name__ == "__main__":
    unittest.main()
