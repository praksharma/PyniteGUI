"""Research-only backward-Euler force-point return for the stated steel law.

Resultants are (N, My, Mz), conjugate to (axial strain, curvature_y, curvature_z).
Use signed derivatives of Phi, not absolute-value normals. This local candidate
rejects nonpositive/unresolved yield-surface curvature: the stated polynomial is
not globally convex. Passing a local branch is NOT global material or frame
qualification. No PyNite/application imports, hardening or engine modifications.
"""
from dataclasses import dataclass
import numpy as np
from scipy.linalg import null_space
from scipy.optimize import brentq


class RejectedReturn(ValueError):
    pass


def surface(x):
    x=np.asarray(x,float)
    if x.shape!=(3,) or not np.isfinite(x).all():raise ValueError('Three finite normalized resultants are required.')
    p,y,z=x
    value=p*p+z*z+y**4+3.5*p*p*z*z+3*p**6*y*y+4.5*z**4*y*y
    gradient=np.array((2*p+7*p*z*z+18*p**5*y*y,4*y**3+6*p**6*y+9*z**4*y,2*z+7*p*p*z+18*z**3*y*y))
    hessian=np.array(((2+7*z*z+90*p**4*y*y,36*p**5*y,14*p*z),
        (36*p**5*y,12*y*y+6*p**6+9*z**4,36*z**3*y),
        (14*p*z,36*z**3*y,2+7*p*p+54*z*z*y*y)))
    return float(value),gradient,hessian


def surface_curvature(x):
    value,gradient,hessian=surface(x)
    if abs(value-1)>1e-8 or np.linalg.norm(gradient)<1e-10:raise ValueError('Curvature requires a resolved point on the yield surface.')
    basis=null_space(gradient.reshape(1,3))
    return float(np.linalg.eigvalsh(basis.T@hessian@basis)[0])


@dataclass(frozen=True)
class MaterialState:
    plastic_strain: tuple=(0.,0.,0.)
    dissipation: float=0.

    def __post_init__(self):
        plastic=np.asarray(self.plastic_strain,float);work=float(self.dissipation)
        if plastic.shape!=(3,) or not np.isfinite(plastic).all() or not np.isfinite(work) or work<0:
            raise ValueError('Committed material history must be finite with nonnegative dissipation.')
        object.__setattr__(self,'plastic_strain',tuple(map(float,plastic)))
        object.__setattr__(self,'dissipation',work)


class SectionReturnMap:
    def __init__(self,stiffness,capacities):
        self.C=np.array(stiffness,float,copy=True);self.cap=np.array(capacities,float,copy=True)
        if self.C.shape!=(3,3) or self.cap.shape!=(3,) or not np.isfinite(self.C).all() or not np.isfinite(self.cap).all() or np.any(self.cap<=0):
            raise ValueError('Finite 3x3 elastic stiffness and three positive capacities are required.')
        if not np.allclose(self.C,self.C.T,rtol=1e-12,atol=0.):raise ValueError('Elastic stiffness must be symmetric.')
        try:np.linalg.cholesky(self.C)
        except np.linalg.LinAlgError as error:raise ValueError('Elastic stiffness must be positive definite.') from error
        metric=self.cap[:,None]*np.linalg.solve(self.C,np.diag(self.cap))
        self.scale=float(np.linalg.eigvalsh(metric)[-1]);self.metric=metric/self.scale
        if np.linalg.cond(self.metric)>1e4:raise ValueError('Normalized elastic metric exceeds the research condition bound.')
        self.C.setflags(write=False);self.cap.setflags(write=False);self.metric.setflags(write=False)

    def update(self,strain,old=MaterialState(),max_iterations=30):
        if not isinstance(old,MaterialState):raise ValueError('Use an immutable committed MaterialState.')
        strain=np.asarray(strain,float);ep=np.asarray(old.plastic_strain,float)
        if strain.shape!=(3,) or ep.shape!=(3,) or not np.isfinite(strain).all() or not np.isfinite(ep).all() or not np.isfinite(old.dissipation) or old.dissipation<0:
            raise ValueError('Finite generalized strain and nonnegative committed material history are required.')
        if type(max_iterations) is not int or not 1<=max_iterations<=100:raise ValueError('Choose 1–100 local iterations.')
        trial=self.C@(strain-ep)/self.cap
        if np.max(abs(trial))>3:raise RejectedReturn('Trial resultants exceed the bounded local study; subdivide the strain path.')
        phi,_,_=surface(trial)
        if phi<=1+1e-12:
            return dict(force=trial*self.cap,tangent=self.C.copy(),state=old,plastic=False,multiplier=0.,
                yield_value=phi,dissipation_increment=0.,residual=0.,iterations=0,curvature=None,
                elastic_energy=float(.5*(strain-ep)@self.C@(strain-ep)),qualification='elastic_or_local_convex_branch_only')
        alpha=brentq(lambda a:surface(a*trial)[0]-1,0.,1.,xtol=1e-14)
        x=alpha*trial;_,g,_=surface(x)
        lam=max(0.,float(g@self.metric@(trial-x)/(g@g)))
        def equations(point,multiplier):
            value,normal,hessian=surface(point)
            residual=np.r_[self.metric@(point-trial)+multiplier*normal,value-1]
            J=np.block([[self.metric+multiplier*hessian,normal[:,None]],[normal[None,:],np.zeros((1,1))]])
            return residual,J
        for iteration in range(max_iterations+1):
            residual,J=equations(x,lam)
            if np.max(abs(residual))<1e-11:break
            if iteration==max_iterations:raise RejectedReturn('Local return iteration limit; committed history was not advanced.')
            try:direction=np.linalg.solve(J,-residual)
            except np.linalg.LinAlgError as error:raise RejectedReturn('Singular local consistency system.') from error
            if not np.isfinite(direction).all():raise RejectedReturn('Nonfinite local return increment.')
            accepted=False;norm=float(np.linalg.norm(residual))
            for cut in range(25):
                step=2.**-cut;candidate=x+step*direction[:3];candidate_lam=lam+step*direction[3]
                if candidate_lam<0:continue
                candidate_residual,_=equations(candidate,candidate_lam)
                if np.linalg.norm(candidate_residual)<=(1-1e-4*step)*norm or np.max(abs(candidate_residual))<1e-11:
                    x,lam=candidate,candidate_lam;accepted=True;break
            if not accepted:raise RejectedReturn('Local return line search failed; committed history was not advanced.')
        curvature=surface_curvature(x)
        if curvature<=1e-8:raise RejectedReturn('Nonpositive or unresolved local yield-surface curvature; global branch is unqualified.')
        _,g,hessian=surface(x)
        if np.linalg.eigvalsh(self.metric+lam*hessian)[0]<=1e-10:raise RejectedReturn('Unresolved local plastic consistency tangent.')
        plastic_increment=self.scale*lam*g/self.cap
        force=x*self.cap;dissipation=float(force@plastic_increment)
        if not np.isfinite(dissipation) or dissipation< -1e-12*self.scale:raise RejectedReturn('Negative or nonfinite plastic dissipation.')
        new_ep=ep+plastic_increment
        closure=force-self.C@(strain-new_ep)
        if np.max(abs(closure)/self.cap)>1e-9:raise RejectedReturn('Elastic/plastic strain decomposition did not close.')
        # Differentiate the converged KKT system at fixed committed history.
        rhs=np.vstack((np.diag(self.cap)/self.scale,np.zeros((1,3))))
        tangent=self.cap[:,None]*np.linalg.solve(J,rhs)[:3]
        normalized=tangent/np.sqrt(np.outer(np.diag(self.C),np.diag(self.C)))
        if np.linalg.norm(normalized-normalized.T)>1e-8 or np.linalg.eigvalsh((normalized+normalized.T)/2)[0]<-1e-9:
            raise RejectedReturn('Nonpositive or nonsymmetric algorithmic material tangent.')
        state=MaterialState(tuple(map(float,new_ep)),old.dissipation+max(0.,dissipation))
        return dict(force=force,tangent=tangent,state=state,plastic=True,multiplier=float(self.scale*lam),
            yield_value=surface(x)[0],dissipation_increment=max(0.,dissipation),residual=float(np.max(abs(residual))),
            iterations=iteration,curvature=curvature,elastic_energy=float(.5*(strain-new_ep)@force),
            qualification='elastic_or_local_convex_branch_only')
