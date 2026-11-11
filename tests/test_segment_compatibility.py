"""Independent constant-moment/axial references and work-conjugate length mapping."""
import unittest
import numpy as np
from constant_resultant_segment import ConstantResultantSegment,SegmentState
from section_return_cases import STIFFNESS,CAPACITIES
from section_return_reference import scalar_cycle
from section_return_map import RejectedReturn


class SegmentCompatibilityTests(unittest.TestCase):
    def test_exact_axial_and_pure_end_couple_response_without_double_elastic_flexibility(self):
        L=120.
        for axis in range(3):
            histories=[]
            for lp in (3.,12.,60.,120.):
                model=ConstantResultantSegment(STIFFNESS,CAPACITIES,L,lp);state=SegmentState();rows=[]
                levels=np.r_[np.linspace(0,1.5,21),np.linspace(1.5,-1.5,41)[1:],np.linspace(-1.5,0,21)[1:]]
                q=CAPACITIES[axis]*L/STIFFNESS[axis,axis]
                exact=scalar_cycle(levels*q,STIFFNESS[axis,axis]/L,CAPACITIES[axis])
                for i,level in enumerate(levels):
                    u=np.eye(3)[axis]*level*q;r=model.update(u,state);state=r['state'];rows.append(r['force'][axis])
                    self.assertAlmostEqual(r['force'][axis],exact[i,0],places=8)
                    self.assertAlmostEqual(state.plastic_deformation[axis],exact[i,1],places=10)
                    self.assertAlmostEqual(state.dissipation,exact[i,2],places=9)
                    np.testing.assert_allclose(r['zone_deformation']+r['remainder_deformation'],u,atol=1e-10)
                    np.testing.assert_allclose(r['plastic_zone_strain']*lp,state.plastic_deformation,atol=1e-12)
                    self.assertAlmostEqual(r['zone_dissipation_density']*lp,state.dissipation,places=10)
                histories.append(rows)
            np.testing.assert_allclose(histories,np.tile(histories[0],(4,1)),atol=1e-9)

    def test_elastic_energy_partition_and_endpoint_work_identity(self):
        model=ConstantResultantSegment(STIFFNESS,CAPACITIES,120.,12.);state=SegmentState();previous_u=np.zeros(3);previous_ep=np.zeros(3);previous_energy=0.
        for level in (0.,.5,1.5,0.,-1.5,0.):
            u=np.array((0.,0.,level*CAPACITIES[2]*120/STIFFNESS[2,2]));r=model.update(u,state)
            ep=np.array(r['state'].plastic_deformation);du_el=u-previous_u-ep+previous_ep
            work=float(r['force']@(u-previous_u));numerical=.5*du_el@(STIFFNESS/120)@du_el
            self.assertAlmostEqual(work-(r['elastic_energy']-previous_energy)-r['dissipation_increment'],numerical,places=11)
            self.assertAlmostEqual(r['elastic_energy'],r['zone_elastic_energy']+r['remainder_elastic_energy'],places=12)
            state=r['state'];previous_u=u;previous_ep=ep;previous_energy=r['elastic_energy']

    def test_mixed_tangent_at_fixed_history_matches_member_deformation_derivatives(self):
        model=ConstantResultantSegment(STIFFNESS,CAPACITIES,120.,6.)
        u=np.linalg.solve(STIFFNESS/120,CAPACITIES*np.array((.1,.2,1.2)));r=model.update(u);columns=[]
        for i in range(3):
            delta=np.eye(3)[i]*1e-5*CAPACITIES[i]/(STIFFNESS[i,i]/120)
            columns.append((model.update(u+delta)['force']-model.update(u-delta)['force'])/(2*delta[i]))
        self.assertLess(np.linalg.norm(np.array(columns).T-r['tangent'])/np.linalg.norm(r['tangent']),2e-7)
        np.testing.assert_allclose(r['zone_deformation']+r['remainder_deformation'],u,atol=1e-10)

    def test_hinge_strain_changes_with_length_but_total_rotation_and_work_do_not(self):
        u=np.array((0.,0.,1.5*CAPACITIES[2]*120/STIFFNESS[2,2]))
        short=ConstantResultantSegment(STIFFNESS,CAPACITIES,120.,6.).update(u)
        long=ConstantResultantSegment(STIFFNESS,CAPACITIES,120.,60.).update(u)
        np.testing.assert_allclose(short['force'],long['force'])
        np.testing.assert_allclose(short['plastic_zone_strain'],10*long['plastic_zone_strain'])
        self.assertAlmostEqual(short['state'].dissipation,long['state'].dissipation)
        np.testing.assert_allclose(short['tangent'],long['tangent'])

    def test_invalid_lengths_and_failed_trial_do_not_commit_state(self):
        for L,lp in ((0.,1.),(120.,0.),(120.,121.),(120.,np.nan),(True,1.)):
            with self.assertRaises(ValueError):ConstantResultantSegment(STIFFNESS,CAPACITIES,L,lp)
        model=ConstantResultantSegment(STIFFNESS,CAPACITIES,120.,12.);old=SegmentState()
        u=np.linalg.solve(STIFFNESS/120,CAPACITIES*np.array((.8,0.,.8)))
        with self.assertRaisesRegex(RejectedReturn,'curvature'):model.update(u,old)
        self.assertEqual(old,SegmentState())
        supplied=[0.,0.,0.];committed=SegmentState(supplied);supplied[0]=1.
        self.assertEqual(committed.plastic_deformation,(0.,0.,0.))
