"""Independent axial/Euler-Bernoulli references, without app or engine imports."""
import numpy as np


def rotation(angle):
    c, s = np.cos(np.radians(angle)), np.sin(np.radians(angle))
    return np.array(((c, -s, 0.), (s, c, 0.), (0., 0., 1.)))


def normal(angle):
    """Roller tangent angle CCW from global +X; reaction is along its normal."""
    return rotation(angle)[:, 1]


def cantilever(roller_angle, beam_angle=0., nodal=(3., -2., 7.), distributed=(.002, -.005),
               length=120., E=30000., A=8., I=80., springs=(0., 0., 0.)):
    """Tip flexibility plus a scalar reaction enforcing n dot d=0.

    Nodal and distributed inputs use beam-local axes; springs use global axes.
    Include uniform distributed loads through independent free-tip integrals.
    """
    L, EI = length, E*I
    Q = rotation(beam_angle)
    F = Q @ np.array(((L/(E*A), 0., 0.), (0., L**3/(3*EI), L**2/(2*EI)),
                      (0., L**2/(2*EI), L/EI))) @ Q.T
    qx, qy = distributed
    free = Q @ np.array((qx*L**2/(2*E*A), qy*L**4/(8*EI), qy*L**3/(6*EI)))
    free += F @ (Q @ nodal)
    # Ground springs change flexibility and free motion without replacing the
    # inclined rigid constraint or rotating the existing global spring axes.
    effective = np.linalg.solve(np.eye(3)+F @ np.diag(springs), F)
    free = np.linalg.solve(np.eye(3)+F @ np.diag(springs), free)
    n = normal(roller_angle)
    reaction = -float(n @ free)/float(n @ effective @ n)*n
    displacement = free+effective @ reaction
    return displacement, reaction


def pinned_beam(points, roller_angle, q=-.005, length=120., E=30000., A=8., I=80.):
    """Horizontal pin/oblique-roller beam under uniform global Y loading.

    Static equilibrium fixes both reaction vectors. Axial strain fixes end u;
    the inclined constraint fixes end v. Add that chord motion to the simply
    supported Euler-Bernoulli bending field (tension-positive axial strain).
    """
    x, L = np.asarray(points), length
    n = normal(roller_angle)
    if abs(n[1]) < 1e-10:
        raise ValueError("The roller cannot restrain rigid-body rotation.")
    right = -q*L/(2*n[1])*n
    end_u = right[0]*L/(E*A)
    end_v = -n[0]*end_u/n[1]
    displacement = np.stack((right[0]*x/(E*A),
        end_v*x/L+q*x*(L**3-2*L*x*x+x**3)/(24*E*I),
        end_v/L+q*(L**3-6*L*x*x+4*x**3)/(24*E*I)), axis=-1)
    left = np.array((-right[0], -q*L-right[1], 0.))
    return displacement, left, right
