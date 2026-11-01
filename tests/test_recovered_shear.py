"""Accepted masked recovery, independent mechanics, scope and serialization."""
from dataclasses import replace
from copy import deepcopy
import csv
import io
import json
from pathlib import Path
import tempfile
import unittest
import numpy as np
from pynitegui.qt.plate_model import PlateDefinition,analyze_plate,select_plate_combination
from pynitegui.qt.plate_inspection import inspect_plate,write_plate_probes
from pynitegui.qt.model import Load
from pynitegui.qt.quad_shear_snapshot import summary
from pynitegui.qt.surface_results import centre_results,surface_table,surface_recovery
from pynitegui.qt.units import UNIT_SYSTEMS
from plate_reference import navier
from plate_energy_reference import OpeningEnergyReference
from recovered_shear_reference import triangular_shear,torsional_edge_shear
from test_surface_results import supported_plate,quiet_solve


def values(meta):return np.array([row if row is not None else [np.nan,np.nan] for row in meta['values']])


def error(actual,expected,mask):return np.linalg.norm(actual[mask]-expected[mask])/np.linalg.norm(expected[mask])


class RecoveredShearTests(unittest.TestCase):
    def test_navier_thickness_axes_units_and_signed_zero_snapshots(self):
        for plane in ('XY','XZ','YZ'):
            d=PlateDefinition(width=120.,height=180.,thickness=1.2,mesh_size=15.,plane=plane,pressure=-1e-7,
                combinations={'Reverse':{'Case 1':-2.},'Zero':{'Case 1':0.}})
            before=d.to_dict();r=analyze_plate(d);meta=r['recovered_shear'];self.assertTrue(meta['eligible']);self.assertEqual(meta['available'],len(r['cells']))
            points=r['points'][r['cells']].mean(axis=1);D=d.material.E*d.thickness**3/(12*(1-d.material.nu**2))
            expected=navier(points,120,180,d.material.nu,d.pressure,D,terms=160)[2];mask=np.array(meta['values'])[:,0]==np.array(meta['values'])[:,0]
            self.assertLess(error(values(meta),expected,mask),.025)
            self.assertIsNone(r['shears']);self.assertEqual(d.to_dict(),before)
            name=r['element_names'][0];probe=inspect_plate(r,name);self.assertNotIn('Qx',probe);self.assertIsNotNone(probe['recovered_Qx'])
            self.assertIsNone(inspect_plate(r,name,.1,0.)['recovered_Qx']);self.assertEqual(inspect_plate(r,name,.1,0.)['shear_status'],'centre_only')
            for combo,factor in (('Reverse',-2.),('Zero',0.)):
                selected=select_plate_combination(r,combo)
                np.testing.assert_allclose(values(selected['recovered_shear']),factor*values(meta),atol=1e-12,rtol=1e-7)
                self.assertEqual(selected['snapshot_id'],r['snapshot_id'])
            with tempfile.TemporaryDirectory() as directory:
                path=Path(directory)/'q.csv';write_plate_probes(path,r,UNIT_SYSTEMS['si_mm'])
                rows=list(csv.DictReader(io.StringIO(path.read_text())))
                self.assertIn('Recovered Qx (N/mm)',rows[0]);self.assertAlmostEqual(float(rows[0]['Recovered Qx (N/mm)']),probe['recovered_Qx']*UNIT_SYSTEMS['si_mm'].factor('intensity'))
                self.assertIn(meta['method'],rows[0]['Recovery'])
            json.dumps(meta,allow_nan=False)

    def test_actual_affine_pressure_profiles_match_independent_triangular_shear(self):
        for axis in ('x','y'):
            history=[]
            for size in (15.,7.5):
                d=PlateDefinition(width=120.,height=180.,thickness=.6,mesh_size=size,pressure=-1e-7,
                    pressure_profiles={'Case 1':{'axis':axis,'end_pressure':0.}})
                r=analyze_plate(d);meta=r['recovered_shear'];points=r['points'][r['cells']].mean(axis=1)
                self.assertEqual(meta['available'],len(points));a=triangular_shear(points,120,180,-1e-7,axis,160);b=triangular_shear(points,120,180,-1e-7,axis,320)
                mask=np.ones(len(points),bool);self.assertLess(error(a,b,mask),.0005)
                history.append(error(values(meta),b,mask))
            self.assertLess(history[-1],history[0]);self.assertLess(history[-1],.01)

    def test_opening_corner_masks_and_available_rim_accuracy(self):
        reference=OpeningEnergyReference(nx=96)
        for size in (5.,4.):
            d=PlateDefinition(width=120.,height=120.,thickness=.6,mesh_size=size,pressure=-1e-7,
                openings=[dict(name='Hole',x_left=40.,y_bott=40.,width=40.,height=40.)])
            r=analyze_plate(d);meta=r['recovered_shear'];points=r['points'][r['cells']].mean(axis=1)
            valid=np.array([row is not None for row in meta['values']]);self.assertTrue(valid.any());self.assertFalse(valid.all())
            expected=-1e-7*reference.shears(points);x,y=points.T;rim=valid&(x>=20)&(x<=40)&(y>=48)&(y<=72)
            self.assertGreater(rim.sum(),0);self.assertLess(error(values(meta),expected,rim),.05)
            missing=np.where(~valid)[0][0];probe=inspect_plate(r,r['element_names'][missing]);self.assertIsNone(probe['recovered_Qx']);self.assertIn('corner',probe['shear_status'])
            json.dumps(meta,allow_nan=False)

    def test_eligibility_fails_closed_without_losing_existing_solved_fields(self):
        base=PlateDefinition(width=120.,height=120.,mesh_size=15.,thickness=.6,pressure=-1e-7)
        cases=[replace(base,mesh_size=30.),replace(base,thickness=3.),replace(base,kx_mod=1.2),
               replace(base,edges=dict.fromkeys(base.edges,'Clamped')),
               replace(base,openings=[dict(name='Offcentre',x_left=30.,y_bott=40.,width=40.,height=40.)])]
        for d in cases:
            r=analyze_plate(d);meta=r['recovered_shear'];self.assertFalse(meta['eligible']);self.assertEqual(meta['available'],0)
            self.assertTrue(all(row is None for row in meta['values']));self.assertTrue(np.isfinite(r['moments']).all())
            self.assertIsNone(r['shears']);json.dumps(meta,allow_nan=False)

    def test_zero_poisson_cantilever_and_surface_gravity_pressure(self):
        d=PlateDefinition(width=120.,height=120.,mesh_size=15.,thickness=.6,pressure=-1e-7)
        d.material.nu=0.;d.edges={key:'Clamped' if key=='Left' else 'Free' for key in d.edges}
        r=analyze_plate(d);points=r['points'][r['cells']].mean(axis=1);q=values(r['recovered_shear'])
        np.testing.assert_allclose(q[:,0],d.pressure*(120.-points[:,0]),atol=1e-12);np.testing.assert_allclose(q[:,1],0.,atol=1e-12)
        d=PlateDefinition(width=120.,height=180.,mesh_size=15.,thickness=.6,plane='XZ',pressure=0.,self_weight_case='Case 1')
        d.material.rho=.0001;r=analyze_plate(d);self.assertEqual(r['recovered_shear']['available'],len(r['cells']))
        self.assertAlmostEqual(r['pressure'],.00006)

    def test_levy_reference_reduces_to_navier_and_checks_torsion_refinement(self):
        points=np.array([[22.5,22.5],[52.5,67.5],[82.5,127.5]])
        expected=navier(points,120.,180.,.2,-1e-7,67.5,terms=320)[2]
        actual=torsional_edge_shear(points,120.,180.,-1e-7,67.5,0.,320)
        np.testing.assert_allclose(actual,expected,atol=2e-10,rtol=1e-4)
        for ratio in (.1,1.,10.):
            a=torsional_edge_shear(points,120.,180.,-1e-7,67.5,ratio*67.5*120.,160)
            b=torsional_edge_shear(points,120.,180.,-1e-7,67.5,ratio*67.5*120.,320)
            self.assertLess(error(a,b,np.ones(len(points),bool)),.0005)

    def test_real_edge_beam_torsion_and_coupled_source_masks(self):
        for ratio in (.1,1.,10.):
            history=[]
            for size in (15.,7.5):
                p=supported_plate(size);mesh=p.surfaces['Plate'];mesh.parameters['height']=180.;mesh.thickness=.6
                p.surface_pressures['Plate']['Case 1']=-1e-7
                D=mesh.material.E*mesh.thickness**3/(12*(1-mesh.material.nu**2));GJ=ratio*D*120.
                material=p.materials[p.default_material];material.shear_modulus=GJ/p.sections[p.default_section].J;material.E=2.6*material.shear_modulus
                r=quiet_solve(p);meta=surface_recovery(r,'Plate');rows=centre_results(r,'Plate')
                self.assertEqual(meta['available'],0);self.assertIn('unvalidated',meta['reason'])
                self.assertTrue(all(row['recovered_Qx'] is None for row in rows))
                # Negative evidence: cell-contact masking alone does not validate
                # a finite-stiffness frame interface, even far from the beam.
                from pynitegui.qt.quad_shear_snapshot import snapshot
                from pynitegui.qt.spatial_surfaces import surface_geometry
                xyz=np.array(surface_geometry(mesh)[2]);cells=np.array(surface_geometry(mesh)[3]);points=xyz[:,:2]-[17.,-31.]
                mapping=r.solver._pynitegui_surfaces['Plate'];quads=[r.solver.quads[n] for n in mapping['elements']]
                moments=np.array([q.moment(combo_name='Service').ravel() for q in quads])
                blocked=points[cells].min(axis=1)[:,1]<size/2
                candidate=snapshot(dict(width=120.,height=180.,family='Quad',thickness=.6,nu=.2,kx_mod=1.,ky_mod=1.,openings=[]),
                    points,cells,moments,np.full(len(cells),-1e-7),blocked=blocked,coupled=True)
                valid=np.array([value is not None for value in candidate['values']])
                xy=points[cells].mean(axis=1);expected=torsional_edge_shear(xy,120.,180.,-1e-7,D,GJ,320)
                history.append(error(values(candidate),expected,valid))
                headers,data=surface_table(p,r,'Plate');self.assertIn('Recovered Qx (kip/in)',headers)
                self.assertTrue(any(value is None for row in data for value in row));json.dumps({'recovery':summary(meta),'rows':data},allow_nan=False)
            self.assertGreater(history[-1],.05)
            self.assertGreater(history[-1],history[0])

    def test_coupled_revision_units_and_unvalidated_loads_supports_fail_closed(self):
        p=supported_plate(15.);p.surfaces['Plate'].thickness=.6
        r=quiet_solve(p);meta=deepcopy(surface_recovery(r,'Plate'));self.assertEqual(meta['available'],0)
        p.unit_system='si_mm';headers,rows=surface_table(p,r,'Plate');self.assertIn('Recovered Qx (N/mm)',headers)
        self.assertEqual(surface_recovery(r,'Plate'),meta)
        from pynitegui.qt.spatial_model import SpatialLoad
        p.loads['Load']=SpatialLoad('Load','A','FZ',1.)
        r=quiet_solve(p);self.assertEqual(surface_recovery(r,'Plate')['available'],0)
        self.assertIn('unvalidated',surface_recovery(r,'Plate')['reason'])
        p.loads.clear();p.surfaces['Plate'].openings=[dict(name='Hole',x_left=40.,y_bott=40.,width=40.,height=40.)]
        r=quiet_solve(p);self.assertEqual(surface_recovery(r,'Plate')['available'],0)
