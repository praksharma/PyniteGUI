"""Research-only total-state elastic beam-column corrector.

Own the solve, not PyNite's incremental pushover path. Local Ke and unit Kg are
read-only engine operators; N is the actual tension-positive mean end action.
Every load target solves both nodal equilibrium and that axial-force closure.
This is an elastic algebraic prototype, NOT a plastic return map or a validated
finite-rotation frame formulation. No application imports or engine patches.
"""
from dataclasses import dataclass
import numpy as np
from Pynite import Analysis

DOFS=('DX','DY','DZ','RX','RY','RZ')


class RejectedState(ValueError):
    pass


@dataclass(frozen=True)
class Element:
    name: str
    indices: np.ndarray
    transform: np.ndarray
    elastic: np.ndarray
    geometric: np.ndarray
    section: object


class ElasticSystem:
    def __init__(self,model):
        if not model.members or len(model.nodes)>64:raise ValueError('Research scope: 1–64 joints and explicit frame members.')
        if (model.quads or model.plates or model.meshes or model.springs
                or getattr(model,'shear_walls',{}) or getattr(model,'mats',{})):
            raise ValueError('Research scope excludes surfaces, mesh recipes, foundations and spring elements.')
        if any(member.PtLoads or member.DistLoads or any(member.Releases) or member.tension_only or member.comp_only for member in model.members.values()):
            raise ValueError('Research scope excludes member loads, releases and unilateral action.')
        if any(any(getattr(node,'Enforced'+dof,None) is not None for dof in DOFS) for node in model.nodes.values()):
            raise ValueError('Research scope excludes imposed support motions.')
        for node in model.nodes.values():
            if any(getattr(node,'spring_'+dof)[0] is not None for dof in DOFS):raise ValueError('Research scope excludes support springs.')
        Analysis._prepare_model(model)
        self.model=model;self.nodes=tuple(model.nodes.values());self.size=6*len(self.nodes)
        self.free=np.array([6*node.ID+j for node in self.nodes for j,dof in enumerate(DOFS) if not getattr(node,'support_'+dof)],int)
        if not len(self.free) or len(self.free)>300:raise ValueError('Research scope requires 1–300 free coordinates.')
        elements=[]
        for physical in model.members.values():
            if len(physical.sub_members)!=1:raise ValueError('Use explicit endpoints; implicit subdivisions are outside research scope.')
            member=next(iter(physical.sub_members.values()))
            properties=(member.L(),member.material.E,member.material.G,member.section.A,member.section.Iy,member.section.Iz,member.section.J)
            if not np.isfinite(properties).all() or min(properties)<=0:
                raise ValueError('Finite positive element length, moduli and section properties are required.')
            indices=np.r_[np.arange(6*member.i_node.ID,6*member.i_node.ID+6),np.arange(6*member.j_node.ID,6*member.j_node.ID+6)]
            transform,elastic,geometric=member.T(),member.ke(),member.kg(1.)
            if any(value.shape!=(12,12) or not np.isfinite(value).all() for value in (transform,elastic,geometric)):
                raise ValueError('Finite, compatible local frame operators are required.')
            elements.append(Element(physical.name,indices,transform,elastic,geometric,member.section))
        self.elements=tuple(elements);self.count=len(elements);self.unknowns=len(self.free)+self.count
        self.axial_selector=np.zeros(12);self.axial_selector[0]=-.5;self.axial_selector[6]=.5
        elastic=np.zeros((self.size,self.size))
        for element in self.elements:
            elastic[np.ix_(element.indices,element.indices)]+=element.transform.T@element.elastic@element.transform
        self.elastic=elastic
        diagonal=np.diag(elastic)[self.free]
        if np.any(diagonal<=0) or not np.isfinite(diagonal).all():raise RejectedState('Unresolved elastic stiffness.')
        self.stability_scale=1/np.sqrt(diagonal)
        self._stable(elastic)

    def _stable(self,matrix):
        normalized=matrix[np.ix_(self.free,self.free)]*np.outer(self.stability_scale,self.stability_scale)
        value=float(np.linalg.eigvalsh((normalized+normalized.T)/2)[0])
        if not np.isfinite(value) or value<=1e-10:raise RejectedState('Nonpositive or unresolved effective elastic stiffness.')
        return value

    def evaluate(self,state,external):
        state=np.asarray(state,float);external=np.asarray(external,float)
        if state.shape!=(self.unknowns,) or external.shape!=(self.size,) or not np.isfinite(state).all() or not np.isfinite(external).all():
            raise ValueError('Finite, shape-compatible research state and nodal forces are required.')
        nfree=len(self.free);motion=np.zeros(self.size);motion[self.free]=state[:nfree]
        axial=state[nfree:];internal=np.zeros(self.size);matrix=np.zeros((self.size,self.size))
        coupling=np.zeros((self.size,self.count));closure=np.zeros(self.count);force_gradient=np.zeros((self.count,self.size));axial_gradient=np.zeros(self.count)
        forces=[]
        for i,element in enumerate(self.elements):
            d=element.transform@motion[element.indices]
            tangent=element.elastic+axial[i]*element.geometric
            force=tangent@d;change=element.geometric@d
            internal[element.indices]+=element.transform.T@force
            matrix[np.ix_(element.indices,element.indices)]+=element.transform.T@tangent@element.transform
            coupling[element.indices,i]+=element.transform.T@change
            closure[i]=axial[i]-self.axial_selector@force
            force_gradient[i,element.indices]=-self.axial_selector@tangent@element.transform
            axial_gradient[i]=1-self.axial_selector@change
            forces.append(force)
        residual=np.r_[internal[self.free]-external[self.free],closure]
        jacobian=np.block([[matrix[np.ix_(self.free,self.free)],coupling[self.free]],
                           [force_gradient[:,self.free],np.diag(axial_gradient)]])
        force_bound=np.abs(internal[self.free])+np.abs(external[self.free])
        axial_bound=abs(axial)+np.array([abs(self.axial_selector)@abs(f) for f in forces])
        absolute=np.array([1e-9 if dof%6<3 else 1e-8 for dof in self.free])
        limits=np.r_[absolute,np.full(self.count,1e-9)]+1e-10*np.r_[force_bound,axial_bound]
        return dict(residual=residual,jacobian=jacobian,limits=limits,motion=motion,axial=axial.copy(),
                    internal=internal,matrix=matrix,forces=np.array(forces))

    def solve(self,external,initial=None,max_iterations=30):
        if type(max_iterations) is not int or not 1<=max_iterations<=100:raise ValueError('Choose 1–100 Newton iterations.')
        state=np.zeros(self.unknowns) if initial is None else np.array(initial,float,copy=True)
        for iteration in range(max_iterations+1):
            data=self.evaluate(state,external);r=data['residual'];limits=data['limits']
            if np.all(abs(r)<=limits):
                minimum=self._stable(data['matrix']);maximum=0.
                for element,force in zip(self.elements,data['forces']):
                    maximum=max(maximum,*(float(element.section.Phi(*force[list(ids)])) for ids in ((0,4,5),(6,10,11))))
                if not np.isfinite(maximum) or maximum>=1-1e-9:raise RejectedState('Yielding is outside the elastic corrector; no trial state was accepted.')
                data.update(state=state.copy(),iterations=iteration,min_normalized_stiffness=minimum,max_yield_interaction=maximum)
                return data
            if iteration==max_iterations:break
            J=data['jacobian'];columns=1/np.maximum(np.linalg.norm(J,axis=0),np.finfo(float).tiny)
            scaled=J*columns;rows=1/np.maximum(np.linalg.norm(scaled,axis=1),np.finfo(float).tiny)
            try:increment=np.linalg.solve(rows[:,None]*scaled,-rows*r)*columns
            except np.linalg.LinAlgError as error:raise RejectedState('Singular equilibrium/axial Newton system.') from error
            if not np.isfinite(increment).all():raise RejectedState('Nonfinite Newton increment.')
            norm=float(np.max(abs(r)/limits));accepted=False
            for cutback in range(20):
                alpha=2.**-cutback;trial=state+alpha*increment;candidate=self.evaluate(trial,external)
                trial_norm=float(np.max(abs(candidate['residual'])/limits))
                if trial_norm<=(1-1e-4*alpha)*norm or trial_norm<=1.:
                    state=trial;accepted=True;break
            if not accepted:raise RejectedState('Equilibrium line search failed.')
        raise RejectedState('Equilibrium iteration limit reached; no trial state was accepted.')

    def path(self,preload,push,steps):
        if type(steps) is not int or not 1<=steps<=400:raise ValueError('Choose 1–400 research load increments.')
        accepted=[];state=None
        for factor in np.linspace(0.,1.,steps+1):
            # Full target equilibrium, never an accumulated compliance increment.
            data=self.solve(np.asarray(preload)+factor*np.asarray(push),state)
            state=data['state'];data['factor']=float(factor)
            # Dense operators belong to the current Newton solve, not history.
            data.pop('matrix');data.pop('jacobian');accepted.append(data)
        return accepted
