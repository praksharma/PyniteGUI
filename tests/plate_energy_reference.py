"""Independent rectangular Kirchhoff plate reference with a free square cutout.

No application or PyNite imports. Minimize the physical bending energy using
conforming tensor-Hermite polynomials: bicubic C1 (BFS) or biquintic C2. Integrate
stiffness/load/resultants by exact-degree Gaussian quadrature. Simply supported
outer traces and a natural free opening; no fictitious supports inside the hole.
The construction is derived here from interpolation and the continuum energy,
not engine stiffness/recovery formulas. Background on tensor-Hermite plate spaces:
https://arxiv.org/abs/1911.00239 (our grid fits the boundary; no cut stabilization).

Unit q and D, physical lengths: scale w by q/D, moments and shears by q.
This is a bounded numerical reference, never a corner-peak or production solver.
"""
from functools import lru_cache
from math import factorial
import numpy as np
from numpy.polynomial import Polynomial
from scipy.sparse import coo_matrix,diags
from scipy.sparse.linalg import LinearOperator,eigsh,splu

CONDITION_LIMIT=1e8
MAX_DOFS=100_000


@lru_cache(maxsize=2)
def hermite_basis(order):
    """Endpoint values/slopes (and curvatures for order=2), derivatives 0..3."""
    if type(order) is not int or order not in (1,2):raise ValueError('Choose cubic or quintic Hermite order 1/2.')
    count=2*(order+1);matrix=np.zeros((count,count))
    for end in (0,1):
        for derivative in range(order+1):
            for power in range(derivative,count):
                matrix[end*(order+1)+derivative,power]=factorial(power)/factorial(power-derivative)*end**(power-derivative)
    coefficients=np.linalg.solve(matrix,np.eye(count))
    return tuple(tuple(Polynomial(coefficients[:,i]).deriv(d) for d in range(4)) for i in range(count))


def shape(order,hx,hy,s,t,dx=0,dy=0):
    """Physical derivative basis, corner order BL/BR/TR/TL, then dy/dx DOFs."""
    s,t=np.broadcast_arrays(s,t);values=[];n=order+1;basis=hermite_basis(order)
    for ex,ey in ((0,0),(1,0),(1,1),(0,1)):
        for iy in range(n):
            for ix in range(n):
                values.append(basis[ex*n+ix][dx](s)*basis[ey*n+iy][dy](t)*hx**(ix-dx)*hy**(iy-dy))
    return np.asarray(values).T


def element_energy(order,hx,hy,nu):
    """D=1 stiffness and q=1 consistent force, from curvature energy only."""
    gauss,weights=np.polynomial.legendre.leggauss(2*order+2)
    s,t=np.meshgrid((gauss+1)/2,(gauss+1)/2);w=np.outer(weights,weights).ravel()*hx*hy/4
    n=shape(order,hx,hy,s.ravel(),t.ravel())
    xx=shape(order,hx,hy,s.ravel(),t.ravel(),2,0)
    yy=shape(order,hx,hy,s.ravel(),t.ravel(),0,2)
    xy=shape(order,hx,hy,s.ravel(),t.ravel(),1,1)
    stiffness=xx.T@(w[:,None]*xx)+yy.T@(w[:,None]*yy)+nu*(xx.T@(w[:,None]*yy)+yy.T@(w[:,None]*xx))+2*(1-nu)*xy.T@(w[:,None]*xy)
    return stiffness,n.T@w


class OpeningEnergyReference:
    """Simply supported rectangle with a centred, natural free rectangular hole.

    The unit-width normalization keeps algebra independent of physical units.
    All four opening lines must lie exactly on the chosen rectangular grid.
    Both order families refine independently. The unchanged 1e8 condition guard
    applies to their Jacobi-scaled free stiffness, with explicit eigen residuals.
    """
    def __init__(self,width=120.,height=120.,nu=.2,hole_width=40.,hole_height=40.,*,nx=24,ny=None,order=2):
        if ny is None:ny=nx
        values=(width,height,nu,hole_width,hole_height)
        if (any(isinstance(v,bool) or not isinstance(v,(int,float)) or not np.isfinite(v) for v in values)
                or min(width,height)<=0 or not -1<nu<.5 or min(hole_width,hole_height)<0
                or hole_width>=width or hole_height>=height or bool(hole_width)!=bool(hole_height)
                or type(nx) is not int or type(ny) is not int or min(nx,ny)<3):
            raise ValueError('Use positive dimensions, physical isotropic nu, a centred interior hole or no hole, and integer grid counts >=3.')
        hermite_basis(order)
        if (nx+1)*(ny+1)*(order+1)**2>MAX_DOFS:raise ValueError('Independent reference exceeds its DOF budget.')
        self.width,self.height,self.nu,self.nx,self.ny,self.order=width,height,nu,nx,ny,order
        self.hx,self.hy=1/nx,height/(width*ny);self.hole_width,self.hole_height=hole_width,hole_height
        hole=None
        if hole_width:
            bounds=np.array([(width-hole_width)/(2*width),(width+hole_width)/(2*width),
                             (height-hole_height)/(2*height),(height+hole_height)/(2*height)])*np.array([nx,nx,ny,ny])
            if not np.allclose(bounds,np.rint(bounds),rtol=0,atol=1e-10):raise ValueError('Grid must fit all opening boundaries without geometry approximation.')
            hole=tuple(np.rint(bounds).astype(int))
        cells=[(i,j) for j in range(ny) for i in range(nx) if hole is None or not (hole[0]<=i<hole[1] and hole[2]<=j<hole[3])]
        nodes=sorted({(i+a,j+b) for i,j in cells for a,b in ((0,0),(1,0),(1,1),(0,1))},key=lambda p:(p[1],p[0]))
        ids={point:k for k,point in enumerate(nodes)};nd=(order+1)**2;size=len(nodes)*nd
        self.points=np.array(nodes,float)*[self.hx,self.hy]
        self.cells=np.array(cells,float)*[self.hx,self.hy]
        self.lookup={ij:k for k,ij in enumerate(cells)}
        mapping=np.array([[nd*ids[(i+a,j+b)]+d for a,b in ((0,0),(1,0),(1,1),(0,1)) for d in range(nd)] for i,j in cells])
        self.mapping=mapping
        stiffness,force=element_energy(order,self.hx,self.hy,nu)
        local=mapping.shape[1]
        rows=np.repeat(mapping,local,axis=1).ravel();columns=np.tile(mapping,(1,local)).ravel()
        matrix=coo_matrix((np.tile(stiffness.ravel(),len(cells)),(rows,columns)),shape=(size,size)).tocsr()
        applied=np.zeros(size);np.add.at(applied,mapping.ravel(),np.tile(force,len(cells)))
        fixed=[]
        for k,(i,j) in enumerate(nodes):
            for iy in range(order+1):
                for ix in range(order+1):
                    # A zero edge trace fixes its tangential Hermite data too;
                    # normal derivatives remain free (not a clamped boundary).
                    if ((i in (0,nx) and ix==0) or (j in (0,ny) and iy==0)):fixed.append(k*nd+iy*(order+1)+ix)
        free=np.setdiff1d(np.arange(size),fixed);a=matrix[free][:,free].tocsc()
        scale=1/np.sqrt(a.diagonal());s=diags(scale);normalized=(s@a@s).tocsc();factor=splu(normalized)
        v0=np.random.default_rng(42).normal(size=len(free))
        largest,top=eigsh(normalized,k=1,which='LA',v0=v0,tol=1e-8)
        inverse=LinearOperator(normalized.shape,matvec=factor.solve)
        smallest,bottom=eigsh(normalized,k=1,sigma=0,OPinv=inverse,which='LM',v0=v0,tol=1e-8)
        residual_top=float(np.linalg.norm(normalized@top[:,0]-largest[0]*top[:,0]))
        residual_bottom=float(np.linalg.norm(normalized@bottom[:,0]-smallest[0]*bottom[:,0]))
        lower=float(smallest[0]-residual_bottom)
        self.condition=float((largest[0]+residual_top)/lower) if lower>0 else float('inf')
        if not np.isfinite(self.condition) or self.condition>CONDITION_LIMIT:raise ValueError('Energy reference exceeds the 1e8 stiffness-condition limit.')
        self.u=np.zeros(size);self.u[free]=scale*factor.solve(scale*applied[free])
        residual=matrix@self.u-applied
        backward=abs(residual[free])/(abs(matrix[free])@abs(self.u)+abs(applied[free])+np.finfo(float).tiny)
        energy=float(self.u@matrix@self.u);work=float(self.u@applied)
        energy_error=abs(energy-work)/abs(work)
        rigid=[]
        for direction in range(3):
            mode=np.zeros(size)
            if direction==0:mode[::nd]=1.
            else:
                mode[::nd]=self.points[:,direction-1]
                mode[(1 if direction==1 else order+1)::nd]=1.
            # Only actual constrained-coordinate reactions enter balance.
            rigid.append(float(mode[fixed]@residual[fixed]+mode@applied))
        area=len(cells)*self.hx*self.hy
        balance_error=max(abs(np.array(rigid)))/area
        if (not np.isfinite(self.u).all() or not np.isfinite(backward).all()
                or not np.isfinite([energy,work,energy_error,balance_error]).all()
                or np.max(backward)>1e-11 or energy_error>1e-8 or balance_error>1e-8):
            raise ValueError('Independent energy solve failed residual, energy or rigid-force/moment balance.')
        self.compliance=work*width**6
        self.diagnostics=dict(dofs=size,free_dofs=len(free),elements=len(cells),condition=self.condition,
            eigen_residuals=[residual_bottom,residual_top],backward_error=float(np.max(backward)),energy_relative_error=energy_error,
            force_moment_relative_error=float(balance_error),compliance=self.compliance,area=area*width**2)
        # Retain only compact fields, not LU factors/global stiffness matrices.

    def _owner(self,point):
        scaled=np.asarray(point,float)/self.width
        dimensions=np.array([1.,self.height/self.width]);tol=64*np.finfo(float).eps
        if np.any(scaled<-tol) or np.any(scaled>dimensions+tol):raise ValueError('Reference point lies outside the plate.')
        indices=np.minimum(np.floor(scaled/[self.hx,self.hy]).astype(int),[self.nx-1,self.ny-1])
        for di,dj in ((0,0),(-1,0),(0,-1),(-1,-1)):
            key=(indices[0]+di,indices[1]+dj)
            if key not in self.lookup:continue
            local=(scaled-np.array(key)*[self.hx,self.hy])/[self.hx,self.hy]
            if np.all(local>=-tol) and np.all(local<=1+tol):return self.lookup[key],np.clip(local,0.,1.)
        raise ValueError('Reference point lies in the opening.')

    def derivative(self,points,dx=0,dy=0):
        points=np.atleast_2d(np.asarray(points,float))
        if points.shape[1:]!=(2,) or not np.isfinite(points).all() or type(dx) is not int or type(dy) is not int or min(dx,dy)<0 or max(dx,dy)>3:
            raise ValueError('Finite planar points and derivative orders 0..3 are required.')
        owners=[self._owner(point) for point in points]
        if not owners:return np.empty(0)
        indices=np.array([item[0] for item in owners]);local=np.array([item[1] for item in owners])
        values=shape(self.order,self.hx,self.hy,local[:,0],local[:,1],dx,dy)
        return np.einsum('ij,ij->i',values,self.u[self.mapping[indices]])*self.width**(4-dx-dy)

    def displacement(self,points):return self.derivative(points)

    def moments(self,points):
        xx,yy,xy=(self.derivative(points,*d) for d in ((2,0),(0,2),(1,1)))
        return -np.column_stack((xx+self.nu*yy,yy+self.nu*xx,(1-self.nu)*xy))

    def shears(self,points):
        xxx,xyy,xxy,yyy=(self.derivative(points,*d) for d in ((3,0),(1,2),(2,1),(0,3)))
        return -np.column_stack((xxx+xyy,xxy+yyy))

    def mean_shears(self,patch):
        """Exact quadrature of the polynomial third derivatives on clipped cells."""
        x0,x1,y0,y1=np.asarray(patch,float)/self.width
        if not np.isfinite([x0,x1,y0,y1]).all() or x0>=x1 or y0>=y1:raise ValueError('Choose a finite positive material patch.')
        result=np.zeros(2);area=0.;g,w=np.polynomial.legendre.leggauss(2*self.order+2)
        for index,(a,b) in enumerate(self.cells):
            low=np.maximum([a,b],[x0,y0]);high=np.minimum([a+self.hx,b+self.hy],[x1,y1]);span=high-low
            if np.any(span<=1e-14):continue
            x,y=np.meshgrid(low[0]+span[0]*(g+1)/2,low[1]+span[1]*(g+1)/2)
            s=(x.ravel()-a)/self.hx;t=(y.ravel()-b)/self.hy;u=self.u[self.mapping[index]]
            qx=-(shape(self.order,self.hx,self.hy,s,t,3,0)+shape(self.order,self.hx,self.hy,s,t,1,2))@u
            qy=-(shape(self.order,self.hx,self.hy,s,t,2,1)+shape(self.order,self.hx,self.hy,s,t,0,3))@u
            weights=np.outer(w,w).ravel()*np.prod(span)/4
            result+=np.array([weights@qx,weights@qy]);area+=np.prod(span)
        expected=(x1-x0)*(y1-y0)
        if area<=0 or abs(area-expected)>1e-10*expected:raise ValueError('Reference patch must be completely covered by material, without crossing the opening or outer boundary.')
        return result/area*self.width
