"""In-plane shear wall membrane, story diaphragm, pier and coupling-beam recovery."""
import csv
import math
import numpy as np

from .model import finite_number, identifier
from .plate_model import EDGES, PLANES


ANALYSIS_MODES = ("transverse", "shear_wall")
WALL_LOAD_KINDS = ("shear", "axial")


def validate_shear_wall_fields(definition):
    if not isinstance(definition.analysis_mode, str) or definition.analysis_mode not in ANALYSIS_MODES:
        raise ValueError("Analysis mode must be transverse or shear_wall.")
    if not isinstance(definition.wall_supports, list) or len(definition.wall_supports) > 16:
        raise ValueError("Use at most 16 shear wall support segments.")
    for support in definition.wall_supports:
        if not isinstance(support, dict) or set(support) != {"elevation", "x_start", "x_end"}:
            raise ValueError("Wall support fields must be elevation, x_start and x_end.")
        if any(not finite_number(support[key]) for key in ("elevation", "x_start", "x_end")):
            raise ValueError("Wall support coordinates must be finite.")
        elev, x0, x1 = support["elevation"], support["x_start"], support["x_end"]
        if not (0. <= elev <= definition.height and 0. <= x0 < x1 <= definition.width and x1 - x0 >= 1e-6):
            raise ValueError("Wall supports must lie within the wall height and span a positive width interval.")
    if not isinstance(definition.wall_stories, list) or len(definition.wall_stories) > 32:
        raise ValueError("Use at most 32 shear wall stories.")
    story_names = set()
    for story in definition.wall_stories:
        if not isinstance(story, dict) or set(story) != {"name", "elevation", "x_start", "x_end"}:
            raise ValueError("Wall story fields must be name, elevation, x_start and x_end.")
        name = story["name"]
        if not identifier(name) or len(name) > 80 or name in story_names:
            raise ValueError("Wall story names must be unique identifiers up to 80 characters.")
        story_names.add(name)
        if any(not finite_number(story[key]) for key in ("elevation", "x_start", "x_end")):
            raise ValueError("Wall story coordinates must be finite.")
        elev, x0, x1 = story["elevation"], story["x_start"], story["x_end"]
        if not (0. <= elev <= definition.height and 0. <= x0 < x1 <= definition.width and x1 - x0 >= 1e-6):
            raise ValueError("Wall stories must lie within the wall height and span a positive width interval.")
    if not isinstance(definition.wall_loads, list) or len(definition.wall_loads) > 64:
        raise ValueError("Use at most 64 shear wall story loads.")
    for load in definition.wall_loads:
        if not isinstance(load, dict) or set(load) != {"story", "case", "kind", "magnitude"}:
            raise ValueError("Wall load fields must be story, case, kind and magnitude.")
        if not isinstance(load["story"], str) or load["story"] not in story_names:
            raise ValueError("Wall story loads require an existing wall story.")
        if not isinstance(load["case"], str) or load["case"] not in definition.load_cases:
            raise ValueError("Wall story loads require an existing load case.")
        if not isinstance(load["kind"], str) or load["kind"] not in WALL_LOAD_KINDS:
            raise ValueError("Wall load kind must be shear or axial.")
        if not finite_number(load["magnitude"]) or abs(load["magnitude"]) > 1e6:
            raise ValueError("Wall load magnitude must be finite and within +/-1e6 kip.")
    if definition.analysis_mode == "shear_wall":
        if definition.element_type != "Quad":
            raise ValueError("In-plane shear wall mode requires Quad membrane elements.")
        if not definition.wall_supports:
            raise ValueError("In-plane shear wall mode requires at least one wall support segment.")
        if definition.subgrade_modulus != 0.:
            raise ValueError("In-plane shear wall mode does not use transverse soil subgrade springs.")
        if definition.self_weight_case is not None:
            raise ValueError("In-plane shear wall mode uses story axial/shear loads or point loads rather than transverse XZ slab self-weight.")
    elif definition.wall_supports or definition.wall_stories or definition.wall_loads:
        raise ValueError("Wall supports, stories and story loads require shear_wall analysis mode.")


def wall_control_coordinates(definition):
    extra_x, extra_y = [], []
    if definition.analysis_mode == "shear_wall":
        for item in (*definition.wall_supports, *definition.wall_stories):
            if isinstance(item, dict):
                extra_x.extend((item.get("x_start"), item.get("x_end")))
                extra_y.append(item.get("elevation"))
    return extra_x, extra_y


def story_nodes(model, definition, story):
    u, v, _, _ = PLANES[definition.plane]
    elev, x0, x1 = story["elevation"], story["x_start"], story["x_end"]
    nodes = [
        node for node in model.nodes.values()
        if math.isclose((node.X, node.Y, node.Z)[v] - definition.origin[v], elev, abs_tol=1e-7)
        and x0 - 1e-7 <= (node.X, node.Y, node.Z)[u] - definition.origin[u] <= x1 + 1e-7
    ]
    if not nodes:
        raise ValueError(f"Wall story {story['name']} has no generated nodes; check openings and elevation.")
    return nodes


def apply_shear_wall_supports_and_loads(model, definition):
    u, v, normal, _ = PLANES[definition.plane]
    for node in model.nodes.values():
        coords = tuple(value - origin for value, origin in zip((node.X, node.Y, node.Z), definition.origin))
        inplane_fixed = any(
            math.isclose(coords[v], sup["elevation"], abs_tol=1e-7)
            and sup["x_start"] - 1e-7 <= coords[u] <= sup["x_end"] + 1e-7
            for sup in definition.wall_supports
        )
        if not definition.wall_supports:
            on_edges = (
                math.isclose(coords[u], 0., abs_tol=1e-8),
                math.isclose(coords[u], definition.width, rel_tol=1e-10, abs_tol=1e-8),
                math.isclose(coords[v], 0., abs_tol=1e-8),
                math.isclose(coords[v], definition.height, rel_tol=1e-10, abs_tol=1e-8),
            )
            inplane_fixed = any(
                definition.edges[edge] != "Free"
                for edge, on in zip(EDGES, on_edges) if on
            )
        fixed = [False] * 6
        fixed[normal] = fixed[3] = fixed[4] = fixed[5] = True
        if inplane_fixed:
            fixed[u] = fixed[v] = True
        model.def_support(node.name, **dict(zip(("support_DX", "support_DY", "support_DZ",
                                                 "support_RX", "support_RY", "support_RZ"), fixed)))
    stories_by_name = {story["name"]: story_nodes(model, definition, story) for story in definition.wall_stories}
    u_force = ("FX", "FY", "FZ")[u]
    v_force = ("FX", "FY", "FZ")[v]
    for load in definition.wall_loads:
        nodes = stories_by_name[load["story"]]
        direction = u_force if load["kind"] == "shear" else v_force
        per_node = (load["magnitude"] if load["kind"] == "shear" else -load["magnitude"]) / len(nodes)
        for node in nodes:
            model.add_node_load(node.name, direction, per_node, load["case"])
    for load in definition.point_loads:
        target = next((node.name for node in model.nodes.values()
                       if math.isclose((node.X, node.Y, node.Z)[u] - definition.origin[u], load["x"], rel_tol=1e-9, abs_tol=1e-7)
                       and math.isclose((node.X, node.Y, node.Z)[v] - definition.origin[v], load["y"], rel_tol=1e-9, abs_tol=1e-7)), None)
        if target is None:
            raise ValueError(f"No generated wall node matches point load at ({load['x']:g}, {load['y']:g}).")
        model.add_node_load(target, load["direction"], load["magnitude"], load["case"])


def shear_wall_equilibrium(model, definition, combination):
    """Independent 6-component force and moment balance for in-plane shear walls."""
    from .equilibrium import FORCE_TOLERANCE, MOMENT_TOLERANCE, RELATIVE_TOLERANCE
    from .plate_pressure import geometric_integrals
    u, v, _, _ = PLANES[definition.plane]
    area = float(geometric_integrals(definition)[0])
    factors = definition.load_combinations[combination]
    applied = np.zeros(6, dtype=float)
    stories_by_name = {story["name"]: story_nodes(model, definition, story) for story in definition.wall_stories}
    for load in definition.wall_loads:
        factor = factors.get(load["case"], 0.)
        if not factor:
            continue
        nodes = stories_by_name[load["story"]]
        total_force = float(load["magnitude"]) * factor
        per_node = (total_force if load["kind"] == "shear" else -total_force) / len(nodes)
        axis = u if load["kind"] == "shear" else v
        for node in nodes:
            f_vec = np.zeros(3)
            f_vec[axis] = per_node
            arm = np.array((node.X, node.Y, node.Z)) - definition.origin
            applied[:3] += f_vec
            applied[3:] += np.cross(arm, f_vec)
    for load in definition.point_loads:
        factor = factors.get(load["case"], 0.)
        if not factor:
            continue
        value = float(load["magnitude"]) * factor
        arm = np.zeros(3)
        arm[u], arm[v] = load["x"], load["y"]
        if load["direction"].startswith("F"):
            f_vec = np.zeros(3)
            f_vec[("FX", "FY", "FZ").index(load["direction"])] = value
            applied[:3] += f_vec
            applied[3:] += np.cross(arm, f_vec)
        else:
            m_vec = np.zeros(3)
            m_vec[("MX", "MY", "MZ").index(load["direction"])] = value
            applied[3:] += m_vec
    contributions = []
    for node in model.nodes.values():
        reaction = np.array([getattr(node, key)[combination] for key in
                             ("RxnFX", "RxnFY", "RxnFZ", "RxnMX", "RxnMY", "RxnMZ")])
        point = np.array((node.X, node.Y, node.Z)) - definition.origin
        contributions.append(np.r_[reaction[:3], reaction[3:] + np.cross(point, reaction[:3])])
    contributions = np.array(contributions)
    rows = []
    for index, component in enumerate(("FX", "FY", "FZ", "MX", "MY", "MZ")):
        total = math.fsum(contributions[:, index])
        residual = math.fsum((applied[index], total))
        tolerance = (FORCE_TOLERANCE if index < 3 else MOMENT_TOLERANCE) + RELATIVE_TOLERANCE * math.fsum(
            [abs(applied[index]), *abs(contributions[:, index])])
        if not all(math.isfinite(value) for value in (total, residual, tolerance)) or abs(residual) > tolerance:
            raise ValueError(f"Shear wall equilibrium failed for {combination}: {component} residual {residual:.6g} (limit {tolerance:.6g}), canonical kip/in units.")
        rows.append(dict(component=component, applied=float(applied[index]), reaction=total, residual=residual, tolerance=tolerance))
    return float(applied[u]), rows, np.zeros(3), area


def _unique_sorted(values):
    ordered = sorted(values)
    unique = []
    for i in range(len(ordered) - 1):
        if not math.isclose(ordered[i], ordered[i + 1]):
            unique.append(float(ordered[i]))
    unique.append(float(ordered[-1]))
    return unique


def _inside_any_opening(x, y, w, h, openings):
    for opng in openings:
        ox, oy, ow, oh = opng["x_left"], opng["y_bott"], opng["width"], opng["height"]
        if (round(x, 10) >= round(ox, 10)
                and round(x + w, 10) <= round(ox + ow, 10)
                and round(y, 10) >= round(oy, 10)
                and round(y + h, 10) <= round(oy + oh, 10)):
            return True
    return False


def identify_piers(definition, elements):
    u, v, _, _ = PLANES[definition.plane]
    x_vals = [0., definition.width]
    y_vals = [0., definition.height]
    for opng in definition.openings:
        x_vals.extend((opng["x_left"], opng["x_left"] + opng["width"]))
        y_vals.extend((opng["y_bott"], opng["y_bott"] + opng["height"]))
    x_vals = _unique_sorted(x_vals)
    y_vals = _unique_sorted(y_vals)
    piers = {}
    count = 1
    for i in range(len(x_vals) - 1):
        for j in range(len(y_vals) - 1):
            x, y = x_vals[i], y_vals[j]
            w, h = x_vals[i + 1] - x, y_vals[j + 1] - y
            if not _inside_any_opening(x, y, w, h, definition.openings):
                piers[f"P{count}"] = {"name": f"P{count}", "x": x, "y": y, "width": w, "height": h, "elements": []}
                count += 1
    # Merge horizontally first, then vertically (matching Pynite.ShearWall._identify_piers).
    merged = True
    while merged:
        merged = False
        snapshot = list(piers.items())
        for k1, p1 in snapshot:
            for k2, p2 in snapshot:
                if (k1 != k2 and math.isclose(p1["y"], p2["y"])
                        and math.isclose(p1["x"] + p1["width"], p2["x"])
                        and math.isclose(p1["height"], p2["height"])):
                    piers[k1]["width"] = p1["width"] + p2["width"]
                    del piers[k2]
                    merged = True
                    break
            if merged:
                break
    merged = True
    while merged:
        merged = False
        snapshot = list(piers.items())
        for k1, p1 in snapshot:
            for k2, p2 in snapshot:
                if (k1 != k2 and math.isclose(p1["x"], p2["x"])
                        and math.isclose(p1["y"] + p1["height"], p2["y"])
                        and math.isclose(p1["width"], p2["width"])):
                    piers[k1]["height"] = p1["height"] + p2["height"]
                    del piers[k2]
                    merged = True
                    break
            if merged:
                break
    ordered = []
    for index, pier in enumerate(piers.values(), 1):
        pier["name"] = f"P{index}"
        ordered.append(pier)
    for element in elements:
        xi = (element.i_node.X, element.i_node.Y, element.i_node.Z)[u] - definition.origin[u]
        yi = (element.i_node.X, element.i_node.Y, element.i_node.Z)[v] - definition.origin[v]
        xm = (element.m_node.X, element.m_node.Y, element.m_node.Z)[u] - definition.origin[u]
        ym = (element.m_node.X, element.m_node.Y, element.m_node.Z)[v] - definition.origin[v]
        x_avg, y_avg = (xi + xm) / 2., (yi + ym) / 2.
        for pier in ordered:
            if (round(x_avg, 10) >= round(pier["x"], 10)
                    and round(x_avg, 10) <= round(pier["x"] + pier["width"], 10)
                    and round(y_avg, 10) >= round(pier["y"], 10)
                    and round(y_avg, 10) <= round(pier["y"] + pier["height"], 10)):
                pier["elements"].append(element)
    return ordered


def identify_coupling_beams(definition, elements):
    u, v, _, _ = PLANES[definition.plane]
    x_vals = [0., definition.width]
    y_vals = [0., definition.height]
    for opng in definition.openings:
        x_vals.extend((opng["x_left"], opng["x_left"] + opng["width"]))
        y_vals.extend((opng["y_bott"], opng["y_bott"] + opng["height"]))
    x_vals = _unique_sorted(x_vals)
    y_vals = _unique_sorted(y_vals)
    beams = {}
    count = 1
    for j in range(len(y_vals) - 1):
        for i in range(len(x_vals) - 1):
            x, y = x_vals[i], y_vals[j]
            w, h = x_vals[i + 1] - x, y_vals[j + 1] - y
            if not _inside_any_opening(x, y, w, h, definition.openings):
                beams[f"B{count}"] = {"name": f"B{count}", "x": x, "y": y, "length": w, "height": h, "elements": []}
                count += 1
    # Merge vertically first, then horizontally, then drop y == 0 (matching Pynite.ShearWall._identify_coupling_beams).
    merged = True
    while merged:
        merged = False
        snapshot = list(beams.items())
        for k1, b1 in snapshot:
            for k2, b2 in snapshot:
                if (k1 != k2 and math.isclose(b1["x"], b2["x"])
                        and math.isclose(b1["y"] + b1["height"], b2["y"])
                        and math.isclose(b1["length"], b2["length"])):
                    beams[k1]["height"] = b1["height"] + b2["height"]
                    del beams[k2]
                    merged = True
                    break
            if merged:
                break
    merged = True
    while merged:
        merged = False
        snapshot = list(beams.items())
        for k1, b1 in snapshot:
            for k2, b2 in snapshot:
                if (k1 != k2 and math.isclose(b1["y"], b2["y"])
                        and math.isclose(b1["x"] + b1["length"], b2["x"])
                        and math.isclose(b1["height"], b2["height"])):
                    beams[k1]["length"] = b1["length"] + b2["length"]
                    del beams[k2]
                    merged = True
                    break
            if merged:
                break
    ordered = []
    index = 1
    for beam in beams.values():
        if math.isclose(beam["y"], 0., abs_tol=1e-9):
            continue
        beam["name"] = f"B{index}"
        ordered.append(beam)
        index += 1
    for element in elements:
        xi = (element.i_node.X, element.i_node.Y, element.i_node.Z)[u] - definition.origin[u]
        yi = (element.i_node.X, element.i_node.Y, element.i_node.Z)[v] - definition.origin[v]
        xm = (element.m_node.X, element.m_node.Y, element.m_node.Z)[u] - definition.origin[u]
        ym = (element.m_node.X, element.m_node.Y, element.m_node.Z)[v] - definition.origin[v]
        x_avg, y_avg = (xi + xm) / 2., (yi + ym) / 2.
        for beam in ordered:
            if (round(x_avg, 10) >= round(beam["x"], 10)
                    and round(x_avg, 10) <= round(beam["x"] + beam["length"], 10)
                    and round(y_avg, 10) >= round(beam["y"], 10)
                    and round(y_avg, 10) <= round(beam["y"] + beam["height"], 10)):
                beam["elements"].append(element)
    return ordered


def recover_piers_and_beams(definition, elements, combination):
    u, v, _, _ = PLANES[definition.plane]
    pier_results = []
    for pier in identify_piers(definition, elements):
        P, M, V = 0., 0., 0.
        for plate in pier["elements"]:
            xi = (plate.i_node.X, plate.i_node.Y, plate.i_node.Z)[u] - definition.origin[u]
            yi = (plate.i_node.X, plate.i_node.Y, plate.i_node.Z)[v] - definition.origin[v]
            xj = (plate.j_node.X, plate.j_node.Y, plate.j_node.Z)[u] - definition.origin[u]
            if math.isclose(yi, pier["y"], abs_tol=1e-7):
                f = plate.f(combination)
                Pi, Pj = float(f[1, 0]), float(f[7, 0])
                P += -Pi - Pj
                xi_p = xi - (pier["x"] + pier["width"] / 2.)
                xj_p = xj - (pier["x"] + pier["width"] / 2.)
                M += -(Pi * xi_p + Pj * xj_p)
                Vi, Vj = -float(f[0, 0]), -float(f[6, 0])
                V += -Vi - Vj
        denom = V * pier["width"]
        m_vl = M / denom if abs(denom) > 1e-12 else 0.
        pier_results.append({
            "name": pier["name"], "x": float(pier["x"]), "y": float(pier["y"]),
            "width": float(pier["width"]), "height": float(pier["height"]),
            "P": float(P), "M": float(M), "V": float(V), "M_VL": float(m_vl),
            "element_count": len(pier["elements"]),
        })
    beam_results = []
    for beam in identify_coupling_beams(definition, elements):
        P, M, V = 0., 0., 0.
        for plate in beam["elements"]:
            xi = (plate.i_node.X, plate.i_node.Y, plate.i_node.Z)[u] - definition.origin[u]
            yi = (plate.i_node.X, plate.i_node.Y, plate.i_node.Z)[v] - definition.origin[v]
            yn = (plate.n_node.X, plate.n_node.Y, plate.n_node.Z)[v] - definition.origin[v]
            if math.isclose(xi, beam["x"], abs_tol=1e-7):
                f = plate.f(combination)
                Pi, Pn = float(f[0, 0]), float(f[18, 0])
                P += -Pi - Pn
                yi_cb = yi - (beam["y"] + beam["height"] / 2.)
                yn_cb = yn - (beam["y"] + beam["height"] / 2.)
                M += -(Pi * yi_cb + Pn * yn_cb)
                Vi, Vn = -float(f[1, 0]), -float(f[19, 0])
                V += -Vi - Vn
        denom = V * beam["height"]
        m_vh = M / denom if abs(denom) > 1e-12 else 0.
        beam_results.append({
            "name": beam["name"], "x": float(beam["x"]), "y": float(beam["y"]),
            "length": float(beam["length"]), "height": float(beam["height"]),
            "P": float(P), "M": float(M), "V": float(V), "M_VH": float(m_vh),
            "element_count": len(beam["elements"]),
        })
    return pier_results, beam_results


def recover_story_stiffnesses(model, definition, K11, D1_indices):
    from scipy.sparse.linalg import spsolve
    if not definition.wall_stories or K11.shape == (0, 0):
        return {}
    u, _, _, _ = PLANES[definition.plane]
    index_map = {dof_idx: pos for pos, dof_idx in enumerate(D1_indices)}
    stiffnesses = {}
    V_ref = 100.
    for story in definition.wall_stories:
        nodes = story_nodes(model, definition, story)
        rhs = np.zeros(len(D1_indices), dtype=float)
        per_node = V_ref / len(nodes)
        for node in nodes:
            dof = node.ID * 6 + u
            if dof in index_map:
                rhs[index_map[dof]] += per_node
        if not np.any(rhs):
            stiffnesses[story["name"]] = 0.
            continue
        d1 = spsolve(K11, rhs)
        d_max = 0.
        for node in nodes:
            dof = node.ID * 6 + u
            if dof in index_map:
                val = float(d1[index_map[dof]])
                if val > d_max:
                    d_max = val
        stiffnesses[story["name"]] = float(V_ref / d_max) if d_max > 1e-15 else 0.
    return stiffnesses


def pier_beam_table(result, units):
    headers = [
        "Kind", "ID", f"Local x ({units.length})", f"Local y ({units.length})",
        f"Length / width ({units.length})", f"Height ({units.length})",
        f"Shear V ({units.force})", f"Moment M ({units.moment})",
        f"Axial P ({units.force})", "Shear span ratio",
    ]
    rows = []
    for pier in result.get("piers", ()):
        rows.append([
            "Pier", pier["name"],
            pier["x"] * units.length_factor, pier["y"] * units.length_factor,
            pier["width"] * units.length_factor, pier["height"] * units.length_factor,
            pier["V"] * units.force_factor, pier["M"] * units.factor("moment"),
            pier["P"] * units.force_factor, pier["M_VL"],
        ])
    for beam in result.get("coupling_beams", ()):
        rows.append([
            "Coupling beam", beam["name"],
            beam["x"] * units.length_factor, beam["y"] * units.length_factor,
            beam["length"] * units.length_factor, beam["height"] * units.length_factor,
            beam["V"] * units.force_factor, beam["M"] * units.factor("moment"),
            beam["P"] * units.force_factor, beam["M_VH"],
        ])
    return headers, rows


def write_pier_beam_csv(path, result, units):
    headers, rows = pier_beam_table(result, units)
    context = [
        result["combination"],
        "; ".join(f"{case}: {factor:g}" for case, factor in result["factors"].items()),
        result["snapshot_id"], result["analyzed_at"], result["model_signature"],
    ]
    with open(path, "w", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(headers + ["Combination", "Case factors", "Snapshot", "Analyzed UTC", "Model signature"])
        writer.writerows([*row, *context] for row in rows)
