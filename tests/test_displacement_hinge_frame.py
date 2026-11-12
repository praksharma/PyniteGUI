"""Independent nonlinear displacement-control reference and post-peak stability."""
import unittest
from dataclasses import replace
from math import sin,cos,sqrt
import numpy as np
from displacement_hinge_frame import DisplacementHingeFrame
from displacement_cantilever_reference import solve
from corotational_hinge_frame import CorotationalHingeFrame

L=120.;EA=290000.;EI=2900000.;MP=1000.
NODES=((0.,0.),(0.,L));MEMBERS=((0,1,EA,EI),);FIXED=(0,1,2);HINGES=((0,0,MP),)


def frame(vertical):
    f=np.zeros(6);f[4]=vertical
    return DisplacementHingeFrame(NODES,MEMBERS,FIXED,HINGES,f,3)


class DisplacementHingeFrameTests(unittest.TestCase):
    def compare(self,r,s):
        np.testing.assert_allclose(r['motion'][3:],s['motion'],atol=1e-8)
        self.assertAlmostEqual(r['actuator_load'],s['actuator_load'],places=7)
        self.assertAlmostEqual(r['actuator_tangent'],s['actuator_tangent'],places=7)
        self.assertAlmostEqual(r['state'].rotations[0],s['state'].rotation,places=9)
        self.assertAlmostEqual(r['state'].dissipation,s['state'].dissipation,places=6)
        self.assertAlmostEqual(r['elastic_energy'],s['elastic_energy'],places=6)
        self.assertTrue(r['constrained_stable']);self.assertFalse(r['production_ready'])
        self.assertEqual(bool(r['active']),s['active'])
        self.assertLess(max(abs(r['residual'])),1e-7)

    def test_compression_zero_and_tension_cycles_and_increments(self):
        for vertical in (-40.,0.,40.):
            for steps in (1,20):
                b=frame(vertical);old=reference=None;previous=0.
                for target in (0.,.5,2.,5.,10.,0.,-10.,0.):
                    for x in np.linspace(previous,target,steps+1)[1:]:
                        r=b.solve_displacement(x,old);s=solve(L,EA,EI,MP,x,vertical,reference)
                        self.compare(r,s);old=r['state'];reference=s['state']
                    previous=target

    def test_peak_softening_and_different_load_control_branch(self):
        b=frame(-40.);psi=MP/(3*EI/L)
        A=L*(1-40./(EA*cos(psi)));B=L*MP*sin(psi)/(EA*cos(psi))
        yield_drift=(A+sqrt(A*A+4*B))/2*sin(psi)
        before=b.solve_displacement(yield_drift*(1-1e-4))
        after=b.solve_displacement(yield_drift*(1+1e-4),before['state'])
        self.assertGreater(before['actuator_tangent'],0.)
        self.assertLess(after['actuator_tangent'],0.)
        self.assertFalse(after['load_control_stable'])
        post=b.solve_displacement(5.,after['state'])
        self.assertLess(post['actuator_load'],after['actuator_load'])
        self.assertTrue(post['constrained_stable']);self.assertFalse(post['load_control_stable'])
        # The same load also has a stable pre-yield response. Force control must
        # not silently label the displacement-held softening pose as stable.
        force=CorotationalHingeFrame(NODES,MEMBERS,FIXED,HINGES).solve(post['loads'])
        self.assertLess(force['motion'][3],yield_drift)
        self.assertGreater(abs(force['motion'][3]-post['motion'][3]),1.)

    def test_actuator_tangent_and_deformed_global_balance(self):
        b=frame(-40.);old=b.solve_displacement(.5)['state'];r=b.solve_displacement(5.,old)
        epsilon=1e-4
        plus=b.solve_displacement(5.+epsilon,old);minus=b.solve_displacement(5.-epsilon,old)
        self.assertAlmostEqual((plus['actuator_load']-minus['actuator_load'])/(2*epsilon),r['actuator_tangent'],places=7)
        total=(r['loads']+r['reaction']).reshape(-1,3)
        xy=np.asarray(NODES)+r['motion'].reshape(-1,3)[:,:2]
        np.testing.assert_allclose(total[:,:2].sum(axis=0),[0.,0.],atol=1e-7)
        self.assertAlmostEqual(sum(xy[:,0]*total[:,1]-xy[:,1]*total[:,0]+total[:,2]),0.,places=6)
        self.assertEqual(r['motion'][3],5.)

    def test_cycle_work_energy_and_uncommitted_rejection(self):
        b=frame(-40.);r=b.solve_displacement(0.);old=r['state'];energy=r['elastic_energy']
        previous_u=r['motion'];previous_load=r['loads'];work=0.
        for start,end in ((0.,10.),(10.,0.),(0.,-10.),(-10.,0.)):
            for x in np.linspace(start,end,401)[1:]:
                r=b.solve_displacement(x,old)
                work+=(r['loads']+previous_load)@(r['motion']-previous_u)/2
                previous_u=r['motion'];previous_load=r['loads'];old=r['state']
        self.assertAlmostEqual(work-r['elastic_energy']+energy,old.dissipation,delta=.02)
        before=repr(old)
        for target in (np.nan,100.):
            with self.assertRaises(ValueError):b.solve_displacement(target,old)
        with self.assertRaises(ValueError):b.solve_displacement(5.,old,max_iterations=1)
        self.assertEqual(repr(old),before)

    def test_connected_portal_four_hinge_softening_and_actuator_derivative(self):
        from test_planar_hinge_frame import NODES as nodes,MEMBERS as members,HINGES as hinges
        preload=np.zeros(12);preload[[7,10]]=-50.
        b=DisplacementHingeFrame(nodes,members,tuple(range(6)),hinges,preload,6)
        old=None
        for target in (0.,.5,1.,1.3,1.5):
            r=b.solve_displacement(target,old);old=r['state']
        self.assertEqual(r['active'],(0,1));self.assertTrue(r['load_control_stable'])
        post=b.solve_displacement(2.5,old)
        self.assertEqual(post['active'],(0,1,2,3))
        self.assertLess(post['actuator_tangent'],0.)
        self.assertFalse(post['load_control_stable']);self.assertTrue(post['constrained_stable'])
        np.testing.assert_allclose(post['hinge_moments'],[MP]*4,atol=1e-6)
        epsilon=1e-4
        plus=b.solve_displacement(2.5+epsilon,old);minus=b.solve_displacement(2.5-epsilon,old)
        self.assertAlmostEqual((plus['actuator_load']-minus['actuator_load'])/(2*epsilon),post['actuator_tangent'],places=6)
        total=(post['loads']+post['reaction']).reshape(-1,3)
        xy=np.asarray(nodes)+post['motion'].reshape(-1,3)[:,:2]
        np.testing.assert_allclose(total[:,:2].sum(axis=0),[0.,0.],atol=1e-7)
        self.assertAlmostEqual(sum(xy[:,0]*total[:,1]-xy[:,1]*total[:,0]+total[:,2]),0.,places=5)
        # Numerical equilibrium/derivative checks do not provide an independent
        # nonlinear portal oracle or certify general post-peak frame behaviour.

    def test_unit_scaling_and_elastic_no_hinge_case(self):
        b=frame(-40.);r=b.solve_displacement(5.);a=25.4;force=4448.2216152605
        f=np.zeros(6);f[4]=-40.*force
        scaled=DisplacementHingeFrame(np.asarray(NODES)*a,((0,1,EA*force,EI*force*a*a),),FIXED,((0,0,MP*force*a),),f,3)
        q=scaled.solve_displacement(5.*a)
        np.testing.assert_allclose(q['motion'][3:],r['motion'][3:]*[a,a,1.],atol=1e-8)
        self.assertAlmostEqual(q['actuator_load']/force,r['actuator_load'],places=8)
        self.assertAlmostEqual(q['actuator_tangent']*a/force,r['actuator_tangent'],places=8)
        self.assertAlmostEqual(q['state'].dissipation/(a*force),r['state'].dissipation,places=7)
        no_hinge=DisplacementHingeFrame(NODES,MEMBERS,FIXED,(),b.preload,3).solve_displacement(.5)
        expected=solve(L,EA,EI,MP,.5,-40.)
        np.testing.assert_allclose(no_hinge['motion'][3:],expected['motion'],atol=1e-10)

    def test_invalid_controls_histories_and_reference_bounds(self):
        b=frame(-40.);old=b.solve_displacement(5.)['state']
        for control in (0,2,5,True):
            with self.assertRaises(ValueError):DisplacementHingeFrame(NODES,MEMBERS,FIXED,HINGES,b.preload,control)
        for bad in (replace(old,rotations=(np.nan,)),replace(old,dissipation=-1.),replace(old,configuration=())):
            with self.assertRaises(ValueError):b.solve_displacement(1.,bad)
        with self.assertRaises(ValueError):frame(40.).solve_displacement(1.,old)
        with self.assertRaises(ValueError):b.solve(np.zeros(6))
        with self.assertRaises(ValueError):solve(L,EA,EI,MP,100.,-40.)
        with self.assertRaises(ValueError):solve(L,EA,EI,MP,1.,-40.,replace(solve(L,EA,EI,MP,5.,-40.)['state'],rotation=.3))
