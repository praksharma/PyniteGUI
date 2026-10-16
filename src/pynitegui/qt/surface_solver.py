"""Conforming rectangular Quad assembly, independent of the native editor.

No nearest-face ties or rigid links: only coincident nodes share six DOFs.
PyNite physical members subsequently subdivide at mesh nodes on their axes.
"""
import math
from itertools import product

import numpy as np

from .spatial_surfaces import surface_geometry


TOLERANCE = 1e-8  # Canonical inches, not a display-unit-dependent snap distance.


def face_weights(points):
    points = np.asarray(points, dtype=float)
    vector = np.cross(points[1] - points[0], points[3] - points[0])
    area = float(np.linalg.norm(vector))
    return area, vector / area, points.mean(axis=0)


def attach_surfaces(project, model):
    """Add bounded, conforming rectangular shells to an existing frame solver.

    Returns stable solver-node maps for deformation/results. Project geometry
    is never changed, and no restraints are added to surface nodes.
    """
    if any(mesh.generator != "rectangle" or mesh.element_type != "Quad" for mesh in project.surfaces.values()):
        raise ValueError("Coupled analysis supports rectangular Quad meshes only.")
    offsets = tuple(product((-1, 0, 1), repeat=3))
    buckets = {}

    def key(point):
        return tuple(math.floor(float(value) / TOLERANCE) for value in point)

    def register(name, point):
        buckets.setdefault(key(point), []).append((name, np.asarray(point)))

    def coincident(point):
        cell = key(point)
        matches = [name for offset in offsets for name, other in
                   buckets.get(tuple(a+b for a, b in zip(cell, offset)), ())
                   if np.linalg.norm(point-other) <= TOLERANCE]
        if len(matches) > 1:
            raise ValueError("Ambiguous coincident joints within the surface connection tolerance.")
        return matches[0] if matches else None

    for name, node in model.nodes.items():
        register(name, (node.X, node.Y, node.Z))
    maps, polygons, used_faces = {}, [], set()
    for index, (name, definition) in enumerate(project.surfaces.items()):
        _, _, points, cells = surface_geometry(definition)
        points = np.array(points)
        names = []
        for number, point in enumerate(points):
            node_name = coincident(point)
            if node_name is None:
                node_name = model.unique_name(model.nodes, f"__S{index}N{number}_")
                model.add_node(node_name, *point)
                register(node_name, point)
            names.append(node_name)
        material = definition.material
        material_name = model.unique_name(model.materials, f"__S{index}Material_")
        model.add_material(material_name, material.E, material.G, material.nu, material.rho)
        elements = []
        for number, cell in enumerate(cells):
            vertices = [names[i] for i in cell]
            face = frozenset(vertices)
            if face in used_faces:
                raise ValueError("Overlapping duplicate surface elements are not supported.")
            used_faces.add(face)
            element_name = model.unique_name(model.quads, f"__S{index}Q{number}_")
            model.add_quad(element_name, *vertices, definition.thickness, material_name,
                           definition.kx_mod, definition.ky_mod)
            elements.append(element_name)
            polygon = points[list(cell)]
            polygons.append((name, vertices, polygon))
            for case, pressure in getattr(project, "surface_pressures", {}).get(name, {}).items():
                model.add_quad_surface_pressure(element_name, pressure, case)
            if project.self_weight_case is not None:
                area, normal, _ = face_weights(polygon)
                gravity = np.array((0., -material.rho * definition.thickness * project.self_weight_factor, 0.))
                normal_pressure = float(gravity @ normal)
                model.add_quad_surface_pressure(element_name, normal_pressure, project.self_weight_case)
                tangent = gravity - normal_pressure * normal
                for vertex in vertices:
                    for direction, value in zip(("FX", "FY", "FZ"), tangent * area / 4):
                        if value:
                            model.add_node_load(vertex, direction, float(value), project.self_weight_case)
        maps[name] = {"nodes": names, "elements": elements}

    # A frame joint (or another mesh's vertex) on a face must be an actual
    # vertex, not a hanging point on its edge or inside the element.
    all_names = list(model.nodes)
    all_points = np.array([(n.X, n.Y, n.Z) for n in model.nodes.values()])
    adjacency = {name: set() for name in model.nodes}
    for surface, vertices, polygon in polygons:
        low, high = polygon.min(axis=0), polygon.max(axis=0)
        inside = np.all((all_points >= low-TOLERANCE) & (all_points <= high+TOLERANCE), axis=1)
        if any(all_names[i] not in vertices for i in np.flatnonzero(inside)):
            raise ValueError(f"Surface {surface}: nonmatching joint or hanging mesh node on a face. Add matching control lines or revise the mesh size.")
        for vertex in vertices:
            adjacency[vertex].update(vertices)
        # Prevent a beam from passing through a shell without a shared node.
        axis = int(np.argmin(high-low))
        for member in project.members.values():
            a, b = (np.array(project.nodes[n].coords) for n in (member.start, member.end))
            delta = b-a
            if abs(delta[axis]) > TOLERANCE:
                fraction = (low[axis]-a[axis])/delta[axis]
                if -TOLERANCE <= fraction <= 1+TOLERANCE:
                    point = a+fraction*delta
                    if np.all(point >= low-TOLERANCE) and np.all(point <= high+TOLERANCE) and coincident(point) is None:
                        raise ValueError(f"Member {member.name} crosses {surface} without a mesh node. Add matching control lines.")
            elif abs(a[axis]-low[axis]) <= TOLERANCE:
                left, right = 0., 1.
                for i in range(3):
                    if i == axis:
                        continue
                    if abs(delta[i]) <= TOLERANCE:
                        if not low[i]-TOLERANCE <= a[i] <= high[i]+TOLERANCE:
                            right = -1.
                    else:
                        bounds = sorted(((low[i]-a[i])/delta[i], (high[i]-a[i])/delta[i]))
                        left, right = max(left, bounds[0]), min(right, bounds[1])
                if right-left > TOLERANCE / max(np.linalg.norm(delta), 1.):
                    first, last = a+left*delta, a+right*delta
                    if coincident(first) is None or coincident(last) is None:
                        raise ValueError(f"Member {member.name} does not follow the mesh grid on {surface}. Add matching control lines.")

    # Reject positive-area coplanar overlaps, including partially overlapping
    # meshes whose vertices happen not to lie on one another's faces.
    lows = np.array([polygon.min(axis=0) for _, _, polygon in polygons])
    highs = np.array([polygon.max(axis=0) for _, _, polygon in polygons])
    owners = np.array([name for name, _, _ in polygons])
    axes = np.argmin(highs-lows, axis=1)
    for i, axis in enumerate(axes):
        candidates = (owners[i+1:] != owners[i]) & (axes[i+1:] == axis) & (abs(lows[i+1:, axis]-lows[i, axis]) <= TOLERANCE)
        widths = np.minimum(highs[i], highs[i+1:][candidates])-np.maximum(lows[i], lows[i+1:][candidates])
        if np.any(np.all(widths[:, [j for j in range(3) if j != axis]] > TOLERANCE, axis=1)):
            raise ValueError("Coplanar surface meshes overlap; remove the overlapping region.")
    for name, member in project.members.items():
        nodes = [node for node, point in zip(all_names, all_points) if project.member_position(name, *point) is not None]
        if member.kind == "truss" and len(nodes) > 2:
            raise ValueError(f"Member {name}: split truss members explicitly at surface nodes to preserve axial-only behaviour.")
        a, b = (np.asarray(project.nodes[n].coords) for n in (member.start, member.end))
        length = float(np.linalg.norm(b-a))
        direction = (b-a)/length
        for node in nodes:
            point = np.array((model.nodes[node].X, model.nodes[node].Y, model.nodes[node].Z))
            distance = float(np.linalg.norm(point-a-direction*((point-a) @ direction)))
            if distance > 1e-12*(1+length):
                raise ValueError(f"Member {name}: nearby mesh node is not exactly on the beam axis. Align the mesh before analysis.")
        for node in nodes:
            adjacency[node].update(nodes)
    visited, pending = set(), [next(iter(adjacency))]
    while pending:
        node = pending.pop()
        if node not in visited:
            visited.add(node)
            pending.extend(adjacency[node]-visited)
    if len(visited) != len(adjacency):
        raise ValueError("Disconnected frame/surface components. Align mesh vertices with frame joints; proximity is not a connection.")
    model._pynitegui_surfaces = maps
    return maps
