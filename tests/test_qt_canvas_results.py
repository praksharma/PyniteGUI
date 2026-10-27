"""Canvas overlays, signed scales and exact one-sided probes retain results."""
import contextlib
import io
import json
import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYNITEGUI_NO_WEBENGINE", "1")
import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QDoubleSpinBox
from pynitegui.qt.analysis import analyze
from pynitegui.qt.app import MainWindow
from pynitegui.qt.canvas_results import member_samples, signed_spans, signed_color, signed_palette
from pynitegui.qt.diagrams import sample_member, member_values
from pynitegui.qt.examples import example_project
from pynitegui.qt.spatial_view import viewport_payload, Bridge
from pynitegui.qt.theme import configure_theme


class CanvasResultsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.w = MainWindow()
        p = example_project("simple_beam")
        p.set_combination("Double", {"Case 1": 2.})
        self.load(p)
        self.c = self.w.canvas_results

    def load(self, p):
        self.w.load_project(p)
        with contextlib.redirect_stdout(io.StringIO()):
            result = analyze(self.w.project)
        self.w.analysis_revision = self.w.revision
        self.w.analysis_finished(result, "")

    def tearDown(self):
        self.w.saved = self.w.project.to_dict()
        self.w.close()
        self.w.deleteLater()
        self.app.processEvents()
        configure_theme(self.app, "light")

    def select_mode(self, kind):
        self.c.mode.setCurrentIndex(self.c.mode.findData(kind))

    def test_native_modes_and_scale_preserve_drafts_snapshot_and_transform(self):
        w, c = self.w, self.c
        w.select(("nodes", "N2"))
        field = w.inspector.findChild(QDoubleSpinBox)
        field.setValue(17.)
        before, revision, result = w.project.to_dict(), w.revision, w.result
        transform = w.view.transform()
        retained = w.diagrams()
        try:
            with patch.object(w, "refresh", side_effect=AssertionError("No model/inspector refresh")):
                for kind in ("model", "deformation", "axial", "shear", "moment"):
                    self.select_mode(kind)
                    self.assertEqual(w.deformed_action.isChecked(), kind == "deformation")
                    items = [i for i in w.view.scene().items() if i.data(0) == ("canvas_result", kind)]
                    self.assertEqual(bool(items), kind in ("axial", "shear", "moment"))
                    self.assertEqual(w.view.transform(), transform)
                c.scale.setValue(2.)
            self.assertIs(w.inspector.findChild(QDoubleSpinBox), field)
            self.assertEqual(field.value(), 17.)
            self.assertEqual(w.project.to_dict(), before)
            self.assertEqual(w.revision, revision)
            self.assertIs(w.result, result)
            self.assertEqual(retained.result.snapshot_id, result.snapshot_id)
        finally:
            retained.close()

    def test_shared_colour_scale_and_signed_line_patterns(self):
        self.select_mode("shear")
        base = max(abs(sample_member(self.w.project, self.w.result, "M1")["shear"]))
        self.c.style.setCurrentIndex(1)
        bound = self.c.colour_bound()
        self.assertAlmostEqual(bound, 2*base)
        self.assertIn("all analyzed combinations", self.c.legend.text())
        overlays = [i for i in self.w.view.scene().items() if i.data(0) == ("canvas_result", "shear")]
        styles = {i.pen().style() for i in overlays}
        self.assertIn(Qt.PenStyle.DashLine, styles)
        self.assertIn(Qt.PenStyle.SolidLine, styles)
        self.w.select_result_combination("Double")
        self.assertEqual(self.c.colour_bound(), bound)
        self.w.set_units("si")
        self.assertEqual(self.c.colour_bound(), bound)
        self.assertIn("kN", self.c.legend.text())
        for theme in ("light", "dark"):
            configure_theme(self.app, theme)
            self.assertEqual(signed_color(-bound, bound).name(), signed_palette()[0])
            self.assertEqual(signed_color(0., bound).name(), signed_palette()[1])
            self.assertEqual(signed_color(bound, bound).name(), signed_palette()[2])

    def test_probe_at_point_load_uses_exact_left_right_and_physical_station(self):
        self.select_mode("shear")
        self.c.inspect_at("M1", (210., 0.), redraw=False)
        self.w.select(("members", "M1"))
        for side in ("left", "right"):
            self.c.side.setCurrentIndex(self.c.side.findData(side))
            values = member_values(self.w.project, self.w.result, "M1", 210., side)
            self.assertIn(f"Fy {values[1]:.6g} kip", self.c.values.text())
            np.testing.assert_allclose(self.c.probe["position"], (210., 0.))
        self.w.set_units("si")
        self.assertAlmostEqual(self.c.distance.value(), 210.*.0254)
        self.assertAlmostEqual(self.c.station, 210.)
        self.w.select_result_combination("Double")
        self.assertAlmostEqual(self.c.station, 210.)
        self.assertIn("right", self.c.values.text())
        self.w.edit("Move", lambda p: setattr(p.nodes["N2"], "x", 432.))
        self.assertFalse(self.c.mode.isEnabled())
        self.assertIsNone(self.c.probe)
        self.assertIn("Run analysis", self.c.legend.text())

    def test_signed_spans_skip_discontinuities_and_split_zero(self):
        points = np.array(((0., 0.), (5., 0.), (5., 0.), (10., 0.)))
        spans = list(signed_spans(points, np.array((2., 2., -2., -2.))))
        self.assertEqual(len(spans), 2)
        self.assertEqual([s[2] for s in spans], [2., -2.])
        spans = list(signed_spans(np.array(((0., 0.), (10., 0.))), (2., -2.)))
        np.testing.assert_allclose(spans[0][1], (5., 0.))
        np.testing.assert_allclose(spans[1][0], (5., 0.))
        self.assertEqual([s[2] for s in spans], [1., -1.])

    def test_spatial_payload_mirrors_existing_controls_and_guarded_click_probe(self):
        self.load(example_project("3d_cantilever"))
        self.select_mode("moment_z")
        self.c.style.setCurrentIndex(1)
        original = viewport_payload(self.w)
        self.assertEqual(original["diagram"]["style"], "colour")
        np.testing.assert_allclose(original["members"][0]["diagramValues"], list(member_samples(self.w.project, self.w.result, "moment_z").values())[0][1])
        bridge = Bridge(self.w.view)
        m = self.w.project.members["M1"]
        a, b = (np.array(self.w.project.nodes[n].coords) for n in (m.start, m.end))
        point = ((a+b)/2).tolist()
        self.w.select(("members", "M1"))
        request = {"position": point, "revision": self.w.revision}
        bridge.inspect("M1", json.dumps(request))
        probe = viewport_payload(self.w)["probe"]
        np.testing.assert_allclose(probe["position"], point)
        station = self.c.station
        request["revision"] -= 1
        request["position"] = a.tolist()
        bridge.inspect("M1", json.dumps(request))
        self.assertEqual(self.c.station, station)
        self.w.view.diagram.setCurrentIndex(self.w.view.diagram.findData("shear_y"))
        self.assertEqual(self.c.mode.currentData(), "shear_y")
        self.w.view.diagram_scale.setValue(2.)
        self.assertEqual(self.c.scale.value(), 2.)
        self.select_mode("model")
        self.assertIsNone(viewport_payload(self.w)["diagram"])

    def test_zero_loads_and_small_window(self):
        p = example_project("simple_beam")
        p.loads.clear()
        self.load(p)
        self.select_mode("moment")
        self.c.style.setCurrentIndex(1)
        self.assertEqual(self.c.colour_bound(), 0.)
        self.w.resize(820, 560)
        self.w.show()
        self.app.processEvents()
        self.assertFalse(self.w.grab().isNull())
        self.assertLessEqual(self.c.minimumSizeHint().width(), 820)
