"""Isotropic Rect resultants from its displacement polynomial, in plate axes.

Only postprocessing: stiffness, pressure loads and nodal solutions are untouched.
The public local nodal vector supplies w, Rx=w,y and Ry=-w,x. Reconstruct the
12-term rectangular polynomial on the unit square, then differentiate it.
"""
from math import factorial

import numpy as np


POWERS = ((0, 0), (1, 0), (0, 1), (2, 0), (1, 1), (0, 2),
          (3, 0), (2, 1), (1, 2), (0, 3), (3, 1), (1, 3))


def polynomial_row(x, y, dx=0, dy=0):
    return np.array([0. if px < dx or py < dy else
                     factorial(px)/factorial(px-dx)*factorial(py)/factorial(py-dy)*x**(px-dx)*y**(py-dy)
                     for px, py in POWERS])


_INTERPOLATION = np.array([polynomial_row(x, y, dx, dy)
                          for x, y in ((0, 0), (1, 0), (1, 1), (0, 1))
                          for dx, dy in ((0, 0), (1, 0), (0, 1))])
_INVERSE = np.linalg.inv(_INTERPOLATION)
_ORDERS = ((2, 0), (0, 2), (1, 1), (3, 0), (1, 2), (2, 1), (0, 3))
_CENTRE = np.array([polynomial_row(.5, .5, dx, dy) for dx, dy in _ORDERS])


def rectangular_coefficients(element, combination="Plate"):
    """Snapshot the solved displacement polynomial on the unit square."""
    a, b = element.width(), element.height()
    nodal = np.asarray(element.d(combination), dtype=float)
    if nodal.shape != (24, 1) or not np.isfinite(nodal).all() or not (0 < a < np.inf and 0 < b < np.inf):
        raise ValueError("Unsupported or nonfinite Rect local displacement contract.")
    nodal = nodal.reshape(4, 6)
    values = np.column_stack((nodal[:, 2], -a*nodal[:, 4], b*nodal[:, 3])).ravel()
    return _INVERSE @ values


def polynomial_resultants(coefficients, a, b, E, nu, thickness, xi=0., eta=0.):
    """Corrected Rect [Mx, My, Mxy], [Qx, Qy] at natural coordinates."""
    evaluation = _CENTRE if xi == eta == 0. else np.array([
        polynomial_row((xi+1)/2, (eta+1)/2, dx, dy) for dx, dy in _ORDERS])
    derivatives = (evaluation @ coefficients)/np.array([a**dx*b**dy for dx, dy in _ORDERS])
    xx, yy, xy, xxx, xyy, xxy, yyy = derivatives
    rigidity = E*thickness**3/(12*(1-nu**2))
    return (-rigidity*np.array([xx+nu*yy, yy+nu*xx, (1-nu)*xy]),
            -rigidity*np.array([xxx+xyy, xxy+yyy]))


def rectangular_resultants(element, E, nu, thickness, combination="Plate"):
    """Return unsmoothed centre [Mx, My, Mxy], [Qx, Qy].

    Mx=-D(w,xx+nu*w,yy), My=-D(w,yy+nu*w,xx), Mxy=-D(1-nu)w,xy;
    Q=-D grad(laplacian(w)). Isotropic, unmodified Rect bending only.
    """
    return polynomial_resultants(rectangular_coefficients(element, combination),
                                 element.width(), element.height(), E, nu, thickness)
