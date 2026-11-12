"""Independent scalar statics oracle for a tension-stabilized hinged cantilever.

This checks the specified corotational member law, not a continuum elastoplastic
beam. Solve current-chord force/moment balance after eliminating the free end
moment; no frame assembly, energy Hessian or frame solver is imported.
"""
from dataclasses import dataclass
from math import sin, cos, isfinite
from scipy.optimize import brentq


@dataclass(frozen=True)
class CantileverHistory:
    configuration: tuple
    plastic_rotation: float=0.
    dissipation: float=0.


def solve(length, axial_rigidity, bending_rigidity, capacity, lateral, tension, old=None):
    values=(length,axial_rigidity,bending_rigidity,capacity,lateral,tension)
    if not all(isfinite(v) for v in values) or min(length,axial_rigidity,bending_rigidity,capacity,tension)<=0:
        raise ValueError('Positive finite properties/tension and finite lateral load required.')
    configuration=tuple(map(float,values[:4]))
    if old is not None and (not isinstance(old,CantileverHistory) or old.configuration!=configuration):
        raise ValueError('Reference history belongs to another configuration.')
    previous=0. if old is None else old.plastic_rotation
    if not isfinite(previous) or abs(previous)>.25 or (old is not None and (not isfinite(old.dissipation) or old.dissipation<0)):
        raise ValueError('Invalid committed reference history.')
    stiffness=3*bending_rigidity/length
    for sign in (0,1,-1):
        def response(psi):
            axial=lateral*sin(psi)+tension*cos(psi)
            transverse=lateral*cos(psi)-tension*sin(psi)
            chord=length*(1+axial/axial_rigidity)
            moment=stiffness*(psi-previous) if sign==0 else sign*capacity
            return moment-chord*transverse
        try:psi=brentq(response,-.2,.2,xtol=1e-14)
        except ValueError:continue
        moment=stiffness*(psi-previous) if sign==0 else sign*capacity
        alpha=previous if sign==0 else psi-moment/stiffness
        if abs(moment)>capacity*(1+1e-10) or sign*(alpha-previous)<-1e-12:continue
        axial=lateral*sin(psi)+tension*cos(psi)
        transverse=lateral*cos(psi)-tension*sin(psi)
        chord=length*(1+axial/axial_rigidity)
        if abs(axial/axial_rigidity)>.01 or abs(alpha)>.25:continue
        modulus=stiffness if sign==0 else 0.
        derivative=modulus+chord*axial-length*transverse**2/axial_rigidity
        if derivative<=0:continue
        coupling=length*sin(psi)*transverse/axial_rigidity+chord*cos(psi)
        dpsi=coupling/derivative
        dx=length*sin(psi)**2/axial_rigidity+coupling*dpsi
        dy=length*sin(psi)*cos(psi)/axial_rigidity+(length*transverse*cos(psi)/axial_rigidity-chord*sin(psi))*dpsi
        dtheta=-(1+modulus/(2*stiffness))*dpsi
        increment=capacity*abs(alpha-previous)
        state=CantileverHistory(configuration,alpha,increment+(0. if old is None else old.dissipation))
        return dict(state=state,motion=(chord*sin(psi),chord*cos(psi)-length,-psi-moment/(2*stiffness)),
            moment=moment,axial_force=axial,active=sign!=0,compliance=(dx,dy,dtheta),
            elastic_energy=axial**2*length/(2*axial_rigidity)+moment**2/(2*stiffness),
            dissipation_increment=increment,chord_angle=psi,production_ready=False)
    raise ValueError('No stable reference branch within the stated tension/angle bounds.')
