"""Independent unilateral mechanics, complementarity, neutral cones and contracts."""
import math
import pickle
import unittest

import numpy as np

from pynitegui.qt.model import Project,Load
from pynitegui.qt.analysis import analyze,model_signature
from pynitegui.qt.analysis_method import analysis_method_issue
from pynitegui.qt.spatial_conversion import to_spatial
from pynitegui.qt.support_axes import support_normal
from pynitegui.qt.unilateral import ITERATIVE_DEFAULTS, spring_mode_fields
from pynitegui.qt.equilibrium import check_equilibrium
from pynitegui.qt.reports import result_table
from unilateral_reference import star


def star_project():
    p=Project(analysis_method='iterative')
    anchors=((-120.,0.),(60.,-100.),(70.,110.))
    for point in anchors:
        p.add_member(point,(0.,0.))
        p.nodes[p.node_at(*point)].support='fixed'
    for member in p.members.values():
        member.kind,member.behavior='truss','tension_only'
    p.nodes['N2'].spring_x=p.nodes['N2'].spring_y=100.
    return p,anchors


def opposing(behavior='tension_only'):
    p=Project(analysis_method='iterative')
    p.add_member((-120.,0.),(0.,0.));p.add_member((120.,0.),(0.,0.))
    p.nodes['N1'].support=p.nodes['N3'].support='fixed'
    p.nodes['N2'].support='custom';p.nodes['N2'].restraint_y=True
    for member in p.members.values():member.kind,member.behavior='truss',behavior
    p.loads={'F':Load('F','N2','FX',3.)}
    p.combinations={'Positive':{'Case 1':1.},'Negative':{'Case 1':-1.},'Zero':{'Case 1':0.}}
    return p


class IterativeEngineeringTests(unittest.TestCase):
    def test_opposing_ties_or_struts_swap_with_load_sign_and_certify_zero_contact(self):
        for behavior in ('tension_only','compression_only'):
            p=opposing(behavior)
            for project in (p,to_spatial(p)):
                before=project.to_dict();r=pickle.loads(pickle.dumps(analyze(project)))
                self.assertEqual(project.to_dict(),before)
                k=p.E*p.A/120.
                for combo,factor in (('Positive',1.),('Negative',-1.),('Zero',0.)):
                    selected=r.for_combination(combo)
                    self.assertAlmostEqual(selected.displacements['N2'][0],3*factor/k,places=11)
                    active=r.solver._brecon_iterations[combo]['contacts']
                    if factor:
                        self.assertEqual(sum(row['active'] for row in active),1)
                        self.assertEqual(sum(row['neutral'] for row in active),0)
                    else:
                        self.assertTrue(all(row['neutral'] for row in active))
                    self.assertTrue(check_equilibrium(project,selected).passed)
                    for name in project.members:
                        value=r.solver.members[name].axial(60.,combo)
                        self.assertGreaterEqual(-value if behavior=='tension_only' else value,-1e-8)
                self.assertEqual(r.analysis_method,'iterative')
                self.assertFalse(r.solver._brecon_iterating)

    def test_reactivation_against_independent_exhaustive_active_sets_and_load_steps(self):
        p,anchors=star_project()
        p.loads={'X':Load('X','N2','FX',9.58063975308847),'Y':Load('Y','N2','FY',.6963722766094482)}
        forces=[(9.58063975308847,.6963722766094482),(4.,-7.),(-3.,8.),(-6.,-4.)]
        for index,force in enumerate(forces):
            p.loads['X'].magnitude,p.loads['Y'].magnitude=force
            stiffnesses=[p.E*p.A/math.dist(point,(0.,0.)) for point in anchors]
            expected,active,trial=star(force,anchors,stiffnesses,['tension_only']*3)
            for steps in (1,4):
                p.load_steps=steps;r=analyze(p)
                np.testing.assert_allclose(r.displacements['N2'][:2],expected,atol=1e-11)
                rows=r.solver._brecon_iterations['Service']['contacts']
                self.assertEqual([row['active'] for row in rows],list(active))
                np.testing.assert_allclose([row['trial'] for row in rows],trial,atol=1e-8)
                if index==0 and steps==1:
                    changes=[key for row in r.solver._brecon_iterations['Service']['history'] for key in row['changed']]
                    self.assertGreater(len(changes),len(set(changes)))

    def test_normal_constraint_and_unfactored_imposed_motion_under_reversed_and_zero_loads(self):
        p,anchors=star_project()
        for node in p.nodes.values():
            if node.support=='fixed':node.settlement_x,node.settlement_y=.01,.02
        p.nodes['N2'].support='inclined';p.nodes['N2'].support_angle=37.;p.nodes['N2'].settlement_normal=.003
        p.loads={'X':Load('X','N2','FX',5.),'Y':Load('Y','N2','FY',-3.)}
        p.combinations={'Service':{'Case 1':1.},'Reverse':{'Case 1':-2.},'Zero':{'Case 1':0.}}
        r=analyze(p)
        for combo,factor in (('Service',1.),('Reverse',-2.),('Zero',0.)):
            expected,_,_=star(np.array((5.,-3.))*factor,anchors,
                [p.E*p.A/math.dist(a,(0.,0.)) for a in anchors],['tension_only']*3,
                anchor_motion=(.01,.02),normal=support_normal(p.nodes['N2']),target=.003)
            np.testing.assert_allclose(r.for_combination(combo).displacements['N2'][:2],expected,atol=1e-11)
            self.assertTrue(check_equilibrium(p,r.for_combination(combo)).passed)

    def test_global_one_way_translation_and_rotation_springs_keep_per_combination_stiffness(self):
        for dof,mode in (('x','negative'),('rz','positive')):
            p=Project(analysis_method='iterative');p.add_member((0.,0.),(120.,0.))
            p.nodes['N1'].support='fixed'
            setattr(p.nodes['N2'],'spring_'+dof,50. if dof=='x' else 1000.)
            setattr(p.nodes['N2'],'spring_'+dof+'_mode',mode)
            p.loads={'F':Load('F','N2','FX' if dof=='x' else 'MZ',3.)}
            p.combinations={'P':{'Case 1':1.},'N':{'Case 1':-1.},'Z':{'Case 1':0.}}
            for q in (p,to_spatial(p)):
                r=analyze(q)
                for combo,factor in (('P',1.),('N',-1.)):
                    selected=r.for_combination(combo);i=0 if dof=='x' else 5 if r.spatial else 2
                    enabled=(factor<0 if mode=='negative' else factor>0)
                    k=q.E*q.A/120. if dof=='x' else q.E*q.Iz/120.
                    expected=3*factor/(k+(50. if dof=='x' else 1000.)*enabled)
                    self.assertAlmostEqual(selected.displacements['N2'][i],expected,places=11)
                    self.assertAlmostEqual(selected.reactions['N2'][i],-(50. if dof=='x' else 1000.)*expected*enabled,places=8)
                    # Ke must retain each combination's spring state, even after
                    # solving a different combination or querying in reverse order.
                    node=r.solver.nodes['N2'];offset=0 if dof=='x' else 5
                    value=r.solver.Ke(combo,check_stability=False).tocsr()[node.ID*6+offset,node.ID*6+offset]
                    baseline=q.E*q.A/120. if dof=='x' else 4*q.E*q.Iz/120.
                    self.assertAlmostEqual(value,baseline+(50. if dof=='x' else 1000.)*enabled,places=8)

    def test_unloaded_single_one_way_support_cannot_hide_a_directional_mechanism(self):
        p=Project(analysis_method='iterative');p.add_member((0.,0.),(120.,0.))
        p.nodes['N1'].support='fixed';p.members['M1'].release_end_x=True
        p.nodes['N2'].spring_x=50.;p.nodes['N2'].spring_x_mode='positive'
        p.loads={'F':Load('F','N2','FX',3.)}
        r=analyze(p);self.assertAlmostEqual(r.displacements['N2'][0],.06,places=10)
        p.loads['F'].magnitude=0.
        with self.assertRaisesRegex(ValueError,'Unilateral mechanism'):analyze(p)
        p.loads['F'].magnitude=-3.
        with self.assertRaisesRegex(ValueError,'stiffness|Unstable'):analyze(p)

    def test_iteration_limit_no_unilateral_silent_fallback_and_no_post_unstable_snapshot(self):
        p=opposing();p.iteration_limit=1
        with self.assertRaisesRegex(ValueError,'did not converge'):analyze(p)
        for method in ('linear','p_delta'):
            p.analysis_method=method
            self.assertIn('Unilateral',analysis_method_issue(p))
            with self.assertRaisesRegex(ValueError,'Unilateral'):analyze(p)

    def test_bilateral_iterative_limit_matches_existing_linear_results(self):
        from pynitegui.qt.examples import example_project
        for key in ('cantilever','inclined_roller','support_settlement','shear_release','gerber','three_hinged_arch','3d_cantilever'):
            p=example_project(key);linear=analyze(p);p.analysis_method='iterative';r=analyze(p)
            for combo in p.combinations:
                a,b=linear.for_combination(combo),r.for_combination(combo)
                np.testing.assert_allclose(np.array(list(a.displacements.values()),dtype=float),np.array(list(b.displacements.values()),dtype=float),atol=1e-9)
                np.testing.assert_allclose(list(a.reactions.values()),list(b.reactions.values()),atol=1e-7)


class IterativeModelTests(unittest.TestCase):
    def test_strict_current_schema_legacy_defaults_and_setting_validation(self):
        for p,current,legacy in ((opposing(),31,29),(to_spatial(opposing()),38,36)):
            data=p.to_dict();self.assertEqual(data['version'],current)
            self.assertEqual(Project.from_dict(data).to_dict(),data)
            for key in ITERATIVE_DEFAULTS:
                bad=p.to_dict();bad.pop(key)
                with self.assertRaisesRegex(ValueError,'Missing unilateral'):Project.from_dict(bad)
            p.analysis_method='linear'
            for member in p.members.values():member.behavior='bilateral'
            data=p.to_dict();data['version']=legacy
            self.assertEqual(Project.from_dict(data).to_dict(),p.to_dict())
            data['members']['M1']['behavior']='tension_only'
            with self.assertRaisesRegex(ValueError,'require version'):Project.from_dict(data)
            for node in p.nodes.values():
                for key in spring_mode_fields(node):
                    setattr(node,key,'invalid')
                    with self.assertRaises(ValueError):p.validate()
                    setattr(node,key,'bilateral')
            for key,badvalues in (('iteration_limit',(True,0,501,2.5)),('load_steps',(False,0,101)),
                                  ('member_tolerance',(float('nan'),-1.,None))):
                original=getattr(p,key)
                for bad in badvalues:
                    setattr(p,key,bad)
                    with self.assertRaises(ValueError):p.validate()
                setattr(p,key,original)
        p=opposing();signature=model_signature(p);p.load_steps=2
        self.assertNotEqual(signature,model_signature(p))

    def test_inactive_bars_keep_chord_motion_and_unit_labelled_active_rows(self):
        from pynitegui.qt.app import deformation_paths
        from pynitegui.qt.diagrams import sample_member
        from pynitegui.qt.spatial_view import viewport_payload
        p=opposing();r=analyze(p)
        inactive=next(item['name'] for item in r.solver._brecon_iterations['Positive']['contacts'] if not item['active'])
        samples=sample_member(p,r,inactive)
        self.assertTrue(np.all(samples['axial']==0.))
        self.assertEqual(len(deformation_paths(p,r)[1]),2)
        p.unit_system='si_mm';headers,rows=result_table(p,r,'active_states')
        self.assertIn('Units',headers);self.assertEqual(rows[0][-1],p.units.force)
        self.assertEqual([row[4] for row in rows],['Yes','No'])


    def test_inactive_bar_governing_station_preserves_transverse_chord_motion(self):
        from pynitegui.qt.examples import example_project
        from pynitegui.qt.station_queries import member_candidates
        p=example_project('official_tension_braced');r=analyze(p)
        self.assertFalse(r.solver.members['Brace2'].active[r.combination])
        candidates=member_candidates(p,r,'Brace2','dy',r.combination)
        self.assertAlmostEqual(candidates[0][2],0.,places=10)
        import json
        from pathlib import Path
        reference=json.loads((Path(__file__).parent/'fixtures/official_unilateral_reference.json').read_text())
        end=reference['examples']['tension_braced'][r.combination]['nodes']['N2']
        expected=(144*end['DX']+180*end['DY'])/math.hypot(144,180)
        self.assertAlmostEqual(candidates[1][2],expected,places=9)


class OfficialUnilateralTests(unittest.TestCase):
    def test_three_official_adaptations_match_pinned_unmodified_engine_reference(self):
        import json
        from pathlib import Path
        from pynitegui.qt.examples import example_project
        from pynitegui.qt.official_examples import SOURCE_COMMIT
        reference=json.loads((Path(__file__).parent/'fixtures/official_unilateral_reference.json').read_text())
        self.assertEqual(reference['source_commit'],SOURCE_COMMIT)
        for key,combinations in reference['examples'].items():
            p=example_project('official_'+key);r=analyze(p)
            for combo,expected in combinations.items():
                selected=r.for_combination(combo)
                for name in p.nodes:
                    values=expected['nodes'][name]
                    np.testing.assert_allclose(selected.displacements[name],[values[k] for k in ('DX','DY','RZ')],rtol=1e-7,atol=2e-9)
                    reactions=[values[k] for k in ('RxnFX','RxnFY','RxnMZ')]
                    if key=='ground_braced' and name in ('N1','N4'):
                        reactions[1]+=expected['nodes'][name+'s']['RxnFY']
                    np.testing.assert_allclose(selected.reactions[name],reactions,rtol=1e-7,atol=2e-7)
                self.assertTrue(check_equilibrium(p,selected).passed)

    def test_foundation_reversed_load_releases_soil_and_matches_simple_beam(self):
        from pynitegui.qt.examples import example_project
        p=example_project('official_foundation');p.loads['P'].magnitude=40.
        r=analyze(p)
        self.assertTrue(all(not item['active'] for item in r.solver._brecon_iterations['Combo 1']['contacts']))
        EI=p.materials['Steel'].E*p.sections['W8x35'].Iz
        for name,node in p.nodes.items():
            x=min(node.x,300-node.x)
            expected=40*x*(3*300**2-4*x*x)/(48*EI)
            self.assertAlmostEqual(r.displacements[name][1],expected,places=8)
        self.assertAlmostEqual(r.reactions['N1'][1],-20.,places=8)
        self.assertAlmostEqual(r.reactions['N26'][1],-20.,places=8)

    def test_gravity_only_one_way_ground_braced_frame_rejects_mechanism(self):
        from pynitegui.qt.examples import example_project
        p=example_project('official_ground_braced');p.combinations={'Gravity':{'D':1.4}}
        with self.assertRaisesRegex(ValueError,'stiffness|Unstable'):analyze(p)


if __name__=='__main__':unittest.main()
