"""Research-only small-deflection propped beam with specified scalar hinges.

Elastic spans have no implicit yield capacity. Only configured interfaces yield.
Active-set enumeration is bounded to four distinct hinge nodes; no P-Delta.
"""
from dataclasses import dataclass
from itertools import product
import numpy as np
from point_hinge_beam import PointHingeBeam


@dataclass(frozen=True)
class HingeHistory:
    configuration: tuple
    rotations: tuple
    dissipation: float
    motion: tuple


class ConfigurableHingeBeam(PointHingeBeam):
    def __init__(self, length, rigidity, capacity, segments, hinges):
        super().__init__(length, rigidity, capacity, segments)
        hinges=tuple(hinges)
        if not 1<=len(hinges)<=4:raise ValueError('Configure one to four hinges.')
        nodes=[]
        for pair in hinges:
            if len(pair)!=2 or any(type(v) is not int for v in pair):raise ValueError('Integer element/end required.')
            element,end=pair
            if not 0<=element<segments or end not in (0,1):raise ValueError('Invalid hinge interface.')
            nodes.append(element+end)
        if len(set(nodes))!=len(nodes):raise ValueError('Only one hinge interface per physical node.')
        self.hinges=hinges;self.configuration=(*self.configuration,hinges)
        self.G=np.zeros((self.size,len(hinges)));self.H=np.zeros((len(hinges),len(hinges)))
        for a,(element,end) in enumerate(hinges):
            ids=self.indices[element];dof=1+2*end
            self.G[ids,a]=self.local[:,dof]
            for b,(other,other_end) in enumerate(hinges):
                if other==element:self.H[a,b]=self.local[dof,1+2*other_end]

    def solve(self, loads, old=None):
        P=np.asarray(loads,dtype=float)
        if P.shape!=(self.size,) or not np.all(np.isfinite(P)):raise ValueError('Finite full nodal load vector required.')
        if old is not None and (not isinstance(old,HingeHistory) or old.configuration!=self.configuration):
            raise ValueError('History belongs to another hinge configuration.')
        previous=np.zeros(len(self.hinges)) if old is None else np.asarray(old.rotations,dtype=float)
        if previous.shape!=(len(self.hinges),) or not np.all(np.isfinite(previous)) or (old is not None and (not np.isfinite(old.dissipation) or old.dissipation<0)):
            raise ValueError('Invalid committed history.')
        K=self.K[np.ix_(self.free,self.free)];G=self.G[self.free]
        statuses=sorted(product((0,-1,1),repeat=len(self.hinges)),key=lambda s:sum(v!=0 for v in s))
        for status in statuses:
            s=np.asarray(status);active=np.flatnonzero(s);inactive=np.flatnonzero(s==0)
            Ga=G[:,active];Haa=self.H[np.ix_(active,active)]
            matrix=np.block([[K,-Ga],[-Ga.T,Haa]])
            diagonal=np.diag(matrix)
            if np.any(diagonal<=0):continue
            scale=1/np.sqrt(diagonal);normalized=matrix*np.outer(scale,scale)
            if np.linalg.eigvalsh(normalized)[0]<=1e-10:continue
            rhs=np.r_[P[self.free]+G[:,inactive]@previous[inactive],
                -s[active]*self.Mp-self.H[np.ix_(active,inactive)]@previous[inactive]]
            solution=np.linalg.solve(normalized,rhs*scale)*scale
            u=np.zeros(self.size);u[self.free]=solution[:len(self.free)]
            alpha=previous.copy();alpha[active]=solution[len(self.free):]
            q=self.G.T@u-self.H@alpha
            if np.any(abs(q)>self.Mp*(1+1e-9)):continue
            if np.any(s[active]*(alpha-previous)[active]<-1e-10):continue
            if active.size and np.max(abs(q[active]-s[active]*self.Mp))>1e-6:continue
            # Conservatively reject a yield-boundary state with a singular fully
            # released supported tangent, including exactly incipient collapse.
            boundary=np.flatnonzero(abs(q)>=self.Mp*(1-1e-10))
            if boundary.size:
                Gb=G[:,boundary];Hb=self.H[np.ix_(boundary,boundary)]
                stability=np.block([[K,-Gb],[-Gb.T,Hb]])
                sb=1/np.sqrt(np.diag(stability))
                if np.linalg.eigvalsh(stability*np.outer(sb,sb))[0]<=1e-10:continue
            residual=self.K@u-self.G@alpha-P
            if np.max(abs(residual[self.free]))>1e-7+1e-10*np.max(abs(P)):continue
            energy=0.;moments=[]
            for element,ids in enumerate(self.indices):
                elastic=u[ids].copy()
                for a,(hinge_element,end) in enumerate(self.hinges):
                    if element==hinge_element:elastic[1+2*end]-=alpha[a]
                energy+=float(.5*elastic@self.local@elastic)
                moments.extend((self.local@elastic)[[1,3]])
            increment=float(self.Mp*np.sum(abs(alpha-previous)))
            state=HingeHistory(self.configuration,tuple(alpha),increment+(0. if old is None else old.dissipation),tuple(u))
            tangent=K-Ga@np.linalg.solve(Haa,Ga.T) if active.size else K.copy()
            return dict(state=state,motion=u,reaction=residual[self.fixed],hinge_moments=q,
                end_moments=np.array(moments),residual=residual[self.free],active=tuple(active),
                elastic_energy=energy,dissipation_increment=increment,free_tangent=tangent,
                production_ready=False,qualification='configured_scalar_hinges_propped_beam_only')
        raise ValueError('No stable consistent hinge equilibrium: mechanism or unresolved branch; no state committed.')
