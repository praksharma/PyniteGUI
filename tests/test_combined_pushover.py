"""Combined P-Delta/plastic eligibility: elastic prerequisites and negative evidence."""
import functools
import inspect
import unittest
from unittest.mock import patch
import numpy as np
from Pynite import FEModel3D
from Pynite.Member3D import Member3D
from combined_pushover_reference import column_field,energy_column,compliance_path_integral
from combined_pushover_probe import probe,supports_combined,LENGTH,RIGIDITY,CRITICAL


class CombinedPushoverTests(unittest.TestCase):
    def test_independent_closed_form_zero_tension_compression_and_branch_guards(self):
        from pdelta_movement_reference import column_field as transfer_reference
        stations=np.linspace(0.,LENGTH,17)
        for ratio in (-.3,-1e-8,0.,1e-8,.1,.3):
            for force in (-2.,0.,1.):
                field=column_field(stations,LENGTH,RIGIDITY,ratio*CRITICAL,force)
                state=transfer_reference(LENGTH,RIGIDITY,ratio*CRITICAL,force=force)['sample'](stations)
                np.testing.assert_allclose(field[:,0],state[:,0],atol=2e-12,rtol=1e-9)
                np.testing.assert_allclose(field[:,1],-state[:,1],atol=2e-13,rtol=1e-9)
        for arguments in (([0.],0.,1.,0.,1.),([0.],1.,-1.,0.,1.),([-1.],1.,1.,0.,1.),
                          ([0.],LENGTH,RIGIDITY,CRITICAL,1.),([np.nan],1.,1.,0.,1.)):
            with self.assertRaises(ValueError):column_field(*arguments)

    def test_independent_energy_refines_for_both_axial_signs(self):
        for ratio in (-.3,.1,.3):
            errors=[]
            for segments in (2,4,8):
                actual,backward=energy_column(segments,LENGTH,RIGIDITY,ratio*CRITICAL,1.)
                expected=column_field(np.linspace(0.,LENGTH,segments+1),LENGTH,RIGIDITY,ratio*CRITICAL,1.)
                errors.append(np.linalg.norm(actual[:,0]-expected[:,0])/np.linalg.norm(expected[:,0]))
                self.assertLess(backward,1e-11)
            self.assertLess(errors[-1],3e-7);self.assertTrue(all(b<a/10 for a,b in zip(errors,errors[1:])))
        with self.assertRaises(ValueError):energy_column(0,LENGTH,RIGIDITY,0.,1.)

    def test_public_engine_capability_is_explicit_and_zero_axial_control_is_exact(self):
        self.assertEqual(supports_combined(),'P_Delta' in inspect.signature(FEModel3D.analyze_pushover).parameters)
        baseline=probe(4,0.,20,variant='first_order')
        self.assertLess(baseline['final']['continuum_relative_error'],1e-10)
        raw=probe(4,0.,20)
        if not supports_combined():
            self.assertFalse(raw['supported']);self.assertIn('no public',raw['reason']);return
        self.assertLess(raw['final']['continuum_relative_error'],1e-10)
        self.assertLess(raw['final']['max_yield_interaction'],1e-10)

    def test_raw_preload_fails_before_yield_and_half_axial_is_only_a_diagnostic(self):
        for ratio in (.1,.3):
            raw=probe(8,ratio,100);corrected=probe(8,ratio,100,variant='half_axial_diagnostic')
            if not supports_combined():
                self.assertFalse(raw['supported']);self.assertFalse(corrected['supported']);continue
            final=raw['final'];half=corrected['final']
            self.assertGreater(final['continuum_relative_error'],.1)
            self.assertLess(half['continuum_relative_error'],3e-7)
            self.assertLess(half['discrete_relative_error'],1e-7)
            self.assertGreater(np.linalg.norm(final['deformed_moment_residual_kip_in']),1.)
            self.assertLess(np.linalg.norm(half['deformed_moment_residual_kip_in']),.001)
            self.assertAlmostEqual(abs(raw['geometric_arguments'][-1]),2*final['compression_kip'],places=6)
            self.assertLess(raw['max_yield_interaction'],1e-10)
            self.assertFalse(corrected['production_ready'])

    def test_simultaneous_axial_ramp_does_not_qualify_after_step_refinement(self):
        for variant in ('raw','half_axial_diagnostic'):
            errors=[]
            for steps in (20,100,400):
                result=probe(8,.3,steps,'ramp',variant)
                if not result['supported']:
                    self.assertFalse(supports_combined());continue
                final=result['final'];errors.append(final['continuum_relative_error'])
                self.assertGreater(errors[-1],.03)
                self.assertGreater(np.linalg.norm(final['deformed_moment_residual_kip_in']),1.)
                self.assertLess(final['free_joint_residual'],1e-8)
                self.assertLess(result['max_yield_interaction'],1e-10)
            if errors:self.assertGreater(errors[-1],.05)

    def test_half_axial_ramp_tends_to_an_incomplete_compliance_integral(self):
        reference=compliance_path_integral(LENGTH,RIGIDITY,.3*CRITICAL,1.)
        refined=compliance_path_integral(LENGTH,RIGIDITY,.3*CRITICAL,1.,128)
        self.assertAlmostEqual(reference,refined,places=12)
        correct=column_field([LENGTH],LENGTH,RIGIDITY,.3*CRITICAL,1.)[0,0]
        self.assertGreater(abs(reference/correct-1),.16)
        errors=[]
        for steps in (20,100,400):
            result=probe(8,.3,steps,'ramp','half_axial_diagnostic')
            if not result['supported']:
                self.assertFalse(supports_combined());continue
            errors.append(abs(result['final']['tip_translation_in']/reference-1))
        if errors:
            self.assertLess(errors[-1],.0005)
            self.assertTrue(all(b<a for a,b in zip(errors,errors[1:])))

    def test_sign_plane_origin_controls_and_patch_restoration(self):
        before=Member3D.kg
        for variant in ('raw','half_axial_diagnostic'):
            base=probe(4,.1,20,variant=variant)
            for plane in ('XY','YZ'):
                other=probe(4,.1,20,variant=variant,force=-2.,plane=plane,origin=(17.,-31.,49.))
                if not base['supported']:
                    self.assertFalse(other['supported']);continue
                self.assertAlmostEqual(other['final']['tip_translation_in'],-2*base['final']['tip_translation_in'],places=10)
            zero=probe(4,.1,20,variant=variant,force=0.)
            if zero['supported']:self.assertEqual(zero['final']['tip_translation_in'],0.)
        self.assertIs(Member3D.kg,before)
        if supports_combined():
            with patch('combined_pushover_probe.column_field',side_effect=ValueError('reference failure')):
                with self.assertRaisesRegex(RuntimeError,'research'):
                    probe(2,.1,3,variant='half_axial_diagnostic',force=2.5)
            self.assertIs(Member3D.kg,before)

    def test_production_pushover_explicitly_remains_first_order_on_both_apis(self):
        from pynitegui.qt.pushover import PushoverSolver
        from test_pushover import propped_beam,settings,solve
        original=FEModel3D.analyze_pushover;calls=[]
        @functools.wraps(original)
        def record(model,*args,**kwargs):
            calls.append(kwargs.copy());result=original(model,*args,**kwargs)
            self.assertFalse(model._pushover_P_Delta)
            return result
        p=propped_beam();p.analysis_method='p_delta'
        with patch.object(PushoverSolver,'analyze_pushover',record):
            result=solve(p,settings(steps=100))
        self.assertTrue(result.complete,result.message);self.assertEqual(len(calls),1)
        if supports_combined():self.assertIs(calls[0]['P_Delta'],False)
        else:self.assertNotIn('P_Delta',calls[0])
        self.assertIn('First-order',result.metadata()['convention'])
