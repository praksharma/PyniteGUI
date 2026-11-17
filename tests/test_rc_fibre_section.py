"""Independent material/section references; no RC frame qualification."""
import unittest
import numpy as np
from scipy.integrate import quad
from rc_fibre_section import RCEnvelope,MonotonicRCSection


def section(n=24):
    # Benchmark net concrete rectangle plus two explicitly entered steel areas.
    # This does not generate physical bar holes or a design-code stress block.
    x,w=np.polynomial.legendre.leggauss(n)
    return MonotonicRCSection([(120.*weight,10.*y,'concrete') for y,weight in zip(x,w)]+[(1.,-8.,'steel'),(1.,8.,'steel')])


class RCFibreSectionTests(unittest.TestCase):
    def test_material_envelopes_and_tangents(self):
        m=RCEnvelope()
        for strain,stress in ((0.,0.),(.001,0.),(-.001,-3.),(-.002,-4.)):
            self.assertAlmostEqual(m.stress('concrete',strain)[0],stress)
        for strain in (-.004,-.001,.001,.004):
            stress,tangent=m.stress('steel',strain);h=1e-8
            self.assertAlmostEqual((m.stress('steel',strain+h)[0]-m.stress('steel',strain-h)[0])/(2*h),tangent,places=5)
            self.assertEqual(np.sign(stress),np.sign(strain))
        self.assertAlmostEqual(m.stress('concrete',-.001)[1],2000.)
        with self.assertRaisesRegex(ValueError,'crushing'):m.stress('concrete',-.0021)

    def test_uniform_compression_and_tension_hand_results(self):
        b=section();m=b.material
        for strain in (-.001,.001,.004):
            r=b.evaluate(strain,0.)
            concrete=m.stress('concrete',strain)[0];steel=m.stress('steel',strain)[0]
            self.assertAlmostEqual(r['resultants'][0],240*concrete+2*steel,places=9)
            self.assertAlmostEqual(r['resultants'][1],0.,places=9)
        self.assertEqual(b.evaluate(.004,0.)['stresses'][0],0.)

    def test_bending_against_independent_continuous_integration(self):
        # Every concrete fibre is on the smooth compression parabola.
        e=-.0007;k=.00002;b=section(8)
        def stress(y):
            ratio=-(e-k*y)/.002
            return -4*(2*ratio-ratio*ratio)
        expected=np.array([quad(lambda y:12*stress(y),-10,10)[0],quad(lambda y:-12*y*stress(y),-10,10)[0]])
        for y in (-8.,8.):
            steel=29000*(e-k*y);expected+=[steel,-y*steel]
        np.testing.assert_allclose(b.evaluate(e,k)['resultants'],expected,atol=1e-9)

    def test_section_and_axial_constraint_derivatives(self):
        b=section();e=.0004;k=.00016;r=b.evaluate(e,k)
        for j,h in ((0,1e-8),(1,1e-9)):
            plus=np.array([e,k]);minus=plus.copy();plus[j]+=h;minus[j]-=h
            derivative=(b.evaluate(*plus)['resultants']-b.evaluate(*minus)['resultants'])/(2*h)
            np.testing.assert_allclose(derivative,r['tangent'][:,j],rtol=1e-7,atol=1e-5)
        fixed=b.moment_at_axial_force(k,0.);h=1e-9
        derivative=(b.moment_at_axial_force(k+h,0.)['resultants'][1]-b.moment_at_axial_force(k-h,0.)['resultants'][1])/(2*h)
        self.assertAlmostEqual(derivative,fixed['flexural_tangent_at_fixed_axial_force'],delta=.01)
        self.assertLess(abs(fixed['resultants'][0]),1e-7)

    def test_moment_curvature_signed_symmetry_yield_and_refinement(self):
        values=[]
        for n in (24,48,96):
            b=section(n);r=b.moment_at_axial_force(.0003,0.)
            self.assertGreater(r['stresses'][-2],60.)
            self.assertGreater(r['resultants'][1],0.)
            reverse=b.moment_at_axial_force(-.0003,0.)
            self.assertAlmostEqual(reverse['resultants'][1],-r['resultants'][1],places=7)
            values.append(r['resultants'][1]);self.assertFalse(r['production_ready'])
        self.assertLess(abs(values[-1]/values[-2]-1),.005)

    def test_axial_compatibility_against_continuous_section_oracle(self):
        from scipy.optimize import brentq
        def reference(k):
            def resultants(e):
                start=max(-10.,min(10.,e/k))
                def concrete(y):
                    ratio=(k*y-e)/.002
                    return -4.*(2*ratio-ratio*ratio)
                N=quad(lambda y:12*concrete(y),start,10.,epsabs=1e-10)[0]
                M=quad(lambda y:-12*y*concrete(y),start,10.,epsabs=1e-10)[0]
                for y in (-8.,8.):
                    trial=29000*(e-k*y)
                    steel=trial if abs(trial)<=60 else np.sign(trial)*(60+.01*(abs(trial)-60))
                    N+=steel;M-=y*steel
                return N,M
            strain=brentq(lambda e:resultants(e)[0],-.002+k*10.,.02-k*10.,xtol=1e-15)
            return resultants(strain)[1]
        for k in (.00005,.0001,.0002,.0003):
            r=section(96).moment_at_axial_force(k,0.)
            self.assertLess(abs(r['resultants'][1]/reference(k)-1),.002)

    def test_units_origin_shift_and_fail_closed_limits(self):
        b=section();r=b.evaluate(-.0007,.00002);a=25.4;force=4448.2216152605
        m=b.material;scaled=RCEnvelope(m.fc*force/a**2,m.peak_strain,m.steel_E*force/a**2,m.steel_yield*force/a**2,m.hardening_ratio)
        q=MonotonicRCSection([(A*a*a,y*a,kind) for A,y,kind in b.fibres],scaled).evaluate(-.0007,.00002/a)
        np.testing.assert_allclose(q['resultants'],r['resultants']*[force,force*a],rtol=1e-12)
        shifted=MonotonicRCSection([(A,y+7.,kind) for A,y,kind in b.fibres]).evaluate(-.0007+.00002*7,.00002)
        np.testing.assert_allclose(shifted['resultants'],[r['resultants'][0],r['resultants'][1]-7*r['resultants'][0]],atol=1e-9)
        with self.assertRaises(ValueError):b.moment_at_axial_force(.01,0.)
        with self.assertRaises(ValueError):b.moment_at_axial_force(0.,-10000.)
        with self.assertRaises(ValueError):MonotonicRCSection([(0.,0.,'steel')])
        with self.assertRaises(ValueError):RCEnvelope(hardening_ratio=1.)
