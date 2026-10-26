"""Undeformed geometry bounds for explicit, presentation-only navigation."""


def selection_bounds(project, selections):
    points = []
    spatial = getattr(project, "dimension", "2D") == "3D"

    def point(name):
        node = project.nodes[name]
        return tuple(node.coords) if spatial else (node.x, node.y, 0.)

    for kind, name in selections:
        if name not in getattr(project, kind, {}):
            continue
        if kind == "nodes":
            points.append(point(name))
        elif kind == "members":
            member = project.members[name]
            points.extend((point(member.start), point(member.end)))
        elif kind == "loads":
            load = project.loads[name]
            if load.target in project.nodes:
                points.append(point(load.target))
            elif load.target in project.members:
                member = project.members[load.target]
                a, b = point(member.start), point(member.end)
                for fraction in ((load.position, load.end_position) if load.kind == "distributed" else (load.position,)):
                    points.append(tuple(left+(right-left)*fraction for left, right in zip(a, b)))
        elif kind == "surfaces" and spatial:
            from .spatial_surfaces import surface_geometry
            points.extend(surface_geometry(project.surfaces[name])[2])
    if not points:
        return None
    low = [min(point[axis] for point in points) for axis in range(3)]
    high = [max(point[axis] for point in points) for axis in range(3)]
    margin = max(max(right-left for left, right in zip(low, high))*.12, project.grid*2, 1.)
    return [[value-margin for value in low], [value+margin for value in high]]
