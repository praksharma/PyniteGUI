"""Independent elastic/plastic beam, accepted-step and mechanism checks."""
import contextlib
import io
import pickle
import unittest
import numpy as np
from pynitegui.qt.model import Project,Material,Section,Load
from pynitegui.qt.pushover import PushoverSettings,analyze_pushover
from pynitegui.qt.spatial_conversion import to_spatial


def propped_beam(push=24.):
    p=Project(materials={'Steel':Material('Steel',29000,.3,0.,shear_modulus=11200.,fy=50.)},default_material='Steel',
        sections={'I':Section('I',10,30,100,1,Zy=10.,Zz=20.,steel_material='Steel')},default_section='I',
        load_cases=['D','Push'],default_load_case='D',combinations={'Primary':{'D':0.},'Push':{'Push':1.}})
    p.add_member((0.,0.),(120.,0.));p.add_member((120.,0.),(240.,0.))
    p.nodes['N1'].support='fixed';p.nodes['N3'].support='pin'
    p.loads={'P':Load('P','N2','FY',-push,case='Push')}
    return p


def settings(**kwargs):
    return PushoverSettings('Primary','Push','N2','DY',kwargs.pop('stop_limit',2.),('N1','N3'),resultant='FY',**kwargs)


def solve(project,options=None):
    with contextlib.redirect_stdout(io.StringIO()):return analyze_pushover(project,options or settings())


def reference(force,EI=29000*100,Mp=1000.,L=240.):
    first=16*Mp/(3*L);collapse=6*Mp/L
    c1,c2=7*L**3/(768*EI),L**3/(48*EI)
    moment=min(3*force*L/16,Mp)
    dy=-(force*c1 if force<=first else first*c1+(force-first)*c2)
    return dy,moment,force/2+moment/L,force/2-moment/L,first,collapse


class SteelPushoverTests(unittest.TestCase):
    def test_elastic_then_plastic_redistribution_converges_to_hand_reference(self):
        errors=[]
        for steps in (100,500):
            p=propped_beam();before=p.to_dict();r=pickle.loads(pickle.dumps(solve(p,settings(steps=steps))))
            self.assertEqual(p.to_dict(),before);self.assertTrue(r.complete);self.assertEqual(r.termination,'full_pattern')
            self.assertEqual(r.displacements.shape,(steps+1,3,6));self.assertEqual(r.end_forces.shape,(steps+1,2,12))
            expected=reference(24.);errors.append(abs(r.curve[-1,0]-expected[0]))
            self.assertAlmostEqual(r.curve[-1,1],24.,places=9);self.assertLess(np.max(abs(r.equilibrium)),1e-7)
            first=next(i for i,phi in enumerate(r.phis[:,0,0]) if phi>=1.)
            self.assertGreaterEqual(r.factors[first]*24,expected[4]);self.assertLessEqual(r.factors[first]*24,expected[4]+24/steps)
            np.testing.assert_allclose(r.curve[:first,0],[reference(24*x)[0] for x in r.factors[:first]],atol=1e-10)
        self.assertLess(errors[1],errors[0]/10);self.assertLess(errors[1],.0002)
        self.assertAlmostEqual(r.end_forces[-1,0,5],expected[1],delta=.1)
        self.assertAlmostEqual(r.reactions[-1,0,1],expected[2],delta=.001)
        self.assertAlmostEqual(r.reactions[-1,2,1],expected[3],delta=.001)

    def test_mechanism_and_overshoot_preserve_only_checked_accepted_steps(self):
        r=solve(propped_beam(26.),settings(steps=1000))
        self.assertFalse(r.complete);self.assertEqual(r.termination,'limit_state')
        self.assertGreater(r.curve[-1,1],25.);self.assertLess(r.curve[-1,1],25.+3*26/1000)
        self.assertLess(r.factors[-1],1.);self.assertTrue(np.isfinite(r.displacements).all())
        self.assertLess(np.max(r.phis),1.01);self.assertLess(np.max(abs(r.equilibrium)),1e-7)
        r=solve(propped_beam(),settings(steps=20))
        self.assertFalse(r.complete);self.assertEqual(r.termination,'yield_overshoot')
        self.assertLess(r.curve[-1,1],reference(24)[4]);self.assertLess(np.max(r.phis),1.)
        self.assertIn('increase load steps',r.message)

    def test_absolute_target_and_initial_preload_stop_are_explicit(self):
        p=propped_beam();r=solve(p,settings(stop_limit=1.))
        self.assertTrue(r.complete);self.assertEqual(r.termination,'target_reached');self.assertLess(r.factors[-1],1.)
        self.assertGreaterEqual(abs(r.curve[-1,0]),1.);self.assertLess(abs(r.curve[-1,0]),1.006)
        p.combinations['Primary']={'D':1.};p.loads['D']=Load('D','N2','FY',-1.,case='D')
        r=solve(p,settings(stop_limit=.001))
        self.assertTrue(r.complete);self.assertEqual(len(r.factors),1);self.assertEqual(r.metadata()['accepted_steps'],0)
        self.assertAlmostEqual(r.curve[0,0],reference(1.)[0],places=10);self.assertAlmostEqual(r.curve[0,1],1.,places=10)

    def test_compound_push_factors_and_mixed_elastic_members_preserve_pattern(self):
        p=propped_beam();base=solve(p,settings(steps=100))
        p.set_load_case('Push2');p.loads['P'].magnitude=-10.
        p.loads['P2']=Load('P2','N2','FY',30.,case='Push2');p.combinations['Push']={'Push':1.5,'Push2':-.3}
        p.sections['Elastic']=Section('Elastic',10,30,100,1);p.members['M2'].section='Elastic'
        r=solve(p,settings(steps=100))
        np.testing.assert_allclose(r.displacements,base.displacements,atol=1e-10)
        np.testing.assert_allclose(r.reactions,base.reactions,atol=1e-10)
        self.assertEqual(r.end_states[-1][1],('Elastic model','Elastic model'))

    def test_spatial_weak_axis_plasticity_and_joint_balance(self):
        p=to_spatial(propped_beam(12.))
        for member in p.members.values():member.roll=90.
        r=solve(p);expected=reference(12.,EI=29000*30,Mp=500.)
        self.assertTrue(r.complete,r.message)
        self.assertAlmostEqual(r.curve[-1,0],expected[0],delta=.0005)
        self.assertAlmostEqual(abs(r.end_forces[-1,0,4]),500.,delta=.1)
        self.assertLess(np.max(abs(r.equilibrium)),1e-7)

    def test_spatial_biaxial_axial_interaction_reaches_independent_yield_root(self):
        from scipy.optimize import brentq
        from pynitegui.qt.spatial_model import SpatialProject,SpatialLoad
        source=propped_beam()
        p=SpatialProject(materials=source.materials,default_material='Steel',sections=source.sections,default_section='I',
            load_cases=['D','Push'],default_load_case='D',combinations=source.combinations)
        p.add_member((0.,0.,0.),(120.,0.,0.));p.nodes['N1'].support='fixed'
        p.loads={key:SpatialLoad(key,'N2',key,value,case='Push') for key,value in (('FX',240.),('FY',-20/3),('FZ',8/3))}
        option=PushoverSettings('Primary','Push','N2','DY',10.,('N1',),'FY',steps=1000)
        def phi(factor):
            axial,my,mz=.48*factor,.64*factor,.8*factor
            return axial**2+mz**2+my**4+3.5*axial**2*mz**2+3*axial**6*my**2+4.5*mz**4*my**2
        root=brentq(lambda factor:phi(factor)-1.,0.,1.)
        r=solve(p,option)
        self.assertFalse(r.complete);self.assertEqual(r.termination,'limit_state')
        self.assertGreaterEqual(r.factors[-1],root);self.assertLess(r.factors[-1],root+.00101)
        self.assertAlmostEqual(r.phis[-1,0,0],phi(r.factors[-1]),places=10)
        np.testing.assert_allclose(r.reactions[-1,0,:3],r.factors[-1]*np.array([-240.,20/3,-8/3]),atol=1e-9)
        self.assertLess(np.max(abs(r.equilibrium)),1e-7)

    def test_preload_yield_and_interior_hinge_scope_fail_closed(self):
        p=propped_beam();p.combinations['Primary']={'D':1.};p.loads['D']=Load('D','N2','FY',-23.,case='D')
        with self.assertRaisesRegex(ValueError,'strictly elastic'):solve(p)
        p=propped_beam();p.loads.clear();p.loads['q']=Load('q','M2','FY',-1.,0.,kind='distributed',end_magnitude=-1.,case='Push')
        with self.assertRaisesRegex(ValueError,'push pattern requires nodal'):solve(p)

    def test_member_end_push_transfer_and_distributed_preload_balance(self):
        p=propped_beam();reference_result=solve(p,settings(steps=100))
        p.loads['P'].target='M1';p.loads['P'].position=1.
        r=solve(p,settings(steps=100))
        np.testing.assert_allclose(r.displacements,reference_result.displacements,atol=1e-10)
        p.combinations['Primary']={'D':1.}
        p.loads['gravity']=Load('gravity','M2','FY',-.002,0.,kind='distributed',end_magnitude=-.002,case='D')
        r=solve(p,settings(steps=500))
        self.assertTrue(r.complete,r.message)
        self.assertLess(np.max(abs(r.equilibrium)),1e-7)

    def test_interior_axial_bending_interaction_requires_a_real_hinge_node(self):
        p=propped_beam();p.members.clear();p.nodes.clear();p.loads.clear()
        p.add_member((0.,0.),(240.,0.));p.nodes['N1'].support='pin';p.nodes['N2'].support='roller'
        p.combinations['Primary']={'D':1.}
        q=8*500/240**2
        p.loads['q']=Load('q','M1','FY',-q,0.,kind='distributed',end_magnitude=-q,case='D')
        p.loads['F']=Load('F','N2','FX',500.,case='Push')
        option=PushoverSettings('Primary','Push','N2','DX',5.,('N1','N2'),resultant='FX',steps=500)
        r=solve(p,option)
        self.assertFalse(r.complete);self.assertEqual(r.termination,'interior_yield')
        critical=500*np.sqrt(.4)  # Phi = .25 + 1.875*(N/Py)^2.
        self.assertLessEqual(abs(r.curve[-1,1]),critical)
        self.assertGreater(abs(r.curve[-1,1]),critical-1.)
        self.assertLess(np.max(r.phis),.401)
        p.subdivide_members(['M1'],2)
        r=solve(p,option)
        self.assertFalse(r.complete);self.assertEqual(r.termination,'limit_state')
        self.assertAlmostEqual(abs(r.curve[-1,1]),critical,delta=1.1)
