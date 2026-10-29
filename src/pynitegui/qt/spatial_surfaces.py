"""Project surface recipes, bounded geometry and explicit analysis opt-in."""
from functools import lru_cache
import json

from .mesh_model import MeshDefinition, generate_mesh, mesh_geometry
from .model import identifier


SURFACE_ANALYSIS_LIMIT = (
    "This project contains uncoupled surface geometry. Mixed frame/slab analysis "
    "is disabled. Select a surface and enable Coupled analysis (experimental) "
    "to include rectangular Quad slabs and their pressure loads. Mesh nodes "
    "must match frame joints; no frame-only result will silently ignore surfaces."
)
MAX_PROJECT_SURFACE_ELEMENTS = 4096


def surface_analysis_issue(project):
    if not getattr(project, "surfaces", {}):
        return None
    from .spatial_releases import has_rotational_releases
    if has_rotational_releases(project):
        return "Spatial rotational releases are frame-only. Released frame/shell interfaces are not validated."
    if not project.surface_analysis_enabled:
        return SURFACE_ANALYSIS_LIMIT
    if any(mesh.generator != "rectangle" or mesh.element_type != "Quad" for mesh in project.surfaces.values()):
        return "Coupled analysis currently supports rectangular Quad meshes only. Other mesh families remain geometry-only."
    return None


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
    from .model import finite_number
    if not isinstance(project.surfaces, dict) or len(project.surfaces) > 16:
        raise ValueError("Use at most 16 surface meshes per spatial project.")
    if type(project.surface_analysis_enabled) is not bool:
        raise ValueError("Coupled surface analysis must be a boolean.")
    if not isinstance(project.surface_pressures, dict):
        raise ValueError("Surface pressures must be keyed by surface and load case.")
    for name, pressures in project.surface_pressures.items():
        if name not in project.surfaces or not isinstance(pressures, dict):
            raise ValueError("Surface pressures require an existing surface.")
        if any(case not in project.load_cases or not finite_number(value) or abs(value) > 1e6
               for case, value in pressures.items()):
            raise ValueError("Surface pressures require valid load cases and finite values within +/-1e6 kip/in2.")
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
    from .surface_supports import validate_supports
    validate_supports(project)


def put_surface(project, definition, previous=None):
    definition = MeshDefinition.from_dict(definition.to_dict())
    if definition.name in project.surfaces and definition.name != previous:
        raise ValueError(f"Surface {definition.name} already exists; choose another mesh name.")
    if previous is not None:
        if previous not in project.surfaces:
            raise ValueError("The surface being edited no longer exists.")
        del project.surfaces[previous]
        if previous in project.surface_pressures:
            project.surface_pressures[definition.name] = project.surface_pressures.pop(previous)
        if previous in project.surface_supports:
            project.surface_supports[definition.name] = project.surface_supports.pop(previous)
    project.surfaces[definition.name] = definition


def surface_payloads(project, result=None, case_filter=None):
    payloads = []
    for name, definition in project.surfaces.items():
        _, _, points, cells = surface_geometry(definition)
        nodes = [{"position": list(p)} for p in points]
        mapping = getattr(result.solver, "_pynitegui_surfaces", {}).get(name) if result else None
        if mapping:
            for node, solver_name in zip(nodes, mapping["nodes"]):
                node["displacement"] = list(result.displacements[solver_name][:3])
        factors = project.combinations[result.combination] if result else {case: 1. for case in project.load_cases}
        pressures = [{"case": case, "value": value*factors.get(case, 0.)}
                     for case, value in project.surface_pressures.get(name, {}).items()
                     if case_filter is not False and (case_filter is None or case_filter == case) and value*factors.get(case, 0.)]
        weight_case = project.self_weight_case
        gravity = (-definition.material.rho*definition.thickness*project.self_weight_factor*factors.get(weight_case, 0.)
                   if project.surface_analysis_enabled and weight_case is not None and case_filter is not False
                   and (case_filter is None or case_filter == weight_case) else 0.)
        from .surface_supports import support_segments
        payloads.append({"name": name, "nodes": nodes, "pressures": pressures,
                         "supportEdges": support_segments(project, name),
                         "gravity": gravity, "weightCase": weight_case,
                         "pressureUnit": project.units.pressure, "pressureFactor": project.units.factor("pressure"),
                         "surfaces": [list(cell) for cell in cells]})
    return payloads
