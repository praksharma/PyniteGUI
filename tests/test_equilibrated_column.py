"""Positive elastic correction checks; no combined-plastic qualification."""
import unittest
import numpy as np
from Pynite.Member3D import Member3D
from combined_pushover_probe import _build,CRITICAL
from equilibrated_beam_column import ElasticSystem,RejectedState
from equilibrated_column_cases import corrected


class EquilibratedColumnTests(unittest.TestCase):
    def test_preload_and_ramp_refine_to_independent_fields_with_the_same_endpoint(self):
        for ratio in (-.3,0.,.1,.3):
            paths=[]
            for path in ('preload','ramp'):
                errors=[]
                for segments in (2,4,8):
                    result=corrected(segments,ratio,20,path);f=result['final'];errors.append(f['continuum_relative_error'])
                    self.assertLess(f['discrete_relative_error'],1e-8)
                    self.assertLess(f['mean_axial_error_kip'],1e-8)
                    self.assertLess(f['rotation_relative_error'],.001)
                    self.assertLess(f['max_equilibrium_residual'],1e-8)
                    self.assertLess(np.linalg.norm(f['deformed_moment_residual_kip_in']),.012)
                    self.assertLess(f['max_scaled_residual'],1.)
                    self.assertLess(f['max_yield_interaction'],1e-10)
                if ratio:self.assertTrue(all(b<a/10 for a,b in zip(errors,errors[1:])))
                self.assertLess(errors[-1],3e-7);self.assertLess(result['final']['rotation_relative_error'],3e-7);paths.append(result)
            self.assertAlmostEqual(paths[0]['final']['tip_translation_in'],paths[1]['final']['tip_translation_in'],places=11)

    def test_endpoint_is_independent_of_increment_size_and_no_patch_leaks(self):
        original=Member3D.kg
        final=[corrected(8,.3,n)['final']['tip_translation_in'] for n in (1,20,100,400)]
        np.testing.assert_allclose(final,final[0],rtol=1e-10,atol=1e-11)
        self.assertIs(Member3D.kg,original)

    def test_zero_reversal_planes_and_translated_origins(self):
        for path in ('preload','ramp'):
            base=corrected(4,.3,10,path)
            for plane in ('XY','YZ'):
                for scale in (-2.,0.):
                    result=corrected(4,.3,10,path,scale,plane,(17.,-31.,49.))
                    self.assertAlmostEqual(result['final']['tip_translation_in'],scale*base['final']['tip_translation_in'],places=11)
                    self.assertLess(np.linalg.norm(result['final']['deformed_moment_residual_kip_in']),.012)
                    if scale:self.assertLess(result['final']['rotation_relative_error'],1e-5)
                    else:
                        self.assertIsNone(result['final']['continuum_relative_error'])
                        self.assertEqual(result['final']['continuum_absolute_error_in'],0.)
                        self.assertEqual(result['final']['rotation_absolute_error_rad'],0.)

    def test_consistent_full_state_jacobian_matches_central_differences(self):
        model,_,_=_build(3,.3,10,'ramp',1.,'XY',(0.,0.,0.));system=ElasticSystem(model)
        force=model.P('Primary').ravel()+10*model.P('Push').ravel();result=system.solve(force)
        state=result['state'];analytic=result['jacobian'];columns=[]
        for i in range(system.unknowns):
            step=1e-5*max(abs(state[i]),1e-3);delta=np.zeros_like(state);delta[i]=step
            columns.append((system.evaluate(state+delta,force)['residual']-system.evaluate(state-delta,force)['residual'])/(2*step))
        numeric=np.array(columns).T
        np.testing.assert_allclose(np.linalg.norm(numeric-analytic,axis=0)/np.linalg.norm(analytic,axis=0),0.,atol=2e-8)

    def test_nonproportional_elastic_loads_re_equilibrate_and_return_to_zero(self):
        model,_,_=_build(4,.3,20,'ramp',1.,'XY',(0.,0.,0.));system=ElasticSystem(model)
        target=20*model.P('Push').ravel();state=None
        # Vary axial and transverse loads independently, including sign changes.
        for axial,lateral in ((1.,0.),(1.,1.),(.5,-1.),(-.5,1.),(0.,0.)):
            force=np.zeros_like(target);force[-5]=axial*target[-5];force[-6]=lateral*target[-6]
            result=system.solve(force,state);state=result['state']
            self.assertLess(result['max_yield_interaction'],1e-10)
            self.assertLess(max(abs(result['residual'])),1e-8)
        np.testing.assert_allclose(state,0.,atol=1e-9)

    def test_scaled_geometry_forces_and_units_preserve_the_same_solution(self):
        def solve(length_scale,force_scale):
            m,_,_=_build(4,.3,20,'ramp',1.,'XY',(0.,0.,0.))
            for node in m.nodes.values():node.X*=length_scale;node.Y*=length_scale;node.Z*=length_scale
            for material in m.materials.values():material.E*=force_scale/length_scale**2;material.G*=force_scale/length_scale**2;material.fy*=force_scale/length_scale**2
            for section in m.sections.values():
                section.A*=length_scale**2;section.Iy*=length_scale**4;section.Iz*=length_scale**4;section.J*=length_scale**4;section.Zy*=length_scale**3;section.Zz*=length_scale**3
            system=ElasticSystem(m);force=m.P('Primary').ravel()+20*m.P('Push').ravel();force=force.reshape(-1,6)
            force[:,:3]*=force_scale;force[:,3:]*=force_scale*length_scale
            result=system.solve(force.ravel());motion=result['motion'].reshape(-1,6).copy();motion[:,:3]/=length_scale
            return motion,result['axial']/force_scale
        baseline=solve(1.,1.);scaled=solve(1000.,.001)
        np.testing.assert_allclose(scaled[0],baseline[0],atol=1e-9,rtol=1e-7)
        np.testing.assert_allclose(scaled[1],baseline[1],atol=1e-7,rtol=1e-9)

    def test_yield_instability_and_nonconvergence_return_no_trial_result(self):
        m,_,_=_build(4,.3,20,'ramp',1.,'XY',(0.,0.,0.));system=ElasticSystem(m);force=20*m.P('Push').ravel()
        with self.assertRaisesRegex(RejectedState,'iteration limit'):system.solve(force,max_iterations=1)
        m.materials['Steel'].fy=50.;m.sections['I'].Zz=.02
        with self.assertRaisesRegex(RejectedState,'Yielding'):system.solve(force)
        m2,_,_=_build(4,.3,20,'ramp',1.,'XY',(0.,0.,0.));s2=ElasticSystem(m2);unstable=20*m2.P('Push').ravel();unstable[-5]=-1.08*CRITICAL
        with self.assertRaisesRegex(RejectedState,'Nonpositive'):s2.solve(unstable)

    def test_unsupported_inputs_and_nonfinite_loads_are_rejected(self):
        m,_,_=_build(2,.1,10,'ramp',1.,'XY',(0.,0.,0.));m.add_member_dist_load('1','FY',1.,1.)
        with self.assertRaisesRegex(ValueError,'member loads'):ElasticSystem(m)
        m,_,_=_build(2,.1,10,'ramp',1.,'XY',(0.,0.,0.));m.def_node_disp('0','DX',.1)
        with self.assertRaisesRegex(ValueError,'imposed'):ElasticSystem(m)
        for unsupported in ('release','unilateral','spring','mesh'):
            m,_,_=_build(2,.1,10,'ramp',1.,'XY',(0.,0.,0.))
            if unsupported=='release':m.def_releases('1',Rzi=True)
            elif unsupported=='unilateral':m.members['1'].tension_only=True
            elif unsupported=='spring':m.def_support_spring('2','DX',1.)
            else:m.add_rectangle_mesh('Mesh',60.,120.,120.,1.,'Steel')
            with self.assertRaisesRegex(ValueError,'scope excludes'):ElasticSystem(m)
        m,_,_=_build(2,.1,10,'ramp',1.,'XY',(0.,0.,0.));s=ElasticSystem(m)
        with self.assertRaisesRegex(ValueError,'Finite'):s.solve(np.full(s.size,np.nan))
        with self.assertRaises(ValueError):s.path(np.zeros(s.size),np.zeros(s.size),0)
