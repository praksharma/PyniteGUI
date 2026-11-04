"""Independent scalar cycling and constrained force-space optimization.

No candidate, application or engine imports. The optimizer uses numerical
constraint derivatives and multiple feasible starts; it cross-checks the bounded
samples, without proving global uniqueness for the nonconvex polynomial.
"""
import numpy as np
from scipy.optimize import minimize


def phi(point):
    axial,minor,major=map(float,point)
    return (axial**2+major**2+minor**4+3.5*(axial*major)**2
            +3*axial**6*minor**2+4.5*major**4*minor**2)


def scalar_cycle(strains,stiffness,capacity):
    plastic=0.;dissipation=0.;rows=[]
    for strain in strains:
        trial=stiffness*(strain-plastic)
        if trial>capacity:
            force=capacity;updated=strain-capacity/stiffness
        elif trial< -capacity:
            force=-capacity;updated=strain+capacity/stiffness
        else:force=trial;updated=plastic
        dissipation+=capacity*abs(updated-plastic);plastic=updated
        rows.append((force,plastic,dissipation))
    return np.array(rows)


def constrained_reference(trial,stiffness,capacities):
    c=np.asarray(capacities);C=np.asarray(stiffness);trial=np.asarray(trial)
    metric=np.diag(c)@np.linalg.inv(C)@np.diag(c);metric/=np.linalg.eigvalsh(metric).max()
    def objective(x):return float(.5*(x-trial)@metric@(x-trial))
    starts=[np.zeros(3),*(sign*np.eye(3)[axis] for axis in range(3) for sign in (-1.,1.))]
    starts.append(trial/max(1.,4*np.linalg.norm(trial)))
    rows=[];failures=0
    for start in starts:
        result=minimize(objective,start,method='SLSQP',constraints={'type':'ineq','fun':lambda x:1-phi(x)},
            options={'ftol':1e-12,'maxiter':300})
        if result.success and phi(result.x)<=1+1e-8:
            rows.append(dict(point=result.x.tolist(),objective=objective(result.x)))
        else:failures+=1
    if len(rows)<6:raise ValueError('Insufficient independent optimizer convergence; reference is unresolved.')
    best=min(rows,key=lambda r:r['objective'])
    if max(r['objective'] for r in rows)-best['objective']>1e-7:raise ValueError('Independent starts found distinct objective levels; reference is unresolved.')
    return dict(point=best['point'],objective=best['objective'],successful_starts=len(rows),failed_starts=failures,
        point_spread=float(max(np.linalg.norm(np.array(r['point'])-best['point']) for r in rows)))


def nonconvex_witness():
    a=np.sqrt((np.sqrt(18)-2)/7);scale=1.0002
    first=scale*np.array((a+.1,0.,a-.1));second=scale*np.array((a-.1,0.,a+.1));mid=(first+second)/2
    boundary=np.array((a,0.,a));direction=np.array((1.,0.,-1.))/np.sqrt(2);h=1e-4
    second_difference=(phi(boundary+h*direction)-2*phi(boundary)+phi(boundary-h*direction))/h**2
    return dict(first=first.tolist(),second=second.tolist(),midpoint=mid.tolist(),
        endpoint_phi=[phi(first),phi(second)],midpoint_phi=phi(mid),boundary=boundary.tolist(),
        tangential_second_difference=float(second_difference),global_elastic_domain_convex=False)
