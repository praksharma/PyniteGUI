"""Independent axial/beam flexibility, connection motion and mechanism checks."""
from copy import deepcopy
import contextlib
import io
import math
import pickle
import unittest
from unittest.mock import patch

import numpy as np

from pynitegui.qt.analysis import analyze, model_signature
from pynitegui.qt.equilibrium import check_equilibrium
from pynitegui.qt.examples import example_project
from pynitegui.qt.model import Material, Project, Section
from pynitegui.qt.spatial_conversion import to_spatial
from pynitegui.qt.spatial_model import SpatialProject, SpatialLoad
from pynitegui.qt.spatial_releases import RELEASE_FIELDS, TRANSLATION_FIELDS
from pynitegui.qt.spatial_results import member_axes, member_end_translations, member_values, sampled_member
from pynitegui.qt.units import UNIT_SYSTEMS


def beam(vector=(120., 0., 0.), roll=0., end='end', cantilever=False):
    p = SpatialProject()
    p.set_material(Material('Test', E=30000., nu=.25, rho=0.))
    p.set_section(Section('Test', A=8., Iy=20., Iz=80., J=5.))
    p.default_material = p.default_section = 'Test'
    p.add_member((17., -31., 49.), tuple(np.array((17., -31., 49.))+vector))
    p.nodes['N1'].support = p.nodes['N2'].support = 'fixed'
    member = p.members['M1']
    member.roll = roll
    for axis in ('x','y','z'):
        setattr(member, f'release_{end}_{axis}', True)
    if cantilever:
        setattr(member, f'release_{end}', True)
        setattr(member, f'release_{end}_ry', True)
    for direction, q in (('Fx',.002),('Fy',-.001),('Fz',.0006)):
        p.loads[direction] = SpatialLoad(direction,'M1',direction,q,0.,'distributed',q)
    p.set_combination('Reverse', {'Case 1':-1.7})
    p.set_combination('Zero', {'Case 1':0.})
    return p


def solve(project):
    with contextlib.redirect_stdout(io.StringIO()):
        return analyze(project)


class SpatialTranslationReleaseTests(unittest.TestCase):
    def test_corrupt_recovered_end_motion_cannot_escape_as_an_accepted_local_result(self):
        result = solve(beam())
        sub = next(iter(result.solver.members['M1'].sub_members.values()))
        sub._released_displacements.clear()
        direct = np.linalg.solve
        with patch('pynitegui.qt.released_member.np.linalg.solve',side_effect=lambda a,b:direct(a,b)+.001):
            with self.assertRaisesRegex(ValueError,'released-end physical equilibrium'):
                sub.d('Service')

    def test_uniform_guided_and_cantilever_fields_for_either_end_oblique_roll_and_reversal(self):
        for vector, roll in (((120.,0.,0.),0.),((72.,64.,80.),31.),((0.,-120.,0.),-47.),((-72.,-64.,-80.),128.)):
            for end in ('start','end'):
                for cantilever in (False,True):
                    with self.subTest(vector=vector,end=end,cantilever=cantilever):
                        p = beam(vector,roll,end,cantilever)
                        before = p.to_dict()
                        r = pickle.loads(pickle.dumps(solve(p)))
                        self.assertEqual(p.to_dict(),before)
                        L, E, A, Iy, Iz = math.dist(p.nodes['N1'].coords,p.nodes['N2'].coords),30000.,8.,20.,80.
                        axes = member_axes(p,'M1')
                        for combination, factor in (('Service',1.),('Reverse',-1.7),('Zero',0.)):
                            result = r.for_combination(combination)
                            member = result.solver.members['M1']
                            sub = next(iter(member.sub_members.values()))
                            d = sub.d(combination).ravel()
                            free = 0 if end=='start' else 6
                            np.testing.assert_allclose(sub.f(combination).ravel()[free:free+3],0.,atol=1e-10)
                            for x in np.linspace(0.,L,7):
                                s = x if end=='end' else L-x
                                # Independent integration of EA u''=-q and EI v''''=q.
                                u = .002*factor*(L*L-(L-s)**2)/(2*E*A)
                                polynomial = s*s*(s*s-4*L*s+(6 if cantilever else 4)*L*L)/24
                                expected = [u,-.001*factor*polynomial/(E*Iz),.0006*factor*polynomial/(E*Iy)]
                                actual = [member.deflection(axis,x,combination) for axis in ('dx','dy','dz')]
                                np.testing.assert_allclose(actual,expected,atol=2e-10)
                            np.testing.assert_allclose(d[free:free+3], member_end_translations(result,'M1')[0 if end=='start' else 1],atol=1e-12)
                            self.assertTrue(check_equilibrium(p,result).passed)
                            for node in p.nodes:
                                np.testing.assert_allclose(result.displacements[node][:3],0.,atol=1e-12)
                            fixed_node = 'N1' if end=='end' else 'N2'
                            np.testing.assert_allclose(axes @ result.reactions[fixed_node][:3],-L*factor*np.array([.002,-.001,.0006]),atol=1e-9)
                            if cantilever:
                                sign = 1. if end=='end' else -1.
                                np.testing.assert_allclose(d[[free+4,free+5]],[-sign*.0006*factor*L**3/(6*E*Iy),sign*-.001*factor*L**3/(6*E*Iz)],atol=1e-11)
                            else:
                                np.testing.assert_allclose(d[[free+4,free+5]],0.,atol=1e-12)
                        points, _, motion = sampled_member(p,r,'M1')
                        np.testing.assert_allclose(motion[-1 if end=='end' else 0],member_end_translations(r,'M1')[0 if end=='start' else 1] @ axes,atol=1e-10)

    def test_partial_varying_and_point_loads_match_independent_beam_flexibility(self):
        for cantilever in (False,True):
            p = beam((72.,64.,80.),31.,cantilever=cantilever)
            p.loads.clear()
            L = math.dist(p.nodes['N1'].coords,p.nodes['N2'].coords)
            for direction, scale in (('Fx',.3),('Fy',-1.),('Fz',.7)):
                p.loads[direction] = SpatialLoad(direction,'M1',direction,2*scale,.37)
                p.loads[direction+'q'] = SpatialLoad(direction+'q','M1',direction,.001*scale,.19,'distributed',.004*scale,.81)
            r = solve(p)
            member = r.solver.members['M1']
            gauss, weights = np.polynomial.legendre.leggauss(8)
            for x in np.linspace(0,L,11):
                def compliance(s,axial):
                    if axial:
                        return min(x,s)/(30000.*8.)
                    value = x*x*(3*s-x)/6 if x<=s else s*s*(3*x-s)/6
                    return value if cantilever else value-s*s*x*x/(4*L)
                for direction, scale, inertia, axis in (('Fx',.3,None,'dx'),('Fy',-1.,80.,'dy'),('Fz',.7,20.,'dz')):
                    expected = 2*scale*compliance(.37*L,inertia is None)
                    # Split at the probe because the point-load Green function
                    # is polynomial on either side, with a known derivative jump.
                    cuts = sorted({.19*L,.81*L,*([x] if .19*L<x<.81*L else [])})
                    for left,right in zip(cuts,cuts[1:]):
                        stations = left+(gauss+1)*(right-left)/2
                        for station,weight in zip(stations,weights):
                            q = scale*(.001+.003*(station/L-.19)/.62)
                            expected += weight*(right-left)/2*q*compliance(station,inertia is None)
                    if inertia is not None:
                        expected /= 30000.*inertia
                    self.assertAlmostEqual(member.deflection(axis,x,'Service'),expected,places=9)
            self.assertTrue(check_equilibrium(p,r).passed)

    def test_connected_joint_or_spring_motion_is_separate_from_released_member_end(self):
        for spring in (False,True):
            p = beam()
            member = p.members['M1']
            member.release_end_x = member.release_end_z = False
            joint = p.nodes['N2']
            joint.support = 'custom'
            joint.restraint_x = joint.restraint_z = joint.restraint_rx = joint.restraint_ry = joint.restraint_rz = True
            if spring:
                joint.spring_y = 100.
                stiffness = 100.
            else:
                p.add_member(joint.coords,(137.,89.,49.))
                p.nodes['N3'].support = 'fixed'
                stiffness = 30000.*8./120.
            p.loads['Joint'] = SpatialLoad('Joint','N2','FY',2.)
            r = solve(p)
            self.assertAlmostEqual(r.displacements['N2'][1],2./stiffness)
            self.assertAlmostEqual(member_end_translations(r,'M1')[1][1],-.001*120**4/(24*30000*80))
            self.assertAlmostEqual(r.solver.members['M1'].shear('Fy',120.,'Service'),0.,places=9)
            self.assertTrue(check_equilibrium(p,r).passed)

    def test_real_free_joint_translation_and_other_unsupported_workflows_are_rejected(self):
        for load in (False,True):
            p = beam()
            p.nodes['N2'].support = 'custom'
            p.nodes['N2'].restraint_x = p.nodes['N2'].restraint_z = True
            p.nodes['N2'].restraint_rx = p.nodes['N2'].restraint_ry = p.nodes['N2'].restraint_rz = True
            if load:
                p.loads['Bad'] = SpatialLoad('Bad','N2','FY',1.)
            before = p.to_dict()
            with self.assertRaisesRegex(ValueError,'unstable|singular|stiffness'):
                solve(p)
            self.assertEqual(before,p.to_dict())
        for field in TRANSLATION_FIELDS:
            p = beam()
            for key in RELEASE_FIELDS:
                setattr(p.members['M1'],key,key==field)
            p.analysis_method = 'p_delta'
            with self.assertRaisesRegex(ValueError,'Linear elastic'):
                solve(p)
        p = example_project('3d_slab_frame')
        p.members['M1'].release_end_z = True
        with self.assertRaisesRegex(ValueError,'frame-only'):
            solve(p)

    def test_validation_migration_unit_persistence_and_signatures(self):
        p = beam()
        data = p.to_dict()
        self.assertEqual(data['version'],40)
        for field in TRANSLATION_FIELDS:
            bad = deepcopy(data)
            bad['members']['M1'].pop(field)
            with self.assertRaisesRegex(ValueError,'Missing spatial translational'):
                Project.from_dict(bad)
            bad = p.clone()
            setattr(bad.members['M1'],field,1)
            with self.assertRaisesRegex(ValueError,'boolean'):
                bad.validate()
        for overrides in ({'release_start_x':True},{'release_start_y':True},{'release_start_z':True},
                          {'release_start':True,'release_end':True},{'release_start_ry':True,'release_end_ry':True},{'kind':'truss'}):
            bad = p.clone()
            for field,value in overrides.items():
                setattr(bad.members['M1'],field,value)
            with self.assertRaisesRegex(ValueError,'both ends|internally unstable|clear manual'):
                bad.validate()
        for version in (28,30):
            old = deepcopy(data)
            old['version'] = version
            for field in TRANSLATION_FIELDS:
                old['members']['M1'].pop(field)
            before = deepcopy(old)
            restored = Project.from_dict(old)
            self.assertEqual(old,before)
            self.assertTrue(all(not getattr(restored.members['M1'],field) for field in TRANSLATION_FIELDS))
            old['members']['M1']['release_end_y'] = True
            with self.assertRaisesRegex(ValueError,'version 32'):
                Project.from_dict(old)
        signature = model_signature(p)
        for units in UNIT_SYSTEMS:
            p.unit_system = units
            restored = Project.from_dict(p.to_dict())
            self.assertEqual(restored.to_dict(),p.to_dict())
            self.assertEqual(model_signature(restored),signature)

    def test_split_preserves_outer_releases_loads_and_the_solved_fields(self):
        p = beam((72.,64.,80.),31.)
        original = solve(p)
        L = original.solver.members['M1'].L()
        names = p.split_member('M1',.4)
        self.assertEqual(p.members[names[0]].release_labels,('None','None'))
        self.assertEqual(p.members[names[1]].release_labels,('None','DX, DY, DZ'))
        result = solve(p)
        for name in ('N1','N2'):
            np.testing.assert_allclose(result.reactions[name],original.reactions[name],atol=1e-8)
        for fraction in (.2,.7):
            member = names[0 if fraction<.4 else 1]
            station = fraction*L if fraction<.4 else (fraction-.4)*L
            np.testing.assert_allclose(member_values(result,member,station),member_values(original,'M1',fraction*L),atol=1e-8)

    def test_planar_axial_and_shear_release_conversion_retains_member_and_joint_fields(self):
        for end in ('start','end'):
            p = Project()
            p.add_member((0.,0.),(120.,0.))
            p.nodes['N1'].support = p.nodes['N2'].support = 'fixed'
            for axis in ('x','y'):
                setattr(p.members['M1'],f'release_{end}_{axis}',True)
            from pynitegui.qt.model import Load
            p.loads['P'] = Load('P','M1','FY',-2.,.37)
            p.loads['Q'] = Load('Q','M1','FX',.002,.19,'distributed',.004,.81)
            p.set_combination('Reverse',{'Case 1':-1.7})
            before = p.to_dict()
            converted = to_spatial(p,offset=54.)
            for combination in ('Service','Reverse'):
                a,b = solve(p).for_combination(combination),solve(converted).for_combination(combination)
                for x in np.linspace(0.,120.,9):
                    for direction in ('dx','dy'):
                        self.assertAlmostEqual(a.solver.members['M1'].deflection(direction,x,combination),b.solver.members['M1'].deflection(direction,x,combination),places=10)
                for node in p.nodes:
                    np.testing.assert_allclose(np.array(b.reactions[node])[[0,1,5]],a.reactions[node],atol=1e-8)
            self.assertEqual(p.to_dict(),before)

    def test_oblique_vertical_and_reversed_planar_conversion_preserves_global_load_meaning(self):
        from pynitegui.qt.model import Load
        for endpoint in ((72.,96.),(0.,-120.),(-72.,-96.)):
            p = Project()
            p.add_member((0.,0.),endpoint)
            p.nodes['N1'].support = p.nodes['N2'].support = 'fixed'
            p.members['M1'].release_start_x = p.members['M1'].release_end_y = True
            p.loads['P'] = Load('P','M1','FY',-2.,.37)
            p.loads['Q'] = Load('Q','M1','FX',.002,.19,'distributed',.004,.81)
            p.loads['M'] = Load('M','M1','MZ',3.,.71)
            converted = to_spatial(p,offset=-54.)
            a,b = solve(p),solve(converted)
            for node in p.nodes:
                np.testing.assert_allclose(np.array(b.reactions[node])[[0,1,5]],a.reactions[node],atol=1e-8)
            length = math.dist((0.,0.),endpoint)
            for x in np.linspace(0.,length,9):
                for axis in ('dx','dy'):
                    self.assertAlmostEqual(a.solver.members['M1'].deflection(axis,x,'Service'),b.solver.members['M1'].deflection(axis,x,'Service'),places=10)
