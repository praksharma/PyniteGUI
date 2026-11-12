"""Independent imposed-drift cantilever statics, including compressive softening."""
from math import sin,cos,sqrt,isfinite
from dataclasses import dataclass
from scipy.optimize import brentq


@dataclass(frozen=True)
class DriftHistory:
    configuration: tuple
    rotation: float=0.
    dissipation: float=0.


def solve(length,EA,EI,capacity,drift,vertical,old=None):
    if not all(isfinite(v) for v in (length,EA,EI,capacity,drift,vertical)) or min(length,EA,EI,capacity)<=0:
        raise ValueError('Finite loads/drift and positive finite properties required.')
    configuration=(length,EA,EI,capacity)
    if old is not None and (not isinstance(old,DriftHistory) or old.configuration!=configuration):raise ValueError('Mismatched reference history.')
    previous=0. if old is None else old.rotation
    if not isfinite(previous) or abs(previous)>.25 or (old is not None and (not isfinite(old.dissipation) or old.dissipation<0)):
        raise ValueError('Invalid reference history.')
    stiffness=3*EI/length
    for sign in (0,1,-1):
        def response(psi):
            moment=stiffness*(psi-previous) if sign==0 else sign*capacity
            A=length*(1+vertical/(EA*cos(psi)));B=length*moment*sin(psi)/(EA*cos(psi))
            discriminant=A*A+4*B
            if discriminant<=0:raise ValueError('No positive chord root.')
            chord=(A+sqrt(discriminant))/2
            return chord*sin(psi)-drift
        try:psi=brentq(response,-.2,.2,xtol=1e-14)
        except ValueError:continue
        moment=stiffness*(psi-previous) if sign==0 else sign*capacity
        alpha=previous if sign==0 else psi-moment/stiffness
        if abs(moment)>capacity*(1+1e-10) or sign*(alpha-previous)<-1e-12 or abs(alpha)>.25:continue
        A=length*(1+vertical/(EA*cos(psi)));B=length*moment*sin(psi)/(EA*cos(psi))
        chord=(A+sqrt(A*A+4*B))/2
        if abs(chord/length-1)>.01:continue
        force=(moment/chord+vertical*sin(psi))/cos(psi)
        axial=force*sin(psi)+vertical*cos(psi)
        Q=force*cos(psi)-vertical*sin(psi)
        modulus=stiffness if sign==0 else 0.
        numerator=modulus+chord*axial-length*Q*Q/EA
        coupling=length*sin(psi)*Q/EA+chord*cos(psi)
        # Avoid dividing by the force-control tangent at its zero crossing.
        slope=numerator/(length*sin(psi)**2/EA*numerator+coupling*coupling)
        state=DriftHistory(configuration,alpha,capacity*abs(alpha-previous)+(0. if old is None else old.dissipation))
        return dict(state=state,motion=(drift,chord*cos(psi)-length,-psi-moment/(2*stiffness)),
            actuator_load=force,actuator_tangent=slope,moment=moment,active=sign!=0,
            elastic_energy=axial**2*length/(2*EA)+moment**2/(2*stiffness),production_ready=False)
    raise ValueError('No reference branch within stated drift/strain/angle bounds.')
