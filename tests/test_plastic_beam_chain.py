"""Global equilibrium, unloading and explicit failed ideal-hinge mesh gates."""
from functools import lru_cache
import unittest
import numpy as np
from plastic_beam_chain import PlasticBeamChain,ChainRejected

L=240.;EI=2900000.;MP=1000.


@lru_cache(maxsize=16)
def loaded(n,steps=20,maximum=24.):
    m=PlasticBeamChain(L,EI,MP,n);state=None;result=None
    for value in np.linspace(0,maximum,steps+1):
        force=np.zeros(m.size);force[n]=-value;result=m.solve(force,state);state=result['state']
    return m,result


def hinge_reference(P):
    first=16*MP/(3*L)
    if P<=first:return -P*7*L**3/(768*EI)
    return -(first*7*L**3/(768*EI)+(P-first)*L**3/(48*EI))


class PlasticBeamChainTests(unittest.TestCase):
    def test_elastic_global_displacement_reactions_and_equilibrium(self):
        for n in (2,8,32):
            m,r=loaded(n,1,20.)
            self.assertAlmostEqual(r['motion'][n],hinge_reference(20.),places=9)
            moment=3*20*L/16
            self.assertAlmostEqual(r['reaction'][1],moment,places=7)
            self.assertAlmostEqual(r['reaction'][0],10+moment/L,places=8)
            self.assertAlmostEqual(r['reaction'][-2],10-moment/L,places=8)
            self.assertLess(max(abs(r['residual'])),1e-7)

    def test_plastic_global_balance_improves_but_does_not_pass_one_percent_mesh_gate(self):
        errors=[];moment_errors=[]
        for n in (2,8,32):
            m,r=loaded(n)
            errors.append(abs(r['motion'][n]/hinge_reference(24.)-1))
            moment_errors.append(abs(r['reaction'][1]/MP-1))
            self.assertAlmostEqual(sum(r['reaction'][::2]),24.,places=7)
            self.assertAlmostEqual(r['reaction'][1]+L*r['reaction'][-2],24*L/2,places=6)
            self.assertLess(max(abs(r['residual'])),1e-7)
            self.assertGreater(r['dissipation'],0.);self.assertGreater(r['min_normalized_tangent'],1e-10)
            self.assertFalse(r['production_ready'])
        self.assertTrue(all(b<a for a,b in zip(errors,errors[1:])))
        self.assertTrue(all(b<a for a,b in zip(moment_errors,moment_errors[1:])))
        self.assertGreater(errors[-1],.01);self.assertGreater(moment_errors[-1],.01)

    def test_increment_refinement_preserves_proportional_endpoint(self):
        _,a=loaded(8,10);_,b=loaded(8,40)
        np.testing.assert_allclose(a['motion'],b['motion'],atol=1e-9,rtol=1e-8)
        self.assertAlmostEqual(a['dissipation'],b['dissipation'],places=8)

    def test_elastic_unloading_after_yield_preserves_plastic_history(self):
        m,r=loaded(8);old=r['state'];unloaded=m.solve(np.zeros(m.size),old)
        self.assertAlmostEqual(unloaded['motion'][8],r['motion'][8]-hinge_reference(20.)*24/20,places=8)
        self.assertAlmostEqual(unloaded['dissipation'],r['dissipation'],places=8)
        for previous,current in zip(old.histories,unloaded['state'].histories):
            grid=np.linspace(0,1,31)
            np.testing.assert_allclose(np.interp(grid,previous.stations,previous.plastic_curvature),np.interp(grid,current.stations,current.plastic_curvature),atol=1e-11)

    def test_overload_nonconvergence_and_bad_inputs_do_not_advance_committed_state(self):
        m,r=loaded(8);old=r['state'];before=repr(old);force=np.zeros(m.size);force[8]=-26.
        for load in (-26.,-25.,25.,26.):
            force[8]=load
            with self.assertRaisesRegex(ChainRejected,'mechanism'):m.solve(force,old)
        self.assertEqual(repr(old),before)
        couple=np.zeros(m.size);couple[3]=1.
        with self.assertRaisesRegex(ValueError,'couples'):m.solve(couple,old)
        with self.assertRaises(ValueError):m.solve(np.full(m.size,np.nan),old)
        with self.assertRaises(ValueError):PlasticBeamChain(L,EI,MP,4).solve(np.zeros(10),old)
        force[8]=-24.
        with self.assertRaises(ChainRejected):m.solve(force,max_iterations=1)
