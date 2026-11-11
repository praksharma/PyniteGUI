"""Generated plastic fronts, independent integration, unloading and member tangent."""
import unittest
import numpy as np
from scipy.integrate import quad
from plastic_bending_member import PlasticBendingMember,BendingHistory
from section_return_reference import scalar_cycle

L=120.;EI=2900000.;MP=1000.


def motion_for_curvature(a,b):
    # Integrate kappa(s)=a+b*s with fixed displacement/rotation at x=0.
    return np.array((0.,0.,L**2*(a/2+b/6),L*(a+b/2)))


class PlasticBendingMemberTests(unittest.TestCase):
    def test_elastic_matrix_and_rigid_modes(self):
        m=PlasticBendingMember(L,EI,MP);r=m.update(motion_for_curvature(.1*MP/EI,.2*MP/EI))
        K=EI/L**3*np.array([[12,6*L,-12,6*L],[6*L,4*L**2,-6*L,2*L**2],[-12,-6*L,12,-6*L],[6*L,2*L**2,-6*L,4*L**2]])
        np.testing.assert_allclose(r['tangent'],K,rtol=1e-12,atol=1e-9)
        np.testing.assert_allclose(m.update([2.,.1,2+.1*L,.1])['force'],0.,atol=1e-9)

    def test_generated_front_and_nodal_response_match_independent_clipped_integrals(self):
        m=PlasticBendingMember(L,EI,MP);a=1.8*MP/EI;b=-2.6*MP/EI;u=motion_for_curvature(a,b);r=m.update(u)
        front=(MP/EI-a)/b
        self.assertAlmostEqual(r['plastic_loading_length'],front*L,places=10)
        def shape(x):
            s=x/L;return np.array(((-6+12*s)/L**2,(-4+6*s)/L,(6-12*s)/L**2,(-2+6*s)/L))
        expected=np.array([quad(lambda x:shape(x)[i]*np.clip(EI*(a+b*x/L),-MP,MP),0,L,points=[front*L],epsabs=1e-10)[0] for i in range(4)])
        np.testing.assert_allclose(r['force'],expected,rtol=1e-11,atol=1e-9)
        expected_work=MP*quad(lambda x:max(a+b*x/L-MP/EI,0),0,L,points=[front*L])[0]
        self.assertAlmostEqual(r['dissipation_increment'],expected_work,places=10)
        self.assertTrue(any(abs(x-front)<1e-12 for x in r['state'].stations))

    def test_uniform_curvature_cycle_matches_scalar_reference_and_energy(self):
        m=PlasticBendingMember(L,EI,MP);old=BendingHistory();levels=np.array((0.,.5,1.5,0.,-1.5,0.))*MP/EI
        exact=scalar_cycle(levels,EI,MP)
        for i,k in enumerate(levels):
            r=m.update(motion_for_curvature(k,0.),old);old=r['state']
            np.testing.assert_allclose(r['force'],[0.,-exact[i,0],0.,exact[i,0]],atol=1e-8)
            self.assertAlmostEqual(old.dissipation,L*exact[i,2],places=9)
            self.assertAlmostEqual(r['elastic_energy'],L*exact[i,0]**2/(2*EI),places=9)

    def test_moving_front_tangent_with_frozen_history_matches_differences(self):
        m=PlasticBendingMember(L,EI,MP);old=m.update(motion_for_curvature(1.6*MP/EI,-MP/EI))['state']
        u=motion_for_curvature(-.35*MP/EI,1.8*MP/EI);r=m.update(u,old);columns=[]
        for i in range(4):
            h=1e-6*MP/EI*(L**2 if i%2==0 else L);d=np.eye(4)[i]*h
            columns.append((m.update(u+d,old)['force']-m.update(u-d,old)['force'])/(2*h))
        self.assertLess(np.linalg.norm(np.array(columns).T-r['tangent'])/np.linalg.norm(r['tangent']),2e-7)
        np.testing.assert_allclose(r['tangent'],r['tangent'].T,atol=1e-9)
        self.assertGreaterEqual(np.linalg.eigvalsh(r['tangent'])[0],-1e-7)

    def test_nonuniform_history_matches_section_returns_and_incremental_energy(self):
        from section_return_map import SectionReturnMap,MaterialState
        section=SectionReturnMap(np.diag([290000.,870000.,EI]),[500.,500.,MP])
        m=PlasticBendingMember(L,EI,MP);old=BendingHistory();previous_u=np.zeros(4);previous_energy=0.
        for a,b in ((1.6,-1.),(-.35,1.8),(.2,.1)):
            u=motion_for_curvature(a*MP/EI,b*MP/EI);r=m.update(u,old)
            for s in np.linspace(.013,.987,17):
                kp=np.interp(s,old.stations,old.plastic_curvature)
                local=section.update([0.,0.,float(m.B(s)@u)],MaterialState((0.,0.,kp)))
                self.assertAlmostEqual(np.interp(s,r['state'].stations,r['state'].plastic_curvature),local['state'].plastic_strain[2],places=11)
            points=sorted(set(old.stations+r['state'].stations))
            def numerical(x):
                s=x/L;ep_new=np.interp(s,r['state'].stations,r['state'].plastic_curvature)
                ep_old=np.interp(s,old.stations,old.plastic_curvature)
                change=float(m.B(s)@(u-previous_u))-ep_new+ep_old
                return .5*EI*change**2
            algorithmic=quad(numerical,0,L,points=[x*L for x in points[1:-1]],epsabs=1e-10)[0]
            balance=r['force']@(u-previous_u)-(r['elastic_energy']-previous_energy)-r['dissipation_increment']
            self.assertAlmostEqual(balance,algorithmic,places=8)
            old=r['state'];previous_u=u;previous_energy=r['elastic_energy']

    def test_scaling_state_ownership_and_rejected_trial(self):
        m=PlasticBendingMember(L,EI,MP);u=motion_for_curvature(1.8*MP/EI,-2.6*MP/EI);r=m.update(u)
        scale=1000.;f=.001;other=PlasticBendingMember(L*scale,EI*f*scale**2,MP*f*scale)
        mapped=u*np.array([scale,1.,scale,1.]);s=other.update(mapped)
        np.testing.assert_allclose(s['force'],r['force']*np.array([f,f*scale,f,f*scale]),rtol=1e-10,atol=1e-8)
        self.assertAlmostEqual(s['state'].dissipation,r['state'].dissipation*f*scale,places=9)
        with self.assertRaisesRegex(ValueError,'configuration'):PlasticBendingMember(L*2,EI,MP).update(u,r['state'])
        with self.assertRaises(ValueError):m.update([np.nan,0.,0.,0.],r['state'])
        self.assertEqual(r['state'],m.update(u)['state'])
        with self.assertRaises(AttributeError):m.L=2*L
