"""Coordinate-change invariance, virtual work and distributed-pattern continuation."""
import unittest
from dataclasses import replace
import numpy as np
from pattern_displacement_frame import PatternDisplacementFrame
from displacement_hinge_frame import DisplacementHingeFrame
from corotational_hinge_frame import CorotationalHingeFrame
from test_planar_hinge_frame import NODES,MEMBERS,HINGES


def setup(pattern=None):
    preload=np.zeros(12);preload[[7,10]]=-50.
    if pattern is None:
        pattern=np.zeros(12);pattern[[6,9]]=.5
    return preload,pattern,PatternDisplacementFrame(NODES,MEMBERS,tuple(range(6)),HINGES,preload,pattern)


class PatternDisplacementFrameTests(unittest.TestCase):
    def test_single_node_pattern_exact_driver_equivalence(self):
        p=np.zeros(12);p[6]=1.;pre,p,b=setup(p)
        original=DisplacementHingeFrame(NODES,MEMBERS,tuple(range(6)),HINGES,pre,6)
        old=reference=None
        for target in (0.,.5,1.3,2.5,5.,0.,-3.):
            r=b.solve_displacement(target,old);s=original.solve_displacement(target,reference)
            np.testing.assert_allclose(r['motion'],s['motion'],atol=1e-10)
            self.assertAlmostEqual(r['load_factor'],s['actuator_load'],places=9)
            self.assertAlmostEqual(r['pattern_tangent'],s['actuator_tangent'],places=8)
            self.assertAlmostEqual(r['state'].dissipation,s['state'].dissipation,places=8)
            old=r['state'];reference=s['state']

    def test_equal_roof_pattern_force_equivalence_and_softening_balance(self):
        pre,p,b=setup();old=b.solve_displacement(0.)['state']
        stable=b.solve_displacement(1.3,old)
        force=CorotationalHingeFrame(NODES,MEMBERS,tuple(range(6)),HINGES).solve(stable['loads'])
        np.testing.assert_allclose(force['motion'],stable['motion'],atol=1e-8)
        r=b.solve_displacement(2.5,stable['state'])
        self.assertEqual(r['active'],(0,1,2,3));self.assertLess(r['pattern_tangent'],0.)
        self.assertTrue(r['constrained_stable']);self.assertFalse(r['load_control_stable'])
        self.assertAlmostEqual(p@r['motion'],2.5,places=10)
        np.testing.assert_allclose(r['loads'],pre+r['load_factor']*p,atol=1e-10)
        np.testing.assert_allclose(r['loads'][[6,9]],[r['load_factor']/2]*2,atol=1e-10)
        total=(r['loads']+r['reaction']).reshape(-1,3)
        xy=np.asarray(NODES)+r['motion'].reshape(-1,3)[:,:2]
        np.testing.assert_allclose(total[:,:2].sum(axis=0),[0.,0.],atol=1e-7)
        self.assertAlmostEqual(sum(xy[:,0]*total[:,1]-xy[:,1]*total[:,0]+total[:,2]),0.,places=5)
        epsilon=1e-4
        plus=b.solve_displacement(2.5+epsilon,stable['state']);minus=b.solve_displacement(2.5-epsilon,stable['state'])
        self.assertAlmostEqual((plus['load_factor']-minus['load_factor'])/(2*epsilon),r['pattern_tangent'],places=6)
        self.assertFalse(r['production_ready'])

    def test_pattern_scale_sign_and_physical_history_identity(self):
        pre,p,b=setup();r=b.solve_displacement(2.5)
        for scale in (3.,-2.):
            _,_,other=setup(p*scale);q=other.solve_displacement(2.5*scale)
            np.testing.assert_allclose(q['motion'],r['motion'],atol=1e-8)
            np.testing.assert_allclose(q['loads'],r['loads'],atol=1e-7)
            self.assertAlmostEqual(q['load_factor']*scale,r['load_factor'],places=7)
            self.assertAlmostEqual(q['pattern_tangent']*scale**2,r['pattern_tangent'],places=7)
            self.assertAlmostEqual(q['state'].dissipation,r['state'].dissipation,places=6)
            with self.assertRaises(ValueError):other.solve_displacement(1.,r['state'])

    def test_work_conjugacy_unloading_reverse_and_energy(self):
        pre,p,b=setup();r=b.solve_displacement(0.);old=r['state'];initial_energy=r['elastic_energy']
        previous=r['motion'];previous_q=0.;previous_factor=r['load_factor'];work=0.;physical_work=0.
        for start,end in ((0.,2.5),(2.5,0.),(0.,-2.5),(-2.5,0.)):
            for q in np.linspace(start,end,101)[1:]:
                r=b.solve_displacement(q,old);du=r['motion']-previous
                increment=.5*(previous_factor+r['load_factor'])*(q-previous_q)+pre@du
                work+=increment;physical_work+=(pre+.5*(previous_factor+r['load_factor'])*p)@du
                self.assertAlmostEqual(increment,(pre+.5*(previous_factor+r['load_factor'])*p)@du,places=9)
                previous=r['motion'];previous_q=q;previous_factor=r['load_factor'];old=r['state']
        self.assertAlmostEqual(work,physical_work,places=8)
        self.assertAlmostEqual(work-r['elastic_energy']+initial_energy,old.dissipation,delta=.03)

    def test_mixed_translation_pattern_and_unit_conversion(self):
        p=np.zeros(12);p[[6,9,10]]=[.6,.3,-.1];pre,p,b=setup(p)
        r=b.solve_displacement(.5)
        reference=CorotationalHingeFrame(NODES,MEMBERS,tuple(range(6)),HINGES).solve(r['loads'])
        np.testing.assert_allclose(r['motion'],reference['motion'],atol=1e-8)
        np.testing.assert_allclose(r['loads'],pre+r['load_factor']*p,atol=1e-10)
        epsilon=1e-4
        plus=b.solve_displacement(.5+epsilon);minus=b.solve_displacement(.5-epsilon)
        self.assertAlmostEqual((plus['load_factor']-minus['load_factor'])/(2*epsilon),r['pattern_tangent'],places=6)
        a=25.4;force=4448.2216152605
        scaled=PatternDisplacementFrame(np.asarray(NODES)*a,
            tuple((i,j,ea*force,ei*force*a*a) for i,j,ea,ei in MEMBERS),tuple(range(6)),
            tuple((m,e,mp*force*a) for m,e,mp in HINGES),pre*force,p)
        q=scaled.solve_displacement(.5*a)
        expected=r['motion'].copy();expected.reshape(-1,3)[:,:2]*=a
        np.testing.assert_allclose(q['motion'],expected,atol=1e-8)
        self.assertAlmostEqual(q['load_factor']/force,r['load_factor'],places=7)
        self.assertAlmostEqual(q['pattern_tangent']*a/force,r['pattern_tangent'],places=7)

    def test_invalid_pattern_and_transactional_rejection(self):
        pre,p,b=setup();old=b.solve_displacement(1.3)['state'];before=repr(old)
        for bad in (np.zeros(12),np.full(12,np.nan),np.ones(3)):
            with self.assertRaises(ValueError):setup(bad)
        for index in (0,8):
            bad=p.copy();bad[index]=1.
            with self.assertRaises(ValueError):setup(bad)
        for bad in (replace(old,motion=(np.nan,)*12),replace(old,dissipation=-1.)):
            with self.assertRaises(ValueError):b.solve_displacement(2.,bad)
        with self.assertRaises(ValueError):b.solve_displacement(100.,old)
        with self.assertRaises(ValueError):b.solve_displacement(2.,old,max_iterations=1)
        self.assertEqual(repr(old),before)
