"""Independent second-order references, settings, result identity and supported scope."""
import contextlib
import csv
import io
import math
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYNITEGUI_NO_WEBENGINE", "1")
import numpy as np
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from pynitegui.qt.analysis import analyze, model_signature
from pynitegui.qt.analysis_method import analysis_method_issue
from pynitegui.qt.model import Load, Project, Section
from pynitegui.qt.spatial_conversion import to_spatial


def column(segments=6, ratio=.4):
    project = Project(analysis_method="p_delta")
    project.sections = {"Test": Section("Test", 10, 100, 100, 5)}
    project.default_section = "Test"
    for i in range(segments):
        project.add_member((0, 240*i/segments), (0, 240*(i+1)/segments))
    project.nodes["N1"].support = "fixed"
    tip = f"N{segments+1}"
    compression = ratio*math.pi**2*project.E*100/(4*240**2)
    project.loads = {"Gravity": Load("Gravity", tip, "FY", -compression),
                     "Wind": Load("Wind", tip, "FX", 1.)}
    return project, tip, compression


def solve(project, **kwargs):
    with contextlib.redirect_stdout(io.StringIO()):
        return analyze(project, **kwargs)


def reference(project, compression, force=1.):
    ei, length = project.E*100, 240
    if compression == 0:
        return force*length**3/(3*ei)
    k = math.sqrt(abs(compression)/ei)
    return (force/compression*(math.tan(k*length)/k-length) if compression > 0 else
            force/(-compression)*(length-math.tanh(k*length)/k))


class PDeltaEngineeringTests(unittest.TestCase):
    def test_compression_tension_and_mesh_refinement_against_beam_column(self):
        for ratio in (.4, -.4):
            errors = []
            for segments in (1, 4, 12):
                project, tip, compression = column(segments, ratio)
                result = solve(project)
                expected = reference(project, compression)
                errors.append(abs(result.displacements[tip][0]-expected))
                if segments == 12:
                    self.assertAlmostEqual(result.displacements[tip][0]/expected, 1, places=6)
                    # PyNite's second-order force recovery is approximate; retain
                    # an independent physical check, not a solver-to-solver test.
                    np.testing.assert_allclose(result.reactions["N1"], (-1, compression,
                        240+compression*expected), rtol=2e-5, atol=1e-7)
            self.assertGreater(errors[0], errors[1])
            self.assertGreater(errors[1], errors[2])

    def test_rotational_support_spring_against_beam_column_boundary_solution(self):
        project, tip, compression = column(12)
        base = project.nodes["N1"]
        base.support = "custom"
        base.restraint_x = base.restraint_y = True
        base.spring_rz = 100000.
        k = math.sqrt(compression/(project.E*100))
        flexural_arm = math.tan(k*240)/k
        expected = ((reference(project, compression)+240*flexural_arm/base.spring_rz)
                    / (1-compression*flexural_arm/base.spring_rz))
        result = solve(project)
        self.assertAlmostEqual(result.displacements[tip][0]/expected, 1, places=6)
        self.assertAlmostEqual(result.reactions["N1"][2],
                               -base.spring_rz*result.displacements["N1"][2], places=8)

    def test_moment_releases_preserve_zero_axial_load_linear_limit(self):
        project = Project(analysis_method="p_delta")
        project.add_member((0, 0), (120, 0))
        project.add_member((120, 0), (240, 0))
        project.nodes["N1"].support = "pin"
        project.nodes["N3"].support = "roller"
        project.members["M1"].release_start = True
        project.members["M2"].release_end = True
        project.loads["L1"] = Load("L1", "N2", "FY", -1)
        result = solve(project)
        self.assertAlmostEqual(result.displacements["N2"][1], -240**3/(48*project.E*project.Iz))
        self.assertIsNone(result.displacements["N1"][2])
        self.assertIsNone(result.displacements["N3"][2])
        for name in ("N1", "N3"):
            self.assertAlmostEqual(result.reactions[name][1], .5)
            self.assertEqual(result.reactions[name][2], 0.)

    def test_combinations_are_solved_independently_without_superposition(self):
        project, tip, _ = column()
        project.set_load_case("Wind")
        project.loads["Wind"].case = "Wind"
        project.combinations = {"Gravity": {"Case 1": 1}, "Wind": {"Wind": 1},
                                "Both": {"Case 1": 1, "Wind": 1}, "Double": {"Case 1": 2, "Wind": 2}}
        phases = []
        result = solve(project, progress=phases.append)
        wind = result.for_combination("Wind").displacements[tip][0]
        both = result.for_combination("Both").displacements[tip][0]
        double = result.for_combination("Double")
        self.assertGreater(both, 1.5*wind)
        self.assertGreater(double.displacements[tip][0], 3*both)
        self.assertEqual(double.analysis_method, "p_delta")
        self.assertEqual(double.snapshot_id, result.snapshot_id)
        for name in project.combinations:
            self.assertTrue(any(f"{name}: solving second-order" in phase for phase in phases))
        for name in ("Both", "Double"):
            single = project.clone()
            single.combinations = {name: project.combinations[name]}
            np.testing.assert_allclose(solve(single).displacements[tip],
                                       result.for_combination(name).displacements[tip], rtol=1e-9, atol=1e-12)

    def test_spatial_biaxial_column_matches_two_independent_references(self):
        planar, tip, compression = column()
        project = to_spatial(planar, "spatial")
        from pynitegui.qt.spatial_model import SpatialLoad
        project.loads["Crosswind"] = SpatialLoad("Crosswind", tip, "FZ", 2.)
        result = solve(project)
        expected = reference(project, compression)
        self.assertAlmostEqual(result.displacements[tip][0]/expected, 1, places=5)
        self.assertAlmostEqual(result.displacements[tip][2]/(2*expected), 1, places=5)
        self.assertEqual(result.analysis_method, "p_delta")
        self.assertTrue(result.spatial)

    def test_above_buckling_is_rejected_in_both_dimensions(self):
        planar, _, _ = column(ratio=1.2)
        for project in (planar, to_spatial(planar, "spatial")):
            with self.subTest(dimension=getattr(project, "dimension", "2D")):
                with self.assertRaisesRegex(ValueError, "P-Delta.*instability.*Service"):
                    solve(project)

    def test_unsupported_entities_fail_before_solving(self):
        from surface_fixtures import two_storey_slabs
        surface = two_storey_slabs()
        surface.analysis_method = "p_delta"
        truss, _, _ = column(1)
        truss.members["M1"].kind = "truss"
        released, _, _ = column(1)
        released.members["M1"].release_end_x = True
        for project, message in ((surface, "frame-only"), (truss, "frame members"), (released, "released member translations")):
            with self.subTest(message=message), self.assertRaisesRegex(ValueError, message):
                solve(project)

    def test_solver_failure_keeps_method_context_and_clears_callback(self):
        project, _, _ = column()
        from pynitegui.qt.analysis import FrameSolver, solve_model
        model = FrameSolver()
        with patch.object(model, "analyze_PDelta", side_effect=RuntimeError("did not converge")):
            with self.assertRaisesRegex(ValueError, "P-Delta analysis failed.*did not converge"):
                solve_model(model, project, lambda message: None)
        self.assertIsNone(model._analysis_progress)


class AnalysisMethodModelTests(unittest.TestCase):
    def test_saved_settings_and_legacy_defaults_in_both_dimensions(self):
        planar, _, _ = column()
        for project, legacy_version in ((planar, 15), (to_spatial(planar), 20)):
            restored = Project.from_dict(project.to_dict())
            self.assertEqual(restored.to_dict(), project.to_dict())
            self.assertEqual(restored.analysis_method, "p_delta")
            data = project.to_dict()
            data["version"] = legacy_version
            with self.assertRaisesRegex(ValueError, "version"):
                Project.from_dict(data)
            del data["analysis_method"]
            self.assertEqual(Project.from_dict(data).analysis_method, "linear")
            data = project.to_dict()
            del data["analysis_method"]
            with self.assertRaisesRegex(ValueError, "analysis_method"):
                Project.from_dict(data)

    def test_invalid_methods_and_method_signature(self):
        project, _, _ = column()
        signature = model_signature(project)
        project.analysis_method = "linear"
        self.assertNotEqual(signature, model_signature(project))
        for method in (None, True, [], "pushover", "P-Delta"):
            data = project.to_dict()
            data["analysis_method"] = method
            with self.subTest(method=method), self.assertRaisesRegex(ValueError, "Analysis method"):
                Project.from_dict(data)
        self.assertIsNone(analysis_method_issue(project))


class AnalysisMethodUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        from pynitegui.qt.app import MainWindow
        self.window = MainWindow()

    def tearDown(self):
        self.window.saved = self.window.project.to_dict()
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()

    def test_real_settings_dialog_is_undoable_and_cancel_is_unchanged(self):
        def choose():
            dialog = self.app.activeModalWidget()
            dialog.method.setCurrentIndex(dialog.method.findData("p_delta"))
            dialog.accept()
        QTimer.singleShot(0, choose)
        self.window.manage_analysis_method()
        self.assertEqual(self.window.project.analysis_method, "p_delta")
        self.assertIn("P-Delta", self.window.analyze_action.toolTip())
        self.window.undo.undo()
        self.assertEqual(self.window.project.analysis_method, "linear")
        self.window.undo.redo()
        self.assertEqual(self.window.project.analysis_method, "p_delta")
        before = self.window.project.to_dict()
        QTimer.singleShot(0, lambda: self.app.activeModalWidget().reject())
        self.window.manage_analysis_method()
        self.assertEqual(before, self.window.project.to_dict())

    def test_result_labels_exports_and_force_only_equilibrium(self):
        from pynitegui.qt.envelopes import export_envelope_csv
        from pynitegui.qt.equilibrium import check_equilibrium
        from pynitegui.qt.reports import export_csv, report_html
        project, _, _ = column()
        result = solve(project)
        self.window.load_project(project)
        self.window.result = result
        self.window.results_panel.update_results(project, result)
        self.window.results_panel.set_analysis_state("Current")
        self.assertIn("P-Delta elastic", self.window.results_panel.snapshot.text())
        self.assertIn("force balance only", self.window.results_panel.equilibrium_summary.text())
        check = check_equilibrium(project, result)
        self.assertEqual([row.component for row in check.rows], ["FX", "FY"])
        self.assertIn("P-Delta elastic", report_html(project, result))
        with tempfile.TemporaryDirectory() as folder:
            for name, export in (("nodes", lambda path: export_csv(path, project, result, "nodes")),
                                 ("envelope", lambda path: export_envelope_csv(path, project, result, ["Service"]))):
                path = Path(folder)/f"{name}.csv"
                export(path)
                with path.open() as stream:
                    rows = list(csv.DictReader(stream))
                self.assertTrue(rows)
                self.assertEqual(rows[0]["Analysis method"], "P-Delta elastic")
