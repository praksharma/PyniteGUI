"""Independent flat-membrane and one-way strip references (NumPy only).

Membrane: plane stress, epsilon=[du/dx, dv/dy, du/dy+dv/dx]. Uniform
tractions sigma*n on a rectangle give the affine field u=ex*x+gamma*y,
v=ey*y after removing rigid translation/rotation with three scalar restraints.

Strip: a simply supported Euler–Bernoulli beam and a thin, nu=0 plate share
their centreline, with no offset. In the narrow-strip limit the bending energy
is 1/2 integral((Eb*Ib + Es*b*t**3/12)*w''**2 dx). Integrating EI*w''''=q*b
with w=0 and w''=0 at both ends gives the expressions below. This is a
slender-strip limit, not an exact finite-width shell solution. Force/moment
sharing follows EI, not transformed/composite-section offset assumptions.
"""
import numpy as np


def membrane_stress(E, nu, strain):
    ex, ey, gamma = strain
    return E/(1-nu**2)*np.array((ex+nu*ey, ey+nu*ex, (1-nu)*gamma/2))


def membrane_displacement(points, strain):
    x, y = np.asarray(points).T
    ex, ey, gamma = strain
    return np.column_stack((ex*x+gamma*y, ey*y))


def strip_solution(x, length, line_load, beam_EI, slab_EI):
    """Positive displacement and moments follow positive shell-normal loading."""
    x = np.asarray(x)
    EI = beam_EI+slab_EI
    w = line_load*x*(length**3-2*length*x**2+x**3)/(24*EI)
    moment = line_load*x*(length-x)/2
    return w, moment*beam_EI/EI, moment*slab_EI/EI
