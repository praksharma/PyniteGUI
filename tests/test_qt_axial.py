"""Axial-force signs, discontinuities, orientation, and diagram controls."""
import contextlib
import io
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import numpy as np
from matplotlib.figure import Figure
from PySide6.QtWidgets import QApplication
from pynitegui.qt.analysis import analyze
from pynitegui.qt.app import MainWindow
from pynitegui.qt.diagrams import DiagramDialog, draw_structure, sample_member, structure_data
from pynitegui.qt.model import Load, Project


def solve(project):
    with contextlib.redirect_stdout(io.StringIO()):
        return analyze(project)


def cantilever(end=(120, 0)):
    project = Project()
    project.add_member((0, 0), end)
    project.nodes["N1"].support = "fixed"
    return project


class AxialTests(unittest.TestCase):
    def test_horizontal_tension_and_compression(self):
        for force in (-10, 10):
            project = cantilever()
            project.loads["L1"] = Load("L1", "N2", "FX", force)
            values = sample_member(project, solve(project), "M1")
            np.testing.assert_allclose(values["axial"], -force, atol=1e-8)
            np.testing.assert_allclose(values["shear"], 0, atol=1e-8)
            np.testing.assert_allclose(values["moment"], 0, atol=1e-8)

    def test_inclined_and_vertical_signs_survive_reversal(self):
        for end, fx, fy in (((60, 80), 6, 8), ((0, 120), 0, 10), ((-60, 80), -6, 8)):
            for sign in (-1, 1):
                with self.subTest(end=end, sign=sign):
                    project = cantilever(end)
                    project.loads["L1"] = Load("L1", "N2", "FX", fx * sign)
                    project.loads["L2"] = Load("L2", "N2", "FY", fy * sign)
                    original = structure_data(project, solve(project), "axial")["M1"]
                    np.testing.assert_allclose(original["values"], -10 * sign, atol=1e-8)
                    member = project.members["M1"]
                    member.start, member.end = member.end, member.start
                    reverse = structure_data(project, solve(project), "axial")["M1"]
                    np.testing.assert_allclose(original["base"], reverse["base"][::-1], atol=1e-8)
                    np.testing.assert_allclose(original["normal"], reverse["normal"], atol=1e-8)
                    np.testing.assert_allclose(original["values"], reverse["values"][::-1], atol=1e-8)

    def test_point_axial_force_has_exact_vertical_jump(self):
        project = cantilever()
        project.loads["L1"] = Load("L1", "M1", "FX", 10, 0.37)
        sampled = sample_member(project, solve(project), "M1")
        index = np.where(np.diff(sampled["x"]) == 0)[0][0]
        self.assertAlmostEqual(sampled["x"][index], 44.4)
        self.assertAlmostEqual(sampled["axial"][index], -10)
        self.assertAlmostEqual(sampled["axial"][index + 1], 0)

    def test_reversed_point_load_distribution(self):
        project = cantilever()
        project.loads["L1"] = Load("L1", "M1", "FX", 10, 0.37)
        original = structure_data(project, solve(project), "axial")["M1"]
        project.members["M1"].start, project.members["M1"].end = "N2", "N1"
        project.loads["L1"].position = 0.63
        reverse = structure_data(project, solve(project), "axial")["M1"]
        np.testing.assert_allclose(original["values"], reverse["values"][::-1], atol=1e-8)
        np.testing.assert_allclose(original["base"], reverse["base"][::-1], atol=1e-8)

    def test_uniform_and_varying_axial_distributions(self):
        for end_intensity in (0.1, 0.3):
            project = cantilever()
            project.loads["L1"] = Load("L1", "M1", "FX", 0.1, 0, "distributed", end_intensity, 1)
            sampled = sample_member(project, solve(project), "M1")
            x = sampled["x"]
            expected = -(0.1 * (120 - x) + (end_intensity - 0.1) * (120**2 - x**2) / (2 * 120))
            np.testing.assert_allclose(sampled["axial"], expected, atol=1e-7)

    def test_partial_sign_changing_distribution(self):
        project = cantilever()
        project.loads["L1"] = Load("L1", "M1", "FX", -0.1, 0.2, "distributed", 0.3, 0.8)
        sampled = sample_member(project, solve(project), "M1")
        self.assertAlmostEqual(sampled["axial"][0], -7.2)
        self.assertAlmostEqual(sampled["axial"].min(), -8.1)
        self.assertAlmostEqual(sampled["axial"][-1], 0)
        self.assertIn(24, sampled["x"])
        self.assertIn(96, sampled["x"])

    def test_pin_jointed_triangle_has_tension_and_compression(self):
        project = Project()
        for start, end in (((0, 0), (120, 0)), ((0, 0), (60, 80)), ((120, 0), (60, 80))):
            project.add_member(start, end)
        project.nodes["N1"].support = "pin"
        project.nodes["N2"].support = "roller"
        for member in project.members.values():
            member.release_start = member.release_end = True
        project.loads["L1"] = Load("L1", "N3", "FY", -10)
        data = structure_data(project, solve(project), "axial")
        np.testing.assert_allclose(data["M1"]["values"], -3.75, atol=1e-8)
        for name in ("M2", "M3"):
            np.testing.assert_allclose(data[name]["values"], 6.25, atol=1e-8)

    def test_axial_combination_factors(self):
        project = cantilever()
        project.set_load_case("Other")
        project.loads["L1"] = Load("L1", "N2", "FX", 10)
        project.loads["L2"] = Load("L2", "N2", "FX", -5, case="Other")
        project.set_combination("Factored", {"Case 1": 1.2, "Other": 1.6})
        result = solve(project)
        np.testing.assert_allclose(sample_member(project, result, "M1")["axial"], -10, atol=1e-8)
        np.testing.assert_allclose(sample_member(project, result.for_combination("Factored"), "M1")["axial"], -4, atol=1e-8)

    def test_common_scale_and_sign_side(self):
        project = cantilever()
        project.add_member((120, 0), (240, 0))
        project.loads["L1"] = Load("L1", "N2", "FX", 5)
        project.loads["L2"] = Load("L2", "N3", "FX", 5)
        ax = Figure().add_subplot(111)
        data = draw_structure(ax, project, solve(project), "axial", amplitude=20)
        np.testing.assert_allclose(data["M1"]["values"], -10, atol=1e-8)
        np.testing.assert_allclose(data["M2"]["values"], -5, atol=1e-8)
        curves = [line for line in ax.lines if line.get_color() == "#3279a4" and len(line.get_xdata()) > 2]
        self.assertEqual(len(curves), 2)
        np.testing.assert_allclose(curves[0].get_ydata(), -48, atol=1e-8)
        np.testing.assert_allclose(curves[1].get_ydata(), -24, atol=1e-8)
        self.assertIn("+ compression", ax.get_title())

    def test_zero_axial_results_are_finite(self):
        project = cantilever()
        project.loads["L1"] = Load("L1", "N2", "FY", -10)
        ax = Figure().add_subplot(111)
        data = draw_structure(ax, project, solve(project), "axial")
        np.testing.assert_allclose(data["M1"]["values"], 0, atol=1e-8)
        for line in ax.lines:
            self.assertTrue(np.all(np.isfinite(line.get_ydata())))


class AxialEditorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = MainWindow()
        project = cantilever()
        project.loads["L1"] = Load("L1", "N2", "FX", 10)
        project.set_combination("Double", {"Case 1": 2})
        self.window.load_project(project)
        self.dialog = DiagramDialog(self.window, project, solve(project))

    def tearDown(self):
        self.dialog.close()
        self.window.saved = self.window.project.to_dict()
        self.window.close()
        self.window.deleteLater()
        self.application.processEvents()

    def test_quantity_selection_and_combination_switch(self):
        self.dialog.quantity.setCurrentIndex(self.dialog.quantity.findData("axial"))
        self.assertIn("Axial Force", self.dialog.structure_figure.axes[0].get_title())
        self.dialog.combination.setCurrentText("Double")
        self.assertEqual(self.dialog.quantity.currentData(), "axial")
        np.testing.assert_allclose(sample_member(self.dialog.project, self.dialog.result, "M1")["axial"], -20, atol=1e-8)
        self.assertAlmostEqual(self.dialog.member_figure.axes[0].lines[0].get_ydata()[0], -20)

    def test_member_detail_four_plots_share_distance_axis(self):
        axes = self.dialog.member_figure.axes
        self.assertEqual(len(axes), 4)
        self.assertIn("Axial N", axes[0].get_ylabel())
        self.assertIn("compression", axes[0].get_ylabel())
        self.assertIn("Moment Mz", axes[2].get_ylabel())
        self.assertEqual(axes[3].get_xlabel(), "Distance from start (in)")
        self.assertTrue(axes[0].get_shared_x_axes().joined(axes[0], axes[3]))

    def test_axial_diagram_snapshot_survives_model_edit(self):
        old = sample_member(self.dialog.project, self.dialog.result, "M1")["axial"].copy()
        self.window.edit("Change force", lambda p: setattr(p.loads["L1"], "magnitude", -15))
        self.dialog.quantity.setCurrentIndex(self.dialog.quantity.findData("axial"))
        np.testing.assert_allclose(sample_member(self.dialog.project, self.dialog.result, "M1")["axial"], old)

    def test_compact_member_detail_labels_do_not_overlap(self):
        self.dialog.tabs.setCurrentIndex(1)
        self.dialog.resize(800, 650)
        self.dialog.show()
        self.application.processEvents()
        self.dialog.member_canvas.draw()
        renderer = self.dialog.member_canvas.get_renderer()
        labels = [ax.yaxis.label.get_window_extent(renderer) for ax in self.dialog.member_figure.axes]
        for first, second in zip(labels, labels[1:]):
            self.assertFalse(first.overlaps(second))
