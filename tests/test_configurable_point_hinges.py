"""Independent propped-beam reference and configurable-interface checks."""
import unittest
from dataclasses import replace
import numpy as np
from configurable_point_hinges import ConfigurableHingeBeam
from test_point_hinge_beam import reference, L, EI, MP


class ConfigurableHingeTests(unittest.TestCase):
    def beam(self,n=8,hinges=None):
        return ConfigurableHingeBeam(L,EI,MP,n,hinges or ((0,0),(n//2-1,1)))

    def load(self,b,p):
        f=np.zeros(b.size);f[b.n]=-p;return f

    def test_reference_mesh_steps_and_equilibrium_mechanism(self):
        for n in (2,4,8,16,32):
            b=self.beam(n)
            for steps in (1,20):
                old=None
                for p in np.linspace(0,24,steps+1):
                    r=b.solve(self.load(b,p),old);old=r['state'];expected=reference(p)
                    self.assertAlmostEqual(r['motion'][n],expected[0],places=8)
                    np.testing.assert_allclose(r['reaction'],[expected[2],expected[1],expected[3]],atol=1e-7)
                    self.assertLess(max(abs(r['hinge_moments'])),MP*(1+1e-9))
                before=repr(old)
                for p in (25.,26.,100.):
                    with self.assertRaisesRegex(ValueError,'mechanism'):b.solve(self.load(b,p),old)
                self.assertEqual(repr(old),before)
                self.assertFalse(r['production_ready'])

    def test_configured_interior_interface_and_arbitrary_nodal_couples(self):
        b=self.beam(8,((2,1),));f=np.zeros(b.size);f[9]=75.;f[10]=-1.5
        r=b.solve(f);expected=np.zeros(b.size)
        expected[b.free]=np.linalg.solve(b.K[np.ix_(b.free,b.free)],f[b.free])
        np.testing.assert_allclose(r['motion'],expected,atol=1e-12)
        # Linear trial gives an independent first-yield load factor for this interface.
        q=(b.G.T@expected)[0];factor=1.2*MP/abs(q)
        plastic=b.solve(f*factor)
        self.assertEqual(plastic['active'],(0,))
        self.assertAlmostEqual(abs(plastic['hinge_moments'][0]),MP,places=7)
        self.assertLess(max(abs(plastic['residual'])),1e-7)
        # With no couple at the hinge, changing its element-side convention
        # preserves translations and rotations away from the split node.
        other=self.beam(8,((3,0),)).solve(f*factor)
        mask=np.arange(b.size)!=7
        np.testing.assert_allclose(plastic['motion'][mask],other['motion'][mask],atol=1e-9)

    def test_unload_reversal_tangent_and_energy(self):
        b=self.beam();old=None;previous_u=np.zeros(b.size);previous_alpha=np.zeros(2);energy=0.
        for p in (0.,20.,24.,0.,-24.):
            f=self.load(b,p);r=b.solve(f,old);du=r['motion']-previous_u
            da=np.array(r['state'].rotations)-previous_alpha
            quadratic=.5*du@b.K@du-du@b.G@da+.5*da@b.H@da
            self.assertAlmostEqual(f@du-(r['elastic_energy']-energy)-r['dissipation_increment'],quadratic,places=8)
            if p==0. and old is not None:
                self.assertEqual(r['state'].rotations,old.rotations)
                self.assertEqual(r['state'].dissipation,old.dissipation)
            if p==24.:
                plus=b.solve(self.load(b,p+1e-5),old);minus=b.solve(self.load(b,p-1e-5),old)
                derivative=(plus['motion'][b.free]-minus['motion'][b.free])/2e-5
                np.testing.assert_allclose(derivative,np.linalg.solve(r['free_tangent'],self.load(b,1.)[b.free]),rtol=1e-7,atol=1e-9)
            old=r['state'];previous_u=r['motion'];previous_alpha=np.array(old.rotations);energy=r['elastic_energy']
        self.assertAlmostEqual(r['motion'][8],-reference(24.)[0],places=9)

    def test_four_interfaces_and_consistent_unit_scaling(self):
        b=self.beam(8,((0,0),(1,1),(3,1),(5,1)))
        r=b.solve(self.load(b,24.))
        self.assertEqual(r['active'],(0,))
        self.assertAlmostEqual(r['motion'][8],reference(24.)[0],places=9)
        # inch/kip to mm/N: rigidity scales by force*length squared.
        a=25.4;force=4448.2216152605
        scaled=ConfigurableHingeBeam(L*a,EI*force*a*a,MP*force*a,8,b.hinges)
        q=scaled.solve(self.load(scaled,24.*force))
        np.testing.assert_allclose(q['motion'][::2],r['motion'][::2]*a,atol=1e-8)
        np.testing.assert_allclose(q['motion'][1::2],r['motion'][1::2],atol=1e-10)
        np.testing.assert_allclose(q['state'].rotations,r['state'].rotations,atol=1e-10)
        self.assertAlmostEqual(q['elastic_energy']/(force*a),r['elastic_energy'],places=8)
        self.assertAlmostEqual(q['state'].dissipation/(force*a),r['state'].dissipation,places=8)
        with self.assertRaisesRegex(ValueError,'mechanism'):b.solve(self.load(b,25.),r['state'])

    def test_invalid_interfaces_history_and_loads(self):
        for hinges in ((),((0,0),)*2,((0,1),(1,0)),((8,0),),((0,2),),((True,0),)):
            with self.assertRaises(ValueError):self.beam(hinges=hinges) if hinges else ConfigurableHingeBeam(L,EI,MP,8,())
        b=self.beam();old=b.solve(self.load(b,24.))['state']
        with self.assertRaises(ValueError):self.beam(4).solve(np.zeros(10),old)
        with self.assertRaises(ValueError):b.solve(np.full(b.size,np.nan),old)
        with self.assertRaises(ValueError):b.solve(np.zeros(b.size),replace(old,rotations=(np.nan,0.)))
        with self.assertRaises(ValueError):b.solve(np.zeros(b.size),replace(old,dissipation=-1.))
