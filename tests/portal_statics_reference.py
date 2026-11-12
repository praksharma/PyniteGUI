"""Independent three-member portal reference from current-chord joint statics.

One left-roof horizontal actuator, equal fixed roof gravity, four column-end
scalar hinges. Numerical root/Jacobian; imports no frame/energy implementation.
Final geometry and local constrained stability are checked, not global uniqueness.
"""
from dataclasses import dataclass
from itertools import product
import numpy as np
from scipy.optimize import root


@dataclass(frozen=True)
class PortalHistory:
    configuration: tuple
    roof_motion: tuple
    rotations: tuple
    dissipation: float=0.


def solve(height,span,EA,EI,capacity,gravity,drift,old=None):
    if not np.isfinite([height,span,EA,EI,capacity,gravity,drift]).all() or min(height,span,EA,EI,capacity)<=0:
        raise ValueError('Finite loads/drift and positive finite portal properties required.')
    config=tuple(map(float,(height,span,EA,EI,capacity,gravity)))
    if old is not None and (not isinstance(old,PortalHistory) or old.configuration!=config):raise ValueError('Reference history belongs to another portal.')
    previous=np.zeros(4) if old is None else np.asarray(old.rotations,dtype=float)
    initial=np.array([0.,-gravity*height/EA,0.,0.,-gravity*height/EA,0.]) if old is None else np.asarray(old.roof_motion,dtype=float)
    if previous.shape!=(4,) or initial.shape!=(6,) or not np.isfinite(previous).all() or not np.isfinite(initial).all() or np.max(abs(previous))>.25 or np.max(abs(initial[[2,5]]))>.25 or (old is not None and (not np.isfinite(old.dissipation) or old.dissipation<0)):
        raise ValueError('Invalid committed reference history.')
    initial=initial.copy();initial[3]+=drift-initial[0];initial[0]=drift
    physical_scale=np.array([height,1.,height,height,1.]);force_scale=capacity/height

    def statics(roof,alpha):
        def member(start,end,theta_i,theta_j,L,initial_angle,ai=0.,aj=0.):
            delta=end-start;length=np.linalg.norm(delta)
            if length<=0 or not np.isfinite(length):raise ValueError('Invalid current chord.')
            direction=delta/length;tangent=np.array([-direction[1],direction[0]])
            angle=np.arctan2(delta[1],delta[0])-initial_angle
            angle=np.arctan2(np.sin(angle),np.cos(angle))
            beta_i=theta_i-angle-ai;beta_j=theta_j-angle-aj
            mi=EI/L*(4*beta_i+2*beta_j);mj=EI/L*(2*beta_i+4*beta_j)
            axial=EA*(length/L-1)
            end_force=axial*direction-(mi+mj)/length*tangent
            energy=axial*axial*L/(2*EA)+.5*(mi*beta_i+mj*beta_j)
            return end_force,mi,mj,energy,length/L-1,angle
        x,y,t,u,v,s=roof
        left=np.array([x,height+y]);right=np.array([span+u,height+v])
        a=member(np.array([0.,0.]),left,0.,t,height,np.pi/2,alpha[0],alpha[2])
        b=member(np.array([span,0.]),right,0.,s,height,np.pi/2,alpha[1],alpha[3])
        c=member(left,right,t,s,span,0.)
        # Column j-end force plus beam i/j-end force at the roof joints.
        left_force=a[0]-c[0];right_force=b[0]+c[0]
        balance=np.array([left_force[0],left_force[1]+gravity,a[2]+c[1],
            right_force[0],right_force[1]+gravity,b[2]+c[2]])
        moments=np.array([a[1],b[1],a[2],b[2]])
        support=np.r_[-a[0],a[1],-b[0],b[1]]
        return balance,moments,support,a[3]+b[3]+c[3],max(abs(a[4]),abs(b[4]),abs(c[4])),max(abs(a[5]),abs(b[5]),abs(c[5]))

    def difference(fun,z):
        epsilon=1e-6
        return np.column_stack([(fun(z+np.eye(len(z))[j]*epsilon)-fun(z-np.eye(len(z))[j]*epsilon))/(2*epsilon) for j in range(len(z))])

    for status in sorted(product((0,-1,1),repeat=4),key=lambda s:sum(v!=0 for v in s)):
        signs=np.asarray(status);active=np.flatnonzero(signs)
        def unpack(z):
            roof=np.r_[drift,z[:5]*physical_scale]
            alpha=previous.copy();alpha[active]=z[5:]
            return roof,alpha
        def equations(z):
            roof,alpha=unpack(z);balance,moments,*_=statics(roof,alpha)
            return np.r_[balance[[1,2,3,4,5]]/[force_scale,capacity,force_scale,force_scale,capacity],
                -moments[active]/capacity+signs[active]]
        guess=np.r_[initial[1:]/physical_scale,previous[active]]
        try:
            candidate=root(equations,guess,method='hybr',options={'xtol':1e-10})
            residual=equations(candidate.x)
        except (ValueError,FloatingPointError):continue
        if not np.isfinite(candidate.x).all() or not np.isfinite(residual).all() or np.max(abs(residual))>2e-9:continue
        roof,alpha=unpack(candidate.x);balance,moments,support,energy,strain,angle=statics(roof,alpha)
        if strain>.01 or angle>.25 or np.max(abs(roof[[2,5]]))>.25 or np.max(abs(alpha))>.25:continue
        if np.any(abs(moments)>capacity*(1+1e-9)) or np.any(signs[active]*(alpha-previous)[active]<-1e-10):continue
        jac=difference(equations,candidate.x)
        if not np.isfinite(jac).all() or np.linalg.eigvalsh((jac+jac.T)/2)[0]<=1e-7:continue
        # Implicit actuator derivative from the independent joint residuals.
        epsilon=1e-6*height
        roof_plus=roof.copy();roof_minus=roof.copy();roof_plus[0]+=epsilon;roof_minus[0]-=epsilon
        def residual_at(roof):
            bal,mom,*_=statics(roof,alpha)
            return np.r_[bal[[1,2,3,4,5]]/[force_scale,capacity,force_scale,force_scale,capacity],-mom[active]/capacity+signs[active]]
        derivative=(residual_at(roof_plus)-residual_at(roof_minus))/(2*epsilon)
        dz=np.linalg.solve(jac,-derivative)
        plus_roof,plus_alpha=unpack(candidate.x+dz*epsilon);plus_roof[0]+=epsilon
        minus_roof,minus_alpha=unpack(candidate.x-dz*epsilon);minus_roof[0]-=epsilon
        slope=(statics(plus_roof,plus_alpha)[0][0]-statics(minus_roof,minus_alpha)[0][0])/(2*epsilon)
        D=capacity*sum(abs(alpha-previous))+(0. if old is None else old.dissipation)
        state=PortalHistory(config,tuple(roof),tuple(alpha),float(D))
        return dict(state=state,roof_motion=roof,actuator_load=float(balance[0]),actuator_tangent=float(slope),
            hinge_moments=moments,support_reactions=support,elastic_energy=energy,active=tuple(active),
            production_ready=False,qualification='bounded_three_member_portal_joint_statics_only')
    raise ValueError('No resolved stable reference portal branch; no history committed.')
