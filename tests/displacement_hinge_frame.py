"""Research-only single-actuator displacement continuation for scalar hinges.

One free translational DOF is prescribed; its required dead actuator load is
recovered. Stability is checked on remaining unknowns, not falsely asserted for
load control. Uses the frozen corotational energy law without changing it.
"""
from dataclasses import dataclass
from itertools import product
import numpy as np
from corotational_hinge_frame import CorotationalHingeFrame


@dataclass(frozen=True)
class ControlledHistory:
    configuration: tuple
    rotations: tuple
    dissipation: float
    motion: tuple


class DisplacementHingeFrame(CorotationalHingeFrame):
    def __init__(self,nodes,members,fixed,hinges,preload,control):
        super().__init__(nodes,members,fixed,hinges)
        preload=np.asarray(preload,dtype=float)
        if preload.shape!=(self.size,) or not np.isfinite(preload).all():raise ValueError('Finite full dead preload required.')
        if type(control) is not int or control not in self.free or control%3==2:
            raise ValueError('Control must be a free translational DOF.')
        self.preload=preload.copy();self.preload.flags.writeable=False;self.control=control
        self.unknown=np.array([d for d in self.free if d!=control],dtype=int)
        if not len(self.unknown):raise ValueError("At least one other free DOF required.")
        self.configuration=(*self.configuration,'single_translation_control',tuple(preload),control)

    def solve(self,*args,**kwargs):
        raise ValueError("Use solve_displacement for controlled histories.")

    def solve_displacement(self,target,old=None,max_iterations=30):
        if isinstance(target,bool) or not np.isfinite(target):raise ValueError('Finite prescribed displacement required.')
        if type(max_iterations) is not int or not 1<=max_iterations<=50:raise ValueError('Use 1–50 iterations.')
        count=len(self.interfaces)
        if old is not None and (not isinstance(old,ControlledHistory) or old.configuration!=self.configuration):
            raise ValueError('History belongs to another controlled configuration.')
        previous=np.zeros(count) if old is None else np.asarray(old.rotations,dtype=float)
        initial=np.zeros(self.size) if old is None else np.asarray(old.motion,dtype=float)
        if previous.shape!=(count,) or initial.shape!=(self.size,) or not np.isfinite(previous).all() or not np.isfinite(initial).all() or (old is not None and (not np.isfinite(old.dissipation) or old.dissipation<0)):
            raise ValueError('Invalid committed controlled history.')
        if np.any(initial[self.fixed]!=0.):raise ValueError('Support motion is unsupported.')
        def matrix(e,dofs,active):
            G=e['coupling'][np.ix_(dofs,active)]
            return np.block([[e['stiffness'][np.ix_(dofs,dofs)],-G],[-G.T,e['hinge_stiffness'][np.ix_(active,active)]]])
        statuses=sorted(product((0,-1,1),repeat=count),key=lambda s:sum(v!=0 for v in s))
        for status in statuses:
            signs=np.asarray(status);active=np.flatnonzero(signs)
            u=initial.copy();u[self.control]=target;alpha=previous.copy();converged=False
            diagonal=np.r_[np.diag(self.K)[self.unknown],np.diag(self.H)[active]]
            if np.any(diagonal<=0):continue
            merit=1/np.sqrt(diagonal)
            def equations(u,alpha):
                e=self.evaluate(u,alpha)
                residual=np.r_[(e['internal']-self.preload)[self.unknown],
                    -e['hinge_moments'][active]+signs[active]*self.capacity[active]]
                return e,residual,matrix(e,self.unknown,active)
            for iteration in range(max_iterations):
                try:e,residual,H=equations(u,alpha)
                except ValueError:break
                if np.max(abs(residual),initial=0.)<=1e-8+1e-11*max(np.max(abs(self.preload)),np.max(self.capacity,initial=0.)):
                    converged=True;break
                scale=self._scaling(H)
                if scale is None:break
                step=np.linalg.solve(H*np.outer(scale,scale),-residual*scale)*scale
                norm=np.linalg.norm(residual*merit);accepted=False
                for factor in 2.**-np.arange(16):
                    trial=u.copy();trial_alpha=alpha.copy()
                    trial[self.unknown]+=factor*step[:len(self.unknown)]
                    trial_alpha[active]+=factor*step[len(self.unknown):]
                    try:_,r,_=equations(trial,trial_alpha)
                    except ValueError:continue
                    if np.linalg.norm(r*merit)<norm*(1-1e-4*factor):
                        u,alpha=trial,trial_alpha;accepted=True;break
                if not accepted:break
            if not converged or self._scaling(H) is None:continue
            q=e['hinge_moments']
            if np.any(abs(q)>self.capacity*(1+1e-9)) or np.any(signs[active]*(alpha-previous)[active]<-1e-10):continue
            boundary=np.flatnonzero(abs(q)>=self.capacity*(1-1e-10))
            if boundary.size and self._scaling(matrix(e,self.unknown,boundary)) is None:continue
            # Schur complement for the actuator's force/displacement derivative.
            hcc=e['stiffness'][self.control,self.control]
            hcr=np.r_[e['stiffness'][self.control,self.unknown],-e['coupling'][self.control,active]]
            slope=float(hcc-hcr@np.linalg.solve(H,hcr))
            actuator=float(e['internal'][self.control]-self.preload[self.control])
            loads=self.preload.copy();loads[self.control]+=actuator
            reaction=np.zeros(self.size);reaction[self.fixed]=(e['internal']-loads)[self.fixed]
            increment=float(self.capacity@abs(alpha-previous))
            state=ControlledHistory(self.configuration,tuple(alpha),increment+(0. if old is None else old.dissipation),tuple(u))
            return dict(state=state,motion=u,actuator_load=actuator,actuator_tangent=slope,
                reaction=reaction,loads=loads,hinge_moments=q,active=tuple(active),
                residual=(e['internal']-loads)[self.free],elastic_energy=e['elastic_energy'],
                constrained_stable=True,load_control_stable=self._scaling(matrix(e,self.free,boundary if boundary.size else active)) is not None,
                production_ready=False,qualification='single_actuator_scalar_hinge_continuation_only')
        raise ValueError('No resolved stable displacement-constrained equilibrium; no state committed.')
