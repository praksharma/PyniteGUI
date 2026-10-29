"""Prescribed motions checked with beam laws, compliance and rigid-body fields."""
from copy import deepcopy
import math
import pickle
import unittest

import numpy as np
from pynitegui.qt.model import Load, Project
from pynitegui.qt.analysis import model_signature
from pynitegui.qt.equilibrium import check_equilibrium
from pynitegui.qt.spatial_model import SpatialProject, SpatialLoad
from pynitegui.qt.spatial_conversion import to_spatial
from pynitegui.qt.support_movements import movement_fields
from pynitegui.qt.support_axes import support_normal
from test_inclined_supports import solve, supported
from test_spatial_inclined import cantilever, compliance


def beam():
    p=Project();p.add_member((0.,0.),(120.,0.))
    p.nodes['N1'].support=p.nodes['N2'].support='fixed'
    p.combinations={'Load':{'Case 1':1.},'Reverse':{'Case 1':-1.7},'Zero':{'Case 1':0.}}
    return p


class SupportMovementTests(unittest.TestCase):
    def test_fixed_beam_settlements_rotations_fields_and_unfactored_combinations(self):
        p=beam();L=120.;E=p.E;I=p.Iz;A=p.A
        left,right=p.nodes.values()
        left.settlement_x=.02;left.settlement_y=.03;left.settlement_rz=-.002
        right.settlement_x=-.05;right.settlement_y=-.1;right.settlement_rz=.001
        p.loads={'Uniform':Load('Uniform','M1','FY',-.01,0.,'distributed',-.01,1.),'Point':Load('Point','N2','FY',-2.)}
        field=np.array((.03,-.002,-.1,.001))
        K=E*I/L**3*np.array(((12,6*L,-12,6*L),(6*L,4*L**2,-6*L,2*L**2),(-12,-6*L,12,-6*L),(6*L,2*L**2,-6*L,4*L**2)))
        before=p.to_dict();r=pickle.loads(pickle.dumps(solve(p)))
        self.assertEqual(before,p.to_dict())
        for combo,factor in (('Load',1.),('Reverse',-1.7),('Zero',0.)):
            selected=r.for_combination(combo)
            np.testing.assert_allclose(selected.displacements['N1'],(.02,.03,-.002),atol=1e-13)
            np.testing.assert_allclose(selected.displacements['N2'],(-.05,-.1,.001),atol=1e-13)
            axial=E*A/L*(.02+.05)
            bending=K@field+factor*np.array((.01*L/2,.01*L**2/12,.01*L/2+2.,-.01*L**2/12))
            np.testing.assert_allclose(selected.reactions['N1'],(axial,*bending[:2]),atol=1e-8)
            np.testing.assert_allclose(selected.reactions['N2'],(-axial,*bending[2:]),atol=1e-8)
            self.assertTrue(check_equilibrium(p,selected).passed)
            for x in np.linspace(0.,L,9):
                t=x/L
                expected=(1-3*t*t+2*t**3)*field[0]+L*(t-2*t*t+t**3)*field[1]+(3*t*t-2*t**3)*field[2]+L*(-t*t+t**3)*field[3]-.01*factor*x*x*(L-x)**2/(24*E*I)
                self.assertAlmostEqual(selected.solver.members['M1'].deflection('dy',x,combo),expected,places=9)
        converted=solve(to_spatial(p))
        for combo in p.combinations:
            for name in p.nodes:
                np.testing.assert_allclose(np.array(converted.for_combination(combo).reactions[name])[[0,1,5]],r.for_combination(combo).reactions[name],atol=1e-8)

    def test_settled_pin_roller_has_rigid_chord_and_no_artificial_moment(self):
        for released in (False,True):
            p=beam();p.nodes['N1'].support='pin';p.nodes['N2'].support='roller';p.nodes['N2'].settlement_y=-.12
            p.members['M1'].release_start=p.members['M1'].release_end=released
            r=solve(p)
            for combo in p.combinations:
                selected=r.for_combination(combo)
                np.testing.assert_allclose(list(selected.reactions.values()),0.,atol=1e-8)
                if released:self.assertIsNone(selected.displacements['N2'][2])
                for x in np.linspace(0.,120.,7):
                    self.assertAlmostEqual(selected.solver.members['M1'].deflection('dy',x,combo),-.001*x,places=10)

    def test_inclined_normal_movement_against_independent_compliance_and_spring_law(self):
        for angle in (-73.,0.,31.,90.):
            p=supported(angle);p.loads.clear();p.nodes['N2'].settlement_normal=-.07
            p.loads['F']=Load('F','N2','FY',-2.)
            L=120.;C=np.array(((L/(p.E*p.A),0.,0.),(0.,L**3/(3*p.E*p.Iz),L**2/(2*p.E*p.Iz)),(0.,L**2/(2*p.E*p.Iz),L/(p.E*p.Iz))))
            normal=np.r_[support_normal(p.nodes['N2']),0.]
            result=solve(p)
            converted=solve(to_spatial(p))
            for combo,factor in (('Service',1.),('Reverse',-1.7),('Zero',0.)):
                f=np.array((0.,-2.,0.))*factor
                reaction=normal*((-.07-normal@C@f)/(normal@C@normal))
                np.testing.assert_allclose(result.for_combination(combo).displacements['N2'],C@(f+reaction),atol=1e-11)
                np.testing.assert_allclose(result.for_combination(combo).reactions['N2'],reaction,atol=1e-8)
                np.testing.assert_allclose(np.array(converted.for_combination(combo).displacements['N2'])[[0,1,5]],C@(f+reaction),atol=1e-11)
                self.assertTrue(check_equilibrium(p,result.for_combination(combo)).passed)
        p=cantilever();p.nodes['N2'].settlement_normal=.04
        result=solve(p);C=compliance(p);normal=np.r_[support_normal(p.nodes['N2']),np.zeros(3)]
        for combo,factor in (('Service',1.),('Reverse',-1.7),('Zero',0.)):
            f=np.array((3.,-2.,1.,7.,-4.,5.))*factor
            reaction=normal*((.04-normal@C@f)/(normal@C@normal))
            np.testing.assert_allclose(result.for_combination(combo).displacements['N2'],C@(f+reaction),atol=1e-10)
            np.testing.assert_allclose(result.for_combination(combo).reactions['N2'],reaction,atol=1e-8)
            self.assertTrue(check_equilibrium(p,result.for_combination(combo)).passed)

    def test_moving_base_and_global_spring_keep_zero_spring_rest_position(self):
        p=beam();p.nodes['N2'].support='free';p.nodes['N1'].settlement_x=.01;p.nodes['N2'].spring_x=50.
        p.loads['F']=Load('F','N2','FX',3.)
        result=solve(p);k=p.E*p.A/120.
        for combo,factor in (('Load',1.),('Reverse',-1.7),('Zero',0.)):
            r=result.for_combination(combo);tip=(3.*factor+k*.01)/(k+50.)
            self.assertAlmostEqual(r.displacements['N2'][0],tip,places=11)
            self.assertAlmostEqual(r.reactions['N2'][0],-50.*tip,places=9)
            self.assertAlmostEqual(r.reactions['N1'][0],k*(.01-tip),places=9)
            self.assertTrue(check_equilibrium(p,r).passed)

    def test_spatial_rigid_body_prescriptions_do_not_create_member_forces(self):
        for end,roll in (((120.,0.,0.),0.),((144.,96.,108.),31.),((-70.,120.,-60.),-73.)):
            p=SpatialProject();origin=np.array((1e5,-2e5,3e5));p.add_member(tuple(origin),tuple(origin+end));p.members['M1'].roll=roll
            translation=np.array((.03,-.02,.04));omega=np.array((.0002,-.0003,.0004))
            for n in p.nodes.values():
                n.support='fixed';movement=np.r_[translation+np.cross(omega,np.array(n.coords)-origin),omega]
                for key,value in zip(movement_fields(n)[:-1],movement):setattr(n,key,float(value))
            r=solve(p)
            np.testing.assert_allclose(list(r.reactions.values()),0.,atol=1e-8)
            self.assertTrue(check_equilibrium(p,r).passed)

    def test_truss_axial_extension_and_member_side_recovery_at_released_joint(self):
        for spatial in (False,True):
            p=beam();p.nodes['N1'].support=p.nodes['N2'].support='pin';p.nodes['N2'].settlement_x=.02;p.members['M1'].kind='truss'
            if spatial:p=to_spatial(p)
            r=solve(p);force=p.E*p.A*.02/120.
            self.assertAlmostEqual(r.reactions['N1'][0],-force,places=9);self.assertAlmostEqual(r.reactions['N2'][0],force,places=9)
            self.assertTrue(check_equilibrium(p,r).passed)
        from pynitegui.qt.examples import example_project
        p=example_project('3d_sliding_beam');p.loads.clear()
        for key,value in (('settlement_x',.1),('settlement_y',-.2),('settlement_z',.15)):setattr(p.nodes['N2'],key,value)
        r=solve(p);np.testing.assert_allclose(list(r.reactions.values()),0.,atol=1e-8)
        member=next(iter(r.solver.members['M1'].sub_members.values()))
        np.testing.assert_allclose(member.d(r.combination)[6:9,0],0.,atol=1e-12)
        np.testing.assert_allclose(r.displacements['N2'][:3],(.1,-.2,.15),atol=1e-12)
        # Prescribing a disconnected joint rotation cannot create a member-end
        # moment or turn an unused-rotation gauge into a physical support torque.
        for spatial in (False, True):
            if spatial:
                p=example_project('3d_released_beam');p.nodes['N2'].support='fixed'
                p.members['M1'].release_end_rx=True
                p.nodes['N2'].settlement_rx=.002;p.nodes['N2'].settlement_ry=-.003
            else:
                p=beam();p.members['M1'].release_start=p.members['M1'].release_end=True
            p.loads.clear();p.nodes['N2'].settlement_rz=.004
            r=solve(p)
            np.testing.assert_allclose(list(r.reactions.values()),0.,atol=1e-8)
            self.assertTrue(check_equilibrium(p,r).passed)

    def test_persistence_migration_signatures_invalid_constraints_and_zero_axial_pdelta_limit(self):
        from pynitegui.qt.automation_core import batch_candidate, AutomationError
        for p,old,current in ((beam(),27,29),(to_spatial(beam()),34,36)):
            self.assertEqual(p.to_dict()['version'],current)
            data=p.to_dict();data['version']=old
            for node in data['nodes'].values():
                for key in movement_fields(next(iter(p.nodes.values()))):node.pop(key)
            self.assertEqual(Project.from_dict(data).to_dict(),p.to_dict())
            original=p.to_dict();signature=model_signature(p);p.nodes['N2'].settlement_y=-.1
            self.assertNotEqual(model_signature(p),signature)
            self.assertEqual(Project.from_dict(p.to_dict()).to_dict(),p.to_dict())
            for key in movement_fields(p.nodes['N2']):
                data=p.to_dict();data['nodes']['N2'].pop(key)
                with self.assertRaisesRegex(ValueError,'Missing imposed'):Project.from_dict(data)
                for bad in (True,None,float('nan'),float('inf'),'0.1'):
                    data=p.to_dict();data['nodes']['N2'][key]=bad
                    with self.assertRaises(ValueError):Project.from_dict(data)
            data=p.to_dict();data['version']=old
            with self.assertRaisesRegex(ValueError,'Imposed support movements require'):Project.from_dict(data)
            before=p.to_dict()
            with self.assertRaises(AutomationError):batch_candidate(p,[{'op':'put','collection':'nodes','key':'N2','value':{'support':'free'}}])
            self.assertEqual(before,p.to_dict())
            linear=solve(p)
            p.analysis_method='p_delta'
            second_order=solve(p)
            for name in p.nodes:
                np.testing.assert_allclose(second_order.displacements[name],linear.displacements[name],atol=1e-12)
                np.testing.assert_allclose(second_order.reactions[name],linear.reactions[name],atol=1e-8)
        p=cantilever((0.,90.));p.nodes['N2'].restraint_y=True;p.nodes['N2'].settlement_y=-.1
        with self.assertRaisesRegex(ValueError,'incompatible prescribed'):p.validate()
        p.nodes['N2'].settlement_normal=-.1
        p.validate();solve(p)

    def test_coupled_shared_nodes_rigid_translation_and_edge_prescription_conflict(self):
        from pynitegui.qt.examples import example_project
        p=example_project('3d_slab_frame');p.loads.clear();p.surface_pressures.clear()
        for node in p.nodes.values():
            if node.support=='fixed':node.settlement_y=-.05
        result=solve(p)
        for combination in p.combinations:
            r=result.for_combination(combination)
            for values in r.displacements.values():self.assertAlmostEqual(values[1],-.05,places=9)
            np.testing.assert_allclose(list(r.reactions.values()),0.,atol=1e-7)
            self.assertTrue(check_equilibrium(p,r).passed)
        p=example_project('3d_slab_frame');n=p.nodes['N2'];n.support='inclined';n.support_angle=0.;n.support_elevation=90.;n.settlement_normal=-.1
        p.surface_supports={'Floor':{'left':['DY']}}
        with self.assertRaisesRegex(ValueError,'incompatible prescribed'):solve(p)
