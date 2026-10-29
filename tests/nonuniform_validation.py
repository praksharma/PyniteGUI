"""Production-path membrane solves with consistent nonuniform edge tractions.

Only three zero in-plane point restraints remove rigid motions. The existing
off-plane anchor is at a zero-motion corner; its force must stay zero. All
interior shell nodes and result probes use the unchanged production assembler.
"""
import numpy as np

from coupled_validation import AXES, FACTORS, membrane_patch
from nonuniform_reference import field, energy
from pynitegui.qt.equilibrium import check_equilibrium
from pynitegui.qt.spatial_model import SpatialLoad, RESTRAINT_FIELDS
from pynitegui.qt.surface_results import inspect_surface


def nonuniform_patch(kind, size=20., plane='XY', origin=(19.,-7.,41.), nu=.2):
    p = membrane_patch(size,plane,strain=(0.,0.,0.),nu=nu)
    mesh = p.surfaces['Patch']
    u,v,normal = AXES[plane]
    old = np.asarray(mesh.origin)
    offset = np.asarray(origin)-old
    for node in p.nodes.values():
        node.x, node.y, node.z = (np.asarray(node.coords)+offset).tolist()
    mesh.origin = list(origin)
    origin = np.asarray(origin)
    boundary = {name: node for name,node in p.nodes.items() if abs(node.coords[normal]-origin[normal])<1e-9}
    for node in boundary.values():
        node.support = 'custom'
        for key in RESTRAINT_FIELDS:
            setattr(node,key,False)
        xy = (np.asarray(node.coords)-origin)[[u,v]]
        if xy[0]==0. and xy[1] in (0.,80.):
            setattr(node,RESTRAINT_FIELDS[u],True)
            if xy[1]==0.:
                setattr(node,RESTRAINT_FIELDS[v],True)
    p.loads.clear()
    for edge,axis,span,other in (('Left',u,0.,v),('Right',u,120.,v),('Bottom',v,0.,u),('Top',v,80.,u)):
        names = sorted((name for name,node in boundary.items() if abs(node.coords[axis]-origin[axis]-span)<1e-9),
                       key=lambda name:boundary[name].coords[other])
        outward = -1. if edge in ('Left','Bottom') else 1.
        for segment,(a,b) in enumerate(zip(names,names[1:])):
            points = np.array([boundary[name].coords for name in (a,b)])
            xy = (points-origin)[:,[u,v]]-np.array((0.,40.))
            _,stress = field(kind,xy,nu=nu)
            traction = stress[:,[0,2] if axis==u else [2,1]]*outward
            length = points[1,other]-points[0,other]
            # Exact integral of linear edge shape functions times linear
            # traction. Equal lumping would lose the end moment in bending.
            forces = mesh.thickness*length/6*np.array((2*traction[0]+traction[1],traction[0]+2*traction[1]))
            for end,(name,force) in enumerate(zip((a,b),forces)):
                for direction,magnitude in zip((u,v),force):
                    if magnitude:
                        key = f'{edge}_{segment}_{end}_{direction}'
                        p.loads[key] = SpatialLoad(key,name,'F'+'XYZ'[direction],float(magnitude))
    p.validate()
    return p


def metrics(project, result, kind):
    mesh = project.surfaces['Patch']
    u,v,normal = AXES[mesh.plane]
    origin = np.asarray(mesh.origin)
    mapping = result.solver._pynitegui_surfaces['Patch']
    factor = FACTORS[result.combination]
    displacement_error = displacement_norm = stress_error = stress_norm = 0.
    max_displacement = max_stress = 0.
    # Three-point quadrature also integrates squared quadratic reference
    # displacements exactly; the element's usual 2x2 rule would underintegrate
    # that error even though it suffices for the bilinear stress field.
    points,weights = np.polynomial.legendre.leggauss(3)
    for name in mapping['elements']:
        quad = result.solver.quads[name]
        nodes = (quad.i_node,quad.j_node,quad.m_node,quad.n_node)
        xyz = np.array([(node.X,node.Y,node.Z) for node in nodes])
        area = float(np.linalg.norm(np.cross(xyz[1]-xyz[0],xyz[3]-xyz[0])))
        nodal = np.array([result.displacements[node.name][:3] for node in nodes])[:,[u,v]]
        for xi,eta,weight in ((a,b,wa*wb*area/4) for a,wa in zip(points,weights) for b,wb in zip(points,weights)):
            shape = np.array(((1-xi)*(1-eta),(1+xi)*(1-eta),(1+xi)*(1+eta),(1-xi)*(1+eta)))/4
            row = inspect_surface(result,'Patch',name,xi,eta)
            xy = (np.asarray(row['position'])-origin)[[u,v]]-np.array((0.,40.))
            expected_d,expected_s = field(kind,xy,nu=mesh.material.nu)
            expected_d,expected_s = expected_d*factor,expected_s*factor
            actual_d = shape @ nodal
            actual_s = np.array([row[key] for key in ('Sx','Sy','Txy')])
            displacement_error += weight*float(np.sum((actual_d-expected_d)**2))
            displacement_norm += weight*float(np.sum(expected_d**2))
            # Frobenius norm of the symmetric in-plane stress tensor: the
            # off-diagonal shear appears twice, unlike displacement components.
            stress_error += weight*float(np.sum((actual_s-expected_s)**2*np.array((1.,1.,2.))))
            stress_norm += weight*float(np.sum(expected_s**2*np.array((1.,1.,2.))))
            max_displacement = max(max_displacement,float(abs(actual_d).max()))
            max_stress = max(max_stress,float(abs(actual_s).max()))
    work = sum(load.magnitude*factor*result.displacements[load.target]['XYZ'.index(load.direction[-1])] for load in project.loads.values())
    reference_energy = factor**2*energy(kind,nu=mesh.material.nu)
    nodes = [result.displacements[name] for name in mapping['nodes']]
    return dict(elements=len(mapping['elements']),
        displacement_relative_l2=(displacement_error/displacement_norm)**.5 if displacement_norm else displacement_error**.5,
        stress_relative_l2=(stress_error/stress_norm)**.5 if stress_norm else stress_error**.5,
        strain_energy=float(work/2), reference_energy=reference_energy,
        energy_relative_error=abs(work/(2*reference_energy)-1) if reference_energy else abs(work/2),
        max_displacement_in=max_displacement,max_stress_ksi=max_stress,
        max_normal_displacement_in=float(max(abs(row[normal]) for row in nodes)),
        max_drilling_rotation_rad=float(max(abs(row[3+normal]) for row in nodes)),
        max_reaction=float(max(abs(value) for row in result.reactions.values() for value in row)),
        equilibrium_passed=check_equilibrium(project,result).passed)
