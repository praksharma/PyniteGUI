"""Snapshot-bound, unsmoothed local Quad results in canonical inch-kip units.

Membrane entries are stresses (tension positive), not membrane forces. Bending
entries are moment/length. Transverse shear recovery is not validated. No stresses
are combined across thickness and no neighbouring elements are averaged.
"""
import math
import numpy as np


FIELDS = {
    "Mx": ("Bending Mx", "surface_moment"),
    "My": ("Bending My", "surface_moment"),
    "Mxy": ("Twisting Mxy", "surface_moment"),
    "Sx": ("Membrane Sx", "stress"),
    "Sy": ("Membrane Sy", "stress"),
    "Txy": ("Membrane Txy", "stress"),
}

QUAD_SHEAR_LIMITATION = (
    "Quad Qx/Qy unavailable: PyNite 3.0/3.2 transverse shear recovery fails the "
    "independent thin-plate Navier benchmark under mesh refinement. "
    "Moments and membrane stresses are separate results; do not infer shear design from these plots."
)


def field_units(units, key):
    quantity = FIELDS[key][1]
    if quantity == "surface_moment":
        return units.force_factor, f"{units.moment}/{units.length}"
    return units.factor(quantity), getattr(units, quantity)


def inspect_surface(result, surface, element, xi=0., eta=0.):
    """Natural coordinates [-1,1] on one explicitly identified solver element."""
    if (isinstance(xi, bool) or isinstance(eta, bool) or not math.isfinite(xi) or not math.isfinite(eta)
            or not -1 <= xi <= 1 or not -1 <= eta <= 1):
        raise ValueError("Surface probe xi and eta must be finite numbers between -1 and 1.")
    mapping = getattr(result.solver, "_pynitegui_surfaces", {}).get(surface)
    if not mapping or element not in mapping["elements"]:
        raise ValueError("Choose an element belonging to the solved surface snapshot.")
    quad = result.solver.quads[element]
    args = dict(xi=xi, eta=eta, local=True, combo_name=result.combination)
    values = np.concatenate([np.asarray(quad.moment(**args)).ravel(),
                             np.asarray(quad.membrane(**args)).ravel()])
    if values.shape != (6,) or not np.all(np.isfinite(values)):
        raise ValueError("Surface recovery returned nonfinite or incompatible local values.")
    nodes = (quad.i_node, quad.j_node, quad.m_node, quad.n_node)
    weights = np.array(((1-xi)*(1-eta), (1+xi)*(1-eta), (1+xi)*(1+eta), (1-xi)*(1+eta))) / 4
    point = weights @ np.array([(node.X, node.Y, node.Z) for node in nodes])
    axes = np.asarray(quad.T())[:3, :3]
    if axes.shape != (3, 3) or not np.all(np.isfinite(axes)):
        raise ValueError("Surface recovery returned incompatible local axes.")
    return {"element": element, "position": point.tolist(), "axes": axes.tolist(),
            "xi": float(xi), "eta": float(eta), **dict(zip(FIELDS, values.tolist()))}


def centre_results(result, surface):
    cache = getattr(result.solver, "_brecon_surface_results", None)
    if cache is None:
        cache = result.solver._brecon_surface_results = {}
    key = (result.combination, surface)
    if key not in cache:
        mapping = getattr(result.solver, "_pynitegui_surfaces", {}).get(surface)
        if not mapping:
            raise ValueError("This snapshot does not contain the requested coupled surface.")
        cache[key] = tuple(inspect_surface(result, surface, name) for name in mapping["elements"])
    return cache[key]


def surface_table(project, result, surface):
    units = project.units
    headers = ["Element", *(f"{axis} ({units.length})" for axis in ("X", "Y", "Z")),
               *(f"{key} ({field_units(units, key)[1]})" for key in FIELDS)]
    rows = [[row["element"], *(v*units.length_factor for v in row["position"]),
             *(row[key]*field_units(units, key)[0] for key in FIELDS)] for row in centre_results(result, surface)]
    return headers, rows
