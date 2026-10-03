"""Envelopes retain provenance, independent extrema, and one-sided member values."""
import contextlib
import csv
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from pynitegui.qt.analysis import analyze
from pynitegui.qt.diagrams import DiagramDialog, sample_member
from pynitegui.qt.envelopes import bounds, display_rows, envelope_rows, export_envelope_csv, member_envelope
from pynitegui.qt.examples import example_project
from pynitegui.qt.theme import colors, configure_theme


class EnvelopeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.project = example_project("simple_beam")
        cls.project.set_combination("Double", {"Case 1": 2})
        cls.project.set_combination("Reverse", {"Case 1": -1})
        with contextlib.redirect_stdout(io.StringIO()):
            cls.result = analyze(cls.project)

    def test_exact_member_extrema_and_governing_combinations(self):
        rows = envelope_rows(self.project, self.result, ("Service", "Double", "Reverse"))
        moment = next(row for row in rows if row[:3] == ("Member", "M1", "Mz"))
        self.assertAlmostEqual(moment[4], -2100)
        self.assertEqual(moment[5], "Double")
        self.assertAlmostEqual(moment[6], 1050)
        self.assertEqual(moment[7], "Reverse")
        reaction = next(row for row in rows if row[:3] == ("Node", "N1", "FY"))
        self.assertAlmostEqual(reaction[4], -5)
        self.assertEqual(reaction[5], "Reverse")
        self.assertAlmostEqual(reaction[6], 10)
        self.assertEqual(reaction[7], "Double")

    def test_subset_and_single_combination(self):
        rows = envelope_rows(self.project, self.result, ("Service",))
        reaction = next(row for row in rows if row[:3] == ("Node", "N1", "FY"))
        self.assertAlmostEqual(reaction[4], reaction[6])
        curve = member_envelope(self.project, self.result, ("Service",), "M1", "moment")
        np.testing.assert_array_equal(curve["minimum"], curve["maximum"])
        np.testing.assert_array_equal(curve["minimum"], sample_member(self.project, self.result, "M1")["moment"])

    def test_curves_bound_each_selected_combination_and_keep_jumps(self):
        names = ("Service", "Double", "Reverse")
        curve = member_envelope(self.project, self.result, names, "M1", "shear")
        self.assertTrue(np.any(np.diff(curve["x"]) == 0))
        for name in names:
            values = sample_member(self.project, self.result.for_combination(name), "M1")["shear"]
            self.assertTrue(np.all(curve["minimum"] <= values))
            self.assertTrue(np.all(curve["maximum"] >= values))
        self.assertEqual(curve["maximum_combination"][0], "Double")
        self.assertEqual(curve["maximum_combination"][-1], "Reverse")

    def test_ties_are_stable_and_missing_rotations_are_not_zero(self):
        self.assertEqual(bounds([(0, "B"), (0, "A")]), (0, "B", 0, "B"))
        self.assertEqual(bounds([(None, "A")]), (None, "", None, ""))
        project = example_project("truss")
        with contextlib.redirect_stdout(io.StringIO()):
            result = analyze(project)
        rows = envelope_rows(project, result, ("Service",))
        rotation = next(row for row in rows if row[:3] == ("Node", "N1", "RZ"))
        self.assertEqual(rotation[4:], (None, "", None, ""))
        for row in rows:
            if row[0] == "Member" and row[2] in ("Fy", "Mz"):
                self.assertEqual((row[4], row[6]), (0, 0))

    def test_selection_validation_and_stale_models(self):
        for names in ((), ("missing",), ("Service", "Service")):
            with self.assertRaises(ValueError):
                envelope_rows(self.project, self.result, names)
        changed = self.project.clone()
        changed.nodes["N2"].x += 1
        with self.assertRaisesRegex(ValueError, "does not match"):
            envelope_rows(changed, self.result, ("Service",))
        with self.assertRaises(ValueError):
            member_envelope(self.project, self.result, ("Service",), "M1", "invalid")

    def test_units_and_model_results_are_unchanged(self):
        before = self.project.to_dict()
        original = dict(self.result.reactions)
        project = self.project.clone()
        rows = envelope_rows(project, self.result, ("Double", "Reverse"))
        canonical = next(row for row in rows if row[:3] == ("Member", "M1", "Mz"))
        for units in ("si", "si_mm", "imperial_ft"):
            project.unit_system = units
            row = next(row for row in display_rows(project, rows) if row[:2] == ("Member", "M1") and row[2].startswith("Mz"))
            self.assertAlmostEqual(row[3], project.units.to_display(canonical[4], "moment"))
            self.assertIn(project.units.moment, row[2])
        self.assertEqual(self.project.to_dict(), before)
        self.assertEqual(self.result.reactions, original)

    def test_csv_identity_selection_and_formula_safety(self):
        project = self.project.clone()
        project.unit_system = "si"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "envelope.csv"
            export_envelope_csv(path, project, self.result, ("Double", "Reverse"), "=unsafe")
            with path.open(newline="") as stream:
                rows = list(csv.DictReader(stream))
            row = next(row for row in rows if row["Entity"] == "Member" and row["Result"].startswith("Mz"))
            self.assertEqual(row["Source"], "'=unsafe")
            self.assertEqual(row["Analysis ID"], self.result.snapshot_id)
            self.assertEqual(json.loads(row["Selected combinations"]), ["Double", "Reverse"])
            self.assertEqual(json.loads(row["Combination factors"])["Double"], {"Case 1": 2})
            self.assertEqual(row["Minimum combination"], "Double")
            self.assertEqual(row["Maximum combination"], "Reverse")
            self.assertAlmostEqual(float(row["Minimum"]), project.units.to_display(-2100, "moment"))
            self.assertEqual(len(list(Path(directory).iterdir())), 1)

    def test_failed_export_preserves_existing_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "existing.csv"
            path.write_text("original")
            with patch("pynitegui.qt.envelopes.os.fsync", side_effect=OSError("failure")):
                with self.assertRaises(OSError):
                    export_envelope_csv(path, self.project, self.result, ("Service",))
            self.assertEqual(path.read_text(), "original")
            self.assertEqual(len(list(Path(directory).iterdir())), 1)

    def test_dialog_selection_units_theme_and_one_sided_inspection(self):
        dialog = DiagramDialog(None, self.project, self.result, "M1")
        widget = dialog.envelopes
        widget.quantity.setCurrentIndex(1)
        widget.distance.setValue(210)
        right = float(widget.inspection.item(0, 0).text())
        widget.side.setCurrentIndex(1)
        left = float(widget.inspection.item(0, 0).text())
        self.assertAlmostEqual(right, -10, places=4)
        self.assertAlmostEqual(left, -5, places=4)
        widget.combinations.item(1).setCheckState(Qt.CheckState.Unchecked)
        chosen = widget.selected_combinations()
        dialog.select_combination("Double")
        self.assertEqual(widget.selected_combinations(), chosen)
        dialog.set_unit_system("si")
        self.assertAlmostEqual(widget.distance.value(), 210 * 0.0254)
        self.assertIn("kN", widget.figure.axes[0].get_ylabel())
        configure_theme(self.app, "dark")
        from matplotlib.colors import to_hex
        self.assertEqual(to_hex(widget.figure.axes[0].get_facecolor()), colors()["canvas"])
        configure_theme(self.app, "light")
        for i in range(widget.combinations.count()):
            widget.combinations.item(i).setCheckState(Qt.CheckState.Unchecked)
        self.assertFalse(widget.export_button.isEnabled())
        self.assertEqual(widget.tables["Node"].rowCount(), 0)
        self.assertEqual(widget.figure.axes[0].get_title(), "No combinations selected")
        widget.combinations.item(0).setCheckState(Qt.CheckState.Checked)
        self.assertTrue(widget.export_button.isEnabled())
        dialog.close()
        self.app.processEvents()

    def test_cancel_export_does_not_write(self):
        dialog = DiagramDialog(None, self.project, self.result)
        with patch("pynitegui.qt.envelopes.QFileDialog.getSaveFileName", return_value=("", "")), \
                patch("pynitegui.qt.envelopes.export_envelope_csv") as export:
            dialog.envelopes.export()
            export.assert_not_called()
        dialog.close()
        self.app.processEvents()
