"""Example catalog validity, responses, fresh data, and safe menu loading."""
import contextlib
import io
import math
import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYNITEGUI_NO_WEBENGINE", "1")
from PySide6.QtWidgets import QApplication
from pynitegui.qt.analysis import analyze
from pynitegui.qt.app import MainWindow
from pynitegui.qt.examples import EXAMPLES, example_project


def solve(project):
    with contextlib.redirect_stdout(io.StringIO()):
        return analyze(project)


class ExampleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_every_example_valid_and_all_combinations_solve(self):
        for key in EXAMPLES:
            with self.subTest(key=key):
                project = example_project(key)
                self.assertEqual(project.analysis_topology_issues(), [])
                self.assertEqual(project.analysis_release_issues(), [])
                result = solve(project)
                for combination in project.combinations:
                    self.assertTrue(all(math.isfinite(value) for row in result.for_combination(combination).displacements.values()
                                        for value in row if value is not None))

    def test_imperial_and_si_have_same_physical_model(self):
        for key in EXAMPLES:
            imperial, si = example_project(key).to_dict(), example_project(key, "si").to_dict()
            self.assertEqual(si.pop("unit_system"), "si")
            imperial.pop("unit_system")
            self.assertEqual(imperial, si)

    def test_fresh_models_and_unknown_key(self):
        first = example_project("portal")
        first.nodes["N1"].x = 100
        self.assertEqual(example_project("portal").nodes["N1"].x, 0)
        with self.assertRaises(ValueError):
            example_project("missing")

    def test_cantilever_resultants(self):
        result = solve(example_project("cantilever"))
        force_y = 0.015 * 240 * 0.6 + 2 * math.sin(math.radians(60)) + 3
        moment = 0.015 * 144 * 72 + 2 * math.sin(math.radians(60)) * 156 + 3 * 240 + 40
        self.assertAlmostEqual(result.reactions["N1"][0], -1)
        self.assertAlmostEqual(result.reactions["N1"][1], force_y)
        self.assertAlmostEqual(result.reactions["N1"][2], moment)

    def test_menu_loads_each_distinct_example_as_unsaved_in_current_units(self):
        window = MainWindow()
        window.project.unit_system = "si"
        with patch.object(window, "confirm_discard", return_value=True):
            for key, action in zip(EXAMPLES, window.examples_menu.actions()):
                action.trigger()
                self.assertEqual(window.project.to_dict(), example_project(key, "si").to_dict())
                self.assertIsNone(window.path)
                self.assertNotEqual(window.project.to_dict(), window.saved)
                self.assertIsNone(window.result)
        window.saved = window.project.to_dict()
        window.close()
        window.deleteLater()
        self.app.processEvents()

    def test_cancelled_example_keeps_active_model(self):
        window = MainWindow()
        before = window.project.to_dict()
        with patch.object(window, "confirm_discard", return_value=False):
            window.example("cantilever")
        self.assertEqual(window.project.to_dict(), before)
        window.close()
        window.deleteLater()
        self.app.processEvents()
