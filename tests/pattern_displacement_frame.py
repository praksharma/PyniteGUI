"""Research-only work-conjugate translational dead-pattern continuation.

Physical loads = preload + factor*p; prescribed q=p.T@u. An orthogonal coordinate
change reuses the bounded single-actuator solver without altering its energy law.
No rotational loads, follower patterns, general arc-length or GUI integration.
"""
from dataclasses import dataclass
import numpy as np
from displacement_hinge_frame import DisplacementHingeFrame,ControlledHistory


@dataclass(frozen=True)
class PatternHistory:
    configuration: tuple
    rotations: tuple
    dissipation: float
    motion: tuple


class _PatternCoordinates(DisplacementHingeFrame):
    def __init__(self,nodes,members,fixed,hinges,preload,pattern):
        pattern=np.asarray(pattern,dtype=float)
        if pattern.shape!=(3*len(nodes),) or not np.isfinite(pattern).all() or np.any(pattern[2::3]!=0.):
            raise ValueError('Finite translational pattern required; nodal moments are unsupported.')
        norm=float(np.linalg.norm(pattern))
        if not np.isfinite(norm) or norm<=0:raise ValueError('Nonzero finite pattern required.')
        control=int(np.flatnonzero(pattern)[0])
        super().__init__(nodes,members,fixed,hinges,preload,control)
        if np.any(pattern[self.fixed]!=0.):raise ValueError('Pattern loads must act on free DOFs.')
        self.pattern=pattern.copy();self.pattern.flags.writeable=False;self.norm=norm
        axis=np.zeros(len(self.free));axis[list(self.free).index(control)]=1.
        difference=axis-pattern[self.free]/norm
        Q=np.eye(len(self.free));squared=float(difference@difference)
        if squared>1e-28:Q-=2*np.outer(difference,difference)/squared
        self.transform=np.eye(self.size);self.transform[np.ix_(self.free,self.free)]=Q
        self.K=self.transform.T@self.K@self.transform
        self.preload=self.transform.T@self.preload;self.preload.flags.writeable=False
        self.configuration=(*self.configuration,'work_conjugate_translation_pattern',tuple(pattern))

    def evaluate(self,motion,rotations):
        result=super().evaluate(self.transform@motion,rotations)
        result['internal']=self.transform.T@result['internal']
        result['stiffness']=self.transform.T@result['stiffness']@self.transform
        result['coupling']=self.transform.T@result['coupling']
        return result


class PatternDisplacementFrame:
    def __init__(self,nodes,members,fixed,hinges,preload,pattern):
        nodes=tuple(tuple(p) for p in nodes)
        self._driver=_PatternCoordinates(nodes,members,fixed,hinges,preload,pattern)
        self.configuration=self._driver.configuration

    def solve_displacement(self,target,old=None,max_iterations=30):
        driver=self._driver;transformed=None
        if isinstance(target,bool) or not np.isfinite(target):raise ValueError('Finite work-conjugate displacement required.')
        if old is not None:
            if not isinstance(old,PatternHistory) or old.configuration!=self.configuration:
                raise ValueError('History belongs to another pattern/configuration.')
            motion=np.asarray(old.motion,dtype=float)
            if motion.shape!=(driver.size,) or not np.isfinite(motion).all():raise ValueError('Invalid physical pattern history.')
            transformed=ControlledHistory(old.configuration,old.rotations,old.dissipation,tuple(driver.transform.T@motion))
        r=driver.solve_displacement(target/driver.norm,transformed,max_iterations)
        r['motion']=driver.transform@r['motion']
        r['reaction']=driver.transform@r['reaction'];r['loads']=driver.transform@r['loads']
        r['residual']=driver.transform[np.ix_(driver.free,driver.free)]@r['residual']
        state=r['state'];r['state']=PatternHistory(state.configuration,state.rotations,state.dissipation,tuple(r['motion']))
        r['load_factor']=r.pop('actuator_load')/driver.norm
        r['pattern_tangent']=r.pop('actuator_tangent')/driver.norm**2
        r['control_displacement']=float(driver.pattern@r['motion'])
        r['qualification']='bounded_work_conjugate_dead_pattern_research_only'
        return r
