"""Display amplification must not change the solved physical model."""
import contextlib
import io
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QGraphicsLineItem
from pynitegui.qt.analysis import analyze
from pynitegui.qt.app import MainWindow, deformation_paths


class DeformationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = MainWindow()
        self.window.example()
        self.solve()
        self.window.deformed_action.trigger()

    def tearDown(self):
        self.window.saved = self.window.project.to_dict()
        self.window.close()
        self.window.deleteLater()
        self.application.processEvents()

    def solve(self):
        with contextlib.redirect_stdout(io.StringIO()):
            result = analyze(self.window.project)
        self.window.analysis_revision = self.window.revision
        self.window.analysis_finished(result, "")

    def lines(self):
        return [item.line() for item in self.window.view.scene().items()
                if isinstance(item, QGraphicsLineItem) and item.pen().color().name() == "#bd3549"]

    def peak(self):
        return max(max(line.y1(), line.y2()) for line in self.lines())

    def test_auto_scales_to_model_extent(self):
        self.assertEqual(self.window.deformation_mode.currentData(), "auto")
        self.assertAlmostEqual(self.peak(), 0.15 * 420)
        self.assertIn("Max", self.window.deformation_peak.text())

    def test_true_and_custom_scale_only_display(self):
        project = self.window.project.to_dict()
        revision = self.window.revision
        solver = self.window.result.solver
        self.window.deformation_mode.setCurrentText("True Scale")
        true_peak = self.peak()
        sampled_peak = max(abs(uy) for path in deformation_paths(self.window.project, self.window.result)
                           for _, _, _, uy in path)
        self.assertAlmostEqual(true_peak, sampled_peak)
        self.assertIn("Factor 1x", self.window.deformation_peak.text())
        self.window.deformation_mode.setCurrentText("Custom")
        self.window.deformation_scale.setValue(25)
        self.assertAlmostEqual(self.peak(), 25 * true_peak)
        self.window.deformation_scale.setValue(0.5)
        self.assertAlmostEqual(self.peak(), 0.5 * true_peak)
        self.assertEqual(self.window.project.to_dict(), project)
        self.assertEqual(self.window.revision, revision)
        self.assertIs(self.window.result.solver, solver)

    def test_auto_handles_zero_load(self):
        self.window.edit("Remove loads", lambda p: p.loads.clear())
        self.solve()
        self.window.deformed_action.trigger()
        self.assertAlmostEqual(self.peak(), 0)
        self.assertIn("Factor 1x | Max 0 in", self.window.deformation_peak.text())

    def test_controls_follow_result_visibility_and_invalidation(self):
        self.assertTrue(self.window.deformation_mode.isEnabled())
        self.assertFalse(self.window.deformation_scale.isEnabled())
        self.assertFalse(self.window.deformation_scale_action.isVisible())
        self.window.deformation_mode.setCurrentText("Custom")
        self.assertTrue(self.window.deformation_scale.isEnabled())
        self.assertTrue(self.window.deformation_scale_action.isVisible())
        self.window.deformed_action.trigger()
        self.assertFalse(self.lines())
        self.assertFalse(self.window.deformation_mode.isEnabled())
        self.window.deformed_action.trigger()
        self.window.edit("Move node", lambda p: setattr(p.nodes["N2"], "x", 432))
        self.assertFalse(self.window.deformation_mode.isEnabled())
        self.assertFalse(self.window.deformation_scale.isEnabled())

    def test_unit_switch_preserves_factor_and_shape(self):
        text = self.window.deformation_peak.text()
        peak = self.peak()
        self.window.set_units("si")
        self.assertAlmostEqual(self.peak(), peak)
        self.assertEqual(self.window.deformation_peak.text().split(" | ")[0], text.split(" | ")[0])
        paths = deformation_paths(self.window.project, self.window.result)
        actual = max((ux**2 + uy**2)**0.5 for path in paths for _, _, ux, uy in path)
        displayed = float(self.window.deformation_peak.text().split("Max ")[1].split()[0])
        self.assertAlmostEqual(displayed, actual * 0.0254, places=7)
        self.assertTrue(self.window.deformation_peak.text().endswith(" m"))

    def test_auto_recalculates_on_combination_change(self):
        self.window.edit("Double combination", lambda p: p.set_combination("Double", {"Case 1": 2}))
        self.solve()
        self.window.deformed_action.trigger()
        peak = self.peak()
        self.window.select_result_combination("Double")
        self.assertAlmostEqual(self.peak(), peak)

    def test_custom_value_survives_mode_changes(self):
        self.window.deformation_mode.setCurrentText("Custom")
        self.window.deformation_scale.setValue(37.5)
        self.window.deformation_mode.setCurrentText("Auto")
        self.window.deformation_mode.setCurrentText("True Scale")
        self.window.deformation_mode.setCurrentText("Custom")
        self.assertEqual(self.window.deformation_scale.value(), 37.5)


if __name__ == "__main__":
    unittest.main()
