"""Consistent snapshot context without changing analytical diagram values."""
import contextlib
import io
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import numpy as np
from matplotlib.figure import Figure
from matplotlib.backends.backend_agg import FigureCanvasAgg
from PySide6.QtWidgets import QApplication

from pynitegui.qt.analysis import analyze
from pynitegui.qt.annotations import combination_loads, load_label, support_geometry, spring_geometry, moment_geometry
from pynitegui.qt.diagrams import DiagramDialog, draw_structure
from pynitegui.qt.diagram_labels import DiagramLabel
from pynitegui.qt.examples import example_project
from pynitegui.qt.model import Load
from pynitegui.qt.reports import ReportOptions, ReportOptionsDialog, report_html
from pynitegui.qt.theme import LIGHT


def solve(project):
    with contextlib.redirect_stdout(io.StringIO()):
        return analyze(project)


class AnnotationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_support_presets_custom_and_springs_have_distinct_geometry(self):
        shapes = [support_geometry(key, flags) for key, flags in
                  (("free", (False, False, False)), ("pin", (True, True, False)),
                   ("roller", (False, True, False)), ("fixed", (True, True, True)),
                   ("custom", (True, False, True)))]
        self.assertEqual(len({repr(shape) for shape in shapes}), 5)
        springs = [spring_geometry(flags) for flags in ((1, 0, 0), (0, 1, 0), (0, 0, 1))]
        self.assertEqual(len({repr(shape) for shape in springs}), 3)
        self.assertEqual(spring_geometry((0, 0, 0)), ([], []))

    def test_signed_moment_arrows_follow_global_rotation(self):
        for magnitude in (10, -10):
            arc = moment_geometry(magnitude)[0][0]
            before, end = np.array(arc[-2]) * [1, -1], np.array(arc[-1]) * [1, -1]
            cross = before[0] * end[1] - before[1] * end[0]
            self.assertGreater(cross * magnitude, 0)

    def test_factored_loads_include_self_weight_and_never_mutate_definitions(self):
        project = example_project("portal")
        project.set_load_case("Dead")
        project.self_weight_case = "Dead"
        project.loads["L3"] = Load("L3", "N2", "Angle", 4, angle=30, case="Dead")
        project.loads["L4"] = Load("L4", "M2", "FY", 0, kind="distributed", end_magnitude=-0.1, case="Dead")
        project.set_combination("Reverse", {"Dead": -2})
        before = project.to_dict()
        loads = combination_loads(project, solve(project).for_combination("Reverse"))
        self.assertNotIn("L1", [load.name for load in loads])
        self.assertEqual(next(load.magnitude for load in loads if load.name == "L3"), -8)
        self.assertEqual(next(load.end_magnitude for load in loads if load.name == "L4"), 0.2)
        self.assertTrue(any(load.name.startswith("SW ") and load.magnitude > 0 for load in loads))
        self.assertEqual(project.to_dict(), before)
        project.unit_system = "si"
        self.assertIn("kN | Angle 30 deg", load_label(project, loads[0]))

    def test_context_toggles_leave_diagram_values_and_geometry_unchanged(self):
        project = example_project("portal")
        result = solve(project)
        a, b = Figure().add_subplot(), Figure().add_subplot()
        before = draw_structure(a, project, result, "moment", palette=LIGHT)
        after = draw_structure(b, project, result, "moment", palette=LIGHT, supports=False, loads=False)
        for name in before:
            np.testing.assert_array_equal(before[name]["values"], after[name]["values"])
        np.testing.assert_array_equal(a.lines[1].get_xydata(), b.lines[1].get_xydata())
        identities = [artist.get_gid() for artist in a.artists + a.texts]
        self.assertIn("support-N1", identities)
        self.assertIn("load-L1", identities)
        self.assertFalse(any(artist.get_gid() for artist in b.artists + b.texts))

    def test_force_arrow_direction_and_partial_load_stations(self):
        project = example_project("cantilever")
        project.loads["L2"].angle = 45
        project.loads["L2"].magnitude = -2
        result = solve(project)
        ax = Figure().add_subplot()
        draw_structure(ax, project, result, "moment", palette=LIGHT)
        arrows = [artist for artist in ax.texts if artist.get_gid() == "load-L1"]
        self.assertEqual(len(arrows), 9)
        self.assertAlmostEqual(arrows[0].xy[0], 0)
        self.assertAlmostEqual(arrows[-1].xy[0], 144)
        angled = next(artist for artist in ax.texts if artist.get_gid() == "load-L2")
        self.assertGreater(angled.get_position()[0], 0)
        self.assertGreater(angled.get_position()[1], 0)
        moments = [artist for artist in ax.artists if artist.get_gid() == "load-L4"]
        self.assertEqual(len(moments), 1)

    def test_labels_render_without_overlapping_text_or_symbols(self):
        project = example_project("elastic")
        figure = Figure(figsize=(10, 6), dpi=100, layout="constrained")
        canvas = FigureCanvasAgg(figure)
        ax = figure.add_subplot()
        draw_structure(ax, project, solve(project), "moment", palette=LIGHT)
        canvas.draw()
        labels = [artist for artist in ax.get_children() if isinstance(artist, DiagramLabel) and artist.placed]
        self.assertTrue(any("spring" in label.get_text() for label in labels))
        self.assertTrue(any("L1:" in label.get_text() for label in labels))
        boxes = [label.get_bbox_patch().get_window_extent(canvas.get_renderer()) for label in labels]
        for index, box in enumerate(boxes):
            self.assertFalse(any(box.overlaps(other) for other in boxes[index + 1:]))
        for obstacle in ax._diagram_label_layout.obstacles:
            rectangle = obstacle.get_window_extent(canvas.get_renderer())
            self.assertFalse(any(rectangle.overlaps(box) for box in boxes))

    def test_member_context_and_report_options_track_combination_and_units(self):
        project = example_project("elastic")
        project.set_combination("Double", {"Case 1": 2})
        dialog = DiagramDialog(None, project, solve(project))
        try:
            self.assertIn("RZ spring 500000 kip-in/rad", dialog.member_context.text())
            dialog.select_combination("Double")
            self.assertIn("L1: -20 kip", dialog.member_context.text())
            dialog.set_unit_system("si")
            self.assertIn("kN-m/rad", dialog.member_context.text())
            dialog.show_loads.setChecked(False)
            dialog.show_supports.setChecked(False)
            options = ReportOptionsDialog(dialog)
            options.accept()
            self.assertFalse(options.definition.loads)
            self.assertFalse(options.definition.supports)
            options.close()
            options.deleteLater()
            self.assertIn("Spring RZ (kN-m/rad)", report_html(dialog.project, dialog.result))
        finally:
            dialog.close()
            dialog.deleteLater()
            self.app.processEvents()

    def test_report_annotation_options_are_strict_booleans(self):
        for options in (ReportOptions(loads=1), ReportOptions(supports=None)):
            with self.assertRaisesRegex(ValueError, "boolean"):
                options.validate()
