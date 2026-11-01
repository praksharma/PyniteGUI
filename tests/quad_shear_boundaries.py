"""Test-only one-sided Quad moment patches; no application imports this recovery.

A stencil is nine contiguous rectangular cells in one constitutive region.
Missing cells, excessive grading, jumps and rank loss never receive a value.
This studies differentiation of solved moments, not a change to the FE solve.
"""
from functools import lru_cache
import numpy as np
from pynitegui.qt.plate_model import PlateDefinition, build_plate, plate_equilibrium
from pynitegui.qt.model import Material
from plate_reference import navier, OpeningRitz

FACTORS = {'Service': 1., 'Reverse': -2., 'Zero': 0.}
CASES = ('boundary', 'graded', 'coupled_boundary', 'coupled_graded', 'opening', 'stiffness_x', 'stiffness_y')
SIZES = {'opening': (10., 5., 4.)}


def recover(cells, moments, regions):
    """Return shear, validity, stencil indices and status, in common local axes.

    cells are [x0,y0,x1,y1]; regions identify constitutive data AND surface owner.
    Complete 3x3 Cartesian stencils must contain the target; nearest points alone
    cannot establish connectivity. Fit complete quadratic tensors in independently
    scaled local coordinates; derive Qx=Mx,x+Mxy,y, Qy=Mxy,x+My,y.
    """
    cells, moments = np.asarray(cells, float), np.asarray(moments, float)
    count = len(cells)
    if (cells.shape != (count,4) or moments.shape != (count,3) or not count
            or len(regions) != count or not all(isinstance(r,str) and r for r in regions)
            or not np.isfinite(cells).all() or not np.isfinite(moments).all()
            or np.any(cells[:,2:] <= cells[:,:2])):
        raise ValueError('Finite positive rectangles, three moments and explicit region IDs are required.')
    # Shared coupled boundary coordinates can differ by a few floating-point
    # ulps after interpolation/merging. Canonicalize only roundoff, never the
    # application's much larger modelling tolerance or a physical narrow gap.
    cells=cells.copy()
    for dimension in (0,1):
        columns=[dimension,dimension+2]
        values=np.unique(cells[:,columns]);tolerance=64*np.finfo(float).eps*max(1.,max(abs(values)))
        representative=values[0];mapping={representative:representative}
        for value in values[1:]:
            if value-representative>tolerance:representative=value
            mapping[value]=representative
        cells[:,columns]=np.vectorize(mapping.__getitem__)(cells[:,columns])
    if np.any(cells[:,2:]<=cells[:,:2]):raise ValueError('Cell geometry is unresolved at floating-point precision.')
    axes = [np.unique(cells[:,[d,d+2]]) for d in (0,1)]
    lower = [np.searchsorted(axes[d], cells[:,d]) for d in (0,1)]
    upper = [np.searchsorted(axes[d], cells[:,d+2]) for d in (0,1)]
    if any(np.any(b-a != 1) for a,b in zip(lower,upper)):
        raise ValueError('Only a conforming Cartesian rectangular cell grid is supported.')
    lookup = {key:i for i,key in enumerate(zip(*lower))}
    if len(lookup) != count:raise ValueError('Duplicate/overlapping cells are not a valid patch.')
    points = (cells[:,:2]+cells[:,2:])/2
    output = np.full((count,2),np.nan);valid = np.zeros(count,bool)
    stencils = np.full((count,9),-1,int);status = np.full(count,'incomplete_or_mixed_region',object)
    for i,(ix,iy) in enumerate(zip(*lower)):
        candidates=[]
        for x0 in range(max(0,ix-2),min(ix,len(axes[0])-4)+1):
            for y0 in range(max(0,iy-2),min(iy,len(axes[1])-4)+1):
                keys=[(x,y) for y in range(y0,y0+3) for x in range(x0,x0+3)]
                if any(key not in lookup for key in keys):continue
                indices=[lookup[key] for key in keys]
                if any(regions[j] != regions[i] for j in indices):continue
                widths=[np.diff(axis[start:start+4]) for axis,start in zip(axes,(x0,y0))]
                if any(max(w)/min(w)>4. for w in widths):
                    status[i]='excessive_grading';continue
                scale=np.ptp(points[indices],axis=0);xy=(points[indices]-points[i])/scale
                x,y=xy.T;design=np.column_stack((np.ones(9),x,y,x*x,x*y,y*y))
                condition=np.linalg.cond(design)
                if not np.isfinite(condition) or condition>1e6:
                    status[i]='ill_conditioned';continue
                # Prefer a centred patch; break ties by actual conditioning.
                distance=np.linalg.norm(xy.mean(axis=0))
                candidates.append((distance,condition,indices,scale,design,ix==x0+1 and iy==y0+1))
        if not candidates:continue
        _,_,indices,scale,design,centered=min(candidates,key=lambda item:item[:2])
        coefficients=np.linalg.lstsq(design,moments[indices],rcond=None)[0]
        dx,dy=coefficients[1]/scale[0],coefficients[2]/scale[1]
        output[i]=[dx[0]+dy[2],dx[2]+dy[1]];valid[i]=True;stencils[i]=indices
        status[i]='centered' if centered else 'one_sided'
    return dict(shear=output,valid=valid,stencils=stencils,status=status)


def gather(elements, combination):
    axes=np.asarray(elements[0].T())[:3,:3]
    origin=np.array([(getattr(elements[0].i_node,d)) for d in ('X','Y','Z')])
    cells=[];moments=[];raw=[];regions=[]
    for element in elements:
        np.testing.assert_allclose(element.T()[:3,:3],axes,atol=1e-12)
        nodes=(element.i_node,element.j_node,element.m_node,element.n_node)
        polygon=(np.array([(n.X,n.Y,n.Z) for n in nodes])-origin)@axes.T
        xy=polygon[:,:2];low,high=xy.min(axis=0),xy.max(axis=0)
        np.testing.assert_allclose(xy,[[*low],[high[0],low[1]],[*high],[low[0],high[1]]],atol=1e-9)
        cells.append([*low,*high]);moments.append(element.moment(combo_name=combination).ravel())
        raw.append(element.shear(combo_name=combination).ravel())
        regions.append(repr((element.E,element.nu,element.t,element.kx_mod,element.ky_mod)))
    cells=np.asarray(cells);moments=np.asarray(moments)
    return dict(cells=cells,points=(cells[:,:2]+cells[:,2:])/2,moments=moments,raw=np.array(raw),regions=regions,
                **recover(cells,moments,regions))


@lru_cache(maxsize=48)
def solve_case(case,size,plane='XY'):
    if case not in CASES:raise ValueError('Unknown boundary benchmark.')
    width,height=(120.,120.) if case=='opening' else (120.,180.)
    nu=0. if case.startswith('stiffness') else .2
    definition=PlateDefinition(width=width,height=height,thickness=.6,mesh_size=size,pressure=-1e-7,
        plane=plane,origin=[17.,-31.,49.],material=Material('Reference',3600.,nu,0.),
        combinations={name:{'Case 1':factor} for name,factor in FACTORS.items()})
    if case.endswith('graded'):definition.x_control=[37.,76.];definition.y_control=[49.,122.]
    if case=='opening':definition.openings=[dict(name='Hole',x_left=40.,y_bott=40.,width=40.,height=40.)]
    if case.startswith('stiffness'):
        direction=0 if case.endswith('x') else 1
        definition.edges={edge:'Clamped' if edge==('Left','Bottom')[direction] else 'Free' for edge in definition.edges}
        if direction==0:definition.x_control=[60.]
        else:definition.y_control=[90.]
    if case.startswith('coupled_'):
        from test_surface_results import supported_plate,quiet_solve
        from pynitegui.qt.equilibrium import check_equilibrium
        project=supported_plate(size,plane);project.materials[project.default_material].E=1e-6
        mesh=project.surfaces['Plate'];mesh.parameters['height']=height;mesh.thickness=.6
        mesh.material=definition.material;mesh.x_control=definition.x_control;mesh.y_control=definition.y_control
        project.surface_pressures['Plate']['Case 1']=-1e-7
        for name,factor in FACTORS.items():project.set_combination(name,{'Case 1':factor},name if name in project.combinations else None)
        result=quiet_solve(project);model=result.solver
        elements=[model.quads[name] for name in model._pynitegui_surfaces['Plate']['elements']]
        if not all(check_equilibrium(project,result.for_combination(name)).passed for name in FACTORS):
            raise AssertionError('Coupled force/moment equilibrium failed.')
    else:
        model=build_plate(definition);elements=list(model.quads.values())
    if case.startswith('stiffness'):
        model.add_material('Stiffer',14400.,6000.,0.,0.)
        axes=elements[0].T()[:3,:3];first=elements[0].i_node
        origin=np.array([first.X,first.Y,first.Z]);threshold=(width,height)[direction]/2
        for element in elements:
            center=np.mean([[n.X,n.Y,n.Z] for n in (element.i_node,element.j_node,element.m_node,element.n_node)],axis=0)
            if ((center-origin)@axes.T)[direction]>threshold:
                element.E=model.materials['Stiffer'].E;element.nu=0.;element.t=.9
    if not case.startswith('coupled_'):model.analyze_linear(check_stability=True,check_statics=False)
    samples={name:gather(elements,name) for name in FACTORS}
    if not case.startswith('coupled_'):
        for name in FACTORS:plate_equilibrium(model,definition,name)
    sample=samples['Service'];points=sample['points']
    if case.endswith(('boundary','graded')):
        rigidity=3600.*.6**3/(12*(1-nu**2))
        reference=navier(points,width,height,nu,definition.pressure,rigidity,terms=320)[2]
    elif case.startswith('stiffness'):
        reference=np.zeros((len(points),2));reference[:,direction]=definition.pressure*((width,height)[direction]-points[:,direction])
    else:reference=None
    for name,factor in FACTORS.items():
        sample=samples[name];sample['reference']=reference*factor if reference is not None else None
        sample['pressure']=definition.pressure*factor
        cells=sample['cells'];sample['areas']=np.prod(cells[:,2:]-cells[:,:2],axis=1)
        sample['outer']=np.any(np.isclose(cells[:,:2],0.)|np.isclose(cells[:,2:],[width,height]),axis=1)
    return samples


def relative_l2(actual,expected,areas,selected):
    weights=np.sqrt(areas[selected,None]);scale=np.linalg.norm(weights*expected[selected])
    return float(np.linalg.norm(weights*(actual[selected]-expected[selected]))/scale) if scale else None


def opening_mean_shear(sample,box):
    cells=sample['cells'];x0,x1,y0,y1=box
    # Integrate the piecewise-constant recovered cell values over the exact
    # material patch, including clipped cells on uneven/nonaligned meshes.
    low=np.maximum(cells[:,:2],[x0,y0]);high=np.minimum(cells[:,2:],[x1,y1])
    overlap=np.prod(np.maximum(high-low,0.),axis=1);selected=overlap>1e-10
    if not selected.any() or not sample['valid'][selected].all():raise ValueError('Opening comparison needs valid material cells.')
    areas=overlap[selected]
    if not np.isclose(sum(areas),(x1-x0)*(y1-y0)):raise ValueError('Material patch is not completely covered by the mesh.')
    return np.average(sample['shear'][selected],axis=0,weights=areas)
