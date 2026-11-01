"""Independent energy/quadrature/reference checks, with opening recovery rejection."""
from functools import lru_cache
from math import factorial
from pathlib import Path
import unittest
import numpy as np
from plate_energy_reference import OpeningEnergyReference,hermite_basis,shape,element_energy,CONDITION_LIMIT
from plate_reference import navier
from quad_shear_boundaries import solve_case,relative_l2,opening_mean_shear

BOXES=((0.,20.,0.,20.),(0.,20.,40.,80.),(20.,40.,48.,72.))


@lru_cache(maxsize=24)
def reference(n=24,order=2,hole=True,width=120.,height=120.,ny=None):
    return OpeningEnergyReference(width,height,.2,40. if hole else 0.,40. if hole else 0.,nx=n,ny=ny,order=order)


def monomial(x,y,p,q,dx=0,dy=0):
    if dx>p or dy>q:return np.zeros_like(x+y,dtype=float)
    return factorial(p)/factorial(p-dx)*factorial(q)/factorial(q-dy)*x**(p-dx)*y**(q-dy)


def nodal_monomial(order,hx,hy,p,q):
    return np.array([monomial(x,y,p,q,dx,dy) for x,y in ((0.,0.),(hx,0.),(hx,hy),(0.,hy))
                     for dy in range(order+1) for dx in range(order+1)])


class PlateEnergyFormulationTests(unittest.TestCase):
    def test_endpoint_interpolation_and_exact_tensor_polynomial_derivatives(self):
        for order in (1,2):
            basis=hermite_basis(order)
            for end in (0,1):
                for derivative in range(order+1):
                    values=[polynomials[derivative](end) for polynomials in basis]
                    np.testing.assert_allclose(values,np.eye(2*(order+1))[end*(order+1)+derivative],atol=1e-12)
            for hx,hy in ((.7,1.1),(.07,11.)):
                for p,q in ((0,0),(1,0),(0,1),(2,2),(2*order+1,2*order+1)):
                    dofs=nodal_monomial(order,hx,hy,p,q)
                    s=np.array([.13,.45,.71]);t=np.array([.23,.66,.84])
                    for dx,dy in ((0,0),(1,0),(0,1),(2,0),(1,1),(0,2),(3,0),(1,2),(2,1),(0,3)):
                        actual=shape(order,hx,hy,s,t,dx,dy)@dofs
                        expected=monomial(s*hx,t*hy,p,q,dx,dy)
                        np.testing.assert_allclose(actual,expected,rtol=1e-9,atol=1e-9)

    def test_stiffness_is_continuum_bending_energy_and_rigid_modes_have_zero_energy(self):
        hx,hy,nu=.7,1.1,.2
        for order in (1,2):
            matrix,force=element_energy(order,hx,hy,nu)
            np.testing.assert_allclose(matrix,matrix.T,atol=1e-11)
            for p,q in ((0,0),(1,0),(0,1),(2,2),(2*order+1,2*order+1)):
                dofs=nodal_monomial(order,hx,hy,p,q)
                expected=0.
                if p>=2:expected+=(p*(p-1))**2*hx**(2*p-3)/(2*p-3)*hy**(2*q+1)/(2*q+1)
                if q>=2:expected+=(q*(q-1))**2*hy**(2*q-3)/(2*q-3)*hx**(2*p+1)/(2*p+1)
                if p and q:
                    common=hx**(2*p-1)/(2*p-1)*hy**(2*q-1)/(2*q-1)
                    expected+=(2*nu*p*(p-1)*q*(q-1)+2*(1-nu)*(p*q)**2)*common
                self.assertAlmostEqual(float(dofs@matrix@dofs),expected,delta=1e-9*max(1.,expected))
                load_integral=hx**(p+1)/(p+1)*hy**(q+1)/(q+1)
                self.assertAlmostEqual(force@dofs,load_integral,delta=1e-11*max(1.,abs(load_integral)))

    def test_simply_supported_trace_is_not_clamped_and_opening_has_no_hidden_supports(self):
        r=reference(12)
        edge=np.array([[0.,25.],[0.,60.],[120.,75.],[40.,0.],[70.,120.]])
        np.testing.assert_allclose(r.displacement(edge),0.,atol=1e-9)
        self.assertGreater(abs(r.derivative([[0.,60.]],1,0)[0]),1.)
        self.assertGreater(r.displacement([[40.,60.]])[0],1.)
        for point in ((60.,60.),(-1.,60.),(121.,60.)):
            with self.assertRaises(ValueError):r.displacement([point])
        for box in ((40.,80.,40.,80.),(0.,130.,0.,20.),(60.,60.0000001,60.,60.0000001)):
            with self.assertRaises(ValueError):r.mean_shears(box)
        self.assertAlmostEqual(r.diagnostics['area'],12800.)

    def test_units_scale_fields_and_compliance_without_changing_normalized_solve(self):
        a=reference(6,width=120.,height=180.,hole=False,ny=9)
        b=reference(6,width=12.,height=18.,hole=False,ny=9)
        points=np.array([[30.,60.],[60.,90.]])
        np.testing.assert_allclose(a.displacement(points),b.displacement(points/10)*10**4,rtol=1e-10)
        np.testing.assert_allclose(a.moments(points),b.moments(points/10)*10**2,rtol=1e-10)
        np.testing.assert_allclose(a.shears(points),b.shears(points/10)*10,rtol=1e-10)
        np.testing.assert_allclose(a.mean_shears((0,20,30,70)),b.mean_shears((0,2,3,7))*10,rtol=1e-10)
        self.assertAlmostEqual(a.compliance/b.compliance,10**6,places=6)

    def test_invalid_geometry_grid_budget_and_derivative_inputs_are_rejected(self):
        for kwargs in ({'width':0.},{'nu':.5},{'nx':True},{'nx':10},{'hole_width':0.},
                       {'hole_width':120.},{'nx':120},{'width':float('nan')},{'order':3}):
            with self.subTest(kwargs=kwargs),self.assertRaises(ValueError):OpeningEnergyReference(**kwargs)
        with self.assertRaisesRegex(ValueError,'1e8 stiffness-condition'):
            OpeningEnergyReference(120.,120.,.2,0.,0.,nx=192,ny=3,order=2)
        import ast
        source=ast.parse(Path(__file__).with_name('plate_energy_reference.py').read_text())
        imports=[item.module for item in ast.walk(source) if isinstance(item,ast.ImportFrom) and item.module]
        imports += [alias.name for item in ast.walk(source) if isinstance(item,ast.Import) for alias in item.names]
        self.assertFalse(any(name.split('.')[0] in ('Pynite','pynitegui','brecon') for name in imports))
        r=reference(6)
        for points,dx,dy in (([[1,2,3]],0,0),([[np.nan,20]],0,0),([[20,20]],4,0),([[20,20]],0,-1)):
            with self.assertRaises(ValueError):r.derivative(points,dx,dy)


class OpeningEnergyBenchmarkTests(unittest.TestCase):
    def test_intact_limit_matches_independent_navier_displacement_moment_and_mean_shear(self):
        points=np.array([[30.,60.],[60.,90.],[90.,120.]])
        w,m,q=navier(points,120,180,.2,1.,1.,terms=320)
        for order in (1,2):
            errors=[]
            for n in (6,12,24):
                r=reference(n,order,hole=False,width=120.,height=180.,ny=3*n//2)
                errors.append(np.linalg.norm(r.displacement(points)-w)/np.linalg.norm(w))
                if n==24:
                    self.assertLess(errors[-1],1e-6)
                    self.assertLess(np.linalg.norm(r.moments(points)-m)/np.linalg.norm(m),.002)
                    if order==2:self.assertLess(np.linalg.norm(r.shears(points)-q)/np.linalg.norm(q),.0001)
            self.assertLess(errors[-1],errors[0]/100.)
        # Area means avoid dependence on which side of a C1 cell interface owns
        # a discontinuous third derivative. Independent Navier quadrature.
        box=(0.,20.,30.,70.);g,weights=np.polynomial.legendre.leggauss(48)
        x,y=np.meshgrid(10*(g+1),20*g+50);means=np.outer(weights,weights).ravel()/4@navier(np.column_stack((x.ravel(),y.ravel())),120,180,.2,1.,1.,terms=320)[2]
        for order in (1,2):
            actual=reference(24,order,hole=False,width=120.,height=180.,ny=36).mean_shears(box)
            self.assertLess(np.linalg.norm(actual-means)/np.linalg.norm(means),.003)

    def test_opening_mean_shear_converges_in_two_independent_polynomial_families(self):
        final=[]
        for order in (1,2):
            history=[];compliances=[]
            for n in (48,72,96):
                r=reference(n,order);history.append(np.array([r.mean_shears(box) for box in BOXES]));compliances.append(r.compliance)
                self.assertLess(r.condition,CONDITION_LIMIT)
                self.assertLess(r.diagnostics['backward_error'],1e-11)
                self.assertLess(r.diagnostics['energy_relative_error'],1e-8)
                self.assertLess(r.diagnostics['force_moment_relative_error'],1e-8)
            self.assertTrue(np.all(np.diff(compliances)>0))
            for index in range(3):
                gap=np.linalg.norm(history[-1][index]-history[-2][index])/np.linalg.norm(history[-1][index])
                self.assertLess(gap,.005)
            final.append(history[-1])
        for cubic,quintic in zip(*final):self.assertLess(np.linalg.norm(cubic-quintic)/np.linalg.norm(quintic),.005)
        self.assertLess(abs(reference(96,1).compliance/reference(96,2).compliance-1),1e-5)

    def test_opening_pointwise_reference_is_checked_away_from_corners_and_fit_fails_near_rim(self):
        coarse,fine=reference(72),reference(96);errors=[]
        for size in (10.,5.,4.):
            sample=solve_case('opening',size)['Service'];points=sample['points'];x,y=points.T
            corners=np.array([[40,40],[40,80],[80,40],[80,80]])
            distance=np.min(np.linalg.norm(points[:,None]-corners[None],axis=2),axis=1)
            away=sample['valid']&(distance>=10.)
            rim=away&(x>=20.)&(x<=40.)&(y>=48.)&(y<=72.)
            a=-1e-7*coarse.shears(points);b=-1e-7*fine.shears(points)
            for region in (away,rim):self.assertLess(relative_l2(a,b,sample['areas'],region),.005)
            errors.append(relative_l2(sample['shear'],b,sample['areas'],rim))
            for name,factor in (('Reverse',-2.),('Zero',0.)):
                other=solve_case('opening',size)[name]
                np.testing.assert_allclose(other['shear'],factor*sample['shear'],rtol=1e-7,atol=1e-12)
        self.assertTrue(all(b<a for a,b in zip(errors,errors[1:])),errors)
        self.assertGreater(errors[-1],.10)  # Known physical recovery gap, not a reference failure.
        means=-1e-7*fine.mean_shears(BOXES[-1])
        sample=solve_case('opening',4.)['Service'];actual=opening_mean_shear(sample,BOXES[-1])
        self.assertGreater(np.linalg.norm(actual-means)/np.linalg.norm(means),.20)
