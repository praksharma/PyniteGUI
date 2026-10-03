"""Additional length/force presets preserve canonical models and solved values."""
import contextlib
import io
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication
from pynitegui.qt.analysis import analyze
from pynitegui.qt.app import MainWindow
from pynitegui.qt.examples import example_project
from pynitegui.qt.reports import result_table
from pynitegui.qt.units import UNIT_SYSTEMS, KIP_TO_KN


class UnitPresetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_known_millimetre_newton_factors(self):
        units = UNIT_SYSTEMS["si_mm"]
        self.assertEqual(units.to_display(1, "length"), 25.4)
        self.assertAlmostEqual(units.to_display(1, "force"), 4448.2216152605)
        self.assertAlmostEqual(units.to_display(1, "moment"), 112984.8290276167)
        self.assertAlmostEqual(units.to_display(1, "stress"), UNIT_SYSTEMS["si"].factor("stress"))
        self.assertAlmostEqual(units.to_display(1, "density"), KIP_TO_KN * 1000 / 25.4**3)

    def test_known_foot_kip_factors_with_inch_section_properties(self):
        units = UNIT_SYSTEMS["imperial_ft"]
        self.assertAlmostEqual(units.to_display(120, "length"), 10)
        self.assertAlmostEqual(units.to_display(120, "moment"), 10)
        self.assertAlmostEqual(units.to_display(1, "intensity"), 12)
        self.assertAlmostEqual(units.to_display(1, "density"), 1728)
        for quantity in ("force", "stress", "area", "inertia"):
            self.assertEqual(units.to_display(1, quantity), 1)

    def test_all_presets_live_result_and_project_preservation(self):
        window = MainWindow()
        window.load_project(example_project("simple_beam"))
        with contextlib.redirect_stdout(io.StringIO()):
            result = analyze(window.project)
        window.analysis_revision = window.revision
        window.analysis_finished(result, "")
        canonical = window.project.to_dict()
        canonical.pop("unit_system")
        try:
            for key, units in UNIT_SYSTEMS.items():
                window.set_units(key)
                data = window.project.to_dict()
                data.pop("unit_system")
                self.assertEqual(data, canonical)
                self.assertEqual(window.result.snapshot_id, result.snapshot_id)
                headers, rows = result_table(window.project, window.result, "nodes")
                self.assertEqual(headers[5], f"FY ({units.force})")
                self.assertAlmostEqual(rows[0][5], units.to_display(5, "force"))
                self.assertEqual(window.project.clone().unit_system, key)
        finally:
            window.saved = window.project.to_dict()
            window.close()
            window.deleteLater()
            self.app.processEvents()
