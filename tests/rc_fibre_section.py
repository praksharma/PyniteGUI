"""Research-only monotonic RC fibre-section envelope, ascending concrete only.

Tension-positive stress/strain; eps(y)=eps0-kappa*y, M=-sum(A*y*stress).
No cyclic material history, tensile concrete, descending/crushing branch, bond,
confinement, shear, member/frame solver or design-code capacity claim.
"""
from dataclasses import dataclass
import numpy as np
from scipy.optimize import brentq


@dataclass(frozen=True)
class RCEnvelope:
    fc: float=4.
    peak_strain: float=.002
    steel_E: float=29000.
    steel_yield: float=60.
    hardening_ratio: float=.01

    def __post_init__(self):
        values=(self.fc,self.peak_strain,self.steel_E,self.steel_yield,self.hardening_ratio)
        if not np.isfinite(values).all() or min(values[:4])<=0 or not 0<=self.hardening_ratio<1:
            raise ValueError('Positive finite properties and hardening ratio in [0,1) required.')
        if self.peak_strain>=.02 or self.steel_yield/self.steel_E>=.02:
            raise ValueError('Material strain range exceeds the bounded study.')

    def stress(self,kind,strain):
        if not np.isfinite(strain):raise ValueError('Finite strain required.')
        if kind=='concrete':
            if strain < -self.peak_strain*(1+1e-12):raise ValueError('Descending/crushing concrete branch is unqualified.')
            if strain>=0:return 0.,0.
            r=min(-strain/self.peak_strain,1.)
            return -self.fc*(2*r-r*r),2*self.fc/self.peak_strain*(1-r)
        if kind=='steel':
            if abs(strain)>.02*(1+1e-12):raise ValueError('Reinforcement strain bound exceeded.')
            trial=self.steel_E*strain
            if abs(trial)<=self.steel_yield:return trial,self.steel_E
            return float(np.sign(strain)*(self.steel_yield+self.hardening_ratio*(abs(trial)-self.steel_yield))),self.hardening_ratio*self.steel_E
        raise ValueError('Fibre material must be concrete or steel.')


class MonotonicRCSection:
    def __init__(self,fibres,material=None):
        self.material=RCEnvelope() if material is None else material
        if not isinstance(self.material,RCEnvelope):raise ValueError('RC envelope properties required.')
        self.fibres=tuple(tuple(f) for f in fibres)
        if not self.fibres or len(self.fibres)>4096:raise ValueError('Use 1–4096 fibres.')
        for fibre in self.fibres:
            if len(fibre)!=3:raise ValueError('Each fibre requires area, y, material.')
            area,y,kind=fibre
            if not np.isfinite([area,y]).all() or area<=0 or kind not in ('concrete','steel'):
                raise ValueError('Positive finite area, finite y and valid material required.')

    def evaluate(self,axial_strain,curvature):
        if not np.isfinite([axial_strain,curvature]).all():raise ValueError('Finite strain and curvature required.')
        force=np.zeros(2);tangent=np.zeros((2,2));strains=[];stresses=[]
        for area,y,kind in self.fibres:
            B=np.array([1.,-y]);strain=axial_strain-curvature*y
            stress,modulus=self.material.stress(kind,strain)
            force+=area*stress*B;tangent+=area*modulus*np.outer(B,B)
            strains.append(strain);stresses.append(stress)
        return dict(resultants=force,tangent=tangent,strains=np.array(strains),stresses=np.array(stresses),
            axial_strain=float(axial_strain),curvature=float(curvature),production_ready=False,
            qualification='monotonic_ascending_concrete_fibre_envelope_only')

    def moment_at_axial_force(self,curvature,axial_force):
        if not np.isfinite([curvature,axial_force]).all():raise ValueError('Finite curvature/axial force required.')
        lower=[];upper=[]
        for _,y,kind in self.fibres:
            limit=self.material.peak_strain if kind=='concrete' else .02
            lower.append(-limit+curvature*y)
            upper.append(.02+curvature*y)
        lo=max(lower);hi=min(upper)
        if lo>=hi:raise ValueError('No admissible strain interval.')
        residual=lambda e:self.evaluate(e,curvature)['resultants'][0]-axial_force
        if residual(lo)>0 or residual(hi)<0:raise ValueError('Requested axial force requires an unqualified material branch.')
        strain=brentq(residual,lo,hi,xtol=1e-15)
        r=self.evaluate(strain,curvature);K=r['tangent']
        if K[0,0]<=0:raise ValueError('Axial compatibility is unresolved on a zero-tangent branch.')
        if abs(r['resultants'][0]-axial_force)>1e-7+abs(axial_force)*1e-10:raise ValueError('Axial equilibrium failed.')
        r['flexural_tangent_at_fixed_axial_force']=float(K[1,1]-K[0,1]*K[1,0]/K[0,0])
        return r
