"""Independent references for the public P-Delta and multistorey slab examples."""
import contextlib
import io
import math
import unittest

import numpy as np
from pynitegui.qt.analysis import analyze
from pynitegui.qt.equilibrium import check_equilibrium
from pynitegui.qt.examples import example_project


def solve(project):
    with contextlib.redirect_stdout(io.StringIO()):
        return analyze(project)


class PDeltaExampleTests(unittest.TestCase):
    def test_public_column_matches_analytical_second_order_and_linear_limits(self):
        project = example_project("p_delta_column")
        original = project.to_dict()
        tip = project.node_at(0., 480.)
        base = project.node_at(0., 0.)
        result = solve(project)
        self.assertEqual(project.to_dict(), original)
        self.assertEqual(result.analysis_method, "p_delta")
        self.assertEqual(result.combination, "Combined")
        stiffness = project.E*project.Iz
        k = math.sqrt(60./stiffness)
        expected = (math.tan(k*480.)/k-480.)/60.
        combined = result.displacements[tip][0]
        lateral = result.for_combination("Lateral").displacements[tip][0]
        self.assertAlmostEqual(combined/expected, 1., places=5)
        self.assertAlmostEqual(lateral, 480.**3/(3*stiffness), places=9)
        self.assertGreater(combined, 1.5*lateral)
        self.assertAlmostEqual(result.for_combination("Gravity").displacements[tip][0], 0.)
        # Preserve the documented second-order recovery tolerance; do not claim
        # that this example passes the UI's much stricter force-residual check.
        np.testing.assert_allclose(result.reactions[base], (-1., 60., 480.+60.*expected), rtol=3e-5)
        check = check_equilibrium(project, result)
        self.assertEqual([row.component for row in check.rows], ["FX", "FY"])
        self.assertIn("force balance only", check.note)
        project.analysis_method = "linear"
        linear = solve(project)
        self.assertAlmostEqual(linear.displacements[tip][0], lateral, places=9)


class SlabExampleTests(unittest.TestCase):
    def test_three_floors_carry_expected_reactions_and_stack_column_shortening(self):
        project = example_project("3d_multistorey_slabs")
        original = project.to_dict()
        result = solve(project)
        self.assertEqual(project.to_dict(), original)
        self.assertEqual(result.analysis_method, "linear")
        self.assertTrue(project.surface_analysis_enabled)
        self.assertEqual(len(project.surfaces), 3)
        self.assertIsNone(project.self_weight_case)
        bases = [node.name for node in project.nodes.values() if node.y == 0.]
        for combo, total in (("Gravity", 183.6), ("Dead", 129.6), ("Factored", 241.92)):
            selected = result.for_combination(combo)
            with self.subTest(combination=combo):
                self.assertTrue(check_equilibrium(project, selected).passed)
                for base in bases:
                    self.assertAlmostEqual(selected.reactions[base][1], total/4, places=6)
                factors = project.combinations[combo]
                floor_forces = [43200.*(.001*factors.get("Dead", 0.)+live*factors.get("Live", 0.))
                                for live in (.0005, .0005, .00025)]
                expected_dy = 0.
                for floor in range(1, 4):
                    expected_dy -= sum(floor_forces[floor-1:])/4*144./(project.E*project.A)
                    for x, z in ((0., 0.), (240., 0.), (240., 180.), (0., 180.)):
                        node = project.node_at(x, floor*144., z)
                        self.assertAlmostEqual(selected.displacements[node][1], expected_dy, places=7)
                for mesh in result.solver._pynitegui_surfaces.values():
                    self.assertTrue(any(selected.displacements[node][1] < 0. for node in mesh["nodes"]))

    def test_mesh_refinement_retains_floor_load_paths(self):
        reactions = []
        for size in (60., 30.):
            project = example_project("3d_multistorey_slabs")
            for surface in project.surfaces.values():
                surface.mesh_size = size
            result = solve(project).for_combination("Factored")
            bases = [node.name for node in project.nodes.values() if node.y == 0.]
            reactions.append([result.reactions[name][1] for name in bases])
            self.assertTrue(check_equilibrium(project, result).passed)
        np.testing.assert_allclose(reactions, 60.48, atol=1e-6)
