"""Two independent plane-stress Airy fields; NumPy only, no solver/app imports.

Rectangle: 0 <= x <= L, -H/2 <= y <= H/2, thickness t. Body forces vanish.
Airy potentials -C*y**3/6 and C*x*y**2/2 give respectively pure bending
and mixed nonuniform normal/shear stress. Boundary loads are t*sigma*n.
Displacements below integrate isotropic plane-stress strain and remove three
rigid motions with u(0,+/-H/2)=v(0,-H/2)=0. No solved field is prescribed.
Method: A.F. Bower, Applied Mechanics of Solids, section 5.2,
https://solidmechanics.org/Text/Chapter5_2/Chapter5_2.htm
"""
import numpy as np


def field(kind, points, E=3600., nu=.2, height=80., amplitude=.001):
    points = np.asarray(points)
    x, y = points[..., 0], points[..., 1]
    C, a = amplitude, height/2
    zero = np.zeros_like(x+y)
    if kind == 'bending':
        u = -C*x*y/E
        v = C*(x*x+nu*(y*y-a*a))/(2*E)
        stress = np.stack((-C*y, zero, zero), axis=-1)
    elif kind == 'mixed':
        u = C*(x*x-(2+nu)*(y*y-a*a))/(2*E)
        v = -nu*C*x*y/E
        stress = np.stack((C*x, zero, -C*y), axis=-1)
    else:
        raise ValueError('Choose bending or mixed.')
    return np.stack((u,v), axis=-1), stress


def energy(kind, length=120., height=80., thickness=.8, E=3600., nu=.2, amplitude=.001):
    if kind == 'bending':
        return amplitude**2*thickness*length*height**3/(24*E)
    if kind == 'mixed':
        G = E/(2*(1+nu))
        return amplitude**2*thickness*(height*length**3/(6*E)+length*height**3/(24*G))
    raise ValueError('Choose bending or mixed.')


def spin(kind, points, E=3600., amplitude=.001):
    """Continuum infinitesimal spin (dv/dx-du/dy)/2, not a nodal drilling DOF."""
    return amplitude*np.asarray(points)[..., 0 if kind=='bending' else 1]/E
