"""Independent Kirchhoff references; no Brecon or PyNite imports.

Uniform transverse pressure, simply supported outer rectangle, optional centred
rectangular free opening. The Ritz basis is sin(m*pi*x/a) sin(n*pi*y/b), odd m/n
by symmetry. Integrate the full bending energy minus the hole analytically.
The hole edge is natural, not restrained; no mesh or element matrices are used.

Energy: D/2 integral(wxx²+wyy²+2nu*wxx*wyy+2(1-nu)*wxy²) - integral(q*w).
References: Sherar, Cranfield thesis, section 5.4.2, equations 5.9–5.11;
https://dspace.lib.cranfield.ac.uk/bitstream/1826/125/2/sherarphd.pdf
Cutout-domain subtraction: https://doi.org/10.32604/cmes.2022.021340
This is a converged numerical reference, not an exact corner-stress solution.
"""
import numpy as np


def cosine_integral(wave, low, high):
    return (high-low)*np.cos(wave*(low+high)/2)*np.sinc(wave*(high-low)/(2*np.pi))


class OpeningRitz:
    """Unit q and D; scale w by q/D and moment resultants by q afterwards."""
    def __init__(self, width, height, nu, hole_width=0., hole_height=0., terms=11):
        m, n = np.meshgrid(np.arange(1, 2*terms, 2), np.arange(1, 2*terms, 2), indexing="ij")
        self.ax, self.by = m.ravel()*np.pi/width, n.ravel()*np.pi/height
        self.nu = nu
        ax, by = self.ax, self.by
        stiffness = np.zeros((len(ax), len(ax)))
        force = np.zeros(len(ax))
        domains = [(1, (0, width, 0, height))]
        if hole_width or hole_height:
            assert 0 < hole_width < width and 0 < hole_height < height
            domains.append((-1, ((width-hole_width)/2, (width+hole_width)/2,
                                 (height-hole_height)/2, (height+hole_height)/2)))
        for sign, (x0, x1, y0, y1) in domains:
            sx = .5*(cosine_integral(ax[:, None]-ax, x0, x1)-cosine_integral(ax[:, None]+ax, x0, x1))
            sy = .5*(cosine_integral(by[:, None]-by, y0, y1)-cosine_integral(by[:, None]+by, y0, y1))
            cx = .5*(cosine_integral(ax[:, None]-ax, x0, x1)+cosine_integral(ax[:, None]+ax, x0, x1))
            cy = .5*(cosine_integral(by[:, None]-by, y0, y1)+cosine_integral(by[:, None]+by, y0, y1))
            aa, bb = ax**2, by**2
            stiffness += sign*((aa[:, None]*aa+bb[:, None]*bb+nu*(aa[:, None]*bb+bb[:, None]*aa))*sx*sy
                               +2*(1-nu)*(ax*by)[:, None]*(ax*by)*cx*cy)
            force += sign*((np.cos(ax*x0)-np.cos(ax*x1))/ax)*((np.cos(by*y0)-np.cos(by*y1))/by)
        scale = np.sqrt(np.diag(stiffness))
        normalized = stiffness/scale[:, None]/scale
        self.condition = np.linalg.cond(normalized)
        if self.condition > 1e8:
            raise ValueError("Ritz truncation is too ill-conditioned for this reference.")
        np.linalg.cholesky(normalized)
        solved = np.linalg.solve(normalized, force/scale)
        np.testing.assert_allclose(normalized @ solved, force/scale, rtol=1e-9, atol=1e-9)
        self.coefficients = solved/scale
        self.compliance = force @ self.coefficients

    def displacement(self, points):
        xy = np.atleast_2d(points)
        return (np.sin(xy[:, 0, None]*self.ax)*np.sin(xy[:, 1, None]*self.by)) @ self.coefficients

    def mean_moments(self, patch):
        """Exact basis integrals on a rectangular material patch, not corner peaks."""
        x0, x1, y0, y1 = patch
        ax, by = self.ax, self.by
        sine = ((np.cos(ax*x0)-np.cos(ax*x1))/ax)*((np.cos(by*y0)-np.cos(by*y1))/by)
        cosine = cosine_integral(ax, x0, x1)*cosine_integral(by, y0, y1)
        return np.array([sine @ ((ax**2+self.nu*by**2)*self.coefficients),
                         sine @ ((by**2+self.nu*ax**2)*self.coefficients),
                         cosine @ (-(1-self.nu)*ax*by*self.coefficients)])/((x1-x0)*(y1-y0))


def navier(points, width, height, nu, pressure, rigidity, terms=80):
    """Classical uniform-load series: w, [Mx, My, Mxy], [Qx, Qy]."""
    m, n = np.meshgrid(np.arange(1, terms, 2), np.arange(1, terms, 2), indexing="ij")
    ax, by = m.ravel()*np.pi/width, n.ravel()*np.pi/height
    coefficient = 16*pressure/(np.pi**2*m.ravel()*n.ravel()*rigidity*(ax**2+by**2)**2)
    x, y = points[:, 0, None], points[:, 1, None]
    sine, cosine = np.sin(ax*x)*np.sin(by*y), np.cos(ax*x)*np.cos(by*y)
    moments = np.array([sine @ ((ax**2+nu*by**2)*coefficient*rigidity),
                        sine @ ((by**2+nu*ax**2)*coefficient*rigidity),
                        cosine @ (-(1-nu)*ax*by*coefficient*rigidity)]).T
    shears = np.array([(np.cos(ax*x)*np.sin(by*y)) @ (rigidity*ax*(ax**2+by**2)*coefficient),
                       (np.sin(ax*x)*np.cos(by*y)) @ (rigidity*by*(ax**2+by**2)*coefficient)]).T
    return sine @ coefficient, moments, shears
