"""Bounded inclined-support feasibility, deliberately outside production solves."""
import contextlib
import io
import unittest

import numpy as np

from inclined_constraints import solve
from inclined_reference import cantilever, pinned_beam, normal, rotation
from inclined_validation import assemble, beam, constraints, balance
from pynitegui.qt.analysis import analyze
from pynitegui.qt.spatial_model import SpatialProject


FACTORS = {"Service": 1., "Reverse": -1.7, "Zero": 0.}


class InclinedConstraintTests(unittest.TestCase):
    def test_exact_elimination_matches_independent_lagrange_multiplier_system(self):
        rng = np.random.default_rng(123)
        A = rng.normal(size=(9, 9))
        K = A.T @ A+np.eye(9)
        f = rng.normal(size=9)
        C = constraints(["A", "B", "C"], fixed=("A",), rollers=(("B", 27.), ("C", -53.)))
        saddle = np.block([[K, C.T], [C, np.zeros((len(C), len(C)))]])
        expected = np.linalg.solve(saddle, np.r_[f, np.zeros(len(C))])
        result = solve(K, f, C, length_scale=120.)
        np.testing.assert_allclose(result['displacement'], expected[:9], atol=1e-12)
        np.testing.assert_allclose(result['rigid_reaction'], -C.T @ expected[9:], atol=1e-12)
        self.assertAlmostEqual(result['quadratic_energy']*2, result['equivalent_nodal_work'], places=12)
        np.testing.assert_allclose(C @ result['displacement'], 0., atol=1e-12)
        fixed = solve(K, f, np.eye(9))
        np.testing.assert_array_equal(fixed['displacement'], np.zeros(9))
        np.testing.assert_allclose(fixed['rigid_reaction'], -f)

    def test_cantilever_tip_flexibility_reactions_and_global_balance(self):
        for beam_angle in (0., 37., 90., -143.):
            p = beam(angle=beam_angle)
            before = p.to_dict()
            names, matrices, forces = assemble(p)
            self.assertEqual(p.to_dict(), before)
            for roller in (-170., -90., -30., 0., 25., 89.9, 90., 135., 180.):
                C = constraints(names, fixed=(names[0],), rollers=((names[-1], roller),))
                expected_d, expected_r = cantilever(roller, beam_angle)
                tangent = rotation(roller)[:, 0]
                for combination, factor in FACTORS.items():
                    with self.subTest(beam=beam_angle, roller=roller, combination=combination):
                        r = solve(matrices[combination], forces[combination], C, 120.)
                        d, reactions = r['displacement'].reshape(-1, 3), r['rigid_reaction'].reshape(-1, 3)
                        np.testing.assert_allclose(d[-1], expected_d*factor, atol=1e-11)
                        np.testing.assert_allclose(reactions[-1], expected_r*factor, atol=1e-9)
                        np.testing.assert_allclose(balance(p, names, reactions, combination), 0., atol=1e-8)
                        self.assertAlmostEqual(float(tangent @ reactions[-1]), 0., places=10)
                        self.assertAlmostEqual(float(normal(roller) @ d[-1]), 0., places=12)
                        self.assertAlmostEqual(r['quadratic_energy']*2, r['equivalent_nodal_work'], places=10)
                        self.assertGreater(r['minimum_scaled_eigenvalue'], r['stability_roundoff_bound'])

    def test_pin_and_inclined_roller_match_entire_independent_nodal_field(self):
        for fractions in ((0., 1.), (0., .17, .53, 1.), tuple(np.linspace(0., 1., 9))):
            p = beam(fractions=fractions, nodal=(0., 0., 0.), distributed=(0., -.005))
            names, matrices, forces = assemble(p)
            for roller in (-65., 0., 17., 60.):
                expected, left, right = pinned_beam(np.array(fractions)*120., roller)
                C = constraints(names, pinned=(names[0],), rollers=((names[-1], roller),))
                for combination, factor in FACTORS.items():
                    with self.subTest(nodes=len(names), roller=roller, combination=combination):
                        r = solve(matrices[combination], forces[combination], C, 120.)
                        np.testing.assert_allclose(r['displacement'].reshape(-1, 3), expected*factor, atol=1e-10)
                        reactions = r['rigid_reaction'].reshape(-1, 3)
                        np.testing.assert_allclose(reactions[[0, -1]], np.array((left, right))*factor, atol=1e-9)
                        np.testing.assert_allclose(reactions[1:-1], 0., atol=1e-9)
                        np.testing.assert_allclose(balance(p, names, reactions, combination), 0., atol=1e-8)

    def test_separate_axial_transverse_moment_and_uniform_load_patterns(self):
        for nodal, distributed in (((3., 0., 0.), (0., 0.)), ((0., -2., 0.), (0., 0.)),
                                   ((0., 0., 7.), (0., 0.)), ((0., 0., 0.), (.002, 0.)),
                                   ((0., 0., 0.), (0., -.005))):
            p = beam(angle=37., nodal=nodal, distributed=distributed)
            names, matrices, forces = assemble(p)
            for roller in (-30., 25., 90.):
                C = constraints(names, fixed=(names[0],), rollers=((names[-1], roller),))
                d, reaction = cantilever(roller, 37., nodal, distributed)
                r = solve(matrices['Service'], forces['Service'], C, 120.)
                np.testing.assert_allclose(r['displacement'][-3:], d, atol=1e-11)
                np.testing.assert_allclose(r['rigid_reaction'][-3:], reaction, atol=1e-9)
                np.testing.assert_allclose(balance(p, names, r['rigid_reaction'], 'Service'), 0., atol=1e-8)

    def test_global_bilateral_springs_keep_axes_and_separate_ground_reactions(self):
        for beam_angle, roller, springs in ((0., 27., (500., 0., 0.)), (37., -26., (0., 700., 200.)),
                                            (-73., 61., (50000., 300., 900.))):
            p = beam(angle=beam_angle)
            tip = next(reversed(p.nodes))
            p.nodes[tip].spring_x, p.nodes[tip].spring_y, p.nodes[tip].spring_rz = springs
            names, matrices, forces = assemble(p)
            C = constraints(names, fixed=(names[0],), rollers=((tip, roller),))
            d, reaction = cantilever(roller, beam_angle, springs=springs)
            for combination, factor in FACTORS.items():
                r = solve(matrices[combination], forces[combination], C, 120.)
                actual_d = r['displacement'].reshape(-1, 3)
                np.testing.assert_allclose(actual_d[-1], d*factor, atol=1e-11)
                actual_r = r['rigid_reaction'].reshape(-1, 3)
                np.testing.assert_allclose(actual_r[-1], reaction*factor, atol=1e-9)
                external = actual_r.copy()
                external[-1] -= np.asarray(springs)*actual_d[-1]
                np.testing.assert_allclose(balance(p, names, external, combination), 0., atol=1e-8)

    def test_coordinate_rotation_origin_and_roller_normal_sign_are_invariant(self):
        base = beam()
        names, matrices, forces = assemble(base)
        C = constraints(names, fixed=(names[0],), rollers=((names[-1], 27.),))
        baseline = solve(matrices['Service'], forces['Service'], C, 120.)
        for angle, origin in ((37., (17., -31.)), (90., (-137., 211.)), (-143., (1e5, -3e5))):
            p = beam(angle=angle, origin=origin)
            names, matrices, forces = assemble(p)
            for normal_sign in (0., 180.):
                C = constraints(names, fixed=(names[0],), rollers=((names[-1], 27.+angle+normal_sign),))
                r = solve(matrices['Service'], forces['Service'], C, 120.)
                for key in ('displacement', 'rigid_reaction'):
                    expected = baseline[key].reshape(-1, 3) @ rotation(angle).T
                    np.testing.assert_allclose(r[key].reshape(-1, 3), expected, rtol=1e-8, atol=1e-9)
                self.assertAlmostEqual(r['quadratic_energy'], baseline['quadratic_energy'], places=10)

    def test_length_scaling_and_constraint_row_scaling_do_not_change_physics(self):
        p = beam(fractions=(0., .17, .53, 1.))
        names, matrices, forces = assemble(p)
        C = constraints(names, fixed=(names[0],), rollers=((names[-1], 27.),))
        baseline = solve(matrices['Service'], forces['Service'], C, 120.)
        for scale in (.1, 1., 120., 1000.):
            r = solve(matrices['Service'], forces['Service'], C*np.array((.01, 10., .3, -7.))[:, None], scale)
            np.testing.assert_allclose(r['displacement'], baseline['displacement'], rtol=1e-8, atol=1e-10)
            np.testing.assert_allclose(r['rigid_reaction'], baseline['rigid_reaction'], atol=1e-8)

    def test_global_angle_limits_match_unchanged_production_supports(self):
        for roller in (0., 90., 180.):
            p = beam(fractions=(0., .17, .53, 1.))
            names, matrices, forces = assemble(p)
            C = constraints(names, fixed=(names[0],), rollers=((names[-1], roller),))
            p.nodes[names[0]].support = 'fixed'
            node = p.nodes[names[-1]]
            node.support = 'custom'
            node.restraint_x, node.restraint_y = roller == 90., roller != 90.
            with contextlib.redirect_stdout(io.StringIO()):
                production = analyze(p)
            for combination in FACTORS:
                expected = production.for_combination(combination)
                r = solve(matrices[combination], forces[combination], C, 120.)
                np.testing.assert_allclose(r['displacement'].reshape(-1, 3), [expected.displacements[name] for name in names], atol=1e-10)
                np.testing.assert_allclose(r['rigid_reaction'].reshape(-1, 3), [expected.reactions[name] for name in names], atol=1e-8)

    def test_mechanisms_are_rejected_even_for_zero_load(self):
        p = beam(nodal=(0., 0., 0.), distributed=(0., 0.))
        names, matrices, forces = assemble(p)
        for C in (constraints(names), constraints(names, pinned=(names[0],)),
                  *(constraints(names, pinned=(names[0],), rollers=((names[-1], angle),))
                    for angle in (90., 89.999999, 90.000001))):
            with self.assertRaisesRegex(ValueError, 'Unstable'):
                solve(matrices['Zero'], forces['Zero'], C, 120.)
        for angle in (90., -90.):
            with self.assertRaisesRegex(ValueError, 'rigid-body'):
                pinned_beam((0., 120.), angle)

    def test_duplicate_nearly_dependent_and_invalid_constraints_are_rejected(self):
        K, f = np.eye(6), np.ones(6)
        for angle in (0., 1e-10):
            C = constraints(['A', 'B'], rollers=(('B', 0.), ('B', angle)))
            with self.assertRaisesRegex(ValueError, 'dependent'):
                solve(K, f, C)
        for C in (np.zeros((1, 6)), np.full((1, 6), np.nan), np.ones((1, 5))):
            with self.assertRaises(ValueError):
                solve(K, f, C)
        for scale in (0., -1., np.inf, np.nan):
            with self.assertRaises(ValueError):
                solve(K, f, np.empty((0, 6)), scale)
        K[0, 1] = 3.
        with self.assertRaisesRegex(ValueError, 'symmetric'):
            solve(K, f, np.empty((0, 6)))

    def test_feasibility_fixture_rejects_uncovered_analysis_and_member_types(self):
        for mode in ('release', 'truss', 'p_delta', 'spatial'):
            p = beam(nodal=(0., 0., 0.), distributed=(0., 0.))
            if mode == 'release':
                p.members['M1'].release_end_y = True
            elif mode == 'truss':
                p.members['M1'].kind = 'truss'
            elif mode == 'p_delta':
                p.analysis_method = mode
            else:
                p = SpatialProject()
            with self.assertRaisesRegex(ValueError, 'unreleased planar linear'):
                assemble(p)


if __name__ == '__main__':
    unittest.main()
