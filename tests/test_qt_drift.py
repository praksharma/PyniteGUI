"""Explicit static drift, signed governing values and retained native inputs."""
import csv
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYNITEGUI_NO_WEBENGINE", "1")
from PySide6.QtWidgets import QApplication
from pynitegui.qt.analysis import model_signature
from pynitegui.qt.drift import DriftWidget, drift_rows, display_rows, export_drift_csv
from pynitegui.qt.examples import example_project


def snapshot(project):
    # Deliberately nonzero lower-node motion; drifting floors must subtract it.
    results = {}
    for name, factor in (("A", 1.), ("B", -2.), ("Tie", 2.)):
        results[name] = SimpleNamespace(combination=name, displacements={
            node: tuple(factor*v for v in ((1., 2., 3.) if i == 0 else (4., 6., 8.)))
            for i, node in enumerate(project.nodes)})
    return SimpleNamespace(model_signature=model_signature(project), solver=SimpleNamespace(load_combos=dict.fromkeys(results)),
                           for_combination=results.__getitem__, snapshot_id="retained-test", analyzed_at="2026-10-27T00:00:00Z",
                           method_label="Linear elastic")


class DriftTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.project = example_project("portal")
        self.result = snapshot(self.project)
        self.pair = ("N1", "N2", "X")
        self.widget = DriftWidget(None, self.project, self.result, "/private/projects/model.json")

    def tearDown(self):
        self.widget.close()
        self.widget.deleteLater()
        self.app.processEvents()

    def test_signed_difference_height_ratio_and_governing_tie(self):
        rows = drift_rows(self.project, self.result, [self.pair], ("A", "B", "Tie"))
        h = self.project.nodes["N2"].y - self.project.nodes["N1"].y
        self.assertEqual([r[7] for r in rows], [3., -6., 6.])
        self.assertEqual([r[8] for r in rows], [3/h, -6/h, 6/h])
        self.assertEqual([r[9] for r in rows], [False, True, False])
        self.project.unit_system = "si"
        displayed = list(display_rows(self.project, rows))
        self.assertAlmostEqual(displayed[0][4], h*.0254)
        self.assertAlmostEqual(displayed[0][7], 3*.0254)
        self.assertEqual(displayed[0][8], rows[0][8])

    def test_validation_unknown_reversed_horizontal_duplicate_and_stale(self):
        for pair in (("N1", "N1", "X"), ("N2", "N1", "X"), ("N2", "N3", "X"),
                     ("missing", "N2", "X"), ("N1", "N2", "Z")):
            with self.subTest(pair=pair), self.assertRaises(ValueError):
                drift_rows(self.project, self.result, [pair], ("A",))
        with self.assertRaises(ValueError):
            drift_rows(self.project, self.result, [self.pair, self.pair], ("A",))
        with self.assertRaises(ValueError):
            drift_rows(self.project, self.result, [self.pair], ("unknown",))
        self.project.nodes["N2"].y += 1
        with self.assertRaisesRegex(ValueError, "snapshot"):
            drift_rows(self.project, self.result, [self.pair], ("A",))

    def test_spatial_z_is_translation_not_rotation_and_multiple_columns(self):
        p = example_project("3d_space_frame")
        # Select explicit vertical node pairs by coordinates without a rigid-floor assumption.
        low = min(p.nodes.values(), key=lambda n: n.y)
        high = next(n for n in p.nodes.values() if n.y > low.y)
        r = snapshot(p)
        rows = drift_rows(p, r, [(low.name, high.name, "Z"), (low.name, high.name, "X")], ("A",))
        self.assertEqual(rows[0][7], 5.)
        self.assertEqual(rows[1][7], 3.)

    def test_native_add_remove_invalid_pair_and_unit_refresh(self):
        w = self.widget
        before = self.project.to_dict()
        self.assertEqual(w.table.rowCount(), 0)
        self.assertFalse(w.export.isEnabled())
        w.add.click()
        self.assertIn("higher", w.message.text())
        w.upper.setCurrentText("N2")
        w.add.click()
        self.assertEqual(w.table.rowCount(), 3)
        w.add.click()
        self.assertIn("already", w.message.text())
        self.assertEqual(len(w.pairs), 1)
        w.combination.setCurrentIndex(1)
        self.assertEqual(w.table.rowCount(), 1)
        self.project.unit_system = "si"
        w.refresh()
        self.assertIn("(m)", w.table.horizontalHeaderItem(4).text())
        self.assertEqual(w.pairs, [self.pair])
        self.assertEqual(self.project.to_dict(), {**before, "unit_system": "si"})
        w.table.selectRow(0)
        w.remove.click()
        self.assertEqual(w.pairs, [])
        self.assertEqual(w.table.rowCount(), 0)
        self.assertFalse(w.export.isEnabled())

    def test_csv_provenance_signed_values_and_atomic_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/"drift.csv"
            export_drift_csv(path, self.project, self.result, [self.pair], ("A", "B"), "/private/projects/model.json")
            with path.open() as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual(rows[0]["Source"], "model.json")
            self.assertEqual(rows[0]["Analysis ID"], "retained-test")
            self.assertEqual(rows[1]["Governing |ratio|"], "Yes")
            self.assertEqual(float(rows[1]["Difference (in)"]), -6.)
            old = path.read_bytes()
            with patch("pynitegui.qt.drift.os.fsync", side_effect=OSError("disk failure")), self.assertRaises(OSError):
                export_drift_csv(path, self.project, self.result, [self.pair], ("A",), "model.json")
            self.assertEqual(path.read_bytes(), old)
            self.assertEqual(list(Path(directory).iterdir()), [path])

    def test_dialog_retains_pairs_when_parent_changes_combination_and_units(self):
        import contextlib
        import io
        from pynitegui.qt.analysis import analyze
        from pynitegui.qt.diagrams import DiagramDialog
        from pynitegui.qt.spatial_diagrams import SpatialDiagramDialog
        for key, dialog_class in (("multistorey", DiagramDialog), ("3d_space_frame", SpatialDiagramDialog)):
            project = example_project(key)
            with contextlib.redirect_stdout(io.StringIO()):
                result = analyze(project)
            dialog = dialog_class(None, project, result)
            try:
                w = dialog.drift
                lower = min(project.nodes.values(), key=lambda n: n.y)
                upper = next(n for n in project.nodes.values() if n.y > lower.y)
                w.lower.setCurrentText(lower.name)
                w.upper.setCurrentText(upper.name)
                w.add.click()
                pairs, count = list(w.pairs), w.table.rowCount()
                dialog.combination.setCurrentIndex(dialog.combination.count()-1)
                dialog.set_unit_system("si")
                project.nodes[lower.name].x += 1  # Original/editor model can diverge.
                w.refresh()
                self.assertEqual(w.pairs, pairs)
                self.assertEqual(w.table.rowCount(), count)
                self.assertEqual(w.result.snapshot_id, result.snapshot_id)
            finally:
                dialog.close()
                dialog.deleteLater()
