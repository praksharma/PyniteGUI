"""Uncoupled surface geometry owned by spatial projects, not solver nodes."""
from functools import lru_cache
import json

from .mesh_model import MeshDefinition, generate_mesh, mesh_geometry
from .model import identifier


SURFACE_ANALYSIS_LIMIT = (
    "This project contains uncoupled surface geometry. Mixed frame/slab analysis "
    "is not enabled yet: surface nodes are not shared with frame joints, and "
    "surface loads and supports are not assigned. Use the separate rectangular "
    "plate workspace for plate-only analysis, or remove the surfaces to analyze "
    "the frame. No frame-only result will be produced for this project."
)
MAX_PROJECT_SURFACE_ELEMENTS = 4096


@lru_cache(maxsize=32)
def _geometry(recipe):
    definition = MeshDefinition.from_dict(json.loads(recipe))
    names, elements, points, cells = mesh_geometry(generate_mesh(definition))
    # Cache only immutable geometry, not live solvers or project-owned objects.
    return (tuple(names), tuple(elements), tuple(map(tuple, points.tolist())),
            tuple(map(tuple, cells.tolist())))


def surface_geometry(definition):
    return _geometry(json.dumps(definition.to_dict(), sort_keys=True, allow_nan=False))


def validate_surfaces(project):
    if not isinstance(project.surfaces, dict) or len(project.surfaces) > 16:
        raise ValueError("Use at most 16 surface meshes per spatial project.")
    total = 0
    for name, definition in project.surfaces.items():
        if (not identifier(name) or not isinstance(definition, MeshDefinition)
                or name != definition.name):
            raise ValueError("Surface keys must match their mesh names and be valid identifiers.")
        if name in {*project.nodes, *project.members, *project.loads}:
            raise ValueError(f"Surface {name}: choose a name distinct from nodes, members and loads.")
        total += definition.validate()
    if total > MAX_PROJECT_SURFACE_ELEMENTS:
        raise ValueError(f"Combined surface meshes exceed {MAX_PROJECT_SURFACE_ELEMENTS} elements.")
    for definition in project.surfaces.values():
        surface_geometry(definition)


def put_surface(project, definition, previous=None):
    definition = MeshDefinition.from_dict(definition.to_dict())
    if definition.name in project.surfaces and definition.name != previous:
        raise ValueError(f"Surface {definition.name} already exists; choose another mesh name.")
    if previous is not None:
        if previous not in project.surfaces:
            raise ValueError("The surface being edited no longer exists.")
        del project.surfaces[previous]
    project.surfaces[definition.name] = definition


def surface_payloads(project):
    payloads = []
    for name, definition in project.surfaces.items():
        _, _, points, cells = surface_geometry(definition)
        payloads.append({"name": name, "nodes": [{"position": list(p)} for p in points],
                         "surfaces": [list(cell) for cell in cells]})
    return payloads
