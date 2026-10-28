"""Geometry-owned outer-edge restraints, resolved anew on every assembly.

Directions are global. At a shared joint rigid restraints are the union of all
owners. A spring on a newly fixed DOF is rejected rather than silently removed.
"""
import numpy as np

from .spatial_surfaces import surface_geometry


EDGES = ("left", "right", "bottom", "top")
DOFS = ("DX", "DY", "DZ", "RX", "RY", "RZ")
PLANE_AXES = {"XY": (0, 1, 2), "XZ": (0, 2, 1), "YZ": (1, 2, 0)}


def edge_indices(definition, points, edge):
    """Indices on an outer rectangle edge; opening rims are never selected."""
    u, v, _ = PLANE_AXES[definition.plane]
    axis = u if edge in ("left", "right") else v
    extent = definition.parameters["width" if axis == u else "height"]
    coordinate = definition.origin[axis] + (extent if edge in ("right", "top") else 0.)
    return np.flatnonzero(np.abs(np.asarray(points)[:, axis] - coordinate) <= 1e-8).tolist()


def validate_supports(project):
    assignments = project.surface_supports
    if not isinstance(assignments, dict):
        raise ValueError("Surface supports must be keyed by surface and outer edge.")
    for name, edges in assignments.items():
        if name not in project.surfaces or not isinstance(edges, dict):
            raise ValueError("Surface supports require an existing surface and an edge map.")
        definition = project.surfaces[name]
        if definition.generator != "rectangle" or definition.element_type != "Quad":
            raise ValueError("Surface edge supports require a rectangular Quad mesh.")
        if set(edges) - set(EDGES):
            raise ValueError("Surface support edges are left, right, bottom and top.")
        points = surface_geometry(definition)[2]
        for edge, dofs in edges.items():
            if (not isinstance(dofs, list) or not dofs or any(not isinstance(dof, str) or dof not in DOFS for dof in dofs)
                    or len(set(dofs)) != len(dofs)):
                raise ValueError("Surface edge supports need unique global DOFs: DX, DY, DZ, RX, RY, RZ; omit free edges.")
            if len(edge_indices(definition, points, edge)) < 2:
                raise ValueError(f"Surface {name}: supported {edge} edge has no material segment.")


def resolved_supports(project, name):
    """Local mesh-node index -> global DOFs, including corner unions."""
    points = surface_geometry(project.surfaces[name])[2]
    resolved = {}
    for edge, dofs in project.surface_supports.get(name, {}).items():
        for index in edge_indices(project.surfaces[name], points, edge):
            resolved.setdefault(index, set()).update(dofs)
    return resolved


def apply_supports(project, model, maps):
    for name, mapping in maps.items():
        for index, dofs in resolved_supports(project, name).items():
            node = model.nodes[mapping["nodes"][index]]
            for dof in dofs:
                if getattr(node, "spring_" + dof)[0] is not None:
                    raise ValueError(f"Surface {name}: edge restraint conflicts with a support spring at {node.name} {dof}.")
                setattr(node, "support_" + dof, True)


def support_segments(project, name):
    """Material boundary segments for honest support display, including notches."""
    definition = project.surfaces[name]
    _, _, points, cells = surface_geometry(definition)
    rows = []
    for edge, dofs in project.surface_supports.get(name, {}).items():
        indices = set(edge_indices(definition, points, edge))
        segments = set()
        for cell in cells:
            for a, b in zip(cell, (*cell[1:], cell[0])):
                if a in indices and b in indices:
                    segments.add(tuple(sorted((a, b))))
        rows.append({"edge": edge, "dofs": [dof for dof in DOFS if dof in dofs],
                     "segments": [[list(points[a]), list(points[b])] for a, b in sorted(segments)]})
    return rows
