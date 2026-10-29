"""Nonuniform, load-solved membrane references and explicit drilling limits."""
import unittest

import numpy as np

from coupled_validation import AXES, FACTORS, quiet_solve
from nonuniform_reference import field, energy, spin
from nonuniform_validation import nonuniform_patch, metrics
from pynitegui.qt.analysis import model_signature
from pynitegui.qt.model import Project
from pynitegui.qt.units import UNIT_SYSTEMS


class NonuniformMembraneTests(unittest.TestCase):
    def test_reference_satisfies_equilibrium_constitutive_law_energy_and_three_gauges(self):
        E,nu,H,L,t,C = 2700.,.31,60.,140.,.61,.0027
        xy = np.array(((0.,-H/2),(0.,H/2),(31.,-7.),(91.,13.)))
        for kind in ('bending','mixed'):
            d,s = field(kind,xy,E,nu,H,C)
            derivatives = []
            for axis in (0,1):
                shifted = xy.astype(complex)
                shifted[:,axis] += 1e-20j
                derivatives.append(tuple(value.imag/1e-20 for value in field(kind,shifted,E,nu,H,C)))
            (dx,sx),(dy,sy) = derivatives
            strain = np.column_stack((dx[:,0],dy[:,1],dy[:,0]+dx[:,1]))
            constitutive = E/(1-nu*nu)*np.array(((1.,nu,0.),(nu,1.,0.),(0.,0.,(1-nu)/2)))
            np.testing.assert_allclose(strain @ constitutive.T,s,rtol=1e-12,atol=1e-12)
            np.testing.assert_allclose(sx[:,0]+sy[:,2],0.,atol=1e-14)
            np.testing.assert_allclose(sx[:,2]+sy[:,1],0.,atol=1e-14)
            np.testing.assert_allclose((d[0,0],d[0,1],d[1,0]),0.,atol=1e-14)
            np.testing.assert_allclose((dx[:,1]-dy[:,0])/2,spin(kind,xy,E,C),atol=1e-14)
            # Independent integration of sigma:epsilon/2, including both
            # symmetric shear entries, checks the closed-form energy reference.
            points,weights = np.polynomial.legendre.leggauss(4)
            integral = 0.
            for a,wa in zip(points,weights):
                for b,wb in zip(points,weights):
                    _,stress = field(kind,((a+1)*L/2,b*H/2),E,nu,H,C)
                    tensor = np.array(((stress[0],stress[2]),(stress[2],stress[1])))
                    epsilon = (1+nu)*tensor/E-nu*np.trace(tensor)*np.eye(2)/E
                    integral += wa*wb*L*H*t/8*float(np.sum(tensor*epsilon))
            self.assertAlmostEqual(integral,energy(kind,L,H,t,E,nu,C),places=12)

    def test_consistent_edge_loads_preserve_exact_force_and_end_moment(self):
        for size in (40.,20.,10.):
            for kind in ('bending','mixed'):
                p = nonuniform_patch(kind,size)
                origin = np.asarray(p.surfaces['Patch'].origin)
                totals = {edge:np.zeros(3) for edge in ('Left','Right','Bottom','Top')}
                for load in p.loads.values():
                    force = np.array((load.magnitude if load.direction=='FX' else 0.,load.magnitude if load.direction=='FY' else 0.))
                    x,y = (np.asarray(p.nodes[load.target].coords)-origin)[:2]-np.array((0.,40.))
                    totals[load.name.split('_')[0]] += (*force,x*force[1]-y*force[0])
                if kind=='bending':
                    np.testing.assert_allclose(totals['Left'],(0.,0.,-.001*.8*80**3/12),atol=1e-12)
                    np.testing.assert_allclose(totals['Right'],(0.,0.,.001*.8*80**3/12),atol=1e-12)
                else:
                    self.assertAlmostEqual(totals['Right'][0],.001*.8*120*80)
                    self.assertAlmostEqual(totals['Top'][0],-.001*.8*120*80/2)
                    self.assertAlmostEqual(totals['Bottom'][0],-.001*.8*120*80/2)
                np.testing.assert_allclose(sum(totals.values()),0.,atol=1e-12)

    def test_nonuniform_traction_fields_converge_in_all_planes_and_combinations(self):
        for kind in ('bending','mixed'):
            for plane in AXES:
                history = []
                for size in (40.,20.,10.,5.):
                    p = nonuniform_patch(kind,size,plane)
                    before = p.to_dict()
                    r = quiet_solve(p)
                    self.assertEqual(p.to_dict(),before)
                    record = metrics(p,r,kind)
                    history.append(record)
                    for name,factor in FACTORS.items():
                        with self.subTest(kind=kind,plane=plane,size=size,combination=name):
                            selected = r.for_combination(name)
                            row = record if factor==1. else metrics(p,selected,kind)
                            self.assertTrue(row['equilibrium_passed'])
                            self.assertLess(row['max_reaction'],1e-9)
                            self.assertLess(row['max_normal_displacement_in'],1e-12)
                            self.assertLess(row['max_drilling_rotation_rad'],1e-12)
                            np.testing.assert_allclose(selected.solver.members['Anchor'].f(name),0.,atol=1e-9)
                            if factor:
                                for key in ('displacement_relative_l2','stress_relative_l2','energy_relative_error'):
                                    self.assertAlmostEqual(row[key],record[key],places=8)
                            else:
                                self.assertLess(row['max_displacement_in'],1e-12)
                                self.assertLess(row['max_stress_ksi'],1e-12)
                                self.assertLess(abs(row['strain_energy']),1e-15)
                for key in ('displacement_relative_l2','stress_relative_l2','energy_relative_error'):
                    self.assertTrue(all(a[key]>b[key] for a,b in zip(history,history[1:])),(kind,plane,key,history))
                self.assertLess(history[-1]['displacement_relative_l2'],.005)
                self.assertLess(history[-1]['stress_relative_l2'],.04)
                self.assertLess(history[-1]['energy_relative_error'],.002)

    def test_translated_origin_units_persistence_and_three_in_plane_restraints(self):
        baseline = None
        for kind in ('bending','mixed'):
            for origin in ((19.,-7.,41.),(-137.,211.,-53.)):
                p = nonuniform_patch(kind,10.,'YZ',origin=origin,nu=.3)
                r = quiet_solve(p)
                row = metrics(p,r,kind)
                u,v,normal = AXES['YZ']
                plane_nodes = [node for node in p.nodes.values() if abs(node.coords[normal]-origin[normal])<1e-9]
                self.assertEqual(sum(node.restraints[u]+node.restraints[v] for node in plane_nodes),3)
                for units in UNIT_SYSTEMS:
                    signature = model_signature(p)
                    p.unit_system = units
                    self.assertEqual(model_signature(p),signature)
                    restored = Project.from_dict(p.to_dict())
                    self.assertEqual(restored.to_dict(),p.to_dict())
                vector = [row[key] for key in ('displacement_relative_l2','stress_relative_l2','energy_relative_error','strain_energy')]
                if origin==(19.,-7.,41.):
                    baseline = vector
                else:
                    np.testing.assert_allclose(vector,baseline,rtol=1e-8,atol=1e-12)

    def test_nodal_drilling_is_not_the_nonuniform_continuum_spin(self):
        for kind in ('bending','mixed'):
            p = nonuniform_patch(kind,20.,'XZ')
            r = quiet_solve(p)
            nodes = r.solver._pynitegui_surfaces['Patch']['nodes']
            xy = np.array([[r.solver.nodes[name].X-19.,r.solver.nodes[name].Z-41.-40.] for name in nodes])
            self.assertGreater(float(abs(spin(kind,xy)).max()),1e-5)
            self.assertLess(max(abs(r.displacements[name][4]) for name in nodes),1e-12)
            # A passing membrane stress/displacement field therefore does not
            # validate shell-normal rotations or moment-connected diaphragms.


if __name__=='__main__':
    unittest.main()
