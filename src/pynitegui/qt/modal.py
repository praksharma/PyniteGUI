"""Small-vibration eigenmodes of bilateral elastic frames with explicit mass.

Use PyNite elastic stiffness, but assemble physical mass explicitly. In the
locked engine, member-load lumping can create negative mass, and M() injects
artificial inertia into zero-mass DOFs. Solve M phi = mu K phi instead: K is
positive definite and massless coordinates need no stabilization mass.
"""
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
import hashlib
import json
import math
import uuid
from importlib.metadata import version

import numpy as np
from scipy.linalg import eigh
from scipy.sparse import coo_matrix, diags
from scipy.sparse.linalg import LinearOperator, eigsh

from .analysis import analyze, model_signature
from .inclined_supports import free_basis, factor_stiffness
from .model import finite_number
from .support_movements import has_movements
from .unilateral import has_unilateral

STANDARD_GRAVITY = 9.80665/.0254  # canonical in/s²
DOFS = ('DX','DY','DZ','RX','RY','RZ')


@dataclass(frozen=True)
class ModalSettings:
    combination: str
    modes: int = 3
    direction: str = 'Y'
    gravity: float = STANDARD_GRAVITY

    def validate(self, project):
        if not isinstance(self.combination,str) or self.combination not in project.combinations:
            raise ValueError('Choose an existing mass-source combination.')
        if type(self.modes) is not int or not 1 <= self.modes <= 50:
            raise ValueError('Request an integer from 1 to 50 modes.')
        if self.direction not in ('X','Y','Z') or (self.direction == 'Z' and getattr(project,'dimension','2D') != '3D'):
            raise ValueError('Choose a global mass direction present in this model (X/Y, or Z in 3D).')
        if not finite_number(self.gravity) or self.gravity <= 0:
            raise ValueError('Gravity must be finite and positive, in canonical in/s².')
        if any(factor < 0 for factor in project.combinations[self.combination].values()):
            raise ValueError('Mass-source combination factors must be nonnegative; weight signs are converted to positive mass individually.')


def modal_issue(project):
    if getattr(project,'surfaces',{}):
        return 'Modal analysis currently supports frame-only models; surface mass and shell modes are not validated.'
    if has_unilateral(project):
        return 'Modal analysis requires bilateral members/support springs; vibration about a solved contact state is not implemented.'
    if any(member.kind != 'frame' or any(any(end) for end in member.end_releases) or
           any(getattr(member,key,False) for key in ('release_start_rx','release_end_rx','release_start_ry','release_end_ry','release_start_z','release_end_z'))
           for member in project.members.values()):
        return 'Modal analysis currently requires unreleased frame members; truss/released mass recovery is not validated.'
    if has_movements(project):
        return 'Modal analysis with imposed support motions is not validated; use a copy with zero prescribed motions.'
    return None


def interpolation(length, fraction):
    """Euler–Bernoulli centreline translation in member-local axes."""
    t=fraction
    h1,h2,h3,h4=1-3*t*t+2*t**3,t-2*t*t+t**3,3*t*t-2*t**3,-t*t+t**3
    shape=np.zeros((3,12))
    shape[0,[0,6]]=(1-t,t)
    shape[1,[1,5,7,11]]=(h1,length*h2,h3,length*h4)
    shape[2,[2,4,8,10]]=(h1,-length*h2,h3,-length*h4)
    return shape


def projected_force(load, project, model, direction, magnitude=None):
    value=0.
    for key, component in load.components(project,magnitude):
        if not key.upper().startswith('F'):
            continue
        vector=np.eye(3)['XYZ'.index(key[-1].upper())]*component
        if key != key.upper():
            vector=model.members[load.target].T()[:3,:3].T @ vector
        value+=vector['XYZ'.index(direction)]
    return float(value)


def mass_matrix(project, model, settings):
    """Consistent line/point masses; material polar inertia only for self-weight.

    A scalar weight component supplies isotropic translational mass. Each line
    load is integrated at its real stations, not lumped at a guessed centroid.
    Four-point Gauss integration is exact for cubic shape products times a
    linearly varying mass. No cancellation between separate physical weights.
    """
    rows,columns,values,source=[],[],[],[]
    size=6*len(model.nodes)
    factors=project.combinations[settings.combination]
    gauss,weights=np.polynomial.legendre.leggauss(4)
    definitions=[(load,False) for load in project.loads.values()]+[(load,True) for load in project.self_weight_loads()]
    for load,generated in definitions:
        factor=factors.get(load.case,0.)
        if factor == 0:continue
        first=factor*projected_force(load,project,model,settings.direction)
        last=factor*projected_force(load,project,model,settings.direction,load.end_magnitude) if load.kind == 'distributed' else first
        if first == 0 and last == 0:continue
        if first*last < 0:
            raise ValueError(f'Mass source {load.name}: split a sign-changing distributed weight before modal analysis.')
        if load.target in project.nodes:
            weight=abs(first)
            indices=model.nodes[load.target].ID*6+np.arange(3)
            block=np.eye(3)*weight/settings.gravity
        else:
            member=model.members[load.target]
            length=member.L();transform=member.T()
            indices=np.r_[member.i_node.ID*6+np.arange(6),member.j_node.ID*6+np.arange(6)]
            block=np.zeros((12,12))
            if load.kind == 'distributed':
                left,right=load.position,load.end_position
                weight=(abs(first)+abs(last))*.5*(right-left)*length
                for point,quadrature in zip(gauss,weights):
                    t=left+(point+1)*.5*(right-left)
                    density=(abs(first)+(abs(last)-abs(first))*(t-left)/(right-left))/settings.gravity
                    shape=interpolation(length,t)
                    local=shape.T @ shape
                    if generated:
                        section=project.sections[project.members[load.target].section]
                        twist=np.zeros(12);twist[[3,9]]=(1-t,t)
                        local+=np.outer(twist,twist)*(section.Iy+section.Iz)/section.A
                    block+=density*quadrature*.5*(right-left)*length*local
            else:
                weight=abs(first)
                shape=interpolation(length,load.position)
                block=weight/settings.gravity*(shape.T @ shape)
            block=transform.T @ block @ transform
        rr,cc=np.meshgrid(indices,indices,indexing='ij')
        rows.extend(rr.ravel());columns.extend(cc.ravel());values.extend(block.ravel())
        source.append(dict(load=load.name,case=load.case,generated_self_weight=generated,weight=float(weight)))
    matrix=coo_matrix((values,(rows,columns)),shape=(size,size)).tocsr()
    if not source or not np.isfinite(matrix.data).all():
        raise ValueError('No finite positive mass was found in the selected load direction/combination.')
    return matrix,source


@dataclass
class ModalResult:
    settings: ModalSettings
    project: object
    frequencies: np.ndarray
    shapes: np.ndarray  # [mode,node,6], max translational component = 1
    axes: dict
    source: list
    residuals: np.ndarray
    orthogonality_error: float
    model_signature: str
    configuration_signature: str
    normalization: list
    engine_version: str
    snapshot_id: str = field(default_factory=lambda:uuid.uuid4().hex[:12])
    analyzed_at: str = field(default_factory=lambda:datetime.now(timezone.utc).isoformat(timespec='seconds'))

    @property
    def periods(self):return 1/self.frequencies

    def metadata(self):
        from pynitegui import __version__
        return dict(snapshot_id=self.snapshot_id,analyzed_at=self.analyzed_at,model_signature=self.model_signature,
                    application=f'Brecon {__version__}',engine=f'PyniteFEA {self.engine_version}',formulation='Euler–Bernoulli centreline consistent mass; physical polar rotary inertia for generated self-weight; zero-mass coordinates retained without artificial inertia.',
                    configuration_signature=self.configuration_signature,analysis_kind='modal',settings=asdict(self.settings),
                    normalization=self.normalization,
                    convention='Translation-normalized modes: translations per inch of reference amplitude, rotations rad/in. Rotation-only modes: translations in/rad, rotations per rad of reference amplitude. Arbitrary mode sign; no static forces/reactions.',
                    mass_rule='Absolute selected force component / positive gravity, separately for each nonnegative-factored load. Density adds mass only through selected generated self-weight. No artificial inertia.',
                    total_weight_kip=sum(item['weight'] for item in self.source),orthogonality_error=self.orthogonality_error)


def analyze_modal(project, settings, progress=None):
    phase=progress or (lambda message:None)
    project.validate();settings.validate(project)
    issue=modal_issue(project)
    if issue:raise ValueError(issue)
    signature=model_signature(project)
    engine_version=version('pynitefea')
    configuration=hashlib.sha256(json.dumps({'model':signature,'formulation':'modal_consistent_v1','engine':engine_version,**asdict(settings)},sort_keys=True,allow_nan=False).encode()).hexdigest()
    phase('Modal: building and checking elastic frame stiffness')
    # Reuse existing topology, support, physical member and stability validation.
    elastic=project.clone();elastic.analysis_method='linear'
    elastic.combinations={settings.combination:dict(project.combinations[settings.combination])}
    model=analyze(elastic,progress=phase).solver
    K=model.Ke(settings.combination,check_stability=False,sparse=True).tocsr()
    basis,labels,translations=free_basis(model,elastic)
    coords=np.array([(n.X,n.Y,n.Z) for n in model.nodes.values()])
    transform,factor,scale=factor_stiffness(K,basis,labels,translations,max(1.,float(np.linalg.norm(np.ptp(coords,axis=0)))))
    if not len(labels):raise ValueError('No free vibration coordinates remain after support constraints.')
    phase('Modal: integrating the explicit mass source')
    M,source=mass_matrix(project,model,settings)
    R=transform @ diags(scale)
    stiffness=(R.T @ K @ R).tocsr();mass=(R.T @ M @ R).tocsr()
    mass_scale=float(abs(mass).sum(axis=1).max())
    if not np.isfinite(mass_scale) or mass_scale <= 0:raise ValueError('The free structure has no positive dynamic mass.')
    mass=mass/mass_scale
    count=len(labels)
    if settings.modes > count:raise ValueError(f'Only {count} free vibration coordinates are available.')
    phase(f'Modal: solving for {settings.modes} finite modes')
    if count <= 600:
        values,vectors=eigh(mass.toarray(),stiffness.toarray(),subset_by_index=(count-settings.modes,count-1))
    else:
        if settings.modes >= count:raise ValueError('For large sparse models request fewer modes than free coordinates.')
        inverse=LinearOperator(stiffness.shape,matvec=factor.solve)
        values,vectors=eigsh(mass,k=settings.modes,M=stiffness,Minv=inverse,which='LA',tol=1e-10,
                            maxiter=max(1000,10*count),v0=np.random.default_rng(0).normal(size=count))
    order=np.argsort(values)[::-1];values,vectors=values[order],vectors[:,order]
    limit=100*np.finfo(float).eps*count*max(float(abs(values).max()),np.finfo(float).tiny)
    if not np.isfinite(values).all() or np.any(values <= limit):
        raise ValueError('Fewer finite mass-carrying modes than requested; reduce the mode count. Massless coordinates were not given artificial inertia.')
    omega2=1/(values*mass_scale)
    physical=np.asarray(R @ vectors)
    mass_gram=physical.T @ M @ physical
    physical/=np.sqrt(np.diag(mass_gram))[None,:]
    gram=physical.T @ M @ physical
    orthogonality=float(np.max(abs(gram-np.eye(settings.modes))))
    if not np.isfinite(orthogonality) or orthogonality > 1e-7:
        raise ValueError('Modal mass orthogonality failed; no results were accepted.')
    residuals=[]
    for index,frequency2 in enumerate(omega2):
        vector=vectors[:,index]
        left=stiffness @ vector;right=(mass @ vector)*(frequency2*mass_scale)
        residual=float(np.linalg.norm(left-right)/max(np.linalg.norm(left)+np.linalg.norm(right),np.finfo(float).tiny))
        if not np.isfinite(residual) or residual > 1e-7:
            raise ValueError('Modal eigen-equation residual failed; no results were accepted.')
        residuals.append(residual)
    shapes=physical.T.reshape(settings.modes,len(model.nodes),6)
    normalization=[]
    span=max(1.,float(np.linalg.norm(np.ptp(coords,axis=0))))
    for shape in shapes:
        rotation_only=float(np.max(abs(shape[:,:3]))) < 1e-10*span*float(np.max(abs(shape[:,3:])))
        entries=shape[:,3:] if rotation_only else shape[:,:3]
        reference=entries.ravel()[int(np.argmax(abs(entries)))]
        if not np.isfinite(reference) or reference == 0:
            raise ValueError('A requested mode has no finite displacement reference; no results were accepted.')
        shape/=reference
        normalization.append('rotation' if rotation_only else 'translation')
    phase('Modal: collecting frequencies and normalized mode shapes')
    return ModalResult(settings,project.clone(),np.sqrt(omega2)/(2*math.pi),shapes,
        {name:model.members[name].T()[:3,:3] for name in project.members},source,np.array(residuals),orthogonality,signature,configuration,normalization,engine_version)
