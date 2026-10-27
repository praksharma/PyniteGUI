"""Hand-statical support reactions and zero hinge moments for public examples."""
import contextlib
import io
import unittest

import numpy as np
from pynitegui.qt.analysis import analyze
from pynitegui.qt.equilibrium import check_equilibrium
from pynitegui.qt.examples import example_project


def solve(project):
    with contextlib.redirect_stdout(io.StringIO()):
        return analyze(project)


class HingedExampleTests(unittest.TestCase):
    def test_gerber_reactions_from_suspended_span_and_lever_equilibrium(self):
        project = example_project("gerber")
        result = solve(project)
        # Right span carries 1.2 kip, half delivered at the internal hinge.
        # Left assembly: RB*120 = 1.8*90 + .6*180; RA = 2.4-RB.
        for name, force in (("N1", .15), ("N2", 2.25), ("N4", .6)):
            np.testing.assert_allclose(result.reactions[name], [0., force, 0.], atol=1e-9)
        self.assertTrue(check_equilibrium(project, result).passed)
        self.assertAlmostEqual(result.solver.members["M2"].moment("Mz", 60., "Service"), 0., places=9)
        self.assertAlmostEqual(result.solver.members["M3"].moment("Mz", 0., "Service"), 0., places=9)
        self.assertAlmostEqual(result.solver.members["M1"].moment("Mz", 120., "Service"), 54., places=9)
        self.assertIsNone(result.displacements["N3"][2])

    def test_arch_vertical_symmetry_and_horizontal_thrust_from_crown_moment(self):
        project = example_project("three_hinged_arch")
        result = solve(project)
        # Each V = 15/2; zero moment about the crown gives H=(120*7.5-60*5)/96.
        np.testing.assert_allclose(result.reactions["N1"], [6.25, 7.5, 0.], atol=1e-9)
        np.testing.assert_allclose(result.reactions["N5"], [-6.25, 7.5, 0.], atol=1e-9)
        self.assertTrue(check_equilibrium(project, result).passed)
        beam = result.solver.members["M2"]
        self.assertAlmostEqual(beam.moment("Mz", beam.L(), "Service"), 0., places=9)
        self.assertAlmostEqual(result.solver.members["M3"].moment("Mz", 0., "Service"), 0., places=9)
        self.assertIsNone(result.displacements["N3"][2])
        self.assertAlmostEqual(result.displacements["N3"][0], 0., places=10)
