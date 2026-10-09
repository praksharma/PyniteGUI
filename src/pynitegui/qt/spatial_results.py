"""Unit-aware spatial result sampling shared by viewport, detail, and exports."""
import math
import numpy as np
from Pynite import FEModel3D

from .spatial_model import DOFS, FORCES


QUANTITIES = ("axial", "shear_y", "shear_z", "torque", "moment_y", "moment_z", "dy", "dz")
LABELS = ("N", "Vy", "Vz", "T", "My", "Mz", "dy", "dz")
UNITS = ("force", "force", "force", "moment", "moment", "moment", "length", "length")
DIAGRAM_AXES = (1, 1, 2, 1, 2, 1)


def diagram_metadata(project, result, kind, scale, samples):
    """Scale one result component consistently across all members, in model units."""
    if result is None or kind not in QUANTITIES[:6] or not samples:
        return None
    index = QUANTITIES.index(kind)
    values = np.concatenate([sample[:, index] for sample in samples])
    low, high = float(values.min()), float(values.max())
    peak = max(abs(low), abs(high))
    extent = max(max(n.coords[i] for n in project.nodes.values()) - min(n.coords[i] for n in project.nodes.values())
                 for i in range(3))
    quantity = UNITS[index]
    return {"kind": kind, "label": LABELS[index], "axis": DIAGRAM_AXES[index],
            "factor": .15 * max(extent, project.grid) * scale / peak if peak else 0.,
            "unit": getattr(project.units, quantity), "displayFactor": project.units.to_display(1., quantity),
            "minimum": project.units.to_display(low, quantity), "maximum": project.units.to_display(high, quantity),
            "combination": result.combination,
            "color": "axial" if index in (0, 3) else "shear" if index in (1, 2) else "moment"}


def member_axes(project, name, result=None):
    if result is not None:
        return result.solver.members[name].T()[:3, :3]
    member = project.members[name]
    model = FEModel3D()
    material, section = project.materials[member.material], project.sections[member.section]
    model.add_material(material.name, material.E, material.G, material.nu, material.rho)
    model.add_section(section.name, section.A, section.Iy, section.Iz, section.J)
    for node in (member.start, member.end):
        model.add_node(node, *project.nodes[node].coords)
    model.add_member(name, member.start, member.end, member.material, member.section, rotation=member.roll)
    return model.members[name].T()[:3, :3]


def member_values(result, name, distance):
    member, combo = result.solver.members[name], result.combination
    return (member.axial(distance, combo), member.shear("Fy", distance, combo), member.shear("Fz", distance, combo),
            member.torque(distance, combo), member.moment("My", distance, combo), member.moment("Mz", distance, combo),
            member.deflection("dy", distance, combo), member.deflection("dz", distance, combo))


def sampled_member(project, result, name):
    definition = project.members[name]
    length = math.dist(project.nodes[definition.start].coords, project.nodes[definition.end].coords)
    breaks = {0., length}
    for load in project.loads.values():
        if load.target == name:
            breaks.add(load.position * length)
            if load.kind == "distributed":
                breaks.add(load.end_position * length)
    boundaries = sorted(breaks)
    points, queries = [], []
    for left, right in zip(boundaries, boundaries[1:]):
        xs = np.linspace(left, right, max(3, math.ceil(60 * (right - left) / length) + 1))
        q = xs.copy()
        epsilon = min((right - left) * 1e-5, max(length * 1e-8, 1e-8))
        if left:
            q[0] += epsilon
        if right < length:
            q[-1] -= epsilon
        points.extend(xs)
        queries.extend(q)
    values = np.array([member_values(result, name, x) for x in queries])
    solver = result.solver.members[name]
    local = np.array([[solver.deflection(axis, x, result.combination) for axis in ("dx", "dy", "dz")] for x in queries])
    return np.array(points), values, local @ solver.T()[:3, :3]


def result_table(project, result, kind):
    units = project.units
    if kind == "nodes":
        headers = ["Node", *(f"{dof} ({units.length if i < 3 else 'rad'})" for i, dof in enumerate(DOFS)),
                   *(f"{force} ({units.force if i < 3 else units.moment})" for i, force in enumerate(FORCES))]
        quantities = ("length",) * 3 + ("rotation",) * 3 + ("force",) * 3 + ("moment",) * 3
        return headers, [[name, *(units.to_display(value, quantity) for value, quantity in
                                 zip((*displacement, *result.reactions[name]), quantities))] for name, displacement in result.displacements.items()]
    if kind != "members":
        raise ValueError("Unknown spatial export type.")
    headers = ["Member", "Station", f"x ({units.length})", *(f"{label} ({getattr(units, quantity)})" for label, quantity in zip(LABELS, UNITS))]
    rows = []
    for name, member in result.solver.members.items():
        for label, x in (("Start", 0.), ("End", member.L())):
            rows.append([name, label, units.to_display(x, "length"), *(units.to_display(value, quantity)
                         for value, quantity in zip(member_values(result, name, x), UNITS))])
        for label, prefix in (("Minimum", "min"), ("Maximum", "max")):
            values = (getattr(member, prefix + "_axial")(result.combination),
                      *(getattr(member, prefix + "_shear")(axis, result.combination) for axis in ("Fy", "Fz")),
                      getattr(member, prefix + "_torque")(result.combination),
                      *(getattr(member, prefix + "_moment")(axis, result.combination) for axis in ("My", "Mz")),
                      *(getattr(member, prefix + "_deflection")(axis, result.combination) for axis in ("dy", "dz")))
            rows.append([name, label, "", *(units.to_display(value, quantity) for value, quantity in zip(values, UNITS))])
    return headers, rows


def definition_tables(project):
    from .reports import model_definition_tables
    from .model import Project
    metadata = Project(materials=project.materials, default_material=project.default_material, sections=project.sections,
                       default_section=project.default_section, unit_system=project.unit_system,
                       load_cases=project.load_cases, default_load_case=project.default_load_case, combinations=project.combinations)
    shared = model_definition_tables(metadata)
    units = project.units
    nodes = (["Node", *(f"{axis} ({units.length})" for axis in ("X", "Y", "Z")), "Support", "Rigid DOFs", "Springs"],
             [[node.name, *(units.to_display(value, "length") for value in node.coords), node.support,
               ", ".join(dof for dof, fixed in zip(DOFS, node.restraints) if fixed) or "None",
               "; ".join(f"{dof}: {units.to_display(k, 'stiffness' if i < 3 else 'rotational_stiffness'):.6g} {units.stiffness if i < 3 else units.rotational_stiffness}"
                         for i, (dof, k) in enumerate(zip(DOFS, node.springs)) if k) or "None"] for node in project.nodes.values()])
    members = (["Member", "Start", "End", "Material", "Section", "Roll (deg)"],
               [[member.name, member.start, member.end, member.material, member.section, member.roll] for member in project.members.values()])
    def loads(definitions):
        rows = []
        for load in definitions:
            quantity = "intensity" if load.kind == "distributed" else "moment" if load.is_moment else "force"
            rows.append([load.name, load.target, load.case, load.kind, load.direction, units.to_display(load.magnitude, quantity),
                         getattr(units, quantity), load.position if load.target in project.members else "",
                         units.to_display(load.end_magnitude, "intensity") if load.kind == "distributed" else "",
                         load.end_position if load.kind == "distributed" else ""])
        return rows
    headers = ["Load", "Target", "Case", "Type", "Direction", "Magnitude / start", "Units", "Start fraction", f"End ({units.intensity})", "End fraction"]
    return [("Nodes and Supports (3D)", *nodes), ("Members and Assignments (3D)", *members), *shared[2:4],
            ("Manual Loads (Unfactored)", headers, loads(project.loads.values())),
            ("Generated Self-Weight (Unfactored)", headers, loads(project.self_weight_loads())), shared[-1]]
