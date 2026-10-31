"""Independent axial-bar equilibrium by exhaustive small active-set enumeration."""
import itertools
import numpy as np


def star(force, anchors, stiffnesses, behaviors, ground=(100.,100.), anchor_motion=(0.,0.), normal=None, target=0.):
    anchors = np.array(anchors,float)
    directions = -anchors/np.linalg.norm(anchors,axis=1)[:,None]
    motion = np.array(anchor_motion)
    candidates = []
    for active in itertools.product((False,True),repeat=len(anchors)):
        K, rhs = np.diag(ground), np.array(force,float)
        for enabled, direction, stiffness in zip(active,directions,stiffnesses):
            if enabled:
                K += stiffness*np.outer(direction,direction)
                rhs += stiffness*direction*(direction @ motion)
        if normal is None:
            d = np.linalg.solve(K,rhs)
        else:
            n = np.array(normal)
            d = np.linalg.solve(np.block([[K,n[:,None]],[n[None,:],np.zeros((1,1))]]),np.r_[rhs,target])[:2]
        trial = np.array([k*(n @ (d-motion)) for n,k in zip(directions,stiffnesses)])
        correct = all((value >= -1e-8 if enabled else value <= 1e-8) if mode == 'tension_only' else
                      (value <= 1e-8 if enabled else value >= -1e-8)
                      for value,enabled,mode in zip(trial,active,behaviors))
        if correct:
            candidates.append((d,active,trial))
    if not candidates:
        raise ValueError('Independent active-set enumeration found no equilibrium.')
    for other in candidates[1:]:
        np.testing.assert_allclose(other[0],candidates[0][0],atol=1e-10)
    return candidates[0]
