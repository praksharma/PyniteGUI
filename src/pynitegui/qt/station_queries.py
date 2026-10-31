"""Governing locations from continuous solver segments, including both jump sides.

Polynomial/rational interpolation recovers the pinned engine's segment formulas;
residual checks fail closed when an engine formula no longer has that form.
"""
import csv
import json
import math
import os
from pathlib import Path
import tempfile

import numpy as np
from numpy.polynomial import Polynomial

from .model import finite_number

COMPONENTS = {
    "N": ("axial", "force"), "Fy": ("shear", "force"), "Mz": ("moment", "moment"),
    "dy": ("deflection", "length"), "Vy": ("shear_y", "force"), "Vz": ("shear_z", "force"),
    "T": ("torque", "moment"), "My": ("moment_y", "moment"), "dz": ("dz", "length"),
}
METHOD = "continuous solver segment derivative roots; both one-sided boundaries"


def real_roots(poly):
    coefficients = np.array(poly.coef, dtype=float)
    if not np.all(np.isfinite(coefficients)):
        raise ValueError("Non-finite segment coefficients; no governing station is reported.")
    scale = max(abs(coefficients), default=0.)
    if not scale:
        return []
    # Trim only noisy high-order terms. Small lower-order terms can locate a
    # genuine root near a segment end (or a P-delta denominator pole).
    roots = Polynomial(coefficients).trim(tol=scale*1e-12).roots()
    return sorted(float(root.real) for root in roots if abs(root.imag) <= 1e-8 and 0 < root.real < 1)


def segment_candidates(function, length, denominator=None):
    """Recover degree <=5 numerators in normalized station; return true limits.

    PyNite's P-little-delta deflection/moment use a quadratic denominator. The
    rational derivative numerator is N'D-ND', so no search grid misses a peak.
    """
    denominator = denominator if denominator is not None else Polynomial([1.])
    if real_roots(denominator) or abs(denominator(0.)) < 1e-12 or abs(denominator(1.)) < 1e-12:
        raise ValueError("A solver segment has a P-delta singularity; governing stations are unavailable.")
    ts = (1-np.cos(np.linspace(0., math.pi, 6)))/2
    values = np.array([function(float(t*length)) for t in ts], dtype=float)
    if not np.all(np.isfinite(values)):
        raise ValueError("Non-finite segment results; governing stations are unavailable.")
    numerator = Polynomial.fit(ts, values*denominator(ts), 5, domain=[0., 1.]).convert()
    probes = np.linspace(.037, .963, 11)
    actual = np.array([function(float(t*length)) for t in probes])
    predicted = numerator(probes)/denominator(probes)
    scale = max(float(np.max(abs(actual))), float(np.max(abs(values))), 1e-12)
    if not np.all(np.isfinite(actual)) or not np.allclose(actual, predicted, rtol=2e-9, atol=scale*2e-10):
        raise ValueError("Solver segment formula is outside the verified polynomial/rational query contract.")
    derivative = numerator.deriv()*denominator-numerator*denominator.deriv()
    locations = [0., *real_roots(derivative), 1.]
    return [(t*length, float(function(float(t*length)))) for t in locations]


def member_candidates(project, result, name, component, combination):
    solver = result.solver.members[name]
    length = solver.L()
    if project.members[name].kind == "truss":
        if component == "N":
            return [(0., "right", float(solver.axial(0., combination))), (length, "left", float(solver.axial(length, combination)))]
        if component in ("dy", "dz"):
            if getattr(project, "dimension", "2D") == "3D":
                from .spatial_results import truss_motion
                r = result.for_combination(combination)
                return [(x, side, float(truss_motion(r, name, x)[1 if component == "dy" else 2])) for x, side in ((0., "right"), (length, "left"))]
            from .unilateral import planar_bar_motion
            r = result.for_combination(combination)
            return [(x, side, float(planar_bar_motion(r, name, x)[1])) for x, side in ((0., "right"), (length, "left"))]
        return [(0., "right", 0.), (length, "left", 0.)]
    points = []
    submembers = list(getattr(solver, "sub_members", {}).values()) or [solver]
    physical_origin = np.array([solver.i_node.X, solver.i_node.Y, solver.i_node.Z])
    tangent = np.array([solver.j_node.X, solver.j_node.Y, solver.j_node.Z])-physical_origin
    tangent = tangent / length
    p_delta = result.solver.solution == "P-Delta"
    for sub in submembers:
        # Public point evaluation prepares the correct combination's segments,
        # including ReleasedMember's recovered displacement implementation.
        sub.axial(0., combination)
        offset = float((np.array([sub.i_node.X, sub.i_node.Y, sub.i_node.Z])-physical_origin) @ tangent)
        if component in ("My", "Vz", "dz"):
            segments = sub.SegmentsY
        elif component == "T":
            segments = sub.SegmentsX
        else:
            segments = sub.SegmentsZ
        for segment in segments:
            if component == "N":
                function = segment.axial
            elif component in ("Fy", "Vy", "Vz"):
                function = segment.shear
            elif component in ("My", "Mz"):
                function = lambda x, segment=segment: segment.moment(x, p_delta)
            elif component == "T":
                function = segment.torsion
            else:
                function = lambda x, segment=segment: segment.deflection(x, p_delta)
            span = float(segment.length())
            denominator = Polynomial([1., 0., segment.P1*span**2/(2*segment.EI)]) if p_delta and component in ("My", "Mz", "dy", "dz") else None
            for local, value in segment_candidates(function, span, denominator):
                side = "right" if local == 0. else "left" if local == span else "interior"
                points.append((offset+float(segment.x1)+local, side, value))
    if not points:
        raise ValueError(f"Member {name}: no continuous solver segments are available.")
    return points


def governing_stations(project, result, combinations, members, component):
    from .envelopes import selected_results
    combinations, members = tuple(combinations), tuple(members)
    selected_results(project, result, combinations)
    valid = ("N", "Vy", "Vz", "T", "My", "Mz", "dy", "dz") if getattr(project, "dimension", "2D") == "3D" else ("N", "Fy", "Mz", "dy")
    if component not in valid or not members or len(set(members)) != len(members) or any(n not in project.members for n in members):
        raise ValueError("Choose a member component and at least one distinct existing member.")
    if len(members)*len(combinations) > 5000:
        raise ValueError("Limit a station query to 5000 member/combination pairs.")
    extrema = {"Minimum": None, "Maximum": None, "Absolute extreme": None}
    for combination in combinations:
        for name in members:
            for station, side, value in member_candidates(project, result, name, component, combination):
                if not finite_number(value) or not finite_number(station):
                    raise ValueError("Non-finite candidate result; governing stations are unavailable.")
                row = {"member": name, "component": component, "value": value, "combination": combination,
                       "station": station, "side": side}
                for mode in extrema:
                    old = extrema[mode]
                    metric = (lambda v: -v) if mode == "Minimum" else abs if mode == "Absolute extreme" else (lambda v: v)
                    if old is None or (metric(value) > metric(old["value"]) and not math.isclose(value, old["value"], rel_tol=1e-10, abs_tol=1e-12)):
                        extrema[mode] = row
    return [{"extreme": mode, **row} for mode, row in extrema.items()]


def export_station_csv(path, project, result, combinations, rows, specification, source="Untitled"):
    from .envelopes import selected_results
    from .reports import csv_text
    combinations = tuple(combinations)
    selected_results(project, result, combinations)
    metadata = (source, result.snapshot_id, result.analyzed_at, result.model_signature,
                json.dumps(list(combinations)), json.dumps({n: result.solver.load_combos[n].factors for n in combinations}),
                project.units.label, result.method_label, project.self_weight_case or "",
                project.self_weight_factor if project.self_weight_case is not None else "",
                "Independent extrema; local axes; N positive compression; first selected combination then model member order wins ties",
                METHOD, json.dumps(specification, ensure_ascii=True))
    path, temporary = Path(path), None
    try:
        with tempfile.NamedTemporaryFile(mode="w", newline="", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            writer = csv.writer(stream)
            writer.writerow(("Source", "Analysis ID", "Analyzed (UTC)", "Model signature", "Selected combinations", "Combination factors", "Unit system", "Analysis method", "Self-weight case", "Self-weight factor", "Convention", "Query method", "Scope", "Extreme", "Member", "Component", "Value", "Unit", "Combination", "Station from start", "Station unit", "Side"))
            for row in rows:
                quantity = COMPONENTS[row["component"]][1]
                writer.writerow([csv_text(v) for v in (*metadata, row["extreme"], row["member"], row["component"], project.units.to_display(row["value"], quantity), getattr(project.units, quantity), row["combination"], project.units.to_display(row["station"], "length"), project.units.length, row["side"])])
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()
