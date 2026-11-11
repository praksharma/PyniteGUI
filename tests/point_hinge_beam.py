"""Research-only propped beam with an explicit zero-length base rotation hinge.

Small-deflection scalar bending, central transverse nodal force and elastic
members. Exact active-set rotational flow; an additional hinge/mechanism is
rejected. This is a concentrated-hinge formulation, not a relabelled correction
of the distributed-curvature element or a general frame/P-Delta solver.
"""
from dataclasses import dataclass
import numpy as np
from beam_gradient_compatibility import integrate


@dataclass(frozen=True)
class PointHingeState:
    configuration: tuple
    plastic_rotation: float
    dissipation: float
    motion: tuple


class PointHingeBeam:
    def __init__(self,length,rigidity,capacity,segments):
        if type(segments) is not int or segments<2 or segments>32 or segments%2:raise ValueError('Use even 2–32 segments.')
        self.configuration=(float(length),float(rigidity),float(capacity),segments)
        self.L,self.EI,self.Mp=map(float,(length,rigidity,capacity));self.n=segments;self.size=2*(segments+1)
        self.local=integrate(self.L/segments,self.EI,[0.,0.])['nodal_elastic_stiffness']
        if not np.isfinite(self.Mp) or self.Mp<=0:raise ValueError('Positive finite plastic moment required.')
        self.indices=tuple(np.arange(2*i,2*i+4) for i in range(segments));self.K=np.zeros((self.size,self.size))
        for ids in self.indices:self.K[np.ix_(ids,ids)]+=self.local
        self.fixed=np.array([0,1,2*segments]);self.free=np.array([i for i in range(self.size) if i not in self.fixed])
        self.g=self.K[:,1].copy();self.h=self.K[1,1]

    def solve(self,force,old=None):
        if isinstance(force,bool) or not np.isfinite(force):raise ValueError('Finite central force required.')
        if abs(force)>=6*self.Mp/self.L*(1-1e-10):raise ValueError('Ideal plastic mechanism bound reached; no state committed.')
        if old is not None and (not isinstance(old,PointHingeState) or old.configuration!=self.configuration):
            raise ValueError('History belongs to another beam configuration.')
        alpha=0. if old is None else old.plastic_rotation;old_alpha=alpha
        if not np.isfinite(alpha) or (old is not None and (not np.isfinite(old.dissipation) or old.dissipation<0)):
            raise ValueError('Invalid committed hinge history.')
        P=np.zeros(self.size);P[self.n]=-force
        Kff=self.K[np.ix_(self.free,self.free)];g=self.g[self.free]
        u=np.zeros(self.size);u[self.free]=np.linalg.solve(Kff,P[self.free]+g*alpha)
        trial=float(g@u[self.free]-self.h*alpha);active=abs(trial)>self.Mp
        if active:
            sign=np.sign(trial)
            matrix=np.block([[Kff,-g[:,None]],[-g[None,:],np.array([[self.h]])]])
            scale=1/np.sqrt(np.diag(matrix));normalized=matrix*np.outer(scale,scale)
            if np.linalg.eigvalsh(normalized)[0]<=1e-10:raise ValueError('Unresolved supported hinge tangent.')
            solution=np.linalg.solve(normalized,np.r_[P[self.free],-sign*self.Mp]*scale)*scale
            u[self.free]=solution[:-1];alpha=float(solution[-1])
            if sign*(alpha-old_alpha)<-1e-10:raise ValueError('Negative plastic multiplier; no state committed.')
        internal=self.K@u-self.g*alpha;residual=internal-P
        if np.max(abs(residual[self.free]))>1e-7+1e-10*np.max(abs(internal)):
            raise ValueError('Global hinge equilibrium failed.')
        energy=0.;moments=[]
        for i,ids in enumerate(self.indices):
            elastic=u[ids].copy()
            if i==0:elastic[1]-=alpha
            f=self.local@elastic;moments.extend(f[[1,3]])
            energy+=float(.5*elastic@self.local@elastic)
        if max(abs(np.array(moments)[1:]))>=self.Mp*(1-1e-10):raise ValueError('Additional plastic hinge requires a broader formulation.')
        if abs(moments[0])>self.Mp*(1+1e-9):raise ValueError('Base moment violates capacity.')
        D=(0. if old is None else old.dissipation)+self.Mp*abs(alpha-old_alpha)
        state=PointHingeState(self.configuration,alpha,D,tuple(map(float,u)))
        reaction=np.zeros(self.size);reaction[self.fixed]=residual[self.fixed]
        tangent=Kff-np.outer(g,g)/self.h if active else Kff
        return dict(state=state,motion=u,reaction=reaction,end_moments=np.array(moments),residual=residual[self.free],
            elastic_energy=energy,dissipation_increment=self.Mp*abs(alpha-old_alpha),active=active,
            free_tangent=tangent,production_ready=False,qualification='explicit_base_hinge_propped_beam_only')
