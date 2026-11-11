"""Research-only global equilibrium of a planar pure-bending beam chain.

Fixed zero support coordinates, nodal loading, no axial force or geometry update.
Trial element histories remain frozen throughout Newton iterations and line search.
Only a converged, positively resolved supported tangent commits a global state.
"""
from dataclasses import dataclass
import numpy as np
from plastic_bending_member import PlasticBendingMember,BendingHistory


class ChainRejected(ValueError):
    pass


@dataclass(frozen=True)
class ChainState:
    configuration: tuple
    motion: tuple
    histories: tuple


class PlasticBeamChain:
    def __init__(self,length,rigidity,capacity,segments):
        if type(segments) is not int or segments<2 or segments>32 or segments%2:
            raise ValueError('Use an even 2–32 beam segments.')
        self.element=PlasticBendingMember(length/segments,rigidity,capacity)
        self.n=segments;self.size=2*(segments+1)
        self.fixed=np.array((0,1,2*segments));self.free=np.array([i for i in range(self.size) if i not in self.fixed])
        self.configuration=(float(length),float(rigidity),float(capacity),segments)
        self.indices=tuple(np.arange(2*i,2*i+4) for i in range(segments))
        K=self.assemble(np.zeros(self.size),(BendingHistory(),)*segments)[1]
        self.scale=1/np.sqrt(np.diag(K)[self.free])

    def assemble(self,u,histories):
        force=np.zeros(self.size);K=np.zeros((self.size,self.size));results=[]
        for indices,old in zip(self.indices,histories):
            result=self.element.update(u[indices],old);results.append(result)
            force[indices]+=result['force'];K[np.ix_(indices,indices)]+=result['tangent']
        return force,K,results

    def solve(self,external,old=None,max_iterations=60):
        P=np.asarray(external,float)
        if P.shape!=(self.size,) or not np.isfinite(P).all():raise ValueError('Finite, compatible nodal forces required.')
        if np.any(P[1::2]):raise ValueError('This bounded mechanism check requires transverse nodal forces, not applied couples.')
        # Independent kinematic upper bound: unit midspan displacement, a base
        # hinge rotation 2/L and an interior hinge rotation 4/L. Positive discrete
        # tangent alone can spuriously accept loads above this physical mechanism.
        length,_,capacity,_=self.configuration
        x=np.linspace(0.,1.,self.n+1);mechanism=1-abs(2*x-1)
        if abs(float(P[::2]@mechanism))>=6*capacity/length*(1-1e-10):
            raise ChainRejected('Kinematic plastic-mechanism work bound reached; no state committed.')
        if type(max_iterations) is not int or not 1<=max_iterations<=100:raise ValueError('Use 1–100 equilibrium iterations.')
        if old is not None and (not isinstance(old,ChainState) or old.configuration!=self.configuration):
            raise ValueError('Global history belongs to a different beam configuration.')
        u=np.zeros(self.size) if old is None else np.array(old.motion,float)
        histories=(BendingHistory(),)*self.n if old is None else old.histories
        for iteration in range(max_iterations+1):
            try:internal,K,results=self.assemble(u,histories)
            except ValueError as error:raise ChainRejected(str(error)) from error
            residual=internal-P;limits=np.where(self.free%2,1e-7,1e-8)+1e-10*(abs(internal[self.free])+abs(P[self.free]))
            norm=float(max(abs(residual[self.free])/limits))
            reduced=K[np.ix_(self.free,self.free)]*np.outer(self.scale,self.scale)
            minimum=float(np.linalg.eigvalsh((reduced+reduced.T)/2)[0])
            if norm<=1:
                if minimum<=1e-10:raise ChainRejected('Nonpositive or unresolved supported tangent; no state committed.')
                state=ChainState(self.configuration,tuple(map(float,u)),tuple(r['state'] for r in results))
                reaction=np.zeros(self.size);reaction[self.fixed]=residual[self.fixed]
                return dict(state=state,motion=u.copy(),reaction=reaction,residual=residual[self.free],iterations=iteration,
                    min_normalized_tangent=minimum,elastic_energy=sum(r['elastic_energy'] for r in results),
                    dissipation=sum(r['state'].dissipation for r in results),qualification='research_global_equilibrium_only',production_ready=False)
            if iteration==max_iterations:break
            if minimum<=1e-10:raise ChainRejected('Nonpositive or unresolved trial tangent; no state committed.')
            try:du=np.linalg.solve(reduced,-residual[self.free]*self.scale)*self.scale
            except np.linalg.LinAlgError as error:raise ChainRejected('Singular global tangent.') from error
            accepted=False
            for cut in range(20):
                trial=u.copy();trial[self.free]+=2.**-cut*du
                try:f,_,_=self.assemble(trial,histories)
                except ValueError:continue
                candidate=max(abs((f-P)[self.free])/limits)
                if candidate<=(1-1e-4*2.**-cut)*norm or candidate<=1:
                    u=trial;accepted=True;break
            if not accepted:raise ChainRejected('Global line search failed; no state committed.')
        raise ChainRejected('Global iteration limit; no state committed.')
