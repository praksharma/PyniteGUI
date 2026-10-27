"""Envelope scoping uses existing extrema and preserves snapshot/unit semantics."""
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
os.environ.setdefault("PYNITEGUI_NO_WEBENGINE", "1")
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QWidget
from pynitegui.qt.analysis import analyze
from pynitegui.qt.envelopes import EnvelopeWidget, envelope_rows, export_envelope_csv
from pynitegui.qt.envelope_filters import filter_rows
from pynitegui.qt.examples import example_project


class EnvelopeFilterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.project = example_project("simple_beam")
        cls.project.set_combination("Double", {"Case 1": 2.})
        cls.project.set_combination("Reverse", {"Case 1": -1.})
        with contextlib.redirect_stdout(io.StringIO()):
            cls.result = analyze(cls.project)

    def test_filter_uses_signed_solver_extrema_and_not_member_end_values(self):
        rows = envelope_rows(self.project, self.result, ("Double", "Reverse"))
        query = {"entities": [("Member", "M1")], "component": ["Member", "Mz"], "mode": "absolute", "threshold": 2000.}
        selected = list(filter_rows(rows, query))
        self.assertEqual(len(selected), 1)
        self.assertAlmostEqual(selected[0][4], -2100.)
        self.assertEqual(selected[0][5], "Double")
        query.update(mode="maximum", threshold=1000.)
        self.assertAlmostEqual(list(filter_rows(rows, query))[0][6], 1050.)
        query.update(mode="minimum", threshold=-2200.)
        self.assertEqual(list(filter_rows(rows, query)), [])
        query.update(mode="all", entities=[])
        self.assertEqual(list(filter_rows(rows, query)), [])

    def test_mixed_components_and_invalid_thresholds_are_rejected(self):
        for query in ({"mode": "minimum", "threshold": 1.},
                      {"mode": "unknown"}, {"threshold": float("nan")}, {"threshold": True},
                      {"mode": "absolute", "component": ["Member", "N"], "threshold": -1.}):
            with self.assertRaises(ValueError):
                list(filter_rows([], query))

    def test_filtered_csv_retains_provenance_scope_and_display_units(self):
        project = self.project.clone()
        project.unit_system = "si"
        query = {"scope": "Group: Beam", "entities": [("Member", "M1")], "component": ["Member", "Mz"],
                 "mode": "absolute", "threshold": 2000., "threshold_quantity": "moment"}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/"filtered.csv"
            export_envelope_csv(path, project, self.result, ("Double", "Reverse"), "=source", summary_filter=query)
            with path.open(newline="") as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["Source"], "'=source")
            self.assertEqual(rows[0]["Analysis ID"], self.result.snapshot_id)
            self.assertEqual(json.loads(rows[0]["Summary filter"])["scope"], "Group: Beam")
            self.assertAlmostEqual(float(rows[0]["Minimum"]), project.units.to_display(-2100., "moment"))
            previous = path.read_bytes()
            with self.assertRaises(ValueError):
                export_envelope_csv(path, project, self.result, ("Double",), summary_filter={"mode": "invalid"})
            self.assertEqual(path.read_bytes(), previous)


class EnvelopeFilterUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.models = {}
        for key in ("simple_beam", "3d_space_frame"):
            p = example_project(key)
            p.groups = {"First": {"nodes": [], "members": ["M1"]}, "Empty": {"nodes": [], "members": []}}
            p.set_combination("Double", {p.default_load_case: 2.})
            with contextlib.redirect_stdout(io.StringIO()):
                cls.models[key] = p, analyze(p)

    def setUp(self):
        self.host = QWidget()
        self.parent = QWidget(self.host)
        self.widgets = []

    def make(self, key="simple_beam"):
        p, r = self.models[key]
        self.host.selections = [("members", "M1")]
        widget = EnvelopeWidget(self.parent, p.clone(), r, "Untitled")
        self.widgets.append(widget)
        return widget

    def tearDown(self):
        self.host.close()
        self.host.deleteLater()
        self.app.processEvents()

    def test_scopes_are_frozen_and_filter_changes_reuse_extrema_preserving_plot_zoom(self):
        for key in self.models:
            w = self.make(key)
            f, before = w.filters, w.project.to_dict()
            w.figure.axes[0].set_xlim(1., 2.)
            self.host.selections.clear()
            with patch("pynitegui.qt.envelopes.envelope_rows", side_effect=AssertionError("Reuse canonical rows")):
                for scope in ("selection", "group:First", "member"):
                    f.scope.setCurrentIndex(f.scope.findData(scope))
                    self.assertGreater(w.tables["Member"].rowCount(), 0)
                    self.assertTrue(all(w.tables["Member"].item(i, 1).text() == "M1" for i in range(w.tables["Member"].rowCount())))
                f.scope.setCurrentIndex(f.scope.findData("group:Empty"))
                self.assertEqual(w.tables["Member"].rowCount(), 0)
                self.assertFalse(w.filtered_export.isEnabled())
            self.assertEqual(w.figure.axes[0].get_xlim(), (1., 2.))
            self.assertEqual(w.project.to_dict(), before)
            self.assertIs(w.result, self.models[key][1])

    def test_threshold_survives_unit_change_and_all_components_resets_value_filter(self):
        w = self.make()
        f = w.filters
        self.assertFalse(f.mode.isEnabled())
        f.component.setCurrentIndex(f.component.findData("Member:Mz"))
        f.mode.setCurrentIndex(f.mode.findData("absolute"))
        f.threshold.setValue(2000.)
        self.assertEqual(w.tables["Member"].rowCount(), 1)
        w.project.unit_system = "si"
        w.refresh()
        self.assertAlmostEqual(f.threshold_canonical, 2000.)
        self.assertAlmostEqual(f.threshold.value(), w.project.units.to_display(2000., "moment"))
        self.assertIn("kN-m", f.threshold.suffix())
        self.assertEqual(w.tables["Member"].rowCount(), 1)
        f.component.setCurrentIndex(0)
        self.assertEqual(f.mode.currentData(), "all")
        self.assertFalse(f.threshold.isEnabled())
        self.assertFalse(f.mode.isEnabled())

    def test_row_navigation_and_empty_combination_selection(self):
        w = self.make("3d_space_frame")
        table = w.tables["Member"]
        target = table.item(table.rowCount()-1, 1).text()
        w.open_summary_member(table, table.rowCount()-1)
        self.assertEqual(w.member.currentText(), target)
        self.assertEqual(w.quantity.currentData(), "dz")
        self.assertEqual(w.views.currentIndex(), 2)
        for i in range(w.combinations.count()):
            w.combinations.item(i).setCheckState(Qt.CheckState.Unchecked)
        self.assertEqual(table.rowCount(), 0)
        self.assertFalse(w.filtered_export.isEnabled())
