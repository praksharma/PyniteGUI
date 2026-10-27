"""Static playback uses retained data and updates artists without new solves."""
import contextlib
import io
import os
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYNITEGUI_NO_WEBENGINE", "1")
import numpy as np
from PySide6.QtWidgets import QApplication
from pynitegui.qt.analysis import analyze
from pynitegui.qt.app import MainWindow
from pynitegui.qt.deformation_animation import StaticDeformationDialog, static_paths
from pynitegui.qt.examples import example_project
from pynitegui.qt.plot_export import export_plot
from pynitegui.qt.theme import configure_theme


def solve(p):
    with contextlib.redirect_stdout(io.StringIO()):
        return analyze(p)


class AnimationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.project = example_project("simple_beam")
        cls.project.set_combination("Double", {"Case 1": 2.})
        cls.result = solve(cls.project)

    def setUp(self):
        self.dialog = StaticDeformationDialog(None, self.project, self.result)

    def tearDown(self):
        self.dialog.close()
        self.app.processEvents()

    def test_fraction_interpolates_cached_paths_and_keeps_fixed_reference_and_limits(self):
        d = self.dialog
        before = self.project.to_dict()
        base, motion = d.paths[0]
        reference = np.array(d.reference.get_segments()[0])
        limits = d.ax.get_xlim(), d.ax.get_ylim()
        artists = list(d.ax.collections)
        with patch("pynitegui.qt.deformation_animation.static_paths", side_effect=AssertionError("No resampling")), \
             patch.object(d.result.solver.members["M1"], "deflection", side_effect=AssertionError("No solver calls")):
            for fraction in (0., .25, 1., .5, 0.):
                d.fraction.setValue(fraction)
                np.testing.assert_allclose(d.animated.get_segments()[0], base+d.factor*fraction*motion)
                np.testing.assert_array_equal(d.reference.get_segments()[0], reference)
                self.assertEqual((d.ax.get_xlim(), d.ax.get_ylim()), limits)
                self.assertEqual(list(d.ax.collections), artists)
        self.assertEqual(self.project.to_dict(), before)

    def test_play_pause_resume_reset_and_display_timing(self):
        d = self.dialog
        with patch("pynitegui.qt.deformation_animation.time.monotonic", return_value=100.):
            d.play.setChecked(True)
        self.assertTrue(d.timer.isActive())
        with patch("pynitegui.qt.deformation_animation.time.monotonic", return_value=101.):
            d.tick()
        self.assertAlmostEqual(d.fraction.value(), .5)
        d.pause()
        phase = d.phase
        self.assertFalse(d.timer.isActive())
        with patch("pynitegui.qt.deformation_animation.time.monotonic", return_value=200.):
            d.play.setChecked(True)
            d.tick()
        self.assertAlmostEqual(d.phase, phase)
        d.duration.setValue(8.)
        self.assertFalse(d.timer.isActive())
        d.reset_frame()
        self.assertEqual(d.fraction.value(), 0.)
        self.assertEqual(d.phase, 0.)
        self.assertEqual(d.play.text(), "Play")

    def test_units_theme_scale_combination_and_image_metadata_preserve_snapshot(self):
        d = self.dialog
        d.mode.setCurrentIndex(d.mode.findData("custom"))
        d.scale.setValue(12.)
        self.assertEqual(d.factor, 12.)
        d.fraction.setValue(.75)
        old = np.array(d.animated.get_segments()[0])
        d.set_unit_system("si")
        np.testing.assert_allclose(d.animated.get_segments()[0], old*.0254)
        self.assertEqual(d.fraction.value(), .75)
        configure_theme(self.app, "dark")
        d.apply_theme()
        self.assertEqual(d.fraction.value(), .75)
        with tempfile.TemporaryDirectory() as directory:
            d.play.setChecked(True)
            metadata = d.canvas.toolbar.metadata()
            self.assertFalse(d.timer.isActive())
            self.assertFalse(d.play.isChecked())
            self.assertEqual(metadata["displacement_fraction"], .75)
            self.assertTrue(metadata["display_only"])
            self.assertEqual(metadata["snapshot_id"], self.result.snapshot_id)
            export_plot(Path(directory)/"frame.svg", d.figure, metadata)
        d.combination.setCurrentText("Double")
        self.assertEqual(d.result.snapshot_id, self.result.snapshot_id)
        self.assertEqual(d.fraction.value(), 0.)
        self.assertEqual(d.factor, 12.)
        configure_theme(self.app, "light")

    def test_action_gating_editor_changes_and_hide_stop_playback(self):
        w = MainWindow()
        try:
            self.assertFalse(w.animation_action.isEnabled())
            w.load_project(self.project)
            w.analysis_revision = w.revision
            w.analysis_finished(self.result, "")
            self.assertTrue(w.animation_action.isEnabled())
            animation = w.animate_deformation()
            result = animation.result
            animation.play.setChecked(True)
            self.assertTrue(animation.timer.isActive())
            animation.hide()
            self.assertFalse(animation.timer.isActive())
            animation.show()
            animation.play.setChecked(True)
            w.automation_mode.changed.emit()
            self.assertFalse(animation.timer.isActive())
            w.edit("Move", lambda p: setattr(p.nodes["N2"], "x", 432))
            self.assertFalse(w.animation_action.isEnabled())
            self.assertIs(animation.result, result)
            np.testing.assert_array_equal(animation.paths[0][0][-1], (420., 0.))
            w.mcp_mode = True
            self.assertIsNone(w.animate_deformation())
            w.mcp_mode = False
            animation.close()
        finally:
            w.saved = w.project.to_dict()
            w.close()
            w.deleteLater()
            self.app.processEvents()

    def test_spatial_curves_use_global_motion_and_artist_reuse(self):
        p = example_project("3d_cantilever")
        r = solve(p)
        d = StaticDeformationDialog(None, p, r)
        try:
            self.assertTrue(d.spatial)
            d.fraction.setValue(1.)
            base, motion = d.paths[0]
            np.testing.assert_allclose(motion[-1], r.displacements[p.members["M1"].end][:3], atol=1e-10)
            with patch.object(d.animated, "set_segments", wraps=d.animated.set_segments) as update:
                d.fraction.setValue(.5)
                np.testing.assert_allclose(update.call_args.args[0][0], base+d.factor*.5*motion)
        finally:
            d.close()


class SurfaceAnimationTests(unittest.TestCase):
    def test_coupled_surface_wireframes_use_snapshot_nodes(self):
        p = example_project("3d_slab_frame")
        r = solve(p)
        paths = static_paths(p, r)
        from pynitegui.qt.spatial_surfaces import surface_payloads
        mesh = surface_payloads(p, r, False)[0]
        first = mesh["surfaces"][0]
        base, motion = paths[len(p.members)]
        nodes = [mesh["nodes"][i] for i in (*first, first[0])]
        np.testing.assert_allclose(base, [n["position"] for n in nodes])
        np.testing.assert_allclose(motion, [n["displacement"] for n in nodes])
        self.assertGreater(np.abs(motion).max(), 0.)
        self.assertEqual(len(paths), len(p.members)+sum(len(m["surfaces"]) for m in surface_payloads(p, r, False)))
