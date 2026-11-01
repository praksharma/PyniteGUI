"""Affine plate loads: independent integration, continuum refinement and parity."""
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import unittest
from unittest.mock import patch
import numpy as np
from Pynite import FEModel3D
from pynitegui.qt.plate_model import PlateDefinition,analyze_plate,select_plate_combination,PLANES
from pynitegui.qt.official_plate import example_definition
from pynitegui.qt.plate_inspection import inspect_plate


def triangular_navier(points,a,b,nu,q,D,terms=80):
    m=np.arange(1,terms+1,2)[:,None];n=np.arange(1,terms+1)[None,:]
    alpha=m*np.pi/a;beta=n*np.pi/b
    C=8*q/(np.pi**2*m*n)/(alpha**2+beta**2)**2
    x,y=np.asarray(points).T
    sx,cx=np.sin(x[:,None]*alpha.T),np.cos(x[:,None]*alpha.T)
    sy,cy=np.sin(y[:,None]*beta),np.cos(y[:,None]*beta)
    def field(matrix,left=sx,right=sy):return np.einsum('pm,mn,pn->p',left,matrix,right)
    return field(C)/D,np.column_stack((field(C*(alpha**2+nu*beta**2)),field(C*(beta**2+nu*alpha**2)),
                                      -field(C*(1-nu)*alpha*beta,cx,cy)))


class PlatePressureTests(unittest.TestCase):
    def test_current_schema_old_uniform_migration_and_profile_validation(self):
        d=PlateDefinition(pressure_profiles={'Case 1':{'axis':'y','end_pressure':0.}})
        self.assertEqual(d.to_dict()['version'],4);self.assertEqual(PlateDefinition.from_dict(d.to_dict()),d)
        for bad in (None,[],{'Missing':{'axis':'y','end_pressure':0.}},
                    {'Case 1':{'axis':'z','end_pressure':0.}}, {'Case 1':{'axis':'y','end_pressure':True}},
                    {'Case 1':{'axis':'y','end_pressure':float('inf')}},{'Case 1':{'axis':'x','end_pressure':1e7}},
                    {'Case 1':{'axis':'y','end_pressure':0.,'nodes':['N1']}}):
            with self.subTest(bad=bad),self.assertRaises(ValueError):replace(d,pressure_profiles=bad).validate()
        legacy=PlateDefinition().to_dict();legacy['version']=3;legacy.pop('pressure_profiles');before=deepcopy(legacy)
        self.assertEqual(PlateDefinition.from_dict(legacy),PlateDefinition());self.assertEqual(legacy,before)
        with self.assertRaises(ValueError):PlateDefinition.from_dict({**d.to_dict(),'version':3})
        bad=d.to_dict();bad.pop('pressure_profiles')
        with self.assertRaises(ValueError):PlateDefinition.from_dict(bad)
        d.rename_case('Case 1','Water');self.assertEqual(d.pressure_profiles,{'Water':{'axis':'y','end_pressure':0.}})

    def test_triangular_force_and_discrete_first_moments_in_all_planes_and_families(self):
        for family in ('Quad','Rect'):
            for plane in PLANES:
                d=PlateDefinition(width=120.,height=80.,mesh_size=20.,element_type=family,plane=plane,origin=[17.,-31.,49.],
                    pressure=1e-5,pressure_profiles={'Case 1':{'axis':'y','end_pressure':0.}},
                    combinations={'Reverse':{'Case 1':-2.},'Zero':{'Case 1':0.}})
                r=analyze_plate(d);area=120*80;F=area*1e-5/2
                # Uniform centroid loads shift the first moment by q*a*h²/12.
                applied=np.r_[d.normal*F,np.cross(np.eye(3)[PLANES[plane][1]],d.normal)*F*(80/3+20**2/(6*80))
                              +np.cross(np.eye(3)[PLANES[plane][0]],d.normal)*F*60]
                np.testing.assert_allclose([row['applied'] for row in r['equilibrium']],applied,atol=1e-10)
                self.assertAlmostEqual(r['applied'],F);self.assertIsNone(r['pressure'])
                self.assertAlmostEqual(r['continuous_pressure_resultants']['first_moment_local_y_kip_in'],F*80/3)
                centres=r['points'][r['cells']].mean(axis=1)
                np.testing.assert_allclose(r['element_pressures'],1e-5*(1-centres[:,1]/80),atol=1e-18)
                self.assertAlmostEqual(r['reactions'].sum(),-F,places=9)
                for name,factor in (('Reverse',-2.),('Zero',0.)):
                    selected=select_plate_combination(r,name)
                    for key in ('displacement','reactions','moments','element_pressures'):
                        np.testing.assert_allclose(selected[key],factor*r[key],atol=1e-10)
                name=r['element_names'][0]
                lo,hi=inspect_plate(r,name,-1.,-1.),inspect_plate(r,name,1.,1.)
                self.assertEqual(lo['applied_pressure'],hi['applied_pressure'])
                self.assertNotEqual(lo['target_pressure'],hi['target_pressure'])

    def test_nonuniform_opening_two_axis_patterns_and_gravity_preserve_recipe_force(self):
        for family in ('Quad','Rect'):
            d=PlateDefinition(width=120.,height=80.,mesh_size=20.,element_type=family,plane='XZ',origin=[23.,17.,-39.],
                x_control=[10.,67.],y_control=[15.],pressure=1e-5,load_case='Y',additional_pressures={'X':-1e-5},
                pressure_profiles={'Y':{'axis':'y','end_pressure':0.},'X':{'axis':'x','end_pressure':1e-5}},
                combinations={'Mix':{'Y':1.3,'X':-.7}},self_weight_case='Y',
                openings=[dict(name='Hole',x_left=30.,y_bott=20.,width=20.,height=20.)])
            d.material.rho=.00009
            r=select_plate_combination(analyze_plate(d),'Mix')
            area=120*80-20*20;Ix=120*80*60-20*20*40;Iy=120*80*40-20*20*30
            q=1.3*(1e-5+.00009*d.thickness)+.7e-5;gx=-.7*2e-5/120;gy=-1.3e-5/80
            expected=q*area+gx*Ix+gy*Iy
            self.assertAlmostEqual(r['applied'],expected,places=11)
            self.assertAlmostEqual(r['reactions'].sum(),-expected,places=8)
            self.assertTrue(all(abs(row['residual'])<=row['tolerance'] for row in r['equilibrium']))

    def test_triangular_navier_displacements_and_moments_converge(self):
        for family in ('Quad','Rect'):
            errors=[]
            for size in (30.,15.,7.5):
                d=PlateDefinition(width=120.,height=180.,thickness=.6,mesh_size=size,element_type=family,pressure=-1e-7,
                    pressure_profiles={'Case 1':{'axis':'y','end_pressure':0.}})
                r=analyze_plate(d);D=d.material.E*d.thickness**3/(12*(1-d.material.nu**2))
                w,_=triangular_navier(r['points'],120.,180.,d.material.nu,-1e-7,D)
                centres=r['points'][r['cells']].mean(axis=1)
                _,moments=triangular_navier(centres,120.,180.,d.material.nu,-1e-7,D)
                error=(np.linalg.norm(r['displacement']-w)/np.linalg.norm(w),np.linalg.norm(r['moments']-moments)/np.linalg.norm(moments))
                errors.append(error)
            self.assertLess(errors[-1][0],.01,(family,errors));self.assertLess(errors[-1][1],.025,(family,errors))
            self.assertTrue(all(b[0]<a[0] and b[1]<a[1] for a,b in zip(errors,errors[1:])),(family,errors))
            w2,m2=triangular_navier(centres,120.,180.,d.material.nu,-1e-7,D,terms=160)
            _,m1=triangular_navier(centres,120.,180.,d.material.nu,-1e-7,D)
            self.assertLess(np.linalg.norm(m2-m1)/np.linalg.norm(m2),.0005)

    def test_wrong_engine_pressure_cannot_pass_independent_equilibrium(self):
        original=FEModel3D.add_quad_surface_pressure
        def tamper(model,name,pressure,case='Case 1'):
            return original(model,name,pressure*1.1,case)
        d=PlateDefinition(mesh_size=30.,pressure_profiles={'Case 1':{'axis':'y','end_pressure':0.}})
        with patch.object(FEModel3D,'add_quad_surface_pressure',tamper),self.assertRaisesRegex(ValueError,'equilibrium failed'):analyze_plate(d)

    def test_official_wall_matches_pinned_original_source_snapshot(self):
        fixture=json.loads((Path(__file__).parent/'fixtures/official_wall_hydrostatic.json').read_text())
        from pynitegui.qt.official_examples import SOURCE_COMMIT
        self.assertEqual(fixture['source_commit'],SOURCE_COMMIT)
        d=example_definition('official_wall_hydrostatic');r=select_plate_combination(analyze_plate(d),'1.4F')
        self.assertEqual(len(r['cells']),375);self.assertEqual(len(r['names']),416)
        self.assertEqual(r['names'],fixture['names'])
        for key in ('displacement','reactions','moments'):
            np.testing.assert_allclose(r[key],fixture[key],rtol=1e-8,atol=1e-10)
        self.assertAlmostEqual(r['applied'],245.7,places=9);self.assertAlmostEqual(r['reactions'].sum(),-245.7,places=8)
        rows={row['component']:row for row in r['equilibrium']}
        self.assertAlmostEqual(rows['MX']['applied'],14774.76,places=7)
        self.assertAlmostEqual(rows['MY']['applied'],-36855.,places=7)
        self.assertIsNone(r['shears'])
