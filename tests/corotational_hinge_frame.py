"""Research-only conservative corotational planar configured-hinge frame.

Small elastic axial strains, bounded rotations, straight Euler-Bernoulli members,
dead nodal loads and scalar perfect-plastic end moments. This is a different
formulation from PyNite's combined solver; no interaction/source parity claim.
"""
from itertools import product
import numpy as np
from planar_hinge_frame import PlanarHingeFrame, FrameHistory


class CorotationalHingeFrame(PlanarHingeFrame):
    def __init__(self,nodes,members,fixed,hinges=()):
        nodes=tuple(tuple(p) for p in nodes);members=tuple(tuple(m) for m in members)
        super().__init__(nodes,members,fixed,hinges)
        self.geometry=[]
        for i,j,EA,EI in members:
            delta=np.asarray(nodes[j])-nodes[i];length=np.linalg.norm(delta)
            C=np.zeros((3,3));C[0,0]=EA/length
            C[1:,1:]=EI/length*np.array([[4.,2.],[2.,4.]])
            self.geometry.append((delta,length,C))
        self.configuration=(*self.configuration,'bounded_corotational_dead_load')

    def evaluate(self,motion,rotations):
        """Analytic gradient/Hessian of elastic energy in nodal/hinge coordinates."""
        u=np.asarray(motion,dtype=float);alpha=np.asarray(rotations,dtype=float)
        count=len(self.interfaces)
        if u.shape!=(self.size,) or alpha.shape!=(count,) or not np.isfinite(u).all() or not np.isfinite(alpha).all():
            raise ValueError('Finite motion/hinge vectors required.')
        if np.max(abs(u[2::3]))>.25 or (count and np.max(abs(alpha))>.25):
            raise ValueError('Research rotation bound exceeded.')
        internal=np.zeros(self.size);q=np.zeros(count);K=np.zeros((self.size,self.size))
        G=np.zeros((self.size,count));H=np.zeros((count,count));energy=0.;basic_forces=[]
        # Relative translation operator: delta = initial chord + D @ local u.
        D=np.array([[-1.,0.,0.,1.,0.,0.],[0.,-1.,0.,0.,1.,0.]])
        for element,((ids,T,k),(delta0,L,C)) in enumerate(zip(self.elements,self.geometry)):
            v=u[ids];delta=delta0+D@v;length=np.linalg.norm(delta)
            if not np.isfinite(length) or length<=0 or abs(length/L-1)>.01:
                raise ValueError('Research axial-strain bound exceeded.')
            angle=np.arctan2(delta0[0]*delta[1]-delta0[1]*delta[0],delta0@delta)
            if abs(angle)>.25:raise ValueError('Research chord-rotation bound exceeded.')
            n=delta/length;t=np.array([-n[1],n[0]])
            grad_length=D.T@n;grad_angle=D.T@t/length
            hess_length=D.T@(np.eye(2)-np.outer(n,n))@D/length
            hess_angle=-D.T@(np.outer(n,t)+np.outer(t,n))@D/length**2
            J=np.vstack((grad_length,-grad_angle,-grad_angle));J[1,2]+=1.;J[2,5]+=1.
            B=np.zeros((3,count))
            for a,(member,end) in enumerate(self.interfaces):
                if member==element:B[1+end,a]=1.
            strain=np.array([length-L,v[2]-angle,v[5]-angle])-B@alpha
            stress=C@strain;energy+=float(.5*strain@stress);basic_forces.append(stress)
            internal[ids]+=J.T@stress;q+=B.T@stress
            K[np.ix_(ids,ids)]+=J.T@C@J+stress[0]*hess_length-(stress[1]+stress[2])*hess_angle
            G[ids]+=J.T@C@B;H+=B.T@C@B
        return dict(internal=internal,hinge_moments=q,stiffness=K,coupling=G,
            hinge_stiffness=H,elastic_energy=energy,basic_forces=np.array(basic_forces))

    def solve(self,loads,old=None,max_iterations=30):
        loads=np.asarray(loads,dtype=float);count=len(self.interfaces)
        if loads.shape!=(self.size,) or not np.isfinite(loads).all():raise ValueError('Finite full nodal loads required.')
        if type(max_iterations) is not int or not 1<=max_iterations<=50:raise ValueError('Use 1–50 Newton iterations.')
        if old is not None and (not isinstance(old,FrameHistory) or old.configuration!=self.configuration):
            raise ValueError('History belongs to another frame formulation/configuration.')
        previous=np.zeros(count) if old is None else np.asarray(old.rotations,dtype=float)
        initial=np.zeros(self.size) if old is None else np.asarray(old.motion,dtype=float)
        if previous.shape!=(count,) or initial.shape!=(self.size,) or not np.isfinite(previous).all() or not np.isfinite(initial).all() or (old is not None and (not np.isfinite(old.dissipation) or old.dissipation<0)):
            raise ValueError('Invalid committed frame history.')
        if np.any(initial[self.fixed]!=0.):raise ValueError('Prescribed support motion is unsupported.')
        statuses=sorted(product((0,-1,1),repeat=count),key=lambda s:sum(v!=0 for v in s))
        # A converged elastic trial can seed geometric coordinates for yielded
        # candidates. Its trial hinge state is never committed or transferred.
        seed=initial.copy()
        for status in statuses:
            signs=np.asarray(status);active=np.flatnonzero(signs)
            u=initial.copy();alpha=previous.copy();converged=False
            def equations(u,alpha):
                e=self.evaluate(u,alpha)
                residual=np.r_[(e['internal']-loads)[self.free],
                    -e['hinge_moments'][active]+signs[active]*self.capacity[active]]
                K=e['stiffness'][np.ix_(self.free,self.free)];G=e['coupling'][np.ix_(self.free,active)]
                H=e['hinge_stiffness'][np.ix_(active,active)]
                return e,residual,np.block([[K,-G],[-G.T,H]])
            # A fixed merit scaling avoids changing the residual norm during line search.
            diagonal=np.r_[np.diag(self.K)[self.free],np.diag(self.H)[active]]
            if np.any(diagonal<=0):continue
            merit_scale=1/np.sqrt(diagonal)
            for iteration in range(max_iterations):
                try:e,residual,matrix=equations(u,alpha)
                except ValueError:break
                if np.max(abs(residual[:len(self.free)]))<=1e-8+1e-11*np.max(abs(loads)) and (not active.size or np.all(abs(residual[len(self.free):])<=1e-9*self.capacity[active])):
                    converged=True;break
                scale=self._scaling(matrix)
                if scale is None:
                    if iteration==0 and active.size and not np.array_equal(u,seed):
                        u=seed.copy()
                        continue
                    break
                step=np.linalg.solve(matrix*np.outer(scale,scale),-residual*scale)*scale
                norm=np.linalg.norm(residual*merit_scale);accepted=False
                for factor in 2.**-np.arange(16):
                    trial_u=u.copy();trial_alpha=alpha.copy()
                    trial_u[self.free]+=factor*step[:len(self.free)]
                    trial_alpha[active]+=factor*step[len(self.free):]
                    try:_,trial_residual,_=equations(trial_u,trial_alpha)
                    except ValueError:continue
                    if np.linalg.norm(trial_residual*merit_scale)<norm*(1-1e-4*factor):
                        u,alpha=trial_u,trial_alpha;accepted=True;break
                if not accepted:break
            if not converged:continue
            if not active.size and self._scaling(matrix) is not None:
                seed=u.copy()
            q=e['hinge_moments']
            if np.any(abs(q)>self.capacity*(1+1e-9)) or np.any(signs[active]*(alpha-previous)[active]<-1e-10):continue
            # Check both the accepted active tangent and all yield-boundary releases.
            if self._scaling(matrix) is None:continue
            boundary=np.flatnonzero(abs(q)>=self.capacity*(1-1e-10))
            K=e['stiffness'][np.ix_(self.free,self.free)]
            if boundary.size:
                Gb=e['coupling'][np.ix_(self.free,boundary)];Hb=e['hinge_stiffness'][np.ix_(boundary,boundary)]
                if self._scaling(np.block([[K,-Gb],[-Gb.T,Hb]])) is None:continue
            G=e['coupling'][np.ix_(self.free,active)];H=e['hinge_stiffness'][np.ix_(active,active)]
            tangent=K-G@np.linalg.solve(H,G.T) if active.size else K.copy()
            increment=float(self.capacity@abs(alpha-previous))
            state=FrameHistory(self.configuration,tuple(alpha),increment+(0. if old is None else old.dissipation),tuple(u))
            reaction=np.zeros(self.size);reaction[self.fixed]=(e['internal']-loads)[self.fixed]
            return dict(state=state,motion=u,reaction=reaction,hinge_moments=q,active=tuple(active),
                residual=(e['internal']-loads)[self.free],free_tangent=tangent,
                elastic_energy=e['elastic_energy'],dissipation_increment=increment,
                basic_forces=e['basic_forces'],iterations=iteration+1,production_ready=False,
                qualification='bounded_corotational_scalar_hinge_research_only')
        raise ValueError('No resolved stable consistent corotational equilibrium; no state committed.')
