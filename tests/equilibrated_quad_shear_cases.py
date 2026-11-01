"""Solved inputs for the bounded compatible-recovery research benchmarks."""
import numpy as np
from equilibrated_quad_shear import recover,FreeEdge
from quad_shear_boundaries import solve_case


def free_edges(case):
    if case=='opening':return [FreeEdge(0,40.,40.,80.),FreeEdge(0,80.,40.,80.),FreeEdge(1,40.,40.,80.),FreeEdge(1,80.,40.,80.)]
    if case=='stiffness_x':return [FreeEdge(0,120.,0.,180.),FreeEdge(1,0.,0.,120.),FreeEdge(1,180.,0.,120.)]
    if case=='stiffness_y':return [FreeEdge(0,0.,0.,180.),FreeEdge(0,120.,0.,180.),FreeEdge(1,180.,0.,120.)]
    return []


def recovered(case,size,plane='XY',combination='Service'):
    sample=solve_case(case,size,plane)[combination]
    result=recover(sample['cells'],sample['moments'],sample['regions'],np.full(len(sample['points']),sample['pressure']),
                   0. if case.startswith('stiffness') else .2,free_edges(case))
    return sample,result
