"""Readable support/mechanism errors and preservation of valid hinge models."""
import contextlib
import io
import math
import unittest
from unittest.mock import patch
from types import SimpleNamespace

from pynitegui.qt.analysis import analyze, stiffness_issue
from pynitegui.qt.model import Load, Project


def solve(project):
    with contextlib.redirect_stdout(io.StringIO()):
        return analyze(project)


def beam():
    project = Project()
    project.add_member((0, 0), (120, 0))
    project.loads["L1"] = Load("L1", "M1", "FY", -10)
    return project


class StabilityTests(unittest.TestCase):
    def test_single_pin_identifies_rotation_motion(self):
        project = beam()
        project.nodes["N1"].support = "pin"
        before = project.to_dict()
        with self.assertRaisesRegex(ValueError, "Insufficient supports.*") as caught:
            solve(project)
        self.assertIn("N2 DY", str(caught.exception))
        self.assertIn("N1 RZ", str(caught.exception))
        self.assertEqual(project.to_dict(), before)

    def test_only_rollers_identify_horizontal_motion(self):
        project = beam()
        for node in project.nodes.values():
            node.support = "roller"
        with self.assertRaises(ValueError) as caught:
            solve(project)
        self.assertIn("N1 DX", str(caught.exception))
        self.assertIn("N2 DX", str(caught.exception))
        self.assertNotIn("N2 DY,", str(caught.exception))

    def test_custom_restraints_and_coordinate_translation(self):
        project = beam()
        project.nodes["N1"].support = "custom"
        project.nodes["N1"].restraint_x = True
        project.nodes["N1"].restraint_y = True
        project.nodes["N2"].support = "roller"
        for node in project.nodes.values():
            node.x += 1e8
            node.y += 1e8
        result = solve(project)
        self.assertAlmostEqual(result.reactions["N1"][1], 5)

    def test_internal_sway_mechanism_localized(self):
        project = Project()
        project.add_member((0, 0), (0, 120))
        project.add_member((0, 120), (240, 120))
        project.add_member((240, 120), (240, 0))
        project.nodes["N1"].support = project.nodes["N4"].support = "fixed"
        for member in project.members.values():
            member.release_start = member.release_end = True
        project.loads["L1"] = Load("L1", "N2", "FX", 10)
        with self.assertRaises(ValueError) as caught:
            solve(project)
        message = str(caught.exception)
        self.assertIn("unstable", message)
        self.assertIn("N2 DX", message)
        self.assertIn("N3 DX", message)
        self.assertNotIn("See console", message)

    def test_zero_stiffness_identifies_free_translation(self):
        project = beam()
        project.nodes["N1"].support = "fixed"
        project.members["M1"].release_start = project.members["M1"].release_end = True
        with self.assertRaisesRegex(ValueError, "N2 DY"):
            solve(project)

    def test_released_simply_supported_beam_remains_valid(self):
        project = beam()
        project.nodes["N1"].support = "pin"
        project.nodes["N2"].support = "roller"
        project.members["M1"].release_start = project.members["M1"].release_end = True
        result = solve(project)
        self.assertIsNone(result.displacements["N1"][2])
        self.assertAlmostEqual(result.reactions["N1"][1], 5)

    def test_nonfinite_values_in_any_combination_are_rejected(self):
        project = beam()
        project.nodes["N1"].support = "fixed"
        project.set_combination("Other", {"Case 1": 2})
        from Pynite import FEModel3D
        original = FEModel3D.analyze_linear

        def corrupt(model, *args, **kwargs):
            original(model, *args, **kwargs)
            model.nodes["N2"].DX["Other"] = math.nan

        with patch.object(FEModel3D, "analyze_linear", corrupt):
            with self.assertRaisesRegex(ValueError, "nonfinite"):
                solve(project)

    def test_unrelated_solver_failure_is_not_called_instability(self):
        project = beam()
        project.nodes["N1"].support = "fixed"
        with patch("pynitegui.qt.analysis.FEModel3D.analyze_linear", side_effect=RuntimeError("Unexpected solver error")):
            with self.assertRaisesRegex(RuntimeError, "Unexpected solver error"):
                solve(project)

    def test_uniformly_soft_material_is_not_misclassified(self):
        project = beam()
        project.nodes["N1"].support = "fixed"
        project.materials[project.default_material].E = 1e-6
        result = solve(project)
        expected = -10 * 120**3 / (3 * project.E * project.Iz) * (0.5**2 * (3 - 0.5) / 2)
        self.assertAlmostEqual(result.displacements["N2"][1] / expected, 1)

    def test_large_model_skips_dense_localization(self):
        model = SimpleNamespace(nodes={str(i): SimpleNamespace(ID=i, name=str(i), support_DX=False,
                                                               support_DY=False, support_RZ=False) for i in range(201)})
        self.assertIsNone(stiffness_issue(model))
