"""General support normals against independent compliance and force balance."""
from copy import deepcopy
import math
import pickle
import unittest
from unittest.mock import patch

import numpy as np
from pynitegui.qt.analysis import analyze, model_signature
from pynitegui.qt.analysis_method import analysis_method_issue
from pynitegui.qt.equilibrium import check_equilibrium
from pynitegui.qt.model import Project, Load
from pynitegui.qt.spatial_model import SpatialProject, SpatialLoad
from pynitegui.qt.spatial_conversion import to_spatial
from pynitegui.qt.support_axes import support_normal
from test_inclined_supports import solve, supported


def cantilever(normal=(31., 24.), springs=(0.,)*6):
    p = SpatialProject()
    p.add_member((0., 0., 0.), (120., 0., 0.))
    p.nodes['N1'].support = 'fixed'
    n = p.nodes['N2']
    n.support, n.support_angle, n.support_elevation = 'inclined', *normal
    for key, value in zip(('spring_x','spring_y','spring_z','spring_rx','spring_ry','spring_rz'), springs):
        setattr(n,key,value)
    for direction, value in zip(('FX','FY','FZ','MX','MY','MZ'), (3.,-2.,1.,7.,-4.,5.)):
        p.loads[direction] = SpatialLoad(direction,'N2',direction,value)
    p.combinations = {'Service':{'Case 1':1.},'Reverse':{'Case 1':-1.7},'Zero':{'Case 1':0.}}
    return p


def compliance(p):
    L=120.; m=p.materials[p.default_material]; s=p.sections[p.default_section]
    C=np.zeros((6,6)); C[0,0]=L/(m.E*s.A); C[3,3]=L/(m.G*s.J)
    for translation,rotation,inertia,sign in ((1,5,s.Iz,1),(2,4,s.Iy,-1)):
        C[translation,translation]=L**3/(3*m.E*inertia)
        C[rotation,rotation]=L/(m.E*inertia)
        C[translation,rotation]=C[rotation,translation]=sign*L**2/(2*m.E*inertia)
    return C


def reference(p):
    node=p.nodes['N2']; C=np.linalg.inv(np.linalg.inv(compliance(p))+np.diag(node.springs))
    f=np.array((3.,-2.,1.,7.,-4.,5.)); n=support_normal(node); c=np.r_[n,np.zeros(3)]
    rows=[c,*(np.eye(6)[i] for i,fixed in enumerate(node.restraints) if fixed)]
    B=np.array(rows)
    # Reference Lagrange multipliers use the closed-form cantilever compliance;
    # neither production stiffness nor its nullspace basis enters this solve.
    reaction=-B.T@np.linalg.pinv(B@C@B.T,rcond=1e-13)@(B@C@f)
    d=C@(f+reaction)
    return d,reaction-np.array(node.springs)*d


class SpatialInclinedTests(unittest.TestCase):
    def test_full_six_dof_compliance_normals_springs_combinations_and_pickle(self):
        for angles in ((0.,0.),(90.,0.),(-180.,0.),(31.,24.),(-123.,-47.),(71.,90.),(24.,-90.)):
            for springs in ((0.,)*6,(5.,7.,11.,100.,200.,300.)):
                # Axis-parallel rigid/spring conflicts remain invalid.
                if angles in ((0.,0.),(90.,0.),(-180.,0.),(71.,90.),(24.,-90.)) and any(springs):
                    continue
                p=cantilever(angles,springs); before=p.to_dict(); d,r=reference(p)
                result=pickle.loads(pickle.dumps(solve(p)))
                self.assertEqual(p.to_dict(),before)
                for combo,factor in (('Service',1.),('Reverse',-1.7),('Zero',0.)):
                    selected=result.for_combination(combo)
                    np.testing.assert_allclose(selected.displacements['N2'],d*factor,rtol=1e-9,atol=1e-11)
                    np.testing.assert_allclose(selected.reactions['N2'],r*factor,rtol=1e-8,atol=1e-8)
                    self.assertTrue(check_equilibrium(p,selected).passed)
                    self.assertAlmostEqual(float(support_normal(p.nodes['N2'])@selected.displacements['N2'][:3]),0.,places=11)
                    member=next(iter(selected.solver.members['M1'].sub_members.values()))
                    np.testing.assert_allclose(member.F(combo)[6:,0],np.array((3.,-2.,1.,7.,-4.,5.))*factor+r*factor,atol=1e-8)

    def test_additional_global_restraints_redundancy_and_nearly_dependent_rejection(self):
        for flags in ((True,False,False,False,False,False),(True,True,False,False,True,False)):
            p=cantilever(); node=p.nodes['N2']
            for key,value in zip(('restraint_x','restraint_y','restraint_z','restraint_rx','restraint_ry','restraint_rz'),flags):
                setattr(node,key,value)
            d,r=reference(p); result=solve(p)
            np.testing.assert_allclose(result.displacements['N2'],d,atol=1e-10)
            np.testing.assert_allclose(result.reactions['N2'],r,atol=1e-7)
        p=cantilever((0.,0.)); p.nodes['N2'].restraint_x=True
        result=solve(p)
        self.assertEqual(result.solver._pynitegui_support_reactions['Service']['N2']['normal_reaction_kip'],0.)
        p.nodes['N2'].support_angle=1e-7
        with self.assertRaisesRegex(ValueError,'Nearly dependent'):
            solve(p)
        p=cantilever((0.,90.));p.nodes['N2'].spring_y=1.
        with self.assertRaisesRegex(ValueError,'rigid restraint'):
            p.validate()

    def test_conversion_released_frames_and_planar_trusses_preserve_physics(self):
        from pynitegui.qt.examples import example_project
        for key in ('inclined_roller','gerber','truss','shear_release'):
            p=example_project(key)
            if key=='shear_release':
                p=supported(90.);p.members['M1'].release_end_x=True
            elif key != 'inclined_roller':
                name=next(n.name for n in p.nodes.values() if n.support=='roller')
                p.nodes[name].support='inclined';p.nodes[name].support_angle=21.
            a=solve(p);b=solve(to_spatial(p))
            for combo in p.combinations:
                x,y=a.for_combination(combo),b.for_combination(combo)
                for name in p.nodes:
                    for i,j in ((0,0),(1,1),(2,5)):
                        expected=x.displacements[name][i]
                        if expected is not None:
                            self.assertAlmostEqual(y.displacements[name][j],expected,places=8)
                    np.testing.assert_allclose(np.array(y.reactions[name])[[0,1,5]],x.reactions[name],atol=1e-7)
                self.assertTrue(check_equilibrium(p,x).passed)
                self.assertTrue(check_equilibrium(to_spatial(p),y).passed)

    def test_spatial_release_recovery_keeps_normal_constraints_and_no_gauge_torque(self):
        from pynitegui.qt.examples import example_project
        for key in ('3d_released_beam','3d_sliding_beam','3d_tripod'):
            p=example_project(key)
            if key=='3d_tripod':
                name=p.node_at(0.,80.,0.)
                p.nodes[name].support='inclined';p.nodes[name].support_angle=30.;p.nodes[name].support_elevation=20.
            else:
                p.nodes['N2'].support='inclined';p.nodes['N2'].support_angle=30.;p.nodes['N2'].support_elevation=20.
                if key=='3d_released_beam':
                    p.nodes['N2'].restraint_y=True
                if key=='3d_sliding_beam':
                    # The released end is unsupported by this member; retain its
                    # physical global support while checking redundant normals.
                    for axis in ('x','y','z','rx','ry','rz'):
                        setattr(p.nodes['N2'],'restraint_'+axis,True)
            result=solve(p)
            for combo in p.combinations:
                r=result.for_combination(combo)
                self.assertTrue(check_equilibrium(p,r).passed)
                self.assertAlmostEqual(float(support_normal(p.nodes[name if key=='3d_tripod' else 'N2'])@r.displacements[name if key=='3d_tripod' else 'N2'][:3]),0.,places=10)
            self.assertIsNotNone(pickle.loads(pickle.dumps(result)))

    def test_spatial_schema_strict_migration_and_orientation_signature(self):
        p=cantilever();data=p.to_dict();self.assertEqual(data['version'],38)
        self.assertEqual(Project.from_dict(data).to_dict(),data)
        for field,values in (('support_angle',(True,None,float('nan'),181.)),('support_elevation',(True,None,float('inf'),91.))):
            for value in values:
                bad=deepcopy(data);bad['nodes']['N2'][field]=value
                with self.assertRaises(ValueError):Project.from_dict(bad)
            bad=deepcopy(data);bad['nodes']['N2'].pop(field)
            with self.assertRaisesRegex(ValueError,'Missing spatial support'):Project.from_dict(bad)
        old=cantilever();old.nodes['N2'].support='free';old.nodes['N2'].support_angle=old.nodes['N2'].support_elevation=0.
        legacy=old.to_dict();legacy['version']=32
        for n in legacy['nodes'].values():n.pop('support_angle');n.pop('support_elevation')
        restored=Project.from_dict(legacy)
        self.assertEqual(restored.to_dict(),old.to_dict())
        legacy['nodes']['N2']['support']='inclined'
        with self.assertRaisesRegex(ValueError,'version 34'):Project.from_dict(legacy)
        signature=model_signature(p);p.nodes['N2'].support_elevation+=1.
        self.assertNotEqual(model_signature(p),signature)

    def test_existing_global_pdelta_restrictions_are_not_weakened(self):
        from pynitegui.qt.examples import example_project
        for key,message in (('3d_tripod','frame members'),('3d_released_beam','Spatial end releases'),('shear_release','released member translations')):
            p=example_project(key);p.analysis_method='p_delta'
            self.assertIn(message,analysis_method_issue(p))

    def test_pdelta_axis_limit_and_oblique_coupled_convergence(self):
        for angle in (0.,23.,-47.):
            p=supported(angle);p.analysis_method='p_delta'
            r=solve(p)
            self.assertEqual(r.analysis_method,'p_delta')
            for combo in p.combinations:
                self.assertTrue(check_equilibrium(p,r.for_combination(combo)).passed)
                node=r.solver.nodes['N2'];d=r.solver.D(combo)
                from Pynite import FEModel3D
                K=FEModel3D.Ke(r.solver,combo,check_stability=False,sparse=True)+FEModel3D.Kg(r.solver,combo,sparse=True,first_step=False)
                raw=np.asarray(K@d+r.solver.FER(combo)-r.solver.P(combo)).ravel()[[6,7,11]]
                metadata=r.solver._pynitegui_support_reactions[combo]['N2']
                np.testing.assert_allclose(raw,metadata['rigid_reaction'],atol=1e-8)
            converted=to_spatial(p)
            spatial=solve(converted)
            np.testing.assert_allclose(np.array(spatial.displacements['N2'])[[0,1,5]],r.displacements['N2'],atol=1e-9)
        p=cantilever((45.,90.));p.analysis_method='p_delta'
        r=solve(p)
        for combo,factor in (('Service',1.),('Reverse',-1.7),('Zero',0.)):
            C=compliance(p);K=np.linalg.inv(C); L=120.; s=p.sections[p.default_section]; m=p.materials[p.default_material]
            applied=np.array((3.,-2.,1.,7.,-4.,5.))*factor
            # Closed-form axial root includes the engine's axial Kg term.
            axial=2*applied[0]/(1+math.sqrt(1+4*applied[0]/(m.E*s.A)))
            geometric=np.diag((1.,6/5,6/5,(s.Iy+s.Iz)/s.A,2*L**2/15,2*L**2/15))
            geometric[1,5]=geometric[5,1]=-L/10
            geometric[2,4]=geometric[4,2]=L/10
            total=K+axial/L*geometric
            free=[0,2,3,4,5];expected=np.zeros(6)
            expected[free]=np.linalg.solve(total[np.ix_(free,free)],applied[free])
            np.testing.assert_allclose(r.for_combination(combo).displacements['N2'],expected,rtol=1e-9,atol=1e-10)

    def test_pdelta_buckling_and_iteration_failure_reject_without_results(self):
        from test_qt_nonlinear import column
        p,tip,_=column(ratio=1.2)
        # Normal fixes only axial tip motion if assigned there, so place an
        # inclined restraint redundantly at the fixed base in a spatial copy.
        p=to_spatial(p,'spatial');node=p.nodes['N1'];node.support='inclined'
        node.support_angle=0.;node.support_elevation=90.
        for axis in ('x','y','z','rx','ry','rz'):setattr(node,'restraint_'+axis,True)
        with self.assertRaisesRegex(ValueError,'Unstable|ill-conditioned'):
            solve(p)
        p=cantilever();p.analysis_method='p_delta'
        from pynitegui.qt.inclined_supports import recover_reactions, FreeEquilibriumError
        with patch('pynitegui.qt.inclined_supports.recover_reactions',side_effect=FreeEquilibriumError('did not converge')) as recovered:
            with self.assertRaisesRegex(ValueError,'did not converge'):solve(p)
        self.assertEqual(recovered.call_count,30)

    def test_oblique_pdelta_against_independent_dense_compliance_iteration(self):
        for angles in ((31.,24.),(-123.,-47.),(30.,-60.)):
            p=cantilever(angles);p.analysis_method='p_delta';p.loads['FX'].magnitude=-10.
            solved=solve(p);L=120.;section=p.sections[p.default_section];material=p.materials[p.default_material]
            elastic=np.linalg.inv(compliance(p));normal=np.r_[support_normal(p.nodes['N2']),np.zeros(3)]
            geometric=np.diag((1.,6/5,6/5,(section.Iy+section.Iz)/section.A,2*L**2/15,2*L**2/15))
            geometric[1,5]=geometric[5,1]=-L/10;geometric[2,4]=geometric[4,2]=L/10
            for combo,factor in (('Service',1.),('Reverse',-1.7),('Zero',0.)):
                force=np.array((-10.,-2.,1.,7.,-4.,5.))*factor;d=np.zeros(6)
                for _ in range(100):
                    axial=material.E*section.A/L*d[0]
                    C=np.linalg.inv(elastic+axial/L*geometric)
                    multiplier=-float(normal@C@force)/float(normal@C@normal)
                    next_d=C@(force+normal*multiplier)
                    if np.max(abs(next_d-d))<1e-13:
                        d=next_d;break
                    d=next_d
                else:self.fail('Independent compliance iteration failed')
                selected=solved.for_combination(combo)
                np.testing.assert_allclose(selected.displacements['N2'],d,rtol=1e-9,atol=1e-10)
                np.testing.assert_allclose(selected.reactions['N2'],normal*multiplier,rtol=1e-8,atol=1e-8)
                self.assertTrue(check_equilibrium(p,selected).passed)

    def test_coupled_surface_shared_node_keeps_normal_and_global_restraint_union(self):
        from pynitegui.qt.examples import example_project
        p=example_project('3d_slab_frame');ordinary=solve(p)
        node=p.nodes['N1'];node.support='inclined';node.support_angle=60.;node.support_elevation=30.
        for axis in ('x','z','rx','ry','rz'):setattr(node,'restraint_'+axis,True)
        constrained=solve(p)
        self.assertGreater(len(constrained.displacements),len(p.nodes))
        for combo in p.combinations:
            a,b=ordinary.for_combination(combo),constrained.for_combination(combo)
            for name in a.displacements:
                np.testing.assert_allclose(a.displacements[name],b.displacements[name],atol=1e-10)
                np.testing.assert_allclose(a.reactions[name],b.reactions[name],atol=1e-7)
            self.assertTrue(check_equilibrium(p,b).passed)

    def test_spatial_support_copy_clearing_and_collision_include_elevation(self):
        from pynitegui.qt.geometry_tools import plan_transform, support_state, clear_support
        p=cantilever();original=p.to_dict()
        copied=plan_transform(p,[('members','M1')],'repeat',offset=(0.,240.,0.),copy_supports=True).definition
        normals=[n for n in copied.nodes.values() if n.support=='inclined']
        self.assertEqual(len(normals),2)
        self.assertTrue(all((n.support_angle,n.support_elevation)==(31.,24.) for n in normals))
        before=support_state(normals[-1]);normals[-1].support_elevation+=1.
        self.assertNotEqual(support_state(normals[-1]),before)
        clear_support(normals[-1])
        self.assertEqual((normals[-1].support_angle,normals[-1].support_elevation),(0.,0.))
        self.assertEqual(p.to_dict(),original)
