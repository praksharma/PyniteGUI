"""Eligibility, provenance and explicit missing values for recovered centre Q.

Raw element shear is never returned. A fit cannot grant its own eligibility.
All values are canonical kip/in; unavailable cells and off-centre probes are null.
"""
from dataclasses import asdict
import numpy as np
from .quad_shear import recover,FreeEdge

METHOD='compatible_equilibrated_quad_v1'
DESCRIPTION='Smoothed compatible, pressure-equilibrated thin-plate recovery at element centres; not raw Quad shear.'


def unavailable(count,reason):
    return dict(method=METHOD,description=DESCRIPTION,sample='element_centres_only',eligible=False,available=0,total=count,
        reason=reason,values=[None]*count,status=[reason]*count,fit_method=[None]*count,condition=[None]*count,
        constraint_backward_error=[None]*count,moment_fit_relative_residual=[None]*count)


def _scope(definition,polygons,*,coupled=False):
    w,h=definition['width'],definition['height'];short=min(w,h)
    if definition['family']!='Quad':return 'Quad elements only'
    if definition['kx_mod']!=1. or definition['ky_mod']!=1.:return 'Isotropic unmodified bending required'
    if not 0.<=definition['nu']<=.3:return 'Poisson ratio outside the verified 0 to 0.3 range'
    if not 2/3-1e-12<=w/h<=1.5+1e-12:return 'Rectangle aspect ratio outside the verified 2:3 to 3:2 range'
    if definition['thickness']/short>.01+1e-12:return 'Thin-plate recovery requires thickness / short span <= 0.01'
    lengths=np.linalg.norm(np.roll(polygons,-1,axis=1)-polygons,axis=2)
    if lengths.max()>short/8*(1+1e-10):return 'Refine recovery mesh to at least eight cells per short span'
    openings=definition['openings']
    if openings:
        if coupled:return 'Coupled opening recovery is not yet validated'
        if len(openings)!=1:return 'Only the verified single centred opening is supported'
        o=openings[0];a=w/3
        if not (np.isclose(w,h) and np.allclose([o['width'],o['height'],o['x_left'],o['y_bott']],[a,a,a,a],rtol=1e-10,atol=1e-10)):
            return 'Opening recovery requires the centred one-third square benchmark geometry'
        if not np.isclose(definition['nu'],.2):return 'Opening recovery is verified for nu=0.2'
        if definition['thickness']/short>.005+1e-12:return 'Opening recovery requires thickness / span <= 0.005'
        if lengths.max()>short/24*(1+1e-10):return 'Refine opening mesh to at least 24 cells per span'
        for axis in (0,1):
            differences=np.diff(np.unique(polygons[:,:,axis]))
            if not np.allclose(differences,differences[0],rtol=1e-9,atol=1e-10):return 'Opening recovery requires a uniform Cartesian grid'
    return None


def snapshot(definition,points,cells,moments,pressures,*,free_edges=(),blocked=None,coupled=False):
    polygons=np.asarray(points)[np.asarray(cells)];count=len(polygons)
    reason=_scope(definition,polygons,coupled=coupled)
    if reason:return unavailable(count,reason)
    blocked=np.zeros(count,bool) if blocked is None else np.asarray(blocked,bool)
    if blocked.shape!=(count,):raise ValueError('Recovery source mask does not match the solved cells.')
    rectangles=np.column_stack((polygons.min(axis=1),polygons.max(axis=1)))
    regions=['pressure_only' if not flag else f'blocked_{i}' for i,flag in enumerate(blocked)]
    try:data=recover(rectangles,moments,regions,pressures,definition['nu'],free_edges)
    except ValueError as error:return unavailable(count,'Unsupported recovery geometry: '+str(error))
    allowed=data['valid'].copy();status=data['status'].tolist()
    for i,flag in enumerate(blocked):
        if flag:allowed[i]=False;status[i]='load_or_frame_transfer_zone'
    corners=[]
    for o in definition['openings']:
        corners.extend([(o['x_left']+x,o['y_bott']+y) for x in (0,o['width']) for y in (0,o['height'])])
    centres=polygons.mean(axis=1)
    for i in range(count):
        if not allowed[i]:continue
        if corners:
            clearance=max(min(definition['width'],definition['height'])/12,2.5*np.max(np.linalg.norm(np.roll(polygons[i],-1,axis=0)-polygons[i],axis=1)))
            if min(np.linalg.norm(centres[i]-corner) for corner in corners)<clearance-1e-10:
                allowed[i]=False;status[i]='reentrant_corner_clearance';continue
            patch=rectangles[data['stencils'][i]];low,high=patch[:,:2].min(axis=0),patch[:,2:].max(axis=0)
            if any(np.all(np.asarray(corner)>=low-1e-10) and np.all(np.asarray(corner)<=high+1e-10) for corner in corners):
                allowed[i]=False;status[i]='corner_in_recovery_stencil';continue
        status[i]='available'
    values=[data['shear'][i].tolist() if allowed[i] else None for i in range(count)]
    if any(not np.isfinite(value).all() for value in values if value is not None):raise ValueError('Nonfinite accepted recovered shear.')
    def masked(key):return [float(data[key][i]) if allowed[i] else None for i in range(count)]
    return dict(method=METHOD,description=DESCRIPTION,sample='element_centres_only',eligible=True,available=int(allowed.sum()),total=count,
        reason='Available only in unmasked pressure-only patches',values=values,status=status,
        fit_method=[str(data['method'][i]) if allowed[i] else None for i in range(count)],condition=masked('condition'),
        constraint_backward_error=masked('constraint_backward_error'),moment_fit_relative_residual=masked('moment_fit_relative_residual'),
        free_edges=[asdict(e) for e in free_edges],thin_ratio=definition['thickness']/min(definition['width'],definition['height']))


def plate_recovery(definition,points,cells,moments,pressures):
    count=len(cells);edges=definition.edges
    simple=all(value=='Simply supported' for value in edges.values())
    cantilever=(not definition.openings and definition.material.nu==0. and list(edges.values()).count('Clamped')==1
                and list(edges.values()).count('Free')==3)
    if not simple and not cantilever:return unavailable(count,'Recovered shear requires simply supported edges or a verified nu=0 cantilever')
    if cantilever and np.ptp(pressures)>1e-10*max(np.max(abs(pressures)),np.finfo(float).tiny):
        return unavailable(count,'Cantilever recovery requires uniform transverse pressure')
    if definition.openings and np.ptp(pressures)>1e-10*max(np.max(abs(pressures)),np.finfo(float).tiny):
        return unavailable(count,'Opening recovery requires uniform transverse pressure')
    free=[];w,h=definition.width,definition.height
    for name,edge in zip(('Left','Right','Bottom','Top'),(FreeEdge(0,0.,0.,h),FreeEdge(0,w,0.,h),FreeEdge(1,0.,0.,w),FreeEdge(1,h,0.,w))):
        if edges[name]=='Free':free.append(edge)
    for o in definition.openings:
        x,y,a,b=(o[k] for k in ('x_left','y_bott','width','height'))
        free.extend((FreeEdge(0,x,y,y+b),FreeEdge(0,x+a,y,y+b),FreeEdge(1,y,x,x+a),FreeEdge(1,y+b,x,x+a)))
    info=dict(width=w,height=h,family=definition.element_type,thickness=definition.thickness,nu=definition.material.nu,
        kx_mod=definition.kx_mod,ky_mod=definition.ky_mod,openings=definition.openings)
    return snapshot(info,points,cells,moments,pressures,free_edges=free)


def probe(metadata,index,xi=0.,eta=0.):
    if xi!=0. or eta!=0.:return dict(recovered_Qx=None,recovered_Qy=None,shear_status='centre_only',shear_fit_method=None)
    value=metadata['values'][index]
    return dict(recovered_Qx=None if value is None else value[0],recovered_Qy=None if value is None else value[1],shear_status=metadata['status'][index],shear_fit_method=metadata['fit_method'][index])


def summary(metadata):
    from collections import Counter
    return {**{key:metadata[key] for key in ('method','description','sample','eligible','available','total','reason')},'status_counts':dict(Counter(metadata['status']))}

