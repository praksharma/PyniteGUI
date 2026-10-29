"""Independent elastic beam-column references; no application/engine imports.

The continuum reference integrates EI*w''''+P*w''=q exactly by a state transfer
matrix. P is the positive compressive geometric preload. The separate 12-DOF
reference integrates cubic Hermite strain energy and uses a scalar axial root
plus Lagrange multipliers, rather than the production free-coordinate iteration.
"""
import math

import numpy as np
from scipy.linalg import expm
from scipy.optimize import root_scalar


def axial_strain_force(applied, EA):
    """Small root of N+N²/EA=applied (N tension positive).

    PyNite's geometric matrix includes the axial N/L term. This is its
    small-strain geometric-stiffness contract, not finite-strain material physics.
    """
    discriminant = 1+4*applied/EA
    if discriminant <= 0:
        raise ValueError("No small axial branch for this applied force.")
    return 2*applied/(1+math.sqrt(discriminant))


def column_field(length, EI, compression, force=0., moment=0., pressure=0.,
                 base_translation=0., base_rotation=0., tip_translation=None,
                 tip_rotation=None, spring=0.):
    """Vertical column's global-X field, with global-Z rotations/couples.

    State = [w, w', EI*w'', EI*w'''+P*w', 1]. Rotations are -w'. A free tip
    has V=-force and M=-moment; a ground spring changes V to -force+spring*w.
    A supplied tip motion replaces the corresponding force boundary equation.
    """
    matrix = np.zeros((5, 5))
    matrix[0, 1], matrix[1, 2] = 1., 1/EI
    matrix[2, 1], matrix[2, 3], matrix[3, 4] = -compression, 1., pressure
    transfer = expm(matrix*length)
    known = np.array((base_translation, -base_rotation, 0., 0., 1.))
    rows, targets = [], []
    for selector, target in (
            (np.array((1., 0., 0., 0., 0.)) if tip_translation is not None else
             np.array((-spring, 0., 0., 1., 0.)), tip_translation if tip_translation is not None else -force),
            (np.array((0., 1., 0., 0., 0.)) if tip_rotation is not None else
             np.array((0., 0., 1., 0., 0.)), -tip_rotation if tip_rotation is not None else -moment)):
        row = selector @ transfer
        rows.append(row[2:4])
        targets.append(target-row @ known)
    known[2:4] = np.linalg.solve(rows, targets)

    def sample(stations):
        return np.array([expm(matrix*station) @ known for station in stations])

    end = sample([length])[0]
    return dict(sample=sample, base_force=float(known[3]), base_moment=float(known[2]),
                tip_force=float(-end[3]-force), tip_moment=float(-end[2]-moment),
                tip_translation=float(end[0]), tip_rotation=float(-end[1]))


def hermite_stiffness(E, G, A, Iy, Iz, J, length):
    """Local 12-DOF elastic K and geometric G per unit tensile preload.

    Integrate curvature products for K and slope products for G independently.
    Axial and torsional terms are the derivatives of their quadratic energies.
    """
    L = length
    K, geometric = np.zeros((12, 12)), np.zeros((12, 12))
    difference = np.array(((1., -1.), (-1., 1.)))
    for indices, stiffness, initial in (((0, 6), E*A/L, 1/L), ((3, 9), G*J/L, (Iy+Iz)/(A*L))):
        K[np.ix_(indices, indices)] += stiffness*difference
        geometric[np.ix_(indices, indices)] += initial*difference
    gauss, weights = np.polynomial.legendre.leggauss(4)
    for indices, inertia, signs in (((1, 5, 7, 11), Iz, np.ones(4)),
                                    ((2, 4, 8, 10), Iy, np.array((1., -1., 1., -1.)))):
        for coordinate, weight in zip((gauss+1)/2, weights*L/2):
            s = coordinate
            slope = np.array(((-6*s+6*s*s)/L, 1-4*s+3*s*s,
                               (6*s-6*s*s)/L, -2*s+3*s*s))*signs
            curvature = np.array(((-6+12*s)/L**2, (-4+6*s)/L,
                                  (6-12*s)/L**2, (-2+6*s)/L))*signs
            K[np.ix_(indices, indices)] += E*inertia*weight*np.outer(curvature, curvature)
            geometric[np.ix_(indices, indices)] += weight*np.outer(slope, slope)
    return K, geometric


def constrained_tip(E, G, A, Iy, Iz, J, length, base, force, constraints, targets, springs):
    """One spatial cantilever, arbitrary affine tip constraints/global springs.

    Coordinates are member-local, with the member on +X and zero roll. A scalar
    secant solve closes N=EA/L*(u_tip-u_base). KKT multipliers enforce the actual
    targets directly; no production lift, nullspace, matrix or result is used.
    """
    K, geometric = hermite_stiffness(E, G, A, Iy, Iz, J, length)
    base, force, springs = map(np.asarray, (base, force, springs))
    constraints, targets = map(np.asarray, (constraints, targets))

    def evaluate(axial):
        total = K+axial*geometric
        tip = total[6:, 6:]+np.diag(springs)
        system = np.block([[tip, constraints.T],
                           [constraints, np.zeros((len(targets), len(targets)))]])
        rhs = np.r_[force-total[6:, :6] @ base, targets]
        displacement = np.r_[base, np.linalg.solve(system, rhs)[:6]]
        residual = axial-E*A/length*(displacement[6]-displacement[0])
        return float(residual), displacement, total

    root = root_scalar(lambda value: evaluate(value)[0], x0=0., x1=1., method="secant", xtol=1e-10, rtol=1e-12)
    if not root.converged:
        raise ValueError("Independent axial root did not converge.")
    residual, displacement, total = evaluate(root.root)
    if abs(residual) > 1e-7:
        raise ValueError("Independent axial root residual is too large.")
    internal = total @ displacement
    # Rigid plus ground-spring external reactions equal internal minus applied.
    return displacement, np.r_[internal[:6], internal[6:]-force], float(root.root)
