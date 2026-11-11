"""Closed-form bending, virtual work and hinge-location checks."""
import unittest
import numpy as np
from beam_gradient_compatibility import integrate


class BeamGradientTests(unittest.TestCase):
    def test_elastic_flexibility_and_nodal_stiffness_match_closed_form(self):
        for L,EI in ((120.,2900000.),(2.,3.)):
            r=integrate(L,EI,[7.,-3.])
            np.testing.assert_allclose(r['flexibility'],L/(6*EI)*np.array([[2.,-1.],[-1.,2.]]),rtol=1e-12)
            expected=EI/L**3*np.array([[12,6*L,-12,6*L],[6*L,4*L**2,-6*L,2*L**2],[-12,-6*L,12,-6*L],[6*L,2*L**2,-6*L,4*L**2]])
            np.testing.assert_allclose(r['nodal_elastic_stiffness'],expected,rtol=1e-12,atol=1e-10)
            np.testing.assert_allclose(expected@np.array([2.,.3,2.+.3*L,.3]),0.,atol=1e-8)

    def test_zone_location_changes_tip_translation_at_equal_plastic_rotation(self):
        L=120.;k=.001
        for a,b in ((0.,12.),(54.,66.),(108.,120.)):
            r=integrate(L,2900000.,[100.,-20.],[(a,b,k)])
            rotation=k*(b-a);translation=rotation*(L-(a+b)/2)
            self.assertAlmostEqual(r['plastic_tip_rotation'],rotation)
            self.assertAlmostEqual(r['plastic_tip_translation'],translation)
            np.testing.assert_allclose(r['plastic_basic_rotations'],[-translation/L,rotation-translation/L],atol=1e-14)

    def test_virtual_work_with_gradient_and_multiple_signed_zones(self):
        L=120.;q=np.array([100.,-20.]);zones=[(0.,10.,.001),(40.,70.,-.0002),(100.,120.,.0004)]
        r=integrate(L,2900000.,q,zones)
        expected=sum(k*(-q[0]*(b-a)+(q[0]+q[1])*(b*b-a*a)/(2*L)) for a,b,k in zones)
        self.assertAlmostEqual(r['curvature_work'],expected,places=12)
        self.assertAlmostEqual(q@r['plastic_basic_rotations'],expected,places=12)
        reversed_result=integrate(L,2900000.,-q,[(a,b,-k) for a,b,k in zones])
        self.assertAlmostEqual(reversed_result['curvature_work'],expected)
        split=integrate(L,2900000.,q,[(0.,5.,.001),(5.,10.,.001),*zones[1:]])
        np.testing.assert_allclose(split['basic_rotations'],r['basic_rotations'],atol=1e-14)

    def test_scaling_and_invalid_zone_geometry(self):
        r=integrate(120.,2900000.,[100.,-20.],[(0.,12.,.001)])
        s=integrate(120000.,2900000.*.001*1000**2,[100.,-20.],[(0.,12000.,.000001)])
        np.testing.assert_allclose(r['basic_rotations'],s['basic_rotations'],rtol=1e-12)
        self.assertAlmostEqual(s['plastic_tip_translation'],1000*r['plastic_tip_translation'])
        for zones in ([(10.,5.,1.)],[(-1.,5.,1.)],[(0.,121.,1.)],[(0.,20.,1.),(10.,30.,1.)],[(0.,10.,np.nan)]):
            with self.assertRaises(ValueError):integrate(120.,1.,[0.,0.],zones)
