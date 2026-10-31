"""Production inclined rollers against independent beam mechanics."""
import contextlib
from copy import deepcopy
import io
import pickle
import unittest
from unittest.mock import patch

import numpy as np

from inclined_reference import cantilever, pinned_beam, rotation
from inclined_validation import beam
from pynitegui.qt.analysis import analyze, model_signature
from pynitegui.qt.equilibrium import check_equilibrium
from pynitegui.qt.model import Project
from pynitegui.qt.spatial_model import SpatialProject
from pynitegui.qt.spatial_conversion import to_spatial
from pynitegui.qt.automation_core import batch_candidate, AutomationError
from pynitegui.qt.geometry_tools import plan_transform


def solve(project):
    with contextlib.redirect_stdout(io.StringIO()):
        return analyze(project)


def supported(angle=27., beam_angle=0., springs=(0., 0., 0.)):
    p = beam(angle=beam_angle)
    p.nodes['N1'].support = 'fixed'
    node = p.nodes['N2']
    node.support, node.support_angle = 'inclined', angle
    node.spring_x, node.spring_y, node.spring_rz = springs
    return p


class InclinedSupportTests(unittest.TestCase):
    def test_tip_flexibility_global_reactions_fields_combinations_and_transport(self):
        for beam_angle in (0., 37., 90., -143.):
            for angle in (-170., -90., -30., 0., 25., 89.9, 90., 135., 180.):
                p = supported(angle, beam_angle)
                before = p.to_dict()
                result = pickle.loads(pickle.dumps(solve(p)))
                self.assertEqual(p.to_dict(), before)
                expected_d, expected_r = cantilever(angle, beam_angle)
                for combo, factor in (('Service', 1.), ('Reverse', -1.7), ('Zero', 0.)):
                    r = result.for_combination(combo)
                    np.testing.assert_allclose(r.displacements['N2'], expected_d*factor, atol=1e-10)
                    np.testing.assert_allclose(r.reactions['N2'], expected_r*factor, atol=1e-8)
                    self.assertTrue(check_equilibrium(p, r).passed)
                    sub = next(iter(r.solver.members['M1'].sub_members.values()))
                    # Ordinary engine member recovery consumes the global
                    # physical node motions, never the tangent coordinates.
                    np.testing.assert_allclose(sub.D(combo).ravel()[[6, 7, 11]], expected_d*factor, atol=1e-10)
                    np.testing.assert_allclose(sub.F(combo).ravel()[[6, 7, 11]], (expected_r+rotation(beam_angle) @ (3., -2., 7.))*factor, atol=1e-8)

    def test_pin_roller_nodal_and_member_fields_under_uniform_load(self):
        for fractions in ((0., 1.), (0., .17, .53, 1.), tuple(np.linspace(0., 1., 9))):
            for angle in (-65., 0., 17., 60.):
                p = beam(fractions=fractions, nodal=(0., 0., 0.), distributed=(0., -.005))
                names = list(p.nodes)
                p.nodes[names[0]].support = 'pin'
                p.nodes[names[-1]].support = 'inclined'
                p.nodes[names[-1]].support_angle = angle
                result = solve(p)
                for combo, factor in (('Service', 1.), ('Reverse', -1.7), ('Zero', 0.)):
                    r = result.for_combination(combo)
                    expected, left, right = pinned_beam(np.array(fractions)*120., angle)
                    np.testing.assert_allclose([r.displacements[name] for name in names], expected*factor, atol=1e-10)
                    np.testing.assert_allclose([r.reactions[name] for name in (names[0], names[-1])], np.array((left, right))*factor, atol=1e-8)
                    self.assertTrue(check_equilibrium(p, r).passed)
                    for member in p.members.values():
                        start = p.nodes[member.start].x-17.
                        L = p.nodes[member.end].x-p.nodes[member.start].x
                        for station in np.linspace(0., L, 5):
                            d = pinned_beam(np.array((start+station,)), angle)[0][0]*factor
                            physical = r.solver.members[member.name]
                            self.assertAlmostEqual(physical.deflection('dx', station, combo), d[0], places=9)
                            self.assertAlmostEqual(physical.deflection('dy', station, combo), d[1], places=9)

    def test_global_spring_reactions_are_separate_from_rigid_normal_reaction(self):
        for beam_angle, angle, springs in ((0., 27., (500., 0., 0.)), (37., -26., (0., 700., 200.)),
                                          (-73., 61., (50000., 300., 900.))):
            p = supported(angle, beam_angle, springs)
            result = solve(p)
            d, rigid = cantilever(angle, beam_angle, springs=springs)
            for combo, factor in (('Service', 1.), ('Reverse', -1.7), ('Zero', 0.)):
                r = result.for_combination(combo)
                np.testing.assert_allclose(r.displacements['N2'], d*factor, atol=1e-10)
                np.testing.assert_allclose(r.reactions['N2'], (rigid-np.array(springs)*d)*factor, atol=1e-8)
                row = r.solver._pynitegui_support_reactions[combo]['N2']
                np.testing.assert_allclose(row['rigid_reaction'], rigid*factor, atol=1e-8)
                np.testing.assert_allclose(row['spring_reaction'], -np.array(springs)*d*factor, atol=1e-8)
                self.assertTrue(check_equilibrium(p, r).passed)

    def test_version_migration_strict_flags_spatial_boundary_units_and_signature(self):
        p = supported()
        data = p.to_dict()
        self.assertEqual(data['version'], 33)
        self.assertEqual(Project.from_dict(data).to_dict(), data)
        for bad in (True, None, float('nan'), float('inf'), 181., '27'):
            copy = deepcopy(data)
            copy['nodes']['N2']['support_angle'] = bad
            with self.assertRaises(ValueError):
                Project.from_dict(copy)
        for old in (1, 21, 23, 25):
            copy = deepcopy(data)
            copy['version'] = old
            with self.assertRaises(ValueError):
                Project.from_dict(copy)
        copy = deepcopy(data)
        del copy['nodes']['N1']['support_angle']
        with self.assertRaisesRegex(ValueError, 'Missing support_angle'):
            Project.from_dict(copy)
        legacy = beam().to_dict()
        legacy['version'] = 25
        for node in legacy['nodes'].values():
            node.pop('support_angle')
        restored = Project.from_dict(legacy)
        self.assertTrue(all(node.support_angle == 0. for node in restored.nodes.values()))
        signature = model_signature(p)
        p.unit_system = 'si'
        self.assertEqual(model_signature(p), signature)
        spatial = to_spatial(p)
        self.assertEqual(spatial.to_dict()['version'], 40)
        self.assertEqual(spatial.nodes['N2'].support, 'inclined')
        spatial.nodes['N1'].support_angle = 27.
        with self.assertRaisesRegex(ValueError, 'spatial'):
            spatial.validate()

    def test_model_gates_and_normal_spring_conflicts(self):
        for angle, spring in ((0., 'spring_y'), (90., 'spring_x')):
            p = supported(angle)
            setattr(p.nodes['N2'], spring, 500.)
            with self.assertRaisesRegex(ValueError, 'rigid restraint'):
                p.validate()

    def test_unsupported_near_mechanisms_and_corrupt_free_recovery_fail(self):
        for angle in (90., 89.999999, 90.000001):
            p = supported(angle)
            p.nodes['N1'].support = 'pin'
            p.loads.clear()
            with self.assertRaisesRegex(ValueError, 'rigid body|Unstable|ill-conditioned'):
                solve(p)
        from pynitegui.qt.inclined_supports import factor_stiffness
        def broken(*args):
            transform, factor, scale = factor_stiffness(*args)
            class Bad:
                def solve(self, rhs):
                    return factor.solve(rhs)+.001
            return transform, Bad(), scale
        with patch('pynitegui.qt.inclined_supports.factor_stiffness', side_effect=broken):
            with self.assertRaisesRegex(ValueError, 'physical equilibrium'):
                solve(supported())

    def test_atomic_mcp_and_global_support_copy_semantics(self):
        p = supported()
        before = p.to_dict()
        candidate = batch_candidate(p, [{'op': 'put', 'collection': 'nodes', 'key': 'N2', 'value': {'support_angle': -31.}}])
        self.assertEqual(candidate.nodes['N2'].support_angle, -31.)
        self.assertEqual(p.to_dict(), before)
        with self.assertRaises(AutomationError):
            batch_candidate(p, [{'op': 'put', 'collection': 'nodes', 'key': 'N2', 'value': {'support_angle': 200.}}])
        plan = plan_transform(p, [('members', 'M1')], 'repeat', offset=(0., 240., 0.), copy_supports=True)
        copy = plan.definition
        self.assertEqual(sum(node.support == 'inclined' and node.support_angle == 27. for node in copy.nodes.values()), 2)
        plain = plan_transform(p, [('members', 'M1')], 'repeat', offset=(0., 240., 0.), copy_supports=False)
        copy = plain.definition
        self.assertEqual(sum(node.support == 'inclined' for node in copy.nodes.values()), 1)

    def test_sparse_stability_branch_and_nonconvergence_fail_closed(self):
        from scipy.sparse.linalg import eigsh, ArpackNoConvergence
        p = beam(fractions=tuple(np.linspace(0., 1., 305)), nodal=(0., -2., 0.), distributed=(0., 0.))
        for node in p.nodes.values():
            node.support = 'roller'
        p.nodes['N1'].support = 'pin'
        tip = next(reversed(p.nodes))
        p.nodes[tip].support, p.nodes[tip].support_angle = 'inclined', 27.
        with patch('pynitegui.qt.inclined_supports.eigsh', wraps=eigsh) as spectral:
            result = solve(p)
        self.assertTrue(spectral.called)
        self.assertTrue(check_equilibrium(p, result).passed)
        with patch('pynitegui.qt.inclined_supports.eigsh', side_effect=ArpackNoConvergence('test', None, None)):
            with self.assertRaisesRegex(ValueError, 'did not converge'):
                solve(p)
