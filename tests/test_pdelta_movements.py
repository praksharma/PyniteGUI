"""Prescribed-motion P-Delta: continuum fields, independent energy and failures."""
import math
import pickle
import unittest
from unittest.mock import patch

import numpy as np

from pdelta_movement_reference import axial_strain_force, column_field, constrained_tip
from test_qt_nonlinear import column, solve
from test_spatial_inclined import cantilever
from pynitegui.qt.analysis import model_signature
from pynitegui.qt.analysis_method import analysis_method_issue
from pynitegui.qt.equilibrium import check_equilibrium
from pynitegui.qt.model import Load
from pynitegui.qt.spatial_model import SpatialLoad
from pynitegui.qt.spatial_conversion import to_spatial
from pynitegui.qt.support_axes import support_normal
from pynitegui.qt.support_movements import movement_fields


class PDeltaMovementTests(unittest.TestCase):
    def test_continuum_reference_reduces_to_closed_form_limits(self):
        EI, L, force, moment, q, u0, theta = 2.9e6, 240., 1.7, 3., .002, .03, -.001
        linear = column_field(L, EI, 0., force, moment, q, u0, theta)
        expected = u0-theta*L+force*L**3/(3*EI)-moment*L**2/(2*EI)+q*L**4/(8*EI)
        self.assertAlmostEqual(linear['tip_translation'], expected, places=11)
        for P in (40., -40.):
            k = math.sqrt(abs(P)/EI)
            arm = (math.tan(k*L) if P > 0 else math.tanh(k*L))/k
            secant = 1/(math.cos(k*L) if P > 0 else math.cosh(k*L))
            result = column_field(L, EI, P, force, moment, base_translation=u0, base_rotation=theta)
            self.assertAlmostEqual(result['tip_translation'], u0-theta*arm+force/P*(arm-L)-moment/P*(secant-1), places=11)
            self.assertAlmostEqual(result['tip_rotation'], theta*secant-force/P*(secant-1)+moment/EI*arm, places=12)

    def test_moving_base_compression_tension_and_zero_cases_converge_to_continuum(self):
        for spatial in (False, True):
            for ratio in (.4, -.4):
                errors = []
                for segments in (1, 4, 24):
                    p, tip, compression = column(segments, ratio)
                    p.nodes['N1'].settlement_x = .03
                    p.nodes['N1'].settlement_y = -.02
                    p.nodes['N1'].settlement_rz = .001
                    p.loads['Couple'] = Load('Couple', tip, 'MZ', 2.)
                    p.combinations = {'Service': {'Case 1': 1.}, 'Reverse': {'Case 1': -1.7}, 'Zero': {'Case 1': 0.}}
                    if spatial:
                        p = to_spatial(p)
                    before = p.to_dict()
                    result = pickle.loads(pickle.dumps(solve(p)))
                    self.assertEqual(before, p.to_dict())
                    for combo, factor in (('Service', 1.), ('Reverse', -1.7), ('Zero', 0.)):
                        axial = axial_strain_force(-compression*factor, p.E*p.A)
                        reference = column_field(240., p.E*100., -axial, factor, 2.*factor,
                            base_translation=.03, base_rotation=.001)
                        selected = result.for_combination(combo)
                        if combo == 'Service':
                            errors.append(abs(selected.displacements[tip][0]-reference['tip_translation']))
                        for name, node in p.nodes.items():
                            if segments != 24:
                                continue
                            state = reference['sample']([node.y])[0]
                            np.testing.assert_allclose(np.array(selected.displacements[name])[[0, 1, 5] if spatial else [0, 1, 2]],
                                [state[0], -.02+axial*node.y/(p.E*p.A), -state[1]], rtol=1e-6, atol=1e-7)
                        if segments == 24:
                            values = np.array(selected.reactions['N1'])[[0, 1, 5] if spatial else [0, 1, 2]]
                            np.testing.assert_allclose(values, [reference['base_force'], compression*factor, reference['base_moment']], rtol=2e-6, atol=2e-6)
                            for name, member in p.members.items():
                                solver = selected.solver.members[name]
                                station = .37*solver.L()
                                local = np.array([solver.deflection(axis, station, combo) for axis in ('dx', 'dy', 'dz')])
                                actual = solver.T()[:3, :3].T @ local
                                expected = reference['sample']([p.nodes[member.start].y+station])[0, 0]
                                # Engine interior P-Delta interpolation remains
                                # approximate; resolve it by member refinement.
                                self.assertLess(abs(actual[0]-expected), 1e-5*max(1., abs(reference['tip_translation'])))
                        self.assertTrue(check_equilibrium(p, selected).passed)
                        np.testing.assert_allclose(np.array(selected.displacements['N1'])[[0, 1, 5] if spatial else [0, 1, 2]], [.03, -.02, .001], atol=1e-13)
                    self.assertEqual(result.model_signature, model_signature(p))
                # The three entries per mesh are deliberately not superposed.
                self.assertGreater(errors[0], errors[1])
                self.assertGreater(errors[1], errors[2])
                self.assertLess(errors[-1], 1e-6)

    def test_prescribed_shortening_generates_preload_even_with_zero_applied_loads(self):
        for spatial in (False, True):
            p, tip, compression = column(12)
            p.loads.clear()
            p.nodes['N1'].settlement_x = .025
            p.nodes['N1'].settlement_rz = -.0008
            end = p.nodes[tip]
            end.support = 'custom'
            end.restraint_x = end.restraint_y = True
            end.settlement_y = -compression*240/(p.E*p.A)
            end.settlement_x = .08
            p.combinations = {'Zero': {'Case 1': 0.}, 'Reverse': {'Case 1': -2.}}
            if spatial:
                p = to_spatial(p)
            r = solve(p)
            reference = column_field(240., p.E*100., compression,
                base_translation=.025, base_rotation=-.0008, tip_translation=.08)
            states = reference['sample']([node.y for node in p.nodes.values()])
            for combo in p.combinations:
                selected = r.for_combination(combo)
                np.testing.assert_allclose([selected.displacements[name][0] for name in p.nodes], states[:, 0], atol=1e-7)
                base = np.array(selected.reactions['N1'])[[0, 1, 5] if spatial else [0, 1, 2]]
                np.testing.assert_allclose(base, [reference['base_force'], compression-compression**2/(p.E*p.A), reference['base_moment']], rtol=2e-6, atol=1e-6)
                self.assertAlmostEqual(selected.reactions[tip][0], reference['tip_force'], delta=1e-6)
                self.assertTrue(check_equilibrium(p, selected).passed)
            np.testing.assert_allclose(r.for_combination('Zero').displacements[tip], r.for_combination('Reverse').displacements[tip], atol=1e-12)

    def test_biaxial_spatial_rotation_settlement_uniform_load_and_ground_spring(self):
        planar, tip, compression = column(12)
        p = to_spatial(planar, 'spatial')
        base = p.nodes['N1']
        base.settlement_x, base.settlement_z = .03, -.02
        base.settlement_rx, base.settlement_rz = -.0004, .0007
        p.loads['Side'] = SpatialLoad('Side', tip, 'FZ', -.8)
        p.loads['Couple'] = SpatialLoad('Couple', tip, 'MX', 2.)
        p.nodes[tip].spring_x = 2.
        for name in p.members:
            p.loads['q'+name] = SpatialLoad('q'+name, name, 'FX', .002, position=0., kind='distributed', end_magnitude=.002)
        r = solve(p)
        axial = axial_strain_force(-compression, p.E*p.A)
        x = column_field(240., p.E*100., -axial, 1., pressure=.002,
            base_translation=.03, base_rotation=.0007, spring=2.)
        z = column_field(240., p.E*100., -axial, -.8, -2., base_translation=-.02, base_rotation=.0004)
        np.testing.assert_allclose(np.array(r.displacements[tip])[[0, 2, 3, 5]],
            [x['tip_translation'], z['tip_translation'], -z['tip_rotation'], x['tip_rotation']], rtol=3e-6, atol=1e-7)
        self.assertAlmostEqual(r.reactions[tip][0], -2.*r.displacements[tip][0], places=9)
        np.testing.assert_allclose(np.array(r.reactions['N1'])[[0, 2, 3, 5]],
            [x['base_force'], z['base_force'], -z['base_moment'], x['base_moment']], rtol=3e-6, atol=1e-6)

    def test_inclined_normal_and_six_dof_base_motion_against_energy_kkt_reference(self):
        for angles in ((0., 0.), (31., 24.), (-123., -47.)):
            for springs in ((0.,)*6, (5., 7., 11., 100., 200., 300.)):
                if angles == (0., 0.) and any(springs):
                    continue
                p = cantilever(angles, springs)
                p.analysis_method = 'p_delta'
                node = p.nodes['N2']
                node.settlement_normal = .006
                constraints = [np.r_[support_normal(node), np.zeros(3)]]
                targets = [.006]
                if angles == (-123., -47.) and not any(springs):
                    node.restraint_ry, node.settlement_ry = True, .0004
                    constraints.append(np.eye(6)[4])
                    targets.append(.0004)
                base = np.array((.01, -.02, .015, .0001, -.0002, .0003))
                for key, value in zip(movement_fields(p.nodes['N1'])[:-1], base):
                    setattr(p.nodes['N1'], key, float(value))
                material, section = p.materials[p.default_material], p.sections[p.default_section]
                result = solve(p)
                for combo, factor in (('Service', 1.), ('Reverse', -1.7), ('Zero', 0.)):
                    force = factor*np.array((3., -2., 1., 7., -4., 5.))
                    displacement, reaction, _ = constrained_tip(material.E, material.G, section.A,
                        section.Iy, section.Iz, section.J, 120., base, force, constraints, targets, node.springs)
                    selected = result.for_combination(combo)
                    np.testing.assert_allclose(selected.displacements['N2'], displacement[6:], rtol=1e-8, atol=1e-10)
                    np.testing.assert_allclose(selected.reactions['N2'], reaction[6:], rtol=1e-8, atol=1e-7)
                    np.testing.assert_allclose(selected.reactions['N1'], reaction[:6], rtol=1e-8, atol=1e-7)
                    self.assertAlmostEqual(support_normal(node) @ np.array(selected.displacements['N2'][:3]), .006, places=12)
                    self.assertTrue(check_equilibrium(p, selected).passed)

    def test_planar_normal_prescription_and_conversion_against_independent_energy(self):
        from test_inclined_supports import supported
        for angle in (-73., 31., 90.):
            p = supported(angle)
            p.loads = {'F': Load('F', 'N2', 'FX', -3.), 'V': Load('V', 'N2', 'FY', -2.),
                       'M': Load('M', 'N2', 'MZ', 7.)}
            p.analysis_method = 'p_delta'
            p.nodes['N1'].settlement_x, p.nodes['N1'].settlement_y, p.nodes['N1'].settlement_rz = .01, -.02, .0003
            p.nodes['N2'].settlement_normal = .006
            result, converted = solve(p), solve(to_spatial(p))
            normal = np.r_[support_normal(p.nodes['N2']), np.zeros(4)]
            rows = [normal, *np.eye(6)[[2, 3, 4]]]
            section, material = p.sections[p.default_section], p.materials[p.default_material]
            for combo, factor in (('Service', 1.), ('Reverse', -1.7), ('Zero', 0.)):
                displacement, reaction, _ = constrained_tip(material.E, material.G, section.A, section.Iy,
                    section.Iz, section.J, 120., [.01, -.02, 0., 0., 0., .0003],
                    factor*np.array((-3., -2., 0., 0., 0., 7.)), rows, [.006, 0., 0., 0.], np.zeros(6))
                expected = displacement[[6, 7, 11]]
                np.testing.assert_allclose(result.for_combination(combo).displacements['N2'], expected, atol=1e-10)
                np.testing.assert_allclose(result.for_combination(combo).reactions['N2'], reaction[[6, 7, 11]], atol=1e-7)
                np.testing.assert_allclose(np.array(converted.for_combination(combo).displacements['N2'])[[0, 1, 5]], expected, atol=1e-10)

    def test_zero_force_rigid_translation_buckling_and_iteration_failure(self):
        for spatial in (False, True):
            p, tip, _ = column(6)
            p.loads.clear()
            p.nodes['N1'].settlement_x = .03
            p.nodes['N1'].settlement_y = -.02
            if spatial:
                p = to_spatial(p, 'spatial')
                p.nodes['N1'].settlement_z = .04
            r = solve(p)
            for name in p.nodes:
                np.testing.assert_allclose(r.displacements[name][:2], [.03, -.02], atol=1e-12)
            np.testing.assert_allclose(list(r.reactions.values()), 0., atol=1e-7)
            p, tip, compression = column(12, 1.2)
            p.loads.clear()
            p.nodes[tip].support = 'custom'
            p.nodes[tip].restraint_y = True
            p.nodes[tip].settlement_y = -compression*240/(p.E*p.A)
            if spatial:
                p = to_spatial(p, 'spatial')
            with self.assertRaisesRegex(ValueError, 'Unstable|ill-conditioned'):
                solve(p)
        p, _, _ = column()
        p.nodes['N1'].settlement_x = .03
        from pynitegui.qt.inclined_supports import FreeEquilibriumError
        with patch('pynitegui.qt.inclined_supports.recover_reactions', side_effect=FreeEquilibriumError('not converged')) as recovered:
            with self.assertRaisesRegex(ValueError, 'P-Delta support-constraint.*not converged'):
                solve(p)
        self.assertEqual(recovered.call_count, 30)

    def test_existing_entity_restrictions_still_reject_with_imposed_movements(self):
        from pynitegui.qt.examples import example_project
        for key in ('truss', '3d_released_beam', '3d_slab_frame', 'shear_release'):
            p = example_project(key)
            p.analysis_method = 'p_delta'
            base = next(node for node in p.nodes.values() if node.restraints[0])
            base.settlement_x = .01
            self.assertIsNotNone(analysis_method_issue(p))
            with self.assertRaises(ValueError):
                solve(p)

    def test_planar_moment_releases_keep_member_side_moments_zero(self):
        # Pin-ended straight chord under prescribed shortening and unequal
        # transverse support motion: EI*w''=0 and V=P*w' everywhere.
        for compression in (-40., 40.):
            p, tip, _ = column(12)
            p.loads.clear()
            p.nodes['N1'].settlement_x = .025
            p.nodes['N1'].settlement_rz = .007
            end = p.nodes[tip]
            end.support = 'fixed'
            end.settlement_x, end.settlement_rz = .08, -.005
            end.settlement_y = -compression*240/(p.E*p.A)
            p.members['M1'].release_start = True
            p.members['M12'].release_end = True
            result = solve(p)
            for name, node in p.nodes.items():
                self.assertAlmostEqual(result.displacements[name][0], .025+(.08-.025)*node.y/240., places=10)
            self.assertAlmostEqual(result.reactions['N1'][0], compression*(.08-.025)/240., places=8)
            self.assertAlmostEqual(result.reactions[tip][0], -compression*(.08-.025)/240., places=8)
            self.assertAlmostEqual(result.reactions['N1'][2], 0., places=8)
            self.assertAlmostEqual(result.reactions[tip][2], 0., places=8)
            for name, index in (('M1', 5), ('M12', 11)):
                member = next(iter(result.solver.members[name].sub_members.values()))
                self.assertAlmostEqual(member.f(result.combination)[index, 0], 0., places=8)


if __name__ == '__main__':
    unittest.main()
