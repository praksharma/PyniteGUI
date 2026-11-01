"""Compatible, load-equilibrated thin-plate centre shear recovery.

Use solved cell-mean moments, prescribed affine transverse pressure and explicitly
identified straight free edges. Fit a quintic potential U=D*w, with no rigid
terms: Mx=-(Uxx+nu*Uyy), My=-(Uyy+nu*Uxx), Mxy=-(1-nu)*Uxy.
Enforce laplacian(laplacian(U))=q and, on a true free straight edge,
Mnn=0 and Vn=Qn+dMnt/dt=0. Q=-grad(laplacian(U)).

No FE solve/reference solution is called. Complete same-region rectangular
patches are mandatory. Geometry/fit availability is not an accuracy certificate.
Production callers must apply the snapshot eligibility and source masks.
"""
from dataclasses import dataclass
from functools import lru_cache
from math import factorial
import numpy as np
from scipy.linalg import null_space

POWERS=tuple((total-b,b) for total in range(2,6) for b in range(total+1))


@dataclass(frozen=True)
class FreeEdge:
    axis: int
    coordinate: float
    start: float
    end: float


def _basis(x,y,dx=0,dy=0,powers=POWERS):
    x,y=np.broadcast_arrays(x,y)
    return np.array([np.zeros_like(x) if a<dx or b<dy else
        factorial(a)/factorial(a-dx)*factorial(b)/factorial(b-dy)*x**(a-dx)*y**(b-dy) for a,b in powers]).T


def _geometry(cells):
    cells=np.asarray(cells,float)
    if cells.ndim!=2 or cells.shape[1]!=4 or not len(cells) or not np.isfinite(cells).all() or np.any(cells[:,2:]<=cells[:,:2]):
        raise ValueError('Finite positive Cartesian rectangles are required.')
    cells=cells.copy();axes=[]
    for d in (0,1):
        columns=[d,d+2];values=np.unique(cells[:,columns]);tolerance=64*np.finfo(float).eps*max(1.,max(abs(values)))
        representative=values[0];mapping={representative:representative}
        for value in values[1:]:
            if value-representative>tolerance:representative=value
            mapping[value]=representative
        cells[:,columns]=np.vectorize(mapping.__getitem__)(cells[:,columns]);axes.append(np.unique(cells[:,columns]))
    if np.any(cells[:,2:]<=cells[:,:2]):raise ValueError('Cell geometry is unresolved at floating-point precision.')
    lower=np.column_stack([np.searchsorted(axes[d],cells[:,d]) for d in (0,1)])
    upper=np.column_stack([np.searchsorted(axes[d],cells[:,d+2]) for d in (0,1)])
    if np.any(upper-lower!=1):raise ValueError('A conforming Cartesian rectangular grid is required.')
    lookup={tuple(key):i for i,key in enumerate(lower)}
    if len(lookup)!=len(cells):raise ValueError('Duplicate/overlapping cells are not a valid recovery patch.')
    return cells,axes,lower,lookup


def _edges(edges,cells,axes,lookup):
    """A free edge must cover whole exposed cell faces, never an interior line."""
    result=[]
    for edge in edges:
        if (not isinstance(edge,FreeEdge) or type(edge.axis) is not int or edge.axis not in (0,1)
                or any(isinstance(v,bool) or not isinstance(v,(int,float)) or not np.isfinite(v) for v in (edge.coordinate,edge.start,edge.end))
                or edge.end<=edge.start):raise ValueError('Explicit finite straight FreeEdge definitions are required.')
        d=edge.axis;t=1-d;normal=axes[d];tangent=axes[t]
        tolerance=64*np.finfo(float).eps*max(1.,max(abs(cells.ravel())))
        def index(axis,value):
            nearest=int(np.argmin(abs(axis-value)))
            if abs(axis[nearest]-value)>tolerance:raise ValueError('Free edges must fit exposed complete cell faces.')
            return nearest
        boundary=index(normal,edge.coordinate);start=index(tangent,edge.start);end=index(tangent,edge.end)
        if end<=start:raise ValueError('Free edge is unresolved at floating-point precision.')
        for j in range(start,end):
            keys=((boundary-1,j),(boundary,j)) if d==0 else ((j,boundary-1),(j,boundary))
            if sum(key in lookup for key in keys)!=1:raise ValueError('Free edge is missing material or crosses an interior/stiffness interface.')
        result.append(FreeEdge(d,float(normal[boundary]),float(tangent[start]),float(tangent[end])))
    if len(set(result))!=len(result):raise ValueError('Duplicate free-edge assignments are not allowed.')
    return result


@lru_cache(maxsize=1024)
def _operator(bounds,sx,sy,nu,boundaries,degree=5):
    powers=tuple((a,b) for a,b in POWERS if a+b<=degree)
    bounds=np.array(bounds).reshape(9,4);area=sx*sy;k=len(powers)
    basis=lambda x,y,dx,dy:_basis(x,y,dx,dy,powers)
    # The element-centre value equals the mean of its own bilinear moment
    # field. Match that mean, not the point value of a different smooth field.
    offset=1/np.sqrt(3.)
    x=np.array([(bounds[:,0]+bounds[:,2]+a*offset*(bounds[:,2]-bounds[:,0]))/2 for a in (-1,1) for b in (-1,1)]).T
    y=np.array([(bounds[:,1]+bounds[:,3]+b*offset*(bounds[:,3]-bounds[:,1]))/2 for a in (-1,1) for b in (-1,1)]).T
    def mean_basis(dx,dy):return basis(x.ravel(),y.ravel(),dx,dy).reshape(9,4,k).mean(axis=1)
    matrix=np.vstack((-( mean_basis(2,0)/sx**2+nu*mean_basis(0,2)/sy**2)*area,
                      -( mean_basis(0,2)/sy**2+nu*mean_basis(2,0)/sx**2)*area,
                      -(1-nu)*mean_basis(1,1)))
    rows=[]
    pressure_terms=((0,0),(1,0),(0,1)) if degree==5 else ((0,0),)
    for r,s in pressure_terms:
        row=np.zeros(k)
        for j,(a,b) in enumerate(powers):
            if (a-4,b)==(r,s):row[j]+=a*(a-1)*(a-2)*(a-3)/sx**4
            if (a-2,b-2)==(r,s):row[j]+=2*a*(a-1)*b*(b-1)/(sx*sy)**2
            if (a,b-4)==(r,s):row[j]+=b*(b-1)*(b-2)*(b-3)/sy**4
        rows.append(row*area)
    for axis,coordinate in boundaries:
        for derivative in (2,3):
            for power in range(degree+1-derivative):
                row=np.zeros(k)
                for j,(a,b) in enumerate(powers):
                    n,t=(a,b) if axis==0 else (b,a)
                    normal,tangent=(sx,sy) if axis==0 else (sy,sx)
                    if n>=derivative and t==power:
                        row[j]-=area*factorial(n)/factorial(n-derivative)*coordinate**(n-derivative)/normal**derivative
                    if t>=2 and n>=derivative-2 and t-2==power:
                        multiplier=nu if derivative==2 else 2-nu
                        row[j]-=area*multiplier*factorial(n)/factorial(n-derivative+2)*t*(t-1)*coordinate**(n-derivative+2)/(normal**(derivative-2)*tangent**2)
                rows.append(row)
    constraints=np.array(rows);norms=np.linalg.norm(constraints,axis=1)
    normalized=constraints/norms[:,None];particular=np.linalg.lstsq(normalized,np.eye(len(rows)),rcond=None)[0]
    z=null_space(normalized)
    if not z.shape[1]:return None
    reduced=matrix@z
    condition=float(np.linalg.cond(reduced))
    if not np.isfinite(condition) or condition>1e6 or np.linalg.matrix_rank(reduced)!=reduced.shape[1]:return None
    moment_map=z@np.linalg.pinv(reduced)
    load_map=(np.eye(k)-moment_map@matrix)@particular/norms[None,:]
    zero=np.zeros(1)
    shear=-area*np.vstack((basis(zero,zero,3,0)/sx**3+basis(zero,zero,1,2)/(sx*sy**2),
                           basis(zero,zero,0,3)/sy**3+basis(zero,zero,2,1)/(sx**2*sy)))
    return matrix,constraints,moment_map,load_map[:,:len(pressure_terms)],shear,condition


def recover(cells,moments,regions,pressures,poisson,free_edges=()):
    """Return smoothed Q, availability, stencils and fit/boundary diagnostics.

    All quantities are canonical inch-kip in one common local coordinate system.
    Region IDs must include surface owner and constitutive data; caller supplies
    the actual affine pressure and only genuinely free straight boundary faces.
    This does not support concentrated loads, line/member transfer, orthotropic
    or thick-plate recovery. Missing values stay NaN, never fabricated zeros.
    """
    cells,axes,lower,lookup=_geometry(cells);count=len(cells)
    moments=np.asarray(moments,float);pressures=np.asarray(pressures,float)
    poisson=np.full(count,poisson,dtype=float) if np.ndim(poisson)==0 else np.asarray(poisson,float)
    if (moments.shape!=(count,3) or pressures.shape!=(count,) or poisson.shape!=(count,)
            or not np.isfinite(moments).all() or not np.isfinite(pressures).all() or not np.isfinite(poisson).all()
            or np.any((poisson<=-1)|(poisson>=.5)) or len(regions)!=count
            or not all(isinstance(r,str) and r for r in regions)):raise ValueError('Finite moments, cell pressures, isotropic nu and explicit region IDs are required.')
    for region in set(regions):
        selected=np.array([r==region for r in regions])
        if np.ptp(poisson[selected])>64*np.finfo(float).eps:raise ValueError('One region ID cannot conceal different constitutive data.')
    edges=_edges(free_edges,cells,axes,lookup);points=(cells[:,:2]+cells[:,2:])/2
    output=np.full((count,2),np.nan);valid=np.zeros(count,bool);stencils=np.full((count,9),-1,int)
    status=np.full(count,'incomplete_or_mixed_region',object);conditions=np.full(count,np.nan)
    methods=np.full(count,'missing',object)
    fit_residual=np.full(count,np.nan);boundary_count=np.zeros(count,int);constraint_error=np.full(count,np.nan)
    tolerance=64*np.finfo(float).eps*max(1.,max(abs(cells.ravel())))
    for i,(ix,iy) in enumerate(lower):
        candidates=[]
        for x0 in range(max(0,ix-2),min(ix,len(axes[0])-4)+1):
            for y0 in range(max(0,iy-2),min(iy,len(axes[1])-4)+1):
                keys=[(x,y) for y in range(y0,y0+3) for x in range(x0,x0+3)]
                if any(key not in lookup for key in keys):continue
                ids=[lookup[key] for key in keys]
                if any(regions[j]!=regions[i] for j in ids):continue
                widths=[np.diff(axis[start:start+4]) for axis,start in zip(axes,(x0,y0))]
                if any(max(w)/min(w)>4. for w in widths):status[i]='excessive_grading';continue
                scale=np.ptp(points[ids],axis=0);xy=(points[ids]-points[i])/scale
                pressure_design=np.column_stack((np.ones(9),xy))
                load=np.linalg.lstsq(pressure_design,pressures[ids],rcond=None)[0]
                error=np.max(abs(pressure_design@load-pressures[ids]))
                if error>1e-10*max(np.max(abs(pressures[ids])),np.finfo(float).tiny):status[i]='non_affine_pressure';continue
                box=np.r_[cells[ids,:2].min(axis=0),cells[ids,2:].max(axis=0)]
                boundaries=[]
                for edge in edges:
                    d=edge.axis;t=1-d
                    if ((abs(box[d]-edge.coordinate)<=tolerance or abs(box[d+2]-edge.coordinate)<=tolerance)
                            and box[t]>=edge.start-tolerance and box[t+2]<=edge.end+tolerance):
                        boundaries.append((d,(edge.coordinate-points[i,d])/scale[d]))
                normalized_bounds=(cells[ids]-np.tile(points[i],2))/np.tile(scale,2)
                key=tuple(np.round(normalized_bounds.ravel(),13)),float(scale[0]),float(scale[1]),float(poisson[i]),tuple(sorted(boundaries))
                operator=_operator(*key)
                if operator is None:status[i]='ill_conditioned';continue
                candidates.append((np.linalg.norm(xy.mean(axis=0)),operator[-1],ids,load,operator,len(boundaries),ix==x0+1 and iy==y0+1,key))
        if not candidates:continue
        _,condition,ids,load,operator,boundaries,centered,key=min(candidates,key=lambda row:row[:2])
        observed=moments[ids].T.ravel();method='equilibrated_quintic'
        # Preserve already exact compatible quadratic moment fields. FE moment
        # averages can have a constant discretization bias at a free boundary;
        # forcing that bias to zero must not spoil their exact shear derivative.
        # This decision uses only polynomial reproduction error, not a reference.
        if np.linalg.norm(load[1:])<=1e-10*max(np.max(abs(pressures[ids])),np.finfo(float).tiny):
            polynomial=_operator(*key[:4],(),degree=4)
            if polynomial is not None:
                a,c,m,l,q,condition_low=polynomial
                trial=m@observed+l@load[:1]
                variation=float(np.max(np.ptp(moments[ids],axis=0)))
                tolerance_poly=1e-8*variation+64*np.finfo(float).eps*max(np.max(abs(observed)),np.finfo(float).tiny)
                if np.max(abs(a@trial-observed))<=tolerance_poly:
                    operator=polynomial;condition=condition_low;boundaries=0;method='polynomial_exact'
        matrix,constraints,moment_map,load_map,shear,_=operator
        terms=load_map.shape[1];coefficients=moment_map@observed+load_map@load[:terms]
        rhs=np.r_[load[:terms],np.zeros(len(constraints)-terms)];closure=constraints@coefficients-rhs
        # A normwise term accounts for roundoff in exactly zero components
        # (e.g. My on a nu=0 strip); no physical solve tolerance is changed.
        bound=abs(constraints)@abs(coefficients)+abs(rhs)+np.linalg.norm(constraints,axis=1)*np.linalg.norm(coefficients)
        if (not np.isfinite(coefficients).all() or np.any(abs(closure)>1e-9*np.maximum(bound,np.finfo(float).tiny))):
            status[i]='constraint_failure';continue
        values=shear@coefficients
        if not np.isfinite(values).all():status[i]='nonfinite_recovery';continue
        output[i]=values;valid[i]=True;methods[i]=method;stencils[i]=ids;conditions[i]=condition;boundary_count[i]=boundaries
        constraint_error[i]=np.max(abs(closure)/np.maximum(bound,np.finfo(float).tiny))
        denominator=np.linalg.norm(observed)
        fit_residual[i]=np.linalg.norm(matrix@coefficients-observed)/denominator if denominator else 0.
        status[i]='centered' if centered else 'one_sided'
    return dict(shear=output,valid=valid,stencils=stencils,status=status,method=methods,condition=conditions,
                moment_fit_relative_residual=fit_residual,free_edge_count=boundary_count,constraint_backward_error=constraint_error)
