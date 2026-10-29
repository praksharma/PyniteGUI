"""Validated, source-preserving candidates for native modelling previews."""
from dataclasses import dataclass, fields, replace
import math

import numpy as np

from .construction import coordinates
from .model import Node, Member, finite_number
from .spatial_model import SpatialNode, SpatialMember

TOL = 1e-8
MAX_ADDITIONS = 2000


@dataclass
class GeometryPlan:
    definition: object
    selections: list
    summary: str


def spatial(project):
    return getattr(project, "dimension", "2D") == "3D"


def unique_name(project, prefix):
    used = {key for collection in ("nodes", "members", "loads", "surfaces")
            for key in getattr(project, collection, {})}
    return project.next_name(prefix, used)


def support_state(node):
    return node.restraints, node.springs, (node.support_angle if node.support == "inclined" else None)


def clear_support(node):
    node.support = "free"
    node.support_angle = 0.
    for field in fields(node):
        if field.name.startswith("restraint_"):
            setattr(node, field.name, False)
        elif field.name.startswith("spring_"):
            setattr(node, field.name, 0.)


def copy_support(source, target):
    for field in fields(source):
        if field.name in ("support", "support_angle") or field.name.startswith(("restraint_", "spring_")):
            setattr(target, field.name, getattr(source, field.name))


def place_node(candidate, point, template=None, *, reuse=False, supports=False):
    hits = [name for name in candidate.nodes if math.dist(coordinates(candidate, name), point) <= TOL]
    if len(hits) > 1:
        raise ValueError("Several nodes are within the connection tolerance. Resolve them before adding geometry.")
    if hits:
        if not reuse:
            raise ValueError(f"Node collision at {hits[0]}. Enable explicit coincident-node reuse or change the placement.")
        if template is not None and supports and support_state(template) != support_state(candidate.nodes[hits[0]]):
            raise ValueError(f"Support conflict at {hits[0]}. Disable support copying or resolve supports before reuse.")
        return hits[0], True
    name = unique_name(candidate, "N")
    cls = SpatialNode if spatial(candidate) else Node
    node = replace(template, name=name) if template is not None else cls(name, *point[:2], **({"z": point[2]} if spatial(candidate) else {}))
    node.x, node.y = point[:2]
    if spatial(candidate):
        node.z = point[2]
    if not supports:
        clear_support(node)
    candidate.nodes[name] = node
    return name, False


def check_candidate(original, candidate):
    candidate.validate()
    # Keep unrelated pre-existing findings, but never introduce new implicit
    # intersections/overlaps. Independent disconnected copies are intentional.
    def problems(project):
        result = set()
        names = list(project.members)
        for i, first in enumerate(names):
            for second in names[i+1:]:
                try:
                    intersection = project.member_intersection(first, second)
                    if intersection and any(TOL < f < 1-TOL for f in intersection):
                        result.add(f"Members {first} and {second} cross without an explicit shared joint.")
                except ValueError as error:
                    result.add(str(error))
        for name in names:
            member = project.members[name]
            for node in project.nodes:
                if node not in (member.start, member.end):
                    fraction = project.member_position(name, *coordinates(project, node))
                    if fraction is not None and 0 < fraction < 1:
                        result.add(f"Node {node} lies inside {name} without an explicit shared joint.")
        return result
    introduced = problems(candidate) - problems(original)
    if introduced:
        raise ValueError(sorted(introduced)[0]+" Adjust the placement or split/connect the geometry explicitly first.")


def transform_matrix(operation, angle=0., axis="Z"):
    if operation in ("move", "repeat"):
        return np.eye(3)
    if axis not in "XYZ" or len(axis) != 1:
        raise ValueError("Choose global X, Y or Z.")
    if operation == "mirror":
        result = np.eye(3)
        result["XYZ".index(axis), "XYZ".index(axis)] = -1.
        return result
    if operation != "rotate" or not finite_number(angle):
        raise ValueError("Choose a valid transform and finite rotation angle.")
    vector = np.eye(3)["XYZ".index(axis)]
    x, y, z = vector
    cross = np.array([[0., -z, y], [z, 0., -x], [-y, x, 0.]])
    radians = math.radians(angle)
    return np.eye(3)*math.cos(radians)+(1-math.cos(radians))*np.outer(vector, vector)+math.sin(radians)*cross


def orient_member(original, candidate, old_name, new_name, matrix):
    if not spatial(candidate):
        return
    from .spatial_results import member_axes
    old_y = member_axes(original, old_name)[1]
    new = candidate.members[new_name]
    new.roll = 0.
    basis = member_axes(candidate, new_name)
    desired = matrix @ old_y
    # Mirror maps x/y; z is recomputed by right-hand rule. Local component
    # names retain their meanings rather than reflecting global load vectors.
    new.roll = math.degrees(math.atan2(float(desired @ basis[2]), float(desired @ basis[1])))


def plan_transform(project, selections, operation, *, offset=(0., 0., 0.), origin=(0., 0., 0.),
                   angle=0., axis="Z", copies=1, copy=False, copy_loads=False, copy_supports=False, reuse=False):
    project.validate()
    identities = list(dict.fromkeys(tuple(item) for item in selections))
    if not identities or any(k not in ("nodes", "members") or n not in getattr(project, k) for k, n in identities):
        raise ValueError("Select nodes and/or members only. Selected members include their end nodes.")
    if any(not finite_number(v) for v in (*offset, *origin)) or len(offset) != 3 or len(origin) != 3:
        raise ValueError("Offsets and reference points need three finite coordinates.")
    if not spatial(project) and (offset[2] != 0 or origin[2] != 0 or (operation == "rotate" and axis != "Z") or (operation == "mirror" and axis not in ("X", "Y"))):
        raise ValueError("Planar transforms stay in XY: rotate about Z or mirror across an X/Y-normal line.")
    if type(copies) is not int or not 1 <= copies <= 50:
        raise ValueError("Use between 1 and 50 additional copies.")
    copying = copy or operation == "repeat"
    count = copies if operation == "repeat" else 1
    members = [n for k, n in identities if k == "members"]
    nodes = list(dict.fromkeys([n for k, n in identities if k == "nodes"]+
                              [n for m in members for n in (project.members[m].start, project.members[m].end)]))
    if copying and count*(len(nodes)+len(members)) > MAX_ADDITIONS:
        raise ValueError(f"Use at most {MAX_ADDITIONS} candidate nodes and members per operation.")
    if not copying and getattr(project, "surfaces", {}):
        raise ValueError("Moving frame joints in a project with surfaces is not supported by this tool. Surface recipes and coupling need a separate coordinated edit.")
    matrix = transform_matrix(operation, angle, axis)
    offset, origin = np.array(offset), np.array(origin)
    if operation not in ("move", "repeat") and np.any(offset):
        raise ValueError("Rotation/mirror use a reference point, not a translation offset.")
    candidate, selected, reused = project.clone(), [], set()
    dimensions = 3 if spatial(project) else 2
    for index in range(1, count+1):
        mapping = {}
        for name in nodes:
            old = coordinates(project, name)
            position = np.array((*old, 0.) if dimensions == 2 else old)
            point = tuple((origin+matrix@(position-origin)+index*offset)[:dimensions])
            if copying:
                new, hit = place_node(candidate, point, project.nodes[name], reuse=reuse, supports=copy_supports)
                if hit:
                    reused.add(new)
            else:
                new = name
                node = candidate.nodes[new]
                node.x, node.y = point[:2]
                if spatial(project):
                    node.z = point[2]
            mapping[name] = new
            selected.append(("nodes", new))
        member_map = {}
        for name in members:
            old = project.members[name]
            new = unique_name(candidate, "M") if copying else name
            candidate.members[new] = replace(old, name=new, start=mapping[old.start], end=mapping[old.end])
            member_map[name] = new
            orient_member(project, candidate, name, new, matrix)
            selected.append(("members", new))
        if copying and copy_loads:
            for load in project.loads.values():
                target = member_map.get(load.target) if load.target in project.members else mapping.get(load.target)
                if target is not None:
                    name = unique_name(candidate, "L")
                    candidate.loads[name] = replace(load, name=name, target=target)
    if not copying:
        # Node-only edits can also move complete incident members rigidly.
        for name, member in project.members.items():
            if name not in members and member.start in nodes and member.end in nodes:
                orient_member(project, candidate, name, name, matrix)
    if candidate.to_dict() == project.to_dict():
        raise ValueError("This transform does not change the model.")
    check_candidate(project, candidate)
    attached = sum(name not in members and (m.start in nodes or m.end in nodes) for name, m in project.members.items()) if not copying else 0
    loads_added = len(candidate.loads)-len(project.loads)
    summary = (f"{operation.title()}: {count if copying else 0} additional copy/copies; {len(nodes)} source nodes, {len(members)} source members.\n"
               f"{len(candidate.nodes)-len(project.nodes)} new nodes, {len(candidate.members)-len(project.members)} new members, {loads_added} copied loads.\n"
               f"Reused joints: {', '.join(sorted(reused)) or 'none'}. {attached} unselected incident members change with moved joints.\n"
               "Global loads and support/spring axes stay global. Local load directions follow member axes; stations and end releases keep start/end meaning.\n"
               "3D section local y follows the transform; local z uses the right-hand rule. Self-weight follows added geometry. Groups/levels are not copied.")
    return GeometryPlan(candidate, list(dict.fromkeys(selected)), summary)


def spacing_list(text, units):
    try:
        values = [units.from_display(float(value.strip()), "length") for value in text.split(",")]
    except (ValueError, TypeError):
        raise ValueError("Enter comma-separated positive spacings in the displayed length units.") from None
    if not 1 <= len(values) <= 40 or any(not finite_number(v) or v <= TOL for v in values):
        raise ValueError("Use 1 to 40 finite, positive spacings.")
    return values


def plan_generator(project, kind, bays, heights=(), *, origin=(0., 0.), material=None,
                   beam_section=None, column_section=None, support="fixed", reuse=False):
    project.validate()
    if spatial(project):
        raise ValueError("These generators create planar XY projects. Use repeat/copy for spatial patterns.")
    if kind not in ("beam", "frame"):
        raise ValueError("Choose Beam or Frame.")
    if not 1 <= len(bays) <= 40 or any(not finite_number(v) or v <= TOL for v in bays):
        raise ValueError("Use 1 to 40 positive bay/span widths.")
    if kind == "frame" and (not 1 <= len(heights) <= 40 or any(not finite_number(v) or v <= TOL for v in heights)):
        raise ValueError("Use 1 to 40 positive storey heights.")
    if len(origin) != 2 or not all(finite_number(v) for v in origin):
        raise ValueError("Enter a finite XY insertion point.")
    material = material or project.default_material
    beam_section, column_section = beam_section or project.default_section, column_section or project.default_section
    if material not in project.materials or any(s not in project.sections for s in (beam_section, column_section)):
        raise ValueError("Choose existing materials and sections.")
    if support not in ("free", "pin", "fixed"):
        raise ValueError("Choose Free, Pin or Fixed base supports.")
    xs, ys = [origin[0]], [origin[1]]
    for width in bays:
        xs.append(xs[-1]+width)
    if kind == "frame":
        for height in heights:
            ys.append(ys[-1]+height)
    members_count = len(bays) if kind == "beam" else len(bays)*len(heights)+(len(bays)+1)*len(heights)
    if len(xs)*len(ys)+members_count > MAX_ADDITIONS:
        raise ValueError(f"Use at most {MAX_ADDITIONS} generated nodes and members per operation.")
    candidate, grid, selected, reused = project.clone(), {}, [], []
    for j, y in enumerate(ys):
        for i, x in enumerate(xs):
            template = Node("", x, y)
            if kind == "frame" and j == 0:
                template.support = support
            elif kind == "beam":
                template.support = "pin" if i == 0 else "roller"
            name, hit = place_node(candidate, (x, y), template, reuse=reuse, supports=True)
            grid[i, j] = name
            selected.append(("nodes", name))
            if hit:
                reused.append(name)
    def add(a, b, section):
        name = unique_name(candidate, "M")
        candidate.members[name] = Member(name, grid[a], grid[b], material, section)
        selected.append(("members", name))
    if kind == "beam":
        for i in range(len(bays)):
            add((i, 0), (i+1, 0), beam_section)
    else:
        for j in range(1, len(ys)):
            for i in range(len(xs)):
                add((i, j-1), (i, j), column_section)
            for i in range(len(bays)):
                add((i, j), (i+1, j), beam_section)
    check_candidate(project, candidate)
    units = project.units
    summary = (f"{kind.title()}: {len(bays)} spans/bays"+(f", {len(heights)} storeys" if kind == "frame" else "")+
               f". {len(candidate.nodes)-len(project.nodes)} new nodes, {members_count} new members.\n"
               f"Width {units.to_display(sum(bays), 'length'):.6g} {units.length}; height {units.to_display(sum(heights) if kind == 'frame' else 0., 'length'):.6g} {units.length}.\n"
               f"Reused joints: {', '.join(reused) or 'none'}. Material: {material}; beams: {beam_section}; columns: {column_section}.\n"
               +(f"Base supports: {support}." if kind == "frame" else "Continuous unreleased spans: first support pin, other supports vertical rollers.")+
               " No manual loads, diaphragms, sizing or design checks. Enabled self-weight includes generated members.")
    return GeometryPlan(candidate, selected, summary)


def plan_merge(project, target, source, tolerance, *, support_policy="reject", combine_loads=False):
    project.validate()
    if target == source or target not in project.nodes or source not in project.nodes:
        raise ValueError("Choose two distinct existing nodes.")
    if not finite_number(tolerance) or tolerance < 0 or math.dist(coordinates(project, target), coordinates(project, source)) > tolerance:
        raise ValueError("The source is outside the specified merge distance.")
    if getattr(project, "surfaces", {}):
        raise ValueError("Node merging with surface recipes requires a coordinated coupling edit and is not supported here.")
    if support_policy not in ("reject", "target", "source"):
        raise ValueError("Choose a support conflict policy.")
    a, b = project.nodes[target], project.nodes[source]
    if support_state(a) != support_state(b) and support_policy == "reject":
        raise ValueError("Supports/springs differ. Explicitly choose which node's support to retain.")
    has_loads = all(any(load.target == name for load in project.loads.values()) for name in (target, source))
    if has_loads and not combine_loads:
        raise ValueError("Both joints have loads. Explicitly allow retaining both load sets at the target.")
    candidate = project.clone()
    if support_policy == "source":
        copy_support(b, candidate.nodes[target])
    affected = []
    for name, member in candidate.members.items():
        if source in (member.start, member.end):
            member.start = target if member.start == source else member.start
            member.end = target if member.end == source else member.end
            affected.append(("members", name))
    loads = []
    for load in candidate.loads.values():
        if load.target == source:
            load.target = target
            loads.append(load.name)
    for group in candidate.groups.values():
        group["nodes"] = list(dict.fromkeys(target if node == source else node for node in group["nodes"]))
    del candidate.nodes[source]
    check_candidate(project, candidate)
    return GeometryPlan(candidate, [("nodes", target), *affected],
                        f"Merge {source} into {target}; retain target coordinates.\n"
                        f"Rewrite {len(affected)} member endpoints, {len(loads)} nodal loads and saved group references.\n"
                        f"Support policy: {support_policy}. Both load sets remain separate and additive.\n"
                        "No members or loads are deleted. Global loads stay global; local loads follow changed member axes. Analyze again after Apply.")


def preview_geometry(original, plan):
    """Read-only changed geometry for both renderers; no selectable identities."""
    if plan is None:
        return {"nodes": [], "lines": []}
    candidate = plan.definition
    nodes = [list(coordinates(candidate, name)) for name in candidate.nodes
             if name not in original.nodes or coordinates(candidate, name) != coordinates(original, name)]
    lines = []
    for name, member in candidate.members.items():
        points = [list(coordinates(candidate, n)) for n in (member.start, member.end)]
        old = original.members.get(name)
        if old is None or points != [list(coordinates(original, n)) for n in (old.start, old.end)]:
            lines.append(points)
    return {"nodes": nodes, "lines": lines}
