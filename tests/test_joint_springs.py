"""Independent joint-spring networks, one-way contact and geometry ownership."""
from copy import deepcopy
from dataclasses import replace
import contextlib
import io
import unittest
import numpy as np
from scipy.spatial.transform import Rotation
from pynitegui.qt.model import Project,Node,Load
from pynitegui.qt.joint_springs import JointSpring,result_values
from pynitegui.qt.examples import example_project
from pynitegui.qt.analysis import analyze
from pynitegui.qt.spatial_conversion import to_spatial
from pynitegui.qt.equilibrium import check_equilibrium
from pynitegui.qt.geometry_tools import plan_transform,plan_merge,preview_geometry
from pynitegui.qt.automation_core import batch_candidate,AutomationError
from pynitegui.qt.reports import result_table,model_definition_tables


def solve(p):
    with contextlib.redirect_stdout(io.StringIO()):return analyze(p)


class JointSpringTests(unittest.TestCase):
    def test_series_network_analytical_response_both_dimensions_endpoint_reversal(self):
        for spatial in (False,True):
            p=example_project('joint_spring_series')
            if spatial:p=to_spatial(p)
            for reverse in (False,True):
                if reverse:
                    for s in p.joint_springs.values():s.start,s.end=s.end,s.start
                before=p.to_dict();r=solve(p)
                self.assertEqual(p.to_dict(),before);self.assertAlmostEqual(r.displacements['B'][0],.1)
                self.assertAlmostEqual(r.displacements['C'][0],.15);self.assertAlmostEqual(r.reactions['A'][0],-10.)
                for name in p.joint_springs:self.assertAlmostEqual(result_values(p,r,name)[1],10.)
                self.assertTrue(check_equilibrium(p,r).passed)
                self.assertIsNone(r.displacements['B'][-1])

    def test_parallel_one_way_reversal_and_zero_state_without_residual_stiffness(self):
        for spatial in (False,True):
            p=example_project('joint_spring_one_way')
            if spatial:p=to_spatial(p)
            r=solve(p)
            for combo,displacement,forces in (('Service',.05,(10.,0.)),('Reverse',-1/30,(0.,-10.)),('Zero',0.,(0.,0.))):
                selected=r.for_combination(combo);self.assertAlmostEqual(selected.displacements['B'][0],displacement)
                np.testing.assert_allclose([result_values(p,selected,key)[1] for key in ('T','C')],forces,atol=1e-10)
                self.assertTrue(check_equilibrium(p,selected).passed)
                headers,rows=result_table(p,selected,'active_states');self.assertEqual(len(rows),2)
                self.assertTrue(all(row[0]=='Joint spring' for row in rows))
            del p.joint_springs['C']
            p.combinations={'Zero':{'Case 1':0.}}
            with self.assertRaisesRegex(ValueError,'Unilateral mechanism'):solve(p)
            p.combinations={'Reverse':{'Case 1':-1.}}
            with self.assertRaises(ValueError):solve(p)

    def test_reactivation_matches_independent_exhaustive_active_sets(self):
        from test_iterative import star_project
        from unilateral_reference import star
        p,anchors=star_project()
        stiffnesses=[]
        for name,m in p.members.items():
            a,b=p.nodes[m.start],p.nodes[m.end]
            k=p.materials[m.material].E*p.sections[m.section].A/np.hypot(b.x-a.x,b.y-a.y)
            stiffnesses.append(k);p.joint_springs[name]=JointSpring(name,m.start,m.end,k,'tension_only')
        p.members={}
        for index,force in enumerate(((9.58063975308847,.6963722766094482),(4.,-7.),(-3.,8.),(-6.,-4.))):
            p.loads={'X':Load('X','N2','FX',force[0]),'Y':Load('Y','N2','FY',force[1])}
            expected,active,trial=star(np.array(force),anchors,stiffnesses,['tension_only']*3)
            for steps in (1,4):
                p.load_steps=steps;r=solve(p)
                np.testing.assert_allclose(r.displacements['N2'][:2],expected,atol=1e-11)
                rows=r.solver._brecon_iterations['Service']['contacts']
                self.assertEqual([row['active'] for row in rows],list(active))
                np.testing.assert_allclose([row['trial'] for row in rows],trial,atol=1e-8)
                if index==0 and steps==1:
                    changes=[key for row in r.solver._brecon_iterations['Service']['history'] for key in row['changed']]
                    self.assertGreater(len(changes),len(set(changes)))

    def test_true_spatial_oblique_network_matches_independent_congruence(self):
        p=example_project('3d_joint_spring_network');r=solve(p)
        R=Rotation.from_rotvec([.4,-.3,.2]).as_matrix();F=np.array([10.,20.,-30.])
        expected=R @ np.diag([.01,.005,1/300]) @ R.T @ F
        np.testing.assert_allclose(r.displacements['B'][:3],expected,atol=1e-12)
        np.testing.assert_allclose(np.sum([v[:3] for v in r.reactions.values()],axis=0),-F,atol=1e-10)
        self.assertTrue(check_equilibrium(p,r).passed)
        p.loads['MX']=type(p.loads['FX'])('MX','B','MX',1.)
        with self.assertRaisesRegex(ValueError,'no rotational stiffness'):solve(p)

    def test_spatial_one_way_principal_directions_and_signed_combinations(self):
        p=example_project('3d_joint_spring_network');p.analysis_method='iterative'
        for name,spring in list(p.joint_springs.items()):
            spring.behavior='tension_only'
            p.joint_springs[name+'C']=replace(spring,name=name+'C',behavior='compression_only',stiffness=2*spring.stiffness)
        p.combinations.update(Reverse={'Case 1':-1.},Zero={'Case 1':0.})
        R=Rotation.from_rotvec([.4,-.3,.2]).as_matrix();F=np.array([10.,20.,-30.])
        for steps in (1,3):
            p.load_steps=steps;r=solve(p)
            for combo,factor in (('Service',1.),('Reverse',-1.),('Zero',0.)):
                local=R.T@(factor*F);stiffness=np.array([100.,200.,300.])*np.where(local<0,2.,1.)
                expected=R@(local/stiffness);selected=r.for_combination(combo)
                np.testing.assert_allclose(selected.displacements['B'][:3],expected,atol=1e-12)
                for i,name in enumerate(('S1','S2','S3')):
                    self.assertAlmostEqual(result_values(p,selected,name)[1],max(local[i],0.))
                    self.assertAlmostEqual(result_values(p,selected,name+'C')[1],min(local[i],0.))
                self.assertTrue(check_equilibrium(p,selected).passed)

    def test_frame_and_link_stiffness_are_independent_and_massless(self):
        p=example_project('cantilever');p.loads.clear();p.self_weight_case='Case 1'
        p.loads['P']=Load('P','N2','FX',10.)
        p.joint_springs={'S':JointSpring('S','N1','N2',1000.)}
        before=p.self_weight_total();r=solve(p);m=p.members['M1'];L=abs(p.nodes[m.end].x-p.nodes[m.start].x)
        k=p.materials[m.material].E*p.sections[m.section].A/L
        self.assertAlmostEqual(r.displacements['N2'][0],10/(k+1000.))
        self.assertAlmostEqual(result_values(p,r,'S')[1],1000*10/(k+1000.))
        self.assertEqual(p.self_weight_total(),before)

    def test_constant_support_movement_and_load_combinations(self):
        for spatial in (False,True):
            p=example_project('joint_spring_series');p.nodes['A'].settlement_x=.2;p.combinations['Zero']={'Case 1':0.}
            if spatial:p=to_spatial(p)
            r=solve(p)
            self.assertAlmostEqual(r.displacements['C'][0],.35)
            zero=r.for_combination('Zero');self.assertAlmostEqual(zero.displacements['C'][0],.2)
            self.assertLess(max(abs(result_values(p,zero,s)[1]) for s in p.joint_springs),1e-10)
            self.assertTrue(check_equilibrium(p,r).passed)

    def test_schema_defaults_strict_versions_and_atomic_dependency_changes(self):
        for p,version,legacy in ((example_project('joint_spring_series'),35,33),(to_spatial(example_project('joint_spring_series')),42,40)):
            data=p.to_dict();self.assertEqual(data['version'],version);self.assertEqual(Project.from_dict(data).to_dict(),data)
            missing=deepcopy(data);missing.pop('joint_springs')
            with self.assertRaisesRegex(ValueError,'Missing.*joint_springs'):Project.from_dict(missing)
            with self.assertRaisesRegex(ValueError,'require project version'):Project.from_dict({**data,'version':legacy})
            old={**missing,'version':legacy};self.assertEqual(Project.from_dict(old).joint_springs,{})
            for value in (True,0.,-1.,float('inf'),float('nan'),'100'):
                bad=p.clone();bad.joint_springs['S1'].stiffness=value
                with self.assertRaises(ValueError):bad.validate()
            for changes in ({'start':'missing'},{'end':'A'},{'name':'A'},{'behavior':'gap'}):
                bad=p.clone();bad.joint_springs['S1']=replace(bad.joint_springs['S1'],**changes)
                with self.assertRaises(ValueError):bad.validate()
            with self.assertRaises(AutomationError):batch_candidate(p,[{'op':'delete','collection':'nodes','key':'A'}])
            q=batch_candidate(p,[{'op':'delete','collection':'joint_springs','key':'S1'},{'op':'delete','collection':'nodes','key':'A'}])
            self.assertNotIn('S1',q.joint_springs);self.assertIn('A',p.nodes)
            q=p.clone();q.delete('nodes','A');self.assertNotIn('S1',q.joint_springs)

    def test_move_repeat_merge_conversion_and_identifier_ownership(self):
        p=example_project('joint_spring_series')
        plan=plan_transform(p,[('nodes','C')],'move',offset=(12.,0.,0.))
        self.assertEqual(len(preview_geometry(p,plan)['lines']),12)
        self.assertEqual(preview_geometry(p,replace(plan,definition=p))['lines'],[])
        moved=plan.definition
        self.assertEqual(moved.joint_springs['S2'].stiffness,200.);self.assertAlmostEqual(solve(moved).displacements['C'][0],.15)
        repeated=plan_transform(p,[('nodes',name) for name in p.nodes],'repeat',offset=(0.,120.,0.),copy_supports=True).definition
        self.assertEqual(len(repeated.joint_springs),4)
        self.assertEqual(sorted(s.stiffness for s in repeated.joint_springs.values()),[100.,100.,200.,200.])
        with self.assertRaisesRegex(ValueError,'endpoints'):plan_merge(p,'A','B',120.,support_policy='target')
        p.joint_springs['N1']=JointSpring('N1','A','B',1.)
        self.assertNotEqual(p.node_at(300.,300.),'N1');p.validate()
        q=to_spatial(p,offset=17.);self.assertEqual(q.joint_springs,p.joint_springs)

    def test_result_units_definition_reports_and_unsupported_methods(self):
        p=example_project('joint_spring_series');r=solve(p)
        headers,rows=result_table(p,r,'joint_springs');self.assertAlmostEqual(rows[0][-1],10.)
        p.unit_system='si_mm';converted=result_table(p,r,'joint_springs')
        self.assertIn('Extension (mm)',converted[0]);self.assertAlmostEqual(converted[1][0][-2],2.54)
        self.assertIn('Joint Springs',[title for title,*_ in model_definition_tables(p)])
        self.assertIn('Joint Springs',[title for title,*_ in model_definition_tables(to_spatial(p))])
        p.analysis_method='p_delta'
        with self.assertRaisesRegex(ValueError,'Joint springs'):solve(p)
        from pynitegui.qt.modal import modal_issue
        from pynitegui.qt.pushover import pushover_issue
        self.assertIn('Joint springs',modal_issue(p));self.assertIn('Joint springs',pushover_issue(p))
