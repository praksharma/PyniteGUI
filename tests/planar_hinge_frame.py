"""Research-only first-order 2D elastic frames with specified scalar end hinges.

No distributed member plasticity, axial/moment interaction, follower loads or
geometric stiffness. Bounded active-set enumeration is not a general frame solver
qualification. Each nodal couple acts on the shared joint rotation.
"""
from dataclasses import dataclass
from itertools import product
import numpy as np
from beam_gradient_compatibility import integrate


@dataclass(frozen=True)
class FrameHistory:
    configuration: tuple
    rotations: tuple
    dissipation: float
    motion: tuple


class PlanarHingeFrame:
    def __init__(self, nodes, members, fixed, hinges=()):
        """nodes=(x,y); members=(i,j,EA,EI); hinges=(member,end,Mp).

        Each hinge subtracts a plastic rotation from that member end's shared
        joint rotation. Distinct member-end interfaces at a joint are allowed;
        any resulting unresolved gauge/mechanism is rejected by stability checks.
        """
        xy=np.asarray(nodes,dtype=float)
        if xy.ndim!=2 or xy.shape[1]!=2 or not 2<=len(xy)<=32 or not np.isfinite(xy).all():
            raise ValueError('Use 2–32 finite planar nodes.')
        self.size=3*len(xy)
        members=tuple(tuple(m) for m in members);hinges=tuple(tuple(h) for h in hinges)
        fixed=tuple(fixed)
        if not 1<=len(members)<=48 or len(hinges)>4:raise ValueError('Use 1–48 members and at most four hinges.')
        if len(set(fixed))!=len(fixed) or any(type(d) is not int or not 0<=d<self.size for d in fixed):
            raise ValueError('Distinct valid restrained DOFs required.')
        self.fixed=np.array(sorted(fixed),dtype=int)
        self.free=np.array([d for d in range(self.size) if d not in fixed],dtype=int)
        if not len(self.free):raise ValueError('At least one free DOF required.')
        self.K=np.zeros((self.size,self.size));self.elements=[]
        for m in members:
            if len(m)!=4:raise ValueError('Member requires i, j, EA, EI.')
            i,j,EA,EI=m
            if any(type(v) is not int or not 0<=v<len(xy) for v in (i,j)) or i==j:
                raise ValueError('Distinct valid member nodes required.')
            if not np.isfinite([EA,EI]).all() or min(EA,EI)<=0:raise ValueError('Positive finite rigidities required.')
            delta=xy[j]-xy[i];length=float(np.linalg.norm(delta))
            if length<=0:raise ValueError('Zero-length member.')
            c,s=delta/length;R=np.array([[c,s,0.],[-s,c,0.],[0.,0.,1.]])
            T=np.zeros((6,6));T[:3,:3]=R;T[3:,3:]=R
            k=np.zeros((6,6));b=np.array([1,2,4,5]);a=np.array([0,3])
            k[np.ix_(b,b)]=integrate(length,EI,[0.,0.])['nodal_elastic_stiffness']
            k[np.ix_(a,a)]=EA/length*np.array([[1.,-1.],[-1.,1.]])
            ids=np.r_[np.arange(3*i,3*i+3),np.arange(3*j,3*j+3)]
            self.K[np.ix_(ids,ids)]+=T.T@k@T
            self.elements.append((ids,T,k))
        interfaces=[];capacities=[]
        for h in hinges:
            if len(h)!=3:raise ValueError('Hinge requires member, end and capacity.')
            member,end,capacity=h
            if type(member) is not int or not 0<=member<len(members) or type(end) is not int or end not in (0,1):
                raise ValueError('Invalid hinge interface.')
            if not np.isfinite(capacity) or capacity<=0:raise ValueError('Positive finite hinge capacity required.')
            interfaces.append((member,end));capacities.append(float(capacity))
        if len(set(interfaces))!=len(interfaces):raise ValueError('Duplicate hinge interface.')
        self.interfaces=tuple(interfaces);self.capacity=np.array(capacities)
        self.G=np.zeros((self.size,len(hinges)));self.H=np.zeros((len(hinges),len(hinges)))
        for a,(member,end) in enumerate(interfaces):
            ids,T,k=self.elements[member];d=2+3*end
            self.G[ids,a]=T.T@k[:,d]
            for b,(other,other_end) in enumerate(interfaces):
                if member==other:self.H[a,b]=k[d,2+3*other_end]
        self.configuration=(tuple(map(tuple,xy)),members,tuple(sorted(fixed)),hinges)

    @staticmethod
    def _scaling(matrix):
        diagonal=np.diag(matrix)
        if not np.isfinite(matrix).all() or np.any(diagonal<=0):return None
        scale=1/np.sqrt(diagonal)
        if np.linalg.eigvalsh(matrix*np.outer(scale,scale))[0]<=1e-10:return None
        return scale

    def solve(self, loads, old=None):
        loads=np.asarray(loads,dtype=float)
        if loads.shape!=(self.size,) or not np.isfinite(loads).all():raise ValueError('Finite full nodal loads required.')
        count=len(self.interfaces)
        if old is not None and (not isinstance(old,FrameHistory) or old.configuration!=self.configuration):
            raise ValueError('History belongs to another frame configuration.')
        previous=np.zeros(count) if old is None else np.asarray(old.rotations,dtype=float)
        if previous.shape!=(count,) or not np.isfinite(previous).all() or (old is not None and (not np.isfinite(old.dissipation) or old.dissipation<0)):
            raise ValueError('Invalid committed frame history.')
        K=self.K[np.ix_(self.free,self.free)];G=self.G[self.free]
        statuses=sorted(product((0,-1,1),repeat=count),key=lambda s:sum(v!=0 for v in s))
        for status in statuses:
            s=np.asarray(status);active=np.flatnonzero(s);inactive=np.flatnonzero(s==0)
            Ga=G[:,active];Haa=self.H[np.ix_(active,active)]
            matrix=np.block([[K,-Ga],[-Ga.T,Haa]]);scale=self._scaling(matrix)
            if scale is None:continue
            rhs=np.r_[loads[self.free]+G[:,inactive]@previous[inactive],
                -s[active]*self.capacity[active]-self.H[np.ix_(active,inactive)]@previous[inactive]]
            answer=np.linalg.solve(matrix*np.outer(scale,scale),rhs*scale)*scale
            u=np.zeros(self.size);u[self.free]=answer[:len(self.free)]
            alpha=previous.copy();alpha[active]=answer[len(self.free):]
            q=self.G.T@u-self.H@alpha
            if np.any(abs(q)>self.capacity*(1+1e-9)):continue
            if np.any(s[active]*(alpha-previous)[active]<-1e-10):continue
            if active.size and np.any(abs(q[active]-s[active]*self.capacity[active])>self.capacity[active]*1e-9):continue
            # Conservative incipient-mechanism rejection, not a directional
            # stability proof at nonsmooth yield/unload transitions.
            boundary=np.flatnonzero(abs(q)>=self.capacity*(1-1e-10))
            if boundary.size:
                Gb=G[:,boundary];Hb=self.H[np.ix_(boundary,boundary)]
                if self._scaling(np.block([[K,-Gb],[-Gb.T,Hb]])) is None:continue
            residual=self.K@u-self.G@alpha-loads
            if np.max(abs(residual[self.free]))>1e-7+1e-10*np.max(abs(loads)):continue
            energy=0.;forces=[]
            for element,(ids,T,k) in enumerate(self.elements):
                elastic=T@u[ids]
                for a,(member,end) in enumerate(self.interfaces):
                    if member==element:elastic[2+3*end]-=alpha[a]
                energy+=float(.5*elastic@k@elastic);forces.append(k@elastic)
            increment=float(self.capacity@abs(alpha-previous))
            state=FrameHistory(self.configuration,tuple(alpha),increment+(0. if old is None else old.dissipation),tuple(u))
            reaction=np.zeros(self.size);reaction[self.fixed]=residual[self.fixed]
            tangent=K-Ga@np.linalg.solve(Haa,Ga.T) if active.size else K.copy()
            return dict(state=state,motion=u,reaction=reaction,local_forces=np.array(forces),
                hinge_moments=q,residual=residual[self.free],active=tuple(active),free_tangent=tangent,
                elastic_energy=energy,dissipation_increment=increment,production_ready=False,
                qualification='first_order_planar_configured_hinge_research_only')
        raise ValueError('No stable consistent frame equilibrium: mechanism or unresolved branch; no state committed.')
