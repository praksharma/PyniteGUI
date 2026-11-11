"""Research-only Euler–Bernoulli basic compatibility with explicit curvature zones.

q=(nodal end moment i, nodal end moment j); internal M=-(1-s)*q_i+s*q_j.
Basic rotations subtract chord rotation. This integrates prescribed plastic
curvature; it does not determine plastic flow, solve a frame or include P-Delta.
"""
import numpy as np


def integrate(length,rigidity,end_moments,zones=()):
    q=np.asarray(end_moments,float)
    if (not np.isfinite([length,rigidity]).all() or length<=0 or rigidity<=0 or q.shape!=(2,) or not np.isfinite(q).all()):
        raise ValueError('Finite positive length/rigidity and two finite end moments are required.')
    intervals=[]
    for zone in zones:
        if len(zone)!=3 or not np.isfinite(zone).all():raise ValueError('Zones require finite start, end and plastic curvature.')
        a,b,k=map(float,zone)
        if not 0<=a<b<=length:raise ValueError('Curvature zone must lie inside the member.')
        intervals.append((a,b,k))
    intervals.sort()
    if any(a[1]>b[0] for a,b in zip(intervals,intervals[1:])):raise ValueError('Overlapping curvature zones are ambiguous.')
    cuts=sorted({0.,float(length),*(x for a,b,_ in intervals for x in (a,b))})
    points,weights=np.polynomial.legendre.leggauss(3)
    flexibility=np.zeros((2,2));plastic=np.zeros(2);tip=np.zeros(2);plastic_work=0.
    for a,b in zip(cuts,cuts[1:]):
        x=(a+b)/2+(b-a)/2*points;w=weights*(b-a)/2
        curvature=next((k for lo,hi,k in intervals if lo<=(a+b)/2<=hi),0.)
        B=np.column_stack((-(1-x/length),x/length));moment=B@q
        flexibility+=np.einsum('p,pi,pj->ij',w/rigidity,B,B)
        plastic+=B.T@(w*curvature)
        tip+=np.array((np.dot(w,(length-x)*curvature),sum(w)*curvature))
        plastic_work+=float(np.dot(w,moment*curvature))
    A=np.array(((1/length,1.,-1/length,0.),(1/length,0.,-1/length,1.)))
    basic=flexibility@q+plastic
    return dict(flexibility=flexibility,plastic_basic_rotations=plastic,basic_rotations=basic,
        nodal_elastic_stiffness=A.T@np.linalg.solve(flexibility,A),
        plastic_tip_translation=tip[0],plastic_tip_rotation=tip[1],curvature_work=plastic_work,
        qualification='prescribed_curvature_compatibility_only')
