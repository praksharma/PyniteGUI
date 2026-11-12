"""Independent nonlinear portal joint statics versus constrained energy solver."""
import unittest
from dataclasses import replace
import numpy as np
from portal_statics_reference import solve
from displacement_hinge_frame import DisplacementHingeFrame
from test_planar_hinge_frame import NODES,MEMBERS,HINGES

H=120.;B=120.;EA=290000.;EI=2900000.;MP=1000.;GRAVITY=50.


def frame():
    preload=np.zeros(12);preload[[7,10]]=-GRAVITY
    return DisplacementHingeFrame(NODES,MEMBERS,tuple(range(6)),HINGES,preload,6)


class PortalStaticsReferenceTests(unittest.TestCase):
    def compare(self,r,s):
        np.testing.assert_allclose(r['motion'][6:],s['roof_motion'],atol=1e-8)
        np.testing.assert_allclose(r['hinge_moments'],s['hinge_moments'],atol=1e-6)
        np.testing.assert_allclose(r['reaction'][:6],s['support_reactions'],atol=1e-6)
        np.testing.assert_allclose(r['state'].rotations,s['state'].rotations,atol=1e-9)
        self.assertAlmostEqual(r['state'].dissipation,s['state'].dissipation,places=6)
        self.assertAlmostEqual(r['elastic_energy'],s['elastic_energy'],places=6)
        self.assertAlmostEqual(r['actuator_load'],s['actuator_load'],places=7)
        self.assertAlmostEqual(r['actuator_tangent'],s['actuator_tangent'],delta=2e-6)
        self.assertEqual(r['active'],s['active'])
        self.assertFalse(s['production_ready'])

    def test_yield_softening_reverse_and_increment_paths(self):
        for steps in (1,10):
            b=frame();old=reference=None;previous=0.
            for target in (0.,.5,1.,1.3,1.5,2.,3.,0.,-3.,0.):
                for x in np.linspace(previous,target,steps+1)[1:]:
                    r=b.solve_displacement(x,old);s=solve(H,B,EA,EI,MP,GRAVITY,x,reference)
                    self.compare(r,s);old=r['state'];reference=s['state']
                previous=target
                if target in (2.,3.):
                    self.assertEqual(r['active'],(0,1,2,3))
                    self.assertLess(r['actuator_tangent'],0.)
                    self.assertFalse(r['load_control_stable'])

    def test_large_step_geometry_predictor_matches_independent_root(self):
        b=frame();old=b.solve_displacement(3.)['state'];before=repr(old)
        reference=solve(H,B,EA,EI,MP,GRAVITY,3.)['state']
        r=b.solve_displacement(5.,old);s=solve(H,B,EA,EI,MP,GRAVITY,5.,reference)
        self.compare(r,s);self.assertEqual(repr(old),before)
        cold=b.solve_displacement(5.);direct=solve(H,B,EA,EI,MP,GRAVITY,5.)
        self.compare(cold,direct)
        np.testing.assert_allclose(cold['motion'],r['motion'],atol=1e-8)
        # No elastic predictor's trial overstress/plastic increment is committed.
        self.assertAlmostEqual(cold['state'].dissipation,MP*sum(abs(np.array(cold['state'].rotations))),places=7)

    def test_reference_tangent_frozen_history_and_deformed_balance(self):
        old=solve(H,B,EA,EI,MP,GRAVITY,1.5)['state'];target=2.5
        s=solve(H,B,EA,EI,MP,GRAVITY,target,old);eps=1e-4
        plus=solve(H,B,EA,EI,MP,GRAVITY,target+eps,old)
        minus=solve(H,B,EA,EI,MP,GRAVITY,target-eps,old)
        self.assertAlmostEqual((plus['actuator_load']-minus['actuator_load'])/(2*eps),s['actuator_tangent'],delta=2e-6)
        forces=np.zeros((4,3));forces[:2]=s['support_reactions'].reshape(2,3)
        forces[2:,1]=-GRAVITY;forces[2,0]=s['actuator_load']
        xy=np.asarray(NODES).copy();xy[2:]+=s['roof_motion'].reshape(2,3)[:,:2]
        np.testing.assert_allclose(forces[:,:2].sum(axis=0),[0.,0.],atol=1e-7)
        self.assertAlmostEqual(sum(xy[:,0]*forces[:,1]-xy[:,1]*forces[:,0]+forces[:,2]),0.,places=5)

    def test_report_gates_and_source_records(self):
        import json,hashlib
        from pathlib import Path
        root=Path(__file__).resolve().parents[1]
        report=json.loads((root/'docs/assets/portal-joint-statics.json').read_text())
        self.assertEqual(len(report['records']),23)
        self.assertTrue(report['bounded_portal_joint_statics_checks_passed'])
        self.assertFalse(report['production_ready']);self.assertFalse(report['general_frame_plastic_validated'])
        for name,limit in report['gates'].items():
            self.assertLess(max(record[name] for record in report['records']),limit)
        for source,digest in report['source_sha256'].items():
            self.assertEqual(hashlib.sha256((root/source).read_bytes()).hexdigest(),digest,source)

    def test_reference_units_and_configuration_history_rejection(self):
        s=solve(H,B,EA,EI,MP,GRAVITY,3.);a=25.4;force=4448.2216152605
        q=solve(H*a,B*a,EA*force,EI*force*a*a,MP*force*a,GRAVITY*force,3.*a)
        expected=s['roof_motion'].copy();expected.reshape(2,3)[:,:2]*=a
        np.testing.assert_allclose(q['roof_motion'],expected,atol=1e-7)
        self.assertAlmostEqual(q['actuator_load']/force,s['actuator_load'],places=7)
        self.assertAlmostEqual(q['actuator_tangent']*a/force,s['actuator_tangent'],delta=2e-6)
        old=s['state'];before=repr(old)
        for bad in (replace(old,rotations=(np.nan,0.,0.,0.)),replace(old,dissipation=-1.),replace(old,configuration=())):
            with self.assertRaises(ValueError):solve(H,B,EA,EI,MP,GRAVITY,1.,bad)
        with self.assertRaises(ValueError):solve(H,B,EA,EI,MP,GRAVITY,np.nan,old)
        with self.assertRaises(ValueError):solve(H,B,EA,EI,MP,GRAVITY,100.,old)
        self.assertEqual(repr(old),before)
