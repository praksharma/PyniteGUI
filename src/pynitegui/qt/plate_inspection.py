"""Snapshot-only plate probes; no solver objects, interpolation across elements or solves."""
import csv
import math
from numbers import Real

import numpy as np

from .plate_model import PLANES
from .plate_recovery import polynomial_resultants


def inspect_plate(result, element, xi=0., eta=0.):
    for value in (xi, eta):
        if isinstance(value, bool) or not isinstance(value, Real) or not math.isfinite(value) or not -1 <= value <= 1:
            raise ValueError("Plate probe xi and eta must be finite numbers between -1 and 1.")
    if element not in result["element_names"]:
        raise ValueError("Choose an element belonging to the solved plate snapshot.")
    index = result["element_names"].index(element)
    polygon = result["points"][result["cells"][index]]
    weights = np.array(((1-xi)*(1-eta), (1+xi)*(1-eta), (1+xi)*(1+eta), (1-xi)*(1+eta)))/4
    point = weights @ polygon
    definition = result["definition"]
    if definition["element_type"] == "Rect":
        a, b = np.linalg.norm(polygon[1]-polygon[0]), np.linalg.norm(polygon[3]-polygon[0])
        mat = definition["material"]
        moments, shears = polynomial_resultants(result["inspection"][index], a, b, mat["E"], mat["nu"],
                                                definition["thickness"], xi, eta)
    else:
        moments, shears = weights @ result["inspection"][index], None
    if np.shape(moments) != (3,) or not np.isfinite(moments).all() or (
            shears is not None and (np.shape(shears) != (2,) or not np.isfinite(shears).all())):
        raise ValueError("Plate recovery returned nonfinite or incompatible local values.")
    u, v, _, _ = PLANES[definition["plane"]]
    axes = np.eye(3)[[u, v]]
    axes = np.vstack((axes, np.cross(*axes)))
    global_point = np.array(definition["origin"], dtype=float)
    global_point[[u, v]] += point
    return dict(element=element, xi=float(xi), eta=float(eta), position=point.tolist(),
        global_position=global_point.tolist(), axes=axes.tolist(),
        **dict(zip(("Mx", "My", "Mxy"), moments.tolist())),
        **({} if shears is None else dict(zip(("Qx", "Qy"), shears.tolist()))))


def plate_probe_table(result, units, probes=None):
    """All element centres by default; explicit probes retain their own xi/eta."""
    probes = probes if probes is not None else [inspect_plate(result, name) for name in result["element_names"]]
    rect = result["definition"]["element_type"] == "Rect"
    headers = ["Element", "xi", "eta", *(f"Local {axis} ({units.length})" for axis in ("x", "y")),
        *(f"Global {axis} ({units.length})" for axis in "XYZ"),
        *(f"{key} ({units.moment}/{units.length})" for key in ("Mx", "My", "Mxy"))]
    if rect:
        headers += [f"{key} ({units.intensity})" for key in ("Qx", "Qy")]
    rows = [[row["element"], row["xi"], row["eta"],
        *(value*units.length_factor for value in (*row["position"], *row["global_position"])),
        *(row[key]*units.force_factor for key in ("Mx", "My", "Mxy")),
        *([row[key]*units.factor("intensity") for key in ("Qx", "Qy")] if rect else [])] for row in probes]
    return headers, rows


def write_plate_probes(path, result, units, probes=None):
    headers, rows = plate_probe_table(result, units, probes)
    definition = result["definition"]
    u, v, n, sign = PLANES[definition["plane"]]
    axes = np.eye(3)[[u, v]].tolist()+[(np.eye(3)[n]*sign).tolist()]
    context = [result["combination"], "; ".join(f"{case}: {factor:g}" for case, factor in result["factors"].items()),
        result["snapshot_id"], result["analyzed_at"], result["model_signature"], definition["element_type"],
        "Corrected Rect polynomial" if definition["element_type"] == "Rect" else "Quad bilinear moment recovery; Qx/Qy unavailable",
        *(str(axis) for axis in axes)]
    with open(path, "w", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(headers+["Combination", "Case factors", "Snapshot", "Analyzed UTC", "Model signature",
                                 "Element family", "Recovery", "Local x global vector", "Local y global vector", "Local z global vector"])
        writer.writerows([*row, *context] for row in rows)
