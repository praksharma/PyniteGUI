"""Local plastic flow, signed reversals, tangents and explicit nonconvex rejection."""
from itertools import product
import unittest
import numpy as np
from section_return_map import SectionReturnMap,MaterialState,RejectedReturn,surface,surface_curvature
from section_return_reference import nonconvex_witness
from section_return_cases import STIFFNESS,CAPACITIES,cycle,mixed


class SectionReturnTests(unittest.TestCase):
    def test_polynomial_matches_engine_and_signed_derivatives_match_differences(self):
        from Pynite import FEModel3D
        m=FEModel3D();m.add_material('Steel',29000.,11200.,.3,0.,50.)
        m.add_steel_section('I',10.,30.,100.,1.,10.,20.,'Steel');section=m.sections['I']
        for point in np.random.default_rng(82).uniform(-1.2,1.2,(30,3)):
            value,gradient,hessian=surface(point)
            self.assertAlmostEqual(value,section.Phi(*(point*CAPACITIES)),places=11)
            step=1e-5
            numeric_g=np.array([(surface(point+np.eye(3)[i]*step)[0]-surface(point-np.eye(3)[i]*step)[0])/(2*step) for i in range(3)])
            numeric_h=np.array([(surface(point+np.eye(3)[i]*step)[1]-surface(point-np.eye(3)[i]*step)[1])/(2*step) for i in range(3)]).T
            np.testing.assert_allclose(gradient,numeric_g,rtol=1e-7,atol=1e-8)
            np.testing.assert_allclose(hessian,numeric_h,rtol=1e-7,atol=1e-8)

    def test_all_three_uniaxial_cycles_match_exact_force_plasticity_and_dissipation(self):
        for axis in range(3):
            finals=[]
            for steps in (1,10,40):
                r=cycle(axis,steps)
                self.assertLess(r['max_force_error'],1e-11);self.assertLess(r['max_plastic_strain_error'],1e-11)
                self.assertLess(r['max_dissipation_error'],1e-10);self.assertLess(r['max_incremental_energy_error'],1e-12)
                self.assertLess(r['max_yield_overshoot'],1e-11)
                finals.append(r['final_state']['dissipation'])
            np.testing.assert_allclose(finals,finals[0],atol=1e-11,rtol=1e-10)

    def test_unloading_is_elastic_and_reverse_yield_has_the_signed_normal(self):
        material=SectionReturnMap(STIFFNESS,CAPACITIES)
        for axis in range(3):
            direction=np.eye(3)[axis]*CAPACITIES[axis]/STIFFNESS[axis,axis]
            yielded=material.update(1.5*direction);self.assertTrue(yielded['plastic'])
            unload=material.update(np.zeros(3),yielded['state'])
            self.assertFalse(unload['plastic']);self.assertIs(unload['state'],yielded['state'])
            np.testing.assert_allclose(unload['tangent'],STIFFNESS)
            self.assertAlmostEqual(unload['force'][axis],-.5*CAPACITIES[axis])
            reverse=material.update(-1.5*direction,unload['state'])
            self.assertTrue(reverse['plastic']);self.assertAlmostEqual(reverse['force'][axis],-CAPACITIES[axis])
            self.assertLess(reverse['state'].plastic_strain[axis],0.)
            self.assertGreater(reverse['dissipation_increment'],0.)

    def test_mixed_local_branches_match_independent_multistart_optimizer_and_tangent(self):
        for base in ((1.2,.1,.1),(.1,1.2,.1),(.1,.2,1.2)):
            for signs in product((-1.,1.),repeat=3):
                r=mixed(tuple(np.array(base)*signs))
                self.assertLess(r['reference_error'],2e-6)
                self.assertLess(r['consistent_tangent_relative_error'],2e-7)
                self.assertLess(abs(r['yield_value']-1),1e-10)
                self.assertGreater(r['curvature'],1e-8);self.assertGreater(r['dissipation_increment'],0.)
                self.assertGreaterEqual(r['reference']['successful_starts'],6)

    def test_nonconvex_domain_has_an_explicit_counterexample_and_is_rejected(self):
        witness=nonconvex_witness()
        self.assertTrue(all(v<1 for v in witness['endpoint_phi']));self.assertGreater(witness['midpoint_phi'],1.)
        self.assertLess(witness['tangential_second_difference'],-.24)
        self.assertAlmostEqual(surface_curvature(witness['boundary']),witness['tangential_second_difference'],delta=1e-6)
        material=SectionReturnMap(STIFFNESS,CAPACITIES);old=MaterialState()
        for signs in product((-1.,1.),repeat=2):
            trial=np.array((.8*signs[0],0.,.8*signs[1]));strain=np.linalg.solve(STIFFNESS,CAPACITIES*trial)
            with self.assertRaisesRegex(RejectedReturn,'curvature'):material.update(strain,old)
        self.assertEqual(old,MaterialState())

    def test_force_length_scaling_and_orthant_covariance(self):
        trial=np.array((.1,.2,1.2));C=STIFFNESS.copy();C[0,2]=C[2,0]=.03*np.sqrt(C[0,0]*C[2,2])
        material=SectionReturnMap(C,CAPACITIES);strain=np.linalg.solve(C,CAPACITIES*trial);base=material.update(strain)
        S=np.diag((-1.,1.,-1.));reflected=SectionReturnMap(S@C@S,CAPACITIES).update(S@strain)
        np.testing.assert_allclose(reflected['force'],S@base['force'],atol=1e-8)
        np.testing.assert_allclose(reflected['tangent'],S@base['tangent']@S,atol=1e-6)
        length,force=1000.,.001
        D=np.diag((1.,1/length,1/length));F=np.diag((force,force*length,force*length))
        scaled=SectionReturnMap(F@C@np.linalg.inv(D),F@CAPACITIES).update(D@strain)
        np.testing.assert_allclose(scaled['force'],F@base['force'],rtol=1e-9,atol=1e-9)
        np.testing.assert_allclose(scaled['state'].plastic_strain,D@np.array(base['state'].plastic_strain),rtol=1e-9,atol=1e-13)
        self.assertAlmostEqual(scaled['dissipation_increment'],force*base['dissipation_increment'],places=12)

    def test_failure_never_commits_history_and_invalid_inputs_are_rejected(self):
        supplied=[0.,0.,0.];committed=MaterialState(supplied);supplied[0]=1.
        self.assertEqual(committed.plastic_strain,(0.,0.,0.))
        material=SectionReturnMap(STIFFNESS,CAPACITIES);old=MaterialState()
        strain=np.linalg.solve(STIFFNESS,CAPACITIES*np.array((.1,.2,1.2)))
        with self.assertRaisesRegex(RejectedReturn,'iteration limit'):material.update(strain,old,max_iterations=1)
        self.assertEqual(old,MaterialState())
        with self.assertRaisesRegex(RejectedReturn,'bounded'):material.update(np.linalg.solve(STIFFNESS,CAPACITIES*np.array((4.,0.,0.))))
        for C,cap in ((np.diag((-1.,1.,1.)),CAPACITIES),(STIFFNESS,[0.,1.,1.]),(STIFFNESS,[np.inf,1.,1.])):
            with self.assertRaises(ValueError):SectionReturnMap(C,cap)
        with self.assertRaises(ValueError):material.update([np.nan,0.,0.])
        with self.assertRaises(ValueError):material.update([0.,0.,0.],MaterialState(dissipation=-1.))
