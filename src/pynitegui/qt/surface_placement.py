"""Rectangle placement from existing frame geometry; no solver connectivity."""
from dataclasses import dataclass
import math

from .mesh_model import MeshDefinition


TOLERANCE = 1e-8
PLANE_AXES = {"XY": (0, 1, 2), "XZ": (0, 2, 1), "YZ": (2, 1, 0)}


@dataclass(frozen=True)
class RectanglePlacement:
    plane: str
    origin: tuple
    width: float
    height: float
    x_control: tuple = ()
    y_control: tuple = ()

    def recipe(self, base):
        if base.generator != "rectangle":
            raise ValueError("Frame fitting is available for Rectangle meshes only.")
        result = MeshDefinition.from_dict(base.to_dict())
        result.plane, result.origin = self.plane, list(self.origin)
        result.parameters = {"width": self.width, "height": self.height}
        # Retain user openings/control lines; incompatible options fail validation.
        result.x_control = sorted(set([*result.x_control, *self.x_control]))
        result.y_control = sorted(set([*result.y_control, *self.y_control]))
        result.validate()
        return result


def _rectangle(project, names):
    if len(names) < 4:
        raise ValueError("Select four rectangular corner nodes or the complete perimeter members.")
    points = [project.nodes[name].coords for name in sorted(names)]
    low = [min(point[i] for point in points) for i in range(3)]
    high = [max(point[i] for point in points) for i in range(3)]
    planes = [(plane, axes) for plane, axes in PLANE_AXES.items()
              if high[axes[2]]-low[axes[2]] <= TOLERANCE
              and min(high[axes[0]]-low[axes[0]], high[axes[1]]-low[axes[1]]) > TOLERANCE]
    if len(planes) != 1:
        raise ValueError("The boundary must lie in one global XY, XZ or YZ plane; tilted surfaces are not supported.")
    plane, (u, v, _) = planes[0]
    def near(a, b):
        return abs(a-b) <= TOLERANCE
    for a in (low[u], high[u]):
        for b in (low[v], high[v]):
            if not any(near(point[u], a) and near(point[v], b) for point in points):
                raise ValueError("All four rectangle corners must exist; an L-shaped or incomplete boundary cannot be filled automatically.")
    if any(not (near(point[u], low[u]) or near(point[u], high[u])
                or near(point[v], low[v]) or near(point[v], high[v])) for point in points):
        raise ValueError("Select only the rectangle perimeter, not interior nodes or members.")
    controls = [tuple(sorted(set(point[axis]-low[axis] for point in points
                                 if low[axis]+TOLERANCE < point[axis] < high[axis]-TOLERANCE)))
                for axis in (u, v)]
    return RectanglePlacement(plane, tuple(low), high[u]-low[u], high[v]-low[v], *controls)


def _covered_perimeter(project, placement, members, strict=True):
    u, v, _ = PLANE_AXES[placement.plane]
    low_u, low_v = placement.origin[u], placement.origin[v]
    high_u, high_v = low_u+placement.width, low_v+placement.height
    intervals = {"left": [], "right": [], "bottom": [], "top": []}
    for member in members:
        a, b = project.nodes[member.start].coords, project.nodes[member.end].coords
        found = False
        for axis, edge, label, other in ((u, low_u, "left", v), (u, high_u, "right", v),
                                          (v, low_v, "bottom", u), (v, high_v, "top", u)):
            if abs(a[axis]-edge) <= TOLERANCE and abs(b[axis]-edge) <= TOLERANCE:
                intervals[label].append(sorted((a[other], b[other])))
                found = True
                break
        if strict and not found:
            raise ValueError("Selected members must follow the four rectangle edges, without diagonals or interior beams.")
    for label, start, end in (("left", low_v, high_v), ("right", low_v, high_v),
                               ("bottom", low_u, high_u), ("top", low_u, high_u)):
        cursor = start
        for a, b in sorted(intervals[label]):
            if a > cursor+TOLERANCE:
                break
            cursor = max(cursor, b)
        if cursor < end-TOLERANCE:
            raise ValueError("The perimeter is not closed. Select all four edges, including any split segments.")


def selected_rectangle(project, selections):
    if not selections or any(kind not in ("nodes", "members") for kind, _ in selections):
        raise ValueError("Select corner nodes or perimeter members in the main model first.")
    names, members = set(), []
    for kind, name in selections:
        if name not in getattr(project, kind):
            raise ValueError("A selected frame entity no longer exists.")
        if kind == "nodes":
            names.add(name)
        else:
            member = project.members[name]
            members.append(member)
            names.update((member.start, member.end))
    result = _rectangle(project, names)
    if members:
        _covered_perimeter(project, result, members)
    return result


def frame_levels(project):
    """Offer complete axis-aligned horizontal perimeters, highest Y first."""
    groups = []
    for member in project.members.values():
        a, b = project.nodes[member.start].coords, project.nodes[member.end].coords
        if abs(a[1]-b[1]) > TOLERANCE or math.dist(a, b) <= TOLERANCE:
            continue
        group = next((group for group in groups if abs(group[0]-a[1]) <= TOLERANCE), None)
        if group is None:
            group = (a[1], [])
            groups.append(group)
        group[1].append(member)
    results = []
    for _, members in groups:
        names = {name for member in members for name in (member.start, member.end)}
        # Interior beams may exist; infer the outer perimeter from its extremes.
        x0, x1 = min(project.nodes[n].x for n in names), max(project.nodes[n].x for n in names)
        z0, z1 = min(project.nodes[n].z for n in names), max(project.nodes[n].z for n in names)
        boundary = {n for n in names if min(abs(project.nodes[n].x-x0), abs(project.nodes[n].x-x1),
                                            abs(project.nodes[n].z-z0), abs(project.nodes[n].z-z1)) <= TOLERANCE}
        try:
            placement = _rectangle(project, boundary)
            _covered_perimeter(project, placement, members, strict=False)
            results.append(placement)
        except ValueError:
            continue
    return sorted(results, key=lambda placement: placement.origin[1], reverse=True)
