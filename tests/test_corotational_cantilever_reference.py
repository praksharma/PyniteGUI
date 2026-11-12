"""Independent current-chord statics and compliance for yielded/unloading motion."""
import unittest
from dataclasses import replace
import numpy as np
from corotational_cantilever_reference import solve
from corotational_hinge_frame import CorotationalHingeFrame

L=120.;EA=290000.;EI=2900000.;MP=1000.


def frame():
    return CorotationalHingeFrame(((0.,0.),(0.,L)),((0,1,EA,EI),),(0,1,2),((0,0,MP),))


def loads(lateral,tension):
    f=np.zeros(6);f[3:5]=[lateral,tension];return f


class CorotationalCantileverReferenceTests(unittest.TestCase):
    def compare(self,r,s):
        np.testing.assert_allclose(r['motion'][3:],s['motion'],atol=1e-8)
        self.assertAlmostEqual(r['state'].rotations[0],s['state'].plastic_rotation,places=9)
        self.assertAlmostEqual(r['state'].dissipation,s['state'].dissipation,places=6)
        self.assertAlmostEqual(r['elastic_energy'],s['elastic_energy'],places=6)
        self.assertAlmostEqual(r['basic_forces'][0,0],s['axial_force'],places=6)
        self.assertAlmostEqual(r['hinge_moments'][0],s['moment'],places=6)
        self.assertEqual(bool(r['active']),s['active'])
        np.testing.assert_allclose(np.linalg.solve(r['free_tangent'],[1.,0.,0.]),s['compliance'],rtol=1e-7,atol=1e-9)

    def test_signed_monotonic_steps_and_three_tension_levels(self):
        for tension,maximum in ((20.,10.),(40.,12.),(80.,16.)):
            for sign in (-1.,1.):
                for steps in (1,20):
                    b=frame();old=reference=None
                    for lateral in np.linspace(0.,sign*maximum,steps+1):
                        r=b.solve(loads(lateral,tension),old)
                        s=solve(L,EA,EI,MP,lateral,tension,reference)
                        self.compare(r,s);old=r['state'];reference=s['state']
                    self.assertTrue(s['active'])
                    self.assertGreater(sign*old.rotations[0],0.)

    def test_cold_combined_load_seeds_coordinates_without_committing_trial_plasticity(self):
        b=frame();r=b.solve(loads(12.,40.));s=solve(L,EA,EI,MP,12.,40.)
        self.compare(r,s)
        pre=b.solve(loads(0.,40.));staged=b.solve(loads(12.,40.),pre['state'])
        np.testing.assert_allclose(r['motion'],staged['motion'],atol=1e-8)
        self.assertAlmostEqual(r['state'].dissipation,MP*abs(r['state'].rotations[0]),places=8)
        self.assertEqual(pre['state'].rotations,(0.,))

    def test_unload_reverse_and_changing_tension_history(self):
        b=frame();old=reference=None
        for lateral,tension in ((0.,40.),(12.,40.),(0.,40.),(-12.,40.),(0.,40.),(8.,80.),(10.,20.),(0.,40.)):
            r=b.solve(loads(lateral,tension),old)
            s=solve(L,EA,EI,MP,lateral,tension,reference)
            self.compare(r,s)
            if old is not None and not r['active']:
                self.assertEqual(r['state'].rotations,old.rotations)
                self.assertEqual(r['state'].dissipation,old.dissipation)
            old=r['state'];reference=s['state']
        self.assertGreater(old.dissipation,0.)

    def test_independent_compliance_and_deformed_moment_balance(self):
        old=solve(L,EA,EI,MP,0.,40.)['state']
        for lateral in (5.,12.,-12.):
            r=solve(L,EA,EI,MP,lateral,40.,old);eps=1e-5
            plus=solve(L,EA,EI,MP,lateral+eps,40.,old)
            minus=solve(L,EA,EI,MP,lateral-eps,40.,old)
            derivative=(np.array(plus['motion'])-minus['motion'])/(2*eps)
            np.testing.assert_allclose(derivative,r['compliance'],rtol=1e-7,atol=1e-9)
            x,dy,theta=r['motion']
            self.assertAlmostEqual(r['moment']+40.*x-lateral*(L+dy),0.,places=8)
            # Free-end moment vanishes: theta = -psi - M/(2*(3EI/L)).
            self.assertAlmostEqual(theta,-r['chord_angle']-r['moment']*L/(6*EI),places=12)

    def test_work_energy_and_dissipation_from_independent_path(self):
        b=frame();old=b.solve(loads(0.,40.))['state'];initial_energy=b.evaluate(old.motion,old.rotations)['elastic_energy']
        work=0.;previous_load=loads(0.,40.);previous_motion=np.array(old.motion)
        for start,end in ((0.,12.),(12.,0.),(0.,-12.),(-12.,0.)):
            for lateral in np.linspace(start,end,201)[1:]:
                f=loads(lateral,40.);r=b.solve(f,old)
                work+=(f+previous_load)@(r['motion']-previous_motion)/2
                old=r['state'];previous_load=f;previous_motion=r['motion']
        self.assertAlmostEqual(work-r['elastic_energy']+initial_energy,old.dissipation,delta=.02)

    def test_published_comparison_gates_and_source_manifest(self):
        import hashlib,json
        from pathlib import Path
        root=Path(__file__).resolve().parents[1]
        report=json.loads((root/'docs/assets/corotational-cantilever.json').read_text())
        self.assertEqual(len(report['records']),48)
        self.assertTrue(report['bounded_member_reference_checks_passed'])
        self.assertFalse(report['production_ready'])
        self.assertFalse(report['general_frame_plastic_validated'])
        for key,limit in report['gates'].items():
            self.assertLess(max(r[key] for r in report['records']),limit)
        for path,digest in report['source_sha256'].items():
            self.assertEqual(hashlib.sha256((root/path).read_bytes()).hexdigest(),digest,path)

    def test_reference_scaling_and_transactional_rejection(self):
        old=solve(L,EA,EI,MP,12.,40.)['state'];before=repr(old)
        r=solve(L,EA,EI,MP,0.,40.,old);a=25.4;force=4448.2216152605
        scaled_old=solve(L*a,EA*force,EI*force*a*a,MP*force*a,12.*force,40.*force)['state']
        scaled=solve(L*a,EA*force,EI*force*a*a,MP*force*a,0.,40.*force,scaled_old)
        np.testing.assert_allclose(scaled['motion'],np.array(r['motion'])*[a,a,1.],atol=1e-10)
        self.assertAlmostEqual(scaled['state'].dissipation/(force*a),r['state'].dissipation,places=8)
        for tension in (0.,-40.,np.nan):
            with self.assertRaises(ValueError):solve(L,EA,EI,MP,1.,tension,old)
        with self.assertRaises(ValueError):solve(L,EA,EI,MP,100.,40.,old)
        with self.assertRaises(ValueError):solve(L,EA,EI,MP,1.,40.,replace(old,dissipation=-1.))
        with self.assertRaises(ValueError):solve(L*2,EA,EI,MP,1.,40.,old)
        with self.assertRaises(ValueError):solve(L,EA,EI,MP,1.,40.,replace(old,plastic_rotation=.3))
        with self.assertRaises(ValueError):solve(L,EA,EI,MP,1.,40.,replace(old,plastic_rotation=np.nan))
        self.assertEqual(repr(old),before)
