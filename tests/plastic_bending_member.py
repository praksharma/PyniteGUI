"""Research-only two-node planar pure-bending material element.

Cubic Hermite kinematics, scalar elastic/perfect-plastic moment-curvature law,
exact yield-front splitting and immutable piecewise-linear plastic curvature.
No axial/biaxial interaction, P-Delta, frame equilibrium or section-law replacement
in the application. This is the pure-Mz restriction, not general steel plasticity.
"""
from dataclasses import dataclass
import numpy as np


@dataclass(frozen=True)
class BendingHistory:
    stations: tuple=(0.,1.)
    plastic_curvature: tuple=(0.,0.)
    dissipation: float=0.
    configuration: tuple|None=None

    def __post_init__(self):
        x=np.asarray(self.stations,float);p=np.asarray(self.plastic_curvature,float)
        if (x.ndim!=1 or len(x)<2 or len(x)>1024 or p.shape!=x.shape or not np.isfinite(x).all()
                or not np.isfinite(p).all() or x[0]!=0 or x[-1]!=1 or np.any(np.diff(x)<=0)
                or not np.isfinite(self.dissipation) or self.dissipation<0):
            raise ValueError('Finite ordered curvature history on [0,1] and nonnegative dissipation required.')
        object.__setattr__(self,'stations',tuple(map(float,x)))
        object.__setattr__(self,'plastic_curvature',tuple(map(float,p)))
        if self.configuration is not None:object.__setattr__(self,'configuration',tuple(self.configuration))


@dataclass(frozen=True)
class PlasticBendingMember:
    L: float
    EI: float
    Mp: float
    configuration: tuple
    yield_curvature: float

    def __init__(self,length,rigidity,plastic_moment):
        values=np.asarray((length,rigidity,plastic_moment),float)
        if not np.isfinite(values).all() or min(values)<=0:raise ValueError('Finite positive L, EI and Mp required.')
        for name,value in zip(('L','EI','Mp'),values):object.__setattr__(self,name,float(value))
        object.__setattr__(self,'configuration',tuple(map(float,values)))
        object.__setattr__(self,'yield_curvature',self.Mp/self.EI)

    def B(self,s):
        s=np.asarray(s);L=self.L
        return np.array(((-6+12*s)/L**2,(-4+6*s)/L,(6-12*s)/L**2,(-2+6*s)/L)).T

    def update(self,motion,old=BendingHistory()):
        u=np.asarray(motion,float)
        if u.shape!=(4,) or not np.isfinite(u).all() or not isinstance(old,BendingHistory):
            raise ValueError('Four finite nodal bending coordinates and committed history required.')
        if old.configuration!=self.configuration:
            if old.configuration is not None or any(old.plastic_curvature) or old.dissipation:
                raise ValueError('Curvature history belongs to another member configuration.')
        total=self.B(np.array((0.,1.)))@u
        if max(abs(total))>10*self.yield_curvature:raise ValueError('Curvature exceeds the bounded research range.')
        old_x=np.array(old.stations);old_p=np.array(old.plastic_curvature)
        cuts=list(old_x)
        trial=np.interp(old_x,[0.,1.],total)-old_p
        for a,b,ta,tb in zip(old_x,old_x[1:],trial,trial[1:]):
            if tb==ta:continue
            for boundary in (-self.yield_curvature,self.yield_curvature):
                ratio=(boundary-ta)/(tb-ta)
                if 0<ratio<1:cuts.append(float(a+ratio*(b-a)))
        cuts=np.unique(cuts)
        if len(cuts)>1024:raise ValueError('Yield-front history exceeds the bounded size; no state committed.')
        curvature=np.interp(cuts,[0.,1.],total);previous=np.interp(cuts,old_x,old_p)
        elastic=np.clip(curvature-previous,-self.yield_curvature,self.yield_curvature)
        updated=curvature-elastic
        # Retain the exact piecewise-linear representation; merge only roundoff-
        # collinear points, never average a resolved moving yield front.
        kept=[0]
        for i in range(1,len(cuts)-1):
            a=kept[-1];linear=updated[a]+(updated[i+1]-updated[a])*(cuts[i]-cuts[a])/(cuts[i+1]-cuts[a])
            if abs(updated[i]-linear)>64*np.finfo(float).eps*max(self.yield_curvature,max(abs(updated))):kept.append(i)
        kept.append(len(cuts)-1)
        points,weights=np.polynomial.legendre.leggauss(3)
        force=np.zeros(4);tangent=np.zeros((4,4));energy=0.;work=0.;plastic_length=0.
        for a,b in zip(cuts,cuts[1:]):
            s=(a+b)/2+(b-a)/2*points;w=weights*(b-a)*self.L/2;B=self.B(s)
            k=B@u;previous_k=np.interp(s,old_x,old_p);trial_k=k-previous_k
            # Use the actual trial at the interval midpoint (including history).
            mid=(a+b)/2;active=abs(float(np.interp(mid,[0.,1.],total)-np.interp(mid,old_x,old_p)))>self.yield_curvature
            moment=self.EI*np.clip(trial_k,-self.yield_curvature,self.yield_curvature)
            force+=B.T@(w*moment)
            if not active:tangent+=np.einsum('p,pi,pj->ij',w*self.EI,B,B)
            else:plastic_length+=(b-a)*self.L
            energy+=float(np.dot(w,.5*moment**2/self.EI))
            work+=float(np.dot(w,self.Mp*abs(k-moment/self.EI-previous_k)))
        if not np.isfinite(force).all() or not np.isfinite(tangent).all() or work<0:raise ValueError('Nonfinite or dissipative-state failure.')
        history=BendingHistory(tuple(cuts[kept]),tuple(updated[kept]),old.dissipation+work,self.configuration)
        return dict(force=force,tangent=tangent,state=history,elastic_energy=energy,dissipation_increment=work,
            plastic_loading_length=plastic_length,qualification='planar_scalar_material_element_only')
