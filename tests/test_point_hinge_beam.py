"""Ideal-hinge independent reference, stress admissibility, cyclic work and mesh invariance."""
import unittest
import numpy as np
from point_hinge_beam import PointHingeBeam

L=240.;EI=2900000.;MP=1000.


def reference(P):
    first=16*MP/(3*L);m=min(3*P*L/16,MP)
    u=-(P*7*L**3/(768*EI) if P<=first else first*7*L**3/(768*EI)+(P-first)*L**3/(48*EI))
    return u,m,P/2+m/L,P/2-m/L


class PointHingeBeamTests(unittest.TestCase):
    def test_mesh_and_load_step_independence_pass_one_percent_gates(self):
        for n in (2,4,8,16,32):
            for steps in (1,20):
                beam=PointHingeBeam(L,EI,MP,n);old=None
                for force in np.linspace(0,24,steps+1):
                    r=beam.solve(force,old);old=r['state'];expected=reference(force)
                    self.assertAlmostEqual(r['motion'][n],expected[0],places=8)
                    self.assertAlmostEqual(r['reaction'][1],expected[1],places=6)
                    self.assertAlmostEqual(r['reaction'][0],expected[2],places=7)
                    self.assertAlmostEqual(r['reaction'][-2],expected[3],places=7)
                    self.assertLess(max(abs(r['end_moments'])),MP*(1+1e-8))
                self.assertLess(abs(r['motion'][n]/reference(24.)[0]-1),.01)
                self.assertLess(abs(r['reaction'][1]/MP-1),.01)
                self.assertFalse(r['production_ready'])

    def test_unload_reverse_yield_and_committed_history(self):
        b=PointHingeBeam(L,EI,MP,8);r=b.solve(24.);old=r['state'];unload=b.solve(0.,old)
        self.assertFalse(unload['active']);self.assertEqual(unload['state'].plastic_rotation,old.plastic_rotation)
        self.assertEqual(unload['state'].dissipation,old.dissipation)
        self.assertAlmostEqual(unload['motion'][8],reference(24.)[0]-reference(20.)[0]*24/20,places=10)
        reverse=b.solve(-24.,unload['state'])
        self.assertTrue(reverse['active']);self.assertLess(reverse['state'].plastic_rotation,0.)
        self.assertAlmostEqual(reverse['motion'][8],-r['motion'][8],places=9)
        self.assertGreater(reverse['state'].dissipation,old.dissipation)

    def test_algorithmic_global_tangent_matches_force_derivative(self):
        b=PointHingeBeam(L,EI,MP,8);old=b.solve(20.)['state'];r=b.solve(24.,old)
        plus=b.solve(24.+1e-5,old);minus=b.solve(24.-1e-5,old)
        derivative=(plus['motion'][b.free]-minus['motion'][b.free])/(2e-5)
        load=np.zeros(len(b.free));load[list(b.free).index(8)]=-1.
        np.testing.assert_allclose(derivative,np.linalg.solve(r['free_tangent'],load),rtol=1e-7,atol=1e-9)

    def test_global_energy_and_mechanism_rejection(self):
        b=PointHingeBeam(L,EI,MP,8);old=None;previous_u=np.zeros(b.size);previous_alpha=0.;energy=0.
        for force in (0.,20.,24.,0.,-24.):
            r=b.solve(force,old);du=r['motion']-previous_u;da=r['state'].plastic_rotation-previous_alpha
            numerical=0.
            for i,ids in enumerate(b.indices):
                d=du[ids].copy()
                if i==0:d[1]-=da
                numerical+=.5*d@b.local@d
            self.assertAlmostEqual(-force*du[8]-(r['elastic_energy']-energy)-r['dissipation_increment'],numerical,places=8)
            old=r['state'];previous_u=r['motion'];previous_alpha=old.plastic_rotation;energy=r['elastic_energy']
        before=repr(old)
        for force in (-26.,-25.,25.,26.):
            with self.assertRaisesRegex(ValueError,'mechanism'):b.solve(force,old)
        self.assertEqual(repr(old),before)
        with self.assertRaises(ValueError):b.solve(np.nan,old)
        with self.assertRaises(ValueError):PointHingeBeam(L,EI,MP,4).solve(20.,old)
