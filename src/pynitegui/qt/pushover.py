"""First-order steel I-section pushover with checked accepted-step histories.

PyNite supplies its associative axial/biaxial-bending interaction law and plastic
reduction. Brecon validates the elastic preload, actual tangent, joint/global
balance and yield overshoot before recording any increment. Failed steps never
become ordinary solved frame results.
"""
from dataclasses import dataclass,asdict,field,replace
from datetime import datetime,timezone
from importlib.metadata import version
from inspect import signature
import hashlib
import json
from types import SimpleNamespace
import uuid

import numpy as np
from scipy.linalg import eigvalsh
from scipy.sparse import diags
from scipy.sparse.linalg import eigsh
from Pynite.Section import Section as EngineSection

from .analysis import analyze,FrameSolver,model_signature
from .equilibrium import check_equilibrium,FORCE_TOLERANCE,MOMENT_TOLERANCE,RELATIVE_TOLERANCE
from .inclined_supports import free_basis,factor_stiffness
from .model import finite_number
from .support_movements import has_movements
from .unilateral import has_unilateral

MAX_HISTORY_VALUES=3_000_000
DOFS=('DX','DY','DZ','RX','RY','RZ')
COMPONENTS=('FX','FY','FZ','MX','MY','MZ')


@dataclass(frozen=True)
class PushoverSettings:
    preload: str
    push: str
    control_node: str
    control_direction: str
    stop_limit: float
    base_nodes: tuple
    resultant: str = 'FX'
    steps: int = 500
    iteration_limit: int = 30
    yield_tolerance: float = .01

    def validate(self,project):
        if any(not isinstance(name,str) or name not in project.combinations for name in (self.preload,self.push)):
            raise ValueError('Choose existing preload and full push-pattern combinations.')
        if not isinstance(self.control_node,str) or self.control_node not in project.nodes:
            raise ValueError('Choose an existing control node.')
        dofs=DOFS if getattr(project,'dimension','2D')=='3D' else ('DX','DY','RZ')
        if self.control_direction not in dofs:raise ValueError('Choose a control direction present in this model.')
        if project.nodes[self.control_node].restraints[dofs.index(self.control_direction)]:
            raise ValueError('Choose an unrestrained control direction.')
        if not finite_number(self.stop_limit) or self.stop_limit<=0:
            raise ValueError('The absolute displacement/rotation stop limit must be finite and positive.')
        if type(self.steps) is not int or not 1<=self.steps<=2000:raise ValueError('Choose 1–2000 load steps.')
        if type(self.iteration_limit) is not int or not 1<=self.iteration_limit<=500:raise ValueError('Choose 1–500 step retries.')
        if not finite_number(self.yield_tolerance) or not 0<=self.yield_tolerance<=.02:
            raise ValueError('The dimensionless yield-surface overshoot tolerance must be between 0 and 0.02.')
        if not isinstance(self.base_nodes,(tuple,list)) or not self.base_nodes or any(not isinstance(n,str) or n not in project.nodes for n in self.base_nodes) or len(set(self.base_nodes))!=len(self.base_nodes):
            raise ValueError('Select distinct existing reaction nodes for the capacity curve.')
        if any(not any(project.nodes[n].restraints) and not any(project.nodes[n].springs) for n in self.base_nodes):
            raise ValueError('Capacity-curve reaction nodes must have physical supports or ground springs.')
        components=COMPONENTS if getattr(project,'dimension','2D')=='3D' else ('FX','FY','MZ')
        if self.resultant not in components:raise ValueError('Choose a reaction component present in this model.')
        count=(self.steps+1)*(12*len(project.nodes)+14*len(project.members))
        if count>MAX_HISTORY_VALUES:raise ValueError('Requested full step histories exceed the bounded result size; reduce load steps or model size.')


def pushover_issue(project):
    if getattr(project,'surfaces',{}):return 'Steel pushover is frame-only; nonlinear surfaces/slabs are not supported.'
    if has_unilateral(project):return 'Steel pushover currently requires bilateral members and ground springs.'
    if has_movements(project) or any(node.support=='inclined' for node in project.nodes.values()):
        return 'Steel pushover does not yet support inclined or imposed support constraints.'
    if any(m.kind!='frame' or any(any(end) for end in m.end_releases) or any(getattr(m,key,False) for key in
           ('release_start_rx','release_end_rx','release_start_ry','release_end_ry','release_start_z','release_end_z')) for m in project.members.values()):
        return 'Steel pushover currently requires unreleased frame members.'
    if not any(project.sections[m.section].steel_material is not None for m in project.members.values()):
        return 'Assign at least one explicit steel I-section plastic profile (positive fy, Zy/Zz and matching material binding).'
    return None


class StopPushover(ValueError):
    def __init__(self,kind,message):super().__init__(message);self.kind=kind


class ElasticPushoverSection(EngineSection):
    """An explicitly elastic member within a mixed elastic/plastic frame."""
    def __init__(self,*args):
        super().__init__(*args)
        # Newer PyNite reads these unused capacity attributes before evaluating
        # Phi. Neutral finite placeholders satisfy that interface only: Phi/G
        # remain exactly zero, so this section can never trigger plasticity.
        self.material=SimpleNamespace(fy=1.)
        self.Zy=self.Zz=1.

    def Phi(self,fx=0,my=0,mz=0):return 0.
    def G(self,fx=0,my=0,mz=0):return np.zeros((6,1))


class PushoverSolver(FrameSolver):
    def Km(self,combo_name='Combo 1',push_combo='Push',step_num=1,log=False,sparse=True):
        matrix=super().Km(combo_name,push_combo,step_num,log,sparse)
        self._plastic_progress(f'Steel pushover: load step {step_num}/{self._plastic_steps}; checking plastic tangent')
        check_tangent(self,matrix)
        return matrix


def check_tangent(model,reduction):
    elastic=model._plastic_elastic;R=model._plastic_normalized_basis
    tangent=(R.T @ (elastic+reduction.tocsr()) @ R).tocsr()
    if not np.isfinite(tangent.data).all():raise StopPushover('nonfinite','The plastic tangent contains nonfinite values.')
    if tangent.shape[0]==0:return
    cancellation=abs(R).T @ (abs(elastic)+abs(reduction.tocsr())) @ abs(R)
    limit=10*np.finfo(float).eps*elastic.shape[0]*max(1.,float(np.asarray(cancellation.sum(axis=1)).max()))
    if tangent.shape[0]<=600:
        value=float(eigvalsh(((tangent+tangent.T)*.5).toarray(),subset_by_index=(0,0))[0])
    else:
        value=float(eigsh((tangent+tangent.T)*.5,k=1,which='SA',return_eigenvectors=False,tol=1e-9,
            maxiter=max(1000,10*tangent.shape[0]),v0=np.random.default_rng(0).normal(size=tangent.shape[0]))[0])
    if value<=limit:raise StopPushover('limit_state','Nonpositive or unresolved plastic tangent: a mechanism/limit state prevents further load increments.')


def prepare_model(project,settings,phase):
    working=project.clone();working.analysis_method='linear'
    private='Brecon push increment'
    while private in working.load_cases:private+='x'
    working.load_cases.append(private)
    has_push=False
    for load in (*project.loads.values(),*project.self_weight_loads()):
        factor=project.combinations[settings.push].get(load.case,0.)
        if factor:
            if not load.magnitude and (load.kind!='distributed' or not load.end_magnitude):continue
            if load.target in project.members:
                if load.kind=='distributed' or load.position not in (0.,1.):
                    raise ValueError('The push pattern requires nodal forces/moments or member-end point loads. Interior/distributed member-load increments are not validated; keep member loads in the elastic preload or define an explicit nodal push pattern.')
                member=project.members[load.target]
                target=member.start if load.position==0. else member.end
                for direction,magnitude in load.components(project):
                    axis='XYZ'.index(direction[-1].upper())
                    vector=np.eye(3)[axis]*magnitude*factor
                    if direction!=direction.upper():
                        from .spatial_results import member_axes
                        vector=member_axes(project,load.target).T @ vector
                    for index,value in enumerate(vector):
                        if not value:continue
                        key=working.next_name('PX',working.loads)
                        working.loads[key]=replace(load,name=key,target=target,direction=('M' if direction.upper().startswith('M') else 'F')+'XYZ'[index],
                            case=private,magnitude=float(value),position=.5,angle=0.,**({'elevation':0.} if hasattr(load,'elevation') else {}))
            else:
                key=working.next_name('PX',working.loads)
                working.loads[key]=replace(load,name=key,case=private,magnitude=load.magnitude*factor,end_magnitude=load.end_magnitude*factor)
            has_push=True
    if not has_push:raise ValueError('The full push pattern has no nonzero nodal/member loads.')
    working.combinations={settings.preload:dict(project.combinations[settings.preload])}
    model=analyze(working,progress=phase).solver
    # Preserve object identity: every existing member/node refers to this checked
    # elastic model. Only its plastic-tangent hook changes.
    model.__class__=PushoverSolver
    for name,material in project.materials.items():model.materials[name].fy=material.fy
    for name,section in project.sections.items():
        if section.steel_material is not None:
            del model.sections[name]
            model.add_steel_section(name,section.A,section.Iy,section.Iz,section.J,section.Zy,section.Zz,section.steel_material)
        else:model.sections[name]=ElasticPushoverSection(model,name,section.A,section.Iy,section.Iz,section.J)
    for name,member in project.members.items():
        model.members[name].section=model.sections[member.section]
        for sub in model.members[name].sub_members.values():sub.section=model.sections[member.section]
    private_combo='Brecon push steps'
    while private_combo==settings.preload:private_combo+='x'
    model.add_load_combo(private_combo,{private:1/settings.steps})
    basis,labels,translations=free_basis(model,working)
    elastic=model.Ke(settings.preload,check_stability=False,sparse=True).tocsr()
    coordinates=np.array([(node.X,node.Y,node.Z) for node in model.nodes.values()])
    transform,_,scale=factor_stiffness(elastic,basis,labels,translations,max(1.,float(np.linalg.norm(np.ptp(coordinates,axis=0)))))
    model._plastic_elastic=elastic;model._plastic_normalized_basis=transform @ diags(scale)
    model._plastic_progress=phase;model._plastic_steps=settings.steps
    return model,basis,private_combo


def section_states(project,model,combination,*,preload=False,tolerance=.01):
    forces=[];phis=[];states=[]
    for name,definition in project.members.items():
        member=model.members[name];parts=list(member.sub_members.values())
        if len(parts)!=1:raise ValueError('Plastic hinges require explicit editable member endpoints; implicit subdivision is not accepted here.')
        sub=parts[0];sub._solved_combo=None
        force=sub.f(combination)[:,0]
        if not np.isfinite(force).all():raise StopPushover('nonfinite','Nonfinite member-end forces; the increment was not accepted.')
        forces.append(force.copy())
        if project.sections[definition.section].steel_material is None:
            phis.append((0.,0.));states.append(('Elastic model','Elastic model'));continue
        ends=[float(sub.section.Phi(*force[[0,4,5]])),float(sub.section.Phi(*force[[6,10,11]]))]
        # Phi is monotone in absolute axial/bending magnitudes. Independent
        # extrema give a conservative within-member bound, never an invented
        # common station. Refine if that bound cannot certify an interior field.
        peak=[max(abs(getattr(member,prefix+'_'+kind)(*args)) for prefix in ('min','max'))
              for kind,args in (('axial',(combination,)),('moment',('My',combination)),('moment',('Mz',combination)))]
        upper=float(sub.section.Phi(*peak))
        if not np.isfinite(upper):raise StopPushover('nonfinite','Nonfinite yield interaction; the increment was not accepted.')
        if preload and upper>=1-1e-9:
            raise ValueError('The primary preload must stay strictly elastic in every plastic section; reduce preload or revise the initial state.')
        if upper>1+tolerance:
            if max(ends)>1+tolerance:raise StopPushover('yield_overshoot','The increment overshoots the yield surface; increase load steps and compare refinement.')
            raise StopPushover('interior_yield','The interior yield bound exceeds the end-hinge scope; subdivide members at potential hinge locations and compare refinement.')
        if upper>max(1.,max(ends))+1e-9:
            raise StopPushover('interior_yield','An interior section may reach yield before the explicit end hinges; subdivide members at potential hinge locations and compare refinement.')
        phis.append(ends)
        states.append(tuple('Unloading' if reversal else 'At yield surface' if phi>=1 else 'Elastic'
                            for phi,reversal in zip(ends,(sub.i_reversal,sub.j_reversal))))
    return np.array(forces),np.array(phis),states


def applied_reference(project,model,combination):
    fake_solver=SimpleNamespace(nodes=model.nodes,members=model.members,load_combos={key:SimpleNamespace(factors=value) for key,value in project.combinations.items()})
    result=SimpleNamespace(solver=fake_solver,reactions={},combination=combination,spatial=getattr(project,'dimension','2D')=='3D',
                           model_signature=model_signature(project),analysis_method='linear')
    return check_equilibrium(project,result)


@dataclass
class PushoverResult:
    project: object
    settings: PushoverSettings
    factors: np.ndarray
    displacements: np.ndarray
    reactions: np.ndarray
    end_forces: np.ndarray
    phis: np.ndarray
    end_states: list
    curve: np.ndarray
    equilibrium: np.ndarray
    equilibrium_limits: np.ndarray
    termination: str
    message: str
    model_signature: str
    configuration_signature: str
    engine_version: str
    axes: dict
    snapshot_id: str=field(default_factory=lambda:uuid.uuid4().hex[:12])
    analyzed_at: str=field(default_factory=lambda:datetime.now(timezone.utc).isoformat(timespec='seconds'))

    @property
    def complete(self):return self.termination in ('full_pattern','target_reached')

    def metadata(self):
        from pynitegui import __version__
        origin=next(iter(self.project.nodes.values()))
        coords=origin.coords if hasattr(origin,"coords") else (origin.x,origin.y,0.)
        return dict(snapshot_id=self.snapshot_id,analyzed_at=self.analyzed_at,model_signature=self.model_signature,
            configuration_signature=self.configuration_signature,application=f'Brecon {__version__}',engine=f'PyniteFEA {self.engine_version}',analysis_kind='steel_pushover',
            reaction_moment_origin={'node':next(iter(self.project.nodes)),'canonical_coordinates':list(coords)},
            settings=asdict(self.settings),termination=self.termination,message=self.message,complete=self.complete,
            accepted_steps=len(self.factors)-1,accepted_factor=float(self.factors[-1]),full_pattern_applied=bool(self.factors[-1]>=1-1e-10),
            convention='First-order steel I-section axial/biaxial-bending interaction at explicit member ends. No P-Delta, RC constitutive model, hardening, shear/torsional yielding, fracture or post-mechanism response. Member tables are node-on-member local end actions; joint motions include preload. Capacity reaction moments are about the first model node. Partial results contain only physically checked accepted steps.')


def analyze_pushover(project,settings,progress=None):
    phase=progress or (lambda message:None)
    project.validate();settings.validate(project)
    issue=pushover_issue(project)
    if issue:raise ValueError(issue)
    source_signature=model_signature(project);engine_version=version('pynitefea')
    configuration=hashlib.sha256(json.dumps({'model':source_signature,'formulation':'steel_I_first_order_v1','engine':engine_version,**asdict(settings)},sort_keys=True,allow_nan=False).encode()).hexdigest()
    phase('Steel pushover: checking elastic preload')
    model,basis,push_combo=prepare_model(project,settings,phase)
    section_states(project,model,settings.preload,preload=True)
    initial=applied_reference(project,model,settings.preload);push=applied_reference(project,model,settings.push)
    node_order=list(project.nodes);node_indices={name:i for i,name in enumerate(node_order)}
    positions=np.array([(model.nodes[name].X,model.nodes[name].Y,model.nodes[name].Z) for name in node_order])
    origin=positions[0];relative=positions-origin
    base_indices=[node_indices[name] for name in settings.base_nodes]
    P0=model.P(settings.preload).reshape(-1);Pi=model.P(push_combo).reshape(-1)
    stiffness=np.zeros((len(node_order),6))
    for i,name in enumerate(node_order):
        keys=DOFS if getattr(project,'dimension','2D')=='3D' else ('DX','DY','RZ')
        for key,k in zip(keys,project.nodes[name].springs):stiffness[i,DOFS.index(key)]=k
    factors=[];motions=[];reactions=[];end_forces=[];phis=[];states=[];curve=[];balances=[];balance_limits=[]

    def capture(step):
        factor=step/settings.steps
        if step:
            model._pushover_state[settings.preload].update(step_num=step,load_factor=factor)
        force,phi,end_state=section_states(project,model,settings.preload,tolerance=settings.yield_tolerance)
        D=np.array([[getattr(model.nodes[name],dof)[settings.preload] for dof in DOFS] for name in node_order])
        if not np.isfinite(D).all():raise StopPushover('nonfinite','Nonfinite joint motions; the increment was not accepted.')
        internal=np.zeros_like(D)
        for index,(name,definition) in enumerate(project.members.items()):
            actual=model.members[name].T().T @ force[index]
            internal[node_indices[definition.start]]+=actual[:6];internal[node_indices[definition.end]]+=actual[6:]
        external=(P0+step*Pi).reshape(-1,6)
        residual=internal-external
        closure=np.asarray(basis.T @ (residual+stiffness*D).reshape(-1)).ravel()
        bound=np.asarray(abs(basis).T @ (abs(internal)+abs(external)+abs(stiffness*D)).reshape(-1)).ravel()
        absolute=np.array([FORCE_TOLERANCE if i%6<3 else MOMENT_TOLERANCE for i in range(D.size)])
        reduced_absolute=np.asarray(abs(basis).T @ absolute).ravel()
        if np.any(abs(closure)>reduced_absolute+1e-10*bound):raise StopPushover('joint_equilibrium','Free-joint equilibrium failed; the increment was not accepted.')
        R=np.zeros_like(D)
        for i,name in enumerate(node_order):
            for j,dof in enumerate(DOFS):
                R[i,j]=residual[i,j] if getattr(model.nodes[name],'support_'+dof) else -stiffness[i,j]*D[i,j]
        force_parts=R[:,:3];moment_parts=R[:,3:]+np.cross(relative,force_parts)
        total=np.r_[force_parts.sum(axis=0),moment_parts.sum(axis=0)]
        scale_R=np.r_[abs(force_parts).sum(axis=0),abs(moment_parts).sum(axis=0)]
        balance=[];limits=[]
        for first,second in zip(initial.rows,push.rows):
            j=COMPONENTS.index(first.component);abs_limit=FORCE_TOLERANCE if j<3 else MOMENT_TOLERANCE
            applied=first.applied+factor*second.applied
            source_scale=(first.tolerance-abs_limit+factor*(second.tolerance-abs_limit))/RELATIVE_TOLERANCE
            limit=abs_limit+RELATIVE_TOLERANCE*(max(0.,source_scale)+scale_R[j])
            error=float(applied+total[j])
            if not np.isfinite(error) or abs(error)>limit:raise StopPushover('global_equilibrium','Global force/moment equilibrium failed; the increment was not accepted.')
            balance.append(error);limits.append(limit)
        selected=R[base_indices]
        capacity=np.r_[selected[:,:3].sum(axis=0),(selected[:,3:]+np.cross(relative[base_indices],selected[:,:3])).sum(axis=0)]
        control=float(D[node_indices[settings.control_node],DOFS.index(settings.control_direction)])
        factors.append(factor);motions.append(D);reactions.append(R);end_forces.append(force);phis.append(phi);states.append(end_state)
        curve.append((control,float(capacity[COMPONENTS.index(settings.resultant)])));balances.append(balance);balance_limits.append(limits)
        return control

    capture(0)
    def accept(combo):
        step=len(factors)
        control=capture(step)
        # Also identify a newly formed mechanism at the accepted endpoint; it
        # must not silently be labelled a stable full-pattern solution.
        reduction=super(PushoverSolver,model).Km(combo,push_combo,step,False,True)
        check_tangent(model,reduction)
        return control
    termination,message='full_pattern','Full requested push pattern applied.'
    try:
        if abs(curve[0][0])>=settings.stop_limit:
            termination,message='target_reached','The elastic preload already reaches the configured absolute control limit; no push increment was applied.'
        else:
            first_order={"P_Delta":False} if "P_Delta" in signature(model.analyze_pushover).parameters else {}
            model.analyze_pushover(push_combo=push_combo,max_iter=settings.iteration_limit,tol=1e-10,
                check_stability=False,sparse=True,control_node=settings.control_node,control_direction=settings.control_direction,
                control_limit=settings.stop_limit,traces={'Brecon accepted step':accept},**first_order)
            state=model._pushover_state[settings.preload]
            if state['status']=='target_displacement_reached':termination,message='target_reached','The configured absolute control limit was reached.'
    except StopPushover as error:
        if len(factors)<=1:raise ValueError(str(error)) from error
        termination,message=error.kind,str(error)
    except RuntimeError as error:
        # PyNite wraps trace exceptions. Preserve our physical rejection and
        # accepted prefix without treating unrelated programming errors as data.
        if isinstance(error.__cause__,StopPushover):
            cause=error.__cause__
            if len(factors)<=1:raise ValueError(str(cause)) from error
            termination,message=cause.kind,str(cause)
        else:
            if 'did not converge' not in str(error) or len(factors)<=1:raise
            termination,message='not_converged',str(error)
    phase('Steel pushover: collecting checked accepted-step history')
    return PushoverResult(project.clone(),settings,np.array(factors),np.array(motions),np.array(reactions),np.array(end_forces),np.array(phis),states,
        np.array(curve),np.array(balances),np.array(balance_limits),termination,message,source_signature,configuration,engine_version,
        {name:model.members[name].T()[:3,:3] for name in project.members})
