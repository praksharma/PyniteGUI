"""Spatial one-sided queries, governing combinations and retained result UI."""
import contextlib
import csv
import io
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYNITEGUI_NO_WEBENGINE", "1")
import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from pynitegui.qt.analysis import analyze
from pynitegui.qt.envelopes import envelope_rows, export_envelope_csv, member_envelope
from pynitegui.qt.reports import ReportOptions, ReportOptionsDialog, report_document, report_html
from pynitegui.qt.spatial_diagrams import SpatialDiagramDialog
from pynitegui.qt.spatial_model import SpatialLoad, SpatialProject
from pynitegui.qt.spatial_results import LABELS, QUANTITIES, UNITS, inspect_member, member_values, sampled_member


class SpatialEnvelopeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.project = SpatialProject()
        cls.project.add_member((0, 0, 0), (120, 0, 0))
        cls.project.nodes["N1"].support = "fixed"
        cls.project.members["M1"].roll = 27
        for index, (direction, magnitude) in enumerate((("Fx", 2), ("Fy", -10), ("Fz", 3),
                                                       ("Mx", 4), ("My", 5), ("Mz", 6)), 1):
            cls.project.loads[f"L{index}"] = SpatialLoad(f"L{index}", "M1", direction, magnitude, .5)
        cls.project.loads["L7"] = SpatialLoad("L7", "M1", "Fz", -.01, .2, "distributed", -.02, .8)
        cls.project.set_combination("Double", {"Case 1": 2})
        cls.project.set_combination("Reverse", {"Case 1": -1})
        cls.project.set_combination("Same", {"Case 1": 1})
        with contextlib.redirect_stdout(io.StringIO()):
            cls.result = analyze(cls.project)

    def test_one_sided_all_force_and_moment_jumps(self):
        left = np.array(inspect_member(self.project, self.result, "M1", 60, "left"))
        right = np.array(inspect_member(self.project, self.result, "M1", 60, "right"))
        np.testing.assert_allclose(abs(left[:6] - right[:6]), (2, 10, 3, 4, 5, 6), atol=1e-4)
        np.testing.assert_allclose(left[6:], right[6:], atol=1e-6)
        for x in (0, 30, 120):
            np.testing.assert_allclose(inspect_member(self.project, self.result, "M1", x),
                                       member_values(self.result, "M1", x))
        for x in (-1, 121, float("nan"), float("inf"), True):
            with self.assertRaises(ValueError):
                inspect_member(self.project, self.result, "M1", x)
        with self.assertRaises(ValueError):
            inspect_member(self.project, self.result, "M1", 60, "unknown")

    def test_exact_extrema_and_all_global_node_components(self):
        names = ("Service", "Double", "Reverse")
        rows = envelope_rows(self.project, self.result, names)
        self.assertEqual(len(rows), 12 * len(self.project.nodes) + 8)
        for index, (label, quantity) in enumerate(zip(LABELS, UNITS)):
            row = next(row for row in rows if row[:3] == ("Member", "M1", label))
            self.assertEqual(row[3], quantity)
            # Independently compare full-member extrema for each selected solve.
            solver = self.result.solver.members["M1"]
            method, args = (("axial", ()), ("shear", ("Fy",)), ("shear", ("Fz",)),
                            ("torque", ()), ("moment", ("My",)), ("moment", ("Mz",)),
                            ("deflection", ("dy",)), ("deflection", ("dz",)))[index]
            lows = [(getattr(solver, "min_" + method)(*args, name), name) for name in names]
            highs = [(getattr(solver, "max_" + method)(*args, name), name) for name in names]
            self.assertEqual(row[4:], (*min(lows, key=lambda pair: pair[0]), *max(highs, key=lambda pair: pair[0])))
        for row in rows:
            if row[0] != "Node":
                continue
            from pynitegui.qt.spatial_model import DOFS, FORCES
            index = (*DOFS, *FORCES).index(row[2])
            pairs = [((r.displacements if index < 6 else r.reactions)[row[1]][index % 6], name)
                     for name in names for r in (self.result.for_combination(name),)]
            self.assertEqual(row[4:], (*min(pairs, key=lambda pair: pair[0]), *max(pairs, key=lambda pair: pair[0])))

    def test_curves_preserve_jumps_bounds_and_ties(self):
        names = ("Service", "Double", "Reverse")
        for index, quantity in enumerate(QUANTITIES):
            curve = member_envelope(self.project, self.result, names, "M1", quantity)
            self.assertTrue(np.any(np.diff(curve["x"]) == 0))
            values = np.stack([sampled_member(self.project, self.result.for_combination(name), "M1")[1][:, index] for name in names])
            np.testing.assert_array_equal(curve["minimum"], values.min(axis=0))
            np.testing.assert_array_equal(curve["maximum_combination"], np.array(names)[values.argmax(axis=0)])
        curve = member_envelope(self.project, self.result, ("Same", "Service"), "M1", "torque")
        self.assertTrue(np.all(curve["minimum_combination"] == "Same"))
        self.assertTrue(np.all(curve["maximum_combination"] == "Same"))

    def test_validation_snapshot_and_nonmutation(self):
        before = self.project.to_dict()
        for names in ((), ("Service", "Service"), ("missing",)):
            with self.assertRaises(ValueError):
                envelope_rows(self.project, self.result, names)
        with self.assertRaises(ValueError):
            member_envelope(self.project, self.result, ("Service",), "M1", "shear")
        changed = self.project.clone()
        changed.nodes["N2"].z = 1
        for action in (lambda: inspect_member(changed, self.result, "M1", 60),
                       lambda: envelope_rows(changed, self.result, ("Service",))):
            with self.assertRaisesRegex(ValueError, "snapshot"):
                action()
        self.assertEqual(before, self.project.to_dict())

    def test_csv_and_printable_envelopes_with_units_and_identity(self):
        project = self.project.clone()
        project.unit_system = "si"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "envelopes.csv"
            export_envelope_csv(path, project, self.result, ("Double", "Reverse"), "=unsafe")
            with path.open(newline="") as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual(len(rows), 32)
            self.assertEqual(rows[0]["Source"], "'=unsafe")
            self.assertEqual(rows[0]["Analysis ID"], self.result.snapshot_id)
            self.assertEqual(json.loads(rows[0]["Selected combinations"]), ["Double", "Reverse"])
            moment = next(row for row in rows if row["Entity"] == "Member" and row["Result"].startswith("My"))
            self.assertIn("kN-m", moment["Result"])
            canonical = next(row for row in envelope_rows(project, self.result, ("Double", "Reverse")) if row[:3] == ("Member", "M1", "My"))
            self.assertAlmostEqual(float(moment["Minimum"]), project.units.to_display(canonical[4], "moment"))
        options = ReportOptions(model=False, nodes=False, members=False, envelope_combinations=("Double", "Reverse"))
        html = report_html(project, self.result, "<source>", options)
        for text in ("Envelope combinations:", "Double", "Reverse", "3D spatial frame", "DZ (m)", "RX (rad)", "T (kN-m)", "dy (m)", "&lt;source&gt;"):
            self.assertIn(text, html)
        document = report_document(project, self.result, options=options)
        self.assertIn("Member Envelopes", document.toPlainText())

    def test_dialog_inspection_units_clicks_envelopes_and_print_choices(self):
        dialog = SpatialDiagramDialog(None, self.project, self.result)
        try:
            self.assertEqual(dialog.tabs.count(), 2)
            dialog.distance.setValue(60)
            right = float(dialog.inspection_values.item(0, 1).text())
            dialog.inspection_side.setCurrentText("Left side")
            left = float(dialog.inspection_values.item(0, 1).text())
            self.assertAlmostEqual(abs(left - right), 10, places=4)
            dialog.set_unit_system("si")
            self.assertAlmostEqual(dialog.distance.value(), 1.524)
            self.assertAlmostEqual(dialog.envelopes.distance.maximum(), 3.048)
            dialog.select_combination("Double")
            self.assertAlmostEqual(float(dialog.inspection_values.item(0, 1).text()),
                                   dialog.project.units.to_display(2 * left, "force"), places=3)
            dialog.inspect_click(SimpleNamespace(button=1, inaxes=dialog.figure.axes[0], xdata=.762))
            self.assertAlmostEqual(dialog.inspection_x, 30)
            self.assertEqual(len(dialog.probes), 8)
            envelope = dialog.envelopes
            self.assertEqual(envelope.quantity.count(), 8)
            envelope.quantity.setCurrentText("T")
            envelope.distance.setValue(1.524)
            envelope.side.setCurrentText("Left side")
            expected = [(inspect_member(dialog.project, self.result.for_combination(name), "M1", 60, "left")[3], name)
                        for name in envelope.selected_combinations()]
            self.assertEqual(envelope.inspection.item(0, 1).text(), min(expected, key=lambda pair: pair[0])[1])
            dialog.tabs.setCurrentWidget(envelope)
            choices = ReportOptionsDialog(dialog)
            self.assertTrue(choices.include_envelopes.isChecked())
            choices.accept()
            self.assertEqual(choices.definition.diagrams, ())
            self.assertEqual(choices.definition.envelope_combinations, envelope.selected_combinations())
            choices.close()
            for index in range(envelope.combinations.count()):
                envelope.combinations.item(index).setCheckState(Qt.CheckState.Unchecked)
            self.assertFalse(envelope.export_button.isEnabled())
            self.assertEqual(envelope.tables["Node"].rowCount(), 0)
            self.assertIsNone(envelope.inspection.item(0, 0))
        finally:
            dialog.close()
            self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
