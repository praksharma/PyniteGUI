"""Physical mass, eigen-equations and independent vibration benchmarks."""
import contextlib
import io
import math
import unittest
import numpy as np
from pynitegui.qt.model import Project,Load,Material,Section
from pynitegui.qt.modal import ModalSettings,analyze_modal,modal_issue,mass_matrix
from pynitegui.qt.spatial_conversion import to_spatial


def beam(segments=1, distributed=False):
    p=Project(materials={'M':Material('M',E=29000.,nu=.3,rho=.0002836)},default_material='M',
              sections={'S':Section('S',A=10.,Iy=30.,Iz=100.,J=.5)},default_section='S')
    for index in range(segments):p.add_member((120*index/segments,0.),(120*(index+1)/segments,0.))
    p.nodes['N1'].support='fixed'
    if distributed:
        p.self_weight_case='Case 1'
    else:
        p.loads['W']=Load('W','N'+str(segments+1),'FY',-10.)
    return p


def solve(p,settings=None):
    with contextlib.redirect_stdout(io.StringIO()):return analyze_modal(p,settings or ModalSettings('Service',1))


class ModalEngineeringTests(unittest.TestCase):
    def test_tip_mass_cantilever_exact_lateral_axial_and_massless_rotation(self):
        p=beam();r=solve(p,ModalSettings('Service',2,gravity=386.4))
        mass=10/386.4
        expected=np.sqrt([3*p.E*p.Iz/120**3/mass,p.E*p.A/120/mass])/(2*math.pi)
        np.testing.assert_allclose(r.frequencies,expected,rtol=1e-11)
        self.assertLess(max(r.residuals),1e-10)
        self.assertLess(r.orthogonality_error,1e-10)
        self.assertEqual(r.normalization,['translation','translation'])
        self.assertEqual(r.shapes.shape,(2,2,6))
        self.assertAlmostEqual(abs(r.shapes[0,1,5]),3/(2*120),places=12)
        with self.assertRaisesRegex(ValueError,'Fewer finite'):solve(p,ModalSettings('Service',3))

    def test_distributed_self_weight_converges_to_continuum_beam(self):
        expected=None;errors=[]
        for count in (1,2,8):
            p=beam(count,True);r=solve(p)
            rho=p.materials['M'].rho*p.A/r.settings.gravity
            expected=1.875104068711961**2/(2*math.pi*120**2)*math.sqrt(p.E*p.Iz/rho)
            errors.append(abs(r.frequencies[0]/expected-1))
            self.assertAlmostEqual(r.metadata()['total_weight_kip'],p.materials['M'].rho*p.A*120,places=12)
        self.assertGreater(errors[0],errors[1]);self.assertGreater(errors[1],errors[2]);self.assertLess(errors[-1],3e-6)

    def test_member_point_and_uniform_weights_preserve_total_and_positive_mass(self):
        from pynitegui.qt.analysis import analyze
        for position in (.0,.13,.5,.87,1.):
            p=beam();p.loads={'W':Load('W','M1','FY',-10.,position)}
            with contextlib.redirect_stdout(io.StringIO()):model=analyze(p).solver
            matrix,source=mass_matrix(p,model,ModalSettings('Service',1))
            self.assertGreaterEqual(np.linalg.eigvalsh(matrix.toarray()).min(),-1e-12)
            for axis in range(3):
                translation=np.zeros(12);translation[[axis,axis+6]]=1
                self.assertAlmostEqual(float(translation @ matrix @ translation),10/ModalSettings('Service').gravity,places=12)
        p=beam();p.loads={'W':Load('W','M1','FY',-.2,.2,kind='distributed',end_magnitude=-.7,end_position=.9)}
        with contextlib.redirect_stdout(io.StringIO()):model=analyze(p).solver
        matrix,source=mass_matrix(p,model,ModalSettings('Service',1))
        self.assertAlmostEqual(source[0]['weight'],.45*.7*120,places=12)
        self.assertGreaterEqual(np.linalg.eigvalsh(matrix.toarray()).min(),-1e-11)

    def test_gravity_weight_scaling_and_no_hidden_density(self):
        p=beam();r=solve(p)
        self.assertAlmostEqual(solve(p,ModalSettings('Service',1,gravity=r.settings.gravity*4)).frequencies[0],2*r.frequencies[0],places=10)
        p.loads['W'].magnitude=-40.
        self.assertAlmostEqual(solve(p).frequencies[0],r.frequencies[0]/2,places=10)
        p.materials['M'].rho*=100
        self.assertAlmostEqual(solve(p).frequencies[0],r.frequencies[0]/2,places=10)
        p.loads.clear()
        with self.assertRaisesRegex(ValueError,'No finite positive mass'):solve(p)

    def test_spatial_torsion_uses_polar_inertia_and_rotational_normalization(self):
        p=to_spatial(beam(1,True),'spatial')
        r=solve(p,ModalSettings('Service',6))
        section=p.sections['S'];rho=p.materials['M'].rho/r.settings.gravity
        expected=math.sqrt(3*p.materials['M'].G*section.J/(rho*(section.Iy+section.Iz)*120**2))/(2*math.pi)
        modes=[i for i,kind in enumerate(r.normalization) if kind=='rotation']
        self.assertEqual(len(modes),1)
        self.assertAlmostEqual(r.frequencies[modes[0]],expected,places=9)
        self.assertAlmostEqual(abs(r.shapes[modes[0],1,3]),1.,places=10)

    def test_exact_inclined_constraint_and_settings_fail_closed(self):
        p=beam();p.nodes['N2'].support='inclined';p.nodes['N2'].support_angle=35.
        r=solve(p);normal=np.array([-math.sin(math.radians(35)),math.cos(math.radians(35))])
        self.assertAlmostEqual(float(r.shapes[0,1,:2] @ normal),0.,places=12)
        for settings in (ModalSettings('missing'),ModalSettings('Service',True),ModalSettings('Service',0),
                         ModalSettings('Service',51),ModalSettings('Service',1,'Z'),ModalSettings('Service',1,gravity=0),
                         ModalSettings('Service',1,gravity=float('nan'))):
            with self.assertRaises(ValueError):solve(p,settings)
        p.combinations['Service']['Case 1']=-1.
        with self.assertRaisesRegex(ValueError,'nonnegative'):solve(p)
        p.combinations['Service']['Case 1']=1.
        p.members['M1'].release_end=True
        self.assertIn('unreleased',modal_issue(p))

    def test_official_modal_column_matches_pinned_engine_frequencies_and_shapes(self):
        import json
        from pathlib import Path
        from pynitegui.qt.official_examples import SOURCE_COMMIT
        from pynitegui.qt.official_modal import example_project
        reference=json.loads((Path(__file__).parent/'fixtures/official_modal_reference.json').read_text())
        self.assertEqual(reference['source_commit'],SOURCE_COMMIT)
        p=example_project();before=p.to_dict()
        r=solve(p,ModalSettings('Mass',3,gravity=386.4))
        np.testing.assert_allclose(r.frequencies,[row['frequency_hz'] for row in reference['modes']],rtol=1e-9)
        np.testing.assert_allclose(r.shapes,[row['shape'] for row in reference['modes']],rtol=1e-8,atol=1e-9)
        self.assertEqual(p.to_dict(),before)

    def test_sparse_603_coordinate_mass_spring_chain_matches_closed_form(self):
        from pynitegui.qt.spatial_model import SpatialLoad
        n=201;p=to_spatial(beam(n),'spatial');p.loads={}
        for i,node in enumerate(list(p.nodes.values())[1:],1):
            node.support='custom'
            node.restraint_x=node.restraint_y=node.restraint_z=False
            node.restraint_rx=node.restraint_ry=node.restraint_rz=True
            node.spring_x=node.spring_y=node.spring_z=100.
            p.loads['W'+str(i)]=SpatialLoad('W'+str(i),node.name,'FY',-1.)
        # Keep each segment 120 in; ground translation springs and rigid nodal
        # rotations are real model definitions, not numerical stabilizers.
        for i,node in enumerate(p.nodes.values()):node.x=120.*i
        r=solve(p,ModalSettings('Service',3))
        coefficients=(p.E*p.A/120,12*p.E*p.Iz/120**3,12*p.E*p.Iy/120**3)
        eigenvalues=sorted(100+4*k*math.sin((2*j-1)*math.pi/(4*n+2))**2 for k in coefficients for j in range(1,4))[:3]
        expected=np.sqrt(np.array(eigenvalues)*r.settings.gravity)/(2*math.pi)
        np.testing.assert_allclose(r.frequencies,expected,rtol=1e-8)

    def test_spatial_orientation_and_roll_preserve_point_mass_frequencies(self):
        p=to_spatial(beam(),'spatial');a=p.nodes['N1'];b=p.nodes['N2']
        a.x,a.y,a.z=11.,-20.,30.
        axis=np.array((2.,-3.,4.));axis/=np.linalg.norm(axis)
        b.x,b.y,b.z=np.array(a.coords)+120*axis
        p.members['M1'].roll=31.
        r=solve(p,ModalSettings('Service',3))
        expected=np.sqrt(np.array(sorted([3*p.E*p.Iy/120**3,3*p.E*p.Iz/120**3,p.E*p.A/120]))*r.settings.gravity/10)/(2*math.pi)
        np.testing.assert_allclose(r.frequencies,expected,rtol=1e-10)
        p.unit_system='si_mm';converted=solve(p,ModalSettings('Service',3))
        np.testing.assert_allclose(r.frequencies,converted.frequencies,rtol=1e-12)
